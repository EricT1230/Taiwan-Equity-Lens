from __future__ import annotations

import json
import re
import secrets
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html
from taiwan_stock_analysis.evidence_quality import assess_evidence_quality
from taiwan_stock_analysis.handoff import NON_ADVICE_NOTICE, build_handoff_quality_gate
from taiwan_stock_analysis.handoff_pack import write_handoff_evidence_pack
from taiwan_stock_analysis.live_market import LiveMarketService, normalize_symbols
from taiwan_stock_analysis.market_breadth import MarketBreadthService
from taiwan_stock_analysis.us_market import USMarketService
from taiwan_stock_analysis.review_action_state import (
    build_review_action_state_report,
    load_review_action_state,
    review_action_key,
    set_review_action_state,
)

_MAX_REQUEST_BYTES = 1024 * 1024
_LOCAL_LIVE_SYMBOL_LIMIT = 40
_PUBLIC_LIVE_SYMBOL_LIMIT = 20
_PUBLIC_LIVE_REQUESTS_PER_MINUTE = 2
_PUBLIC_LIVE_PROVIDER_CALLS_PER_MINUTE = 60
_PUBLIC_LIVE_PROVIDER_FIXED_CALLS = 4
_LOCAL_LIVE_MIN_REFRESH_SECONDS = 5
_PUBLIC_LIVE_MIN_REFRESH_SECONDS = 30
_LIVE_SNAPSHOT_TIMEOUT_SECONDS = 14.0
_MARKET_BREADTH_TIMEOUT_SECONDS = 27.0
_LIVE_SNAPSHOT_WORKERS = 4
_LIVE_SNAPSHOT_OUTSTANDING = 8
_MARKET_BREADTH_WORKERS = 1
_MARKET_BREADTH_OUTSTANDING = 1
_MUTATION_TOKEN_HEADER = "X-Taiwan-Equity-Lens-Token"

DashboardOpener = Callable[[str], object]


class DashboardServer(ThreadingHTTPServer):
    def __init__(
        self,
        *args: Any,
        snapshot_executor: ThreadPoolExecutor,
        breadth_executor: ThreadPoolExecutor,
        live_service: LiveMarketService,
        **kwargs: Any,
    ) -> None:
        self._snapshot_executor = snapshot_executor
        self._breadth_executor = breadth_executor
        self._live_service = live_service
        super().__init__(*args, **kwargs)

    def server_close(self) -> None:
        super().server_close()
        self._snapshot_executor.shutdown(wait=False, cancel_futures=True)
        self._breadth_executor.shutdown(wait=False, cancel_futures=True)
        close = getattr(self._live_service, "close", None)
        if callable(close):
            close()


class _SlidingWindowLimiter:
    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        max_clients: int = 2048,
    ) -> None:
        self._max_requests = max(1, int(max_requests))
        self._window_seconds = max(1.0, float(window_seconds))
        self._max_clients = max(1, int(max_clients))
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        key: str,
        *,
        now: float | None = None,
        cost: int = 1,
    ) -> bool:
        timestamp = time.monotonic() if now is None else float(now)
        cutoff = timestamp - self._window_seconds
        normalized_key = str(key or "unknown")
        normalized_cost = max(1, int(cost))
        with self._lock:
            bucket = [
                seen_at
                for seen_at in self._requests.get(normalized_key, [])
                if seen_at > cutoff
            ]
            if not bucket:
                self._requests.pop(normalized_key, None)
            if normalized_key not in self._requests and len(self._requests) >= self._max_clients:
                expired = [
                    client
                    for client, seen in self._requests.items()
                    if not seen or seen[-1] <= cutoff
                ]
                for client in expired:
                    self._requests.pop(client, None)
                if len(self._requests) >= self._max_clients:
                    oldest = min(
                        self._requests,
                        key=lambda client: self._requests[client][-1],
                    )
                    self._requests.pop(oldest, None)
            if len(bucket) + normalized_cost > self._max_requests:
                self._requests[normalized_key] = bucket
                return False
            bucket.extend([timestamp] * normalized_cost)
            self._requests[normalized_key] = bucket
            return True


