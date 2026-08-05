from __future__ import annotations

import copy
import math
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

from taiwan_stock_analysis.bounded_loader import run_bounded_loaders
from taiwan_stock_analysis.market_data_importer import build_official_profiles
from taiwan_stock_analysis.market_intelligence import _http_json
from taiwan_stock_analysis.trading_calendar import (
    TAIPEI,
    TWSE_HOLIDAY_URL,
    expected_latest_completed_session,
    parse_twse_closed_dates,
)


TWSE_PROFILE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_FINANCIAL_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
TWSE_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TWSE_VALUATION_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TWSE_DAILY_RWD_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_DAILY_FALLBACK_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

TPEX_PROFILE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_FINANCIAL_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
TPEX_REVENUE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
TPEX_VALUATION_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
TPEX_DAILY_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

JsonFetcher = Callable[[str], Any]
Clock = Callable[[], datetime]
SupportingLoader = Callable[[], dict[str, Any]]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_NON_SECURITY_RE = re.compile(r"^[0-9A-Za-z.\-]+$")
_FAILED_REFRESH_CACHE_SECONDS = 30.0
_CATALOG_BASELINE_AS_OF = "2026-07-29"
_CATALOG_BASELINE_COUNTS = {"TWSE": 1092, "TPEX": 891}
_FIRST_LOAD_MAX_DROP_RATIO = 0.01
_DEFAULT_MIN_CATALOG_COUNTS = {
    market: math.ceil(count * (1.0 - _FIRST_LOAD_MAX_DROP_RATIO))
    for market, count in _CATALOG_BASELINE_COUNTS.items()
}
_MAX_CATALOG_DROP_RATIO = 0.01
_MARKET_LOOKBACK_DAYS = 15
_BREADTH_HTTP_TIMEOUT_SECONDS = 3.0
_BREADTH_SNAPSHOT_DEADLINE_SECONDS = 25.0


