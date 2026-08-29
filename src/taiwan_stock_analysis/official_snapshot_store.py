from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


Clock = Callable[[], datetime]

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cert_password",
    "cert_path",
    "certificate_path",
    "cookie",
    "headers",
    "personal_id",
    "sdk_token",
    "token",
}
_SECRET_KEY_SUFFIXES = (
    "accesstoken",
    "apikey",
    "apisecret",
    "authorization",
    "bearertoken",
    "certificatepassword",
    "certificatepath",
    "certpassword",
    "certpath",
    "clientsecret",
    "cookie",
    "credential",
    "idtoken",
    "password",
    "passphrase",
    "personalid",
    "privatekey",
    "privatetoken",
    "refreshtoken",
    "sdktoken",
    "secretkey",
    "sessiontoken",
)
_DEMO_MARKERS = ("fixture", "offline", "synthetic", "example.com", "example.test")
_DATASET_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
_PROVENANCE_KEYS = {
    "data_mode",
    "dataset_mode",
    "fixture",
    "mode",
    "provenance",
    "provider_mode",
    "source",
    "source_mode",
}
_SENSITIVE_REASON_MARKERS = re.compile(
    r"(?i)(?:authorization|bearer|access[\s_-]*token|refresh[\s_-]*token|"
    r"client[\s_-]*secret|password|api[\s_-]*key|sdk[\s_-]*token)"
)