def set_review_action_status_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    state_path = _allowed_state_path(str(payload.get("state_path") or ""), allowed_roots)
    stock_id = _required_text(payload, "stock_id")
    action_id = _required_text(payload, "action_id")
    status = _required_text(payload, "status")
    # CRITICAL: None means the JSON payload omitted this key entirely (bulk
    # updates and status-only single-row re-sets both do this on purpose), OR
    # sent it as an explicit JSON null -- either way there is no real value to
    # write, so set_review_action_state() must treat it as "preserve the
    # currently stored value". Checking payload.get(key) is not None (not
    # "key" in payload) is what folds null and absent together: `"note" in
    # payload` alone would be True for {"note": null}, and str(None) would
    # then write the literal string "None" over real evidence. A payload that
    # includes the key with any non-null value (even "") is an explicit
    # set/clear and is written as-is. This is what stops bulk/status-only
    # updates from silently wiping previously recorded evidence (the CRITICAL
    # bug this fixes).
    note = str(payload["note"]) if payload.get("note") is not None else None
    reviewer = str(payload["reviewer"]) if payload.get("reviewer") is not None else None
    evidence_url = str(payload["evidence_url"]) if payload.get("evidence_url") is not None else None

    output_path, backup_path = set_review_action_state(
        state_path,
        stock_id,
        action_id,
        status,
        note=note,
        reviewer=reviewer,
        evidence_url=evidence_url,
    )
    report = _state_report_for_path(output_path)
    # Read back what is actually persisted rather than echoing the local
    # variables above (which may be None, or may reflect a different call's
    # preserved value) -- keeps the response honest whether this call set,
    # cleared, or preserved the evidence fields.
    stored_note, stored_reviewer, stored_evidence_url = _stored_evidence_fields(output_path, stock_id, action_id)
    return {
        "action_id": action_id,
        "backup_path": str(backup_path) if backup_path else "",
        "by_status": report.get("by_status", {}),
        "last_updated": report.get("last_updated", "-"),
        "ok": True,
        "note": stored_note,
        "reviewer": stored_reviewer,
        "evidence_missing_count": report.get("evidence_missing_count", 0),
        "invalid_evidence_count": report.get("invalid_evidence_count", 0),
        "handoff_status": report.get("handoff_status", "blocked"),
        "ready": bool(report.get("ready")),
        "blocker_count": report.get("blocker_count", 0),
        "open_count": report.get("open_count", 0),
        "next_step": report.get("next_step", ""),
        "evidence_url": stored_evidence_url,
        "state_path": str(output_path),
        "status": status,
        "stale_count": report.get("stale_count", 0),
        "stock_id": stock_id,
        "updated_at": report.get("last_updated", "-"),
    }


def _stored_evidence_fields(state_path: Path, stock_id: str, action_id: str) -> tuple[str, str, str]:
    state, warning = load_review_action_state(state_path)
    if warning:
        return "", "", ""
    entry = state.get("actions", {}).get(review_action_key(stock_id, action_id))
    if not isinstance(entry, dict):
        return "", "", ""
    return (
        str(entry.get("note") or ""),
        str(entry.get("reviewer") or ""),
        str(entry.get("evidence_url") or ""),
    )


def compose_evidence_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    state_path = _allowed_state_path(str(payload.get("state_path") or ""), allowed_roots)
    stock_id = _required_text(payload, "stock_id")
    action_id = _required_text(payload, "action_id")
    status = str(payload.get("status") or "done").strip()
    if status == "open":
        raise ValueError("evidence composer status must be done, deferred, or ignored")
    note = _required_text(payload, "note")
    reviewer = _required_text(payload, "reviewer")
    evidence_summary = _required_text(payload, "evidence_summary")
    evidence_url = str(payload.get("evidence_url") or "").strip() or _default_evidence_url(stock_id, action_id)
    evidence_path = _allowed_evidence_path(evidence_url, state_path, allowed_roots)

    evidence_created = not evidence_path.exists()
    overwrite = _payload_bool(payload.get("overwrite"))
    if evidence_created or overwrite:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            _compose_evidence_markdown(
                stock_id=stock_id,
                action_id=action_id,
                status=status,
                note=note,
                reviewer=reviewer,
                evidence_summary=evidence_summary,
            ),
            encoding="utf-8",
        )

    state_result = set_review_action_status_from_payload(
        {
            **payload,
            "state_path": str(state_path),
            "stock_id": stock_id,
            "action_id": action_id,
            "status": status,
            "note": note,
            "reviewer": reviewer,
            "evidence_url": evidence_url,
        },
        allowed_roots=allowed_roots,
    )
    evidence_content = _read_text(evidence_path)
    evidence_quality = assess_evidence_quality(
        note=note,
        reviewer=reviewer,
        evidence_summary=evidence_summary,
        evidence_path=evidence_path,
        evidence_content=evidence_content,
    )
    return {
        **state_result,
        "evidence_created": evidence_created,
        "evidence_path": str(evidence_path),
        "evidence_preview": _evidence_preview(evidence_path, evidence_content),
        "evidence_quality": evidence_quality,
        "evidence_updated": bool(overwrite and not evidence_created),
        "evidence_url": evidence_url,
        "reviewer_confidence_ready": evidence_quality["ready"],
        "reviewer_confidence_status": evidence_quality["status"],
    }


