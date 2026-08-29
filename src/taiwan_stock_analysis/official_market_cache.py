from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from taiwan_stock_analysis.official_snapshot_store import OfficialSnapshotStore


SnapshotLoader = Callable[[], dict[str, Any]]
_CACHEABLE_QUOTE_STATUSES = {"LIVE", "EOD"}
_CACHEABLE_BREADTH_STATUSES = {"LIVE", "EOD", "PARTIAL"}
_CACHEABLE_CATALOG_STATUSES = {"LIVE", "EOD", "FRESH", "PARTIAL"}
_CACHEABLE_BREADTH_SOURCE_STATUSES = {"LIVE", "EOD", "FRESH", "PARTIAL"}
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,19}")
_TIMESTAMP_KEYS = {
    "as_of",
    "fetched_at",
    "generated_at",
    "latest_event_at",
    "live_refreshed_at",
    "published_at",
    "source_event_time",
}
_DATE_ONLY_EVENT_SOURCE_COMPONENTS = {
    "alerts",
    "disposition_alerts",
    "fund_flow",
    "notice_alerts",
}
_EXACT_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PROVENANCE_FIELDS = {"id", "source", "url"}
_INACTIVE_SOURCE_STATUSES = {"", "NOT_CONNECTED", "STALE", "UNAVAILABLE"}
_OFFICIAL_PROVENANCE_PREFIX = re.compile(
    r"(?i)^(?:fubon|twse|tpex|mops(?:fin)?)(?:$|[\s:._/-])"
)
_OFFICIAL_DOMAINS = (
    "fbs.com.tw",
    "fubon.com",
    "fubon.com.tw",
    "tpex.org.tw",
    "twse.com.tw",
)


class OfficialMarketCache:
    """Keep only validated official snapshots and expose them as STALE fallback."""

    def __init__(self, store: OfficialSnapshotStore) -> None:
        self._store = store

    def refresh_live(
        self,
        symbols: Iterable[object],
        loader: SnapshotLoader,
    ) -> dict[str, Any]:
        dataset = _live_dataset(symbols)
        try:
            payload = loader()
        except Exception as exc:
            fallback = self._store.load_stale(
                dataset,
                reason=_safe_error_reason(exc),
            )
            if fallback is not None:
                fallback["quotes_ok"] = False
                return fallback
            raise

        if _cacheable_live(payload):
            try:
                self._store.save(dataset, payload)
            except (TypeError, ValueError):
                fallback = self._store.load_stale(
                    dataset,
                    reason="CACHE_PAYLOAD_REJECTED",
                )
                if fallback is not None:
                    fallback["quotes_ok"] = False
                    return fallback
                raise
            return payload

        fallback = self._store.load_stale(
            dataset,
            reason="UPSTREAM_CONTRACT_INVALID",
        )
        if fallback is not None:
            fallback["quotes_ok"] = False
            return fallback
        return payload

    def load_stale_live(
        self,
        symbols: Iterable[object],
        *,
        reason: str,
    ) -> dict[str, Any] | None:
        payload = self._store.load_stale(
            _live_dataset(symbols),
            reason=reason,
        )
        if payload is not None:
            payload["quotes_ok"] = False
        return payload

    def refresh_breadth(self, loader: SnapshotLoader) -> dict[str, Any]:
        try:
            payload = loader()
        except Exception as exc:
            fallback = self.load_stale_breadth(reason=_safe_error_reason(exc))
            if fallback is not None:
                return fallback
            raise

        if _current_breadth(payload):
            if not _persistable_breadth(payload):
                return payload
            try:
                self._store.save("market-breadth", payload)
            except (TypeError, ValueError):
                fallback = self.load_stale_breadth(
                    reason="CACHE_PAYLOAD_REJECTED"
                )
                if fallback is not None:
                    return fallback
                raise
            return payload

        fallback = self.load_stale_breadth(
            reason="UPSTREAM_CONTRACT_INVALID"
        )
        return fallback if fallback is not None else payload

    def load_stale_breadth(self, *, reason: str) -> dict[str, Any] | None:
        return self._store.load_stale("market-breadth", reason=reason)


