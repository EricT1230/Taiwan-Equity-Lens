from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit


__all__ = ["admit_dashboard_items"]

DashboardItems = dict[str, list[dict[str, Any]]]

_DATA_MODE_KEYS = {"data_mode", "mode", "source_mode"}
_SOURCE_KEYS = {"origin", "provider", "source", "source_name"}
_URL_KEYS = {"href", "link", "original_link", "original_url", "source_url", "url"}
_FORBIDDEN_MODE_TOKENS = {"demo", "fixture", "offline", "synthetic"}
_EXAMPLE_HOSTS = {"example.com", "example.net", "example.org"}
_SOURCE_ALIASES = {
    "fubon",
    "fubonneo",
    "fubonneosdk",
    "fubonsecurities",
    "marketobservationpostsystem",
    "mops",
    "taipei exchange",
    "taipeiexchange",
    "taiwanstockexchange",
    "tpex",
    "twse",
}
_ADMISSIBLE_STATUSES = {"DELAYED", "EOD", "FRESH", "LIVE", "OK", "PARTIAL", "READY"}


def _reason(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").strip().casefold())
        if token
    }


def _normalised_identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().casefold())


_NORMALISED_SOURCE_ALIASES = {_normalised_identifier(alias) for alias in _SOURCE_ALIASES}


def _parse_observation_time(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_example_url(value: Any) -> bool:
    text = str(value or "").strip()
    try:
        hostname = (urlsplit(text).hostname or "").rstrip(".").casefold()
    except ValueError:
        return False
    return any(hostname == host or hostname.endswith(f".{host}") for host in _EXAMPLE_HOSTS)


def _is_example_path(value: Any) -> bool:
    parts = {
        part
        for part in re.split(r"[\\/]", str(value or "").strip().casefold())
        if part
    }
    return bool(parts & {"example", "examples"})


def _is_http_url(value: Any) -> bool:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.hostname)