def write_handoff_pack_from_payload(
    payload: dict[str, Any],
    *,
    allowed_roots: list[Path],
) -> dict[str, Any]:
    research_summary_path = _allowed_path(
        str(payload.get("research_summary_path") or ""),
        allowed_roots,
        label="research_summary_path",
    )
    raw_state_path = str(payload.get("state_path") or "").strip()
    state_path = (
        _allowed_path(raw_state_path, allowed_roots, label="state_path")
        if raw_state_path
        else research_summary_path.with_name("review_action_state.json")
    )
    raw_output_dir = str(payload.get("output_dir") or "").strip()
    output_dir = (
        _allowed_path(raw_output_dir, allowed_roots, label="output_dir")
        if raw_output_dir
        else research_summary_path.parent / "handoff-pack"
    )
    if not any(_is_relative_to(output_dir.resolve(), root.resolve()) for root in allowed_roots):
        raise ValueError("output_dir is outside the served dashboard directories")

    try:
        blocker_limit = int(payload.get("blocker_limit") or 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("blocker_limit must be an integer") from exc

    summary_path = write_handoff_evidence_pack(
        research_summary_path,
        output_dir,
        state_path=state_path,
        output_format=str(payload.get("format") or "both"),
        blocker_limit=blocker_limit,
    )
    summary = _load_pack_summary(summary_path)
    return {
        "blocker_count": summary.get("blocker_count", 0),
        "evidence_missing_count": summary.get("evidence_missing_count", 0),
        "gate_status": summary.get("gate_status", "blocked"),
        "html_path": summary.get("html_path", ""),
        "invalid_evidence_count": summary.get("invalid_evidence_count", 0),
        "markdown_path": summary.get("markdown_path", ""),
        "ok": True,
        "output_dir": str(output_dir),
        "ready": bool(summary.get("ready")),
        "research_summary_path": str(research_summary_path),
        "state_path": str(state_path),
        "summary_path": str(summary_path),
    }


def serve_dashboard(
    search_dirs: list[Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    market_data_provider: str = "auto",
    public_read_only: bool = False,
    opener: DashboardOpener | None = None,
) -> str:
    server, url = create_dashboard_server(
        search_dirs,
        host=host,
        port=port,
        market_data_provider=market_data_provider,
        public_read_only=public_read_only,
    )
    if open_browser:
        (opener or webbrowser.open)(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return url


def create_dashboard_server(
    search_dirs: list[Path],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    live_service: LiveMarketService | None = None,
    breadth_service: MarketBreadthService | None = None,
    us_market_service: USMarketService | None = None,
    market_data_provider: str = "auto",
    public_read_only: bool = False,
) -> tuple[DashboardServer, str]:
    roots = [directory.resolve() for directory in search_dirs]
    allow_mutations = _is_loopback_host(host) and not public_read_only
    mutation_token = secrets.token_urlsafe(32) if allow_mutations else ""
    if live_service is not None:
        service = live_service
        if (
            not allow_mutations
            and getattr(service, "public_mode", None) is not True
        ):
            raise ValueError(
                "public/read-only dashboard requires a public-mode live service"
            )
    else:
        service = LiveMarketService(
            public_mode=not allow_mutations,
            provider=market_data_provider,
        )
    market_breadth = breadth_service or MarketBreadthService(
        supporting_loader=getattr(service, "breadth_support", None),
    )
    us_market = us_market_service or USMarketService()
    snapshot_executor = ThreadPoolExecutor(
        max_workers=_LIVE_SNAPSHOT_WORKERS,
        thread_name_prefix="market-snapshot",
    )
    breadth_executor = ThreadPoolExecutor(
        max_workers=_MARKET_BREADTH_WORKERS,
        thread_name_prefix="market-breadth",
    )
    handler = _build_handler(
        roots,
        live_service=service,
        breadth_service=market_breadth,
        us_market_service=us_market,
        allow_mutations=allow_mutations,
        mutation_token=mutation_token,
        snapshot_executor=snapshot_executor,
        breadth_executor=breadth_executor,
    )
    try:
        server = DashboardServer(
            (host, port),
            handler,
            snapshot_executor=snapshot_executor,
            breadth_executor=breadth_executor,
            live_service=service,
        )
    except Exception:
        snapshot_executor.shutdown(wait=False, cancel_futures=True)
        breadth_executor.shutdown(wait=False, cancel_futures=True)
        raise
    actual_host, actual_port = server.server_address[:2]
    return server, f"http://{actual_host}:{actual_port}/"


def _build_handler(
    search_dirs: list[Path],
    *,
    live_service: LiveMarketService,
    breadth_service: MarketBreadthService,
    us_market_service: USMarketService,
    allow_mutations: bool,
    mutation_token: str,
    snapshot_executor: ThreadPoolExecutor,
    breadth_executor: ThreadPoolExecutor,
) -> type[BaseHTTPRequestHandler]:
    provider_health = live_service.health()
    provider_mode = str(provider_health.get("provider_mode") or "")
    capacity_guarded = not allow_mutations or bool(
        provider_health.get(
            "provider_capacity_guarded",
            provider_mode in {"fubon", "fugle"},
        )
    )
    live_symbol_limit = (
        _PUBLIC_LIVE_SYMBOL_LIMIT
        if capacity_guarded
        else _LOCAL_LIVE_SYMBOL_LIMIT
    )
    policy_minimum_refresh = (
        _PUBLIC_LIVE_MIN_REFRESH_SECONDS
        if not allow_mutations
        else _LOCAL_LIVE_MIN_REFRESH_SECONDS
    )
    minimum_refresh_seconds = max(
        policy_minimum_refresh,
        int(
            provider_health.get("minimum_client_refresh_seconds")
            or (
                _PUBLIC_LIVE_MIN_REFRESH_SECONDS
                if provider_mode == "fugle"
                else _LOCAL_LIVE_MIN_REFRESH_SECONDS
            )
        ),
    )
    live_requests_per_minute = (
        _PUBLIC_LIVE_REQUESTS_PER_MINUTE
        if not allow_mutations
        else max(
            _PUBLIC_LIVE_REQUESTS_PER_MINUTE,
            (
                60 + max(1, minimum_refresh_seconds) - 1
            )
            // max(1, minimum_refresh_seconds),
        )
    )
    public_live_limiter = _SlidingWindowLimiter(
        max_requests=live_requests_per_minute,
        window_seconds=60,
    )
    public_provider_budget = _SlidingWindowLimiter(
        max_requests=int(
            provider_health.get("provider_calls_per_minute_budget")
            or _PUBLIC_LIVE_PROVIDER_CALLS_PER_MINUTE
        ),
        window_seconds=60,
        max_clients=1,
    )
    snapshot_slots = threading.BoundedSemaphore(_LIVE_SNAPSHOT_OUTSTANDING)
    breadth_slots = threading.BoundedSemaphore(_MARKET_BREADTH_OUTSTANDING)
    breadth_limiter = _SlidingWindowLimiter(
        max_requests=12,
        window_seconds=60,
    )
    mutation_token_attribute = (
        f'data-action-api-token="{mutation_token}" '
        if allow_mutations
        else ""
    )

    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if allow_mutations and not self._has_trusted_loopback_host():
                self._send_json(
                    {"error": "untrusted Host header", "ok": False},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            parsed = urlsplit(self.path)
            if parsed.path == "/api/live/health":
                self._send_json(live_service.health(), cache_control="no-store")
                return
            if parsed.path == "/api/market/health":
                self._send_json(breadth_service.health(), cache_control="no-store")
                return
            if parsed.path == "/api/us/health":
                payload = us_market_service.health()
                payload["enabled"] = allow_mutations
                self._send_json(payload, cache_control="no-store")
                return
            if parsed.path == "/api/us/market":
                if not allow_mutations:
                    self._send_json(
                        {
                            "error": (
                                "Nasdaq.com reference data is available only "
                                "on the loopback personal dashboard"
                            ),
                            "ok": False,
                        },
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return
                try:
                    payload = us_market_service.snapshot()
                except Exception as exc:
                    self.log_error(
                        "US market snapshot failed: %s",
                        type(exc).__name__,
                    )
                    self._send_json(
                        {"error": "US market snapshot failed", "ok": False},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._send_json(payload, cache_control="no-store")
                return
            if parsed.path == "/api/market/breadth":
                if not breadth_limiter.allow(self.client_address[0]):
                    self._send_json(
                        {
                            "error": "market breadth refresh limit exceeded",
                            "ok": False,
                        },
                        status=HTTPStatus.TOO_MANY_REQUESTS,
                        extra_headers={"Retry-After": "10"},
                    )
                    return
                if not breadth_slots.acquire(blocking=False):
                    self._send_json(
                        {"error": "market breadth refresh is already running", "ok": False},
                        status=HTTPStatus.SERVICE_UNAVAILABLE,
                        extra_headers={"Retry-After": "5"},
                    )
                    return
                try:
                    future = breadth_executor.submit(breadth_service.snapshot)
                except RuntimeError:
                    breadth_slots.release()
                    self._send_json(
                        {"error": "market breadth service is stopping", "ok": False},
                        status=HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                future.add_done_callback(lambda _future: breadth_slots.release())
                try:
                    payload = future.result(timeout=_MARKET_BREADTH_TIMEOUT_SECONDS)
                except FutureTimeoutError:
                    future.cancel()
                    self._send_json(
                        {"error": "market breadth deadline exceeded", "ok": False},
                        status=HTTPStatus.GATEWAY_TIMEOUT,
                        extra_headers={"Retry-After": "15"},
                    )
                    return
                except Exception as exc:
                    self.log_error(
                        "market breadth snapshot failed: %s",
                        type(exc).__name__,
                    )
                    self._send_json(
                        {"error": "market breadth snapshot failed", "ok": False},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._send_json(payload, cache_control="no-store")
                return
            if parsed.path == "/api/live/snapshot":
                raw_symbols = parse_qs(parsed.query).get("symbols", [""])[0]
                symbols = normalize_symbols(
                    re.split(r"[\s,|]+", raw_symbols),
                    limit=live_symbol_limit + 1,
                )
                if len(symbols) > live_symbol_limit:
                    self._send_json(
                        {
                            "error": (
                                "live-data requests accept at most "
                                f"{live_symbol_limit} symbols for this provider mode"
                            ),
                            "ok": False,
                            "symbol_limit": live_symbol_limit,
                        },
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                if capacity_guarded:
                    cost_loader = getattr(
                        live_service,
                        "provider_request_cost",
                        None,
                    )
                    provider_cost = (
                        int(cost_loader(symbols))
                        if callable(cost_loader)
                        else len(symbols) + _PUBLIC_LIVE_PROVIDER_FIXED_CALLS
                    )
                    client_allowed = public_live_limiter.allow(self.client_address[0])
                    provider_allowed = (
                        client_allowed
                        and public_provider_budget.allow(
                            "licensed-provider",
                            cost=provider_cost,
                        )
                    )
                    if not provider_allowed:
                        self._send_json(
                            {
                                "error": "live-data provider request budget exceeded",
                                "ok": False,
                            },
                            status=HTTPStatus.TOO_MANY_REQUESTS,
                            extra_headers={"Retry-After": "60"},
                        )
                        return
                if not snapshot_slots.acquire(blocking=False):
                    self._send_json(
                        {"error": "live snapshot workers are busy", "ok": False},
                        status=HTTPStatus.SERVICE_UNAVAILABLE,
                        extra_headers={"Retry-After": "5"},
                    )
                    return
                try:
                    future = snapshot_executor.submit(live_service.snapshot, symbols)
                except RuntimeError:
                    snapshot_slots.release()
                    self._send_json(
                        {"error": "live snapshot service is stopping", "ok": False},
                        status=HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                future.add_done_callback(lambda _future: snapshot_slots.release())
                try:
                    payload = future.result(timeout=_LIVE_SNAPSHOT_TIMEOUT_SECONDS)
                except FutureTimeoutError:
                    future.cancel()
                    self._send_json(
                        {"error": "live snapshot deadline exceeded", "ok": False},
                        status=HTTPStatus.GATEWAY_TIMEOUT,
                        extra_headers={"Retry-After": "15"},
                    )
                    return
                except Exception as exc:
                    self.log_error(
                        "live snapshot failed: %s",
                        type(exc).__name__,
                    )
                    self._send_json(
                        {"error": "live snapshot failed", "ok": False},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._send_json(payload, cache_control="no-store")
                return
            if parsed.path not in {"/", "/dashboard", "/dashboard.html"}:
                self._send_json({"error": "not found", "ok": False}, status=HTTPStatus.NOT_FOUND)
                return
            items = discover_dashboard_items(search_dirs)
            html = render_dashboard_html(
                items,
                action_api_enabled=allow_mutations,
                live_api_enabled=True,
            )
            html = html.replace(
                "<body ",
                (
                    f'<body data-live-symbol-limit="{live_symbol_limit}" '
                    f'data-live-min-refresh-seconds="{minimum_refresh_seconds}" '
                    f'data-us-market-api-enabled="{"true" if allow_mutations else "false"}" '
                    f"{mutation_token_attribute}"
                ),
                1,
            )
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if not allow_mutations:
                self._discard_bounded_request_body()
                self._send_json(
                    {"error": "write APIs are available only on a loopback server", "ok": False},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            if not self._has_trusted_loopback_host():
                self._discard_bounded_request_body()
                self._send_json(
                    {"error": "untrusted Host header", "ok": False},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            if not self._has_same_origin_when_present():
                self._discard_bounded_request_body()
                self._send_json(
                    {"error": "cross-origin mutation request", "ok": False},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            supplied_tokens = self.headers.get_all(_MUTATION_TOKEN_HEADER) or []
            supplied_token = str(supplied_tokens[0]) if len(supplied_tokens) == 1 else ""
            if not secrets.compare_digest(supplied_token, mutation_token):
                self._discard_bounded_request_body()
                self._send_json(
                    {"error": "invalid mutation token", "ok": False},
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            if self.path not in {
                "/api/review-actions/set",
                "/api/handoff-pack/write",
                "/api/evidence/compose-and-set",
            }:
                self._discard_bounded_request_body()
                self._send_json({"error": "not found", "ok": False}, status=HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json()
                if self.path == "/api/review-actions/set":
                    result = set_review_action_status_from_payload(payload, allowed_roots=search_dirs)
                elif self.path == "/api/handoff-pack/write":
                    result = write_handoff_pack_from_payload(payload, allowed_roots=search_dirs)
                else:
                    result = compose_evidence_from_payload(payload, allowed_roots=search_dirs)
            except ValueError as exc:
                self._send_json({"error": str(exc), "ok": False}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)

        def _discard_bounded_request_body(self) -> None:
            try:
                content_length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                return
            if 0 < content_length <= _MAX_REQUEST_BYTES:
                self.rfile.read(content_length)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _has_trusted_loopback_host(self) -> bool:
            host_headers = self.headers.get_all("Host") or []
            if len(host_headers) != 1:
                return False
            return (
                _validated_loopback_authority(
                    host_headers[0],
                    expected_port=int(self.server.server_address[1]),
                )
                is not None
            )

        def _has_same_origin_when_present(self) -> bool:
            origin_headers = self.headers.get_all("Origin") or []
            if not origin_headers:
                return True
            if len(origin_headers) != 1:
                return False
            origin = str(origin_headers[0]).strip()
            if not origin:
                return False
            host_headers = self.headers.get_all("Host") or []
            if len(host_headers) != 1:
                return False
            host = _validated_loopback_authority(
                host_headers[0],
                expected_port=int(self.server.server_address[1]),
            )
            if host is None:
                return False
            parsed = urlsplit(origin)
            if (
                parsed.scheme.lower() != "http"
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
            ):
                return False
            origin_host = _validated_loopback_authority(
                parsed.netloc,
                expected_port=int(self.server.server_address[1]),
            )
            return origin_host == host

        def _read_json(self) -> dict[str, Any]:
            content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._discard_bounded_request_body()
                raise ValueError("Content-Type must be application/json")
            try:
                content_length = int(self.headers.get("Content-Length") or "0")
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if content_length <= 0:
                raise ValueError("request body is required")
            if content_length > _MAX_REQUEST_BYTES:
                raise ValueError("request body is too large")
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
            cache_control: str = "no-store",
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardRequestHandler


def _is_loopback_host(host: str) -> bool:
    return str(host or "").strip().lower() in {"127.0.0.1", "::1", "localhost"}


def _validated_loopback_authority(
    raw_authority: str | None,
    *,
    expected_port: int,
) -> str | None:
    authority = str(raw_authority or "").strip()
    if not authority:
        return None
    parsed = urlsplit(f"//{authority}")
    if (
        parsed.scheme
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    host = str(parsed.hostname or "").lower()
    if port != int(expected_port) or not _is_loopback_host(host):
        return None
    return host


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _allowed_state_path(raw_path: str, allowed_roots: list[Path]) -> Path:
    if not raw_path.strip():
        raise ValueError("state_path is required")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(root / raw).resolve() for root in roots]
    for candidate in candidates:
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError("state_path is outside the served dashboard directories")


def _allowed_path(raw_path: str, allowed_roots: list[Path], *, label: str) -> Path:
    if not raw_path.strip():
        raise ValueError(f"{label} is required")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(root / raw).resolve() for root in roots]
    for candidate in candidates:
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError(f"{label} is outside the served dashboard directories")


def _allowed_evidence_path(raw_path: str, state_path: Path, allowed_roots: list[Path]) -> Path:
    if not raw_path.strip():
        raise ValueError("evidence_url is required")
    if "://" in raw_path:
        raise ValueError("evidence composer only writes local evidence files")
    roots = [root.resolve() for root in allowed_roots]
    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(state_path.parent / raw).resolve()]
    if not raw.is_absolute():
        candidates.extend((root / raw).resolve() for root in roots)
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if any(_is_relative_to(candidate, root) for root in roots):
            return candidate
    raise ValueError("evidence_url is outside the served dashboard directories")


def _compose_evidence_markdown(
    *,
    stock_id: str,
    action_id: str,
    status: str,
    note: str,
    reviewer: str,
    evidence_summary: str,
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return "\n".join(
        [
            f"# Evidence: {stock_id} / {action_id}",
            "",
            f"- Reviewer: {reviewer}",
            f"- Status: {status}",
            f"- Generated at: {generated_at}",
            "",
            "## Review Note",
            note,
            "",
            "## Evidence Summary",
            evidence_summary,
            "",
            "## Non-Investment-Advice Notice",
            NON_ADVICE_NOTICE,
            "",
        ]
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _evidence_preview(evidence_path: Path, evidence_content: str, *, limit: int = 900) -> dict[str, Any]:
    excerpt = evidence_content.strip()
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rstrip() + "..."
    return {
        "excerpt": excerpt,
        "line_count": len(evidence_content.splitlines()),
        "path": str(evidence_path.resolve()),
    }


def _default_evidence_url(stock_id: str, action_id: str) -> str:
    return f"evidence/{_safe_slug(stock_id)}-{_safe_slug(action_id)}.md"


def _safe_slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "evidence"


def _payload_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _state_report_for_path(state_path: Path) -> dict[str, Any]:
    research_summary = state_path.with_name("research_summary.json")
    if not research_summary.exists():
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    try:
        payload = json.loads(research_summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    queue = payload.get("review_action_queue", []) if isinstance(payload, dict) else []
    state, warning = load_review_action_state(state_path)
    if warning:
        return {"by_status": {}, "last_updated": "-", "stale_count": 0}
    report = build_review_action_state_report(queue if isinstance(queue, list) else [], state)
    gate = (
        build_handoff_quality_gate(payload, state, evidence_base_dir=research_summary.parent)
        if isinstance(payload, dict)
        else {}
    )
    report["evidence_missing_count"] = gate.get("evidence_missing_count", 0)
    report["invalid_evidence_count"] = gate.get("invalid_evidence_count", 0)
    report["handoff_status"] = gate.get("status", "blocked")
    report["ready"] = bool(gate.get("ready"))
    report["blocker_count"] = gate.get("blocker_count", 0)
    report["open_count"] = gate.get("open_count", 0)
    report["next_step"] = gate.get("next_step", "")
    return report


def _load_pack_summary(summary_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("could not read generated handoff pack summary") from exc
    if not isinstance(payload, dict):
        raise ValueError("generated handoff pack summary must be a JSON object")
    return payload


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
