from __future__ import annotations

import json
import math
import os
import re
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import quote as quote_path_segment
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
    urlopen,
)

from taiwan_stock_analysis.bounded_loader import run_bounded_loaders
from taiwan_stock_analysis.fubon_market import (
    FUBON_STOCK_BASE_URL,
    FubonAuthenticationError,
    FubonConfigurationError,
    FubonSDKUnavailableError,
    FubonSessionError,
    FubonSessionManager,
)
from taiwan_stock_analysis.fubon_stream import (
    FubonWebSocketFeed,
    resolve_fubon_websocket_index_symbol,
)
from taiwan_stock_analysis.market_intelligence import (
    fetch_tpex_fund_flow,
    fetch_twse_fund_flow,
)
from taiwan_stock_analysis.news_urls import safe_http_url
from taiwan_stock_analysis.trading_calendar import (
    TAIPEI,
    TWSE_HOLIDAY_URL,
    expected_latest_completed_session,
    expected_live_quote_session,
    parse_twse_closed_dates,
)


TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TWSE_NEWS_URL = "https://openapi.twse.com.tw/v1/news/newsList"
TWSE_MATERIAL_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"
TPEX_MATERIAL_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"
TWSE_DISPOSITION_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
TWSE_NOTICE_URL = "https://openapi.twse.com.tw/v1/announcement/notice"
TPEX_DISPOSITION_URL = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
TPEX_WARNING_URL = "https://www.tpex.org.tw/openapi/v1/tpex_trading_warning_information"
FUGLE_QUOTE_URL = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
FUGLE_TICKERS_URL = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/tickers"
FUBON_SNAPSHOT_PATH = "snapshot/quotes/{market}"
FUBON_QUOTE_PATH = "intraday/quote/{symbol}"
FUBON_TICKERS_PATH = "intraday/tickers"

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,15}$")
_MAX_RESPONSE_BYTES = 24 * 1024 * 1024
_NEWS_RESPONSE_LIMIT = 96
_DEFAULT_SYMBOL_LIMIT = 40
_MAX_CACHE_ENTRIES = 256
_FUGLE_MAX_CALLS_PER_MINUTE = 60
_FUGLE_MAX_CONCURRENCY = 4
_FUGLE_REQUEST_DEADLINE_SECONDS = 12.0
_FUGLE_NEGATIVE_CACHE_SECONDS = 15.0
_FUBON_MAX_CALLS_PER_MINUTE = 240
_FUBON_MAX_CONCURRENCY = 4
_FUBON_REQUEST_DEADLINE_SECONDS = 12.0
_FUBON_NEGATIVE_CACHE_SECONDS = 15.0
_FUBON_RATE_LIMIT_CACHE_SECONDS = 60.0
_SNAPSHOT_COMPONENT_DEADLINE_SECONDS = 11.0
_SNAPSHOT_COMPONENT_CAPACITY = 4
_MARKET_DATA_PROVIDERS = {"auto", "fubon", "fugle", "twse-mis-personal"}

JsonFetcher = Callable[..., Any]
Clock = Callable[[], datetime]