def _news_contract_reasons(
    value: Any,
    *,
    path: str = "$",
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if key.strip().casefold() != "news":
                reasons.extend(_news_contract_reasons(child, path=child_path))
                continue
            if not isinstance(child, (list, tuple)):
                reasons.append(
                    _reason(
                        "invalid_news_contract",
                        child_path,
                        "editorial news must be a list of attributable source records",
                    )
                )
                continue
            for index, item in enumerate(child):
                item_path = f"{child_path}[{index}]"
                if not isinstance(item, Mapping):
                    reasons.append(
                        _reason(
                            "invalid_news_contract",
                            item_path,
                            "news requires source, publication time, and an HTTP(S) original link",
                        )
                    )
                    continue
                source = str(item.get("source") or "").strip()
                published_at = str(
                    item.get("published_at")
                    or item.get("publication_time")
                    or ""
                ).strip()
                original_url = (
                    item.get("original_url")
                    or item.get("original_link")
                    or item.get("url")
                    or item.get("link")
                )
                if (
                    not source
                    or _parse_observation_time(published_at) is None
                    or not _is_http_url(original_url)
                ):
                    reasons.append(
                        _reason(
                            "invalid_news_contract",
                            item_path,
                            "news requires source, publication time, and an HTTP(S) original link",
                        )
                    )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reasons.extend(_news_contract_reasons(child, path=f"{path}[{index}]"))
    return reasons


def _contamination_reasons(value: Any, *, path: str = "$") -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized_key = key.strip().casefold()
            child_path = f"{path}.{key}"
            tokens = _tokens(child)
            if normalized_key in _DATA_MODE_KEYS and tokens & _FORBIDDEN_MODE_TOKENS:
                reasons.append(
                    _reason(
                        "forbidden_data_mode",
                        child_path,
                        "production artifacts cannot contain Demo, fixture, offline, or synthetic modes",
                    )
                )
            if normalized_key in _SOURCE_KEYS and tokens & _FORBIDDEN_MODE_TOKENS:
                reasons.append(
                    _reason(
                        "forbidden_data_source",
                        child_path,
                        "production artifacts cannot contain Demo, fixture, offline, or synthetic sources",
                    )
                )
            if normalized_key in _URL_KEYS and _is_example_url(child):
                reasons.append(
                    _reason(
                        "example_reference",
                        child_path,
                        "production artifacts cannot contain example-domain references",
                    )
                )
            if (normalized_key == "path" or normalized_key.endswith("_path")) and _is_example_path(child):
                reasons.append(
                    _reason(
                        "example_reference",
                        child_path,
                        "production artifacts cannot contain example input paths",
                    )
                )
            reasons.extend(_contamination_reasons(child, path=child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reasons.extend(_contamination_reasons(child, path=f"{path}[{index}]"))
    return reasons


def _provenance_reasons(
    artifact: Mapping[str, Any],
    *,
    now: datetime,
    max_age: timedelta,
    future_tolerance: timedelta,
) -> list[dict[str, str]]:
    provenance = artifact.get("provenance")
    if not isinstance(provenance, Mapping):
        return [
            _reason(
                "missing_provenance",
                "$.provenance",
                "production artifacts require a provenance object",
            )
        ]

    reasons: list[dict[str, str]] = []
    source = str(provenance.get("source") or "").strip()
    status = str(provenance.get("status") or "").strip().upper()
    observed_at = str(provenance.get("observed_at") or "").strip()
    if not source:
        reasons.append(
            _reason("missing_source", "$.provenance.source", "provenance source is required")
        )
    elif _normalised_identifier(source) not in _NORMALISED_SOURCE_ALIASES:
        reasons.append(
            _reason(
                "unrecognised_source",
                "$.provenance.source",
                "source is not an approved production authority",
            )
        )
    if not status:
        reasons.append(
            _reason("missing_status", "$.provenance.status", "provenance status is required")
        )
    elif status not in _ADMISSIBLE_STATUSES:
        reasons.append(
            _reason(
                "invalid_status",
                "$.provenance.status",
                "status is not publishable in production",
            )
        )
    if not observed_at:
        reasons.append(
            _reason(
                "missing_observation_time",
                "$.provenance.observed_at",
                "provenance observation time is required",
            )
        )
    else:
        observed = _parse_observation_time(observed_at)
        if observed is None:
            reasons.append(
                _reason(
                    "invalid_observation_time",
                    "$.provenance.observed_at",
                    "observation time must be an ISO timestamp with a timezone",
                )
            )
        elif observed - now > future_tolerance:
            reasons.append(
                _reason(
                    "future_observation_time",
                    "$.provenance.observed_at",
                    "observation time exceeds the allowed clock-skew tolerance",
                )
            )
        elif now - observed > max_age:
            reasons.append(
                _reason(
                    "stale_observation_time",
                    "$.provenance.observed_at",
                    "observation time is older than the production freshness limit",
                )
            )
    return reasons


def admit_dashboard_items(
    items: Mapping[str, list[dict[str, Any]]],
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(days=7),
    future_tolerance: timedelta = timedelta(minutes=5),
) -> tuple[DashboardItems, dict[str, Any]]:
    """Filter production artifacts without mutating the discovered dashboard items.

    Each artifact must carry ``provenance.source``, ``provenance.status``, and a
    timezone-aware ``provenance.observed_at``. The returned items retain every
    input collection key; rejected artifacts are described only by collection,
    index, safe reason codes, and JSON-style field paths.
    """

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if max_age < timedelta(0):
        raise ValueError("max_age cannot be negative")
    if future_tolerance < timedelta(0):
        raise ValueError("future_tolerance cannot be negative")
    current = current.astimezone(timezone.utc)
    admitted: DashboardItems = {key: [] for key in items}
    by_collection = {
        key: {"admitted": 0, "rejected": 0}
        for key in items
    }
    rejections: list[dict[str, Any]] = []
    for collection, artifacts in items.items():
        for index, artifact in enumerate(artifacts):
            reasons = _provenance_reasons(
                artifact,
                now=current,
                max_age=max_age,
                future_tolerance=future_tolerance,
            )
            reasons.extend(_contamination_reasons(artifact))
            reasons.extend(_news_contract_reasons(artifact))
            if reasons:
                rejections.append(
                    {
                        "collection": collection,
                        "index": index,
                        "artifact_ref": f"{collection}[{index}]",
                        "reasons": reasons,
                    }
                )
                by_collection[collection]["rejected"] += 1
                continue
            admitted[collection].append(artifact)
            by_collection[collection]["admitted"] += 1

    admitted_count = sum(len(value) for value in admitted.values())
    by_reason = Counter(
        reason["code"]
        for rejection in rejections
        for reason in rejection["reasons"]
    )
    return admitted, {
        "mode": "production",
        "admitted_count": admitted_count,
        "rejected_count": len(rejections),
        "by_collection": by_collection,
        "by_reason": dict(sorted(by_reason.items())),
        "rejections": rejections,
    }
