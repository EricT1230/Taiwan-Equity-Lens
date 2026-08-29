import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from taiwan_stock_analysis.dashboard_server import create_dashboard_server


FIXED_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class _SwitchingLiveService:
    public_mode = False
    provider_mode = "fubon"

    def __init__(self):
        self.fail = False
        self.forces = []
        self.called = threading.Event()

    def health(self):
        return {
            "ok": True,
            "provider_mode": "fubon",
            "provider_capacity_guarded": True,
            "provider_calls_per_minute_budget": 240,
            "minimum_client_refresh_seconds": 5,
        }

    def provider_request_cost(self, _symbols):
        return 1

    def snapshot(self, symbols, *, force=False):
        self.forces.append(bool(force))
        self.called.set()
        if self.fail:
            raise TimeoutError("licensed provider timeout")
        return {
            "schema_version": 1,
            "kind": "live_market_snapshot",
            "ok": True,
            "quotes_ok": True,
            "generated_at": "2026-08-28T13:30:00+08:00",
            "status": "EOD",
            "provider": {"id": "fubon-rest", "source": "Fubon"},
            "market": {
                "status": "EOD",
                "as_of": "2026-08-28T13:30:00+08:00",
            },
            "quotes": [
                {
                    "symbol": symbol,
                    "status": "EOD",
                    "price": 2420,
                    "source": "Fubon",
                    "source_event_time": "2026-08-28T13:30:00+08:00",
                }
                for symbol in symbols
            ],
            "indices": [
                {
                    "symbol": "t00",
                    "status": "EOD",
                    "price": 46331.45,
                    "source": "Fubon",
                    "source_event_time": "2026-08-28T13:30:00+08:00",
                },
                {
                    "symbol": "o00",
                    "status": "EOD",
                    "price": 402.83,
                    "source": "Fubon",
                    "source_event_time": "2026-08-28T13:30:00+08:00",
                },
            ],
            "missing_symbols": [],
            "source_status": {
                "quotes": {
                    "id": "fubon-rest",
                    "source": "Fubon",
                    "status": "EOD",
                    "fetched_at": "2026-08-28T13:30:00+08:00",
                    "fallback": False,
                }
            },
        }


class _SwitchingBreadthService:
    def __init__(self):
        self.fail = False
        self.forces = []
        self.called = threading.Event()

    def health(self):
        return {"ok": True, "kind": "market_breadth_health"}

    def snapshot(self, *, force=False):
        self.forces.append(bool(force))
        self.called.set()
        if self.fail:
            raise RuntimeError("official breadth unavailable")
        return {
            "schema_version": 1,
            "kind": "market_breadth_snapshot",
            "ok": True,
            "generated_at": "2026-08-28T13:30:00+08:00",
            "status": "PARTIAL",
            "mode": "EOD_PARTIAL+LIVE_PAGE",
            "session_fresh": True,
            "live_session_fresh": False,
            "coverage": {
                "catalog_total": 1,
                "quoted_total": 1,
                "ratio": 1.0,
            },
            "full_market": [
                {
                    "symbol": "2330",
                    "market": "TWSE",
                    "quote_status": "EOD",
                    "session_date": "2026-08-28",
                    "quote_source": "TWSE official daily quotes",
                }
            ],
            "source_status": {
                "catalog": {
                    "id": "twse-catalog",
                    "source": "TWSE official catalog",
                    "status": "FRESH",
                },
                "quotes": {
                    "id": "twse-quotes",
                    "source": "TWSE official daily quotes",
                    "status": "EOD",
                },
            },
        }


class _USMarketService:
    def health(self):
        return {"ok": False, "status": "NOT_LOADED"}


