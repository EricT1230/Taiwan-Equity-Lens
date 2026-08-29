import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from unittest.mock import patch

from taiwan_stock_analysis.fubon_market import (
    FUBON_STOCK_BASE_URL,
    FubonAuthenticationError,
    FubonSession,
)
from taiwan_stock_analysis.live_market import (
    FUGLE_QUOTE_URL,
    FUGLE_TICKERS_URL,
    TPEX_DISPOSITION_URL,
    TPEX_MATERIAL_URL,
    TPEX_WARNING_URL,
    TWSE_DISPOSITION_URL,
    TWSE_MATERIAL_URL,
    TWSE_MIS_URL,
    TWSE_NEWS_URL,
    TWSE_NOTICE_URL,
    TWSE_HOLIDAY_URL,
    LiveMarketService,
    _LoadedRows,
    _ProviderGate,
    _http_json,
    _verified_ssl_context,
    _component_public_status,
    _quote_status,
    build_market_summary,
    normalize_symbols,
)


TAIPEI = timezone(timedelta(hours=8))


class _FixtureFetcher:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        if url.startswith(TWSE_MIS_URL):
            return {
                "rtcode": "0000",
                "msgArray": [
                    {
                        "c": "t00",
                        "n": "發行量加權股價指數",
                        "ex": "tse",
                        "z": "40100",
                        "y": "40000",
                        "d": "20260729",
                        "t": "10:05:00",
                    },
                    {
                        "c": "o00",
                        "n": "櫃買指數",
                        "ex": "otc",
                        "z": "351",
                        "y": "350",
                        "d": "20260729",
                        "t": "10:05:00",
                    },
                    {
                        "c": "2330",
                        "n": "台積電",
                        "ex": "tse",
                        "z": "2210",
                        "y": "2200",
                        "o": "2190",
                        "h": "2220",
                        "l": "2180",
                        "v": "12000",
                        "b": "2205_2200",
                        "a": "2210_2215",
                        "d": "20260729",
                        "t": "10:05:00",
                    },
                ],
            }
        if url == TWSE_NEWS_URL:
            return [
                {
                    "Date": "1150729",
                    "Title": "交易所最新消息",
                    "Url": "https://www.twse.com.tw/news/example",
                }
            ]
        if url == TWSE_MATERIAL_URL:
            return [
                {
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "主旨": "董事會重要決議",
                    "發言日期": "1150729",
                    "發言時間": "100500",
                    "說明": "依規定公告。",
                }
            ]
        if url == TPEX_MATERIAL_URL:
            return []
        if url == TWSE_DISPOSITION_URL:
            return [
                {
                    "Code": "2330",
                    "Name": "台積電",
                    "Date": "1150729",
                    "DispositionPeriod": "1150729~1150805",
                    "ReasonsOfDisposition": "測試處置條件",
                }
            ]
        if url in {TWSE_NOTICE_URL, TPEX_DISPOSITION_URL, TPEX_WARNING_URL}:
            return []
        if url.startswith(FUGLE_TICKERS_URL):
            if "exchange=TWSE" in url:
                return {
                    "date": "2026-07-29",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "data": [
                        {"symbol": "IX0001", "name": "發行量加權股價指數"},
                    ],
                }
            if "exchange=TPEx" in url:
                return {
                    "date": "2026-07-29",
                    "type": "INDEX",
                    "exchange": "TPEx",
                    "data": [
                        {"symbol": "IX0043", "name": "櫃買指數"},
                    ],
                }
        if url.startswith(FUGLE_QUOTE_URL.rsplit("/", 1)[0]):
            symbol = url.rsplit("/", 1)[-1]
            if symbol in {"IX0001", "IX0043"}:
                is_taiex = symbol == "IX0001"
                return {
                    "symbol": symbol,
                    "name": "發行量加權股價指數" if is_taiex else "櫃買指數",
                    "type": "INDEX",
                    "exchange": "TWSE" if is_taiex else "TPEx",
                    "date": "2026-07-29",
                    "lastPrice": 40100 if is_taiex else 351,
                    "previousClose": 40000 if is_taiex else 350,
                    "change": 100 if is_taiex else 1,
                    "changePercent": 0.25 if is_taiex else 0.2857,
                    "lastUpdated": 1785290700000000,
                    "isClose": False,
                    "total": {"tradeVolume": 0},
                }
            return {
                "symbol": symbol,
                "name": "台積電",
                "type": "EQUITY",
                "exchange": "TWSE",
                "date": "2026-07-29",
                "lastPrice": 2210,
                "previousClose": 2200,
                "change": 10,
                "changePercent": 0.4545,
                "openPrice": 2190,
                "highPrice": 2220,
                "lowPrice": 2180,
                "lastUpdated": 1785290700000000,
                "bids": [{"price": 2205}],
                "asks": [{"price": 2210}],
                "total": {"tradeVolume": 12000},
                "isClose": False,
            }
        raise AssertionError(f"unexpected URL: {url}")


class _FakeFubonSessionManager:
    def __init__(self):
        self.invalidations = 0
        self.closes = 0
        self.fail_authentication = False

    def configuration_error(self):
        return ""

    def sdk_available(self):
        return True

    def session(self, *, timeout_seconds=None):
        if self.fail_authentication:
            raise FubonAuthenticationError(
                "fixture rejected fubon credentials"
            )
        return FubonSession(
            base_url=FUBON_STOCK_BASE_URL,
            sdk_token="fubon-session-token",
        )

    def invalidate(self, *, authentication_failure=False):
        self.invalidations += 1

    def close(self):
        self.closes += 1


class _FakeFubonStream:
    def __init__(self, overlay):
        self.overlay = overlay
        self.subscribe_calls = []
        self.unsubscribe_calls = []
        self.connects = 0
        self.closes = 0

    def subscribe(self, *, stock_symbols=(), index_symbols=()):
        self.subscribe_calls.append((set(stock_symbols), set(index_symbols)))

    def unsubscribe(self, *, stock_symbols=(), index_symbols=()):
        self.unsubscribe_calls.append((set(stock_symbols), set(index_symbols)))

    def connect(self):
        self.connects += 1

    def overlay_snapshot(self):
        return self.overlay

    def health(self):
        status = self.overlay.get("status", "UNAVAILABLE")
        health = {
            "ok": status in {"LIVE", "EOD"},
            "ready": status in {"LIVE", "EOD"},
            "usable": status in {"LIVE", "DELAYED", "EOD"},
            "status": status,
            "transport_status": self.overlay.get(
                "transport_status", "STREAMING"
            ),
        }
        for key in (
            "connect_worker_active",
            "reconnect_failures",
            "retry_after_seconds",
        ):
            if key in self.overlay:
                health[key] = self.overlay[key]
        return health

    def close(self):
        self.closes += 1


class _FubonFixtureFetcher(_FixtureFetcher):
    def __call__(
        self,
        url,
        headers=None,
        timeout_seconds=None,
        allow_redirects=None,
        compatibility_tls=None,
    ):
        self.calls.append((url, dict(headers or {})))
        if url.startswith(
            f"{FUBON_STOCK_BASE_URL}/snapshot/quotes/"
        ):
            market = "TSE" if "/snapshot/quotes/TSE" in url else "OTC"
            is_twse = market == "TSE"
            return {
                "date": "2026-07-29",
                "time": "100500",
                "market": market,
                "data": [
                    {
                        "symbol": "2330" if is_twse else "6488",
                        "name": "台積電" if is_twse else "環球晶",
                        "type": "EQUITY",
                        "openPrice": 2190 if is_twse else 470,
                        "highPrice": 2220 if is_twse else 486,
                        "lowPrice": 2180 if is_twse else 468,
                        "closePrice": 2210 if is_twse else 482,
                        "change": 10 if is_twse else 4,
                        "changePercent": 0.4545 if is_twse else 0.8368,
                        "tradeVolume": 12000 if is_twse else 1800,
                        "tradeValue": 26520000 if is_twse else 867600,
                        "lastUpdated": 1785290700000000,
                        "isTrial": False,
                    }
                ],
            }
        if url.startswith(
            f"{FUBON_STOCK_BASE_URL}/intraday/tickers?"
        ):
            if "exchange=TWSE" in url:
                return {
                    "date": "2026-07-29",
                    "type": "INDEX",
                    "exchange": "TWSE",
                    "data": [
                        {"symbol": "IX0001", "name": "發行量加權股價指數"},
                    ],
                }
            if "exchange=TPEx" in url:
                return {
                    "date": "2026-07-29",
                    "type": "INDEX",
                    "exchange": "TPEx",
                    "data": [
                        {"symbol": "IX0043", "name": "櫃買指數"},
                    ],
                }
        if url.startswith(
            f"{FUBON_STOCK_BASE_URL}/intraday/quote/"
        ):
            symbol = url.rsplit("/", 1)[-1]
            is_taiex = symbol == "IX0001"
            return {
                "symbol": symbol,
                "name": "發行量加權股價指數" if is_taiex else "櫃買指數",
                "type": "INDEX",
                "exchange": "TWSE" if is_taiex else "TPEx",
                "date": "2026-07-29",
                "lastPrice": 40100 if is_taiex else 351,
                "previousClose": 40000 if is_taiex else 350,
                "change": 100 if is_taiex else 1,
                "changePercent": 0.25 if is_taiex else 0.2857,
                "lastUpdated": 1785290700000000,
                "isClose": False,
                "total": {"tradeVolume": 0},
            }
        self.calls.pop()
        return super().__call__(url, headers)


class _DriftAlertFetcher(_FixtureFetcher):
    def __call__(self, url, headers=None):
        if url in {
            TWSE_DISPOSITION_URL,
            TWSE_NOTICE_URL,
            TPEX_DISPOSITION_URL,
            TPEX_WARNING_URL,
        }:
            return [{"unexpected": "schema"}]
        return super().__call__(url, headers)