class OfficialSnapshotStore:
    """Persist validated public market snapshots for explicit stale fallback."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Clock,
        max_bytes: int = 64 * 1024 * 1024,
        max_files: int = 64,
    ) -> None:
        self._root = Path(root)
        self._clock = clock
        self._max_bytes = max(1, int(max_bytes))
        self._max_files = max(1, int(max_files))

    def save(self, dataset: str, payload: dict[str, Any]) -> Path:
        _assert_dataset_name(dataset)
        _assert_cache_safe(payload)
        saved_at = self._clock()
        if not _is_timezone_aware(saved_at):
            raise ValueError("official snapshot cache clock must be timezone-aware")
        self._root.mkdir(parents=True, exist_ok=True)
        output_path = self._root / f"{dataset}.json"
        envelope = {
            "schema_version": 1,
            "kind": "official_snapshot_cache",
            "dataset": dataset,
            "saved_at": saved_at.isoformat(),
            "payload": payload,
        }
        serialized = json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        if len(serialized.encode("utf-8")) > self._max_bytes:
            raise ValueError("official snapshot exceeds the cache size limit")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._root,
                prefix=f".{dataset}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, output_path)
            self._prune_files(protected=output_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return output_path

    def _prune_files(self, *, protected: Path) -> None:
        candidates: list[tuple[int, str, Path]] = []
        for path in self._root.glob("*.json"):
            try:
                candidates.append((path.stat().st_mtime_ns, path.name, path))
            except OSError:
                continue
        excess = max(0, len(candidates) - self._max_files)
        deletable = [row for row in sorted(candidates) if row[2] != protected]
        for _, _, path in deletable[:excess]:
            try:
                path.unlink()
            except OSError:
                continue

    def load_stale(self, dataset: str, *, reason: str) -> dict[str, Any] | None:
        _assert_dataset_name(dataset)
        input_path = self._root / f"{dataset}.json"
        try:
            if input_path.stat().st_size > self._max_bytes:
                return None
            with input_path.open("rb") as handle:
                raw = handle.read(self._max_bytes + 1)
            if len(raw) > self._max_bytes:
                return None
            envelope = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(envelope, dict)
            or envelope.get("schema_version") != 1
            or envelope.get("kind") != "official_snapshot_cache"
            or envelope.get("dataset") != dataset
            or not isinstance(envelope.get("payload"), dict)
        ):
            return None
        try:
            _assert_cache_safe(envelope["payload"])
        except ValueError:
            return None
        payload = deepcopy(envelope["payload"])
        original_status = str(payload.get("status") or "UNAVAILABLE")
        original_generated_at = str(payload.get("generated_at") or "")
        _mark_snapshot_tree_stale(payload)
        payload["status"] = "STALE"
        if isinstance(payload.get("market"), dict):
            payload["market"]["status"] = "STALE"
        for key in ("quotes", "indices"):
            rows = payload.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    row["status"] = "STALE"
        if payload.get("kind") == "market_breadth_snapshot":
            _mark_breadth_payload_stale(payload)
        payload["cache"] = {
            "fallback": True,
            "saved_at": str(envelope.get("saved_at") or ""),
            "original_status": original_status,
            "original_generated_at": original_generated_at,
            "reason": _safe_cache_reason(reason),
        }
        return payload


def _safe_cache_reason(reason: Any) -> str:
    text = " ".join(str(reason or "upstream unavailable").split())[:240]
    if _SENSITIVE_REASON_MARKERS.search(text):
        return "UPSTREAM_REASON_REDACTED"
    return text or "upstream unavailable"


def _is_timezone_aware(value: Any) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _assert_dataset_name(dataset: str) -> None:
    if not isinstance(dataset, str) or _DATASET_NAME.fullmatch(dataset) is None:
        raise ValueError("invalid official snapshot dataset name")


def _mark_breadth_payload_stale(payload: dict[str, Any]) -> None:
    payload["last_observed_mode"] = str(payload.get("mode") or "")
    payload["mode"] = "STALE_FALLBACK+LIVE_PAGE"
    payload["session_fresh"] = False
    payload["live_session_fresh"] = False
    for row in payload.get("full_market") or []:
        if not isinstance(row, dict):
            continue
        quote_status = str(row.get("quote_status") or "").upper()
        if quote_status in {"LIVE", "EOD", "SUSPENDED"}:
            row["last_observed_quote_status"] = row.get("quote_status")
            row["quote_status"] = "STALE"
        if str(row.get("institutional_status") or "").upper() == "MATCHED":
            row["last_observed_institutional_status"] = row.get(
                "institutional_status"
            )
            row["institutional_status"] = "STALE"


def _mark_snapshot_tree_stale(
    value: Any,
    *,
    within_coverage: bool = False,
) -> None:
    if isinstance(value, list):
        for nested in value:
            _mark_snapshot_tree_stale(
                nested,
                within_coverage=within_coverage,
            )
        return
    if not isinstance(value, dict):
        return

    for key, nested in list(value.items()):
        normalized_key = str(key).strip().casefold().replace("-", "_")
        if normalized_key.startswith(("last_observed_", "original_")):
            continue
        if normalized_key == "source_status" and isinstance(
            nested,
            (dict, list),
        ):
            _mark_snapshot_tree_stale(
                nested,
                within_coverage=within_coverage,
            )
            continue
        if normalized_key == "status" or normalized_key.endswith("_status"):
            if nested is not None and nested != "":
                value.setdefault(f"last_observed_{key}", deepcopy(nested))
                value[key] = "STALE"
            continue
        if (
            normalized_key == "statuses"
            or normalized_key.endswith("_statuses")
        ) and isinstance(nested, dict):
            value.setdefault(f"last_observed_{key}", deepcopy(nested))
            for status_key, status_value in list(nested.items()):
                if status_value is not None and status_value != "":
                    nested[status_key] = "STALE"
            continue
        if normalized_key == "authoritative" or normalized_key.endswith(
            "_authoritative"
        ):
            if nested is True:
                value.setdefault(f"last_observed_{key}", True)
            value[key] = False
            continue
        if normalized_key == "coverage" or normalized_key.endswith("_coverage"):
            if isinstance(nested, bool):
                if nested:
                    value.setdefault(f"last_observed_{key}", True)
                value[key] = False
                continue
            if isinstance(nested, str) and nested:
                value.setdefault(f"last_observed_{key}", nested)
                value[key] = "STALE"
                continue
            if isinstance(nested, (dict, list)):
                _mark_snapshot_tree_stale(
                    nested,
                    within_coverage=True,
                )
                continue
        nested_coverage = within_coverage or normalized_key == "coverage"
        if isinstance(nested, bool) and (
            nested_coverage or "coverage" in normalized_key
        ):
            if nested:
                value.setdefault(f"last_observed_{key}", True)
            value[key] = False
            continue
        if isinstance(nested, (dict, list)):
            _mark_snapshot_tree_stale(
                nested,
                within_coverage=nested_coverage,
            )


def _assert_cache_safe(value: Any, *, field_name: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).strip().casefold().replace("-", "_")
            if _is_secret_field_name(normalized_key):
                raise ValueError("official snapshot contains a secret-bearing field")
            _assert_cache_safe(nested, field_name=normalized_key)
        return
    if isinstance(value, list):
        for nested in value:
            _assert_cache_safe(nested, field_name=field_name)
        return
    if isinstance(value, str):
        normalized_value = value.casefold()
        provenance_field = (
            field_name in _PROVENANCE_KEYS
            or field_name.endswith("_source")
            or field_name.endswith("_mode")
            or field_name.endswith("_path")
            or field_name.endswith("_url")
            or field_name in {"path", "url"}
        )
        if provenance_field and any(
            marker in normalized_value for marker in _DEMO_MARKERS
        ):
            raise ValueError("official snapshot contains demo-only provenance")


def _is_secret_field_name(normalized_key: str) -> bool:
    if normalized_key in _SECRET_KEYS:
        return True
    compact_key = re.sub(r"[^a-z0-9]", "", normalized_key.casefold())
    return any(compact_key.endswith(suffix) for suffix in _SECRET_KEY_SUFFIXES)


__all__ = ["OfficialSnapshotStore"]