class _RejectRedirects(HTTPRedirectHandler):
    """Keep authentication headers on the originally requested origin."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class _CacheValue:
    payload: Any
    fetched_at: datetime
    expires_at: float


@dataclass(frozen=True)
class _LoadedRows:
    rows: list[dict[str, Any]]
    errors: tuple[str, ...] = ()
    upstreams: tuple[dict[str, Any], ...] = ()


class _NegativeFugleCacheHit(TimeoutError):
    """Raised when a request is suppressed by an existing negative cache entry."""


class _FugleAdmissionError(TimeoutError):
    """Raised before upstream I/O when provider capacity or deadline is exhausted."""


class _FubonAdmissionError(TimeoutError):
    """Raised before upstream I/O when Fubon capacity or deadline is exhausted."""


class _NegativeFubonCacheHit(TimeoutError):
    """Raised while a failed Fubon request remains in cooldown."""


class _ProviderGate:
    def __init__(
        self,
        *,
        max_calls: int,
        window_seconds: float,
        concurrency: int,
        provider_label: str = "Fugle",
        admission_error: type[TimeoutError] = _FugleAdmissionError,
    ) -> None:
        self._max_calls = max(1, int(max_calls))
        self._window_seconds = max(1.0, float(window_seconds))
        self._provider_label = str(provider_label)
        self._admission_error = admission_error
        self._calls: list[float] = []
        self._calls_lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(max(1, int(concurrency)))

    def call(self, loader: Callable[[], Any], *, deadline: float) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._semaphore.acquire(timeout=remaining):
            raise self._admission_error(
                f"{self._provider_label} request deadline or concurrency limit reached"
            )
        try:
            now = time.monotonic()
            with self._calls_lock:
                cutoff = now - self._window_seconds
                self._calls = [called_at for called_at in self._calls if called_at > cutoff]
                if len(self._calls) >= self._max_calls:
                    raise self._admission_error(
                        f"{self._provider_label} provider-wide request budget exhausted"
                    )
                self._calls.append(now)
            return loader()
        finally:
            self._semaphore.release()


_FUGLE_PROCESS_GATE = _ProviderGate(
    max_calls=_FUGLE_MAX_CALLS_PER_MINUTE,
    window_seconds=60,
    concurrency=_FUGLE_MAX_CONCURRENCY,
)
_FUBON_PROCESS_GATE = _ProviderGate(
    max_calls=_FUBON_MAX_CALLS_PER_MINUTE,
    window_seconds=60,
    concurrency=_FUBON_MAX_CONCURRENCY,
    provider_label="Fubon",
    admission_error=_FubonAdmissionError,
)


def _default_clock() -> datetime:
    return datetime.now(TAIPEI)


def _http_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    timeout_seconds: float | None = None,
    allow_redirects: bool = True,
    compatibility_tls: bool = True,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Taiwan-Equity-Lens/0.54 (+local-live-market-dashboard)",
    }
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    context = _verified_ssl_context(compatibility_tls=compatibility_tls)
    timeout = 8.0
    if timeout_seconds is not None:
        requested_timeout = float(timeout_seconds)
        if not math.isfinite(requested_timeout) or requested_timeout <= 0:
            raise TimeoutError("upstream request deadline reached")
        timeout = min(timeout, max(0.001, requested_timeout))
    if allow_redirects:
        response_context = urlopen(request, timeout=timeout, context=context)
    else:
        opener = build_opener(
            HTTPSHandler(context=context),
            _RejectRedirects(),
        )
        response_context = opener.open(request, timeout=timeout)
    with response_context as response:
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("upstream response exceeded the configured size limit")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("upstream returned invalid UTF-8 JSON") from exc


def _verified_ssl_context(*, compatibility_tls: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    # Several official Taiwan market endpoints still serve a certificate chain
    # that OpenSSL 3 rejects only when X509 strict-mode extension checks are on.
    # Keep hostname and CA verification enabled, but match the compatibility
    # policy already used by market_intelligence._open_url. Credential-bearing
    # Fugle requests explicitly enable strict mode on runtimes that support it.
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        if compatibility_tls:
            context.verify_flags &= ~strict_flag
        else:
            context.verify_flags |= strict_flag
    return context


def _valid_fugle_api_key(value: str) -> bool:
    return bool(value) and len(value) <= 512 and all(
        33 <= ord(character) <= 126
        for character in value
    )


def _valid_fubon_api_key(value: str) -> bool:
    return _valid_fugle_api_key(value)


def normalize_symbols(values: Iterable[object], *, limit: int = _DEFAULT_SYMBOL_LIMIT) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = str(value or "").strip().upper()
        if not symbol or symbol in seen or not _SYMBOL_RE.fullmatch(symbol):
            continue
        symbols.append(symbol)
        seen.add(symbol)
        if len(symbols) >= limit:
            break
    return symbols


def _normalize_probe_symbols(
    values: Iterable[object],
) -> tuple[list[str], list[str]]:
    symbols: list[str] = []
    seen: set[str] = set()
    invalid_count = 0
    over_limit = False
    for value in values:
        symbol = str(value or "").strip().upper()
        if not symbol or not _SYMBOL_RE.fullmatch(symbol):
            invalid_count += 1
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        if len(symbols) >= _DEFAULT_SYMBOL_LIMIT:
            over_limit = True
            continue
        symbols.append(symbol)
    errors: list[str] = []
    if invalid_count:
        errors.append(
            "provider probe rejected "
            f"{invalid_count} invalid symbol value"
            + ("" if invalid_count == 1 else "s")
        )
    if over_limit:
        errors.append(
            "provider probe accepts at most "
            f"{_DEFAULT_SYMBOL_LIMIT} unique symbols"
        )
    if not symbols and not errors:
        errors.append("provider probe requires at least one valid symbol")
    return symbols, errors


class LiveMarketService:
    """Short-lived provider cache and normalized live-market snapshot.

    The default TWSE MIS provider is intentionally restricted to a loopback,
    personal-development server.  It is an undocumented browser endpoint and
    must not be treated as a production redisplay licence.  A public server
    requires an explicitly licensed provider configuration.
    """

    def __init__(
        self,
        *,
        public_mode: bool = False,
        fetch_json: JsonFetcher | None = None,
        clock: Clock | None = None,
        fubon_personal_id: str | None = None,
        fubon_api_key: str | None = None,
        fubon_cert_path: str | None = None,
        fubon_cert_password: str | None = None,
        fubon_market_data_only_confirmed: bool | None = None,
        fubon_redisplay_licensed: bool | None = None,
        fubon_session_manager: FubonSessionManager | None = None,
        fubon_stream_feed: Any | None = None,
        fugle_api_key: str | None = None,
        fugle_redisplay_licensed: bool | None = None,
        provider: str | None = None,
        component_deadline_seconds: float = _SNAPSHOT_COMPONENT_DEADLINE_SECONDS,
    ) -> None:
        self.public_mode = bool(public_mode)
        self._fetch_json = fetch_json or _http_json
        self._fetch_json_supports_timeout = fetch_json is None
        self._clock = clock or _default_clock
        requested_provider = str(
            (
                provider
                if provider is not None
                else os.getenv("MARKET_DATA_PROVIDER", "auto")
            )
            or "auto"
        ).strip().lower()
        if requested_provider not in _MARKET_DATA_PROVIDERS:
            supported = ", ".join(sorted(_MARKET_DATA_PROVIDERS))
            raise ValueError(
                f"unsupported market data provider {requested_provider!r}; "
                f"expected one of: {supported}"
            )
        self._provider_requested = requested_provider
        self._fubon_personal_id = str(
            fubon_personal_id
            if fubon_personal_id is not None
            else os.getenv("FUBON_PERSONAL_ID", "")
        ).strip()
        self._fubon_api_key = str(
            fubon_api_key
            if fubon_api_key is not None
            else os.getenv("FUBON_API_KEY", "")
        ).strip()
        self._fubon_cert_path = str(
            fubon_cert_path
            if fubon_cert_path is not None
            else os.getenv("FUBON_CERT_PATH", "")
        ).strip()
        self._fubon_cert_password = str(
            fubon_cert_password
            if fubon_cert_password is not None
            else os.getenv("FUBON_CERT_PASSWORD", "")
        )
        self._fubon_key_format_valid = _valid_fubon_api_key(self._fubon_api_key)
        fubon_scope_confirmed = os.getenv(
            "FUBON_MARKET_DATA_ONLY_CONFIRMED",
            "",
        ).strip().lower()
        if (
            fubon_market_data_only_confirmed is not None
            and not isinstance(fubon_market_data_only_confirmed, bool)
        ):
            raise TypeError(
                "fubon_market_data_only_confirmed must be a boolean"
            )
        self._fubon_market_data_only_confirmed = (
            fubon_market_data_only_confirmed is True
            if fubon_market_data_only_confirmed is not None
            else (
                True
                if fubon_session_manager is not None
                else fubon_scope_confirmed in {"1", "true", "yes"}
            )
        )
        fubon_env_licensed = os.getenv(
            "FUBON_REDISPLAY_LICENSED",
            "",
        ).strip().lower()
        if (
            fubon_redisplay_licensed is not None
            and not isinstance(fubon_redisplay_licensed, bool)
        ):
            raise TypeError("fubon_redisplay_licensed must be a boolean")
        self._fubon_redisplay_licensed = (
            fubon_redisplay_licensed is True
            if fubon_redisplay_licensed is not None
            else fubon_env_licensed in {"1", "true", "yes"}
        )
        self._fubon_session_injected = fubon_session_manager is not None
        self._fubon_any_config = bool(
            self._fubon_personal_id
            or self._fubon_api_key
            or self._fubon_cert_path
            or self._fubon_cert_password
        )
        self._fubon_session_manager = (
            fubon_session_manager
            if fubon_session_manager is not None
            else FubonSessionManager(
                personal_id=self._fubon_personal_id,
                api_key=self._fubon_api_key,
                cert_path=self._fubon_cert_path,
                cert_password=self._fubon_cert_password,
            )
        )
        self._fubon_stream_feed = fubon_stream_feed
        self._fubon_stream_injected = fubon_stream_feed is not None
        self._fubon_stream_create_attempted = False
        self._fubon_stream_desired_stocks: set[str] = set()
        self._fubon_stream_desired_indices: set[str] = set()
        self._fubon_stream_lock = threading.RLock()
        self._fugle_api_key = str(
            fugle_api_key if fugle_api_key is not None else os.getenv("FUGLE_API_KEY", "")
        ).strip()
        self._fugle_key_format_valid = _valid_fugle_api_key(self._fugle_api_key)
        env_licensed = os.getenv("FUGLE_REDISPLAY_LICENSED", "").strip().lower()
        if (
            fugle_redisplay_licensed is not None
            and not isinstance(fugle_redisplay_licensed, bool)
        ):
            raise TypeError("fugle_redisplay_licensed must be a boolean")
        self._fugle_redisplay_licensed = (
            fugle_redisplay_licensed is True
            if fugle_redisplay_licensed is not None
            else env_licensed in {"1", "true", "yes"}
        )
        self._provider_state_lock = threading.Lock()
        self._provider_last_attempt_ok: bool | None = None
        self._provider_last_success_at = ""
        self._provider_last_error = ""
        self._cache: dict[str, _CacheValue] = {}
        self._cache_lock = threading.RLock()
        self._fubon_auth_generation = 0
        self._fubon_auth_blocked = False
        self._fubon_auth_invalidation_in_progress = False
        self._loader_locks: dict[str, threading.Lock] = {}
        self._fugle_gate = (
            _FUGLE_PROCESS_GATE
            if fetch_json is None
            else _ProviderGate(
                max_calls=_FUGLE_MAX_CALLS_PER_MINUTE,
                window_seconds=60,
                concurrency=_FUGLE_MAX_CONCURRENCY,
            )
        )
        self._fugle_negative_cache: dict[str, float] = {}
        self._fubon_gate = (
            _FUBON_PROCESS_GATE
            if fetch_json is None
            else _ProviderGate(
                max_calls=_FUBON_MAX_CALLS_PER_MINUTE,
                window_seconds=60,
                concurrency=_FUBON_MAX_CONCURRENCY,
                provider_label="Fubon",
                admission_error=_FubonAdmissionError,
            )
        )
        self._fubon_negative_cache: dict[str, float] = {}
        self._component_deadline_seconds = max(
            0.05,
            float(component_deadline_seconds),
        )
        self._component_capacity = threading.BoundedSemaphore(
            _SNAPSHOT_COMPONENT_CAPACITY
        )

    def snapshot(
        self,
        symbols: Iterable[object],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(force, bool):
            raise TypeError("force must be a boolean")
        if force:
            with self._cache_lock:
                self._purge_snapshot_component_caches_locked()
        snapshot_deadline = (
            time.monotonic() + self._component_deadline_seconds
        )
        requested_symbols = normalize_symbols(symbols)
        now = self._now()
        provider_mode = self._quote_provider_mode()
        errors: list[str] = []

        component_results = self._load_snapshot_components(
            requested_symbols,
            provider_mode=provider_mode,
            errors=errors,
        )
        quotes_result = component_results["quotes"]
        news_result = component_results["news"]
        alert_result = component_results["alerts"]
        flow_result = component_results["fund_flow"]

        quotes = [
            dict(row)
            for row in quotes_result.get("payload") or []
            if isinstance(row, dict)
        ]
        calendar_result: dict[str, Any] | None = None
        calendar_closed_dates: set[date] | None = None
        if (
            not quotes_result.get("fallback")
            and _quotes_need_calendar_reclassification(quotes, now=now)
        ):
            calendar_result = self._load_calendar_component(
                errors,
                timeout_seconds=max(
                    0.01,
                    snapshot_deadline - time.monotonic(),
                ),
            )
            if str(calendar_result.get("status") or "") == "FRESH":
                closed_dates = {
                    parsed
                    for row in calendar_result.get("payload") or []
                    if isinstance(row, dict)
                    for parsed in [_iso_date(row.get("date"))]
                    if parsed is not None
                }
                if closed_dates:
                    calendar_closed_dates = closed_dates
                    quotes = [
                        _reclassify_quote_with_calendar(
                            row,
                            now=now,
                            closed_dates=closed_dates,
                        )
                        for row in quotes
                    ]
                    quotes_result = _reclassified_quote_component(
                        quotes_result,
                        quotes,
                    )
        stream_health: dict[str, Any] | None = None
        if provider_mode == "fubon":
            quotes, stream_health = self._apply_fubon_stream_overlay(
                quotes,
                requested_symbols=requested_symbols,
                errors=errors,
            )
        news = list(news_result.get("payload") or [])
        alerts = list(alert_result.get("payload") or [])
        fund_flow = list(flow_result.get("payload") or [])
        if calendar_closed_dates is not None and not flow_result.get("fallback"):
            flow_result = _reclassified_dated_component(
                flow_result,
                fund_flow,
                now=now,
                key="date",
                closed_dates=calendar_closed_dates,
            )
        indices = [row for row in quotes if row.get("kind") == "index"]
        securities = [row for row in quotes if row.get("kind") == "equity"]
        market = build_market_summary(indices, securities, now=now)
        if quotes_result.get("fallback") and quotes_result.get("status") == "STALE":
            market = {
                **market,
                "status": "STALE",
                "regime": "行情快取已過期",
                "strategy": "neutral",
                "posture": "行情來源更新失敗；目前只保留最後成功快取，不作即時盤勢判讀。",
            }
        # The headline status is specifically the quote-session status.  Fresh
        # news must never make an unavailable quote feed look like EOD market
        # data; each non-price component has its own status below.
        overall_status = str(market.get("status") or "UNAVAILABLE")
        flow_by_stock = {
            str(row.get("stock_id") or ""): row
            for row in fund_flow
            if str(row.get("stock_id") or "")
        }
        selected_flow = [flow_by_stock[symbol] for symbol in requested_symbols if symbol in flow_by_stock]
        flow_total = sum(
            float(row.get("total_net") or 0)
            for row in selected_flow
            if _finite(row.get("total_net")) is not None
        )
        active_alerts = [
            row
            for row in alerts
            if row.get("active") and str(row.get("symbol") or "") in set(requested_symbols)
        ]
        returned_symbols = {
            str(row.get("symbol") or "")
            for row in securities
            if str(row.get("symbol") or "")
        }
        missing_symbols = [
            symbol for symbol in requested_symbols if symbol not in returned_symbols
        ]
        quote_public_status = _component_public_status(quotes_result)
        websocket_rows = [
            row
            for row in quotes
            if "WebSocket" in str(row.get("source") or "")
        ]
        if websocket_rows:
            quote_public_status["status"] = _quote_collection_status(
                row.get("status") for row in quotes
            )
        quote_public_status["requested_symbol_count"] = len(requested_symbols)
        quote_public_status["returned_symbol_count"] = (
            len(requested_symbols) - len(missing_symbols)
        )
        quote_public_status["missing_symbols"] = missing_symbols
        if missing_symbols:
            quote_public_status["partial"] = True
            quote_public_status["status"] = "STALE"
        if stream_health is not None:
            quote_public_status["stream"] = stream_health
        source_status = {
            "quotes": quote_public_status,
            "news": _component_public_status(news_result),
            "alerts": _component_public_status(alert_result),
            "fund_flow": _component_public_status(
                flow_result,
                status=_dated_market_rows_status(
                    fund_flow,
                    now=now,
                    key="date",
                    closed_dates=calendar_closed_dates,
                ),
            ),
        }
        source_status["news"]["available_row_count"] = len(news)
        source_status["news"]["returned_row_count"] = min(
            len(news),
            _NEWS_RESPONSE_LIMIT,
        )
        source_status["news"]["truncated"] = len(news) > _NEWS_RESPONSE_LIMIT
        if calendar_result is not None:
            source_status["trading_calendar"] = _component_public_status(
                calendar_result
            )
        return {
            "schema_version": 1,
            "kind": "live_market_snapshot",
            "ok": bool(quotes or news or alerts),
            "quotes_ok": (
                overall_status in {"LIVE", "EOD"}
                and not missing_symbols
            ),
            "generated_at": now.isoformat(),
            "status": overall_status,
            "refresh_after_seconds": (
                self._minimum_refresh_seconds(provider_mode)
                if market.get("status") == "LIVE"
                else 60
            ),
            "provider": self._provider_metadata(),
            "market": market,
            "quotes": securities,
            "indices": indices,
            "missing_symbols": missing_symbols,
            "news": news[:_NEWS_RESPONSE_LIMIT],
            "alerts": alerts[:120],
            "active_watchlist_alerts": active_alerts,
            "fund_flow": selected_flow,
            "fund_flow_total": flow_total if selected_flow else None,
            "source_status": source_status,
            "errors": errors,
        }

    def health(self) -> dict[str, Any]:
        mode = self._quote_provider_mode()
        configuration_error = self._provider_unavailable_reason()
        with self._provider_state_lock:
            last_attempt_ok = self._provider_last_attempt_ok
            last_success_at = self._provider_last_success_at
            last_error = self._provider_last_error
        configured = mode != "unavailable"
        ready = bool(configured and last_attempt_ok is True)
        health = {
            "ok": ready,
            "process_alive": True,
            "configured": configured,
            "ready": ready,
            "usable": ready,
            "provider_requested": self._provider_requested,
            "provider_mode": mode,
            "public_mode": self.public_mode,
            "fubon_configured": (
                self._fubon_session_injected
                or not bool(self._fubon_configuration_error())
            ),
            "fubon_key_configured": bool(self._fubon_api_key),
            "fubon_key_format_valid": (
                self._fubon_key_format_valid if self._fubon_api_key else None
            ),
            "fubon_market_data_only_confirmed": (
                self._fubon_market_data_only_confirmed
            ),
            "fubon_sdk_available": (
                True
                if self._fubon_session_injected
                else self._fubon_session_manager.sdk_available()
            ),
            "fubon_redisplay_licensed": self._fubon_redisplay_licensed,
            "fugle_configured": bool(self._fugle_api_key),
            "fugle_key_format_valid": (
                self._fugle_key_format_valid if self._fugle_api_key else None
            ),
            "fugle_redisplay_licensed": self._fugle_redisplay_licensed,
            "provider_budget_scope": "single_process",
            "provider_capacity_guarded": mode in {"fubon", "fugle"},
            "provider_calls_per_minute_budget": (
                _FUBON_MAX_CALLS_PER_MINUTE
                if mode == "fubon"
                else _FUGLE_MAX_CALLS_PER_MINUTE
                if mode == "fugle"
                else 60
            ),
            "configuration_error": configuration_error,
            "last_attempt_ok": last_attempt_ok,
            "last_success_at": last_success_at,
            "last_error": last_error,
            "quote_cache_seconds": 4,
            "minimum_client_refresh_seconds": self._minimum_refresh_seconds(mode),
            "estimated_provider_calls_per_snapshot": self.provider_request_cost(
                (str(index) for index in range(_DEFAULT_SYMBOL_LIMIT))
            ),
            "news_refresh_seconds": 60,
            "component_deadline_seconds": self._component_deadline_seconds,
        }
        with self._fubon_stream_lock:
            stream = self._fubon_stream_feed
        if mode == "fubon":
            if stream is not None:
                try:
                    health["stream"] = _public_stream_health(
                        dict(stream.health())
                    )
                except Exception:
                    health["stream"] = {
                        "ok": False,
                        "ready": False,
                        "usable": False,
                        "status": "STALE",
                        "transport_status": "ERROR",
                    }
            else:
                health["stream"] = {
                    "ok": False,
                    "ready": False,
                    "usable": False,
                    "status": "UNAVAILABLE",
                    "transport_status": "NOT_CONNECTED",
                }
        return health

    def provider_request_cost(self, symbols: Iterable[object]) -> int:
        """Return a conservative upstream-call reservation for one snapshot."""

        mode = self._quote_provider_mode()
        symbol_count = len(normalize_symbols(symbols))
        if mode == "fubon":
            # Two full-market snapshots, two index quotes, plus first-use index
            # discovery. Cached refreshes normally consume only four calls.
            return 6
        if mode == "fugle":
            return symbol_count + 4
        if mode == "twse_mis_personal":
            return 1
        return 0

    def _apply_fubon_stream_overlay(
        self,
        rows: list[dict[str, Any]],
        *,
        requested_symbols: list[str],
        errors: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        feed = self._ensure_fubon_stream(errors)
        if feed is None:
            return rows, {
                "ok": False,
                "ready": False,
                "usable": False,
                "status": "UNAVAILABLE",
                "transport_status": "NOT_CONNECTED",
            }

        stock_symbols = {
            str(row.get("provider_symbol") or row.get("symbol") or "")
            for row in rows
            if row.get("kind") == "equity"
            and str(row.get("symbol") or "") in set(requested_symbols)
        }
        stock_symbols.discard("")
        index_symbol_map = {
            provider_symbol: resolve_fubon_websocket_index_symbol(
                provider_symbol
            )
            for row in rows
            if row.get("kind") == "index"
            and (
                provider_symbol := str(
                    row.get("provider_symbol") or ""
                )
            )
        }
        index_symbols = set(index_symbol_map.values())
        try:
            with self._fubon_stream_lock:
                removed_stocks = (
                    self._fubon_stream_desired_stocks - stock_symbols
                )
                removed_indices = (
                    self._fubon_stream_desired_indices - index_symbols
                )
                self._fubon_stream_desired_stocks = set(stock_symbols)
                self._fubon_stream_desired_indices = set(index_symbols)
            if removed_stocks or removed_indices:
                feed.unsubscribe(
                    stock_symbols=removed_stocks,
                    index_symbols=removed_indices,
                )
            feed.subscribe(
                stock_symbols=stock_symbols,
                index_symbols=index_symbols,
            )
            feed.connect()
            overlay = feed.overlay_snapshot()
            health = dict(feed.health())
        except Exception as exc:
            errors.append(
                "fubon-stream: "
                + self._safe_provider_error(exc, provider_mode="fubon")
            )
            return rows, {
                "ok": False,
                "ready": False,
                "usable": False,
                "status": "STALE",
                "transport_status": "ERROR",
            }

        aggregates = overlay.get("aggregates")
        indices = overlay.get("indices")
        aggregate_map = aggregates if isinstance(aggregates, dict) else {}
        index_map = indices if isinstance(indices, dict) else {}
        overlaid: list[dict[str, Any]] = []
        for baseline in rows:
            provider_symbol = str(
                baseline.get("provider_symbol")
                or baseline.get("symbol")
                or ""
            )
            websocket_symbol = index_symbol_map.get(
                provider_symbol,
                provider_symbol,
            )
            stream_row = (
                index_map.get(websocket_symbol)
                if baseline.get("kind") == "index"
                else aggregate_map.get(provider_symbol)
            )
            stream_status = str(
                (stream_row or {}).get("status") or "UNAVAILABLE"
            ).upper()
            if not isinstance(stream_row, dict) or stream_status not in {
                "LIVE",
                "DELAYED",
                "EOD",
            }:
                overlaid.append(baseline)
                continue
            if not _stream_row_matches_rest_baseline(baseline, stream_row):
                overlaid.append(baseline)
                continue
            if baseline.get("kind") == "index":
                index_value = _finite(stream_row.get("index"))
                if index_value is None:
                    overlaid.append(baseline)
                    continue
                normalized_index = dict(baseline)
                normalized_index["price"] = index_value
                normalized_index["status"] = stream_status
                normalized_index["source"] = (
                    "Fubon Neo WebSocket (Normal)"
                )
                normalized_index["stream_provider_symbol"] = (
                    websocket_symbol
                )
                normalized_index["source_event_time"] = str(
                    stream_row.get("source_event_time") or ""
                )
                previous_close = _finite(
                    normalized_index.get("previous_close")
                )
                if previous_close not in {None, 0}:
                    change = index_value - previous_close
                    normalized_index["change"] = change
                    normalized_index["change_percent"] = (
                        change / previous_close * 100.0
                    )
                overlaid.append(normalized_index)
                continue
            stream_price = _first_finite(
                stream_row.get("lastPrice"),
                stream_row.get("closePrice"),
            )
            if stream_price is None:
                overlaid.append(baseline)
                continue
            normalized = dict(baseline)
            normalized["price"] = stream_price
            normalized["status"] = stream_status
            normalized["source"] = "Fubon Neo WebSocket (Normal)"
            normalized["provider_symbol"] = provider_symbol
            normalized["stream_provider_symbol"] = websocket_symbol
            normalized["source_event_time"] = str(
                stream_row.get("source_event_time")
                or baseline.get("source_event_time")
                or ""
            )
            for provider_key, output_key in (
                ("openPrice", "open"),
                ("highPrice", "high"),
                ("lowPrice", "low"),
            ):
                value = _finite(stream_row.get(provider_key))
                if value is not None:
                    normalized[output_key] = value
            total = (
                stream_row.get("total")
                if isinstance(stream_row.get("total"), dict)
                else {}
            )
            for provider_key, output_key in (
                ("tradeVolume", "volume"),
                ("tradeValue", "trade_value"),
            ):
                value = _finite(total.get(provider_key))
                if value is not None:
                    normalized[output_key] = value
            bids = stream_row.get("bids")
            asks = stream_row.get("asks")
            if isinstance(bids, list) and bids and isinstance(bids[0], dict):
                bid = _finite(bids[0].get("price"))
                if bid is not None:
                    normalized["best_bid"] = bid
            if isinstance(asks, list) and asks and isinstance(asks[0], dict):
                ask = _finite(asks[0].get("price"))
                if ask is not None:
                    normalized["best_ask"] = ask
            is_close = _optional_bool(stream_row.get("isClose"))
            if is_close is not None:
                normalized["provider_is_close"] = is_close
            previous_close = _finite(baseline.get("previous_close"))
            if previous_close not in {None, 0}:
                change = stream_price - previous_close
                normalized["change"] = change
                normalized["change_percent"] = change / previous_close * 100.0
            else:
                normalized["change"] = None
                normalized["change_percent"] = None
            overlaid.append(normalized)
        return overlaid, _public_stream_health(health)

    def _ensure_fubon_stream(
        self,
        errors: list[str],
    ) -> Any | None:
        with self._fubon_stream_lock:
            if self._fubon_stream_feed is not None:
                return self._fubon_stream_feed
            if self._fubon_stream_create_attempted:
                return None
            self._fubon_stream_create_attempted = True
        client_loader = getattr(
            self._fubon_session_manager,
            "stock_websocket_client",
            None,
        )
        if not callable(client_loader):
            return None
        authentication_generation = self._fubon_auth_generation_value()
        try:
            client = client_loader(
                timeout_seconds=self._component_deadline_seconds
            )
            candidate = FubonWebSocketFeed(
                client,
                clock=self._clock,
            )
        except Exception as exc:
            with self._fubon_stream_lock:
                self._fubon_stream_create_attempted = False
            errors.append(
                "fubon-stream: "
                + self._safe_provider_error(
                    exc,
                    provider_mode="fubon",
                )
            )
            return None
        if authentication_generation != self._fubon_auth_generation_value():
            try:
                candidate.close()
            except Exception:
                pass
            with self._fubon_stream_lock:
                self._fubon_stream_create_attempted = False
            return None
        with self._fubon_stream_lock:
            if self._fubon_stream_feed is None:
                self._fubon_stream_feed = candidate
                return candidate
            existing = self._fubon_stream_feed
        try:
            candidate.close()
        except Exception:
            pass
        return existing

    def close(self) -> None:
        """Release the optional broker SDK session without surfacing secrets."""

        self._detach_fubon_stream()
        self._fubon_session_manager.close()

    def _detach_fubon_stream(self) -> None:
        with self._fubon_stream_lock:
            stream = self._fubon_stream_feed
            self._fubon_stream_feed = None
            self._fubon_stream_create_attempted = False
            self._fubon_stream_desired_stocks.clear()
            self._fubon_stream_desired_indices.clear()
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass

    @staticmethod
    def _minimum_refresh_seconds(mode: str) -> int:
        return 30 if mode == "fugle" else 5

    def probe(self, symbols: Iterable[object] = ("2330",)) -> dict[str, Any]:
        """Probe only the configured quote provider without loading other feeds.

        The returned evidence is safe to log: it contains provider metadata and
        normalized market rows, but never includes the API key or request headers.
        """

        requested_symbols, input_errors = _normalize_probe_symbols(symbols)
        mode = self._quote_provider_mode()
        if input_errors:
            return {
                "ok": False,
                "kind": "market_data_provider_probe",
                "generated_at": self._now().isoformat(),
                "provider_requested": self._provider_requested,
                "provider_mode": mode,
                "provider": self._provider_metadata(),
                "status": "UNAVAILABLE",
                "requested_symbols": requested_symbols,
                "returned_symbols": [],
                "missing_symbols": requested_symbols,
                "indices_complete": False,
                "quotes_complete": False,
                "quotes": [],
                "indices": [],
                "errors": input_errors,
            }
        if mode == "unavailable":
            reason = self._provider_unavailable_reason()
            return {
                "ok": False,
                "kind": "market_data_provider_probe",
                "generated_at": self._now().isoformat(),
                "provider_requested": self._provider_requested,
                "provider_mode": mode,
                "provider": self._provider_metadata(),
                "status": "UNAVAILABLE",
                "requested_symbols": requested_symbols,
                "returned_symbols": [],
                "missing_symbols": requested_symbols,
                "indices_complete": False,
                "quotes_complete": False,
                "quotes": [],
                "indices": [],
                "errors": [reason] if reason else ["quote provider is unavailable"],
            }
        try:
            loaded = self._load_quotes(requested_symbols)
        except (
            FubonAuthenticationError,
            FubonConfigurationError,
            FubonSDKUnavailableError,
            FubonSessionError,
            OSError,
            ValueError,
            TimeoutError,
        ) as exc:
            safe_error = self._safe_provider_error(
                exc,
                provider_mode=mode,
            )
            self._record_provider_attempt(False, error=safe_error)
            return {
                "ok": False,
                "kind": "market_data_provider_probe",
                "generated_at": self._now().isoformat(),
                "provider_requested": self._provider_requested,
                "provider_mode": mode,
                "provider": self._provider_metadata(),
                "status": "UNAVAILABLE",
                "requested_symbols": requested_symbols,
                "returned_symbols": [],
                "missing_symbols": requested_symbols,
                "indices_complete": False,
                "quotes_complete": False,
                "quotes": [],
                "indices": [],
                "errors": [safe_error],
            }
        payload, errors, _ = _unpack_loaded_rows(loaded)
        rows = [dict(row) for row in payload or [] if isinstance(row, dict)]
        quotes = [row for row in rows if row.get("kind") == "equity"]
        indices = [row for row in rows if row.get("kind") == "index"]
        returned_symbols = [
            symbol
            for symbol in requested_symbols
            if any(str(row.get("symbol") or "") == symbol for row in quotes)
        ]
        missing_symbols = [
            symbol for symbol in requested_symbols if symbol not in returned_symbols
        ]
        status = _quote_collection_status(
            row.get("status") for row in [*indices, *quotes]
        )
        index_symbols = {
            str(row.get("symbol") or "")
            for row in indices
            if (
                str(row.get("status") or "") in {"LIVE", "EOD"}
                and _finite(row.get("price")) is not None
            )
        }
        indices_complete = {"t00", "o00"}.issubset(index_symbols)
        priced_symbols = {
            str(row.get("symbol") or "")
            for row in quotes
            if (
                str(row.get("status") or "") in {"LIVE", "EOD"}
                and _finite(row.get("price")) is not None
            )
        }
        quotes_complete = set(requested_symbols).issubset(priced_symbols)
        if (
            missing_symbols
            or not indices_complete
            or not quotes_complete
            or errors
        ) and status != "UNAVAILABLE":
            status = "STALE"
        return {
            "ok": bool(requested_symbols)
            and not missing_symbols
            and indices_complete
            and quotes_complete
            and not errors
            and status in {"LIVE", "EOD"},
            "kind": "market_data_provider_probe",
            "generated_at": self._now().isoformat(),
            "provider_requested": self._provider_requested,
            "provider_mode": mode,
            "provider": self._provider_metadata(),
            "status": status,
            "requested_symbols": requested_symbols,
            "returned_symbols": returned_symbols,
            "missing_symbols": missing_symbols,
            "indices_complete": indices_complete,
            "quotes_complete": quotes_complete,
            "quotes": quotes,
            "indices": indices,
            "errors": errors,
        }

    def _record_provider_attempt(self, ok: bool, *, error: str = "") -> None:
        with self._provider_state_lock:
            self._provider_last_attempt_ok = bool(ok)
            self._provider_last_error = str(error or "")
            if ok:
                self._provider_last_success_at = self._now().isoformat()

    def _safe_provider_error(
        self,
        exc: BaseException,
        *,
        provider_mode: str | None = None,
    ) -> str:
        mode = provider_mode or self._quote_provider_mode()
        if mode == "twse_mis_personal":
            if isinstance(exc, TimeoutError):
                return "TWSE MIS provider request timed out"
            if isinstance(exc, OSError):
                return "TWSE MIS provider request failed"
            return "TWSE MIS provider response was invalid"
        if mode == "fubon" or self._provider_requested == "fubon":
            if isinstance(exc, HTTPError):
                messages = {
                    401: "Fubon market-data authentication expired (HTTP 401)",
                    403: "Fubon market-data entitlement rejected the request (HTTP 403)",
                    429: "Fubon market-data request quota was exceeded (HTTP 429)",
                }
                return messages.get(
                    int(exc.code),
                    f"Fubon market-data provider returned HTTP {int(exc.code)}",
                )
            if isinstance(exc, FubonSDKUnavailableError):
                return "Fubon Neo SDK is not installed in the active Python environment"
            if isinstance(exc, FubonConfigurationError):
                return str(exc)
            if isinstance(exc, FubonAuthenticationError):
                return "Fubon authentication was rejected"
            if isinstance(exc, FubonSessionError):
                return "Fubon market-data session initialization failed"
            if isinstance(exc, _FubonAdmissionError):
                return str(exc)
            if isinstance(exc, _NegativeFubonCacheHit):
                return str(exc)
            if isinstance(exc, TimeoutError):
                return "Fubon market-data request timed out"
            if isinstance(exc, OSError):
                return "Fubon market-data request failed"
            return "Fubon market-data response was invalid"
        if isinstance(exc, HTTPError):
            messages = {
                401: "Fugle authentication was rejected (HTTP 401)",
                403: "Fugle plan or entitlement rejected the request (HTTP 403)",
                429: "Fugle request quota was exceeded (HTTP 429)",
            }
            return messages.get(
                int(exc.code),
                f"Fugle provider returned HTTP {int(exc.code)}",
            )
        if isinstance(exc, _FugleAdmissionError):
            return str(exc)
        if isinstance(exc, _NegativeFugleCacheHit):
            return str(exc)
        if isinstance(exc, TimeoutError):
            return "Fugle provider request timed out"
        if isinstance(exc, OSError):
            return "Fugle provider request failed"
        message = str(exc)
        if self._fugle_api_key:
            message = message.replace(self._fugle_api_key, "[redacted]")
        message = re.sub(r"[\x00-\x1f\x7f]+", " ", message).strip()
        return message[:240] or "Fugle provider response was invalid"

    def _load_snapshot_components(
        self,
        requested_symbols: list[str],
        *,
        provider_mode: str,
        errors: list[str],
    ) -> dict[str, dict[str, Any]]:
        quote_key = "quotes:" + ",".join(requested_symbols)

        def component(
            key: str,
            ttl_seconds: float,
            loader: Callable[[], Any],
            *,
            wait_for_loader: bool,
        ) -> Callable[[], tuple[dict[str, Any], list[str]]]:
            def load() -> tuple[dict[str, Any], list[str]]:
                local_errors: list[str] = []
                result = self._safe_component(
                    key,
                    ttl_seconds,
                    loader,
                    local_errors,
                    wait_for_loader=wait_for_loader,
                )
                return result, local_errors

            return load

        loaded, failures = run_bounded_loaders(
            {
                "quotes": component(
                    quote_key,
                    4.0 if provider_mode != "unavailable" else 30.0,
                    lambda: self._load_quotes(requested_symbols),
                    wait_for_loader=True,
                ),
                "news": component(
                    "news",
                    60.0,
                    self._load_news,
                    wait_for_loader=False,
                ),
                "alerts": component(
                    "alerts",
                    180.0,
                    self._load_alerts,
                    wait_for_loader=False,
                ),
                "fund_flow": component(
                    "fund-flow",
                    300.0,
                    self._load_fund_flow,
                    wait_for_loader=False,
                ),
            },
            timeout_seconds=self._component_deadline_seconds,
            capacity=self._component_capacity,
        )
        cache_keys = {
            "quotes": quote_key,
            "news": "news",
            "alerts": "alerts",
            "fund_flow": "fund-flow",
        }
        results: dict[str, dict[str, Any]] = {}
        for name in ("quotes", "news", "alerts", "fund_flow"):
            if name in loaded:
                result, local_errors = loaded[name]
                errors.extend(local_errors)
                results[name] = result
                continue
            failure = failures.get(name) or TimeoutError(
                "component snapshot did not complete"
            )
            errors.append(f"{cache_keys[name]}: {failure}")
            results[name] = self._timed_out_component(cache_keys[name])
        return results

    def _timed_out_component(self, key: str) -> dict[str, Any]:
        fallback = self._stale_cache(key)
        if fallback is not None:
            value, _, upstreams = _unpack_loaded_rows(fallback.payload)
            return {
                "payload": value,
                "fetched_at": fallback.fetched_at,
                "cached": True,
                "fallback": True,
                "status": "STALE",
                "upstreams": upstreams,
            }
        return {
            "payload": [],
            "fetched_at": self._now(),
            "cached": False,
            "fallback": False,
            "status": "UNAVAILABLE",
            "upstreams": [],
        }

    def _load_calendar_component(
        self,
        errors: list[str],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        local_errors: list[str] = []
        loaded, failures = run_bounded_loaders(
            {
                "calendar": lambda: self._safe_component(
                    "trading-calendar",
                    6 * 60 * 60,
                    self._load_trading_calendar,
                    local_errors,
                    wait_for_loader=False,
                )
            },
            timeout_seconds=timeout_seconds,
            capacity=self._component_capacity,
        )
        if "calendar" in loaded:
            errors.extend(local_errors)
            return loaded["calendar"]
        failure = failures.get("calendar") or TimeoutError(
            "calendar snapshot did not complete"
        )
        errors.append(f"trading-calendar: {failure}")
        return self._timed_out_component("trading-calendar")

    def breadth_support(self) -> dict[str, Any]:
        """Return complete cached flow/alert rows for full-market enrichment.

        The regular snapshot intentionally intersects these rows with the
        requested watchlist.  The breadth service instead needs the complete
        official batches, while still sharing this service's single-flight
        cache and source freshness metadata.
        """

        errors: list[str] = []
        alert_result = self._safe_component(
            "alerts",
            180.0,
            self._load_alerts,
            errors,
        )
        flow_result = self._safe_component(
            "fund-flow",
            300.0,
            self._load_fund_flow,
            errors,
        )
        live_quote_result: dict[str, Any] | None = None
        if self._quote_provider_mode() == "fubon":
            live_quote_result = self._safe_component(
                "fubon-full-market",
                4.0,
                self._load_fubon_full_market_quotes,
                errors,
            )
        fund_flow = list(flow_result.get("payload") or [])
        source_status = {
            "alerts": _component_public_status(alert_result),
            "fund_flow": _component_public_status(
                flow_result,
                status=_dated_market_rows_status(
                    fund_flow,
                    now=self._now(),
                    key="date",
                ),
            ),
        }
        payload = {
            "alerts": list(alert_result.get("payload") or []),
            "fund_flow": fund_flow,
            "live_quotes": [],
            "source_status": source_status,
            "errors": errors,
        }
        if live_quote_result is not None:
            payload["live_quotes"] = list(
                live_quote_result.get("payload") or []
            )
            source_status["live_quotes"] = _component_public_status(
                live_quote_result
            )
        return payload

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=TAIPEI)
        return value.astimezone(TAIPEI)

    def _quote_provider_mode(self) -> str:
        fubon_ready = not self._fubon_configuration_error() and (
            not self.public_mode or self._fubon_redisplay_licensed
        )
        if self._provider_requested == "fubon":
            return "fubon" if fubon_ready else "unavailable"
        if self._provider_requested == "fugle":
            if self._fugle_key_format_valid and (
                not self.public_mode or self._fugle_redisplay_licensed
            ):
                return "fugle"
            return "unavailable"
        if self._provider_requested == "twse-mis-personal":
            return "twse_mis_personal" if not self.public_mode else "unavailable"
        if self._fubon_any_config or self._fubon_session_injected:
            return "fubon" if fubon_ready else "unavailable"
        if self._fugle_key_format_valid and (
            not self.public_mode or self._fugle_redisplay_licensed
        ):
            return "fugle"
        if not self.public_mode:
            return "twse_mis_personal"
        return "unavailable"

    def _provider_unavailable_reason(self) -> str:
        if self._quote_provider_mode() != "unavailable":
            return ""
        if self._provider_requested == "fubon" or (
            self._provider_requested == "auto"
            and (self._fubon_any_config or self._fubon_session_injected)
        ):
            reason = self._fubon_configuration_error()
            if reason:
                return reason
            if self.public_mode and not self._fubon_redisplay_licensed:
                return (
                    "public mode requires FUBON_REDISPLAY_LICENSED=1 backed by "
                    "an explicit Fubon and exchange redisplay agreement"
                )
            return "the requested Fubon market-data provider is unavailable"
        if self._provider_requested == "twse-mis-personal":
            return "TWSE MIS personal mode is restricted to loopback"
        if self._provider_requested == "auto" and self.public_mode:
            return (
                "public mode requires an explicitly configured Fubon or Fugle "
                "provider with written redisplay permission"
            )
        if not self._fugle_api_key:
            return "FUGLE_API_KEY is not configured"
        if not self._fugle_key_format_valid:
            return "FUGLE_API_KEY has an invalid local format"
        if self.public_mode and not self._fugle_redisplay_licensed:
            return (
                "public mode requires FUGLE_REDISPLAY_LICENSED=1 backed by "
                "an explicit Fugle redisplay agreement"
            )
        return "the requested market data provider is unavailable"

    def _fubon_configuration_error(self) -> str:
        if not self._fubon_session_injected:
            if self._fubon_api_key and not self._fubon_key_format_valid:
                return "FUBON_API_KEY has an invalid local format"
            configuration_error = (
                self._fubon_session_manager.configuration_error()
            )
            if configuration_error:
                return configuration_error
        if not self._fubon_market_data_only_confirmed:
            return (
                "FUBON_MARKET_DATA_ONLY_CONFIRMED=1 is required after "
                "verifying that the broker-side API key has no trading scope"
            )
        return ""

    def _provider_metadata(self) -> dict[str, Any]:
        mode = self._quote_provider_mode()
        if mode == "fubon":
            return {
                "id": "fubon-neo",
                "label": "富邦新一代行情",
                "mode": (
                    "LICENSED_LIVE"
                    if self._fubon_redisplay_licensed
                    else "PERSONAL_BROKER_SESSION"
                ),
                "redistribution_allowed": bool(
                    self._fubon_redisplay_licensed
                ),
                "notice": (
                    "書面合約授權的即時行情。"
                    if self._fubon_redisplay_licensed
                    else "富邦客戶本人使用；不代表可公開轉傳行情。"
                ),
            }
        if mode == "fugle":
            return {
                "id": "fugle-rest",
                "label": "Fugle 即時行情",
                "mode": "LICENSED_LIVE" if self._fugle_redisplay_licensed else "PERSONAL_KEY",
                "redistribution_allowed": bool(self._fugle_redisplay_licensed),
                "notice": (
                    "已宣告公開再揭示授權。"
                    if self._fugle_redisplay_licensed
                    else "個人 API 金鑰僅供本機使用，不代表公開再揭示權。"
                ),
            }
        if mode == "twse_mis_personal":
            return {
                "id": "twse-mis-personal",
                "label": "TWSE 基本市況（本機）",
                "mode": "PERSONAL_LIVE",
                "redistribution_allowed": False,
                "notice": "未文件化的交易所瀏覽端點；僅供本機開發，不可作公開產品資料源。",
            }
        return {
            "id": "unavailable",
            "label": "即時行情尚未授權",
            "mode": "UNAVAILABLE",
            "redistribution_allowed": False,
            "notice": self._provider_unavailable_reason(),
        }

    def _load_quotes(self, symbols: list[str]) -> list[dict[str, Any]] | _LoadedRows:
        mode = self._quote_provider_mode()
        if mode == "fubon":
            return self._load_fubon_quotes(symbols)
        if mode == "fugle":
            return self._load_fugle_quotes(symbols)
        if mode == "twse_mis_personal":
            return self._load_twse_mis_quotes(symbols)
        raise ValueError(self._provider_unavailable_reason())

    def _load_trading_calendar(self) -> _LoadedRows:
        payload = self._fetch_json(TWSE_HOLIDAY_URL, None)
        if not isinstance(payload, list):
            raise ValueError("TWSE holiday schedule returned a non-list payload")
        closed_dates = parse_twse_closed_dates(payload)
        if not closed_dates:
            raise ValueError("TWSE holiday schedule contained no closed dates")
        rows = [{"date": value.isoformat()} for value in sorted(closed_dates)]
        return _LoadedRows(
            rows,
            upstreams=(
                {
                    "id": "twse-holiday-schedule",
                    "status": "FRESH",
                    "row_count": len(rows),
                    "latest_event_at": rows[-1]["date"],
                },
            ),
        )

    def _load_twse_mis_quotes(self, symbols: list[str]) -> _LoadedRows:
        channels = ["tse_t00.tw", "otc_o00.tw"]
        for symbol in symbols:
            channels.extend((f"tse_{symbol}.tw", f"otc_{symbol}.tw"))
        query = urlencode(
            {
                "ex_ch": "|".join(channels),
                "json": "1",
                "delay": "0",
                "_": str(int(time.time() * 1000)),
            }
        )
        payload = self._fetch_json(
            f"{TWSE_MIS_URL}?{query}",
            {
                "Referer": "https://mis.twse.com.tw/stock/index.jsp",
                "User-Agent": "Mozilla/5.0 (Taiwan Equity Lens local dashboard)",
            },
        )
        if not isinstance(payload, dict) or payload.get("rtcode") != "0000":
            raise ValueError("TWSE MIS returned an unexpected response")
        raw_rows = payload.get("msgArray")
        if not isinstance(raw_rows, list):
            raise ValueError("TWSE MIS response is missing msgArray")
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            symbol = str(raw.get("c") or "").strip()
            exchange = str(raw.get("ex") or "").strip().upper()
            key = (exchange, symbol)
            if not symbol or key in seen:
                continue
            quote = _normalize_mis_quote(raw, now=self._now())
            if quote is None:
                continue
            rows.append(quote)
            seen.add(key)
        latest_event = _latest_row_datetime(rows, "source_event_time")
        fresh_rows = [
            row
            for row in rows
            if (
                str(row.get("status") or "") in {"LIVE", "EOD"}
                and _finite(row.get("price")) is not None
            )
        ]
        fresh_equities = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "equity"
        }
        fresh_indices = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "index"
        }
        attempt_ok = (
            set(symbols).issubset(fresh_equities)
            and {"t00", "o00"}.issubset(fresh_indices)
        )
        self._record_provider_attempt(
            attempt_ok,
            error=(
                ""
                if attempt_ok
                else "TWSE MIS response did not contain every required quote"
            ),
        )
        return _LoadedRows(
            rows,
            upstreams=(
                {
                    "id": "twse-mis",
                    "status": _quote_collection_status(
                        str(row.get("status") or "") for row in rows
                    ),
                    "row_count": len(rows),
                    "latest_event_at": latest_event.isoformat() if latest_event else "",
                },
            ),
        )

    def _load_fubon_quotes(self, symbols: list[str]) -> _LoadedRows:
        # Authenticate before consulting stale quote caches. Credential,
        # certificate, or entitlement failures must fail closed instead of
        # returning an old quote as if the broker session were still valid.
        authentication_generation = self._fubon_auth_generation_value()
        deadline = time.monotonic() + _FUBON_REQUEST_DEADLINE_SECONDS
        self._fubon_session_manager.session(
            timeout_seconds=max(0.01, deadline - time.monotonic())
        )
        rows, errors, upstreams = self._load_fubon_equity_snapshots(
            set(symbols),
            deadline=deadline,
        )
        benchmarks, benchmark_errors = self._discover_fubon_benchmarks(
            deadline=deadline,
        )
        errors.extend(benchmark_errors)
        for provider_symbol, benchmark_symbol in benchmarks:
            cache_key = f"fubon-index:{benchmark_symbol}:{provider_symbol}"
            try:
                quote, _, _ = self._fubon_cached(
                    cache_key,
                    4.0,
                    lambda provider_symbol=provider_symbol,
                    benchmark_symbol=benchmark_symbol: (
                        self._fetch_and_normalize_fubon_index(
                            provider_symbol,
                            benchmark_symbol=benchmark_symbol,
                            deadline=deadline,
                        )
                    ),
                )
            except (
                FubonAuthenticationError,
                FubonConfigurationError,
                FubonSDKUnavailableError,
                FubonSessionError,
                OSError,
                ValueError,
                TimeoutError,
            ) as exc:
                if self._is_fubon_auth_failure(exc):
                    raise
                errors.append(
                    f"Fubon {provider_symbol}: "
                    f"{self._safe_provider_error(exc, provider_mode='fubon')}"
                )
                stale = self._stale_cache(cache_key)
                stale_quote = (
                    dict(stale.payload)
                    if stale is not None and isinstance(stale.payload, dict)
                    else None
                )
                if stale_quote is not None:
                    stale_quote["status"] = "STALE"
                    rows.append(stale_quote)
                    upstreams.append(
                        {
                            "id": f"fubon:{provider_symbol}",
                            "status": "STALE",
                            "row_count": 1,
                            "latest_event_at": str(
                                stale_quote.get("source_event_time") or ""
                            ),
                        }
                    )
                else:
                    upstreams.append(
                        {
                            "id": f"fubon:{provider_symbol}",
                            "status": "UNAVAILABLE",
                            "row_count": 0,
                            "latest_event_at": "",
                        }
                    )
                continue
            if isinstance(quote, dict):
                rows.append(quote)
                upstreams.append(
                    {
                        "id": f"fubon:{provider_symbol}",
                        "status": str(
                            quote.get("status") or "UNAVAILABLE"
                        ),
                        "row_count": 1,
                        "latest_event_at": str(
                            quote.get("source_event_time") or ""
                        ),
                    }
                )

        expected_any_rows = bool(symbols or benchmarks)
        if expected_any_rows and not rows:
            detail = errors[0] if errors else "no requested symbols"
            self._record_provider_attempt(False, error=detail)
            raise ValueError(
                f"Fubon returned no usable quotes ({detail})"
            )

        fresh_rows = [
            row
            for row in rows
            if (
                str(row.get("status") or "") in {"LIVE", "EOD"}
                and _finite(row.get("price")) is not None
            )
        ]
        fresh_equities = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "equity"
        }
        fresh_indices = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "index"
        }
        attempt_ok = (
            not errors
            and set(symbols).issubset(fresh_equities)
            and {"t00", "o00"}.issubset(fresh_indices)
        )
        self._record_provider_attempt(
            attempt_ok,
            error=(
                errors[0]
                if errors
                else (
                    ""
                    if attempt_ok
                    else "Fubon response did not contain every required quote"
                )
            ),
        )
        self._complete_fubon_authenticated_load(authentication_generation)
        return _LoadedRows(rows, tuple(errors), tuple(upstreams))

    def _load_fubon_full_market_quotes(self) -> _LoadedRows:
        authentication_generation = self._fubon_auth_generation_value()
        deadline = time.monotonic() + _FUBON_REQUEST_DEADLINE_SECONDS
        self._fubon_session_manager.session(
            timeout_seconds=max(0.01, deadline - time.monotonic())
        )
        rows, errors, upstreams = self._load_fubon_equity_snapshots(
            None,
            deadline=deadline,
        )
        if not rows and errors:
            raise ValueError(errors[0])
        self._complete_fubon_authenticated_load(authentication_generation)
        upstream_statuses = {
            str(upstream.get("id") or ""): str(
                upstream.get("status") or "UNAVAILABLE"
            )
            for upstream in upstreams
        }
        attempt_ok = (
            not errors
            and bool(rows)
            and upstream_statuses.get("fubon-snapshot:TSE")
            in {"LIVE", "EOD"}
            and upstream_statuses.get("fubon-snapshot:OTC")
            in {"LIVE", "EOD"}
        )
        self._record_provider_attempt(
            attempt_ok,
            error=(
                ""
                if attempt_ok
                else (
                    errors[0]
                    if errors
                    else "Fubon full-market snapshot was incomplete"
                )
            ),
        )
        return _LoadedRows(rows, tuple(errors), tuple(upstreams))

    def _load_fubon_equity_snapshots(
        self,
        symbols: set[str] | None,
        *,
        deadline: float,
    ) -> tuple[
        list[dict[str, Any]],
        list[str],
        list[dict[str, Any]],
    ]:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        upstreams: list[dict[str, Any]] = []
        for market, normalized_market in (
            ("TSE", "TWSE"),
            ("OTC", "TPEX"),
        ):
            cache_key = f"fubon-snapshot:{market}"
            try:
                market_rows, _, _ = self._fubon_cached(
                    cache_key,
                    4.0,
                    lambda market=market,
                    normalized_market=normalized_market: (
                        self._fetch_and_normalize_fubon_snapshot(
                            market,
                            normalized_market=normalized_market,
                            deadline=deadline,
                        )
                    ),
                )
            except (
                FubonAuthenticationError,
                FubonConfigurationError,
                FubonSDKUnavailableError,
                FubonSessionError,
                OSError,
                ValueError,
                TimeoutError,
            ) as exc:
                if self._is_fubon_auth_failure(exc):
                    raise
                safe_error = self._safe_provider_error(
                    exc,
                    provider_mode="fubon",
                )
                errors.append(f"Fubon {market} snapshot: {safe_error}")
                stale = self._stale_cache(cache_key)
                stale_rows = (
                    [dict(row) for row in stale.payload if isinstance(row, dict)]
                    if stale is not None and isinstance(stale.payload, list)
                    else []
                )
                for row in stale_rows:
                    row["status"] = "STALE"
                selected_stale = (
                    stale_rows
                    if symbols is None
                    else [
                        row
                        for row in stale_rows
                        if str(row.get("symbol") or "") in symbols
                    ]
                )
                rows.extend(selected_stale)
                upstreams.append(
                    {
                        "id": f"fubon-snapshot:{market}",
                        "status": "STALE" if selected_stale else "UNAVAILABLE",
                        "row_count": len(selected_stale),
                        "latest_event_at": _latest_source_event(selected_stale),
                    }
                )
                continue
            normalized_rows = [
                dict(row)
                for row in market_rows
                if isinstance(row, dict)
            ]
            selected = (
                normalized_rows
                if symbols is None
                else [
                    row
                    for row in normalized_rows
                    if str(row.get("symbol") or "") in symbols
                ]
            )
            rows.extend(selected)
            upstreams.append(
                {
                    "id": f"fubon-snapshot:{market}",
                    "status": _quote_collection_status(
                        row.get("status") for row in normalized_rows
                    ),
                    "row_count": len(normalized_rows),
                    "returned_row_count": len(selected),
                    "latest_event_at": _latest_source_event(
                        normalized_rows
                    ),
                }
            )
        return rows, errors, upstreams

    def _fetch_and_normalize_fubon_snapshot(
        self,
        market: str,
        *,
        normalized_market: str,
        deadline: float,
    ) -> list[dict[str, Any]]:
        payload = self._fubon_json(
            FUBON_SNAPSHOT_PATH.format(market=market),
            {},
            deadline=deadline,
        )
        return _normalize_fubon_snapshot(
            payload,
            requested_market=market,
            normalized_market=normalized_market,
            now=self._now(),
        )

    def _discover_fubon_benchmarks(
        self,
        *,
        deadline: float,
    ) -> tuple[list[tuple[str, str]], list[str]]:
        requests: list[tuple[str, str]] = []
        errors: list[str] = []
        configurations = (
            ("TWSE", "t00", os.getenv("FUBON_TAIEX_SYMBOL", "").strip()),
            ("TPEx", "o00", os.getenv("FUBON_TPEX_SYMBOL", "").strip()),
        )
        for exchange, benchmark_symbol, configured_symbol in configurations:
            if configured_symbol:
                if not _SYMBOL_RE.fullmatch(configured_symbol):
                    errors.append(
                        f"Fubon {exchange} benchmark: configured symbol is invalid"
                    )
                    continue
                requests.append((configured_symbol, benchmark_symbol))
                continue
            cache_key = f"fubon-index-list:{exchange}"
            try:
                payload, _, _ = self._fubon_cached(
                    cache_key,
                    3600.0,
                    lambda exchange=exchange: self._fubon_json(
                        FUBON_TICKERS_PATH,
                        {"type": "INDEX", "exchange": exchange},
                        deadline=deadline,
                    ),
                )
                symbol = _select_fugle_benchmark_symbol(
                    payload,
                    benchmark_symbol=benchmark_symbol,
                )
                if not symbol or not _SYMBOL_RE.fullmatch(symbol):
                    raise ValueError(
                        f"no valid {benchmark_symbol} benchmark in "
                        f"{exchange} index list"
                    )
                requests.append((symbol, benchmark_symbol))
            except (
                FubonAuthenticationError,
                FubonConfigurationError,
                FubonSDKUnavailableError,
                FubonSessionError,
                OSError,
                ValueError,
                TimeoutError,
            ) as exc:
                if self._is_fubon_auth_failure(exc):
                    raise
                errors.append(
                    f"Fubon {exchange} benchmark: "
                    f"{self._safe_provider_error(exc, provider_mode='fubon')}"
                )
                stale = self._stale_cache(cache_key)
                symbol = (
                    _select_fugle_benchmark_symbol(
                        stale.payload,
                        benchmark_symbol=benchmark_symbol,
                    )
                    if stale is not None
                    else ""
                )
                if symbol and _SYMBOL_RE.fullmatch(symbol):
                    requests.append((symbol, benchmark_symbol))
        return requests, errors

    def _fetch_and_normalize_fubon_index(
        self,
        symbol: str,
        *,
        benchmark_symbol: str,
        deadline: float,
    ) -> dict[str, Any]:
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("Fubon benchmark symbol is invalid")
        encoded_symbol = quote_path_segment(symbol, safe="")
        payload = self._fubon_json(
            FUBON_QUOTE_PATH.format(symbol=encoded_symbol),
            {},
            deadline=deadline,
        )
        if not isinstance(payload, dict):
            raise ValueError(
                f"Fubon quote {symbol} returned an unexpected payload"
            )
        returned_symbol = str(payload.get("symbol") or "").strip()
        if returned_symbol != symbol:
            raise ValueError(
                f"Fubon quote symbol mismatch: requested {symbol}, "
                f"received {returned_symbol or 'missing'}"
            )
        payload_type = str(payload.get("type") or "").strip().upper()
        payload_exchange = str(
            payload.get("exchange") or payload.get("market") or ""
        ).strip().upper()
        expected_exchanges = (
            {"TWSE", "TSE"}
            if benchmark_symbol == "t00"
            else {"TPEX", "OTC"}
        )
        if payload_type != "INDEX":
            raise ValueError(
                f"Fubon benchmark {benchmark_symbol} returned "
                f"type {payload_type or 'missing'} instead of INDEX"
            )
        if payload_exchange not in expected_exchanges:
            raise ValueError(
                f"Fubon benchmark {benchmark_symbol} returned "
                f"exchange {payload_exchange or 'missing'}"
            )
        if not str(payload.get("name") or "").strip():
            raise ValueError(f"Fubon quote {symbol} is missing name")
        if _iso_date(payload.get("date")) is None:
            raise ValueError(
                f"Fubon quote {symbol} is missing a valid date"
            )
        if _epoch_microseconds(payload.get("lastUpdated")) is None:
            raise ValueError(
                f"Fubon quote {symbol} is missing a valid lastUpdated"
            )
        quote = _normalize_fugle_quote(
            payload,
            now=self._now(),
            benchmark_symbol=benchmark_symbol,
            source="Fubon Neo MarketData",
        )
        if quote is None:
            raise ValueError(
                f"Fubon quote {symbol} is missing required fields"
            )
        return quote

    def _fubon_json(
        self,
        path: str,
        params: dict[str, str],
        *,
        deadline: float,
    ) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _FubonAdmissionError("Fubon request deadline reached")
        session = self._fubon_session_manager.session(
            timeout_seconds=remaining
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _FubonAdmissionError("Fubon request deadline reached")
        query = urlencode(params)
        url = f"{session.base_url}/{path}"
        if query:
            url = f"{url}?{query}"
        headers = {"X-SDK-TOKEN": session.sdk_token}
        try:
            return self._fubon_gate.call(
                lambda: self._fetch_fubon_json(
                    url,
                    headers,
                    deadline=deadline,
                ),
                deadline=deadline,
            )
        except HTTPError as exc:
            if int(exc.code) in {401, 403}:
                self._invalidate_fubon_authentication(int(exc.code))
            raise

    def _invalidate_fubon_authentication(self, status_code: int) -> None:
        with self._cache_lock:
            self._fubon_auth_blocked = True
            self._fubon_auth_invalidation_in_progress = True
            self._fubon_auth_generation += 1
            self._purge_fubon_quote_caches_locked()
            self._fubon_negative_cache.clear()
        self._detach_fubon_stream()
        try:
            self._fubon_session_manager.invalidate(
                authentication_failure=True
            )
        finally:
            with self._cache_lock:
                self._fubon_auth_generation += 1
                self._fubon_auth_invalidation_in_progress = False
                self._purge_fubon_quote_caches_locked()
                self._fubon_negative_cache.clear()
        safe_error = self._safe_provider_error(
            HTTPError(
                FUBON_STOCK_BASE_URL,
                int(status_code),
                "Fubon authentication rejected",
                {},
                None,
            ),
            provider_mode="fubon",
        )
        self._record_provider_attempt(False, error=safe_error)

    def _fubon_auth_generation_value(self) -> int:
        with self._cache_lock:
            return self._fubon_auth_generation

    def _ensure_fubon_auth_generation(self, expected: int) -> None:
        with self._cache_lock:
            if (
                self._fubon_auth_generation == expected
                and not self._fubon_auth_blocked
                and not self._fubon_auth_invalidation_in_progress
            ):
                return
            self._purge_fubon_quote_caches_locked()
        raise FubonAuthenticationError(
            "Fubon authentication changed while loading market data"
        )

    def _complete_fubon_authenticated_load(self, expected: int) -> None:
        with self._cache_lock:
            if (
                self._fubon_auth_generation != expected
                or self._fubon_auth_invalidation_in_progress
            ):
                self._purge_fubon_quote_caches_locked()
                failed = True
            else:
                self._fubon_auth_blocked = False
                failed = False
        if failed:
            raise FubonAuthenticationError(
                "Fubon authentication changed while loading market data"
            )

    def _purge_fubon_quote_caches_locked(self) -> None:
        for cache_key in tuple(self._cache):
            if (
                cache_key == "fubon-full-market"
                or cache_key.startswith("fubon-")
                or cache_key.startswith("quotes:")
            ):
                self._cache.pop(cache_key, None)

    def _purge_snapshot_component_caches_locked(self) -> None:
        exact_keys = {"alerts", "fund-flow", "news", "trading-calendar"}
        prefixes = (
            "fubon-",
            "fugle-benchmark",
            "fugle-symbol:",
            "quotes:",
        )
        for cache_key in tuple(self._cache):
            if cache_key in exact_keys or cache_key.startswith(prefixes):
                self._cache.pop(cache_key, None)

    def _fetch_fubon_json(
        self,
        url: str,
        headers: dict[str, str],
        *,
        deadline: float,
    ) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _FubonAdmissionError("Fubon request deadline reached")
        if self._fetch_json_supports_timeout:
            return self._fetch_json(
                url,
                headers,
                timeout_seconds=min(8.0, remaining),
                allow_redirects=False,
                compatibility_tls=False,
            )
        return self._fetch_json(url, headers)

    def _fubon_cached(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Any],
    ) -> tuple[Any, datetime, bool]:
        def guarded_loader() -> Any:
            self._raise_for_negative_fubon_cache(key)
            try:
                payload = loader()
            except (_NegativeFubonCacheHit, _FubonAdmissionError):
                raise
            except HTTPError as exc:
                if int(exc.code) in {401, 403}:
                    self._clear_negative_fubon_cache(key)
                else:
                    self._record_negative_fubon_cache(
                        key,
                        seconds=(
                            _FUBON_RATE_LIMIT_CACHE_SECONDS
                            if int(exc.code) == 429
                            else _FUBON_NEGATIVE_CACHE_SECONDS
                        ),
                    )
                raise
            except (
                FubonAuthenticationError,
                FubonConfigurationError,
                FubonSDKUnavailableError,
                FubonSessionError,
                OSError,
                ValueError,
                TimeoutError,
            ):
                self._record_negative_fubon_cache(
                    key,
                    seconds=_FUBON_NEGATIVE_CACHE_SECONDS,
                )
                raise
            self._clear_negative_fubon_cache(key)
            return payload

        return self._cached(key, ttl_seconds, guarded_loader)

    def _raise_for_negative_fubon_cache(self, key: str) -> None:
        now = time.monotonic()
        with self._cache_lock:
            expires_at = self._fubon_negative_cache.get(key, 0.0)
            if expires_at <= now:
                self._fubon_negative_cache.pop(key, None)
                return
            retry_after = max(1, math.ceil(expires_at - now))
        raise _NegativeFubonCacheHit(
            "temporarily cooling down after a Fubon upstream failure "
            f"(retry in about {retry_after}s)"
        )

    def _record_negative_fubon_cache(
        self,
        key: str,
        *,
        seconds: float,
    ) -> None:
        with self._cache_lock:
            self._fubon_negative_cache[key] = (
                time.monotonic() + max(1.0, float(seconds))
            )
            if len(self._fubon_negative_cache) > _MAX_CACHE_ENTRIES:
                victim = min(
                    self._fubon_negative_cache,
                    key=self._fubon_negative_cache.get,
                )
                self._fubon_negative_cache.pop(victim, None)

    def _clear_negative_fubon_cache(self, key: str) -> None:
        with self._cache_lock:
            self._fubon_negative_cache.pop(key, None)

    @staticmethod
    def _is_fubon_auth_failure(exc: BaseException) -> bool:
        return isinstance(
            exc,
            (
                FubonAuthenticationError,
                FubonConfigurationError,
                FubonSDKUnavailableError,
                FubonSessionError,
            ),
        ) or (isinstance(exc, HTTPError) and int(exc.code) in {401, 403})

    def _load_fugle_quotes(self, symbols: list[str]) -> _LoadedRows:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        upstreams: list[dict[str, Any]] = []
        headers = {"X-API-KEY": self._fugle_api_key}
        deadline = time.monotonic() + _FUGLE_REQUEST_DEADLINE_SECONDS
        benchmarks, benchmark_errors = self._discover_fugle_benchmarks(
            headers,
            deadline=deadline,
        )
        # Protect the market headline under a bounded request deadline: fetch
        # both benchmarks before the watchlist so a slow large watchlist cannot
        # consume the entire budget and leave the regime without indices.
        requests = [*benchmarks, *((symbol, "") for symbol in symbols)]
        errors.extend(benchmark_errors)
        seen_requests: set[tuple[str, str]] = set()
        for symbol, benchmark_symbol in requests:
            request_key = (symbol, benchmark_symbol)
            if request_key in seen_requests:
                continue
            seen_requests.add(request_key)
            cache_key = f"fugle-symbol:{benchmark_symbol or 'equity'}:{symbol}"
            try:
                quote, _, _ = self._fugle_cached(
                    cache_key,
                    4.0,
                    lambda symbol=symbol: self._fetch_and_normalize_fugle_quote(
                        symbol,
                        headers,
                        deadline=deadline,
                        benchmark_symbol=benchmark_symbol,
                    ),
                )
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(
                    f"Fugle {symbol}: {self._safe_provider_error(exc)}"
                )
                stale = self._stale_cache(cache_key)
                stale_quote = dict(stale.payload) if stale and isinstance(stale.payload, dict) else None
                if stale_quote is not None:
                    stale_quote["status"] = "STALE"
                    rows.append(stale_quote)
                    upstreams.append(
                        {
                            "id": f"fugle:{symbol}",
                            "status": "STALE",
                            "row_count": 1,
                            "latest_event_at": str(
                                stale_quote.get("source_event_time") or ""
                            ),
                        }
                    )
                    continue
                upstreams.append(
                    {
                        "id": f"fugle:{symbol}",
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                        "latest_event_at": "",
                    }
                )
                continue
            if isinstance(quote, dict):
                rows.append(quote)
                upstreams.append(
                    {
                        "id": f"fugle:{symbol}",
                        "status": str(quote.get("status") or "UNAVAILABLE"),
                        "row_count": 1,
                        "latest_event_at": str(quote.get("source_event_time") or ""),
                    }
                )
        if requests and not rows:
            detail = errors[0] if errors else "no requested symbols"
            self._record_provider_attempt(False, error=detail)
            raise ValueError(f"Fugle returned no usable quotes ({detail})")
        fresh_rows = [
            row
            for row in rows
            if (
                str(row.get("status") or "") in {"LIVE", "EOD"}
                and _finite(row.get("price")) is not None
            )
        ]
        fresh_equities = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "equity"
        }
        fresh_indices = {
            str(row.get("symbol") or "")
            for row in fresh_rows
            if row.get("kind") == "index"
        }
        attempt_ok = (
            not errors
            and set(symbols).issubset(fresh_equities)
            and {"t00", "o00"}.issubset(fresh_indices)
        )
        self._record_provider_attempt(
            attempt_ok,
            error=(
                errors[0]
                if errors
                else (
                    ""
                    if attempt_ok
                    else "Fugle response did not contain every required quote"
                )
            ),
        )
        return _LoadedRows(rows, tuple(errors), tuple(upstreams))

    def _discover_fugle_benchmarks(
        self,
        headers: dict[str, str],
        *,
        deadline: float,
    ) -> tuple[list[tuple[str, str]], list[str]]:
        requests: list[tuple[str, str]] = []
        errors: list[str] = []
        configurations = (
            ("TWSE", "t00", os.getenv("FUGLE_TAIEX_SYMBOL", "").strip()),
            ("TPEx", "o00", os.getenv("FUGLE_TPEX_SYMBOL", "").strip()),
        )
        for exchange, benchmark_symbol, configured_symbol in configurations:
            if configured_symbol:
                requests.append((configured_symbol, benchmark_symbol))
                continue
            query = urlencode({"type": "INDEX", "exchange": exchange})
            cache_key = f"fugle-index-list:{exchange}"
            try:
                payload, _, _ = self._fugle_cached(
                    cache_key,
                    3600.0,
                    lambda query=query: self._fugle_json(
                        f"{FUGLE_TICKERS_URL}?{query}",
                        headers,
                        deadline=deadline,
                    ),
                )
                symbol = _select_fugle_benchmark_symbol(
                    payload,
                    benchmark_symbol=benchmark_symbol,
                )
                if not symbol:
                    raise ValueError(f"no {benchmark_symbol} benchmark in {exchange} index list")
                requests.append((symbol, benchmark_symbol))
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(
                    "Fugle "
                    f"{exchange} benchmark: {self._safe_provider_error(exc)}"
                )
                stale = self._stale_cache(cache_key)
                symbol = (
                    _select_fugle_benchmark_symbol(
                        stale.payload,
                        benchmark_symbol=benchmark_symbol,
                    )
                    if stale is not None
                    else ""
                )
                if symbol:
                    requests.append((symbol, benchmark_symbol))
        return requests, errors

    def _fetch_and_normalize_fugle_quote(
        self,
        symbol: str,
        headers: dict[str, str],
        *,
        deadline: float,
        benchmark_symbol: str = "",
    ) -> dict[str, Any]:
        payload = self._fugle_json(
            FUGLE_QUOTE_URL.format(symbol=symbol),
            headers,
            deadline=deadline,
        )
        if not isinstance(payload, dict):
            raise ValueError(f"Fugle quote {symbol} returned an unexpected payload")
        returned_symbol = str(payload.get("symbol") or "").strip()
        if returned_symbol != symbol:
            raise ValueError(
                f"Fugle quote symbol mismatch: requested {symbol}, "
                f"received {returned_symbol or 'missing'}"
            )
        payload_type = str(payload.get("type") or "").strip().upper()
        payload_exchange = str(
            payload.get("exchange") or payload.get("market") or ""
        ).strip().upper()
        if not str(payload.get("name") or "").strip():
            raise ValueError(f"Fugle quote {symbol} is missing name")
        if _iso_date(payload.get("date")) is None:
            raise ValueError(f"Fugle quote {symbol} is missing a valid date")
        if _epoch_microseconds(payload.get("lastUpdated")) is None:
            raise ValueError(
                f"Fugle quote {symbol} is missing a valid lastUpdated"
            )
        if _first_finite(
            payload.get("lastPrice"),
            payload.get("closePrice"),
        ) is None:
            raise ValueError(f"Fugle quote {symbol} is missing a usable price")
        if _first_finite(
            payload.get("previousClose"),
            payload.get("referencePrice"),
        ) is None:
            raise ValueError(
                f"Fugle quote {symbol} is missing a usable reference price"
            )
        if benchmark_symbol:
            expected_exchanges = (
                {"TWSE", "TSE"}
                if benchmark_symbol == "t00"
                else {"TPEX", "OTC"}
            )
            if payload_type != "INDEX":
                raise ValueError(
                    f"Fugle benchmark {benchmark_symbol} returned "
                    f"type {payload_type or 'missing'} instead of INDEX"
                )
            if payload_exchange not in expected_exchanges:
                raise ValueError(
                    f"Fugle benchmark {benchmark_symbol} returned "
                    f"exchange {payload_exchange or 'missing'}"
                )
        elif payload_type == "INDEX":
            raise ValueError(
                f"Fugle equity quote {symbol} unexpectedly returned INDEX"
            )
        elif payload_type != "EQUITY":
            raise ValueError(
                f"Fugle equity quote {symbol} returned "
                f"type {payload_type or 'missing'}"
            )
        elif payload_exchange not in {"TWSE", "TSE", "TPEX", "OTC"}:
            raise ValueError(
                f"Fugle equity quote {symbol} returned "
                f"exchange {payload_exchange or 'missing'}"
            )
        quote = _normalize_fugle_quote(
            payload,
            now=self._now(),
            benchmark_symbol=benchmark_symbol,
        )
        if quote is None:
            raise ValueError(f"Fugle quote {symbol} is missing required fields")
        return quote

    def _fugle_json(
        self,
        url: str,
        headers: dict[str, str],
        *,
        deadline: float,
    ) -> Any:
        return self._fugle_gate.call(
            lambda: self._fetch_fugle_json(url, headers, deadline=deadline),
            deadline=deadline,
        )

    def _fetch_fugle_json(
        self,
        url: str,
        headers: dict[str, str],
        *,
        deadline: float,
    ) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _FugleAdmissionError("Fugle request deadline reached")
        if self._fetch_json_supports_timeout:
            return self._fetch_json(
                url,
                headers,
                timeout_seconds=min(8.0, remaining),
                allow_redirects=False,
                compatibility_tls=False,
            )
        return self._fetch_json(url, headers)

    def _fugle_cached(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Any],
    ) -> tuple[Any, datetime, bool]:
        def guarded_loader() -> Any:
            # This check deliberately runs under _cached's per-key loader lock.
            # Concurrent callers therefore observe the first failure's negative
            # cache entry instead of each issuing the same upstream request.
            self._raise_for_negative_fugle_cache(key)
            try:
                payload = loader()
            except (_NegativeFugleCacheHit, _FugleAdmissionError):
                raise
            except (OSError, ValueError, TimeoutError):
                self._record_negative_fugle_cache(key)
                raise
            self._clear_negative_fugle_cache(key)
            return payload

        return self._cached(key, ttl_seconds, guarded_loader)

    def _raise_for_negative_fugle_cache(self, key: str) -> None:
        now = time.monotonic()
        with self._cache_lock:
            expires_at = self._fugle_negative_cache.get(key, 0.0)
            if expires_at <= now:
                self._fugle_negative_cache.pop(key, None)
                return
        raise _NegativeFugleCacheHit(
            "temporarily negative-cached after an upstream failure"
        )

    def _record_negative_fugle_cache(self, key: str) -> None:
        with self._cache_lock:
            self._fugle_negative_cache[key] = (
                time.monotonic() + _FUGLE_NEGATIVE_CACHE_SECONDS
            )
            if len(self._fugle_negative_cache) > _MAX_CACHE_ENTRIES:
                victim = min(
                    self._fugle_negative_cache,
                    key=self._fugle_negative_cache.get,
                )
                self._fugle_negative_cache.pop(victim, None)

    def _clear_negative_fugle_cache(self, key: str) -> None:
        with self._cache_lock:
            self._fugle_negative_cache.pop(key, None)

    def _load_news(self) -> _LoadedRows:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        upstreams: list[dict[str, Any]] = []
        now = self._now()

        def normalize_twse_news(item: dict[str, Any]) -> dict[str, Any] | None:
            title = str(item.get("Title") or "").strip()
            published = _roc_datetime(item.get("Date"))
            url = safe_http_url(item.get("Url"))
            if not title or published is None or not url:
                return None
            return {
                "published_at": published.isoformat(),
                "title": title,
                "summary": "",
                "url": url,
                "source": "TWSE 交易所新聞",
                "kind": "exchange_news",
                "symbol": "",
            }

        sources: tuple[
            tuple[str, str, Callable[[dict[str, Any]], dict[str, Any] | None]],
            ...,
        ] = (
            ("twse-news", TWSE_NEWS_URL, normalize_twse_news),
            (
                "twse-material",
                TWSE_MATERIAL_URL,
                lambda item: _normalize_material_announcement(
                    item,
                    market="TWSE",
                    source_url=TWSE_MATERIAL_URL,
                ),
            ),
            (
                "tpex-material",
                TPEX_MATERIAL_URL,
                lambda item: _normalize_material_announcement(
                    item,
                    market="TPEx",
                    source_url=TPEX_MATERIAL_URL,
                ),
            ),
        )
        for source_id, endpoint, normalizer in sources:
            source_rows: list[dict[str, Any]] = []
            try:
                payload = self._fetch_json(endpoint, None)
                if not isinstance(payload, list):
                    raise ValueError("upstream returned a non-list news payload")
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(f"{source_id}: {exc}")
                upstreams.append(
                    {
                        "id": source_id,
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                        "latest_event_at": "",
                    }
                )
                continue
            rejected_rows = 0
            for item in payload:
                if not isinstance(item, dict):
                    rejected_rows += 1
                    continue
                normalized = normalizer(item)
                if normalized is None:
                    rejected_rows += 1
                    continue
                published = _iso_datetime(normalized.get("published_at"))
                if published is not None and published > now + timedelta(minutes=5):
                    errors.append(
                        f"{source_id}: discarded future event {published.isoformat()}"
                    )
                    rejected_rows += 1
                    continue
                source_rows.append(normalized)
            if rejected_rows:
                errors.append(
                    f"{source_id}: rejected {rejected_rows} of {len(payload)} rows"
                )
            rows.extend(source_rows)
            latest_event = _latest_row_datetime(source_rows, "published_at")
            upstreams.append(
                {
                    "id": source_id,
                    "status": (
                        "PARTIAL"
                        if source_rows and rejected_rows
                        else (
                            "UNAVAILABLE"
                            if rejected_rows
                            else _event_rows_status(
                                source_rows,
                                now=now,
                                key="published_at",
                                max_age=timedelta(hours=72),
                            )
                        )
                    ),
                    "row_count": len(source_rows),
                    "latest_event_at": latest_event.isoformat() if latest_event else "",
                }
            )
        rows.sort(key=lambda row: str(row.get("published_at") or ""), reverse=True)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (
                str(row.get("published_at") or ""),
                str(row.get("symbol") or ""),
                str(row.get("title") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return _LoadedRows(deduped, tuple(errors), tuple(upstreams))

    def _load_alerts(self) -> _LoadedRows:
        now = self._now()
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        upstreams: list[dict[str, Any]] = []
        sources = (
            ("TWSE", "disposition", TWSE_DISPOSITION_URL),
            ("TWSE", "notice", TWSE_NOTICE_URL),
            ("TPEx", "disposition", TPEX_DISPOSITION_URL),
            ("TPEx", "notice", TPEX_WARNING_URL),
        )
        for market, alert_type, endpoint in sources:
            source_id = f"{market.lower()}-{alert_type}"
            source_rows: list[dict[str, Any]] = []
            try:
                payload = self._fetch_json(endpoint, None)
                if not isinstance(payload, list):
                    raise ValueError("upstream returned a non-list alert payload")
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(f"{source_id}: {exc}")
                upstreams.append(
                    {
                        "id": source_id,
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                        "latest_event_at": "",
                    }
                )
                continue
            rejected_rows = 0
            for item in payload:
                if _is_empty_twse_notice_sentinel(
                    item,
                    market=market,
                    alert_type=alert_type,
                ):
                    continue
                normalized = _normalize_alert(
                    item,
                    market=market,
                    alert_type=alert_type,
                    source_url=endpoint,
                    today=now.date(),
                )
                if normalized is None:
                    rejected_rows += 1
                    continue
                published = _iso_date(normalized.get("published_date"))
                if published is not None and published > now.date():
                    errors.append(
                        f"{source_id}: discarded future event {published.isoformat()}"
                    )
                    rejected_rows += 1
                    continue
                source_rows.append(normalized)
            if rejected_rows:
                errors.append(
                    f"{source_id}: rejected {rejected_rows} of {len(payload)} rows"
                )
            rows.extend(source_rows)
            latest_date = max(
                (
                    str(row.get("published_date") or "")
                    for row in source_rows
                    if str(row.get("published_date") or "")
                ),
                default="",
            )
            upstreams.append(
                {
                    "id": source_id,
                    # A successfully parsed official alert list is authoritative
                    # even when it contains no event published today. Event dates
                    # describe the records, not whether the source request worked.
                    "status": (
                        "PARTIAL"
                        if source_rows and rejected_rows
                        else ("UNAVAILABLE" if rejected_rows else "FRESH")
                    ),
                    "row_count": len(source_rows),
                    "latest_event_at": latest_date,
                }
            )
        rows.sort(
            key=lambda row: (
                bool(row.get("active")),
                str(row.get("published_date") or ""),
                str(row.get("symbol") or ""),
            ),
            reverse=True,
        )
        return _LoadedRows(rows, tuple(errors), tuple(upstreams))

    def _load_fund_flow(self) -> _LoadedRows:
        now = self._now()
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        upstreams: list[dict[str, Any]] = []
        sources: tuple[tuple[str, Callable[[], list[dict[str, Any]]]], ...] = (
            (
                "twse-t86",
                lambda: fetch_twse_fund_flow(as_of=now.date(), lookback_days=45),
            ),
            ("tpex-3insti", fetch_tpex_fund_flow),
        )
        for source_id, loader in sources:
            try:
                source_rows = loader()
                if not isinstance(source_rows, list):
                    raise ValueError("upstream returned a non-list fund-flow payload")
            except (OSError, ValueError, TimeoutError) as exc:
                errors.append(f"{source_id}: {exc}")
                upstreams.append(
                    {
                        "id": source_id,
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                        "latest_event_at": "",
                    }
                )
                continue
            rows.extend(source_rows)
            latest_date = max(
                (
                    str(row.get("date") or "")
                    for row in source_rows
                    if isinstance(row, dict) and str(row.get("date") or "")
                ),
                default="",
            )
            upstreams.append(
                {
                    "id": source_id,
                    "status": _dated_market_rows_status(
                        source_rows,
                        now=now,
                        key="date",
                    ),
                    "row_count": len(source_rows),
                    "latest_event_at": latest_date,
                }
            )
        return _LoadedRows(rows, tuple(errors), tuple(upstreams))

    def _safe_component(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Any],
        errors: list[str],
        *,
        wait_for_loader: bool = True,
    ) -> dict[str, Any]:
        fubon_quote_component = (
            key == "fubon-full-market"
            or (
                key.startswith("quotes:")
                and self._quote_provider_mode() == "fubon"
            )
        )
        authentication_generation = (
            self._fubon_auth_generation_value()
            if fubon_quote_component
            else -1
        )
        try:
            raw_value, fetched_at, cached = self._cached(
                key,
                ttl_seconds,
                loader,
                wait_for_loader=wait_for_loader,
            )
            if fubon_quote_component:
                self._ensure_fubon_auth_generation(
                    authentication_generation
                )
            value, partial_errors, upstreams = _unpack_loaded_rows(raw_value)
            errors.extend(f"{key}: {message}" for message in partial_errors)
            status = (
                _upstream_component_status(upstreams)
                if upstreams
                else _payload_status(value, fetched_at=fetched_at, now=self._now())
            )
            return {
                "payload": value,
                "fetched_at": fetched_at,
                "cached": cached,
                "fallback": False,
                "status": status,
                "upstreams": upstreams,
            }
        except HTTPError as exc:
            if (
                fubon_quote_component
                and self._is_fubon_auth_failure(exc)
            ):
                safe_error = self._safe_provider_error(
                    exc,
                    provider_mode="fubon",
                )
                self._record_provider_attempt(False, error=safe_error)
                errors.append(f"{key}: {safe_error}")
                return {
                    "payload": [],
                    "fetched_at": self._now(),
                    "cached": False,
                    "fallback": False,
                    "status": "UNAVAILABLE",
                    "upstreams": [],
                }
            errors.append(f"{key}: {exc}")
            fallback = self._stale_cache(key)
            if fallback is not None:
                value, _, upstreams = _unpack_loaded_rows(fallback.payload)
                return {
                    "payload": value,
                    "fetched_at": fallback.fetched_at,
                    "cached": True,
                    "fallback": True,
                    "status": "STALE",
                    "upstreams": upstreams,
                }
            return {
                "payload": [],
                "fetched_at": self._now(),
                "cached": False,
                "fallback": False,
                "status": "UNAVAILABLE",
                "upstreams": [],
            }
        except (
            FubonAuthenticationError,
            FubonConfigurationError,
            FubonSDKUnavailableError,
            FubonSessionError,
        ) as exc:
            safe_error = self._safe_provider_error(
                exc,
                provider_mode="fubon",
            )
            self._record_provider_attempt(False, error=safe_error)
            errors.append(f"{key}: {safe_error}")
            return {
                "payload": [],
                "fetched_at": self._now(),
                "cached": False,
                "fallback": False,
                "status": "UNAVAILABLE",
                "upstreams": [],
            }
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append(f"{key}: {exc}")
            fallback = self._stale_cache(key)
            if fallback is not None:
                value, _, upstreams = _unpack_loaded_rows(fallback.payload)
                return {
                    "payload": value,
                    "fetched_at": fallback.fetched_at,
                    "cached": True,
                    "fallback": True,
                    "status": "STALE",
                    "upstreams": upstreams,
                }
            return {
                "payload": [],
                "fetched_at": self._now(),
                "cached": False,
                "fallback": False,
                "status": "UNAVAILABLE",
                "upstreams": [],
            }

    def _cached(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Any],
        *,
        wait_for_loader: bool = True,
    ) -> tuple[Any, datetime, bool]:
        now_monotonic = time.monotonic()
        with self._cache_lock:
            current = self._cache.get(key)
            if current is not None and current.expires_at > now_monotonic:
                return current.payload, current.fetched_at, True
            loader_lock = self._loader_locks.setdefault(key, threading.Lock())
        acquired = loader_lock.acquire(blocking=wait_for_loader)
        if not acquired:
            raise TimeoutError(f"{key} refresh is already in progress")
        try:
            now_monotonic = time.monotonic()
            with self._cache_lock:
                current = self._cache.get(key)
                if current is not None and current.expires_at > now_monotonic:
                    return current.payload, current.fetched_at, True
            try:
                payload = loader()
            except Exception:
                with self._cache_lock:
                    if self._loader_locks.get(key) is loader_lock:
                        self._loader_locks.pop(key, None)
                raise
            fetched_at = self._now()
            completed_monotonic = time.monotonic()
            entry = _CacheValue(
                payload,
                fetched_at,
                completed_monotonic + max(0.0, ttl_seconds),
            )
            with self._cache_lock:
                self._cache[key] = entry
                if self._loader_locks.get(key) is loader_lock:
                    self._loader_locks.pop(key, None)
                self._prune_cache_locked(protected_key=key)
            return payload, fetched_at, False
        finally:
            loader_lock.release()

    def _stale_cache(self, key: str) -> _CacheValue | None:
        with self._cache_lock:
            return self._cache.get(key)

    def _prune_cache_locked(self, *, protected_key: str) -> None:
        if len(self._cache) > _MAX_CACHE_ENTRIES:
            victims = sorted(
                (
                    (key, value)
                    for key, value in self._cache.items()
                    if key != protected_key
                ),
                key=lambda item: (item[1].expires_at, item[1].fetched_at),
            )
            for key, _ in victims[: max(0, len(self._cache) - _MAX_CACHE_ENTRIES)]:
                self._cache.pop(key, None)
                lock = self._loader_locks.get(key)
                if lock is not None and not lock.locked():
                    self._loader_locks.pop(key, None)
        if len(self._loader_locks) > _MAX_CACHE_ENTRIES * 2:
            for key, lock in list(self._loader_locks.items()):
                if key not in self._cache and not lock.locked():
                    self._loader_locks.pop(key, None)


def build_market_summary(
    indices: list[dict[str, Any]],
    securities: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    taiex = next((row for row in indices if row.get("symbol") == "t00"), None)
    otc = next((row for row in indices if row.get("symbol") == "o00"), None)
    benchmark_rows = [taiex, otc]
    benchmark_statuses = [
        str(row.get("status") or "").upper() if row is not None else "UNAVAILABLE"
        for row in benchmark_rows
    ]
    benchmark_session_dates = [
        str(row.get("session_date") or "") if row is not None else ""
        for row in benchmark_rows
    ]
    coherent_status = (
        len(set(benchmark_statuses)) == 1
        and benchmark_statuses[0] in {"LIVE", "EOD"}
    )
    coherent_session = (
        all(benchmark_session_dates)
        and len(set(benchmark_session_dates)) == 1
    )
    usable_benchmarks = all(
        row is not None
        and _finite(row.get("change_percent")) is not None
        for row in benchmark_rows
    ) and coherent_status and coherent_session
    changes = (
        [float(row["change_percent"]) for row in benchmark_rows if row is not None]
        if usable_benchmarks
        else []
    )
    average = sum(changes) / len(changes) if len(changes) == 2 else None
    if average is None:
        regime = "市場指數資料不完整"
        posture = (
            "需同時取得狀態可用的加權與櫃買指數，才會產生全市場盤勢判讀；"
            "單一、過期或研究池個股資料都不代替市場。"
        )
        temperature = None
        strategy = "neutral"
    else:
        temperature = max(0.0, min(100.0, 50.0 + average * 8.0))
        taiex_change = _finite(taiex.get("change_percent")) if taiex else None
        otc_change = _finite(otc.get("change_percent")) if otc else None
        if taiex_change is not None and otc_change is not None and taiex_change * otc_change < 0:
            regime = "大型股與櫃買分歧"
            strategy = "mixed"
        elif average >= 1.0:
            regime = "市場動能偏多"
            strategy = "bull"
        elif average > 0:
            regime = "市場溫和上行"
            strategy = "bull"
        elif average <= -1.0:
            regime = "市場全面承壓"
            strategy = "bear"
        elif average < 0:
            regime = "市場偏弱整理"
            strategy = "bear"
        else:
            regime = "市場震盪整理"
            strategy = "mixed"
        posture = "盤勢溫度由加權與櫃買即時漲跌幅計算；它是市場描述，不是買賣訊號。"
    status = _quote_collection_status(benchmark_statuses)
    if status in {"LIVE", "EOD"} and (not coherent_status or not coherent_session):
        status = "STALE"
    session_dates = [
        str(row.get("session_date") or "")
        for row in indices
        if str(row.get("session_date") or "")
    ]
    event_times = [
        str(row.get("source_event_time") or "")
        for row in indices
        if str(row.get("source_event_time") or "")
    ]
    return {
        "status": status,
        "regime": regime,
        "strategy": strategy,
        "posture": posture,
        "temperature": round(temperature, 1) if temperature is not None else None,
        "methodology": (
            "50 + 加權與櫃買平均漲跌幅 × 8，限制於 0–100"
            if changes
            else "需同時取得加權與櫃買指數"
        ),
        "average_change_percent": round(average, 4) if average is not None else None,
        "session_date": max(session_dates) if session_dates else "",
        "as_of": max(event_times) if event_times else "",
    }


def _normalize_mis_quote(raw: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    symbol = str(raw.get("c") or "").strip()
    exchange = str(raw.get("ex") or "").strip().upper()
    if not symbol or exchange not in {"TSE", "OTC"}:
        return None
    price = _first_finite(raw.get("z"), raw.get("pz"))
    previous = _finite(raw.get("y"))
    change = price - previous if price is not None and previous is not None else None
    change_percent = (
        change / previous * 100.0
        if change is not None and previous not in {None, 0}
        else None
    )
    session_date = _yyyymmdd_date(raw.get("d"))
    event_time = _date_time(session_date, raw.get("t") or raw.get("%"))
    kind = "index" if symbol in {"t00", "o00"} else "equity"
    return {
        "symbol": symbol,
        "name": str(raw.get("n") or raw.get("nf") or symbol).strip(),
        "exchange": "TWSE" if exchange == "TSE" else "TPEx",
        "kind": kind,
        "price": price,
        "previous_close": previous,
        "change": change,
        "change_percent": change_percent,
        "open": _finite(raw.get("o")),
        "high": _finite(raw.get("h")),
        "low": _finite(raw.get("l")),
        "volume": _finite(raw.get("v")),
        "best_bid": _book_first(raw.get("b")),
        "best_ask": _book_first(raw.get("a")),
        "session_date": session_date.isoformat() if session_date else "",
        "source_event_time": event_time.isoformat() if event_time else "",
        "status": _quote_status(
            session_date,
            now,
            event_time=event_time,
            require_close_event=kind == "index",
        ),
        "source": "TWSE MIS personal-use",
    }


def _normalize_fugle_quote(
    payload: dict[str, Any],
    *,
    now: datetime,
    benchmark_symbol: str = "",
    source: str = "Fugle MarketData",
) -> dict[str, Any] | None:
    provider_symbol = str(payload.get("symbol") or "").strip()
    if not provider_symbol:
        return None
    payload_type = str(payload.get("type") or "EQUITY").strip().upper()
    kind = "index" if payload_type == "INDEX" or benchmark_symbol else "equity"
    symbol = benchmark_symbol or provider_symbol
    price = _first_finite(payload.get("lastPrice"), payload.get("closePrice"))
    previous = _first_finite(payload.get("previousClose"), payload.get("referencePrice"))
    change = _finite(payload.get("change"))
    if change is None and price is not None and previous is not None:
        change = price - previous
    change_percent = _finite(payload.get("changePercent"))
    if change_percent is None and change is not None and previous not in {None, 0}:
        change_percent = change / previous * 100.0
    session_date = _iso_date(payload.get("date"))
    last_updated = _epoch_microseconds(payload.get("lastUpdated"))
    bids = payload.get("bids") if isinstance(payload.get("bids"), list) else []
    asks = payload.get("asks") if isinstance(payload.get("asks"), list) else []
    total = payload.get("total") if isinstance(payload.get("total"), dict) else {}
    return {
        "symbol": symbol,
        "name": str(payload.get("name") or symbol),
        "exchange": str(payload.get("exchange") or payload.get("market") or ""),
        "kind": kind,
        "provider_symbol": provider_symbol,
        "price": price,
        "previous_close": previous,
        "change": change,
        "change_percent": change_percent,
        "open": _finite(payload.get("openPrice")),
        "high": _finite(payload.get("highPrice")),
        "low": _finite(payload.get("lowPrice")),
        "volume": _finite(total.get("tradeVolume")),
        "best_bid": _finite(bids[0].get("price")) if bids and isinstance(bids[0], dict) else None,
        "best_ask": _finite(asks[0].get("price")) if asks and isinstance(asks[0], dict) else None,
        "session_date": session_date.isoformat() if session_date else "",
        "source_event_time": last_updated.isoformat() if last_updated else "",
        "provider_is_close": _optional_bool(payload.get("isClose")),
        "status": _quote_status(
            session_date,
            now,
            event_time=last_updated,
            require_close_event=kind == "index",
            is_close=_optional_bool(payload.get("isClose")),
        ),
        "source": source,
    }


def _normalize_fubon_snapshot(
    payload: Any,
    *,
    requested_market: str,
    normalized_market: str,
    now: datetime,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Fubon snapshot returned a non-object payload")
    returned_market = str(payload.get("market") or "").strip().upper()
    if returned_market != requested_market.upper():
        raise ValueError(
            "Fubon snapshot market mismatch: "
            f"requested {requested_market}, "
            f"received {returned_market or 'missing'}"
        )
    session_date = _iso_date(payload.get("date"))
    if session_date is None:
        raise ValueError("Fubon snapshot is missing a valid date")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Fubon snapshot is missing its data array")
    snapshot_time = _fubon_snapshot_datetime(
        session_date,
        payload.get("time"),
    )
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    for raw in data:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not _SYMBOL_RE.fullmatch(symbol):
            continue
        payload_type = str(raw.get("type") or "EQUITY").strip().upper()
        if payload_type not in {"EQUITY", "STOCK", "ETF"}:
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        is_trial = _optional_bool(raw.get("isTrial")) is True
        close_price = _finite(raw.get("closePrice"))
        last_price = _finite(raw.get("lastPrice"))
        price = close_price
        if price is None and not is_trial:
            price = last_price
        change = _finite(raw.get("change"))
        previous = (
            price - change
            if price is not None and change is not None
            else None
        )
        change_percent = _finite(raw.get("changePercent"))
        if (
            change_percent is None
            and change is not None
            and previous not in {None, 0}
        ):
            change_percent = change / previous * 100.0
        event_time = (
            _epoch_microseconds(raw.get("lastUpdated"))
            or snapshot_time
        )
        row = {
            "symbol": symbol,
            "name": name,
            "exchange": normalized_market,
            "market": normalized_market,
            "kind": "equity",
            "provider_symbol": symbol,
            "price": price,
            "previous_close": previous,
            "reference_price": previous,
            "change": change,
            "change_percent": change_percent,
            "open": _finite(raw.get("openPrice")),
            "high": _finite(raw.get("highPrice")),
            "low": _finite(raw.get("lowPrice")),
            "volume": _finite(raw.get("tradeVolume")),
            "trade_value": _finite(raw.get("tradeValue")),
            "best_bid": None,
            "best_ask": None,
            "session_date": session_date.isoformat(),
            "source_event_time": event_time.isoformat() if event_time else "",
            "provider_is_close": None,
            "provider_is_trial": is_trial,
            "status": (
                "STALE"
                if is_trial
                else _quote_status(
                    session_date,
                    now,
                    event_time=event_time,
                )
            ),
            "source": "Fubon Neo MarketData",
        }
        existing = rows_by_symbol.get(symbol)
        existing_time = (
            _iso_datetime(existing.get("source_event_time"))
            if existing is not None
            else None
        )
        if existing is None or (
            event_time is not None
            and (existing_time is None or event_time >= existing_time)
        ):
            rows_by_symbol[symbol] = row
    if data and not rows_by_symbol:
        raise ValueError("Fubon snapshot contained no usable quote rows")
    return list(rows_by_symbol.values())


def _fubon_snapshot_datetime(
    session_date: date,
    raw_time: object,
) -> datetime | None:
    digits = re.sub(r"\D", "", str(raw_time or ""))
    if len(digits) < 6:
        return None
    try:
        parsed_time = datetime.strptime(digits[:6], "%H%M%S").time()
    except ValueError:
        return None
    return datetime.combine(session_date, parsed_time, tzinfo=TAIPEI)


def _latest_source_event(rows: Iterable[dict[str, Any]]) -> str:
    values = [
        parsed
        for row in rows
        for parsed in [_iso_datetime(row.get("source_event_time"))]
        if parsed is not None
    ]
    return max(values).isoformat() if values else ""


def _select_fugle_benchmark_symbol(
    payload: Any,
    *,
    benchmark_symbol: str,
) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return ""
    candidates: list[tuple[int, str]] = []
    for item in payload["data"]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        name = re.sub(r"\s+", "", str(item.get("name") or ""))
        if not symbol:
            continue
        score = 0
        if benchmark_symbol == "t00":
            if name in {"發行量加權股價指數", "臺灣證券交易所發行量加權股價指數"}:
                score = 100
            elif "發行量加權股價指數" in name:
                score = 80
            elif name == "加權指數":
                score = 60
        elif benchmark_symbol == "o00":
            if name in {"櫃買指數", "櫃檯買賣市場加權股價指數"}:
                score = 100
            elif "櫃買指數" in name:
                score = 80
        if score:
            candidates.append((score, symbol))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _normalize_material_announcement(
    item: dict[str, Any],
    *,
    market: str,
    source_url: str,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if market == "TWSE":
        symbol = _dict_text(item, "公司代號")
        company = _dict_text(item, "公司名稱")
        title = _dict_text(item, "主旨", "主旨 ")
        raw_date = _dict_text(item, "發言日期", "出表日期")
        raw_time = _dict_text(item, "發言時間")
        summary = _dict_text(item, "說明")
    else:
        symbol = _dict_text(item, "SecuritiesCompanyCode")
        company = _dict_text(item, "CompanyName")
        title = _dict_text(item, "主旨", "主旨 ")
        raw_date = _dict_text(item, "發言日期", "Date")
        raw_time = _dict_text(item, "發言時間")
        summary = _dict_text(item, "說明")
    published = _roc_datetime(raw_date, raw_time)
    if not title or published is None:
        return None
    display_title = f"{symbol} {company}｜{title}".strip(" ｜")
    return {
        "published_at": published.isoformat(),
        "title": display_title,
        "summary": _clean_excerpt(summary, 240),
        "url": source_url,
        "source": f"{market} 重大訊息 OpenAPI",
        "kind": "material_announcement",
        "symbol": symbol,
    }


def _normalize_alert(
    item: dict[str, Any],
    *,
    market: str,
    alert_type: str,
    source_url: str,
    today: date,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    symbol = _dict_text(item, "Code", "SecuritiesCompanyCode")
    company = _dict_text(item, "Name", "CompanyName")
    if not symbol:
        return None
    published = _roc_date(_dict_text(item, "Date"))
    period_text = _dict_text(item, "DispositionPeriod")
    start, end = _roc_period(period_text)
    active = bool(start and end and start <= today <= end)
    if alert_type == "notice" and published == today:
        active = True
    reason = _dict_text(
        item,
        "ReasonsOfDisposition",
        "DispositionReasons",
        "DisposalCondition",
        "TradingInformation",
        "TradingInfoForAttention",
        "DispositionMeasures",
    )
    return {
        "symbol": symbol,
        "name": company,
        "market": market,
        "type": alert_type,
        "active": active,
        "published_date": published.isoformat() if published else "",
        "start_date": start.isoformat() if start else "",
        "end_date": end.isoformat() if end else "",
        "period": period_text,
        "reason": _clean_excerpt(reason, 280),
        "source": source_url,
    }


def _is_empty_twse_notice_sentinel(
    item: Any,
    *,
    market: str,
    alert_type: str,
) -> bool:
    if (
        market != "TWSE"
        or alert_type != "notice"
        or not isinstance(item, dict)
    ):
        return False
    zero_markers = (
        str(item.get("Number") or "").strip(),
        str(item.get("NumberOfAnnouncement") or "").strip(),
    )
    if "0" not in zero_markers:
        return False
    return not any(
        str(item.get(key) or "").strip()
        for key in (
            "Code",
            "SecuritiesCompanyCode",
            "Date",
            "CompanyName",
            "Name",
        )
    )


def _component_public_status(
    component: dict[str, Any],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    fetched_at = component.get("fetched_at")
    component_status = str(component.get("status") or "UNAVAILABLE").upper()
    fallback = bool(component.get("fallback"))
    effective_status = (
        component_status
        if fallback or component_status in {"STALE", "UNAVAILABLE"}
        else str(status or component_status)
    )
    upstreams = component.get("upstreams")
    normalized_upstreams = (
        [dict(row) for row in upstreams if isinstance(row, dict)]
        if isinstance(upstreams, list)
        else []
    )
    latest_events = [
        str(row.get("latest_event_at") or "")
        for row in normalized_upstreams
        if str(row.get("latest_event_at") or "")
    ]
    result = {
        "status": effective_status,
        "fetched_at": fetched_at.isoformat() if isinstance(fetched_at, datetime) else "",
        "cached": bool(component.get("cached")),
        "fallback": fallback,
        "latest_event_at": max(latest_events) if latest_events else "",
    }
    if normalized_upstreams:
        result["upstreams"] = normalized_upstreams
        result["partial"] = any(
            str(row.get("status") or "") == "PARTIAL"
            for row in normalized_upstreams
        ) or (
            any(
            str(row.get("status") or "") == "UNAVAILABLE"
            for row in normalized_upstreams
            )
            and any(
                str(row.get("status") or "") != "UNAVAILABLE"
                for row in normalized_upstreams
            )
        )
    return result


def _unpack_loaded_rows(
    value: Any,
) -> tuple[Any, list[str], list[dict[str, Any]]]:
    if not isinstance(value, _LoadedRows):
        return value, [], []
    return value.rows, list(value.errors), [dict(row) for row in value.upstreams]


def _upstream_component_status(upstreams: list[dict[str, Any]]) -> str:
    statuses = {
        str(row.get("status") or "UNAVAILABLE").upper()
        for row in upstreams
    }
    if "LIVE" in statuses:
        return "LIVE"
    if "DELAYED" in statuses:
        return "DELAYED"
    if "FRESH" in statuses:
        return "FRESH"
    if "EOD" in statuses:
        return "EOD"
    if "STALE" in statuses:
        return "STALE"
    return "UNAVAILABLE"


def _dated_market_rows_status(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    key: str,
    closed_dates: set[date] | None = None,
) -> str:
    dates = [
        parsed
        for row in rows
        if isinstance(row, dict)
        for parsed in [_iso_date(row.get(key))]
        if parsed is not None
    ]
    if not dates:
        return "UNAVAILABLE"
    latest = max(dates)
    if latest > now.date():
        return "STALE"
    if closed_dates is not None:
        return (
            "EOD"
            if latest
            == expected_latest_completed_session(
                now,
                closed_dates=closed_dates,
            )
            else "STALE"
        )
    completed_business_days = sum(
        1
        for offset in range(1, (now.date() - latest).days + 1)
        if (latest + timedelta(days=offset)).weekday() < 5
    )
    if completed_business_days <= 1:
        return "EOD"
    return "STALE"


def _reclassified_dated_component(
    component: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    key: str,
    closed_dates: set[date],
) -> dict[str, Any]:
    normalized = dict(component)
    upstreams: list[dict[str, Any]] = []
    for source in component.get("upstreams") or []:
        if not isinstance(source, dict):
            continue
        updated = dict(source)
        latest_event = str(updated.get("latest_event_at") or "")
        adjusted_status = _dated_market_rows_status(
            [{key: latest_event}] if latest_event else [],
            now=now,
            key=key,
            closed_dates=closed_dates,
        )
        if adjusted_status != str(updated.get("status") or "UNAVAILABLE"):
            updated["transport_status"] = updated.get("status")
            updated["status"] = adjusted_status
            updated["calendar_adjusted"] = True
        upstreams.append(updated)
    normalized["upstreams"] = upstreams
    normalized["status"] = (
        _quote_collection_status(
            source.get("status") for source in upstreams
        )
        if upstreams
        else _dated_market_rows_status(
            rows,
            now=now,
            key=key,
            closed_dates=closed_dates,
        )
    )
    return normalized


def _latest_row_datetime(
    rows: list[dict[str, Any]],
    key: str,
) -> datetime | None:
    values = [
        parsed
        for row in rows
        if isinstance(row, dict)
        for parsed in [_iso_datetime(row.get(key))]
        if parsed is not None
    ]
    return max(values) if values else None


def _event_rows_status(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    key: str,
    max_age: timedelta,
) -> str:
    if not rows:
        return "FRESH"
    latest = _latest_row_datetime(rows, key)
    if latest is None:
        return "STALE"
    age = now - latest.astimezone(now.tzinfo)
    if age < -timedelta(minutes=5):
        return "STALE"
    return "FRESH" if age <= max_age else "STALE"


def _public_stream_health(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "aggregate_count",
        "connect_worker_active",
        "coverage_complete",
        "desired_index_count",
        "desired_stock_count",
        "index_count",
        "last_message_at",
        "ok",
        "quiet_seconds",
        "ready",
        "reconnect_failures",
        "rejected_messages",
        "retry_after_seconds",
        "status",
        "transport_status",
        "usable",
    }
    return {key: value[key] for key in allowed if key in value}


def _payload_status(payload: Any, *, fetched_at: datetime, now: datetime) -> str:
    if not payload:
        return "UNAVAILABLE"
    if isinstance(payload, list):
        statuses = [
            str(row.get("status") or "")
            for row in payload
            if isinstance(row, dict) and row.get("status")
        ]
        if statuses:
            return _quote_collection_status(statuses)
    age = max(0.0, (now - fetched_at).total_seconds())
    return "FRESH" if age <= 600 else "STALE"


def _overall_status(values: Iterable[object]) -> str:
    statuses = {str(value or "").upper() for value in values}
    if "LIVE" in statuses:
        return "LIVE"
    if "EOD" in statuses or "FRESH" in statuses:
        return "EOD"
    if "STALE" in statuses:
        return "STALE"
    return "UNAVAILABLE"


def _quote_collection_status(values: Iterable[object]) -> str:
    statuses = [str(value or "").upper() for value in values if str(value or "").strip()]
    if not statuses:
        return "UNAVAILABLE"
    if all(status == "UNAVAILABLE" for status in statuses):
        return "UNAVAILABLE"
    if any(status in {"STALE", "UNAVAILABLE"} for status in statuses):
        return "STALE"
    if all(status == "LIVE" for status in statuses):
        return "LIVE"
    if all(status == "DELAYED" for status in statuses):
        return "DELAYED"
    if set(statuses).issubset({"LIVE", "DELAYED"}):
        return "DELAYED"
    if all(status == "EOD" for status in statuses):
        return "EOD"
    return "STALE"


def _quotes_need_calendar_reclassification(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
) -> bool:
    for row in rows:
        if (
            str(row.get("kind") or "") != "index"
            or str(row.get("status") or "") != "STALE"
        ):
            continue
        session = _iso_date(row.get("session_date"))
        if session is None or session >= now.date():
            continue
        event = _iso_datetime(row.get("source_event_time"))
        if row.get("provider_is_close") is True or _is_credible_index_close_event(event):
            return True
    return False


def _stream_row_matches_rest_baseline(
    baseline: dict[str, Any],
    stream_row: dict[str, Any],
) -> bool:
    if str(baseline.get("status") or "").upper() not in {"LIVE", "EOD"}:
        return False
    baseline_session = _iso_date(baseline.get("session_date"))
    stream_event = _iso_datetime(stream_row.get("source_event_time"))
    if (
        baseline_session is None
        or stream_event is None
        or baseline_session != stream_event.date()
    ):
        return False
    if str(baseline.get("kind") or "") != "index":
        stream_session = _iso_date(stream_row.get("date"))
        if stream_session is None or stream_session != stream_event.date():
            return False
    return True


def _reclassify_quote_with_calendar(
    row: dict[str, Any],
    *,
    now: datetime,
    closed_dates: set[date],
) -> dict[str, Any]:
    normalized = dict(row)
    normalized["status"] = _quote_status(
        _iso_date(row.get("session_date")),
        now,
        event_time=_iso_datetime(row.get("source_event_time")),
        require_close_event=str(row.get("kind") or "") == "index",
        is_close=_optional_bool(row.get("provider_is_close")),
        closed_dates=closed_dates,
    )
    return normalized


def _reclassified_quote_component(
    component: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = dict(component)
    normalized["payload"] = rows
    normalized["status"] = _quote_collection_status(
        row.get("status") for row in rows
    )
    quote_statuses: dict[str, str] = {}
    for row in rows:
        status = str(row.get("status") or "UNAVAILABLE")
        for symbol in (row.get("symbol"), row.get("provider_symbol")):
            key = str(symbol or "")
            if key:
                quote_statuses[key] = status
    market_statuses = {
        market: _quote_collection_status(
            row.get("status")
            for row in rows
            if str(row.get("market") or row.get("exchange") or "").upper()
            == market
        )
        for market in ("TWSE", "TPEX")
    }
    upstreams: list[dict[str, Any]] = []
    for source in component.get("upstreams") or []:
        if not isinstance(source, dict):
            continue
        updated = dict(source)
        source_id = str(updated.get("id") or "")
        if source_id == "twse-mis":
            adjusted_status = normalized["status"]
        elif source_id == "fubon-snapshot:TSE":
            adjusted_status = market_statuses["TWSE"]
        elif source_id == "fubon-snapshot:OTC":
            adjusted_status = market_statuses["TPEX"]
        else:
            adjusted_status = quote_statuses.get(
                source_id.removeprefix("fugle:").removeprefix("fubon:")
            )
        if adjusted_status and adjusted_status != updated.get("status"):
            updated["unadjusted_status"] = updated.get("status")
            updated["status"] = adjusted_status
            updated["calendar_adjusted"] = True
        upstreams.append(updated)
    normalized["upstreams"] = upstreams
    return normalized


def _quote_status(
    session_date: date | None,
    now: datetime,
    *,
    event_time: datetime | None,
    require_close_event: bool = False,
    is_close: bool | None = None,
    closed_dates: set[date] | None = None,
) -> str:
    if session_date is None:
        return "UNAVAILABLE"
    if session_date > now.date():
        return "STALE"
    normalized_event = event_time.astimezone(now.tzinfo) if event_time else None
    if normalized_event is not None:
        if normalized_event.date() != session_date:
            return "STALE"
        if normalized_event > now + timedelta(seconds=15):
            return "STALE"
    expected_session = (
        expected_live_quote_session(now, closed_dates=closed_dates)
        if closed_dates is not None
        else None
    )
    if expected_session is not None and session_date != expected_session:
        return "STALE"
    if session_date == now.date():
        if require_close_event and is_close is True:
            return "EOD"
        current_minutes = now.hour * 60 + now.minute
        if now.weekday() < 5 and 9 * 60 <= current_minutes <= 13 * 60 + 40:
            if (
                require_close_event
                and is_close is not False
                and _is_credible_index_close_event(normalized_event)
            ):
                return "EOD"
            if normalized_event is None:
                return "STALE"
            age_seconds = (now - normalized_event).total_seconds()
            return "LIVE" if -15 <= age_seconds <= 120 else "STALE"
        if require_close_event:
            if is_close is True:
                return "EOD"
            if is_close is False:
                return "STALE"
            return (
                "EOD"
                if _is_credible_index_close_event(normalized_event)
                else "STALE"
            )
        return "EOD"
    if expected_session == session_date:
        if not require_close_event:
            return "EOD"
        if is_close is True:
            return "EOD"
        if is_close is False:
            return "STALE"
        return (
            "EOD"
            if _is_credible_index_close_event(normalized_event)
            else "STALE"
        )
    delta = (now.date() - session_date).days
    if require_close_event and 0 <= delta <= 3:
        current_minutes = now.hour * 60 + now.minute
        prior_close_is_current = now.weekday() >= 5 or current_minutes < 9 * 60
        if not prior_close_is_current:
            return "STALE"
        if is_close is True:
            return "EOD"
        if is_close is False:
            return "STALE"
        return (
            "EOD"
            if _is_credible_index_close_event(normalized_event)
            else "STALE"
        )
    if 0 <= delta <= 3:
        current_minutes = now.hour * 60 + now.minute
        if now.weekday() >= 5 or current_minutes < 9 * 60:
            return "EOD"
    return "STALE"


def _is_credible_index_close_event(event_time: datetime | None) -> bool:
    if event_time is None:
        return False
    event_minutes = event_time.hour * 60 + event_time.minute
    # Without an explicit provider isClose signal, only accept the exchange's
    # post-auction index timestamp. 13:25–13:30 is still the closing auction
    # and must never be promoted to EOD merely because the quote later froze.
    return 13 * 60 + 33 <= event_minutes <= 14 * 60 + 30


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _dict_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_excerpt(value: object, limit: int) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "---", "N/A", "nan", "None"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_finite(*values: object) -> float | None:
    for value in values:
        number = _finite(value)
        if number is not None:
            return number
    return None


def _book_first(value: object) -> float | None:
    text = str(value or "").split("_", 1)[0]
    return _finite(text)


def _yyyymmdd_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI)


def _roc_date(value: object) -> date | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) not in {7, 8}:
        return None
    try:
        if len(digits) == 7:
            year = int(digits[:3]) + 1911
            month = int(digits[3:5])
            day = int(digits[5:7])
        else:
            year = int(digits[:4])
            month = int(digits[4:6])
            day = int(digits[6:8])
        return date(year, month, day)
    except ValueError:
        return None


def _roc_datetime(raw_date: object, raw_time: object = "") -> datetime | None:
    parsed_date = _roc_date(raw_date)
    if parsed_date is None:
        return None
    digits = re.sub(r"\D", "", str(raw_time or "")).zfill(6)[-6:]
    try:
        parsed_time = datetime.strptime(digits, "%H%M%S").time()
    except ValueError:
        parsed_time = datetime.min.time()
    return datetime.combine(parsed_date, parsed_time, tzinfo=TAIPEI)


def _roc_period(value: object) -> tuple[date | None, date | None]:
    parts = re.split(r"[~～－—–至]+", str(value or ""))
    parsed = [_roc_date(part) for part in parts if part.strip()]
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    return None, None


def _date_time(session_date: date | None, raw_time: object) -> datetime | None:
    if session_date is None:
        return None
    text = str(raw_time or "").strip()
    try:
        parsed_time = datetime.strptime(text, "%H:%M:%S").time()
    except ValueError:
        return None
    return datetime.combine(session_date, parsed_time, tzinfo=TAIPEI)


def _epoch_microseconds(value: object) -> datetime | None:
    number = _finite(value)
    if number is None:
        return None
    if number >= 100_000_000_000_000:
        seconds = number / 1_000_000
    elif number >= 100_000_000_000:
        seconds = number / 1_000
    else:
        seconds = number
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(TAIPEI)
    except (OSError, OverflowError, ValueError):
        return None