def _flow_rows():
    return [
        {
            "date": "2026-07-29",
            "stock_id": "2330",
            "company_name": "台積電",
            "foreign_net": 100,
            "investment_trust_net": 20,
            "dealer_net": -5,
            "total_net": 115,
            "source": "fixture",
        }
    ]


class LiveMarketServiceTests(unittest.TestCase):
    def test_normalize_symbols_deduplicates_rejects_and_limits(self):
        values = [" 2330 ", "2330", "../bad", "BRK.B", "", None, "A" * 17]
        self.assertEqual(["2330", "BRK.B"], normalize_symbols(values))

    def test_personal_snapshot_normalizes_live_quotes_news_alerts_and_flow(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            snapshot = service.snapshot(["2330", "2330", "bad/symbol"])

        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual("PERSONAL_LIVE", snapshot["provider"]["mode"])
        self.assertFalse(snapshot["provider"]["redistribution_allowed"])
        self.assertEqual(["2330"], [row["symbol"] for row in snapshot["quotes"]])
        self.assertEqual({"t00", "o00"}, {row["symbol"] for row in snapshot["indices"]})
        self.assertAlmostEqual(0.4545, snapshot["quotes"][0]["change_percent"], places=3)
        self.assertEqual(2, len(snapshot["news"]))
        self.assertEqual("2330", snapshot["active_watchlist_alerts"][0]["symbol"])
        self.assertEqual(115, snapshot["fund_flow_total"])
        self.assertEqual("LIVE", snapshot["source_status"]["quotes"]["status"])
        self.assertEqual(
            "2026-07-29T10:05:00+08:00",
            snapshot["source_status"]["quotes"]["latest_event_at"],
        )
        self.assertEqual("EOD", snapshot["source_status"]["fund_flow"]["status"])
        self.assertEqual([], snapshot["errors"])
        self.assertEqual(5, snapshot["refresh_after_seconds"])

    def test_snapshot_returns_bounded_but_explorable_news_collection(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        news = [
            {
                "title": f"事件 {index}",
                "published_at": "2026-07-29T10:05:00+08:00",
                "url": f"https://example.com/news/{index}",
                "source": "fixture",
            }
            for index in range(120)
        ]
        empty = _LoadedRows([], (), ())
        with (
            patch.object(
                service,
                "_load_quotes",
                return_value=empty,
            ),
            patch.object(
                service,
                "_load_news",
                return_value=_LoadedRows(
                    news,
                    (),
                    ({"id": "fixture-news", "status": "FRESH", "row_count": 120},),
                ),
            ),
            patch.object(service, "_load_alerts", return_value=empty),
            patch.object(service, "_load_fund_flow", return_value=empty),
        ):
            snapshot = service.snapshot([])

        self.assertEqual(96, len(snapshot["news"]))
        self.assertEqual(120, snapshot["source_status"]["news"]["available_row_count"])
        self.assertEqual(96, snapshot["source_status"]["news"]["returned_row_count"])
        self.assertTrue(snapshot["source_status"]["news"]["truncated"])

    def test_breadth_support_keeps_latest_completed_session_authoritative_after_midnight(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 30, 0, 13, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            support = service.breadth_support()

        self.assertEqual("EOD", support["source_status"]["fund_flow"]["status"])
        self.assertEqual("FRESH", support["source_status"]["alerts"]["status"])
        self.assertFalse(support["source_status"]["alerts"].get("partial", False))
        self.assertEqual([], support["errors"])

    def test_breadth_support_rejects_nonempty_alert_schema_drift(self):
        service = LiveMarketService(
            fetch_json=_DriftAlertFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            support = service.breadth_support()

        alerts = support["source_status"]["alerts"]
        self.assertEqual("UNAVAILABLE", alerts["status"])
        self.assertTrue(
            all(
                row["status"] == "UNAVAILABLE"
                for row in alerts["upstreams"]
            )
        )
        self.assertEqual([], support["alerts"])
        self.assertTrue(
            any("rejected 1 of 1 rows" in error for error in support["errors"])
        )

    def test_twse_notice_zero_sentinel_is_a_successful_empty_feed(self):
        fixture = _FixtureFetcher()

        def sentinel_fetch(url, headers=None):
            if url == TWSE_NOTICE_URL:
                return [
                    {
                        "Number": "0",
                        "Code": "",
                        "NumberOfAnnouncement": "0",
                        "Date": "",
                        "CompanyName": "",
                    }
                ]
            if url == TPEX_WARNING_URL:
                return [
                    {
                        "SecuritiesCompanyCode": "6488",
                        "CompanyName": "環球晶",
                        "Date": "1150729",
                        "TradingInformation": "達公布注意交易資訊標準",
                    }
                ]
            return fixture(url, headers)

        service = LiveMarketService(
            fetch_json=sentinel_fetch,
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
        )
        loaded = service._load_alerts()
        statuses = {row["id"]: row for row in loaded.upstreams}

        self.assertEqual("FRESH", statuses["twse-notice"]["status"])
        self.assertEqual(0, statuses["twse-notice"]["row_count"])
        self.assertGreaterEqual(statuses["tpex-notice"]["row_count"], 1)
        self.assertFalse(
            any("twse-notice: rejected" in error for error in loaded.errors)
        )

    def test_public_component_status_never_upgrades_stale_fallback(self):
        status = _component_public_status(
            {
                "status": "STALE",
                "fallback": True,
                "cached": True,
                "upstreams": [
                    {
                        "id": "twse-t86",
                        "status": "EOD",
                        "latest_event_at": "2026-07-29",
                    }
                ],
            },
            status="EOD",
        )

        self.assertEqual("STALE", status["status"])
        self.assertTrue(status["fallback"])

    def test_live_snapshot_does_not_wait_for_breadth_support_refresh_lock(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        started = threading.Event()
        release = threading.Event()

        def blocking_alerts():
            started.set()
            release.wait(timeout=5)
            return _LoadedRows([], (), ())

        with (
            patch.object(service, "_load_alerts", side_effect=blocking_alerts),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            support_thread = threading.Thread(
                target=service.breadth_support,
                daemon=True,
            )
            support_thread.start()
            self.assertTrue(started.wait(timeout=2))
            started_at = time.monotonic()
            snapshot = service.snapshot(["2330"])
            elapsed = time.monotonic() - started_at
            release.set()
            support_thread.join(timeout=5)

        self.assertLess(elapsed, 1.0)
        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual(
            "UNAVAILABLE",
            snapshot["source_status"]["alerts"]["status"],
        )
        self.assertTrue(
            any(
                "refresh is already in progress" in error
                for error in snapshot["errors"]
            )
        )

    def test_slow_first_refresh_releases_snapshot_caller_and_fails_fast(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
            component_deadline_seconds=0.05,
        )
        release = threading.Event()

        def blocking_component(*args, **kwargs):
            del args, kwargs
            release.wait(timeout=2)
            return _LoadedRows([], upstreams=({"id": "slow", "status": "FRESH"},))

        with (
            patch.object(service, "_load_quotes", side_effect=blocking_component),
            patch.object(service, "_load_news", side_effect=blocking_component),
            patch.object(service, "_load_alerts", side_effect=blocking_component),
            patch.object(service, "_load_fund_flow", side_effect=blocking_component),
        ):
            started = time.monotonic()
            first = service.snapshot(["2330"])
            first_elapsed = time.monotonic() - started
            started = time.monotonic()
            second = service.snapshot(["2330"])
            second_elapsed = time.monotonic() - started
            release.set()
            time.sleep(0.05)

        self.assertLess(first_elapsed, 0.25)
        self.assertLess(second_elapsed, 0.1)
        self.assertEqual("UNAVAILABLE", first["status"])
        self.assertEqual("UNAVAILABLE", second["status"])
        self.assertTrue(
            any("capacity is busy" in error for error in second["errors"])
        )

    def test_personal_quote_cache_avoids_duplicate_upstream_requests(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            service.snapshot(["2330"])
            service.snapshot(["2330"])

        mis_calls = [url for url, _ in fetcher.calls if url.startswith(TWSE_MIS_URL)]
        self.assertEqual(1, len(mis_calls))

    def test_manual_force_refresh_bypasses_snapshot_component_cache(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            service.snapshot(["2330"])
            service.snapshot(["2330"])
            service.snapshot(["2330"], force=True)

        mis_calls = [url for url, _ in fetcher.calls if url.startswith(TWSE_MIS_URL)]
        self.assertEqual(2, len(mis_calls))

    def test_fugle_symbol_cache_reuses_shared_symbols_across_watchlists(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            service.snapshot(["2330"])
            service.snapshot(["2330", "2303"])

        quote_calls = [
            url
            for url, _ in fetcher.calls
            if "/intraday/quote/" in url
        ]
        self.assertEqual(
            [
                FUGLE_QUOTE_URL.format(symbol="IX0001"),
                FUGLE_QUOTE_URL.format(symbol="IX0043"),
                FUGLE_QUOTE_URL.format(symbol="2330"),
                FUGLE_QUOTE_URL.format(symbol="2303"),
            ],
            quote_calls,
        )

    def test_fubon_probe_uses_authenticated_bulk_snapshots_and_indices(self):
        fetcher = _FubonFixtureFetcher()
        sessions = _FakeFubonSessionManager()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fubon",
            fubon_api_key="must-not-appear",
            fubon_personal_id="A123456789",
            fubon_cert_path="must-not-appear.pfx",
            fubon_cert_password="must-not-appear",
            fubon_session_manager=sessions,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertTrue(probe["ok"])
        self.assertEqual("LIVE", probe["status"])
        self.assertEqual("fubon", probe["provider_mode"])
        self.assertEqual(["2330"], probe["returned_symbols"])
        self.assertEqual({"t00", "o00"}, {
            row["symbol"] for row in probe["indices"]
        })
        self.assertEqual("Fubon Neo MarketData", probe["quotes"][0]["source"])
        self.assertEqual(2210, probe["quotes"][0]["price"])
        self.assertEqual(2200, probe["quotes"][0]["previous_close"])
        self.assertEqual(12000, probe["quotes"][0]["volume"])
        self.assertIsNone(probe["quotes"][0]["best_bid"])
        self.assertIsNone(probe["quotes"][0]["best_ask"])
        fubon_calls = [
            (url, headers)
            for url, headers in fetcher.calls
            if url.startswith(FUBON_STOCK_BASE_URL)
        ]
        self.assertEqual(6, len(fubon_calls))
        self.assertTrue(
            all(
                headers == {"X-SDK-TOKEN": "fubon-session-token"}
                for _, headers in fubon_calls
            )
        )
        self.assertEqual(
            {
                f"{FUBON_STOCK_BASE_URL}/snapshot/quotes/TSE",
                f"{FUBON_STOCK_BASE_URL}/snapshot/quotes/OTC",
            },
            {
                url
                for url, _ in fubon_calls
                if "/snapshot/quotes/" in url
            },
        )
        self.assertNotIn("must-not-appear", str(probe))
        self.assertNotIn("fubon-session-token", str(probe))
        health = service.health()
        self.assertTrue(health["ready"])
        self.assertEqual(240, health["provider_calls_per_minute_budget"])
        self.assertEqual(6, health["estimated_provider_calls_per_snapshot"])
        self.assertEqual(5, health["minimum_client_refresh_seconds"])
        self.assertNotIn("must-not-appear", str(health))

    def test_fubon_websocket_aggregate_overlays_rest_baseline_and_is_reported(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        event_time = int(now.timestamp() * 1_000_000)
        stream = _FakeFubonStream(
            {
                "status": "LIVE",
                "transport_status": "STREAMING",
                "connect_worker_active": False,
                "reconnect_failures": 2,
                "retry_after_seconds": 10.0,
                "aggregates": {
                    "2330": {
                        "date": "2026-07-29",
                        "type": "EQUITY",
                        "exchange": "TWSE",
                        "symbol": "2330",
                        "name": "串流名稱不得取代 REST 名稱",
                        "lastPrice": 2222,
                        "previousClose": 1000,
                        "change": 1222,
                        "changePercent": 122.2,
                        "lastUpdated": event_time,
                        "source_event_time": now.isoformat(),
                        "status": "LIVE",
                        "total": {"tradeVolume": 12345},
                    }
                },
                "indices": {},
            }
        )
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            fubon_stream_feed=stream,
            clock=lambda: now,
        )

        snapshot = service.snapshot(["2330"])
        quote = next(
            row for row in snapshot["quotes"] if row["symbol"] == "2330"
        )

        self.assertEqual(2222, quote["price"])
        self.assertEqual("台積電", quote["name"])
        self.assertEqual(2200, quote["previous_close"])
        self.assertEqual(22, quote["change"])
        self.assertEqual(1.0, quote["change_percent"])
        self.assertEqual("2330", quote["provider_symbol"])
        self.assertEqual("TWSE", quote["exchange"])
        self.assertEqual(12345, quote["volume"])
        self.assertEqual("LIVE", quote["status"])
        self.assertIn("WebSocket", quote["source"])
        self.assertEqual(
            "LIVE",
            snapshot["source_status"]["quotes"]["stream"]["status"],
        )
        self.assertEqual(
            2,
            snapshot["source_status"]["quotes"]["stream"]["reconnect_failures"],
        )
        self.assertEqual(
            10.0,
            snapshot["source_status"]["quotes"]["stream"]["retry_after_seconds"],
        )
        self.assertFalse(
            snapshot["source_status"]["quotes"]["stream"]["connect_worker_active"]
        )
        self.assertEqual({"2330"}, stream.subscribe_calls[0][0])
        self.assertEqual(
            {"IR0001", "IR0043"},
            stream.subscribe_calls[0][1],
        )
        self.assertGreaterEqual(stream.connects, 1)

        service.close()
        self.assertEqual(1, stream.closes)

    def test_fubon_websocket_never_upgrades_stale_or_cross_session_rest_baseline(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        stream = _FakeFubonStream(
            {
                "status": "LIVE",
                "transport_status": "STREAMING",
                "aggregates": {
                    "2330": {
                        "date": "2026-07-29",
                        "type": "EQUITY",
                        "exchange": "TWSE",
                        "symbol": "2330",
                        "lastPrice": 2222,
                        "source_event_time": now.isoformat(),
                        "status": "LIVE",
                    }
                },
                "indices": {},
            }
        )
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            fubon_stream_feed=stream,
            clock=lambda: now,
        )
        baseline = {
            "symbol": "2330",
            "provider_symbol": "2330",
            "kind": "equity",
            "status": "LIVE",
            "session_date": "2026-07-29",
            "price": 2210,
            "previous_close": 2200,
            "change": 10,
            "change_percent": 10 / 2200 * 100,
            "source": "Fubon Neo MarketData",
        }

        for status, session_date in (
            ("STALE", "2026-07-29"),
            ("LIVE", "2026-07-28"),
        ):
            with self.subTest(status=status, session_date=session_date):
                candidate = dict(
                    baseline,
                    status=status,
                    session_date=session_date,
                )
                rows, _ = service._apply_fubon_stream_overlay(
                    [candidate],
                    requested_symbols=["2330"],
                    errors=[],
                )
                self.assertEqual(candidate, rows[0])
                self.assertEqual(2210, rows[0]["price"])
                self.assertNotIn("WebSocket", rows[0]["source"])

    def test_fubon_stream_exception_never_exposes_sdk_derived_secrets(self):
        derived_secret = "sdk_token=DERIVED-SESSION account=987654321"

        class ExplodingStream(_FakeFubonStream):
            def subscribe(self, *, stock_symbols=(), index_symbols=()):
                raise RuntimeError(derived_secret)

        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        stream = ExplodingStream({"status": "UNAVAILABLE"})
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            fubon_stream_feed=stream,
            clock=lambda: now,
        )

        snapshot = service.snapshot(["2330"])
        health = service.health()

        self.assertNotIn(derived_secret, str(snapshot))
        self.assertNotIn("DERIVED-SESSION", str(snapshot))
        self.assertNotIn("987654321", str(snapshot))
        self.assertNotIn(derived_secret, str(health))
        self.assertIn("Fubon market-data response was invalid", str(snapshot))

    def test_fubon_delayed_websocket_indices_disable_market_strategy(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        stream = _FakeFubonStream(
            {
                "status": "DELAYED",
                "transport_status": "STREAMING",
                "aggregates": {},
                "indices": {
                    "IR0001": {
                        "symbol": "IR0001",
                        "index": 40110,
                        "source_event_time": now.isoformat(),
                        "status": "DELAYED",
                    },
                    "IR0043": {
                        "symbol": "IR0043",
                        "index": 351.5,
                        "source_event_time": now.isoformat(),
                        "status": "DELAYED",
                    },
                },
            }
        )
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            fubon_stream_feed=stream,
            clock=lambda: now,
        )

        snapshot = service.snapshot(["2330"])

        self.assertEqual("DELAYED", snapshot["status"])
        self.assertEqual("DELAYED", snapshot["market"]["status"])
        self.assertEqual("neutral", snapshot["market"]["strategy"])
        self.assertIsNone(snapshot["market"]["temperature"])
        self.assertFalse(snapshot["quotes_ok"])
        self.assertEqual(
            "DELAYED",
            snapshot["source_status"]["quotes"]["status"],
        )

    def test_fubon_breadth_support_returns_both_market_snapshots(self):
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            support = service.breadth_support()

        self.assertEqual(
            {"2330", "6488"},
            {row["symbol"] for row in support["live_quotes"]},
        )
        self.assertEqual(
            {"TWSE", "TPEX"},
            {row["market"] for row in support["live_quotes"]},
        )
        self.assertEqual(
            "LIVE",
            support["source_status"]["live_quotes"]["status"],
        )
        upstreams = {
            row["id"]: row
            for row in support["source_status"]["live_quotes"]["upstreams"]
        }
        self.assertEqual(1, upstreams["fubon-snapshot:TSE"]["row_count"])
        self.assertEqual(1, upstreams["fubon-snapshot:OTC"]["row_count"])

    def test_fubon_trial_snapshot_does_not_publish_trial_last_price(self):
        fixture = _FubonFixtureFetcher()

        def trial_fetch(
            url,
            headers=None,
            timeout_seconds=None,
            allow_redirects=None,
            compatibility_tls=None,
        ):
            payload = fixture(
                url,
                headers,
                timeout_seconds,
                allow_redirects,
                compatibility_tls,
            )
            if "/snapshot/quotes/TSE" in url:
                row = payload["data"][0]
                row["closePrice"] = None
                row["lastPrice"] = 9999
                row["isTrial"] = True
            return payload

        service = LiveMarketService(
            fetch_json=trial_fetch,
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        loaded = service._load_fubon_full_market_quotes()
        quote = next(row for row in loaded.rows if row["symbol"] == "2330")

        self.assertTrue(quote["provider_is_trial"])
        self.assertIsNone(quote["price"])
        self.assertIsNone(quote["previous_close"])
        self.assertEqual("STALE", quote["status"])

    def test_fubon_rejects_invalid_configured_benchmark_before_http(self):
        fetcher = _FubonFixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        with patch.dict(
            os.environ,
            {
                "FUBON_TAIEX_SYMBOL": "../private?token=1",
                "FUBON_TPEX_SYMBOL": "IX0043",
            },
        ):
            requests, errors = service._discover_fubon_benchmarks(
                deadline=time.monotonic() + 1,
            )

        self.assertEqual([("IX0043", "o00")], requests)
        self.assertTrue(any("configured symbol is invalid" in error for error in errors))
        self.assertEqual([], fetcher.calls)

    def test_fubon_rejects_invalid_discovered_benchmark_before_http(self):
        fetcher = _FubonFixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        with self.assertRaisesRegex(ValueError, "benchmark symbol is invalid"):
            service._fetch_and_normalize_fubon_index(
                "../private?token=1",
                benchmark_symbol="t00",
                deadline=time.monotonic() + 1,
            )

        self.assertEqual([], fetcher.calls)

    def test_fubon_requires_market_data_only_operator_confirmation(self):
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_market_data_only_confirmed=False,
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        health = service.health()

        self.assertFalse(health["configured"])
        self.assertFalse(health["fubon_market_data_only_confirmed"])
        self.assertIn(
            "FUBON_MARKET_DATA_ONLY_CONFIRMED=1",
            health["configuration_error"],
        )

    def test_fubon_auth_failure_never_falls_back_to_cached_live_rows(self):
        sessions = _FakeFubonSessionManager()
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=sessions,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            first = service.breadth_support()
            sessions.fail_authentication = True
            for key, entry in list(service._cache.items()):
                service._cache[key] = entry.__class__(
                    entry.payload,
                    entry.fetched_at,
                    0.0,
                )
            second = service.breadth_support()

        self.assertEqual(2, len(first["live_quotes"]))
        self.assertEqual([], second["live_quotes"])
        self.assertEqual(
            "UNAVAILABLE",
            second["source_status"]["live_quotes"]["status"],
        )
        self.assertTrue(
            any(
                "Fubon authentication was rejected" in error
                for error in second["errors"]
            )
        )

    def test_fubon_http_401_clears_visible_quote_cache_and_health(self):
        fixture = _FubonFixtureFetcher()
        reject = {"value": False}

        def authenticated_fetch(
            url,
            headers=None,
            timeout_seconds=None,
            allow_redirects=None,
            compatibility_tls=None,
        ):
            if reject["value"] and url.startswith(FUBON_STOCK_BASE_URL):
                raise HTTPError(
                    url,
                    401,
                    "fixture token expired",
                    {},
                    None,
                )
            return fixture(
                url,
                headers,
                timeout_seconds,
                allow_redirects,
                compatibility_tls,
            )

        sessions = _FakeFubonSessionManager()
        service = LiveMarketService(
            fetch_json=authenticated_fetch,
            provider="fubon",
            fubon_session_manager=sessions,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            first = service.snapshot(["2330"])
            for key, entry in list(service._cache.items()):
                service._cache[key] = entry.__class__(
                    entry.payload,
                    entry.fetched_at,
                    0.0,
                )
            reject["value"] = True
            second = service.snapshot(["2330"])

        self.assertEqual("LIVE", first["status"])
        self.assertEqual("UNAVAILABLE", second["status"])
        self.assertEqual([], second["quotes"])
        self.assertEqual([], second["indices"])
        self.assertTrue(
            any(
                "authentication expired (HTTP 401)" in error
                for error in second["errors"]
            )
        )
        self.assertGreaterEqual(sessions.invalidations, 1)
        self.assertEqual({}, service._fubon_negative_cache)
        health = service.health()
        self.assertFalse(health["ready"])
        self.assertFalse(health["last_attempt_ok"])
        self.assertEqual(
            "Fubon market-data authentication expired (HTTP 401)",
            health["last_error"],
        )

    def test_fubon_breadth_401_purges_fresh_watchlist_quote_cache(self):
        fixture = _FubonFixtureFetcher()
        reject = {"value": False}

        def authenticated_fetch(
            url,
            headers=None,
            timeout_seconds=None,
            allow_redirects=None,
            compatibility_tls=None,
        ):
            if reject["value"] and url.startswith(FUBON_STOCK_BASE_URL):
                raise HTTPError(url, 401, "fixture token expired", {}, None)
            return fixture(
                url,
                headers,
                timeout_seconds,
                allow_redirects,
                compatibility_tls,
            )

        service = LiveMarketService(
            fetch_json=authenticated_fetch,
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            first = service.snapshot(["2330"])
            quote_key = next(
                key for key in service._cache if key.startswith("quotes:")
            )
            for key, entry in list(service._cache.items()):
                if key.startswith("fubon-"):
                    service._cache[key] = entry.__class__(
                        entry.payload,
                        entry.fetched_at,
                        0.0,
                    )
            reject["value"] = True
            breadth = service.breadth_support()
            second = service.snapshot(["2330"])

        self.assertEqual("LIVE", first["status"])
        self.assertEqual([], breadth["live_quotes"])
        self.assertNotIn(quote_key, service._cache)
        self.assertEqual("UNAVAILABLE", second["status"])
        self.assertEqual([], second["quotes"])
        self.assertFalse(service.health()["ready"])

    def test_fubon_auth_invalidation_blocks_concurrent_old_cache_writer(self):
        invalidation_started = threading.Event()
        release_invalidation = threading.Event()

        class BlockingInvalidationManager(_FakeFubonSessionManager):
            def invalidate(self, *, authentication_failure=False):
                invalidation_started.set()
                release_invalidation.wait(2)
                super().invalidate(
                    authentication_failure=authentication_failure
                )

        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=BlockingInvalidationManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        service._cached(
            "quotes:2330",
            4.0,
            lambda: _LoadedRows(
                [
                    {
                        "symbol": "2330",
                        "kind": "equity",
                        "status": "LIVE",
                        "price": 2210,
                    }
                ]
            ),
        )

        invalidator = threading.Thread(
            target=service._invalidate_fubon_authentication,
            args=(401,),
        )
        invalidator.start()
        self.assertTrue(invalidation_started.wait(1))
        errors = []
        concurrent = service._safe_component(
            "quotes:2330",
            4.0,
            lambda: _LoadedRows(
                [
                    {
                        "symbol": "2330",
                        "kind": "equity",
                        "status": "LIVE",
                        "price": 2210,
                    }
                ]
            ),
            errors,
        )
        release_invalidation.set()
        invalidator.join(2)

        self.assertFalse(invalidator.is_alive())
        self.assertEqual("UNAVAILABLE", concurrent["status"])
        self.assertEqual([], concurrent["payload"])
        self.assertNotIn("quotes:2330", service._cache)

    def test_fubon_auth_invalidation_closes_and_detaches_old_stream(self):
        stream = _FakeFubonStream({"status": "LIVE"})
        manager = _FakeFubonSessionManager()
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=manager,
            fubon_stream_feed=stream,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        service._fubon_stream_desired_stocks = {"2330"}
        service._fubon_stream_desired_indices = {"IR0001"}
        service._fubon_stream_create_attempted = True

        service._invalidate_fubon_authentication(401)

        self.assertEqual(1, stream.closes)
        self.assertIsNone(service._fubon_stream_feed)
        self.assertFalse(service._fubon_stream_create_attempted)
        self.assertEqual(set(), service._fubon_stream_desired_stocks)
        self.assertEqual(set(), service._fubon_stream_desired_indices)
        self.assertEqual(1, manager.invalidations)

    def test_successful_fubon_breadth_refresh_recovers_provider_health(self):
        service = LiveMarketService(
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        service._record_provider_attempt(False, error="fixture failure")

        with (
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            support = service.breadth_support()

        self.assertEqual(2, len(support["live_quotes"]))
        self.assertTrue(service.health()["ready"])
        self.assertEqual("", service.health()["last_error"])

    def test_partial_news_failure_preserves_other_sources_and_exposes_status(self):
        fixture = _FixtureFetcher()

        def partially_failing_fetch(url, headers=None):
            if url == TPEX_MATERIAL_URL:
                raise OSError("fixture TPEx outage")
            return fixture(url, headers)

        service = LiveMarketService(
            fetch_json=partially_failing_fetch,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=_flow_rows()):
            snapshot = service.snapshot(["2330"])

        self.assertEqual(2, len(snapshot["news"]))
        self.assertTrue(snapshot["source_status"]["news"]["partial"])
        upstreams = {
            row["id"]: row["status"]
            for row in snapshot["source_status"]["news"]["upstreams"]
        }
        self.assertEqual("UNAVAILABLE", upstreams["tpex-material"])
        self.assertEqual("FRESH", snapshot["source_status"]["news"]["status"])
        self.assertTrue(any("fixture TPEx outage" in error for error in snapshot["errors"]))

    def test_news_nonempty_schema_drift_is_unavailable_and_reports_rejections(self):
        def drifted_news_fetch(url, headers=None):
            if url in {TWSE_NEWS_URL, TWSE_MATERIAL_URL, TPEX_MATERIAL_URL}:
                return [{"unexpected": "schema"}]
            raise AssertionError(f"unexpected URL: {url}")

        service = LiveMarketService(
            fetch_json=drifted_news_fetch,
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
        )

        loaded = service._load_news()

        self.assertEqual([], loaded.rows)
        self.assertEqual(
            {
                "twse-news": "UNAVAILABLE",
                "twse-material": "UNAVAILABLE",
                "tpex-material": "UNAVAILABLE",
            },
            {row["id"]: row["status"] for row in loaded.upstreams},
        )
        self.assertEqual(
            3,
            sum("rejected 1 of 1 rows" in error for error in loaded.errors),
        )

    def test_news_mixed_valid_invalid_and_future_rows_is_partial(self):
        def mixed_news_fetch(url, headers=None):
            if url == TWSE_NEWS_URL:
                return [
                    {
                        "Date": "1150730",
                        "Title": "有效新聞",
                        "Url": "https://www.twse.com.tw/news/valid",
                    },
                    {"unexpected": "schema"},
                    {
                        "Date": "1150731",
                        "Title": "未來新聞",
                        "Url": "https://www.twse.com.tw/news/future",
                    },
                    {
                        "Date": "1150730",
                        "Title": "缺少原文連結",
                        "Url": "",
                    },
                ]
            if url in {TWSE_MATERIAL_URL, TPEX_MATERIAL_URL}:
                return []
            raise AssertionError(f"unexpected URL: {url}")

        service = LiveMarketService(
            fetch_json=mixed_news_fetch,
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
        )

        loaded = service._load_news()
        twse_news = next(row for row in loaded.upstreams if row["id"] == "twse-news")

        self.assertEqual(["有效新聞"], [row["title"] for row in loaded.rows])
        self.assertEqual("PARTIAL", twse_news["status"])
        self.assertEqual(1, twse_news["row_count"])
        self.assertTrue(
            any("twse-news: rejected 3 of 4 rows" in error for error in loaded.errors)
        )
        self.assertTrue(
            any("discarded future event 2026-07-31" in error for error in loaded.errors)
        )

    def test_partial_watchlist_is_explicitly_degraded_and_lists_missing_symbols(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        rows = [
            {
                "symbol": symbol,
                "kind": "index",
                "status": "LIVE",
                "session_date": "2026-07-29",
                "source_event_time": "2026-07-29T10:05:00+08:00",
                "change_percent": 1.0,
            }
            for symbol in ("t00", "o00")
        ]
        rows.append(
            {
                "symbol": "2330",
                "kind": "equity",
                "status": "LIVE",
                "session_date": "2026-07-29",
                "source_event_time": "2026-07-29T10:05:00+08:00",
                "change_percent": 1.0,
            }
        )
        loaded = _LoadedRows(
            rows=rows,
            errors=("Fugle 2303: request deadline reached",),
            upstreams=(
                {
                    "id": "fugle:2330",
                    "status": "LIVE",
                    "row_count": 1,
                    "latest_event_at": "2026-07-29T10:05:00+08:00",
                },
                {
                    "id": "fugle:2303",
                    "status": "UNAVAILABLE",
                    "row_count": 0,
                    "latest_event_at": "",
                },
            ),
        )
        with (
            patch.object(service, "_load_quotes", return_value=loaded),
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330", "2303"])

        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual(["2303"], snapshot["missing_symbols"])
        self.assertTrue(snapshot["source_status"]["quotes"]["partial"])
        self.assertEqual("STALE", snapshot["source_status"]["quotes"]["status"])
        self.assertEqual(2, snapshot["source_status"]["quotes"]["requested_symbol_count"])
        self.assertEqual(1, snapshot["source_status"]["quotes"]["returned_symbol_count"])

    def test_cache_and_completed_loader_lock_maps_are_bounded(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        for index in range(300):
            service._cached(f"fixture:{index}", 60.0, lambda index=index: index)

        self.assertLessEqual(len(service._cache), 256)
        self.assertEqual({}, service._loader_locks)

    def test_fresh_news_does_not_mislabel_unlicensed_public_quotes_as_eod(self):
        service = LiveMarketService(
            public_mode=True,
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 18, 0, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[{"title": "fresh"}]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=_flow_rows()),
        ):
            snapshot = service.snapshot(["2330"])

        self.assertEqual("UNAVAILABLE", snapshot["status"])
        self.assertFalse(snapshot["provider"]["redistribution_allowed"])
        self.assertEqual("UNAVAILABLE", snapshot["provider"]["mode"])
        self.assertTrue(
            any(
                "public mode requires an explicitly configured" in error
                for error in snapshot["errors"]
            )
        )

    def test_fugle_key_uses_documented_header_and_does_not_imply_redisplay_right(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            fugle_api_key="test-key",
            fugle_redisplay_licensed=False,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330"])

        quote_calls = [(url, headers) for url, headers in fetcher.calls if "/intraday/quote/" in url]
        self.assertIn(
            (FUGLE_QUOTE_URL.format(symbol="2330"), {"X-API-KEY": "test-key"}),
            quote_calls,
        )
        self.assertEqual({"t00", "o00"}, {row["symbol"] for row in snapshot["indices"]})
        self.assertEqual("LIVE", snapshot["market"]["status"])
        self.assertEqual("PERSONAL_KEY", snapshot["provider"]["mode"])
        self.assertFalse(snapshot["provider"]["redistribution_allowed"])
        self.assertEqual("LIVE", snapshot["quotes"][0]["status"])
        self.assertEqual(30, snapshot["refresh_after_seconds"])

    def test_forced_fugle_mode_without_key_fails_closed_on_loopback(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fugle",
            fugle_api_key="",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        health = service.health()
        probe = service.probe(["2330"])

        self.assertFalse(health["ok"])
        self.assertEqual("fugle", health["provider_requested"])
        self.assertEqual("unavailable", health["provider_mode"])
        self.assertEqual(
            "FUGLE_API_KEY is not configured",
            health["configuration_error"],
        )
        self.assertFalse(probe["ok"])
        self.assertEqual("UNAVAILABLE", probe["status"])
        self.assertEqual(["FUGLE_API_KEY is not configured"], probe["errors"])
        self.assertEqual([], fetcher.calls)

    def test_forced_fubon_mode_without_credentials_fails_closed(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fubon",
            fubon_personal_id="",
            fubon_api_key="",
            fubon_cert_path="",
            fubon_cert_password="",
        )

        health = service.health()
        probe = service.probe(["2330"])

        self.assertFalse(health["ok"])
        self.assertEqual("fubon", health["provider_requested"])
        self.assertEqual("unavailable", health["provider_mode"])
        self.assertEqual(
            "Fubon configuration requires personal_id",
            health["configuration_error"],
        )
        self.assertFalse(probe["ok"])
        self.assertEqual("UNAVAILABLE", probe["status"])
        self.assertEqual(
            ["Fubon configuration requires personal_id"],
            probe["errors"],
        )
        self.assertEqual([], fetcher.calls)

    def test_public_fubon_mode_requires_explicit_redisplay_entitlement(self):
        service = LiveMarketService(
            public_mode=True,
            fetch_json=_FubonFixtureFetcher(),
            provider="fubon",
            fubon_session_manager=_FakeFubonSessionManager(),
            fubon_redisplay_licensed=False,
        )

        health = service.health()

        self.assertFalse(health["ok"])
        self.assertEqual("unavailable", health["provider_mode"])
        self.assertEqual(
            "public mode requires FUBON_REDISPLAY_LICENSED=1 backed by "
            "an explicit Fubon and exchange redisplay agreement",
            health["configuration_error"],
        )

    def test_forced_personal_mis_mode_does_not_use_present_fugle_key(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="twse-mis-personal",
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertTrue(probe["ok"])
        self.assertEqual("LIVE", probe["status"])
        self.assertEqual("twse_mis_personal", probe["provider_mode"])
        self.assertTrue(any(url.startswith(TWSE_MIS_URL) for url, _ in fetcher.calls))
        self.assertFalse(
            any(url.startswith(FUGLE_QUOTE_URL.rsplit("/", 1)[0]) for url, _ in fetcher.calls)
        )

    def test_personal_mis_health_is_not_ready_when_requested_equity_is_missing(self):
        fixture = _FixtureFetcher()

        def indices_only_fetch(url, headers=None):
            payload = fixture(url, headers)
            if url.startswith(TWSE_MIS_URL):
                return {
                    **payload,
                    "msgArray": [
                        row
                        for row in payload["msgArray"]
                        if row.get("c") in {"t00", "o00"}
                    ],
                }
            return payload

        service = LiveMarketService(
            fetch_json=indices_only_fetch,
            provider="twse-mis-personal",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertFalse(probe["ok"])
        self.assertFalse(probe["quotes_complete"])
        self.assertEqual(["2330"], probe["missing_symbols"])
        self.assertFalse(service.health()["ready"])

    def test_personal_mis_outage_is_not_mislabeled_as_fugle(self):
        def failing_fetch(url, headers=None):
            raise OSError("fixture MIS outage")

        service = LiveMarketService(
            fetch_json=failing_fetch,
            provider="twse-mis-personal",
        )

        probe = service.probe(["2330"])

        self.assertFalse(probe["ok"])
        self.assertEqual(
            ["TWSE MIS provider request failed"],
            probe["errors"],
        )
        self.assertEqual(
            "TWSE MIS provider request failed",
            service.health()["last_error"],
        )

    def test_public_fugle_mode_requires_explicit_redisplay_entitlement(self):
        service = LiveMarketService(
            public_mode=True,
            fetch_json=_FixtureFetcher(),
            provider="fugle",
            fugle_api_key="test-key",
            fugle_redisplay_licensed=False,
        )

        health = service.health()

        self.assertFalse(health["ok"])
        self.assertEqual("unavailable", health["provider_mode"])
        self.assertEqual(
            "public mode requires FUGLE_REDISPLAY_LICENSED=1 backed by "
            "an explicit Fugle redisplay agreement",
            health["configuration_error"],
        )

    def test_redisplay_entitlement_rejects_non_boolean_values(self):
        with self.assertRaisesRegex(
            TypeError,
            "fugle_redisplay_licensed must be a boolean",
        ):
            LiveMarketService(
                public_mode=True,
                provider="fugle",
                fugle_api_key="test-key",
                fugle_redisplay_licensed="false",
            )

    def test_invalid_key_format_is_rejected_without_leaking_the_key(self):
        secret = "prefix\nSUPERSECRET"
        service = LiveMarketService(
            provider="fugle",
            fugle_api_key=secret,
        )

        probe = service.probe(["2330"])
        health = service.health()

        self.assertFalse(probe["ok"])
        self.assertEqual(
            ["FUGLE_API_KEY has an invalid local format"],
            probe["errors"],
        )
        self.assertEqual(
            "FUGLE_API_KEY has an invalid local format",
            health["configuration_error"],
        )
        self.assertFalse(health["fugle_key_format_valid"])
        self.assertNotIn("SUPERSECRET", str(probe))
        self.assertNotIn("SUPERSECRET", str(health))

    def test_provider_name_is_validated(self):
        with self.assertRaisesRegex(ValueError, "unsupported market data provider"):
            LiveMarketService(provider="fixture")

    def test_fugle_probe_returns_sanitized_live_connection_evidence(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            fetch_json=fetcher,
            provider="fugle",
            fugle_api_key="do-not-print-this",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertTrue(probe["ok"])
        self.assertEqual("LIVE", probe["status"])
        self.assertEqual("fugle", probe["provider_mode"])
        self.assertEqual(["2330"], probe["requested_symbols"])
        self.assertEqual(["2330"], probe["returned_symbols"])
        self.assertEqual([], probe["missing_symbols"])
        self.assertNotIn("do-not-print-this", str(probe))
        self.assertEqual("Fugle MarketData", probe["quotes"][0]["source"])
        health = service.health()
        self.assertTrue(health["ok"])
        self.assertTrue(health["ready"])
        self.assertTrue(health["last_attempt_ok"])
        self.assertTrue(health["last_success_at"])

    def test_provider_probe_rejects_invalid_and_over_limit_symbols(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            provider="fugle",
            fugle_api_key="test-key",
        )

        invalid = service.probe(["2330", "../bad"])
        too_many = service.probe(
            [str(1000 + index) for index in range(41)]
        )

        self.assertFalse(invalid["ok"])
        self.assertEqual(["2330"], invalid["requested_symbols"])
        self.assertEqual(
            ["provider probe rejected 1 invalid symbol value"],
            invalid["errors"],
        )
        self.assertFalse(too_many["ok"])
        self.assertEqual(40, len(too_many["requested_symbols"]))
        self.assertEqual(
            ["provider probe accepts at most 40 unique symbols"],
            too_many["errors"],
        )

    def test_fugle_rejects_a_quote_for_the_wrong_symbol(self):
        fixture = _FixtureFetcher()

        def wrong_symbol_fetch(url, headers=None):
            payload = fixture(url, headers)
            if url == FUGLE_QUOTE_URL.format(symbol="2330"):
                return {**payload, "symbol": "2317", "name": "鴻海"}
            return payload

        service = LiveMarketService(
            fetch_json=wrong_symbol_fetch,
            provider="fugle",
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertFalse(probe["ok"])
        self.assertEqual(["2330"], probe["missing_symbols"])
        self.assertTrue(any("symbol mismatch" in error for error in probe["errors"]))
        self.assertFalse(service.health()["ready"])

    def test_fugle_rejects_equities_configured_as_market_benchmarks(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            provider="fugle",
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        with patch.dict(
            os.environ,
            {
                "FUGLE_TAIEX_SYMBOL": "2330",
                "FUGLE_TPEX_SYMBOL": "2303",
            },
        ):
            probe = service.probe(["2330"])

        self.assertFalse(probe["ok"])
        self.assertFalse(probe["indices_complete"])
        self.assertEqual([], probe["indices"])
        self.assertTrue(
            any("instead of INDEX" in error for error in probe["errors"])
        )
        self.assertFalse(service.health()["ready"])

    def test_fugle_rejects_schema_valid_identity_without_quote_values(self):
        fixture = _FixtureFetcher()

        def missing_values_fetch(url, headers=None):
            payload = fixture(url, headers)
            if url == FUGLE_QUOTE_URL.format(symbol="2330"):
                return {
                    "symbol": "2330",
                    "name": "台積電",
                    "type": "EQUITY",
                    "exchange": "TWSE",
                    "date": "2026-07-29",
                    "lastUpdated": 1785290700000000,
                }
            return payload

        service = LiveMarketService(
            fetch_json=missing_values_fetch,
            provider="fugle",
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )

        probe = service.probe(["2330"])

        self.assertFalse(probe["ok"])
        self.assertFalse(probe["quotes_complete"])
        self.assertTrue(
            any("missing a usable price" in error for error in probe["errors"])
        )
        self.assertFalse(service.health()["ready"])

    def test_cache_ttl_starts_after_a_slow_loader_completes(self):
        service = LiveMarketService(fetch_json=_FixtureFetcher())

        with patch(
            "taiwan_stock_analysis.live_market.time.monotonic",
            side_effect=[100.0, 100.0, 110.0],
        ):
            payload, _, cached = service._cached(
                "slow-fixture",
                4.0,
                lambda: {"ok": True},
            )

        self.assertEqual({"ok": True}, payload)
        self.assertFalse(cached)
        self.assertEqual(114.0, service._cache["slow-fixture"].expires_at)

    def test_negative_cache_hit_does_not_extend_expiry_or_repeat_upstream_call(self):
        calls = []

        def failing_fetch(url, headers=None):
            calls.append(url)
            raise OSError("fixture Fugle outage")

        service = LiveMarketService(
            fetch_json=failing_fetch,
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with patch.dict(
            os.environ,
            {
                "FUGLE_TAIEX_SYMBOL": "IX0001",
                "FUGLE_TPEX_SYMBOL": "IX0043",
            },
        ):
            with self.assertRaises(ValueError):
                service._load_fugle_quotes(["2330"])
            expiry = service._fugle_negative_cache["fugle-symbol:equity:2330"]
            with self.assertRaises(ValueError):
                service._load_fugle_quotes(["2330"])

        self.assertEqual(
            expiry,
            service._fugle_negative_cache["fugle-symbol:equity:2330"],
        )
        self.assertEqual(1, calls.count(FUGLE_QUOTE_URL.format(symbol="2330")))

    def test_concurrent_fugle_failures_are_single_flight_per_request_key(self):
        calls = []
        calls_lock = threading.Lock()

        def failing_fetch(url, headers=None):
            with calls_lock:
                calls.append(url)
            time.sleep(0.02)
            raise OSError("fixture Fugle outage")

        service = LiveMarketService(
            fetch_json=failing_fetch,
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        start = threading.Barrier(10)

        def load_quotes(_):
            start.wait()
            with self.assertRaises(ValueError):
                service._load_fugle_quotes(["2330"])

        with (
            patch.dict(
                os.environ,
                {
                    "FUGLE_TAIEX_SYMBOL": "IX0001",
                    "FUGLE_TPEX_SYMBOL": "IX0043",
                },
            ),
            ThreadPoolExecutor(max_workers=10) as executor,
        ):
            list(executor.map(load_quotes, range(10)))

        self.assertEqual(
            {
                FUGLE_QUOTE_URL.format(symbol="2330"),
                FUGLE_QUOTE_URL.format(symbol="IX0001"),
                FUGLE_QUOTE_URL.format(symbol="IX0043"),
            },
            set(calls),
        )
        self.assertEqual(3, len(calls))

    def test_benchmark_discovery_failure_is_negative_cached(self):
        calls = []

        def failing_fetch(url, headers=None):
            calls.append(url)
            raise OSError("fixture ticker discovery outage")

        service = LiveMarketService(
            fetch_json=failing_fetch,
            fugle_api_key="test-key",
        )
        deadline = time.monotonic() + 10
        first, first_errors = service._discover_fugle_benchmarks(
            {"X-API-KEY": "test-key"},
            deadline=deadline,
        )
        expiries = dict(service._fugle_negative_cache)
        second, second_errors = service._discover_fugle_benchmarks(
            {"X-API-KEY": "test-key"},
            deadline=deadline,
        )

        self.assertEqual([], first)
        self.assertEqual([], second)
        self.assertEqual(2, len(first_errors))
        self.assertEqual(2, len(second_errors))
        self.assertEqual(expiries, service._fugle_negative_cache)
        self.assertEqual(2, len(calls))

    def test_probe_fails_when_benchmark_discovery_uses_stale_fallback(self):
        fixture = _FixtureFetcher()
        fail_tickers = {"value": False}

        def flaky_fetch(url, headers=None):
            if fail_tickers["value"] and url.startswith(FUGLE_TICKERS_URL):
                raise OSError("fixture ticker refresh outage")
            return fixture(url, headers)

        service = LiveMarketService(
            fetch_json=flaky_fetch,
            provider="fugle",
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        first = service.probe(["2330"])
        self.assertTrue(first["ok"])
        for key, entry in list(service._cache.items()):
            if key.startswith("fugle-index-list:"):
                service._cache[key] = entry.__class__(
                    entry.payload,
                    entry.fetched_at,
                    0.0,
                )
        fail_tickers["value"] = True

        second = service.probe(["2330"])

        self.assertFalse(second["ok"])
        self.assertEqual("STALE", second["status"])
        self.assertTrue(second["errors"])
        self.assertFalse(service.health()["ready"])

    def test_fugle_default_transport_receives_remaining_deadline_as_timeout(self):
        captured = {}

        def fake_http(
            url,
            headers=None,
            *,
            timeout_seconds=None,
            allow_redirects=True,
            compatibility_tls=True,
        ):
            captured["timeout_seconds"] = timeout_seconds
            captured["allow_redirects"] = allow_redirects
            captured["compatibility_tls"] = compatibility_tls
            return {}

        with patch(
            "taiwan_stock_analysis.live_market._http_json",
            side_effect=fake_http,
        ):
            service = LiveMarketService(fugle_api_key="test-key")
            service._fugle_json(
                FUGLE_QUOTE_URL.format(symbol="2330"),
                {"X-API-KEY": "test-key"},
                deadline=time.monotonic() + 0.25,
            )

        self.assertGreater(captured["timeout_seconds"], 0)
        self.assertLessEqual(captured["timeout_seconds"], 0.25)
        self.assertFalse(captured["allow_redirects"])
        self.assertFalse(captured["compatibility_tls"])

    def test_authenticated_transport_does_not_follow_redirects(self):
        received_api_keys = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_api_keys.append(self.headers.get("X-API-KEY"))
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()
        target_url = f"http://127.0.0.1:{target.server_port}/target"

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", target_url)
                self.end_headers()

            def log_message(self, format, *args):
                return

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        redirect_thread = threading.Thread(
            target=redirect.serve_forever,
            daemon=True,
        )
        redirect_thread.start()
        try:
            with self.assertRaises(HTTPError) as caught:
                _http_json(
                    f"http://127.0.0.1:{redirect.server_port}/redirect",
                    {"X-API-KEY": "must-not-leak"},
                    allow_redirects=False,
                )
            self.assertEqual(302, caught.exception.code)
            caught.exception.close()
            self.assertEqual([], received_api_keys)
        finally:
            redirect.shutdown()
            target.shutdown()
            redirect_thread.join(timeout=5)
            target_thread.join(timeout=5)
            redirect.server_close()
            target.server_close()

    def test_fugle_tls_context_enables_x509_strict_when_available(self):
        class FakeContext:
            verify_flags = 0

        context = FakeContext()
        strict_flag = 32
        with (
            patch(
                "taiwan_stock_analysis.live_market.ssl.create_default_context",
                return_value=context,
            ),
            patch(
                "taiwan_stock_analysis.live_market.ssl.VERIFY_X509_STRICT",
                strict_flag,
                create=True,
            ),
        ):
            returned = _verified_ssl_context(compatibility_tls=False)

        self.assertIs(context, returned)
        self.assertEqual(strict_flag, context.verify_flags & strict_flag)

    def test_licensed_public_fugle_path_fetches_both_market_benchmarks(self):
        fetcher = _FixtureFetcher()
        service = LiveMarketService(
            public_mode=True,
            fetch_json=fetcher,
            fugle_api_key="test-key",
            fugle_redisplay_licensed=True,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330"])

        self.assertEqual("LIVE", snapshot["status"])
        self.assertEqual({"t00", "o00"}, {row["symbol"] for row in snapshot["indices"]})
        self.assertEqual("LICENSED_LIVE", snapshot["provider"]["mode"])
        ticker_calls = [url for url, _ in fetcher.calls if url.startswith(FUGLE_TICKERS_URL)]
        self.assertEqual(2, len(ticker_calls))

    def test_fugle_refresh_failure_retains_expired_symbol_rows_as_stale(self):
        fixture = _FixtureFetcher()
        should_fail = {"value": False}

        def flaky_fetch(url, headers=None):
            if should_fail["value"] and (
                url.startswith(FUGLE_TICKERS_URL)
                or "/intraday/quote/" in url
            ):
                raise OSError("fixture Fugle outage")
            return fixture(url, headers)

        service = LiveMarketService(
            public_mode=True,
            fetch_json=flaky_fetch,
            fugle_api_key="test-key",
            fugle_redisplay_licensed=True,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            first = service.snapshot(["2330"])
            for key, entry in list(service._cache.items()):
                service._cache[key] = entry.__class__(
                    entry.payload,
                    entry.fetched_at,
                    0.0,
                )
            should_fail["value"] = True
            second = service.snapshot(["2330"])

        self.assertEqual("LIVE", first["status"])
        self.assertEqual("STALE", second["status"])
        self.assertEqual({"2330"}, {row["symbol"] for row in second["quotes"]})
        self.assertEqual({"t00", "o00"}, {row["symbol"] for row in second["indices"]})
        self.assertTrue(all(row["status"] == "STALE" for row in second["quotes"] + second["indices"]))

    def test_after_close_same_session_is_eod(self):
        fetcher = _FixtureFetcher()

        def closed_fetch(url, headers=None):
            payload = fetcher(url, headers)
            if url.startswith(TWSE_MIS_URL):
                for row in payload["msgArray"]:
                    row["t"] = "13:33:00" if row["c"] in {"t00", "o00"} else "13:30:00"
            return payload

        service = LiveMarketService(
            fetch_json=closed_fetch,
            clock=lambda: datetime(2026, 7, 29, 18, 0, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330"])

        self.assertEqual("EOD", snapshot["status"])
        self.assertEqual(60, snapshot["refresh_after_seconds"])

    def test_frozen_intraday_indices_are_not_promoted_to_eod_after_close(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            clock=lambda: datetime(2026, 7, 29, 18, 0, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330"])

        self.assertEqual("STALE", snapshot["status"])
        self.assertTrue(all(row["status"] == "STALE" for row in snapshot["indices"]))

    def test_market_summary_requires_both_fresh_benchmarks(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        one_index = {
            "symbol": "t00",
            "change_percent": 2.0,
            "status": "LIVE",
            "session_date": "2026-07-29",
            "source_event_time": "2026-07-29T10:05:00+08:00",
        }
        summary = build_market_summary([one_index], [], now=now)

        self.assertEqual("STALE", summary["status"])
        self.assertEqual("市場指數資料不完整", summary["regime"])
        self.assertIsNone(summary["temperature"])
        self.assertEqual("neutral", summary["strategy"])

    def test_market_summary_rejects_mixed_index_sessions_and_statuses(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        base = {
            "change_percent": 2.0,
            "source_event_time": "2026-07-29T10:05:00+08:00",
        }
        cases = (
            (
                {
                    **base,
                    "symbol": "t00",
                    "status": "LIVE",
                    "session_date": "2026-07-29",
                },
                {
                    **base,
                    "symbol": "o00",
                    "status": "LIVE",
                    "session_date": "2026-07-28",
                },
            ),
            (
                {
                    **base,
                    "symbol": "t00",
                    "status": "LIVE",
                    "session_date": "2026-07-29",
                },
                {
                    **base,
                    "symbol": "o00",
                    "status": "EOD",
                    "session_date": "2026-07-29",
                },
            ),
        )

        for taiex, otc in cases:
            with self.subTest(taiex=taiex, otc=otc):
                summary = build_market_summary([taiex, otc], [], now=now)
                self.assertEqual("STALE", summary["status"])
                self.assertEqual("市場指數資料不完整", summary["regime"])
                self.assertIsNone(summary["temperature"])
                self.assertIsNone(summary["average_change_percent"])
                self.assertEqual("neutral", summary["strategy"])

    def test_index_eod_requires_close_evidence_for_current_and_prior_sessions(self):
        current_session = datetime(2026, 7, 29, 10, 5, tzinfo=TAIPEI)
        current_now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        self.assertEqual(
            "EOD",
            _quote_status(
                current_session.date(),
                current_now,
                event_time=current_session,
                require_close_event=True,
                is_close=True,
            ),
        )

        weekend_now = datetime(2026, 8, 1, 9, 0, tzinfo=TAIPEI)
        prior_session = datetime(2026, 7, 31, 13, 33, tzinfo=TAIPEI)
        self.assertEqual(
            "EOD",
            _quote_status(
                prior_session.date(),
                weekend_now,
                event_time=prior_session,
                require_close_event=True,
            ),
        )
        self.assertEqual(
            "STALE",
            _quote_status(
                prior_session.date(),
                weekend_now,
                event_time=prior_session.replace(hour=10),
                require_close_event=True,
            ),
        )
        self.assertEqual(
            "LIVE",
            _quote_status(
                current_session.date(),
                current_session.replace(hour=13, minute=26),
                event_time=current_session.replace(hour=13, minute=25),
                require_close_event=True,
            ),
        )
        self.assertEqual(
            "STALE",
            _quote_status(
                prior_session.date(),
                weekend_now,
                event_time=None,
                require_close_event=True,
            ),
        )
        self.assertEqual(
            "EOD",
            _quote_status(
                current_session.date(),
                current_session.replace(hour=13, minute=34),
                event_time=current_session.replace(hour=13, minute=33),
                require_close_event=True,
            ),
        )

    def test_prior_index_close_is_stale_after_current_session_begins(self):
        now = datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI)
        prior_event = datetime(2026, 7, 28, 13, 33, tzinfo=TAIPEI)
        self.assertEqual(
            "STALE",
            _quote_status(
                prior_event.date(),
                now,
                event_time=prior_event,
                require_close_event=True,
                is_close=True,
            ),
        )
        indices = [
            {
                "symbol": symbol,
                "change_percent": 1.0,
                "status": "STALE",
                "session_date": "2026-07-28",
                "source_event_time": prior_event.isoformat(),
            }
            for symbol in ("t00", "o00")
        ]
        securities = [
            {
                "symbol": "2330",
                "change_percent": 2.0,
                "status": "LIVE",
                "session_date": "2026-07-29",
                "source_event_time": "2026-07-29T10:05:00+08:00",
            }
        ]
        summary = build_market_summary(indices, securities, now=now)
        self.assertEqual("STALE", summary["status"])
        self.assertEqual("2026-07-28", summary["session_date"])
        self.assertEqual("市場指數資料不完整", summary["regime"])
        self.assertIsNone(summary["temperature"])

    def test_long_holiday_prior_close_remains_eod_until_market_reopens(self):
        lunar_new_year_closed = {
            date(2026, 2, day)
            for day in (12, 13, 16, 17, 18, 19, 20)
        }
        prior_session = datetime(2026, 2, 11, 13, 33, tzinfo=TAIPEI)

        for now in (
            datetime(2026, 2, 18, 10, 0, tzinfo=TAIPEI),
            datetime(2026, 2, 23, 8, 30, tzinfo=TAIPEI),
        ):
            with self.subTest(now=now):
                self.assertEqual(
                    "EOD",
                    _quote_status(
                        prior_session.date(),
                        now,
                        event_time=prior_session,
                        require_close_event=True,
                        closed_dates=lunar_new_year_closed,
                    ),
                )

        self.assertEqual(
            "STALE",
            _quote_status(
                prior_session.date(),
                datetime(2026, 2, 23, 10, 0, tzinfo=TAIPEI),
                event_time=prior_session,
                require_close_event=True,
                closed_dates=lunar_new_year_closed,
            ),
        )

    def test_prior_equity_close_is_eod_before_open_and_stale_after_open(self):
        prior_session = datetime(2026, 7, 29, 13, 30, tzinfo=TAIPEI)
        for now in (
            datetime(2026, 7, 30, 0, 47, tzinfo=TAIPEI),
            datetime(2026, 7, 30, 8, 59, tzinfo=TAIPEI),
        ):
            with self.subTest(now=now):
                self.assertEqual(
                    "EOD",
                    _quote_status(
                        prior_session.date(),
                        now,
                        event_time=prior_session,
                    ),
                )
        self.assertEqual(
            "STALE",
            _quote_status(
                prior_session.date(),
                datetime(2026, 7, 30, 9, 0, tzinfo=TAIPEI),
                event_time=prior_session,
            ),
        )

    def test_snapshot_reclassifies_long_holiday_close_with_official_calendar(self):
        def fetcher(url, headers=None):
            del headers
            if url.startswith(TWSE_MIS_URL):
                return {
                    "rtcode": "0000",
                    "msgArray": [
                        {
                            "c": symbol,
                            "n": symbol,
                            "ex": exchange,
                            "z": price,
                            "y": previous,
                            "d": "20260211",
                            "t": "13:33:00",
                        }
                        for symbol, exchange, price, previous in (
                            ("t00", "tse", "34900", "34800"),
                            ("o00", "otc", "270", "268"),
                        )
                    ],
                }
            if url == TWSE_HOLIDAY_URL:
                return [
                    {
                        "Date": f"11502{day:02d}",
                        "Name": "春節休市",
                        "Description": "無交易",
                    }
                    for day in (12, 13, 16, 17, 18, 19, 20)
                ]
            raise AssertionError(url)

        service = LiveMarketService(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 2, 23, 8, 30, tzinfo=TAIPEI),
        )
        empty = _LoadedRows([], upstreams=({"id": "fixture", "status": "FRESH"},))
        flow = _LoadedRows(
            [{"stock_id": "2330", "date": "2026-02-11", "total_net": 1}],
            upstreams=(
                {
                    "id": "twse-t86",
                    "status": "STALE",
                    "row_count": 1,
                    "latest_event_at": "2026-02-11",
                },
            ),
        )
        with (
            patch.object(service, "_load_news", return_value=empty),
            patch.object(service, "_load_alerts", return_value=empty),
            patch.object(service, "_load_fund_flow", return_value=flow),
        ):
            snapshot = service.snapshot([])

        self.assertEqual("EOD", snapshot["status"])
        self.assertEqual("EOD", snapshot["market"]["status"])
        self.assertEqual(
            {"EOD"},
            {row["status"] for row in snapshot["indices"]},
        )
        self.assertEqual(
            "FRESH",
            snapshot["source_status"]["trading_calendar"]["status"],
        )
        self.assertTrue(
            snapshot["source_status"]["quotes"]["upstreams"][0][
                "calendar_adjusted"
            ]
        )
        self.assertEqual(
            "EOD",
            snapshot["source_status"]["fund_flow"]["status"],
        )
        self.assertEqual(
            "STALE",
            snapshot["source_status"]["fund_flow"]["upstreams"][0][
                "transport_status"
            ],
        )

    def test_snapshot_handles_single_midweek_holiday_but_not_next_open_day(self):
        def fetcher(url, headers=None):
            del headers
            if url.startswith(TWSE_MIS_URL):
                return {
                    "rtcode": "0000",
                    "msgArray": [
                        {
                            "c": symbol,
                            "n": symbol,
                            "ex": exchange,
                            "z": price,
                            "y": previous,
                            "d": "20260406",
                            "t": "13:33:00",
                        }
                        for symbol, exchange, price, previous in (
                            ("t00", "tse", "34900", "34800"),
                            ("o00", "otc", "270", "268"),
                        )
                    ],
                }
            if url == TWSE_HOLIDAY_URL:
                return [
                    {
                        "Date": "1150407",
                        "Name": "休市",
                        "Description": "無交易",
                    }
                ]
            raise AssertionError(url)

        empty = _LoadedRows([], upstreams=({"id": "fixture", "status": "FRESH"},))
        for now, expected in (
            (datetime(2026, 4, 7, 10, 0, tzinfo=TAIPEI), "EOD"),
            (datetime(2026, 4, 8, 10, 0, tzinfo=TAIPEI), "STALE"),
        ):
            service = LiveMarketService(fetch_json=fetcher, clock=lambda now=now: now)
            with (
                patch.object(service, "_load_news", return_value=empty),
                patch.object(service, "_load_alerts", return_value=empty),
                patch.object(service, "_load_fund_flow", return_value=empty),
            ):
                snapshot = service.snapshot([])
            with self.subTest(now=now):
                self.assertEqual(expected, snapshot["market"]["status"])
                self.assertEqual(
                    {expected},
                    {row["status"] for row in snapshot["indices"]},
                )

    def test_provider_gate_enforces_shared_budget_and_deadline(self):
        gate = _ProviderGate(max_calls=2, window_seconds=60, concurrency=1)
        deadline = 10**12
        self.assertEqual("one", gate.call(lambda: "one", deadline=deadline))
        self.assertEqual("two", gate.call(lambda: "two", deadline=deadline))
        with self.assertRaisesRegex(TimeoutError, "budget exhausted"):
            gate.call(lambda: "three", deadline=deadline)
        with self.assertRaisesRegex(TimeoutError, "deadline"):
            gate.call(lambda: "late", deadline=0)

    def test_provider_admission_rejection_does_not_create_negative_cache(self):
        service = LiveMarketService(
            fetch_json=_FixtureFetcher(),
            fugle_api_key="test-key",
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        service._fugle_gate = _ProviderGate(
            max_calls=1,
            window_seconds=60,
            concurrency=1,
        )
        with patch.dict(
            os.environ,
            {
                "FUGLE_TAIEX_SYMBOL": "IX0001",
                "FUGLE_TPEX_SYMBOL": "IX0043",
            },
        ):
            loaded = service._load_fugle_quotes(["2330"])

        self.assertEqual(["t00"], [row["symbol"] for row in loaded.rows])
        self.assertEqual({}, service._fugle_negative_cache)

    def test_frozen_and_future_intraday_events_are_not_labeled_live(self):
        for now in (
            datetime(2026, 7, 29, 10, 10, tzinfo=TAIPEI),
            datetime(2026, 7, 29, 10, 0, tzinfo=TAIPEI),
        ):
            with self.subTest(now=now):
                service = LiveMarketService(
                    fetch_json=_FixtureFetcher(),
                    clock=lambda now=now: now,
                )
                with (
                    patch.object(service, "_load_news", return_value=[]),
                    patch.object(service, "_load_alerts", return_value=[]),
                    patch.object(service, "_load_fund_flow", return_value=[]),
                ):
                    snapshot = service.snapshot(["2330"])
                self.assertEqual("STALE", snapshot["status"])
                self.assertEqual("STALE", snapshot["indices"][0]["status"])

    def test_failed_refresh_cannot_keep_cached_market_headline_live(self):
        fixture = _FixtureFetcher()
        should_fail = {"value": False}

        def flaky_fetch(url, headers=None):
            if should_fail["value"] and url.startswith(TWSE_MIS_URL):
                raise OSError("fixture quote outage")
            return fixture(url, headers)

        service = LiveMarketService(
            fetch_json=flaky_fetch,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            first = service.snapshot(["2330"])
            quote_key = next(key for key in service._cache if key.startswith("quotes:"))
            entry = service._cache[quote_key]
            service._cache[quote_key] = entry.__class__(
                entry.payload,
                entry.fetched_at,
                0.0,
            )
            should_fail["value"] = True
            second = service.snapshot(["2330"])

        self.assertEqual("LIVE", first["status"])
        self.assertEqual("STALE", second["status"])
        self.assertEqual("行情快取已過期", second["market"]["regime"])
        self.assertEqual("STALE", second["source_status"]["quotes"]["status"])

    def test_no_trade_does_not_manufacture_zero_percent_current_quote(self):
        fixture = _FixtureFetcher()

        def no_trade_fetch(url, headers=None):
            payload = fixture(url, headers)
            if url.startswith(TWSE_MIS_URL):
                for row in payload["msgArray"]:
                    if row["c"] == "2330":
                        row["z"] = "-"
                        row["pz"] = "-"
            return payload

        service = LiveMarketService(
            fetch_json=no_trade_fetch,
            clock=lambda: datetime(2026, 7, 29, 10, 6, tzinfo=TAIPEI),
        )
        with (
            patch.object(service, "_load_news", return_value=[]),
            patch.object(service, "_load_alerts", return_value=[]),
            patch.object(service, "_load_fund_flow", return_value=[]),
        ):
            snapshot = service.snapshot(["2330"])

        quote = snapshot["quotes"][0]
        self.assertIsNone(quote["price"])
        self.assertEqual(2200, quote["previous_close"])
        self.assertIsNone(quote["change"])
        self.assertIsNone(quote["change_percent"])

    def test_tpex_disposition_reason_schema_is_preserved(self):
        fixture = _FixtureFetcher()

        def tpex_disposition_fetch(url, headers=None):
            if url == TPEX_DISPOSITION_URL:
                return [
                    {
                        "SecuritiesCompanyCode": "6223",
                        "CompanyName": "旺矽",
                        "Date": "1150729",
                        "DispositionPeriod": "1150729~1150805",
                        "DispositionReasons": "最近十個營業日累積異常",
                        "DisposalCondition": "人工管制撮合",
                    }
                ]
            return fixture(url, headers)

        service = LiveMarketService(
            fetch_json=tpex_disposition_fetch,
            clock=lambda: datetime(2026, 7, 29, 18, 0, tzinfo=TAIPEI),
        )
        with patch.object(service, "_load_fund_flow", return_value=[]):
            snapshot = service.snapshot(["6223"])

        alert = next(row for row in snapshot["alerts"] if row["symbol"] == "6223")
        self.assertIn("最近十個營業日", alert["reason"])


if __name__ == "__main__":
    unittest.main()