def _live_dataset(symbols: Iterable[object]) -> str:
    normalized = sorted(
        {
            symbol
            for value in symbols
            if (symbol := str(value or "").strip().upper())
            and _SYMBOL.fullmatch(symbol)
        }
    )
    digest = hashlib.sha256(",".join(normalized).encode("ascii")).hexdigest()[:20]
    return f"live-market-{digest}"


def _cacheable_live(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    source_status = payload.get("source_status")
    if not isinstance(source_status, dict):
        return False
    quote_source = source_status.get("quotes")
    cache = payload.get("cache", {})
    market = payload.get("market")
    if (
        not isinstance(quote_source, dict)
        or not isinstance(cache, dict)
        or not isinstance(market, dict)
    ):
        return False
    return bool(
        payload.get("schema_version") == 1
        and payload.get("kind") == "live_market_snapshot"
        and payload.get("ok") is True
        and payload.get("quotes_ok") is True
        and _is_aware_iso_datetime(payload.get("generated_at"))
        and _timestamps_are_aware(
            payload,
            official_event_date_limit=_aware_iso_datetime_date(
                payload.get("generated_at")
            ),
        )
        and _has_required_live_rows(payload)
        and _has_only_recognized_provenance(payload.get("provider"))
        and _has_only_recognized_provenance(quote_source)
        and _active_sources_are_recognized(source_status)
        and str(payload.get("status") or "").upper()
        in _CACHEABLE_QUOTE_STATUSES
        and str(market.get("status") or "").upper()
        in _CACHEABLE_QUOTE_STATUSES
        and str(market.get("status") or "").upper()
        == str(payload.get("status") or "").upper()
        and _is_aware_iso_datetime(market.get("as_of"))
        and str(quote_source.get("status") or "").upper()
        in _CACHEABLE_QUOTE_STATUSES
        and str(quote_source.get("status") or "").upper()
        == str(payload.get("status") or "").upper()
        and _is_aware_iso_datetime(quote_source.get("fetched_at"))
        and _source_evidence_is_usable(
            quote_source,
            allowed_statuses=_CACHEABLE_QUOTE_STATUSES,
            require_observation_time=True,
        )
        and not bool(quote_source.get("partial"))
        and isinstance(payload.get("missing_symbols"), list)
        and not payload["missing_symbols"]
        and not bool(cache.get("fallback"))
        and not bool(quote_source.get("fallback"))
    )


def _is_aware_iso_datetime(value: Any) -> bool:
    return _aware_iso_datetime_date(value) is not None


def _aware_iso_datetime_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.date()


def _has_required_live_rows(payload: dict[str, Any]) -> bool:
    quotes = payload.get("quotes")
    indices = payload.get("indices")
    if not isinstance(quotes, list) or not quotes or not isinstance(indices, list):
        return False
    if not all(_valid_live_row(row) for row in [*quotes, *indices]):
        return False
    benchmark_symbols = {
        str(row.get("symbol") or "").strip()
        for row in indices
        if isinstance(row, dict)
    }
    return {"t00", "o00"}.issubset(benchmark_symbols)


def _valid_live_row(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    price = value.get("price")
    return bool(
        str(value.get("symbol") or "").strip()
        and str(value.get("status") or "").upper()
        in _CACHEABLE_QUOTE_STATUSES
        and _is_aware_iso_datetime(value.get("source_event_time"))
        and _has_only_recognized_provenance(
            {"source": value.get("source")}
        )
        and _is_finite_number(price)
    )


def _is_finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _timestamps_are_aware(
    value: Any,
    *,
    official_event_date_limit: date | None = None,
    allow_date_only_latest_event: bool = False,
    source_status_container: bool = False,
) -> bool:
    if isinstance(value, list):
        return all(
            _timestamps_are_aware(
                nested,
                official_event_date_limit=official_event_date_limit,
                allow_date_only_latest_event=allow_date_only_latest_event,
            )
            for nested in value
        )
    if not isinstance(value, dict):
        return True
    for key, nested in value.items():
        normalized_key = str(key).strip().casefold().replace("-", "_")
        if normalized_key in _TIMESTAMP_KEYS and nested is not None and nested != "":
            date_only_is_valid = (
                normalized_key == "latest_event_at"
                and allow_date_only_latest_event
                and _is_exact_iso_date_not_after(
                    nested,
                    official_event_date_limit,
                )
            )
            if not _is_aware_iso_datetime(nested) and not date_only_is_valid:
                return False
        if isinstance(nested, (dict, list)):
            child_is_source_status = normalized_key == "source_status"
            child_allows_date_only = allow_date_only_latest_event
            if source_status_container:
                child_allows_date_only = (
                    normalized_key in _DATE_ONLY_EVENT_SOURCE_COMPONENTS
                    and official_event_date_limit is not None
                )
            if not _timestamps_are_aware(
                nested,
                official_event_date_limit=official_event_date_limit,
                allow_date_only_latest_event=child_allows_date_only,
                source_status_container=child_is_source_status,
            ):
                return False
    return True


def _is_exact_iso_date_not_after(
    value: Any,
    maximum: date | None,
) -> bool:
    if (
        maximum is None
        or not isinstance(value, str)
        or _EXACT_ISO_DATE.fullmatch(value.strip()) is None
    ):
        return False
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return False
    return parsed <= maximum


def _has_only_recognized_provenance(value: Any) -> bool:
    provenance = list(_iter_provenance_values(value))
    return bool(provenance) and all(_is_official_provenance(item) for item in provenance)


def _active_sources_are_recognized(source_status: dict[str, Any]) -> bool:
    for component in source_status.values():
        if not isinstance(component, dict):
            return False
        status = str(component.get("status") or "").strip().upper()
        if status in _INACTIVE_SOURCE_STATUSES:
            continue
        if not _has_only_recognized_provenance(component):
            return False
    return True


def _iter_provenance_values(value: Any) -> Iterable[str]:
    if isinstance(value, list):
        for nested in value:
            yield from _iter_provenance_values(nested)
        return
    if not isinstance(value, dict):
        return
    for key, nested in value.items():
        normalized_key = str(key).strip().casefold().replace("-", "_")
        if normalized_key in _PROVENANCE_FIELDS and isinstance(nested, str):
            text = nested.strip()
            if text:
                yield text
        if isinstance(nested, (dict, list)):
            yield from _iter_provenance_values(nested)


def _is_official_provenance(value: str) -> bool:
    text = str(value or "").strip()
    try:
        hostname = str(urlparse(text).hostname or "").casefold().rstrip(".")
    except ValueError:
        return False
    return bool(
        _OFFICIAL_PROVENANCE_PREFIX.search(text)
        or any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in _OFFICIAL_DOMAINS
        )
        or any(
            marker in text
            for marker in (
                "富邦",
                "臺灣證券交易所",
                "台灣證券交易所",
                "證交所",
                "櫃買",
                "公開資訊觀測站",
            )
        )
    )


def _current_breadth(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    cache = payload.get("cache", {})
    coverage = payload.get("coverage")
    source_status = payload.get("source_status")
    if (
        not isinstance(cache, dict)
        or not isinstance(coverage, dict)
        or not isinstance(source_status, dict)
    ):
        return False
    catalog_source = source_status.get("catalog")
    quote_source = source_status.get("quotes")
    if not isinstance(catalog_source, dict) or not isinstance(quote_source, dict):
        return False
    return bool(
        payload.get("schema_version") == 1
        and payload.get("kind") == "market_breadth_snapshot"
        and payload.get("ok") is True
        and _valid_positive_int(coverage.get("catalog_total"))
        and _valid_breadth_rows(payload, coverage)
        and _is_aware_iso_datetime(payload.get("generated_at"))
        and _timestamps_are_aware(
            payload,
            official_event_date_limit=_aware_iso_datetime_date(
                payload.get("generated_at")
            ),
        )
        and str(payload.get("mode") or "")
        in {
            "EOD_FULL+LIVE_PAGE",
            "EOD_PARTIAL+LIVE_PAGE",
            "LIVE_FULL+OFFICIAL_EOD",
        }
        and payload.get("session_fresh") is True
        and isinstance(payload.get("live_session_fresh"), bool)
        and str(payload.get("status") or "").upper()
        in _CACHEABLE_BREADTH_STATUSES
        and str(catalog_source.get("status") or "").upper()
        in _CACHEABLE_CATALOG_STATUSES
        and str(quote_source.get("status") or "").upper()
        in _CACHEABLE_BREADTH_SOURCE_STATUSES
        and _has_only_recognized_provenance(catalog_source)
        and _has_only_recognized_provenance(quote_source)
        and _source_evidence_is_usable(
            catalog_source,
            allowed_statuses=_CACHEABLE_CATALOG_STATUSES,
        )
        and _source_evidence_is_usable(
            quote_source,
            allowed_statuses=_CACHEABLE_BREADTH_SOURCE_STATUSES,
        )
        and _active_sources_are_recognized(source_status)
        and not bool(cache.get("fallback"))
    )


def _persistable_breadth(payload: dict[str, Any]) -> bool:
    return not bool(payload.get("cached"))


def _valid_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _source_evidence_is_usable(
    component: dict[str, Any],
    *,
    allowed_statuses: set[str],
    require_observation_time: bool = False,
) -> bool:
    upstreams = component.get("upstreams")
    if upstreams is None:
        evidence: list[Any] = [component]
    elif isinstance(upstreams, list) and upstreams:
        evidence = upstreams
    else:
        return False
    for row in evidence:
        if not isinstance(row, dict):
            return False
        if str(row.get("status") or "").upper() not in allowed_statuses:
            return False
        if not _has_only_recognized_provenance(row):
            return False
        row_count = row.get("row_count")
        if row_count is not None and not _valid_positive_int(row_count):
            return False
        if require_observation_time and not any(
            _is_aware_iso_datetime(row.get(key))
            for key in ("latest_event_at", "fetched_at")
        ):
            return False
    return True


def _valid_breadth_rows(
    payload: dict[str, Any],
    coverage: dict[str, Any],
) -> bool:
    rows = payload.get("full_market")
    catalog_total = coverage.get("catalog_total")
    quoted_total = coverage.get("quoted_total")
    ratio = coverage.get("ratio")
    if (
        not isinstance(rows, list)
        or not rows
        or len(rows) != catalog_total
        or not _valid_positive_int(quoted_total)
        or quoted_total > catalog_total
        or not _is_finite_number(ratio)
        or not 0.0 <= float(ratio) <= 1.0
        or abs(float(ratio) - quoted_total / catalog_total) > 0.00001
    ):
        return False
    active_rows = 0
    for row in rows:
        if (
            not isinstance(row, dict)
            or not str(row.get("symbol") or "").strip()
            or str(row.get("market") or "").upper() not in {"TWSE", "TPEX"}
        ):
            return False
        quote_status = str(row.get("quote_status") or "").upper()
        if quote_status not in {"LIVE", "EOD", "SUSPENDED"}:
            continue
        active_rows += 1
        if not _valid_iso_date(row.get("session_date")):
            return False
        if not _has_only_recognized_provenance(
            {"source": row.get("quote_source")}
        ):
            return False
        if quote_status == "LIVE" and not _is_aware_iso_datetime(
            row.get("source_event_time")
        ):
            return False
    return active_rows >= quoted_total


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def _safe_error_reason(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "UPSTREAM_TIMEOUT"
    if isinstance(exc, ConnectionError):
        return "UPSTREAM_CONNECTION_ERROR"
    if isinstance(exc, PermissionError):
        return "UPSTREAM_PERMISSION_ERROR"
    if isinstance(exc, OSError):
        return "UPSTREAM_IO_ERROR"
    if isinstance(exc, (TypeError, ValueError)):
        return "UPSTREAM_PAYLOAD_ERROR"
    return "UPSTREAM_FAILURE"


__all__ = ["OfficialMarketCache"]
