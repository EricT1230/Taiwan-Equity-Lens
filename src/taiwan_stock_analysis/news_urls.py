from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid"})
_MAX_PERCENT_DECODING_PASSES = 4


def safe_http_url(value: Any) -> str | None:
    """Return a link-safe absolute HTTP(S) URL, or ``None`` for untrusted input."""
    url = str(value or "").strip()
    if (
        not url
        or "\\" in url
        or any(character.isspace() for character in url)
        or _has_control_character(url)
    ):
        return None
    if _has_encoded_control_character(url):
        return None
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except (UnicodeError, ValueError):
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.netloc.endswith(":")
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
        or not _valid_http_host(hostname, parsed.netloc)
    ):
        return None
    return url


def canonical_news_url(value: Any) -> str | None:
    """Return the deterministic identity for a valid external news URL."""
    safe_url = safe_http_url(value)
    if safe_url is None:
        return None
    parsed = urlsplit(safe_url)
    hostname = parsed.hostname
    if hostname is None:  # guarded by safe_http_url; keeps the return type explicit.
        return None
    host = _canonical_host(hostname, parsed.netloc)
    if host is None:
        return None
    if ":" in host:
        authority = f"[{host}]"
    else:
        authority = host
    port = parsed.port
    if port is not None and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        authority = f"{authority}:{port}"
    pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query_key(key)
    ]
    query = urlencode(sorted(pairs))
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), authority, path, query, ""))


def _is_tracking_query_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized.startswith("utm_") or normalized in _TRACKING_QUERY_KEYS


def _has_encoded_control_character(value: str) -> bool:
    decoded = value
    for _ in range(_MAX_PERCENT_DECODING_PASSES):
        try:
            next_value = _strict_unquote(decoded)
        except UnicodeError:
            return True
        if _has_control_character(next_value):
            return True
        if next_value == decoded:
            return False
        decoded = next_value
    return _has_control_character(decoded)


def _strict_unquote(value: str) -> str:
    from urllib.parse import unquote

    return unquote(value, errors="strict")


def _valid_http_host(hostname: str, netloc: str) -> bool:
    if not hostname or "%" in hostname or _has_control_character(hostname):
        return False
    if netloc.startswith("["):
        try:
            IPv6Address(hostname)
        except ValueError:
            return False
        return True
    if ":" in hostname:
        return False
    try:
        ascii_host = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    host_core = ascii_host[:-1] if ascii_host.endswith(".") else ascii_host
    if not host_core or len(host_core.encode("ascii")) > 253:
        return False
    labels = host_core.split(".")
    if all(_NUMERIC_HOST_LABEL.fullmatch(label) for label in labels):
        return _is_canonical_ipv4(host_core)
    return all(
        len(label.encode("ascii")) <= 63
        and _DOMAIN_LABEL.fullmatch(label) is not None
        for label in labels
    )


def _canonical_host(hostname: str, netloc: str) -> str | None:
    if netloc.startswith("["):
        try:
            return IPv6Address(hostname).compressed.lower()
        except ValueError:
            return None
    try:
        ascii_host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    host_core = ascii_host[:-1] if ascii_host.endswith(".") else ascii_host
    if _is_canonical_ipv4(host_core):
        return str(IPv4Address(host_core))
    return host_core


def _is_canonical_ipv4(host: str) -> bool:
    try:
        return str(IPv4Address(host)) == host
    except ValueError:
        return False


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value)


_DOMAIN_LABEL = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII | re.IGNORECASE
)
_NUMERIC_HOST_LABEL = re.compile(r"(?:[0-9]+|0x[0-9a-f]*)", re.ASCII | re.IGNORECASE)
