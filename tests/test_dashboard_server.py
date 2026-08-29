import json
import shutil
import threading
import time
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html
from taiwan_stock_analysis.dashboard_server import (
    _SlidingWindowLimiter,
    compose_evidence_from_payload,
    create_dashboard_server,
    set_review_action_status_from_payload,
    write_handoff_pack_from_payload,
)


FIXED_DASHBOARD_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class _FakeLiveService:
    def __init__(self, *, provider_mode="fixture", public_mode=False):
        self.requested_symbols = []
        self.provider_mode = provider_mode
        self.public_mode = public_mode

    def snapshot(self, symbols):
        self.requested_symbols.append(list(symbols))
        return {
            "ok": True,
            "status": "EOD",
            "quotes": [{"symbol": symbol} for symbol in symbols],
        }

    def health(self):
        return {"ok": True, "provider_mode": self.provider_mode}


class _FakeFubonLiveService(_FakeLiveService):
    def __init__(self):
        super().__init__(provider_mode="fubon")
        self.cost_requests = []

    def health(self):
        return {
            "ok": True,
            "provider_mode": "fubon",
            "provider_capacity_guarded": True,
            "provider_calls_per_minute_budget": 240,
            "minimum_client_refresh_seconds": 5,
        }

    def provider_request_cost(self, symbols):
        self.cost_requests.append(list(symbols))
        return 6


class _FakeBreadthService:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {
            "ok": True,
            "kind": "market_breadth_snapshot",
            "status": "EOD",
            "coverage": {"catalog_total": 1983, "quoted_total": 1979},
            "market_catalog": [{"symbol": "2330"}],
            "full_market": [{"symbol": "2330", "price": 2200}],
            "industry_summaries": [{"industry_name": "半導體業"}],
        }

    def health(self):
        return {
            "ok": True,
            "kind": "market_breadth_health",
            "catalog_total": 1983,
            "quoted_total": 1979,
        }


class _BlockingBreadthService(_FakeBreadthService):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def snapshot(self):
        self.started.set()
        self.release.wait(timeout=5)
        return super().snapshot()


class _FailingBreadthService(_FakeBreadthService):
    def snapshot(self):
        raise TypeError("internal fixture failure")


class _FakeUSMarketService:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return {
            "ok": True,
            "kind": "us_market_snapshot",
            "status": "REFERENCE",
            "row_count": 2,
            "rows": [
                {"symbol": "AAPL", "market": "US", "price": 210.25},
                {"symbol": "MSFT", "market": "US", "price": 510.0},
            ],
        }

    def health(self):
        return {
            "ok": self.calls > 0,
            "kind": "us_market_health",
            "status": "REFERENCE" if self.calls else "NOT_LOADED",
            "row_count": 2 if self.calls else 0,
        }