class DashboardServerProductionModeTests(unittest.TestCase):
    def _start_server(
        self,
        root,
        *,
        live=None,
        breadth=None,
        cache_root=None,
        startup_refresh=False,
    ):
        server, url = create_dashboard_server(
            [Path(root).resolve()],
            port=0,
            live_service=live or _SwitchingLiveService(),
            breadth_service=breadth or _SwitchingBreadthService(),
            us_market_service=_USMarketService(),
            official_snapshot_root=cache_root,
            startup_refresh=startup_refresh,
            clock=lambda: FIXED_NOW,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, url

    def test_root_is_production_and_demo_is_explicit_read_only_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rendered = []

            def fake_render(_items, **kwargs):
                rendered.append(kwargs)
                mode = kwargs["data_mode"]
                return f'<html><body data-data-mode="{mode}">{mode}</body></html>'

            with patch(
                "taiwan_stock_analysis.dashboard_server.render_dashboard_html",
                side_effect=fake_render,
            ):
                server, thread, url = self._start_server(temp_dir)
                try:
                    production = urlopen(url, timeout=3).read().decode("utf-8")
                    demo = urlopen(f"{url}demo", timeout=3).read().decode("utf-8")
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
                    server.server_close()

        self.assertIn('data-data-mode="production"', production)
        self.assertIn('data-data-mode="demo"', demo)
        self.assertIn("data-action-api-token=", production)
        self.assertNotIn("data-action-api-token=", demo)
        self.assertTrue(rendered[0]["live_api_enabled"])
        self.assertFalse(rendered[1]["live_api_enabled"])
        self.assertFalse(rendered[1]["action_api_enabled"])
        self.assertEqual(FIXED_NOW, rendered[0]["now"])
        self.assertEqual(FIXED_NOW, rendered[1]["now"])

    def test_dashboard_clock_must_be_timezone_aware(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                create_dashboard_server(
                    [Path(temp_dir).resolve()],
                    port=0,
                    live_service=_SwitchingLiveService(),
                    breadth_service=_SwitchingBreadthService(),
                    us_market_service=_USMarketService(),
                    clock=lambda: datetime(2026, 8, 28, 12, 0),
                )

    def test_real_http_discovery_admission_and_render_separate_production_from_demo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official_dir = root / "official"
            demo_dir = root / "DEMO_SENTINEL_PATH"
            official_dir.mkdir()
            demo_dir.mkdir()
            (official_dir / "market_intelligence_report.json").write_text(
                json.dumps(
                    {
                        "kind": "market_intelligence_report",
                        "provenance": {
                            "source": "TWSE",
                            "status": "EOD",
                            "observed_at": "2026-08-28T06:00:00Z",
                        },
                        "news": [
                            {
                                "title": "OFFICIAL_SENTINEL_NEWS",
                                "source": "TWSE",
                                "published_at": "2026-08-28T05:00:00Z",
                                "url": "https://www.twse.com.tw/OFFICIAL_SENTINEL_URL",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (demo_dir / "market_intelligence_report.json").write_text(
                json.dumps(
                    {
                        "kind": "market_intelligence_report",
                        "provenance": {
                            "source": "TWSE",
                            "status": "EOD",
                            "observed_at": "2026-08-28T06:00:00Z",
                        },
                        "news": [
                            {
                                "title": "DEMO_SENTINEL_NEWS",
                                "source": "synthetic-demo",
                                "source_mode": "fixture",
                                "published_at": "2026-08-28T05:00:00Z",
                                "url": "https://example.com/DEMO_SENTINEL_URL",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            server, url = create_dashboard_server(
                [demo_dir, official_dir],
                port=0,
                live_service=_SwitchingLiveService(),
                breadth_service=_SwitchingBreadthService(),
                us_market_service=_USMarketService(),
                clock=lambda: FIXED_NOW,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                production = urlopen(url, timeout=3).read().decode("utf-8")
                demo = urlopen(f"{url}demo", timeout=3).read().decode("utf-8")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertIn("OFFICIAL_SENTINEL_NEWS", production)
        self.assertNotIn("DEMO_SENTINEL_NEWS", production)
        self.assertNotIn("DEMO_SENTINEL_PATH", production)
        self.assertNotIn("DEMO_SENTINEL_URL", production)
        self.assertIn('data-data-mode="demo"', demo)
        self.assertIn("Demo 模式", demo)
        self.assertIn("DEMO_SENTINEL_NEWS", demo)
        self.assertIn("DEMO_SENTINEL_PATH", demo)
        self.assertIn("DEMO_SENTINEL_URL", demo)

    def test_live_api_serves_persisted_official_snapshot_only_as_stale(self):
        live = _SwitchingLiveService()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server, thread, url = self._start_server(
                root,
                live=live,
                cache_root=root / "official-cache",
            )
            try:
                first = json.loads(
                    urlopen(
                        f"{url}api/live/snapshot?symbols=2330",
                        timeout=3,
                    ).read()
                )
                cache_files = list((root / "official-cache").glob("*.json"))
                self.assertEqual(1, len(cache_files))
                cache_saved_at = json.loads(
                    cache_files[0].read_text(encoding="utf-8")
                )["saved_at"]
                live.fail = True
                fallback = json.loads(
                    urlopen(
                        f"{url}api/live/snapshot?symbols=2330",
                        timeout=3,
                    ).read()
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual("EOD", first["status"])
        self.assertEqual(FIXED_NOW.isoformat(), cache_saved_at)
        self.assertEqual("STALE", fallback["status"])
        self.assertFalse(fallback["quotes_ok"])
        self.assertTrue(fallback["cache"]["fallback"])

    def test_breadth_api_serves_persisted_official_snapshot_only_as_stale(self):
        breadth = _SwitchingBreadthService()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server, thread, url = self._start_server(
                root,
                breadth=breadth,
                cache_root=root / "official-cache",
            )
            try:
                first = json.loads(
                    urlopen(f"{url}api/market/breadth", timeout=3).read()
                )
                breadth.fail = True
                fallback = json.loads(
                    urlopen(f"{url}api/market/breadth", timeout=3).read()
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual("PARTIAL", first["status"])
        self.assertEqual("STALE", fallback["status"])
        self.assertEqual("STALE_FALLBACK+LIVE_PAGE", fallback["mode"])
        self.assertTrue(fallback["cache"]["fallback"])

    def test_manual_breadth_refresh_reaches_service_as_force(self):
        breadth = _SwitchingBreadthService()
        with tempfile.TemporaryDirectory() as temp_dir:
            server, thread, url = self._start_server(temp_dir, breadth=breadth)
            try:
                token = _mutation_token(url)
                _post_json(
                    f"{url}api/market/breadth/refresh",
                    {},
                    token=token,
                    origin=url.rstrip("/"),
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([True], breadth.forces)

    def test_manual_live_refresh_reaches_service_as_force(self):
        live = _SwitchingLiveService()
        with tempfile.TemporaryDirectory() as temp_dir:
            server, thread, url = self._start_server(temp_dir, live=live)
            try:
                token = _mutation_token(url)
                _post_json(
                    f"{url}api/live/snapshot/refresh",
                    {"symbols": ["2330"]},
                    token=token,
                    origin=url.rstrip("/"),
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([True], live.forces)

    def test_manual_live_refresh_preserves_validated_stale_cache_fallback(self):
        live = _SwitchingLiveService()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server, thread, url = self._start_server(
                root,
                live=live,
                cache_root=root / "official-cache",
            )
            try:
                token = _mutation_token(url)
                first = _post_json(
                    f"{url}api/live/snapshot/refresh",
                    {"symbols": ["2330"]},
                    token=token,
                    origin=url.rstrip("/"),
                )
                live.fail = True
                fallback = _post_json(
                    f"{url}api/live/snapshot/refresh",
                    {"symbols": ["2330"]},
                    token=token,
                    origin=url.rstrip("/"),
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual("EOD", first["status"])
        self.assertEqual("STALE", fallback["status"])
        self.assertFalse(fallback["quotes_ok"])
        self.assertEqual([True, True], live.forces)

    def test_manual_live_refresh_keeps_the_provider_symbol_cap(self):
        live = _SwitchingLiveService()
        with tempfile.TemporaryDirectory() as temp_dir:
            server, thread, url = self._start_server(temp_dir, live=live)
            try:
                token = _mutation_token(url)
                with self.assertRaises(HTTPError) as caught:
                    _post_json(
                        f"{url}api/live/snapshot/refresh",
                        {"symbols": [f"S{index:02d}" for index in range(41)]},
                        token=token,
                        origin=url.rstrip("/"),
                    )
                self.assertEqual(400, caught.exception.code)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([], live.forces)

    def test_get_force_query_is_treated_as_an_ordinary_read(self):
        live = _SwitchingLiveService()
        breadth = _SwitchingBreadthService()
        with tempfile.TemporaryDirectory() as temp_dir:
            server, thread, url = self._start_server(
                temp_dir,
                live=live,
                breadth=breadth,
            )
            try:
                urlopen(f"{url}api/market/breadth?force=1", timeout=3).read()
                urlopen(
                    f"{url}api/live/snapshot?symbols=2330&force=1",
                    timeout=3,
                ).read()
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([False], breadth.forces)
        self.assertEqual([False], live.forces)

    def test_refresh_posts_reject_missing_token_hostile_origin_and_host(self):
        live = _SwitchingLiveService()
        breadth = _SwitchingBreadthService()
        with tempfile.TemporaryDirectory() as temp_dir:
            server, thread, url = self._start_server(
                temp_dir,
                live=live,
                breadth=breadth,
            )
            try:
                token = _mutation_token(url)
                cases = (
                    ("api/market/breadth/refresh", {}),
                    ("api/live/snapshot/refresh", {"symbols": ["2330"]}),
                )
                for path, payload in cases:
                    with self.subTest(path=path, guard="missing-token"):
                        with self.assertRaises(HTTPError) as caught:
                            _post_json(f"{url}{path}", payload, token="")
                        self.assertEqual(403, caught.exception.code)
                    with self.subTest(path=path, guard="hostile-origin"):
                        with self.assertRaises(HTTPError) as caught:
                            _post_json(
                                f"{url}{path}",
                                payload,
                                token=token,
                                origin="https://attacker.example",
                            )
                        self.assertEqual(403, caught.exception.code)
                    with self.subTest(path=path, guard="hostile-host"):
                        with self.assertRaises(HTTPError) as caught:
                            _post_json(
                                f"{url}{path}",
                                payload,
                                token=token,
                                host=f"attacker.example:{server.server_port}",
                            )
                        self.assertEqual(403, caught.exception.code)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([], breadth.forces)
        self.assertEqual([], live.forces)

    def test_startup_refresh_warms_live_and_breadth_without_a_browser_request(self):
        live = _SwitchingLiveService()
        breadth = _SwitchingBreadthService()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server, thread, _url = self._start_server(
                root,
                live=live,
                breadth=breadth,
                cache_root=root / "official-cache",
                startup_refresh=True,
            )
            try:
                self.assertTrue(live.called.wait(timeout=2))
                self.assertTrue(breadth.called.wait(timeout=2))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual([False], live.forces)
        self.assertEqual([False], breadth.forces)


def _mutation_token(url: str) -> str:
    html = urlopen(url, timeout=3).read().decode("utf-8")
    marker = 'data-action-api-token="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    token: str,
    origin: str | None = None,
    host: str | None = None,
) -> dict[str, object]:
    headers = {
        "Content-Type": "application/json",
        "X-Taiwan-Equity-Lens-Token": token,
    }
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise AssertionError("response must be a JSON object")
    return result


if __name__ == "__main__":
    unittest.main()