class MarketBreadthService:
    """Build the official universe and optionally overlay licensed live quotes.

    The TWSE/TPEx catalog and EOD coverage remain the completeness baseline.
    A provider batch can update matching quote fields, but it only promotes the
    aggregate to ``LIVE`` after independent per-market health, session, and
    coverage checks pass.
    """

    def __init__(
        self,
        *,
        fetch_json: JsonFetcher | None = None,
        clock: Clock | None = None,
        supporting_loader: SupportingLoader | None = None,
        cache_seconds: float = 300.0,
        live_overlay_seconds: float = 5.0,
        minimum_catalog_counts: dict[str, int] | None = None,
        snapshot_deadline_seconds: float = _BREADTH_SNAPSHOT_DEADLINE_SECONDS,
    ) -> None:
        self._fetch_json = fetch_json or (
            lambda url: _http_json(
                url,
                timeout_seconds=_BREADTH_HTTP_TIMEOUT_SECONDS,
            )
        )
        self._clock = clock or (lambda: datetime.now(TAIPEI))
        self._supporting_loader = supporting_loader
        self._cache_seconds = max(30.0, float(cache_seconds))
        self._live_overlay_seconds = max(
            5.0,
            float(live_overlay_seconds),
        )
        self._snapshot_deadline_seconds = max(
            0.05,
            float(snapshot_deadline_seconds),
        )
        requested_minimums = minimum_catalog_counts or _DEFAULT_MIN_CATALOG_COUNTS
        self._minimum_catalog_counts = {
            market: max(1, int(requested_minimums.get(market) or 0))
            for market in ("TWSE", "TPEX")
        }
        self._catalog_baseline_enforced = minimum_catalog_counts is None
        self._baseline_payload: dict[str, Any] | None = None
        self._cache_payload: dict[str, Any] | None = None
        self._cache_expires_at = 0.0
        self._live_overlay_expires_at = 0.0
        self._live_overlay_enabled = False
        self._cache_lock = threading.RLock()
        self._loader_lock = threading.Lock()
        self._component_capacity = threading.BoundedSemaphore(1)
        self._deadline_local = threading.local()

    def health(self) -> dict[str, Any]:
        with self._cache_lock:
            cached = self._cache_payload
        cache_session_current = bool(
            cached
            and _cache_matches_completed_session(cached, self._now())
        )
        observed_status = str((cached or {}).get("status") or "UNAVAILABLE")
        status = (
            observed_status
            if cache_session_current
            else ("STALE" if cached else "UNAVAILABLE")
        )
        usable = bool(
            cached
            and cached.get("ok") is True
            and status not in {"UNAVAILABLE"}
        )
        ready = bool(usable and status in {"LIVE", "EOD"})
        return {
            "ok": ready,
            "process_alive": True,
            "ready": ready,
            "usable": usable,
            "kind": "market_breadth_health",
            "status": status,
            "last_observed_status": (
                observed_status if status != observed_status else ""
            ),
            "cache_session_current": cache_session_current,
            "cache_seconds": self._cache_seconds,
            "live_overlay_seconds": self._live_overlay_seconds,
            "live_overlay_enabled": self._live_overlay_enabled,
            "cached": cached is not None,
            "catalog_total": int((cached or {}).get("coverage", {}).get("catalog_total") or 0),
            "quoted_total": (
                int((cached or {}).get("coverage", {}).get("quoted_total") or 0)
                if cache_session_current
                else 0
            ),
            "live_quoted_total": (
                int(
                    (cached or {}).get("coverage", {}).get(
                        "live_quoted_total"
                    )
                    or 0
                )
                if cache_session_current
                else 0
            ),
            "refresh_after_seconds": float(
                (cached or {}).get("refresh_after_seconds")
                or self._cache_seconds
            ),
            "snapshot_deadline_seconds": self._snapshot_deadline_seconds,
        }

    def snapshot(self) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        now = self._now()
        with self._cache_lock:
            baseline_current = self._baseline_cache_current(
                now_monotonic,
                now,
            )
            if self._failed_refresh_cache_current(now_monotonic):
                return _cached_copy(self._cache_payload)
            live_refresh_due = (
                baseline_current
                and self._live_overlay_enabled
                and self._live_overlay_expires_at <= now_monotonic
            )
            if baseline_current and not live_refresh_due:
                return _cached_copy(self._cache_payload)

        with self._loader_lock:
            now_monotonic = time.monotonic()
            now = self._now()
            with self._cache_lock:
                baseline_current = self._baseline_cache_current(
                    now_monotonic,
                    now,
                )
                if self._failed_refresh_cache_current(now_monotonic):
                    return _cached_copy(self._cache_payload)
                live_refresh_due = (
                    baseline_current
                    and self._live_overlay_enabled
                    and self._live_overlay_expires_at <= now_monotonic
                )
                if baseline_current and not live_refresh_due:
                    return _cached_copy(self._cache_payload)
                stale = self._cache_payload
                baseline = self._baseline_payload
            if baseline_current and live_refresh_due and baseline is not None:
                refresh_errors: list[str] = []
                support = self._load_support(refresh_errors)
                if refresh_errors:
                    combined_errors = list(
                        dict.fromkeys(
                            [
                                *(
                                    str(error)
                                    for error in support.get("errors") or []
                                ),
                                *refresh_errors,
                            ]
                        )
                    )
                    support = {
                        **support,
                        "errors": combined_errors,
                    }
                refreshed = self._apply_live_overlay(
                    baseline,
                    support=support,
                    now=now,
                    configured_hint=True,
                )
                with self._cache_lock:
                    self._cache_payload = refreshed
                    self._live_overlay_expires_at = (
                        time.monotonic() + self._live_overlay_seconds
                    )
                return _cached_copy(refreshed)
            try:
                payload = self._build_snapshot_with_deadline(now)
                self._validate_catalog_regression(
                    payload,
                    previous=stale,
                )
            except (OSError, ValueError, TimeoutError) as exc:
                if stale is not None:
                    fallback = _mark_breadth_stale(
                        stale,
                        now=self._now(),
                        error=f"breadth: {exc}",
                    )
                else:
                    fallback = _unavailable_snapshot(self._now(), str(exc))
                with self._cache_lock:
                    self._baseline_payload = None
                    self._cache_payload = fallback
                    self._cache_expires_at = (
                        time.monotonic() + _FAILED_REFRESH_CACHE_SECONDS
                    )
                    self._live_overlay_expires_at = self._cache_expires_at
                return copy.deepcopy(fallback)
            baseline = self._official_baseline_copy(payload)
            live_overlay_enabled = bool(payload.get("live_overlay_enabled"))
            with self._cache_lock:
                self._baseline_payload = baseline
                self._cache_payload = payload
                self._cache_expires_at = time.monotonic() + self._cache_seconds
                self._live_overlay_enabled = live_overlay_enabled
                self._live_overlay_expires_at = (
                    time.monotonic()
                    + (
                        self._live_overlay_seconds
                        if live_overlay_enabled
                        else self._cache_seconds
                    )
                )
            return copy.deepcopy(payload)

    def _baseline_cache_current(
        self,
        now_monotonic: float,
        now: datetime,
    ) -> bool:
        return bool(
            self._baseline_payload is not None
            and self._cache_payload is not None
            and self._cache_expires_at > now_monotonic
            and _cache_matches_completed_session(self._baseline_payload, now)
        )

    def _failed_refresh_cache_current(
        self,
        now_monotonic: float,
    ) -> bool:
        return bool(
            self._baseline_payload is None
            and self._cache_payload is not None
            and self._cache_expires_at > now_monotonic
            and str(self._cache_payload.get("status") or "")
            in {"STALE", "UNAVAILABLE"}
        )

    def _build_snapshot_with_deadline(self, now: datetime) -> dict[str, Any]:
        deadline_at = time.monotonic() + self._snapshot_deadline_seconds
        cancelled = threading.Event()

        def build() -> dict[str, Any]:
            self._deadline_local.at = deadline_at
            self._deadline_local.cancelled = cancelled
            try:
                return self._build_snapshot(now)
            finally:
                self._deadline_local.at = None
                self._deadline_local.cancelled = None

        try:
            results, failures = run_bounded_loaders(
                {"breadth": build},
                timeout_seconds=self._snapshot_deadline_seconds,
                capacity=self._component_capacity,
            )
        finally:
            cancelled.set()
        if "breadth" in failures:
            failure = failures["breadth"]
            if isinstance(failure, (OSError, ValueError, TimeoutError)):
                raise failure
            raise RuntimeError("market breadth loader failed") from failure
        payload = results.get("breadth")
        if not isinstance(payload, dict):
            raise TimeoutError("market breadth snapshot deadline exceeded")
        return payload

    def _ensure_deadline(self) -> None:
        cancelled = getattr(self._deadline_local, "cancelled", None)
        if cancelled is not None and cancelled.is_set():
            raise TimeoutError("market breadth snapshot deadline exceeded")
        deadline = getattr(self._deadline_local, "at", None)
        if deadline is not None and time.monotonic() >= float(deadline):
            raise TimeoutError("market breadth snapshot deadline exceeded")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=TAIPEI)
        return value.astimezone(TAIPEI)

    def _validate_catalog_regression(
        self,
        payload: dict[str, Any],
        *,
        previous: dict[str, Any] | None,
    ) -> None:
        if not isinstance(previous, dict):
            return
        previous_counts = (
            (previous.get("coverage") or {}).get("market_catalog_counts") or {}
        )
        current_counts = (
            (payload.get("coverage") or {}).get("market_catalog_counts") or {}
        )
        for market in ("TWSE", "TPEX"):
            previous_count = int(previous_counts.get(market) or 0)
            current_count = int(current_counts.get(market) or 0)
            if previous_count <= 0:
                continue
            minimum_allowed = math.ceil(
                previous_count * (1.0 - _MAX_CATALOG_DROP_RATIO)
            )
            if current_count < minimum_allowed:
                raise ValueError(
                    f"{market} company catalog regressed from "
                    f"{previous_count} to {current_count}"
                )

    def _validate_catalog_counts(self, counts: dict[str, int]) -> None:
        incomplete = [
            market
            for market in ("TWSE", "TPEX")
            if int(counts.get(market) or 0)
            < self._minimum_catalog_counts[market]
        ]
        if incomplete:
            raise ValueError(
                "official company catalog is incomplete or truncated: "
                + ", ".join(
                    f"{market}={int(counts.get(market) or 0)}"
                    f"<{self._minimum_catalog_counts[market]}"
                    for market in incomplete
                )
            )

    def _catalog_matches_verified_baseline(
        self,
        counts: dict[str, int],
    ) -> bool:
        if not self._catalog_baseline_enforced:
            return True
        return all(
            int(counts.get(market) or 0)
            >= int(_CATALOG_BASELINE_COUNTS[market])
            for market in ("TWSE", "TPEX")
        )

    def _build_snapshot(self, now: datetime) -> dict[str, Any]:
        errors: list[str] = []
        self._ensure_deadline()
        (
            catalog,
            fundamentals,
            catalog_sources,
            fundamental_sources,
        ) = self._load_catalog_and_fundamentals(errors)
        self._ensure_deadline()
        holiday_rows = self._fetch_list(
            "twse-holiday-schedule",
            TWSE_HOLIDAY_URL,
            errors,
        )
        closed_dates = parse_twse_closed_dates(holiday_rows)
        calendar_source = {
            "status": "FRESH" if holiday_rows and closed_dates else "UNAVAILABLE",
            "row_count": len(holiday_rows),
            "closed_date_count": len(closed_dates),
            "closed_dates": sorted(value.isoformat() for value in closed_dates),
            "source": "TWSE holidaySchedule OpenAPI",
        }
        expected_session_date = expected_latest_completed_session(
            now,
            closed_dates=closed_dates,
        ).isoformat()
        self._ensure_deadline()
        quotes, quote_sources = self._load_quotes(
            now,
            errors,
            closed_dates=closed_dates,
        )
        self._ensure_deadline()
        valuations, valuation_sources = self._load_valuations(errors)
        self._ensure_deadline()
        revenues, revenue_sources = self._load_revenues(errors)
        self._ensure_deadline()
        official_errors = list(errors)
        support = self._load_support(errors)
        live_errors = errors[len(official_errors):]
        self._ensure_deadline()

        if not catalog:
            raise ValueError("official TWSE/TPEx company catalog returned no usable companies")
        catalog_market_counts = {
            market: int(
                (catalog_sources.get("market_counts") or {}).get(market) or 0
            )
            for market in ("TWSE", "TPEX")
        }
        self._validate_catalog_counts(catalog_market_counts)
        catalog_baseline_complete = self._catalog_matches_verified_baseline(
            catalog_market_counts
        )
        catalog_gap_by_market = {
            market: max(
                0,
                int(_CATALOG_BASELINE_COUNTS[market])
                - int(catalog_market_counts.get(market) or 0),
            )
            for market in ("TWSE", "TPEX")
        }
        fundamental_sources = _align_component_to_catalog(
            fundamental_sources,
            catalog_counts=catalog_market_counts,
        )
        valuation_sources = _align_component_to_catalog(
            valuation_sources,
            catalog_counts=catalog_market_counts,
        )
        valuation_sources = _align_valuation_to_session(
            valuation_sources,
            rows=valuations,
            as_of=now,
            closed_dates=closed_dates,
        )
        revenue_sources = _align_component_to_catalog(
            revenue_sources,
            catalog_counts=catalog_market_counts,
        )

        quote_by_key = {
            (str(row.get("market") or ""), str(row.get("symbol") or "")): row
            for row in quotes
            if str(row.get("market") or "") and str(row.get("symbol") or "")
        }
        valuation_by_key = {
            (str(row.get("market") or ""), str(row.get("symbol") or "")): row
            for row in valuations
        }
        fundamental_by_key = {
            (str(row.get("market") or ""), str(row.get("symbol") or "")): row
            for row in fundamentals
        }
        revenue_by_key = {
            (str(row.get("market") or ""), str(row.get("symbol") or "")): row
            for row in revenues
        }
        support_source_status = (
            support.get("source_status")
            if isinstance(support.get("source_status"), dict)
            else {}
        )
        live_quote_support = _assess_live_quote_support(
            support,
            catalog=catalog,
            catalog_counts=catalog_market_counts,
            catalog_baseline_complete=catalog_baseline_complete,
            as_of=now,
        )
        live_quote_by_key = live_quote_support["overlay_by_key"]

        expected_markets = ("TWSE", "TPEX")
        market_session_sets: dict[str, set[str]] = {
            market: set() for market in expected_markets
        }
        undated_quote_markets: set[str] = set()
        for row in quotes:
            market = str(row.get("market") or "")
            if market not in market_session_sets:
                continue
            session_date = str(row.get("session_date") or "")
            if _valid_session_date(session_date):
                market_session_sets[market].add(session_date)
            else:
                undated_quote_markets.add(market)
        session_dates_by_market = {
            market: max(sessions)
            for market, sessions in market_session_sets.items()
            if sessions
        }
        market_sessions_complete = all(
            len(market_session_sets[market]) == 1
            and market not in undated_quote_markets
            for market in expected_markets
        )
        distinct_sessions = sorted(set(session_dates_by_market.values()))
        cross_market_comparable = (
            market_sessions_complete
            and len(session_dates_by_market) == len(expected_markets)
            and len(distinct_sessions) == 1
        )
        session_fresh = (
            calendar_source["status"] == "FRESH"
            and
            market_sessions_complete
            and all(
                _session_date_is_fresh(
                    session_date,
                    as_of=now,
                    closed_dates=closed_dates,
                )
                for session_date in session_dates_by_market.values()
            )
        )
        aggregate_session = max(distinct_sessions, default="")
        raw_alert_source_status = support_source_status.get("alerts")
        alert_source_status = _with_authority(
            raw_alert_source_status,
            accepted_statuses={"EOD", "FRESH", "LIVE"},
        )
        disposition_source_status = _with_authority(
            _alert_component_for_type(
                raw_alert_source_status,
                alert_type="disposition",
            ),
            accepted_statuses={"EOD", "FRESH", "LIVE"},
        )
        notice_source_status = _with_authority(
            _alert_component_for_type(
                raw_alert_source_status,
                alert_type="notice",
            ),
            accepted_statuses={"EOD", "FRESH", "LIVE"},
        )
        flow_source_status = _with_authority(
            support_source_status.get("fund_flow"),
            accepted_statuses={"EOD", "FRESH", "LIVE"},
            required_event_date=aggregate_session,
        )
        disposition_authoritative = bool(
            disposition_source_status["authoritative"]
        )
        notice_authoritative = bool(notice_source_status["authoritative"])
        alerts_authoritative = disposition_authoritative or notice_authoritative
        flow_authoritative = bool(flow_source_status["authoritative"])
        alert_state = str(alert_source_status["coverage_status"])
        flow_state = str(flow_source_status["coverage_status"])
        flow_by_symbol = (
            _latest_by_symbol(support.get("fund_flow"))
            if flow_authoritative
            else {}
        )
        trusted_alerts = [
            row
            for row in support.get("alerts") or []
            if isinstance(row, dict)
            and (
                (
                    str(row.get("alert_type") or row.get("type") or "")
                    == "disposition"
                    and disposition_authoritative
                )
                or (
                    str(row.get("alert_type") or row.get("type") or "")
                    == "notice"
                    and notice_authoritative
                )
            )
        ]
        alerts_by_symbol = (
            _alerts_by_symbol(trusted_alerts) if alerts_authoritative else {}
        )

        market_catalog: list[dict[str, Any]] = []
        full_market: list[dict[str, Any]] = []
        official_summary_rows: list[dict[str, Any]] = []
        for profile in catalog:
            symbol = str(profile.get("stock_id") or "")
            market = str(profile.get("market") or "")
            key = (market, symbol)
            catalog_row = {
                "symbol": symbol,
                "name": str(
                    profile.get("company_abbreviation")
                    or profile.get("company_name")
                    or symbol
                ),
                "company_name": str(profile.get("company_name") or ""),
                "market": market,
                "industry_code": str(profile.get("industry_code") or ""),
                "industry_name": str(profile.get("industry_name") or "未分類"),
                "snapshot_date": str(profile.get("snapshot_date") or ""),
                "source": str(profile.get("source") or ""),
            }
            market_catalog.append(catalog_row)

            official_quote = quote_by_key.get(key, {})
            live_quote = live_quote_by_key.get(key, {})
            valuation = valuation_by_key.get(key, {})
            fundamental = fundamental_by_key.get(key, {})
            revenue = revenue_by_key.get(key, {})
            flow = flow_by_symbol.get(symbol, {}) if flow_authoritative else {}
            stock_alerts = alerts_by_symbol.get(symbol, [])
            active_alerts = [
                row
                for row in stock_alerts
                if _alert_active_for_session(row, aggregate_session)
            ]
            disposition = (
                any(
                    str(row.get("alert_type") or row.get("type") or "")
                    == "disposition"
                    for row in active_alerts
                )
                if disposition_authoritative
                else None
            )
            attention = (
                any(
                    str(row.get("alert_type") or row.get("type") or "") == "notice"
                    for row in active_alerts
                )
                if notice_authoritative
                else None
            )
            official_session_date = str(
                official_quote.get("session_date") or ""
            )
            official_quote_status = str(
                official_quote.get("status") or "MISSING"
            )
            if (
                official_quote_status in {"EOD", "SUSPENDED"}
                and _session_date_is_future(
                    official_session_date,
                    as_of=now.date(),
                )
            ):
                official_quote_status = "FUTURE"
            elif (
                official_quote_status in {"EOD", "SUSPENDED"}
                and (
                    not aggregate_session
                    or official_session_date != aggregate_session
                    or not _session_date_is_fresh(
                        official_session_date,
                        as_of=now,
                        closed_dates=closed_dates,
                    )
                )
            ):
                official_quote_status = "STALE"
            official_quote_values = (
                {}
                if official_quote_status in {"FUTURE", "UNDATED"}
                else official_quote
            )
            quote = live_quote or official_quote
            quote_status = (
                str(live_quote.get("status") or "")
                if live_quote
                else official_quote_status
            ) or "MISSING"
            session_date = str(quote.get("session_date") or "")
            quote_values = live_quote if live_quote else official_quote_values
            flow_date = str(flow.get("date") or "")
            flow_same_session = bool(
                flow_authoritative
                and official_session_date
                and official_session_date == aggregate_session
                and flow_date == official_session_date
            )
            market_row = {
                **catalog_row,
                "price": quote_values.get("price"),
                "reference_price": quote_values.get("reference_price"),
                "change": quote_values.get("change"),
                "change_percent": quote_values.get("change_percent"),
                "open": quote_values.get("open"),
                "high": quote_values.get("high"),
                "low": quote_values.get("low"),
                "volume": quote_values.get("volume"),
                "trade_value": quote_values.get("trade_value"),
                "quote_status": quote_status,
                "session_date": session_date,
                "source_event_time": str(
                    quote.get("source_event_time") or ""
                ),
                "quote_source": str(quote.get("source") or ""),
                "official_quote_status": official_quote_status,
                "official_session_date": official_session_date,
                "official_quote_source": str(
                    official_quote.get("source") or ""
                ),
                "official_source_event_time": str(
                    official_quote.get("source_event_time") or ""
                ),
                "official_price": official_quote_values.get("price"),
                "official_reference_price": official_quote_values.get(
                    "reference_price"
                ),
                "official_change": official_quote_values.get("change"),
                "official_change_percent": official_quote_values.get(
                    "change_percent"
                ),
                "official_open": official_quote_values.get("open"),
                "official_high": official_quote_values.get("high"),
                "official_low": official_quote_values.get("low"),
                "official_volume": official_quote_values.get("volume"),
                "official_trade_value": official_quote_values.get(
                    "trade_value"
                ),
                "live_quote_status": (
                    str(live_quote.get("status") or "MISSING")
                    if live_quote
                    else "MISSING"
                ),
                "live_source_event_time": str(
                    live_quote.get("source_event_time") or ""
                ),
                "pe_ratio": valuation.get("pe_ratio"),
                "pb_ratio": valuation.get("pb_ratio"),
                "dividend_yield": valuation.get("dividend_yield"),
                "valuation_date": str(valuation.get("date") or ""),
                "eps": fundamental.get("eps"),
                "operating_revenue": fundamental.get("operating_revenue"),
                "operating_profit": fundamental.get("operating_profit"),
                "net_income": fundamental.get("net_income"),
                "financial_period": str(fundamental.get("period") or ""),
                "monthly_revenue": revenue.get("monthly_revenue"),
                "revenue_month": str(revenue.get("month") or ""),
                "revenue_mom_percent": revenue.get("revenue_mom_percent"),
                "revenue_yoy_percent": revenue.get("revenue_yoy_percent"),
                "institutional_net": (
                    flow.get("total_net") if flow_authoritative else None
                ),
                "institutional_date": flow_date,
                "institutional_status": (
                    "MATCHED"
                    if flow_same_session
                    else (
                        ("STALE" if flow else "NO_ROW")
                        if flow_authoritative
                        else flow_state
                    )
                ),
                "disposition": disposition,
                "attention": attention,
                "alert_status": alert_state,
                "disposition_status": str(
                    disposition_source_status["coverage_status"]
                ),
                "attention_status": str(
                    notice_source_status["coverage_status"]
                ),
                "alert_count": (
                    len(active_alerts) if alerts_authoritative else None
                ),
                "alert_titles": [
                    str(row.get("title") or row.get("reason") or "")
                    for row in active_alerts[:3]
                    if str(row.get("title") or row.get("reason") or "")
                ]
                if alerts_authoritative
                else [],
            }
            full_market.append(market_row)
            official_summary_rows.append(
                {
                    **market_row,
                    "price": official_quote_values.get("price"),
                    "reference_price": official_quote_values.get(
                        "reference_price"
                    ),
                    "change": official_quote_values.get("change"),
                    "change_percent": official_quote_values.get(
                        "change_percent"
                    ),
                    "open": official_quote_values.get("open"),
                    "high": official_quote_values.get("high"),
                    "low": official_quote_values.get("low"),
                    "volume": official_quote_values.get("volume"),
                    "trade_value": official_quote_values.get("trade_value"),
                    "quote_status": official_quote_status,
                    "session_date": official_session_date,
                    "quote_source": str(
                        official_quote.get("source") or ""
                    ),
                }
            )

        quoted_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") in {"EOD", "SUSPENDED"}
            and row.get("official_session_date") == aggregate_session
        )
        traded_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") == "EOD"
            and row.get("official_session_date") == aggregate_session
        )
        suspended_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") == "SUSPENDED"
            and row.get("official_session_date") == aggregate_session
        )
        stale_quote_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") == "STALE"
        )
        undated_quote_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") == "UNDATED"
        )
        future_quote_total = sum(
            1
            for row in full_market
            if row.get("official_quote_status") == "FUTURE"
        )
        catalog_total = len(market_catalog)
        ratio = quoted_total / catalog_total if catalog_total else 0.0
        official_market_quoted_counts = {
            market: sum(
                1
                for row in full_market
                if row.get("market") == market
                and row.get("official_quote_status") in {"EOD", "SUSPENDED"}
                and row.get("official_session_date") == aggregate_session
            )
            for market in ("TWSE", "TPEX")
        }
        official_market_ratios = {
            market: round(
                official_market_quoted_counts[market]
                / int(catalog_market_counts.get(market) or 1),
                6,
            )
            for market in ("TWSE", "TPEX")
        }
        if self._catalog_baseline_enforced and not catalog_baseline_complete:
            errors.append(
                "catalog below recently verified baseline: "
                + ", ".join(
                    f"{market}={catalog_market_counts[market]}"
                    f"<{_CATALOG_BASELINE_COUNTS[market]}"
                    for market in ("TWSE", "TPEX")
                    if catalog_gap_by_market[market]
                )
            )
        eod_status = (
            "EOD"
            if (
                catalog_baseline_complete
                and cross_market_comparable
                and session_fresh
                and ratio >= 0.95
            )
            else "PARTIAL"
        )
        live_full = bool(live_quote_support["full_coverage"])
        status = "LIVE" if live_full else eod_status
        official_mode = (
            "EOD_FULL+LIVE_PAGE"
            if eod_status == "EOD"
            else "EOD_PARTIAL+LIVE_PAGE"
        )
        industry_session = (
            str(live_quote_support["aggregate_session"])
            if live_full
            else aggregate_session
        )
        industry_summaries = build_industry_summaries(
            full_market if live_full else official_summary_rows,
            aggregate_session=industry_session,
        )

        return {
            "schema_version": 1,
            "kind": "market_breadth_snapshot",
            "ok": bool(full_market),
            "cached": False,
            "generated_at": now.isoformat(),
            "mode": (
                "LIVE_FULL+OFFICIAL_EOD"
                if live_full
                else official_mode
            ),
            "status": status,
            "official_mode": official_mode,
            "official_status": eod_status,
            "live_overlay_enabled": live_quote_support["configured"],
            "refresh_after_seconds": (
                self._live_overlay_seconds
                if live_quote_support["configured"]
                else self._cache_seconds
            ),
            "expected_session_date": expected_session_date,
            "session_dates": session_dates_by_market,
            "session_fresh": session_fresh,
            "cross_market_comparable": cross_market_comparable,
            "live_session_dates": live_quote_support["session_dates"],
            "live_session_fresh": live_quote_support["session_fresh"],
            "live_cross_market_comparable": live_quote_support[
                "cross_market_comparable"
            ],
            "market_catalog": market_catalog,
            "full_market": full_market,
            "industry_summaries": industry_summaries,
            "coverage": {
                "catalog_total": catalog_total,
                "quoted_total": quoted_total,
                "traded_total": traded_total,
                "suspended_total": suspended_total,
                "missing_quote_total": max(0, catalog_total - quoted_total),
                "stale_quote_total": stale_quote_total,
                "undated_quote_total": undated_quote_total,
                "future_quote_total": future_quote_total,
                "ratio": round(ratio, 6),
                "official_quoted_total": quoted_total,
                "official_ratio": round(ratio, 6),
                "official_market_quoted_counts": (
                    official_market_quoted_counts
                ),
                "official_market_ratios": official_market_ratios,
                "live_quoted_total": live_quote_support["quoted_total"],
                "live_missing_quote_total": max(
                    0,
                    catalog_total - int(live_quote_support["quoted_total"]),
                ),
                "live_ratio": live_quote_support["ratio"],
                "live_market_quoted_counts": live_quote_support[
                    "market_counts"
                ],
                "live_market_ratios": live_quote_support["market_ratios"],
                "live_full_coverage": live_full,
                "industry_total": len(industry_summaries),
                "market_catalog_counts": catalog_market_counts,
                "minimum_market_catalog_counts": dict(
                    self._minimum_catalog_counts
                ),
                "catalog_baseline_as_of": _CATALOG_BASELINE_AS_OF,
                "catalog_baseline_counts": dict(_CATALOG_BASELINE_COUNTS),
                "catalog_baseline_enforced": self._catalog_baseline_enforced,
                "catalog_baseline_complete": catalog_baseline_complete,
                "catalog_gap_by_market": catalog_gap_by_market,
                "valuation_total": len(valuation_by_key),
                "fundamental_total": len(fundamental_by_key),
                "revenue_total": len(revenue_by_key),
                "institutional_total": (
                    sum(
                        1
                        for row in full_market
                        if row.get("institutional_status") != "NO_ROW"
                    )
                    if flow_authoritative
                    else None
                ),
                "institutional_same_session_total": (
                    sum(
                        1
                        for row in full_market
                        if row.get("institutional_status") == "MATCHED"
                    )
                    if flow_authoritative
                    else None
                ),
                "alert_security_total": (
                    sum(
                        1
                        for row in full_market
                        if str(row.get("symbol") or "") in alerts_by_symbol
                    )
                    if alerts_authoritative
                    else None
                ),
                "active_alert_security_total": (
                    sum(
                        1
                        for row in full_market
                        if int(row.get("alert_count") or 0) > 0
                    )
                    if alerts_authoritative
                    else None
                ),
            },
            "source_status": {
                "catalog": catalog_sources,
                "quotes": quote_sources,
                "valuation": valuation_sources,
                "fundamentals": fundamental_sources,
                "revenue": revenue_sources,
                "fund_flow": flow_source_status,
                "alerts": alert_source_status,
                "disposition_alerts": disposition_source_status,
                "notice_alerts": notice_source_status,
                "calendar": calendar_source,
                "live_quotes": live_quote_support["source_status"],
            },
            "errors": errors,
            "official_errors": official_errors,
            "live_errors": live_errors,
        }

    def _official_baseline_copy(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        baseline = copy.deepcopy(payload)
        for row in baseline.get("full_market") or []:
            _restore_official_quote_fields(row)

        official_status = str(
            baseline.get("official_status") or "PARTIAL"
        )
        official_mode = str(
            baseline.get("official_mode") or "EOD_PARTIAL+LIVE_PAGE"
        )
        baseline["status"] = official_status
        baseline["mode"] = official_mode
        baseline["live_session_dates"] = {}
        baseline["live_session_fresh"] = False
        baseline["live_cross_market_comparable"] = False
        baseline["industry_summaries"] = build_industry_summaries(
            baseline.get("full_market") or [],
            aggregate_session=_aggregate_session(
                baseline.get("session_dates")
            ),
        )
        coverage = baseline.setdefault("coverage", {})
        catalog_total = int(coverage.get("catalog_total") or 0)
        coverage["live_quoted_total"] = 0
        coverage["live_missing_quote_total"] = catalog_total
        coverage["live_ratio"] = 0.0
        coverage["live_market_quoted_counts"] = {"TWSE": 0, "TPEX": 0}
        coverage["live_market_ratios"] = {"TWSE": 0.0, "TPEX": 0.0}
        coverage["live_full_coverage"] = False
        coverage["industry_total"] = len(baseline["industry_summaries"])
        live_source = (
            (baseline.get("source_status") or {}).get("live_quotes") or {}
        )
        baseline_source_status = baseline.setdefault("source_status", {})
        baseline_source_status["live_quotes"] = {
            "status": "UNAVAILABLE",
            "configured": bool(
                baseline.get("live_overlay_enabled")
                or live_source.get("configured")
            ),
            "authoritative": False,
            "coverage_status": "UNAVAILABLE",
            "row_count": 0,
            "live_row_count": 0,
            "coverage_ratio": 0.0,
            "market_statuses": {
                "TWSE": "UNAVAILABLE",
                "TPEX": "UNAVAILABLE",
            },
            "market_counts": {"TWSE": 0, "TPEX": 0},
            "market_ratios": {"TWSE": 0.0, "TPEX": 0.0},
            "session_dates": {},
            "session_fresh": False,
            "cross_market_comparable": False,
        }
        baseline["errors"] = list(baseline.get("official_errors") or [])
        baseline["live_errors"] = []
        baseline["cached"] = False
        return baseline

    def _apply_live_overlay(
        self,
        baseline: dict[str, Any],
        *,
        support: dict[str, Any],
        now: datetime,
        configured_hint: bool,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(baseline)
        coverage = payload.setdefault("coverage", {})
        catalog_counts = {
            market: int(
                (coverage.get("market_catalog_counts") or {}).get(market)
                or 0
            )
            for market in ("TWSE", "TPEX")
        }
        assessment = _assess_live_quote_support(
            support,
            catalog=payload.get("market_catalog") or [],
            catalog_counts=catalog_counts,
            catalog_baseline_complete=bool(
                coverage.get("catalog_baseline_complete")
            ),
            as_of=now,
            configured_hint=configured_hint,
        )
        overlay_by_key = assessment["overlay_by_key"]
        for row in payload.get("full_market") or []:
            _restore_official_quote_fields(row)
            key = (
                str(row.get("market") or "").upper(),
                str(row.get("symbol") or "").upper(),
            )
            live_quote = overlay_by_key.get(key)
            if live_quote is None:
                continue
            _apply_quote_fields(row, live_quote)
            row["live_quote_status"] = str(
                live_quote.get("status") or "MISSING"
            )
            row["live_source_event_time"] = str(
                live_quote.get("source_event_time") or ""
            )

        live_full = bool(assessment["full_coverage"])
        official_status = str(
            payload.get("official_status") or "PARTIAL"
        )
        official_mode = str(
            payload.get("official_mode") or "EOD_PARTIAL+LIVE_PAGE"
        )
        payload["status"] = "LIVE" if live_full else official_status
        payload["mode"] = (
            "LIVE_FULL+OFFICIAL_EOD" if live_full else official_mode
        )
        payload["live_overlay_enabled"] = bool(assessment["configured"])
        payload["live_session_dates"] = assessment["session_dates"]
        payload["live_session_fresh"] = assessment["session_fresh"]
        payload["live_cross_market_comparable"] = assessment[
            "cross_market_comparable"
        ]
        catalog_total = int(coverage.get("catalog_total") or 0)
        coverage["live_quoted_total"] = assessment["quoted_total"]
        coverage["live_missing_quote_total"] = max(
            0,
            catalog_total - int(assessment["quoted_total"]),
        )
        coverage["live_ratio"] = assessment["ratio"]
        coverage["live_market_quoted_counts"] = assessment["market_counts"]
        coverage["live_market_ratios"] = assessment["market_ratios"]
        coverage["live_full_coverage"] = live_full
        industry_rows = (
            payload.get("full_market") or []
            if live_full
            else [
                _official_quote_row_copy(row)
                for row in payload.get("full_market") or []
            ]
        )
        payload["industry_summaries"] = build_industry_summaries(
            industry_rows,
            aggregate_session=(
                str(assessment["aggregate_session"])
                if live_full
                else _aggregate_session(payload.get("session_dates"))
            ),
        )
        coverage["industry_total"] = len(payload["industry_summaries"])
        payload_source_status = payload.setdefault("source_status", {})
        payload_source_status["live_quotes"] = assessment[
            "source_status"
        ]
        live_errors = [
            str(error)
            for error in support.get("errors") or []
            if str(error)
        ]
        payload["live_errors"] = live_errors
        payload["errors"] = [
            *list(payload.get("official_errors") or []),
            *live_errors,
        ]
        payload["generated_at"] = now.isoformat()
        payload["live_refreshed_at"] = now.isoformat()
        payload["refresh_after_seconds"] = self._live_overlay_seconds
        payload["cached"] = False
        return payload

    def _load_catalog_and_fundamentals(
        self,
        errors: list[str],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, Any],
    ]:
        twse_profiles = self._fetch_list("twse-catalog", TWSE_PROFILE_URL, errors)
        twse_financials = self._fetch_list(
            "twse-financial-summary",
            TWSE_FINANCIAL_URL,
            errors,
        )
        tpex_profiles = self._fetch_list("tpex-catalog", TPEX_PROFILE_URL, errors)
        tpex_financials = self._fetch_list(
            "tpex-financial-summary",
            TPEX_FINANCIAL_URL,
            errors,
        )
        rows = build_official_profiles(
            twse_profiles,
            twse_financials,
            tpex_profiles,
            tpex_financials,
        )
        rows = [
            row
            for row in rows
            if _valid_company_symbol(row.get("stock_id"))
            and str(row.get("market") or "") in {"TWSE", "TPEX"}
        ]
        market_counts = {
            market: sum(
                1 for row in rows if str(row.get("market") or "") == market
            )
            for market in ("TWSE", "TPEX")
        }
        fundamentals = [
            *normalize_fundamental_rows(twse_financials, market="TWSE"),
            *normalize_fundamental_rows(tpex_financials, market="TPEX"),
        ]
        catalog_status = {
            "status": (
                "FRESH"
                if all(market_counts.values())
                else ("PARTIAL" if any(market_counts.values()) else "UNAVAILABLE")
            ),
            "row_count": len(rows),
            "market_counts": market_counts,
            "upstreams": [
                {
                    "id": "twse-catalog",
                    "market": "TWSE",
                    "status": "FRESH" if market_counts["TWSE"] else "UNAVAILABLE",
                    "row_count": market_counts["TWSE"],
                },
                {
                    "id": "tpex-catalog",
                    "market": "TPEX",
                    "status": "FRESH" if market_counts["TPEX"] else "UNAVAILABLE",
                    "row_count": market_counts["TPEX"],
                },
            ],
        }
        return (
            rows,
            fundamentals,
            catalog_status,
            _paired_market_component_status(
                fundamentals,
                {"TWSE": "twse-financial-summary", "TPEX": "tpex-financial-summary"},
            ),
        )

    def _load_quotes(
        self,
        now: datetime,
        errors: list[str],
        *,
        closed_dates: set[date],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        target = now.date()
        twse_rows: list[dict[str, Any]] = []
        for candidate in _lookback_dates(
            target,
            _MARKET_LOOKBACK_DAYS,
            closed_dates=closed_dates,
        ):
            self._ensure_deadline()
            query = urlencode(
                {
                    "date": candidate.strftime("%Y%m%d"),
                    "type": "ALLBUT0999",
                    "response": "json",
                }
            )
            try:
                payload = self._fetch_json(f"{TWSE_DAILY_RWD_URL}?{query}")
                self._ensure_deadline()
                twse_rows = parse_twse_rwd_quotes(payload)
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(f"twse-daily-{candidate.isoformat()}: {exc}")
                continue
            if twse_rows:
                break
        if not twse_rows:
            try:
                self._ensure_deadline()
                payload = self._fetch_json(TWSE_DAILY_FALLBACK_URL)
                self._ensure_deadline()
                twse_rows = parse_twse_openapi_quotes(payload)
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(f"twse-daily-fallback: {exc}")
            if not twse_rows:
                errors.append("twse-daily: no usable RWD or OpenAPI rows")

        try:
            self._ensure_deadline()
            tpex_payload = self._fetch_json(TPEX_DAILY_URL)
            self._ensure_deadline()
            tpex_rows = parse_tpex_daily_quotes(tpex_payload)
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append(f"tpex-daily: {exc}")
            tpex_rows = []
        if not tpex_rows:
            errors.append("tpex-daily: no usable OpenAPI rows")
        rows = [*twse_rows, *tpex_rows]
        upstreams = [
            _rows_source_status(
                "twse-daily",
                twse_rows,
                as_of=now,
                closed_dates=closed_dates,
            ),
            _rows_source_status(
                "tpex-daily",
                tpex_rows,
                as_of=now,
                closed_dates=closed_dates,
            ),
        ]
        return rows, {
            "status": (
                "EOD"
                if all(row["status"] == "EOD" for row in upstreams)
                else ("PARTIAL" if rows else "UNAVAILABLE")
            ),
            "row_count": len(rows),
            "upstreams": upstreams,
        }

    def _load_valuations(
        self,
        errors: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        twse = normalize_valuation_rows(
            self._fetch_list("twse-valuation", TWSE_VALUATION_URL, errors),
            market="TWSE",
        )
        tpex = normalize_valuation_rows(
            self._fetch_list("tpex-valuation", TPEX_VALUATION_URL, errors),
            market="TPEX",
        )
        rows = [*twse, *tpex]
        return rows, _paired_market_component_status(
            rows,
            {"TWSE": "twse-valuation", "TPEX": "tpex-valuation"},
        )

    def _load_revenues(
        self,
        errors: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        twse = normalize_revenue_rows(
            self._fetch_list("twse-revenue", TWSE_REVENUE_URL, errors),
            market="TWSE",
        )
        tpex = normalize_revenue_rows(
            self._fetch_list("tpex-revenue", TPEX_REVENUE_URL, errors),
            market="TPEX",
        )
        rows = [*twse, *tpex]
        return rows, _paired_market_component_status(
            rows,
            {"TWSE": "twse-revenue", "TPEX": "tpex-revenue"},
        )

    def _load_support(self, errors: list[str]) -> dict[str, Any]:
        if self._supporting_loader is None:
            return {"alerts": [], "fund_flow": [], "source_status": {}}
        try:
            self._ensure_deadline()
            payload = self._supporting_loader()
            self._ensure_deadline()
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append(f"market-support: {exc}")
            return {"alerts": [], "fund_flow": [], "source_status": {}}
        if not isinstance(payload, dict):
            errors.append("market-support: loader returned a non-object payload")
            return {"alerts": [], "fund_flow": [], "source_status": {}}
        errors.extend(str(error) for error in payload.get("errors") or [])
        return payload

    def _fetch_list(
        self,
        source_id: str,
        url: str,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        try:
            self._ensure_deadline()
            payload = self._fetch_json(url)
            self._ensure_deadline()
            if not isinstance(payload, list):
                raise ValueError("upstream returned a non-list payload")
            return [row for row in payload if isinstance(row, dict)]
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append(f"{source_id}: {exc}")
            return []


def parse_twse_rwd_quotes(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or str(payload.get("stat") or "") != "OK":
        return []
    session_date = _parse_gregorian_date(payload.get("date"))
    tables = payload.get("tables")
    if not isinstance(tables, list):
        return []
    table = next(
        (
            item
            for item in tables
            if isinstance(item, dict)
            and "證券代號" in [str(field) for field in item.get("fields") or []]
            and "收盤價" in [str(field) for field in item.get("fields") or []]
        ),
        None,
    )
    if table is None:
        return []
    fields = [str(field) for field in table.get("fields") or []]
    indexes = {
        "symbol": _field_index(fields, "證券代號"),
        "name": _field_index(fields, "證券名稱"),
        "volume": _field_index(fields, "成交股數"),
        "trade_value": _field_index(fields, "成交金額"),
        "open": _field_index(fields, "開盤價"),
        "high": _field_index(fields, "最高價"),
        "low": _field_index(fields, "最低價"),
        "price": _field_index(fields, "收盤價"),
        "direction": _field_index(fields, "漲跌(+/-)"),
        "change": _field_index(fields, "漲跌價差"),
    }
    rows: list[dict[str, Any]] = []
    for values in table.get("data") or []:
        if not isinstance(values, list) or len(values) <= max(indexes.values()):
            continue
        price = _number(values[indexes["price"]])
        symbol = _text(values[indexes["symbol"]])
        if not symbol:
            continue
        change = _signed_change(
            values[indexes["direction"]],
            values[indexes["change"]],
        )
        rows.append(
            _quote_row(
                symbol=symbol,
                name=_text(values[indexes["name"]]),
                market="TWSE",
                session_date=session_date,
                price=price,
                change=change,
                open_value=_number(values[indexes["open"]]),
                high=_number(values[indexes["high"]]),
                low=_number(values[indexes["low"]]),
                volume=_number(values[indexes["volume"]]),
                trade_value=_number(values[indexes["trade_value"]]),
                source="TWSE MI_INDEX RWD",
            )
        )
    return rows


def parse_twse_openapi_quotes(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("ClosingPrice"))
        symbol = _text(item.get("Code"))
        if not symbol:
            continue
        rows.append(
            _quote_row(
                symbol=symbol,
                name=_text(item.get("Name")),
                market="TWSE",
                session_date=_parse_roc_date(item.get("Date")),
                price=price,
                change=_number(item.get("Change")),
                open_value=_number(item.get("OpeningPrice")),
                high=_number(item.get("HighestPrice")),
                low=_number(item.get("LowestPrice")),
                volume=_number(item.get("TradeVolume")),
                trade_value=_number(item.get("TradeValue")),
                source="TWSE STOCK_DAY_ALL",
            )
        )
    return rows


def parse_tpex_daily_quotes(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        price = _number(item.get("Close"))
        symbol = _text(item.get("SecuritiesCompanyCode"))
        if not symbol:
            continue
        rows.append(
            _quote_row(
                symbol=symbol,
                name=_text(item.get("CompanyName")),
                market="TPEX",
                session_date=_parse_roc_date(item.get("Date")),
                price=price,
                change=_number(item.get("Change")),
                open_value=_number(item.get("Open")),
                high=_number(item.get("High")),
                low=_number(item.get("Low")),
                volume=_number(item.get("TradingShares")),
                trade_value=_number(item.get("TransactionAmount")),
                source="TPEx mainboard quotes",
            )
        )
    return rows


def normalize_valuation_rows(
    rows: Iterable[dict[str, Any]],
    *,
    market: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in rows:
        symbol = _text(
            item.get("Code")
            if market == "TWSE"
            else item.get("SecuritiesCompanyCode")
        )
        if not symbol:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "market": market,
                "date": _parse_roc_date(item.get("Date")),
                "pe_ratio": _number(
                    item.get("PEratio")
                    if market == "TWSE"
                    else item.get("PriceEarningRatio")
                ),
                "dividend_yield": _number(
                    item.get("DividendYield")
                    if market == "TWSE"
                    else item.get("YieldRatio")
                ),
                "pb_ratio": _number(
                    item.get("PBratio")
                    if market == "TWSE"
                    else item.get("PriceBookRatio")
                ),
            }
        )
    return normalized


def normalize_fundamental_rows(
    rows: Iterable[dict[str, Any]],
    *,
    market: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in rows:
        symbol = _text(
            item.get("公司代號")
            if market == "TWSE"
            else item.get("SecuritiesCompanyCode")
        )
        if not symbol:
            continue
        year = _text(item.get("年度") if market == "TWSE" else item.get("Year"))
        quarter = _text(item.get("季別"))
        normalized.append(
            {
                "symbol": symbol,
                "market": market,
                "period": f"{year}Q{quarter}" if year and quarter else "",
                "eps": _number(
                    item.get("基本每股盈餘(元)")
                    if market == "TWSE"
                    else item.get("基本每股盈餘")
                ),
                "operating_revenue": _number(item.get("營業收入")),
                "operating_profit": _number(item.get("營業利益")),
                "net_income": _number(item.get("稅後淨利")),
            }
        )
    return normalized


def normalize_revenue_rows(
    rows: Iterable[dict[str, Any]],
    *,
    market: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in rows:
        symbol = _text(item.get("公司代號"))
        if not symbol:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "market": market,
                "month": _text(item.get("資料年月")),
                "monthly_revenue": _number(item.get("營業收入-當月營收")),
                "revenue_mom_percent": _number(item.get("營業收入-上月比較增減(%)")),
                "revenue_yoy_percent": _number(item.get("營業收入-去年同月增減(%)")),
            }
        )
    return normalized


_QUOTE_TO_OFFICIAL_FIELD = {
    "price": "official_price",
    "reference_price": "official_reference_price",
    "change": "official_change",
    "change_percent": "official_change_percent",
    "open": "official_open",
    "high": "official_high",
    "low": "official_low",
    "volume": "official_volume",
    "trade_value": "official_trade_value",
    "quote_status": "official_quote_status",
    "session_date": "official_session_date",
    "source_event_time": "official_source_event_time",
    "quote_source": "official_quote_source",
}


def _restore_official_quote_fields(row: dict[str, Any]) -> None:
    for field, official_field in _QUOTE_TO_OFFICIAL_FIELD.items():
        row[field] = row.get(official_field)
    row["live_quote_status"] = "MISSING"
    row["live_source_event_time"] = ""


def _official_quote_row_copy(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    _restore_official_quote_fields(result)
    return result


def _apply_quote_fields(
    row: dict[str, Any],
    quote: dict[str, Any],
) -> None:
    for field in (
        "price",
        "reference_price",
        "change",
        "change_percent",
        "open",
        "high",
        "low",
        "volume",
        "trade_value",
    ):
        row[field] = quote.get(field)
    row["quote_status"] = str(quote.get("status") or "MISSING")
    row["session_date"] = str(quote.get("session_date") or "")
    row["source_event_time"] = str(
        quote.get("source_event_time") or ""
    )
    row["quote_source"] = str(quote.get("source") or "")


def _aggregate_session(value: Any) -> str:
    session_dates = value if isinstance(value, dict) else {}
    return max(
        (
            str(session_date)
            for session_date in session_dates.values()
            if str(session_date)
        ),
        default="",
    )


def _assess_live_quote_support(
    support: dict[str, Any],
    *,
    catalog: Iterable[dict[str, Any]],
    catalog_counts: dict[str, int],
    catalog_baseline_complete: bool,
    as_of: datetime,
    minimum_ratio: float = 0.95,
    configured_hint: bool = False,
) -> dict[str, Any]:
    """Validate Fubon full-market rows before using them as a live overlay.

    Row-level live data may still be useful when one market is incomplete, but
    the aggregate can only claim full live coverage when both market
    upstreams are independently healthy, current, comparable, and sufficiently
    complete against the official catalog.
    """

    source_statuses = (
        support.get("source_status")
        if isinstance(support.get("source_status"), dict)
        else {}
    )
    raw_source_status = source_statuses.get("live_quotes")
    raw_rows = (
        support.get("live_quotes")
        if isinstance(support.get("live_quotes"), list)
        else []
    )
    configured = bool(
        configured_hint
        or isinstance(raw_source_status, dict)
        or raw_rows
    )
    source_status = (
        copy.deepcopy(raw_source_status)
        if isinstance(raw_source_status, dict)
        else {"status": "UNAVAILABLE"}
    )
    source_status["configured"] = configured
    upstreams = [
        row
        for row in source_status.get("upstreams") or []
        if isinstance(row, dict)
    ]
    upstream_status_by_market: dict[str, str] = {}
    for upstream in upstreams:
        market = _live_upstream_market(upstream)
        if market:
            upstream_status_by_market[market] = str(
                upstream.get("status") or "UNAVAILABLE"
            ).upper()

    transport_usable = not bool(source_status.get("fallback"))
    overlay_markets = {
        market
        for market in ("TWSE", "TPEX")
        if transport_usable
        and upstream_status_by_market.get(market) in {"LIVE", "EOD"}
    }
    catalog_keys = {
        (
            str(row.get("market") or "").upper(),
            str(row.get("stock_id") or row.get("symbol") or "").upper(),
        )
        for row in catalog
        if str(row.get("market") or "").upper() in {"TWSE", "TPEX"}
        and str(row.get("stock_id") or row.get("symbol") or "")
    }
    overlay_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        market = str(raw.get("market") or raw.get("exchange") or "").upper()
        if market == "TSE":
            market = "TWSE"
        elif market == "OTC":
            market = "TPEX"
        symbol = str(raw.get("symbol") or "").strip().upper()
        key = (market, symbol)
        status = str(raw.get("status") or "").upper()
        if (
            market not in overlay_markets
            or key not in catalog_keys
            or status not in {"LIVE", "EOD"}
            or _number(raw.get("price")) is None
            or not _valid_session_date(raw.get("session_date"))
        ):
            continue
        normalized = dict(raw)
        normalized["market"] = market
        normalized["status"] = status
        existing = overlay_by_key.get(key)
        if existing is None or str(
            normalized.get("source_event_time") or ""
        ) >= str(existing.get("source_event_time") or ""):
            overlay_by_key[key] = normalized

    live_rows = [
        row
        for row in overlay_by_key.values()
        if str(row.get("status") or "") == "LIVE"
    ]
    market_counts = {
        market: sum(
            1
            for row in live_rows
            if str(row.get("market") or "") == market
        )
        for market in ("TWSE", "TPEX")
    }
    market_ratios = {
        market: round(
            market_counts[market] / int(catalog_counts.get(market) or 1),
            6,
        )
        for market in ("TWSE", "TPEX")
    }
    quoted_total = sum(market_counts.values())
    catalog_total = sum(
        int(catalog_counts.get(market) or 0)
        for market in ("TWSE", "TPEX")
    )
    ratio = round(quoted_total / catalog_total, 6) if catalog_total else 0.0

    session_sets = {
        market: {
            str(row.get("session_date") or "")
            for row in live_rows
            if str(row.get("market") or "") == market
            and _valid_session_date(row.get("session_date"))
        }
        for market in ("TWSE", "TPEX")
    }
    session_dates = {
        market: max(values)
        for market, values in session_sets.items()
        if values
    }
    distinct_sessions = set(session_dates.values())
    cross_market_comparable = (
        all(len(session_sets[market]) == 1 for market in ("TWSE", "TPEX"))
        and len(session_dates) == 2
        and len(distinct_sessions) == 1
    )
    aggregate_session = max(distinct_sessions, default="")
    session_fresh = bool(
        cross_market_comparable
        and aggregate_session == as_of.date().isoformat()
    )
    markets_healthy = (
        transport_usable
        and not bool(source_status.get("partial"))
        and all(
            upstream_status_by_market.get(market) == "LIVE"
            for market in ("TWSE", "TPEX")
        )
    )
    full_coverage = bool(
        catalog_baseline_complete
        and markets_healthy
        and cross_market_comparable
        and session_fresh
        and ratio >= minimum_ratio
        and all(
            market_ratios[market] >= minimum_ratio
            for market in ("TWSE", "TPEX")
        )
    )

    source_status["market_statuses"] = {
        market: upstream_status_by_market.get(market, "UNAVAILABLE")
        for market in ("TWSE", "TPEX")
    }
    source_status["market_counts"] = market_counts
    source_status["market_ratios"] = market_ratios
    source_status["row_count"] = len(overlay_by_key)
    source_status["live_row_count"] = quoted_total
    source_status["coverage_ratio"] = ratio
    source_status["coverage_status"] = (
        "COMPLETE"
        if full_coverage
        else ("PARTIAL" if quoted_total else "UNAVAILABLE")
    )
    source_status["authoritative"] = full_coverage
    source_status["session_dates"] = session_dates
    source_status["session_fresh"] = session_fresh
    source_status["cross_market_comparable"] = cross_market_comparable

    return {
        "overlay_by_key": overlay_by_key,
        "configured": configured,
        "source_status": source_status,
        "quoted_total": quoted_total,
        "ratio": ratio,
        "market_counts": market_counts,
        "market_ratios": market_ratios,
        "session_dates": session_dates,
        "aggregate_session": aggregate_session,
        "session_fresh": session_fresh,
        "cross_market_comparable": cross_market_comparable,
        "full_coverage": full_coverage,
    }


def _live_upstream_market(upstream: dict[str, Any]) -> str:
    market = str(upstream.get("market") or "").upper()
    if market in {"TWSE", "TSE"}:
        return "TWSE"
    if market in {"TPEX", "OTC"}:
        return "TPEX"
    source_id = str(upstream.get("id") or "").upper()
    if source_id.endswith(":TSE") or "TWSE" in source_id:
        return "TWSE"
    if source_id.endswith(":OTC") or "TPEX" in source_id:
        return "TPEX"
    return ""


def build_industry_summaries(
    rows: Iterable[dict[str, Any]],
    *,
    aggregate_session: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    catalog_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        industry = str(row.get("industry_name") or "未分類")
        catalog_counts[industry] += 1
        if (
            row.get("quote_status") in {"LIVE", "EOD"}
            and str(row.get("session_date") or "") == aggregate_session
            and _number(row.get("change_percent")) is not None
        ):
            grouped[industry].append(row)

    summaries: list[dict[str, Any]] = []
    for industry in sorted(catalog_counts):
        quoted = grouped.get(industry, [])
        changes = [
            float(row["change_percent"])
            for row in quoted
            if _number(row.get("change_percent")) is not None
        ]
        advance_count = sum(1 for value in changes if value > 0)
        decline_count = sum(1 for value in changes if value < 0)
        flat_count = len(changes) - advance_count - decline_count
        average = sum(changes) / len(changes) if changes else None
        breadth_balance = (
            (advance_count - decline_count) / len(changes)
            if changes
            else 0.0
        )
        temperature = (
            max(0.0, min(100.0, 50.0 + average * 8.0 + breadth_balance * 25.0))
            if average is not None
            else None
        )
        institutional_values = [
            float(row["institutional_net"])
            for row in quoted
            if row.get("institutional_status") == "MATCHED"
            and _number(row.get("institutional_net")) is not None
        ]
        summaries.append(
            {
                "industry_name": industry,
                "stock_count": catalog_counts[industry],
                "quoted_count": len(quoted),
                "advance_count": advance_count,
                "decline_count": decline_count,
                "flat_count": flat_count,
                "average_change_percent": round(average, 4) if average is not None else None,
                "breadth_percent": round(breadth_balance * 100.0, 2) if changes else None,
                "temperature": round(temperature, 1) if temperature is not None else None,
                "total_trade_value": sum(
                    float(row.get("trade_value") or 0)
                    for row in quoted
                    if _number(row.get("trade_value")) is not None
                ),
                "institutional_net": (
                    sum(institutional_values) if institutional_values else None
                ),
                "session_date": aggregate_session,
            }
        )
    summaries.sort(
        key=lambda row: (
            -(float(row.get("total_trade_value") or 0)),
            str(row.get("industry_name") or ""),
        )
    )
    return summaries


def _quote_row(
    *,
    symbol: str,
    name: str,
    market: str,
    session_date: str,
    price: float | None,
    change: float | None,
    open_value: float | None,
    high: float | None,
    low: float | None,
    volume: float | None,
    trade_value: float | None,
    source: str,
) -> dict[str, Any]:
    reference_price = (
        price - change
        if price is not None and change is not None
        else None
    )
    change_percent = (
        change / reference_price * 100.0
        if change is not None and reference_price is not None and reference_price > 0
        else None
    )
    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "session_date": session_date,
        "price": price,
        "reference_price": reference_price,
        "change": change,
        "change_percent": change_percent,
        "open": open_value,
        "high": high,
        "low": low,
        "volume": volume,
        "trade_value": trade_value,
        "status": (
            ("EOD" if price is not None else "SUSPENDED")
            if _valid_session_date(session_date)
            else "UNDATED"
        ),
        "source": source,
    }


def _latest_by_symbol(value: Any) -> dict[str, dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("stock_id") or "")
        if not symbol:
            continue
        if str(row.get("date") or "") >= str(selected.get(symbol, {}).get("date") or ""):
            selected[symbol] = row
    return selected


def _alerts_by_symbol(value: Any) -> dict[str, list[dict[str, Any]]]:
    rows = value if isinstance(value, list) else []
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        if symbol:
            selected[symbol].append(row)
    return dict(selected)


def _alert_active_for_session(row: dict[str, Any], session_date: str) -> bool:
    try:
        session = date.fromisoformat(session_date)
    except ValueError:
        return False
    alert_type = str(row.get("alert_type") or row.get("type") or "")
    published = _iso_date_value(row.get("published_date"))
    start = _iso_date_value(row.get("start_date"))
    end = _iso_date_value(row.get("end_date"))
    if alert_type == "disposition" and (start is not None or end is not None):
        return bool(
            (start is None or start <= session)
            and (end is None or session <= end)
        )
    if published is not None:
        return published == session
    return bool(row.get("active"))


def _iso_date_value(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _cached_copy(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result["cached"] = True
    return result


def _cache_matches_completed_session(
    payload: dict[str, Any],
    now: datetime,
) -> bool:
    """Do not carry a successful snapshot across the 15:00 session boundary."""

    status = str(payload.get("status") or "").upper()
    if status in {"STALE", "UNAVAILABLE"}:
        return True
    cached_expected = str(payload.get("expected_session_date") or "")
    calendar = (payload.get("source_status") or {}).get("calendar") or {}
    closed_dates = {
        parsed
        for value in calendar.get("closed_dates") or []
        if (parsed := _iso_date_value(value)) is not None
    }
    current_expected = expected_latest_completed_session(
        now,
        closed_dates=closed_dates,
    ).isoformat()
    return bool(cached_expected and cached_expected == current_expected)


def _mark_breadth_stale(
    payload: dict[str, Any],
    *,
    now: datetime,
    error: str,
) -> dict[str, Any]:
    """Turn a failed refresh into an explicitly stale, non-EOD fallback."""

    fallback = copy.deepcopy(payload)
    fallback["cached"] = True
    fallback["last_observed_status"] = str(fallback.get("status") or "")
    fallback["status"] = "STALE"
    fallback["last_observed_mode"] = str(fallback.get("mode") or "")
    fallback["mode"] = "STALE_FALLBACK+LIVE_PAGE"
    fallback["session_fresh"] = False
    fallback["stale_at"] = now.isoformat()
    fallback["errors"] = [*list(fallback.get("errors") or []), error]

    for source in (fallback.get("source_status") or {}).values():
        _mark_source_tree_stale(source)

    stale_quote_total = 0
    for row in fallback.get("full_market") or []:
        quote_status = str(row.get("quote_status") or "")
        if quote_status in {"LIVE", "EOD", "SUSPENDED"}:
            row["last_observed_quote_status"] = quote_status
            row["quote_status"] = "STALE"
            stale_quote_total += 1
        institutional_status = str(row.get("institutional_status") or "")
        if institutional_status == "MATCHED":
            row["last_observed_institutional_status"] = institutional_status
            row["institutional_status"] = "STALE"

    coverage = fallback.get("coverage") or {}
    for key in ("quoted_total", "traded_total", "suspended_total"):
        coverage[f"last_observed_{key}"] = int(coverage.get(key) or 0)
        coverage[key] = 0
    catalog_total = int(coverage.get("catalog_total") or 0)
    coverage["missing_quote_total"] = catalog_total
    coverage["stale_quote_total"] = max(
        stale_quote_total,
        int(coverage.get("stale_quote_total") or 0),
    )
    coverage["ratio"] = 0.0
    coverage["last_observed_official_quoted_total"] = int(
        coverage.get("official_quoted_total") or 0
    )
    coverage["official_quoted_total"] = 0
    coverage["official_ratio"] = 0.0
    coverage["last_observed_official_market_quoted_counts"] = dict(
        coverage.get("official_market_quoted_counts") or {}
    )
    coverage["official_market_quoted_counts"] = {"TWSE": 0, "TPEX": 0}
    coverage["official_market_ratios"] = {"TWSE": 0.0, "TPEX": 0.0}
    coverage["last_observed_live_quoted_total"] = int(
        coverage.get("live_quoted_total") or 0
    )
    coverage["live_quoted_total"] = 0
    coverage["live_missing_quote_total"] = catalog_total
    coverage["live_ratio"] = 0.0
    coverage["live_full_coverage"] = False
    coverage["live_market_quoted_counts"] = {"TWSE": 0, "TPEX": 0}
    coverage["live_market_ratios"] = {"TWSE": 0.0, "TPEX": 0.0}

    aggregate_session = max(
        (
            str(value)
            for value in (fallback.get("session_dates") or {}).values()
            if str(value)
        ),
        default="",
    )
    fallback["industry_summaries"] = build_industry_summaries(
        fallback.get("full_market") or [],
        aggregate_session=aggregate_session,
    )
    return fallback


def _mark_source_tree_stale(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _mark_source_tree_stale(item)
        return
    if not isinstance(value, dict):
        return
    status = str(value.get("status") or "").upper()
    if status and status not in {"UNAVAILABLE", "NOT_CONNECTED", "STALE"}:
        value["last_observed_status"] = str(value.get("status") or "")
        value["status"] = "STALE"
    if "authoritative" in value and bool(value.get("authoritative")):
        value["last_observed_authoritative"] = True
        value["authoritative"] = False
    coverage_status = str(value.get("coverage_status") or "").upper()
    if coverage_status and coverage_status not in {"UNAVAILABLE", "STALE"}:
        value["last_observed_coverage_status"] = str(
            value.get("coverage_status") or ""
        )
        value["coverage_status"] = "STALE"
    for nested in value.values():
        if isinstance(nested, (dict, list)):
            _mark_source_tree_stale(nested)


def _unavailable_snapshot(now: datetime, error: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "market_breadth_snapshot",
        "ok": False,
        "cached": False,
        "generated_at": now.isoformat(),
        "mode": "UNAVAILABLE",
        "status": "UNAVAILABLE",
        "session_dates": {},
        "cross_market_comparable": False,
        "market_catalog": [],
        "full_market": [],
        "industry_summaries": [],
        "coverage": {
            "catalog_total": 0,
            "quoted_total": 0,
            "traded_total": 0,
            "suspended_total": 0,
            "missing_quote_total": 0,
            "ratio": 0.0,
            "industry_total": 0,
        },
        "source_status": {},
        "errors": [f"breadth: {error}"],
    }


def _paired_market_component_status(
    rows: list[dict[str, Any]],
    source_ids: dict[str, str],
) -> dict[str, Any]:
    market_counts = {
        market: sum(
            1 for row in rows if str(row.get("market") or "") == market
        )
        for market in ("TWSE", "TPEX")
    }
    return {
        "status": (
            "FRESH"
            if all(market_counts.values())
            else ("PARTIAL" if any(market_counts.values()) else "UNAVAILABLE")
        ),
        "row_count": len(rows),
        "market_counts": market_counts,
        "upstreams": [
            {
                "id": source_ids[market],
                "market": market,
                "status": "FRESH" if market_counts[market] else "UNAVAILABLE",
                "row_count": market_counts[market],
            }
            for market in ("TWSE", "TPEX")
        ],
    }


def _align_component_to_catalog(
    value: dict[str, Any],
    *,
    catalog_counts: dict[str, int],
    minimum_ratio: float = 0.90,
) -> dict[str, Any]:
    result = copy.deepcopy(value)
    component_counts = result.get("market_counts") or {}
    ratios: dict[str, float] = {}
    incomplete_markets: list[str] = []
    for market in ("TWSE", "TPEX"):
        catalog_count = int(catalog_counts.get(market) or 0)
        component_count = int(component_counts.get(market) or 0)
        ratio = component_count / catalog_count if catalog_count else 0.0
        ratios[market] = round(ratio, 6)
        if ratio < minimum_ratio:
            incomplete_markets.append(market)
    result["coverage_ratios"] = ratios
    result["minimum_coverage_ratio"] = minimum_ratio
    result["partial"] = bool(incomplete_markets)
    if incomplete_markets:
        result["status"] = "PARTIAL" if any(component_counts.values()) else "UNAVAILABLE"
        for upstream in result.get("upstreams") or []:
            market = str(upstream.get("market") or "")
            if market in incomplete_markets:
                upstream["status"] = (
                    "PARTIAL"
                    if int(upstream.get("row_count") or 0) > 0
                    else "UNAVAILABLE"
                )
    return result


def _align_valuation_to_session(
    value: dict[str, Any],
    *,
    rows: list[dict[str, Any]],
    as_of: datetime,
    closed_dates: set[date],
) -> dict[str, Any]:
    """Require each market's valuation rows to match the completed session."""

    result = copy.deepcopy(value)
    expected = expected_latest_completed_session(
        as_of,
        closed_dates=closed_dates,
    ).isoformat()
    dates_by_market: dict[str, set[str]] = {
        "TWSE": set(),
        "TPEX": set(),
    }
    undated_by_market = {"TWSE": 0, "TPEX": 0}
    for row in rows:
        market = str(row.get("market") or "")
        if market not in dates_by_market:
            continue
        effective_date = str(row.get("date") or "")
        if _valid_session_date(effective_date):
            dates_by_market[market].add(effective_date)
        else:
            undated_by_market[market] += 1

    aligned_markets = [
        market
        for market in ("TWSE", "TPEX")
        if dates_by_market[market] == {expected}
        and undated_by_market[market] == 0
    ]
    effective_dates = {
        market: max(dates_by_market[market], default="")
        for market in ("TWSE", "TPEX")
    }
    result["expected_session_date"] = expected
    result["effective_dates"] = effective_dates
    result["date_aligned_markets"] = aligned_markets
    result["undated_counts"] = undated_by_market

    for upstream in result.get("upstreams") or []:
        market = str(upstream.get("market") or "")
        if market not in dates_by_market:
            continue
        upstream["expected_session_date"] = expected
        upstream["effective_date"] = effective_dates[market]
        upstream["date_aligned"] = market in aligned_markets
        if int(upstream.get("row_count") or 0) > 0 and market not in aligned_markets:
            upstream["status"] = "STALE"

    any_rows = any(int(count or 0) > 0 for count in (result.get("market_counts") or {}).values())
    coverage_partial = bool(result.get("partial"))
    date_partial = len(aligned_markets) != 2
    result["partial"] = coverage_partial or date_partial
    if not any_rows:
        result["status"] = "UNAVAILABLE"
    elif not date_partial and not coverage_partial:
        result["status"] = "FRESH"
    elif coverage_partial or aligned_markets:
        result["status"] = "PARTIAL"
    else:
        result["status"] = "STALE"
    return result


def _rows_source_status(
    source_id: str,
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
    closed_dates: set[date],
) -> dict[str, Any]:
    raw_sessions = [str(row.get("session_date") or "") for row in rows]
    sessions = {
        session_date
        for session_date in raw_sessions
        if _valid_session_date(session_date)
    }
    complete_session = bool(
        rows
        and len(sessions) == 1
        and len(raw_sessions) == sum(
            1 for session_date in raw_sessions if _valid_session_date(session_date)
        )
    )
    session_date = max(sessions, default="")
    if complete_session and _session_date_is_fresh(
        session_date,
        as_of=as_of,
        closed_dates=closed_dates,
    ):
        status = "EOD"
    elif rows:
        status = "STALE" if complete_session else "PARTIAL"
    else:
        status = "UNAVAILABLE"
    return {
        "id": source_id,
        "status": status,
        "row_count": len(rows),
        "session_date": session_date,
    }


def _alert_component_for_type(
    value: Any,
    *,
    alert_type: str,
) -> dict[str, Any]:
    source = copy.deepcopy(value) if isinstance(value, dict) else {}
    all_upstreams = (
        [row for row in source.get("upstreams") or [] if isinstance(row, dict)]
        if isinstance(source.get("upstreams"), list)
        else []
    )
    # Older fixture/custom loaders expose only the component-level status.
    # Preserve that contract when no per-feed evidence exists.
    if not all_upstreams:
        return source
    suffix = f"-{alert_type}"
    upstreams = [
        row
        for row in all_upstreams
        if str(row.get("id") or "").lower().endswith(suffix)
    ]
    source["upstreams"] = upstreams
    source["row_count"] = sum(
        int(row.get("row_count") or 0) for row in upstreams
    )
    latest_events = [
        str(row.get("latest_event_at") or "")
        for row in upstreams
        if str(row.get("latest_event_at") or "")
    ]
    source["latest_event_at"] = max(latest_events) if latest_events else ""
    statuses = {
        str(row.get("status") or "UNAVAILABLE").upper()
        for row in upstreams
    }
    accepted = {"EOD", "FRESH", "LIVE"}
    if upstreams and statuses.issubset(accepted):
        source["status"] = (
            "LIVE"
            if "LIVE" in statuses
            else ("FRESH" if "FRESH" in statuses else "EOD")
        )
        source["partial"] = False
    elif not upstreams or statuses == {"UNAVAILABLE"}:
        source["status"] = "UNAVAILABLE"
        source["partial"] = False
    else:
        source["status"] = "PARTIAL"
        source["partial"] = True
    return source


def _with_authority(
    value: Any,
    *,
    accepted_statuses: set[str],
    required_event_date: str = "",
) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    status = str(source.get("status") or "UNAVAILABLE").upper()
    upstreams = (
        [dict(row) for row in source.get("upstreams") if isinstance(row, dict)]
        if isinstance(source.get("upstreams"), list)
        else []
    )
    upstream_statuses = {
        str(row.get("status") or "UNAVAILABLE").upper() for row in upstreams
    }
    explicitly_partial = bool(source.get("partial"))
    has_unavailable_upstream = "UNAVAILABLE" in upstream_statuses
    has_available_upstream = any(
        upstream_status != "UNAVAILABLE"
        for upstream_status in upstream_statuses
    )
    fallback = bool(source.get("fallback"))
    upstream_event_dates = [
        str(row.get("latest_event_at") or "")[:10] for row in upstreams
    ]
    session_aligned = bool(
        not required_event_date
        or (
            upstreams
            and all(
                event_date == required_event_date
                for event_date in upstream_event_dates
            )
        )
        or (
            not upstreams
            and not str(source.get("latest_event_at") or "")
        )
        or (
            not upstreams
            and str(source.get("latest_event_at") or "")[:10]
            == required_event_date
        )
    )
    all_upstreams_authoritative = (
        not upstreams
        or all(
            str(row.get("status") or "UNAVAILABLE").upper()
            in accepted_statuses
            or (
                bool(required_event_date)
                and str(row.get("status") or "").upper() == "STALE"
                and str(row.get("latest_event_at") or "")[:10]
                == required_event_date
            )
            for row in upstreams
        )
    )
    source_status_authoritative = bool(
        status in accepted_statuses
        or (
            required_event_date
            and status == "STALE"
            and session_aligned
            and not fallback
        )
    )
    authoritative = bool(
        source_status_authoritative
        and not explicitly_partial
        and all_upstreams_authoritative
        and session_aligned
        and not fallback
    )
    if authoritative:
        coverage_status = "COMPLETE"
    elif status == "STALE":
        coverage_status = "STALE"
    elif (
        explicitly_partial
        or (has_unavailable_upstream and has_available_upstream)
        or (upstreams and not all_upstreams_authoritative)
        or not session_aligned
    ):
        coverage_status = "PARTIAL"
    else:
        coverage_status = "UNAVAILABLE"
    source["transport_status"] = status
    source["status"] = (
        "EOD"
        if authoritative and required_event_date and status == "STALE"
        else status
    )
    source["authoritative"] = authoritative
    source["coverage_status"] = coverage_status
    if required_event_date:
        source["required_event_date"] = required_event_date
        source["session_aligned"] = session_aligned
    if upstreams:
        if authoritative and required_event_date:
            for upstream in upstreams:
                upstream_status = str(
                    upstream.get("status") or "UNAVAILABLE"
                ).upper()
                if (
                    upstream_status == "STALE"
                    and str(upstream.get("latest_event_at") or "")[:10]
                    == required_event_date
                ):
                    upstream["transport_status"] = upstream_status
                    upstream["status"] = "EOD"
        source["upstreams"] = upstreams
    return source


def _valid_session_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value or ""))
    except ValueError:
        return False
    return True


def _session_date_is_fresh(
    value: Any,
    *,
    as_of: datetime,
    closed_dates: set[date],
) -> bool:
    try:
        session = date.fromisoformat(str(value or ""))
    except ValueError:
        return False
    expected_session = expected_latest_completed_session(
        as_of,
        closed_dates=closed_dates,
    )
    return session == expected_session


def _session_date_is_future(value: Any, *, as_of: date) -> bool:
    try:
        session = date.fromisoformat(str(value or ""))
    except ValueError:
        return False
    return session > as_of


def _valid_company_symbol(value: Any) -> bool:
    symbol = _text(value)
    return bool(symbol and _NON_SECURITY_RE.fullmatch(symbol))


def _lookback_dates(
    target: date,
    days: int,
    *,
    closed_dates: set[date] | None = None,
) -> Iterable[date]:
    closed = closed_dates or set()
    for offset in range(max(1, days)):
        candidate = target - timedelta(days=offset)
        if candidate.weekday() < 5 and candidate not in closed:
            yield candidate


def _field_index(fields: list[str], name: str) -> int:
    try:
        return fields.index(name)
    except ValueError as exc:
        raise ValueError(f"official daily quote payload is missing field: {name}") from exc


def _signed_change(direction: Any, value: Any) -> float | None:
    magnitude = _number(value)
    if magnitude is None:
        return None
    direction_text = _HTML_TAG_RE.sub("", str(direction or "")).strip()
    if "-" in direction_text:
        return -abs(magnitude)
    if "+" in direction_text:
        return abs(magnitude)
    return magnitude


def _text(value: Any) -> str:
    return _HTML_TAG_RE.sub("", str(value or "")).strip()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = _HTML_TAG_RE.sub("", str(value)).strip().replace(",", "")
    if not text or text in {"--", "---", "N/A", "nan", "NaN", "null"}:
        return None
    text = text.replace("+", "", 1)
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _parse_gregorian_date(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) != 8:
        return ""
    try:
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def _parse_roc_date(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) == 8 and text.startswith("20"):
        return _parse_gregorian_date(text)
    if len(text) < 7:
        return ""
    try:
        year = int(text[:-4]) + 1911
        month = int(text[-4:-2])
        day = int(text[-2:])
        return date(year, month, day).isoformat()
    except ValueError:
        return ""