class DashboardServerTests(unittest.TestCase):
    def test_market_breadth_api_returns_full_market_payload_and_health(self):
        root = Path(".tmp-cli-test/dashboard-server-market-breadth-api")
        root.mkdir(parents=True, exist_ok=True)
        breadth_service = _FakeBreadthService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
            breadth_service=breadth_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"{url}api/market/breadth", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                cache_control = response.headers.get("Cache-Control")
            health = json.loads(_http_get_text(f"{url}api/market/health"))

            self.assertEqual("market_breadth_snapshot", payload["kind"])
            self.assertEqual(1983, payload["coverage"]["catalog_total"])
            self.assertEqual([{"symbol": "2330", "price": 2200}], payload["full_market"])
            self.assertEqual("no-store", cache_control)
            self.assertEqual("market_breadth_health", health["kind"])
            self.assertEqual(1, breadth_service.calls)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_market_breadth_refresh_is_coalesced_and_does_not_block_live_quotes(self):
        root = Path(".tmp-cli-test/dashboard-server-market-breadth-isolation")
        root.mkdir(parents=True, exist_ok=True)
        breadth_service = _BlockingBreadthService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
            breadth_service=breadth_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        first_result = {}

        def request_breadth():
            with urlopen(f"{url}api/market/breadth", timeout=5) as response:
                first_result["status"] = response.status

        request_thread = threading.Thread(target=request_breadth, daemon=True)
        request_thread.start()
        try:
            self.assertTrue(breadth_service.started.wait(timeout=2))
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{url}api/market/breadth", timeout=2)
            self.assertEqual(503, caught.exception.code)

            with urlopen(
                f"{url}api/live/snapshot?symbols=2330",
                timeout=2,
            ) as response:
                live_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual([{"symbol": "2330"}], live_payload["quotes"])
        finally:
            breadth_service.release.set()
            request_thread.join(timeout=5)
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
        self.assertEqual(200, first_result["status"])

    def test_market_breadth_exception_returns_bounded_json_error(self):
        root = Path(".tmp-cli-test/dashboard-server-market-breadth-error")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
            breadth_service=_FailingBreadthService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{url}api/market/breadth", timeout=2)
            payload = json.loads(caught.exception.read().decode("utf-8"))

            self.assertEqual(500, caught.exception.code)
            self.assertEqual(
                {"error": "market breadth snapshot failed", "ok": False},
                payload,
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_us_market_api_and_page_capability_are_available(self):
        root = Path(".tmp-cli-test/dashboard-server-us-market")
        root.mkdir(parents=True, exist_ok=True)
        us_market_service = _FakeUSMarketService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
            breadth_service=_FakeBreadthService(),
            us_market_service=us_market_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            page = _http_get_text(f"{url}dashboard.html")
            snapshot = json.loads(_http_get_text(f"{url}api/us/market"))
            health = json.loads(_http_get_text(f"{url}api/us/health"))

            self.assertIn('data-us-market-api-enabled="true"', page)
            self.assertEqual("us_market_snapshot", snapshot["kind"])
            self.assertEqual(2, snapshot["row_count"])
            self.assertEqual(["AAPL", "MSFT"], [row["symbol"] for row in snapshot["rows"]])
            self.assertTrue(health["enabled"])
            self.assertTrue(health["ok"])
            self.assertEqual(1, us_market_service.calls)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_live_api_normalizes_symbols_and_disables_http_cache(self):
        root = Path(".tmp-cli-test/dashboard-server-live-api")
        root.mkdir(parents=True, exist_ok=True)
        live_service = _FakeLiveService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=live_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"{url}api/live/snapshot?symbols=2330,2330,bad%2Fsymbol,BRK.B",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                cache_control = response.headers.get("Cache-Control")

            self.assertEqual(["2330", "BRK.B"], live_service.requested_symbols[-1])
            self.assertEqual([{"symbol": "2330"}, {"symbol": "BRK.B"}], payload["quotes"])
            self.assertEqual("no-store", cache_control)
            self.assertEqual(
                {"ok": True, "provider_mode": "fixture"},
                json.loads(_http_get_text(f"{url}api/live/health")),
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_served_dashboard_enables_live_same_origin_client_on_html_alias(self):
        root = Path(".tmp-cli-test/dashboard-server-live-page")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(f"{url}dashboard.html")
            self.assertIn('data-live-api-enabled="true"', html)
            self.assertIn("/api/live/snapshot?symbols=", html)
            self.assertIn("正在連接市場資料", html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_non_loopback_bind_keeps_live_reads_but_refuses_file_writes(self):
        root = Path(".tmp-cli-test/dashboard-server-public-read-only")
        root.mkdir(parents=True, exist_ok=True)
        server, _ = create_dashboard_server(
            [root.resolve()],
            host="0.0.0.0",
            port=0,
            live_service=_FakeLiveService(public_mode=True),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        local_url = f"http://127.0.0.1:{server.server_port}/"
        try:
            html = _http_get_text(f"{local_url}dashboard.html")
            self.assertIn('data-live-api-enabled="true"', html)
            self.assertIn('data-live-symbol-limit="20"', html)
            self.assertIn('data-live-min-refresh-seconds="30"', html)
            self.assertNotIn('data-action-api="review-action"', html)
            self.assertNotIn("data-action-api-token=", html)

            request = Request(
                f"{local_url}api/review-actions/set",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(403, caught.exception.code)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertIn("loopback", payload["error"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_public_live_api_rejects_over_cap_and_rate_limits_each_client(self):
        root = Path(".tmp-cli-test/dashboard-server-public-rate-limit")
        root.mkdir(parents=True, exist_ok=True)
        live_service = _FakeLiveService(public_mode=True)
        server, _ = create_dashboard_server(
            [root.resolve()],
            host="0.0.0.0",
            port=0,
            live_service=live_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        local_url = f"http://127.0.0.1:{server.server_port}/"
        requested = ",".join(str(1000 + index) for index in range(20))
        over_cap = requested + ",9999"
        try:
            with self.assertRaises(HTTPError) as caught:
                urlopen(
                    f"{local_url}api/live/snapshot?symbols={over_cap}",
                    timeout=5,
                )
            self.assertEqual(400, caught.exception.code)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(20, payload["symbol_limit"])
            self.assertEqual([], live_service.requested_symbols)

            for _ in range(2):
                _http_get_text(f"{local_url}api/live/snapshot?symbols={requested}")

            self.assertEqual(20, len(live_service.requested_symbols[0]))
            self.assertEqual(2, len(live_service.requested_symbols))
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{local_url}api/live/snapshot?symbols=2330", timeout=5)
            self.assertEqual(429, caught.exception.code)
            self.assertEqual("60", caught.exception.headers.get("Retry-After"))
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertFalse(payload["ok"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_public_read_only_loopback_requires_public_mode_live_service(self):
        root = Path(".tmp-cli-test/dashboard-server-public-loopback-policy")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(
            ValueError,
            "requires a public-mode live service",
        ):
            create_dashboard_server(
                [root.resolve()],
                port=0,
                public_read_only=True,
                live_service=_FakeLiveService(public_mode=False),
            )

        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            public_read_only=True,
            live_service=_FakeLiveService(public_mode=True),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(f"{url}dashboard.html")
            self.assertIn('data-live-symbol-limit="20"', html)
            self.assertNotIn("data-action-api-token=", html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_weighted_public_budget_cannot_exceed_sixty_provider_units(self):
        limiter = _SlidingWindowLimiter(max_requests=60, window_seconds=60)

        self.assertTrue(limiter.allow("licensed-provider", now=0, cost=24))
        self.assertTrue(limiter.allow("licensed-provider", now=0, cost=24))
        self.assertFalse(limiter.allow("licensed-provider", now=0, cost=13))
        self.assertTrue(limiter.allow("licensed-provider", now=61, cost=24))

    def test_loopback_fugle_uses_provider_capacity_cadence_and_budget(self):
        root = Path(".tmp-cli-test/dashboard-server-local-fugle-budget")
        root.mkdir(parents=True, exist_ok=True)
        live_service = _FakeLiveService(provider_mode="fugle")
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=live_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        requested = ",".join(str(1000 + index) for index in range(20))
        try:
            html = _http_get_text(f"{url}dashboard.html")
            self.assertIn('data-live-symbol-limit="20"', html)
            self.assertIn('data-live-min-refresh-seconds="30"', html)

            for _ in range(2):
                _http_get_text(f"{url}api/live/snapshot?symbols={requested}")
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{url}api/live/snapshot?symbols=2330", timeout=5)
            self.assertEqual(429, caught.exception.code)
            self.assertEqual("60", caught.exception.headers.get("Retry-After"))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_fubon_uses_five_second_cadence_and_fixed_bulk_cost(self):
        root = Path(".tmp-cli-test/dashboard-server-local-fubon-budget")
        root.mkdir(parents=True, exist_ok=True)
        live_service = _FakeFubonLiveService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=live_service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        requested = ",".join(str(1000 + index) for index in range(20))
        try:
            html = _http_get_text(f"{url}dashboard.html")
            self.assertIn('data-live-symbol-limit="20"', html)
            self.assertIn('data-live-min-refresh-seconds="5"', html)

            for _ in range(12):
                _http_get_text(f"{url}api/live/snapshot?symbols={requested}")
            with self.assertRaises(HTTPError) as caught:
                urlopen(f"{url}api/live/snapshot?symbols=2330", timeout=5)
            self.assertEqual(429, caught.exception.code)
            self.assertEqual("60", caught.exception.headers.get("Retry-After"))
            self.assertEqual(
                ([20] * 12) + [1],
                [len(symbols) for symbols in live_service.cost_requests],
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_live_snapshot_handler_has_a_bounded_response_deadline(self):
        root = Path(".tmp-cli-test/dashboard-server-live-deadline")
        root.mkdir(parents=True, exist_ok=True)
        live_service = _FakeLiveService()
        original_snapshot = live_service.snapshot

        def slow_snapshot(symbols):
            time.sleep(0.2)
            return original_snapshot(symbols)

        live_service.snapshot = slow_snapshot
        with patch(
            "taiwan_stock_analysis.dashboard_server._LIVE_SNAPSHOT_TIMEOUT_SECONDS",
            0.05,
        ):
            server, url = create_dashboard_server(
                [root.resolve()],
                port=0,
                live_service=live_service,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            started = time.monotonic()
            try:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(
                        f"{url}api/live/snapshot?symbols=2330",
                        timeout=1,
                    )
                elapsed = time.monotonic() - started
                self.assertEqual(504, caught.exception.code)
                self.assertEqual("15", caught.exception.headers.get("Retry-After"))
                payload = json.loads(caught.exception.read().decode("utf-8"))
                self.assertEqual("live snapshot deadline exceeded", payload["error"])
                self.assertLess(elapsed, 0.18)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_loopback_write_api_requires_application_json_to_block_simple_csrf(self):
        root = Path(".tmp-cli-test/dashboard-server-json-only")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = _mutation_token_from_html(_http_get_text(url))
            request = Request(
                f"{url}api/review-actions/set",
                data=b"{}",
                headers={
                    "Content-Type": "text/plain",
                    "X-Taiwan-Equity-Lens-Token": token,
                },
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(400, caught.exception.code)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual("Content-Type must be application/json", payload["error"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_write_api_rejects_hostile_host_and_wrong_port(self):
        root = Path(".tmp-cli-test/dashboard-server-host-guard")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = _mutation_token_from_html(_http_get_text(url))
            for hostile_host in (
                f"attacker.example:{server.server_port}",
                "127.0.0.1:1",
            ):
                request = Request(
                    f"{url}api/review-actions/set",
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "Host": hostile_host,
                        "X-Taiwan-Equity-Lens-Token": token,
                    },
                    method="POST",
                )
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request, timeout=5)
                self.assertEqual(403, caught.exception.code)
                payload = json.loads(caught.exception.read().decode("utf-8"))
                self.assertEqual("untrusted Host header", payload["error"])

            # Do not expose the mutation token through a DNS-rebound page load.
            hostile_get = Request(
                url,
                headers={"Host": f"attacker.example:{server.server_port}"},
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(hostile_get, timeout=5)
            self.assertEqual(403, caught.exception.code)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_write_api_rejects_cross_origin_request(self):
        root = Path(".tmp-cli-test/dashboard-server-origin-guard")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            token = _mutation_token_from_html(_http_get_text(url))
            request = Request(
                f"{url}api/review-actions/set",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://attacker.example",
                    "X-Taiwan-Equity-Lens-Token": token,
                },
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(403, caught.exception.code)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual("cross-origin mutation request", payload["error"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_expensive_reads_reject_cross_site_browser_requests(self):
        root = Path(".tmp-cli-test/dashboard-server-read-origin-guard")
        root.mkdir(parents=True, exist_ok=True)
        live = _FakeLiveService()
        breadth = _FakeBreadthService()
        us_market = _FakeUSMarketService()
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=live,
            breadth_service=breadth,
            us_market_service=us_market,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for endpoint in (
                "api/live/snapshot?symbols=2330",
                "api/market/breadth",
                "api/us/market",
            ):
                with self.subTest(endpoint=endpoint):
                    request = Request(
                        f"{url}{endpoint}",
                        headers={
                            "Sec-Fetch-Site": "cross-site",
                            "Referer": "https://attacker.example/drive-by",
                        },
                    )
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=5)
                    self.assertEqual(403, caught.exception.code)
                    payload = json.loads(caught.exception.read().decode("utf-8"))
                    self.assertEqual("cross-site data request", payload["error"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual([], live.requested_symbols)
        self.assertEqual(0, breadth.calls)
        self.assertEqual(0, us_market.calls)

    def test_loopback_write_api_rejects_missing_mutation_token(self):
        root = Path(".tmp-cli-test/dashboard-server-token-required")
        root.mkdir(parents=True, exist_ok=True)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"{url}api/review-actions/set",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(403, caught.exception.code)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual("invalid mutation token", payload["error"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_loopback_write_api_accepts_same_origin_request_with_session_token(self):
        root = Path(".tmp-cli-test/dashboard-server-token-valid")
        _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            live_service=_FakeLiveService(),
            clock=lambda: FIXED_DASHBOARD_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(url)
            token = _mutation_token_from_html(html)
            self.assertGreaterEqual(len(token), 43)
            self.assertIn('"X-Taiwan-Equity-Lens-Token": mutationToken', html)

            body = json.dumps(
                {
                    "state_path": "review_action_state.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "done",
                    "note": "checked source filing",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source.md",
                }
            ).encode("utf-8")
            request = Request(
                f"{url}api/review-actions/set",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": url.rstrip("/"),
                    "X-Taiwan-Equity-Lens-Token": token,
                },
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual("done", payload["status"])
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_sector_evidence_board_done_button_payload_updates_state(self):
        root = Path(".tmp-cli-test/dashboard-server-sector-evidence")
        state_path = _write_sector_evidence_fixture(root)

        html = render_dashboard_html(discover_dashboard_items([root.resolve()]), action_api_enabled=True)
        button = _find_button_by_text(html, "標記完成")

        result = set_review_action_status_from_payload(
            {
                "state_path": button["data-state-path"],
                "stock_id": button["data-stock"],
                "action_id": button["data-action-id"],
                "status": button["data-status"],
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root.resolve()],
        )

        self.assertTrue(result["ok"])
        self.assertEqual("done", result["status"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertEqual(0, result["invalid_evidence_count"])
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        action = payload["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("done", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

        # NOTE: the old sector evidence board (data-industry-evidence-status) is
        # gone -- merged into the unified queue per design spec §3.5. Re-render and
        # confirm the queue row + gate card reflect the state change instead.
        updated_html = render_dashboard_html(discover_dashboard_items([root.resolve()]), action_api_enabled=True)
        self.assertIn('data-status="done"', updated_html)
        self.assertIn('<span class="ui-badge ui-badge-ok">已完成</span>', updated_html)
        self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', updated_html)
        self.assertIn('<strong id="wb-gate-blockers">0</strong>', updated_html)

    def test_served_dashboard_http_updates_sector_evidence_state(self):
        root = Path(".tmp-cli-test/dashboard-server-sector-evidence-http")
        state_path = _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            clock=lambda: FIXED_DASHBOARD_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(url)
            self.assertIn('class="queue-row next"', html)
            self.assertIn('data-action-api="review-action"', html)
            button = _find_button_by_text(html, "標記完成")

            result = _http_post_json(
                f"{url}api/review-actions/set",
                {
                    "state_path": button["data-state-path"],
                    "stock_id": button["data-stock"],
                    "action_id": button["data-action-id"],
                    "status": button["data-status"],
                    "note": "checked source filing",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source.md",
                },
                token=_mutation_token_from_html(html),
            )

            self.assertTrue(result["ok"])
            self.assertEqual("done", result["status"])
            self.assertEqual(0, result["evidence_missing_count"])
            self.assertEqual(0, result["invalid_evidence_count"])
            action = json.loads(state_path.read_text(encoding="utf-8"))["actions"][
                "2330:source-audit-manual-review"
            ]
            self.assertEqual("done", action["status"])
            self.assertEqual("checked source filing", action["note"])
            self.assertEqual("source-audit-lead", action["reviewer"])
            self.assertEqual("evidence/2330-source.md", action["evidence_url"])

            # NOTE: the old sector evidence board (data-industry-evidence-status) is
            # gone -- merged into the unified queue per design spec §3.5.
            updated_html = _http_get_text(url)
            self.assertIn('data-status="done"', updated_html)
            self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', updated_html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_served_dashboard_http_guided_next_action_workbench_updates_gate(self):
        root = Path(".tmp-cli-test/dashboard-server-next-action-http")
        _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            clock=lambda: FIXED_DASHBOARD_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(url)
            self.assertIn('class="queue-row next"', html)
            self.assertIn("處理建議下一步", html)
            button = _find_button_by_text(html, "標記完成")

            result = _http_post_json(
                f"{url}api/review-actions/set",
                {
                    "state_path": button["data-state-path"],
                    "stock_id": button["data-stock"],
                    "action_id": button["data-action-id"],
                    "status": button["data-status"],
                    "note": "checked source filing",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source.md",
                },
                token=_mutation_token_from_html(html),
            )

            self.assertTrue(result["ok"])
            self.assertEqual("done", result["status"])
            self.assertEqual("ready", result["handoff_status"])
            self.assertTrue(result["ready"])
            self.assertEqual(0, result["blocker_count"])
            self.assertEqual(0, result["open_count"])
            self.assertIn("人工閱讀", result["next_step"])

            # NOTE: the old dedicated "next action workbench" widget
            # (data-next-action-*) is merged into the unified queue's gate card
            # per design spec §3.5 -- same blocker math, different markup.
            updated_html = _http_get_text(url)
            self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', updated_html)
            self.assertIn('<strong id="wb-gate-blockers">0</strong>', updated_html)
            self.assertIn("產出 Evidence Pack", updated_html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_compose_evidence_from_payload_writes_stub_and_updates_state(self):
        root = Path(".tmp-cli-test/dashboard-server-evidence-composer")
        state_path = _write_sector_evidence_fixture(root)
        evidence_path = root / "evidence" / "2330-source-audit-manual-review.md"

        result = compose_evidence_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "Checked fixture source freshness, source mode, and the manual-review reason before handoff.",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source-audit-manual-review.md",
                "evidence_summary": "The fixture source remains acceptable for this demo handoff because the manual source-audit reason was inspected and documented.",
                "overwrite": True,
            },
            allowed_roots=[root.resolve()],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["evidence_created"])
        self.assertEqual(str(evidence_path.resolve()), result["evidence_path"])
        self.assertEqual("evidence/2330-source-audit-manual-review.md", result["evidence_url"])
        self.assertEqual("done", result["status"])
        self.assertTrue(result["ready"])
        self.assertEqual("ready", result["handoff_status"])
        self.assertEqual(0, result["blocker_count"])
        self.assertEqual(0, result["open_count"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertEqual("handoff_ready", result["evidence_quality"]["status"])
        self.assertTrue(result["evidence_quality"]["ready"])
        self.assertIn("Evidence:", result["evidence_preview"]["excerpt"])
        self.assertEqual(str(evidence_path.resolve()), result["evidence_preview"]["path"])
        self.assertTrue(evidence_path.exists())
        content = evidence_path.read_text(encoding="utf-8")
        self.assertIn("# Evidence: 2330 / source-audit-manual-review", content)
        self.assertIn("Reviewer: source-audit-lead", content)
        self.assertIn("Checked fixture source freshness", content)
        self.assertIn("The fixture source remains acceptable", content)
        self.assertIn("不構成投資建議", content)
        action = json.loads(state_path.read_text(encoding="utf-8"))["actions"][
            "2330:source-audit-manual-review"
        ]
        self.assertEqual("done", action["status"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source-audit-manual-review.md", action["evidence_url"])

    def test_compose_evidence_from_payload_flags_low_confidence_stub(self):
        root = Path(".tmp-cli-test/dashboard-server-evidence-composer-quality")
        _write_sector_evidence_fixture(root)

        result = compose_evidence_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "Reviewed handoff blocker: Review source audit before handoff.",
                "reviewer": "handoff-reviewer",
                "evidence_url": "evidence/2330-source-audit-manual-review.md",
                "evidence_summary": "Review source audit before handoff.",
                "overwrite": True,
            },
            allowed_roots=[root.resolve()],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready"])
        self.assertEqual("needs_review", result["evidence_quality"]["status"])
        self.assertFalse(result["evidence_quality"]["ready"])
        issue_ids = {issue["id"] for issue in result["evidence_quality"]["issues"]}
        self.assertIn("reviewer_named", issue_ids)
        self.assertIn("note_specific", issue_ids)
        self.assertIn("summary_specific", issue_ids)

    def test_served_dashboard_http_composes_evidence_and_updates_gate(self):
        root = Path(".tmp-cli-test/dashboard-server-evidence-composer-http")
        _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            clock=lambda: FIXED_DASHBOARD_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # This exercises the /api/evidence/compose-and-set route directly
            # (no markup dependency) as a lower-level contract check --
            # test_served_dashboard_http_evidence_compose_button_creates_file_and_updates_gate
            # below drives the same endpoint through the actual rendered
            # queue-row button (data-evidence-compose, restored in
            # views/workbench.py after the redesign migration dropped it).
            html = _http_get_text(url)
            self.assertIn('class="queue-row next"', html)

            result = _http_post_json(
                f"{url}api/evidence/compose-and-set",
                {
                    "state_path": "review_action_state.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "done",
                    "note": "checked source filing",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source-audit-manual-review.md",
                    "evidence_summary": "Source audit reviewed from the dashboard evidence composer.",
                    "overwrite": True,
                },
                token=_mutation_token_from_html(html),
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["evidence_created"])
            self.assertEqual("ready", result["handoff_status"])
            self.assertTrue(result["ready"])
            self.assertEqual(0, result["blocker_count"])
            self.assertIn("evidence_quality", result)
            self.assertIn("evidence_preview", result)
            self.assertTrue((root / "evidence" / "2330-source-audit-manual-review.md").exists())

            updated_html = _http_get_text(url)
            self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', updated_html)
            self.assertIn("evidence/2330-source-audit-manual-review.md", updated_html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_served_dashboard_http_evidence_compose_button_creates_file_and_updates_gate(self):
        # Restores the served-mode client for compose_evidence_from_payload
        # (spec Â§10 "è­‰æ“šå»ºç«‹å™¨"): discovers the *actual* rendered compose-and-set
        # button (mirroring test_sector_evidence_board_done_button_payload_updates_state's
        # button-driven pattern above) instead of posting to the endpoint
        # blind, proving the queue row's new markup + JS actually reach this
        # unchanged server route end to end.
        root = Path(".tmp-cli-test/dashboard-server-evidence-compose-button")
        state_path = _write_sector_evidence_fixture(root)
        server, url = create_dashboard_server(
            [root.resolve()],
            port=0,
            clock=lambda: FIXED_DASHBOARD_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            html = _http_get_text(url)
            self.assertIn('data-evidence-compose="true"', html)
            self.assertIn('data-evidence-compose-summary="true"', html)
            button = _find_button_by_text(html, "建立證據並標記完成")
            self.assertEqual("done", button["data-status"])
            self.assertEqual("2330", button["data-stock"])
            self.assertEqual("source-audit-manual-review", button["data-action-id"])

            result = _http_post_json(
                f"{url}api/evidence/compose-and-set",
                {
                    "state_path": button["data-state-path"],
                    "stock_id": button["data-stock"],
                    "action_id": button["data-action-id"],
                    "status": button["data-status"],
                    "note": "checked source filing from the restored composer button",
                    "reviewer": "source-audit-lead",
                    "evidence_url": "evidence/2330-source-audit-manual-review.md",
                    "evidence_summary": "Source audit reviewed from the restored dashboard evidence composer button.",
                    "overwrite": True,
                },
                token=_mutation_token_from_html(html),
            )

            self.assertTrue(result["ok"])
            self.assertTrue(result["evidence_created"])
            self.assertEqual("done", result["status"])
            self.assertIn("status", result["evidence_quality"])
            self.assertIn("excerpt", result["evidence_preview"])
            self.assertIn("blocker_count", result)
            self.assertIn("by_status", result)
            self.assertEqual(0, result["blocker_count"])
            self.assertTrue(result["ready"])

            evidence_path = root / "evidence" / "2330-source-audit-manual-review.md"
            self.assertTrue(evidence_path.exists())
            content = evidence_path.read_text(encoding="utf-8")
            self.assertIn("# Evidence: 2330 / source-audit-manual-review", content)

            action = json.loads(state_path.read_text(encoding="utf-8"))["actions"]["2330:source-audit-manual-review"]
            self.assertEqual("done", action["status"])
            self.assertEqual("source-audit-lead", action["reviewer"])

            updated_html = _http_get_text(url)
            self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', updated_html)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_set_review_action_status_from_payload_writes_state(self):
        root = Path(".tmp-cli-test/dashboard-server-api")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        (root / "research_summary.json").write_text(
            json.dumps(
                {
                    "review_action_queue": [
                        {
                            "stock_id": "2330",
                            "priority": "high",
                            "actions": [
                                {"id": "source-audit-manual-review", "status": "open"},
                                {"id": "reliability-warning", "status": "open"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root],
        )

        self.assertTrue(result["ok"])
        self.assertEqual("done", result["status"])
        self.assertEqual({"open": 1, "done": 1, "deferred": 0, "ignored": 0}, result["by_status"])
        self.assertEqual("checked source filing", result["note"])
        self.assertEqual("source-audit-lead", result["reviewer"])
        self.assertEqual("evidence/2330-source.md", result["evidence_url"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertEqual(1, result["invalid_evidence_count"])
        self.assertEqual(0, result["stale_count"])
        self.assertNotEqual("-", result["last_updated"])
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        action = payload["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("2330", action["stock_id"])
        self.assertEqual("source-audit-manual-review", action["action_id"])
        self.assertEqual("done", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

    def test_set_review_action_status_from_payload_status_only_preserves_evidence(self):
        # CRITICAL fix regression test: reproduces the reviewer's finding.
        # 1) set with full evidence -> gate ready.
        # 2) status-only update (mirrors bulk, which never sends note/reviewer/
        #    evidence_url) -> evidence must stay intact and the gate must NOT
        #    flip back to blocked.
        root = Path(".tmp-cli-test/dashboard-server-preserve-evidence")
        state_path = _write_sector_evidence_fixture(root)

        first = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root.resolve()],
        )
        self.assertTrue(first["ready"])
        self.assertEqual(0, first["blocker_count"])

        second = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "deferred",
            },
            allowed_roots=[root.resolve()],
        )

        self.assertTrue(second["ok"])
        self.assertEqual("deferred", second["status"])
        self.assertEqual("checked source filing", second["note"])
        self.assertEqual("source-audit-lead", second["reviewer"])
        self.assertEqual("evidence/2330-source.md", second["evidence_url"])
        self.assertEqual(0, second["evidence_missing_count"])
        self.assertTrue(second["ready"])
        self.assertEqual(0, second["blocker_count"])

        action = json.loads(state_path.read_text(encoding="utf-8"))["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("deferred", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

    def test_set_review_action_status_from_payload_with_keys_overwrites_evidence(self):
        # The other half of the merge-semantics contract: WITH the keys present
        # (even to different values), the payload always writes them -- single-
        # row updates always send typed fields, so they must still be able to
        # correct/replace previously stored evidence.
        root = Path(".tmp-cli-test/dashboard-server-overwrite-evidence")
        state_path = _write_sector_evidence_fixture(root)

        set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root.resolve()],
        )

        updated = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "re-reviewed after amended filing",
                "reviewer": "second-reviewer",
                "evidence_url": "evidence/2330-source-v2.md",
            },
            allowed_roots=[root.resolve()],
        )

        self.assertEqual("re-reviewed after amended filing", updated["note"])
        self.assertEqual("second-reviewer", updated["reviewer"])
        self.assertEqual("evidence/2330-source-v2.md", updated["evidence_url"])
        action = json.loads(state_path.read_text(encoding="utf-8"))["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("re-reviewed after amended filing", action["note"])
        self.assertEqual("second-reviewer", action["reviewer"])
        self.assertEqual("evidence/2330-source-v2.md", action["evidence_url"])

    def test_set_review_action_status_from_payload_json_null_preserves_evidence(self):
        # A client sending {"note": null} (JSON null, decoded to Python None)
        # has the KEY PRESENT -- "note" in payload is True -- so it must be
        # treated the same as the key being absent (preserve), not as an
        # explicit value. Before this fix, str(payload["note"]) on a None
        # value wrote the literal string "None" over real evidence.
        root = Path(".tmp-cli-test/dashboard-server-json-null-evidence")
        state_path = _write_sector_evidence_fixture(root)

        set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "done",
                "note": "checked source filing",
                "reviewer": "source-audit-lead",
                "evidence_url": "evidence/2330-source.md",
            },
            allowed_roots=[root.resolve()],
        )

        result = set_review_action_status_from_payload(
            {
                "state_path": "review_action_state.json",
                "stock_id": "2330",
                "action_id": "source-audit-manual-review",
                "status": "deferred",
                "note": None,
                "reviewer": None,
                "evidence_url": None,
            },
            allowed_roots=[root.resolve()],
        )

        self.assertEqual("checked source filing", result["note"])
        self.assertEqual("source-audit-lead", result["reviewer"])
        self.assertEqual("evidence/2330-source.md", result["evidence_url"])
        action = json.loads(state_path.read_text(encoding="utf-8"))["actions"]["2330:source-audit-manual-review"]
        self.assertEqual("deferred", action["status"])
        self.assertEqual("checked source filing", action["note"])
        self.assertNotEqual("None", action["note"])
        self.assertEqual("source-audit-lead", action["reviewer"])
        self.assertEqual("evidence/2330-source.md", action["evidence_url"])

    def test_set_review_action_status_from_payload_rejects_outside_state_path(self):
        root = Path(".tmp-cli-test/dashboard-server-api-safe")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "outside the served dashboard directories"):
            set_review_action_status_from_payload(
                {
                    "state_path": "../outside.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "done",
                },
                allowed_roots=[root],
            )

    def test_set_review_action_status_from_payload_rejects_invalid_status(self):
        root = Path(".tmp-cli-test/dashboard-server-api-invalid")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "invalid review action status"):
            set_review_action_status_from_payload(
                {
                    "state_path": "review_action_state.json",
                    "stock_id": "2330",
                    "action_id": "source-audit-manual-review",
                    "status": "bad",
                },
                allowed_roots=[root],
            )

    def test_write_handoff_pack_from_payload_writes_outputs(self):
        root = Path(".tmp-cli-test/dashboard-server-handoff-pack")
        root.mkdir(parents=True, exist_ok=True)
        (root / "evidence").mkdir(exist_ok=True)
        (root / "evidence" / "2330-reliability.md").write_text("checked", encoding="utf-8")
        (root / "research_summary.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "stock_id": "2330",
                            "company_name": "TSMC",
                            "priority": "high",
                            "research_state": "watching",
                            "thesis": "Leading foundry scale",
                            "follow_up_questions": "Are assumptions current?",
                            "workflow_status": "ok",
                            "reliability_status": "warning",
                            "source_audit_status": "fresh",
                            "attention_reasons": ["data reliability is warning"],
                        }
                    ],
                    "review_action_queue": [
                        {
                            "stock_id": "2330",
                            "company_name": "TSMC",
                            "priority": "high",
                            "actions": [
                                {
                                    "id": "reliability-warning",
                                    "category": "reliability",
                                    "severity": "warning",
                                    "message": "Inspect data reliability warning before handoff.",
                                    "status": "open",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "review_action_state.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": {
                        "2330:reliability-warning": {
                            "stock_id": "2330",
                            "action_id": "reliability-warning",
                            "status": "done",
                            "note": "checked reliability warning",
                            "reviewer": "handoff-lead",
                            "evidence_url": "evidence/2330-reliability.md",
                            "updated_at": "2026-05-20T01:00:00Z",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = write_handoff_pack_from_payload(
            {
                "research_summary_path": "research_summary.json",
                "state_path": "review_action_state.json",
                "output_dir": "handoff-pack",
            },
            allowed_roots=[root],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["ready"])
        self.assertEqual("ready", result["gate_status"])
        self.assertEqual(0, result["evidence_missing_count"])
        self.assertTrue((root / "handoff-pack" / "handoff-pack.md").exists())
        self.assertTrue((root / "handoff-pack" / "handoff-pack.html").exists())
        self.assertEqual(str(root.resolve() / "handoff-pack" / "handoff_pack_summary.json"), result["summary_path"])

    def test_write_handoff_pack_from_payload_rejects_outside_output_dir(self):
        root = Path(".tmp-cli-test/dashboard-server-handoff-pack-safe")
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "outside the served dashboard directories"):
            write_handoff_pack_from_payload(
                {
                    "research_summary_path": "research_summary.json",
                    "output_dir": "../outside-pack",
                },
                allowed_roots=[root],
            )


def _write_sector_evidence_fixture(root: Path) -> Path:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(exist_ok=True)
    (root / "evidence" / "2330-source.md").write_text("checked source audit", encoding="utf-8")
    state_path = root / "review_action_state.json"
    (root / "research_summary.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "source": "TWSE",
                    "status": "EOD",
                    "observed_at": FIXED_DASHBOARD_NOW.isoformat(),
                },
                "review_action_queue": [
                    {
                        "stock_id": "2330",
                        "company_name": "TSMC",
                        "priority": "high",
                        "actions": [
                            {
                                "id": "source-audit-manual-review",
                                "category": "source_audit",
                                "severity": "manual_review",
                                "message": "Review source audit before handoff.",
                                "status": "open",
                            }
                        ],
                    }
                ],
                "items": [
                    {
                        "stock_id": "2330",
                        "company_name": "TSMC",
                        "category": "Semiconductor",
                        "priority": "high",
                        "research_state": "watching",
                        "workflow_status": "ok",
                        "reliability_status": "ok",
                        "source_audit_status": "manual_review",
                        "attention_reasons": ["source audit requires handoff evidence"],
                        "thesis": "foundry scale requires source freshness review",
                        "follow_up_questions": "confirm source freshness before handoff",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return state_path


class _ButtonTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[tuple[dict[str, str], str]] = []
        self._attrs: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            self._attrs = {key: value or "" for key, value in attrs}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._attrs is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._attrs is not None:
            self.buttons.append((self._attrs, "".join(self._text).strip()))
            self._attrs = None
            self._text = []


def _find_button_by_text(html: str, text: str) -> dict[str, str]:
    parser = _ButtonTextParser()
    parser.feed(html)
    for attrs, button_text in parser.buttons:
        if button_text == text:
            return attrs
    raise AssertionError(f"button not found: {text}")


def _http_get_text(url: str) -> str:
    with urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def _mutation_token_from_html(html: str) -> str:
    marker = 'data-action-api-token="'
    start = html.find(marker)
    if start < 0:
        raise AssertionError("dashboard mutation token is missing")
    start += len(marker)
    end = html.find('"', start)
    if end < 0:
        raise AssertionError("dashboard mutation token is malformed")
    token = html[start:end]
    if not token:
        raise AssertionError("dashboard mutation token is empty")
    return token


def _http_post_json(
    url: str,
    payload: dict[str, object],
    *,
    token: str,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Taiwan-Equity-Lens-Token": token,
        },
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise AssertionError("JSON response must be an object")
    return result


if __name__ == "__main__":
    unittest.main()
