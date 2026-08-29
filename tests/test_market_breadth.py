import copy
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from taiwan_stock_analysis.market_breadth import (
    TPEX_DAILY_URL,
    TPEX_FINANCIAL_URL,
    TPEX_PROFILE_URL,
    TPEX_REVENUE_URL,
    TPEX_VALUATION_URL,
    TWSE_DAILY_FALLBACK_URL,
    TWSE_FINANCIAL_URL,
    TWSE_HOLIDAY_URL,
    TWSE_PROFILE_URL,
    TWSE_REVENUE_URL,
    TWSE_VALUATION_URL,
    MarketBreadthService,
    build_industry_summaries,
    parse_tpex_daily_quotes,
    parse_twse_closed_dates,
    parse_twse_rwd_quotes,
)


TAIPEI = timezone(timedelta(hours=8))


class _BreadthFetcher:
    def __init__(
        self,
        *,
        tpex_date="1150729",
        twse_date="20260729",
        empty_urls=(),
        holiday_rows=None,
    ):
        self.calls = []
        self.tpex_date = tpex_date
        self.twse_date = twse_date
        self.empty_urls = set(empty_urls)
        self.holiday_rows = holiday_rows or [
            {
                "Name": "中華民國開國紀念日",
                "Date": "1150101",
                "Description": "依規定放假1日。",
            }
        ]

    def __call__(self, url):
        self.calls.append(url)
        if url in self.empty_urls:
            return []
        if url == TWSE_HOLIDAY_URL:
            return self.holiday_rows
        if url == TWSE_PROFILE_URL:
            return [
                {
                    "出表日期": "1150729",
                    "公司代號": "2330",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                    "公司簡稱": "台積電",
                    "產業別": "24",
                }
            ]
        if url == TPEX_PROFILE_URL:
            return [
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "6488",
                    "CompanyName": "環球晶圓股份有限公司",
                    "CompanyAbbreviation": "環球晶",
                    "SecuritiesIndustryCode": "24",
                }
            ]
        if url == TWSE_FINANCIAL_URL:
            return [
                {
                    "出表日期": "1150728",
                    "年度": "115",
                    "季別": "1",
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "產業別": "半導體業",
                    "基本每股盈餘(元)": "12.50",
                    "營業收入": "100000",
                    "營業利益": "45000",
                    "稅後淨利": "38000",
                }
            ]
        if url == TPEX_FINANCIAL_URL:
            return [
                {
                    "Date": "1150728",
                    "Year": "115",
                    "季別": "1",
                    "SecuritiesCompanyCode": "6488",
                    "CompanyName": "環球晶",
                    "產業別": "半導體業",
                    "基本每股盈餘": "3.97",
                    "營業收入": "90000",
                    "營業利益": "18000",
                    "稅後淨利": "15000",
                }
            ]
        if url == TWSE_VALUATION_URL:
            return [
                {
                    "Date": "1150728",
                    "Code": "2330",
                    "PEratio": "30.65",
                    "DividendYield": "0.96",
                    "PBratio": "10.04",
                }
            ]
        if url == TPEX_VALUATION_URL:
            return [
                {
                    "Date": self.tpex_date,
                    "SecuritiesCompanyCode": "6488",
                    "PriceEarningRatio": "53.30",
                    "YieldRatio": "0.89",
                    "PriceBookRatio": "4.42",
                }
            ]
        if url == TWSE_REVENUE_URL:
            return [
                {
                    "資料年月": "11506",
                    "公司代號": "2330",
                    "營業收入-當月營收": "50000",
                    "營業收入-上月比較增減(%)": "1.2",
                    "營業收入-去年同月增減(%)": "8.8",
                }
            ]
        if url == TPEX_REVENUE_URL:
            return [
                {
                    "資料年月": "11506",
                    "公司代號": "6488",
                    "營業收入-當月營收": "12000",
                    "營業收入-上月比較增減(%)": "-2.2",
                    "營業收入-去年同月增減(%)": "4.4",
                }
            ]
        if url == TPEX_DAILY_URL:
            return [
                {
                    "Date": self.tpex_date,
                    "SecuritiesCompanyCode": "6488",
                    "CompanyName": "環球晶",
                    "Close": "440",
                    "Change": "+10",
                    "Open": "430",
                    "High": "445",
                    "Low": "425",
                    "TradingShares": "5000000",
                    "TransactionAmount": "2200000000",
                }
            ]
        if url == TWSE_DAILY_FALLBACK_URL:
            return []
        if url.startswith("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?"):
            return _twse_rwd_fixture(self.twse_date)
        raise AssertionError(f"unexpected URL: {url}")


def _twse_rwd_fixture(session_date="20260729"):
    return {
        "stat": "OK",
        "date": session_date,
        "tables": [
            {
                "title": "每日收盤行情",
                "fields": [
                    "證券代號",
                    "證券名稱",
                    "成交股數",
                    "成交筆數",
                    "成交金額",
                    "開盤價",
                    "最高價",
                    "最低價",
                    "收盤價",
                    "漲跌(+/-)",
                    "漲跌價差",
                ],
                "data": [
                    [
                        "2330",
                        "台積電",
                        "10,000,000",
                        "99,999",
                        "22,000,000,000",
                        "2,260",
                        "2,280",
                        "2,180",
                        "2,200",
                        "<p style=color:green>-</p>",
                        "80",
                    ]
                ],
            }
        ],
    }


def _support_fixture():
    return {
        "alerts": [
            {
                "symbol": "6488",
                "type": "disposition",
                "active": True,
                "reason": "處置期間",
            }
        ],
        "fund_flow": [
            {"stock_id": "2330", "date": "2026-07-29", "total_net": 123456},
            {"stock_id": "6488", "date": "2026-07-29", "total_net": -999},
        ],
        "source_status": {
            "alerts": {"status": "FRESH"},
            "fund_flow": {"status": "EOD"},
        },
        "errors": [],
    }


def _support_with_live_quotes(
    *,
    include_tpex=True,
    tpex_source_status="LIVE",
    fallback=False,
):
    support = _support_fixture()
    support["live_quotes"] = [
        {
            "symbol": "2330",
            "name": "TSMC",
            "market": "TWSE",
            "price": 2260.0,
            "reference_price": 2200.0,
            "change": 60.0,
            "change_percent": 2.727273,
            "open": 2210.0,
            "high": 2270.0,
            "low": 2205.0,
            "volume": 12_000_000.0,
            "trade_value": 27_120_000_000.0,
            "status": "LIVE",
            "session_date": "2026-07-30",
            "source_event_time": "2026-07-30T10:00:00+08:00",
            "source": "Fubon Neo MarketData",
        }
    ]
    if include_tpex:
        support["live_quotes"].append(
            {
                "symbol": "6488",
                "name": "GlobalWafers",
                "market": "TPEX",
                "price": 450.0,
                "reference_price": 440.0,
                "change": 10.0,
                "change_percent": 2.272727,
                "open": 442.0,
                "high": 452.0,
                "low": 440.0,
                "volume": 6_000_000.0,
                "trade_value": 2_700_000_000.0,
                "status": "LIVE",
                "session_date": "2026-07-30",
                "source_event_time": "2026-07-30T10:00:01+08:00",
                "source": "Fubon Neo MarketData",
            }
        )
    support["source_status"]["live_quotes"] = {
        "status": "LIVE",
        "fallback": fallback,
        "partial": tpex_source_status != "LIVE",
        "upstreams": [
            {
                "id": "fubon-snapshot:TSE",
                "status": "LIVE",
                "row_count": 1,
            },
            {
                "id": "fubon-snapshot:OTC",
                "status": tpex_source_status,
                "row_count": 1 if include_tpex else 0,
            },
        ],
    }
    return support


def _market_service(**kwargs):
    return MarketBreadthService(
        minimum_catalog_counts={"TWSE": 1, "TPEX": 1},
        **kwargs,
    )


class MarketBreadthTests(unittest.TestCase):
    def test_live_overlay_refreshes_without_refetching_official_baseline_and_reverts(self):
        tick = {"value": 100.0}
        support_calls = {"count": 0}

        def support_loader():
            support_calls["count"] += 1
            if support_calls["count"] <= 2:
                support = _support_with_live_quotes()
                if support_calls["count"] == 2:
                    support["live_quotes"][0]["price"] = 2300.0
                    support["live_quotes"][0]["change"] = 100.0
                    support["live_quotes"][0]["change_percent"] = 4.545455
                    support["live_quotes"][0][
                        "source_event_time"
                    ] = "2026-07-30T10:00:06+08:00"
                return support
            support = _support_fixture()
            support["live_quotes"] = []
            support["source_status"]["live_quotes"] = {
                "status": "UNAVAILABLE",
                "fallback": False,
                "upstreams": [
                    {
                        "id": "fubon-snapshot:TSE",
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                    },
                    {
                        "id": "fubon-snapshot:OTC",
                        "status": "UNAVAILABLE",
                        "row_count": 0,
                    },
                ],
            }
            support["errors"] = ["fubon-full-market: authentication failed"]
            return support

        fetcher = _BreadthFetcher()
        service = _market_service(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
            supporting_loader=support_loader,
            cache_seconds=300,
            live_overlay_seconds=5,
        )
        with patch(
            "taiwan_stock_analysis.market_breadth.time.monotonic",
            side_effect=lambda: tick["value"],
        ):
            initial = service.snapshot()
            official_call_count = len(fetcher.calls)
            support_after_initial = support_calls["count"]

            tick["value"] = 104.0
            before_short_expiry = service.snapshot()
            support_before_short_expiry = support_calls["count"]

            tick["value"] = 106.0
            refreshed = service.snapshot()
            support_after_refresh = support_calls["count"]

            tick["value"] = 112.0
            unavailable = service.snapshot()

        initial_by_symbol = {
            row["symbol"]: row for row in initial["full_market"]
        }
        refreshed_by_symbol = {
            row["symbol"]: row for row in refreshed["full_market"]
        }
        unavailable_by_symbol = {
            row["symbol"]: row for row in unavailable["full_market"]
        }
        self.assertEqual("LIVE", initial["status"])
        self.assertTrue(initial["live_overlay_enabled"])
        self.assertEqual(5.0, initial["refresh_after_seconds"])
        self.assertEqual(2260.0, initial_by_symbol["2330"]["price"])
        self.assertEqual(1, support_after_initial)
        self.assertEqual(1, support_before_short_expiry)
        self.assertEqual(2, support_after_refresh)
        self.assertEqual(2260.0, {
            row["symbol"]: row
            for row in before_short_expiry["full_market"]
        }["2330"]["price"])
        self.assertEqual(2300.0, refreshed_by_symbol["2330"]["price"])
        self.assertEqual("LIVE", refreshed["status"])
        self.assertEqual("EOD", unavailable["status"])
        self.assertEqual("EOD_FULL+LIVE_PAGE", unavailable["mode"])
        self.assertEqual(2200.0, unavailable_by_symbol["2330"]["price"])
        self.assertEqual("EOD", unavailable_by_symbol["2330"]["quote_status"])
        self.assertEqual(0, unavailable["coverage"]["live_quoted_total"])
        self.assertFalse(unavailable["coverage"]["live_full_coverage"])
        self.assertEqual(2, unavailable["coverage"]["official_quoted_total"])
        self.assertEqual(1.0, unavailable["coverage"]["official_ratio"])
        self.assertEqual(
            2,
            unavailable["industry_summaries"][0]["quoted_count"],
        )
        self.assertEqual(
            "2026-07-29",
            unavailable["industry_summaries"][0]["session_date"],
        )
        self.assertEqual(
            "UNAVAILABLE",
            unavailable["source_status"]["live_quotes"]["status"],
        )
        self.assertIn(
            "authentication failed",
            " ".join(unavailable["live_errors"]),
        )
        self.assertEqual(3, support_calls["count"])
        self.assertEqual(official_call_count, len(fetcher.calls))
        self.assertEqual(5.0, service.health()["live_overlay_seconds"])

    def test_fubon_full_market_overlay_is_live_only_with_two_healthy_markets(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
            supporting_loader=_support_with_live_quotes,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertEqual("LIVE", payload["status"])
        self.assertEqual("LIVE_FULL+OFFICIAL_EOD", payload["mode"])
        self.assertTrue(payload["live_session_fresh"])
        self.assertTrue(payload["live_cross_market_comparable"])
        self.assertEqual(
            {"TWSE": "2026-07-30", "TPEX": "2026-07-30"},
            payload["live_session_dates"],
        )
        self.assertEqual(2, payload["coverage"]["quoted_total"])
        self.assertEqual(1.0, payload["coverage"]["ratio"])
        self.assertEqual(2, payload["coverage"]["official_quoted_total"])
        self.assertEqual(1.0, payload["coverage"]["official_ratio"])
        self.assertEqual(
            {"TWSE": 1, "TPEX": 1},
            payload["coverage"]["official_market_quoted_counts"],
        )
        self.assertEqual(2, payload["coverage"]["live_quoted_total"])
        self.assertEqual(1.0, payload["coverage"]["live_ratio"])
        self.assertTrue(payload["coverage"]["live_full_coverage"])
        self.assertEqual(
            {"TWSE": 1, "TPEX": 1},
            payload["coverage"]["live_market_quoted_counts"],
        )
        self.assertEqual(2260.0, by_symbol["2330"]["price"])
        self.assertEqual("LIVE", by_symbol["2330"]["quote_status"])
        self.assertEqual("EOD", by_symbol["2330"]["official_quote_status"])
        self.assertEqual(
            "2026-07-29",
            by_symbol["2330"]["official_session_date"],
        )
        self.assertEqual(
            "Fubon Neo MarketData",
            by_symbol["2330"]["quote_source"],
        )
        self.assertEqual(2, payload["industry_summaries"][0]["quoted_count"])
        self.assertEqual(
            "2026-07-30",
            payload["industry_summaries"][0]["session_date"],
        )
        self.assertTrue(
            payload["source_status"]["live_quotes"]["authoritative"]
        )
        self.assertTrue(service.health()["ready"])

    def test_partial_fubon_market_overlays_rows_without_claiming_live_full(self):
        support = _support_with_live_quotes(
            include_tpex=False,
            tpex_source_status="UNAVAILABLE",
        )
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertEqual("EOD", payload["status"])
        self.assertEqual("EOD_FULL+LIVE_PAGE", payload["mode"])
        self.assertFalse(payload["coverage"]["live_full_coverage"])
        self.assertEqual(1, payload["coverage"]["live_quoted_total"])
        self.assertEqual(
            {"TWSE": 1, "TPEX": 0},
            payload["coverage"]["live_market_quoted_counts"],
        )
        self.assertEqual("LIVE", by_symbol["2330"]["quote_status"])
        self.assertEqual("EOD", by_symbol["6488"]["quote_status"])
        self.assertFalse(
            payload["source_status"]["live_quotes"]["authoritative"]
        )
        self.assertEqual(
            "PARTIAL",
            payload["source_status"]["live_quotes"]["coverage_status"],
        )
        self.assertEqual(2, payload["industry_summaries"][0]["quoted_count"])
        self.assertEqual(
            "2026-07-29",
            payload["industry_summaries"][0]["session_date"],
        )

    def test_fubon_fallback_rows_do_not_override_official_eod(self):
        support = _support_with_live_quotes(fallback=True)
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 30, 10, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertEqual("EOD", payload["status"])
        self.assertFalse(payload["coverage"]["live_full_coverage"])
        self.assertEqual(0, payload["coverage"]["live_quoted_total"])
        self.assertEqual(2200.0, by_symbol["2330"]["price"])
        self.assertEqual("EOD", by_symbol["2330"]["quote_status"])

    def test_builds_full_market_catalog_quotes_fundamentals_and_industries(self):
        fetcher = _BreadthFetcher()
        service = _market_service(
            fetch_json=fetcher,
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )
        self.assertFalse(service.health()["ok"])

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertTrue(payload["ok"])
        self.assertEqual("EOD", payload["status"])
        self.assertTrue(payload["cross_market_comparable"])
        self.assertEqual(2, payload["coverage"]["catalog_total"])
        self.assertEqual(
            {"TWSE": 1, "TPEX": 1},
            payload["coverage"]["market_catalog_counts"],
        )
        self.assertEqual(2, payload["coverage"]["quoted_total"])
        self.assertEqual(1.0, payload["coverage"]["ratio"])
        self.assertEqual(2, len(payload["market_catalog"]))
        self.assertEqual(-80.0, by_symbol["2330"]["change"])
        self.assertAlmostEqual(-3.50877, by_symbol["2330"]["change_percent"], places=4)
        self.assertEqual(12.5, by_symbol["2330"]["eps"])
        self.assertEqual(8.8, by_symbol["2330"]["revenue_yoy_percent"])
        self.assertEqual(123456, by_symbol["2330"]["institutional_net"])
        self.assertEqual("MATCHED", by_symbol["2330"]["institutional_status"])
        self.assertTrue(by_symbol["6488"]["disposition"])
        self.assertEqual(1, len(payload["industry_summaries"]))
        self.assertEqual(2, payload["industry_summaries"][0]["quoted_count"])
        self.assertTrue(service.health()["ok"])
        self.assertTrue(service.health()["ready"])

        cached = service.snapshot()
        self.assertTrue(cached["cached"])
        self.assertEqual(len(fetcher.calls), len(set(fetcher.calls)))

    def test_cross_market_session_mismatch_is_partial_and_excludes_older_quote_from_industry(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(tpex_date="1150728"),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )

        payload = service.snapshot()

        self.assertEqual("PARTIAL", payload["status"])
        self.assertFalse(payload["cross_market_comparable"])
        self.assertEqual({"TWSE": "2026-07-29", "TPEX": "2026-07-28"}, payload["session_dates"])
        self.assertEqual(1, payload["industry_summaries"][0]["quoted_count"])

    def test_previous_session_is_eod_before_open_but_stale_after_next_close(self):
        cases = (
            (datetime(2026, 7, 30, 0, 13, tzinfo=TAIPEI), "EOD", 2),
            (datetime(2026, 7, 30, 18, 0, tzinfo=TAIPEI), "PARTIAL", 0),
        )
        for now, expected_status, expected_quoted in cases:
            with self.subTest(now=now):
                service = _market_service(
                    fetch_json=_BreadthFetcher(),
                    clock=lambda now=now: now,
                    supporting_loader=_support_fixture,
                )

                payload = service.snapshot()

                self.assertEqual(expected_status, payload["status"])
                self.assertEqual(
                    expected_status == "EOD",
                    payload["session_fresh"],
                )
                self.assertEqual(
                    expected_quoted,
                    payload["coverage"]["quoted_total"],
                )

    def test_success_cache_expires_when_completed_session_advances(self):
        current = {
            "now": datetime(2026, 7, 30, 14, 59, tzinfo=TAIPEI),
        }
        fetcher = _BreadthFetcher()
        service = _market_service(
            fetch_json=fetcher,
            clock=lambda: current["now"],
            supporting_loader=_support_fixture,
            cache_seconds=300,
        )

        before_close = service.snapshot()
        calls_before_close = len(fetcher.calls)
        current["now"] = datetime(2026, 7, 30, 15, 1, tzinfo=TAIPEI)
        transitioned_health = service.health()
        after_close = service.snapshot()

        self.assertEqual("EOD", before_close["status"])
        self.assertEqual("2026-07-29", before_close["expected_session_date"])
        self.assertFalse(transitioned_health["ready"])
        self.assertFalse(transitioned_health["cache_session_current"])
        self.assertEqual("STALE", transitioned_health["status"])
        self.assertEqual(0, transitioned_health["quoted_total"])
        self.assertEqual("PARTIAL", after_close["status"])
        self.assertEqual("2026-07-30", after_close["expected_session_date"])
        self.assertFalse(after_close["session_fresh"])
        self.assertGreater(len(fetcher.calls), calls_before_close)

    def test_official_holiday_calendar_preserves_latest_preholiday_session(self):
        holiday_rows = [
            {
                "Name": "市場無交易",
                "Date": f"11502{day:02d}",
                "Description": "市場無交易",
            }
            for day in (12, 13, 16, 17, 18, 19, 20)
        ]
        support = _support_fixture()
        for row in support["fund_flow"]:
            row["date"] = "2026-02-11"
        support["source_status"]["fund_flow"] = {
            "status": "STALE",
            "fallback": False,
            "upstreams": [
                {
                    "id": "twse-t86",
                    "status": "STALE",
                    "latest_event_at": "2026-02-11",
                },
                {
                    "id": "tpex-3insti",
                    "status": "STALE",
                    "latest_event_at": "2026-02-11",
                },
            ],
        }
        service = _market_service(
            fetch_json=_BreadthFetcher(
                twse_date="20260211",
                tpex_date="1150211",
                holiday_rows=holiday_rows,
            ),
            clock=lambda: datetime(2026, 2, 18, 18, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()

        self.assertEqual("EOD", payload["status"])
        self.assertTrue(payload["session_fresh"])
        self.assertEqual(
            {"TWSE": "2026-02-11", "TPEX": "2026-02-11"},
            payload["session_dates"],
        )
        self.assertEqual("FRESH", payload["source_status"]["calendar"]["status"])
        self.assertTrue(payload["source_status"]["fund_flow"]["authoritative"])
        self.assertEqual("EOD", payload["source_status"]["fund_flow"]["status"])
        self.assertEqual(
            "STALE",
            payload["source_status"]["fund_flow"]["transport_status"],
        )

    def test_alert_activity_is_aligned_to_the_breadth_quote_session(self):
        support = _support_fixture()
        support["alerts"] = [
            {
                "symbol": "6488",
                "type": "notice",
                "active": False,
                "published_date": "2026-07-29",
                "reason": "latest completed session notice",
            }
        ]
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 30, 0, 13, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertEqual("EOD", payload["status"])
        self.assertTrue(by_symbol["6488"]["attention"])
        self.assertEqual(1, by_symbol["6488"]["alert_count"])

    def test_incomplete_catalog_fails_closed_instead_of_claiming_full_coverage(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(empty_urls={TPEX_PROFILE_URL}),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )

        payload = service.snapshot()

        self.assertFalse(payload["ok"])
        self.assertEqual("UNAVAILABLE", payload["status"])
        self.assertEqual("UNAVAILABLE", payload["mode"])
        self.assertTrue(
            any("catalog is incomplete" in error for error in payload["errors"])
        )

    def test_nonempty_but_truncated_first_catalog_fails_production_floor(self):
        service = MarketBreadthService(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )

        payload = service.snapshot()

        self.assertFalse(payload["ok"])
        self.assertEqual("UNAVAILABLE", payload["status"])
        self.assertFalse(service.health()["ok"])
        self.assertFalse(service.health()["ready"])
        self.assertTrue(service.health()["process_alive"])
        self.assertTrue(
            any(
                "incomplete or truncated" in error
                and "TWSE=1<1082" in error
                and "TPEX=1<883" in error
                for error in payload["errors"]
            )
        )

    def test_default_first_load_floor_rejects_old_truncated_counts(self):
        service = MarketBreadthService()
        with self.assertRaisesRegex(
            ValueError,
            r"TWSE=900<1082, TPEX=750<883",
        ):
            service._validate_catalog_counts({"TWSE": 900, "TPEX": 750})

        service._validate_catalog_counts({"TWSE": 1092, "TPEX": 891})
        self.assertFalse(
            service._catalog_matches_verified_baseline(
                {"TWSE": 1091, "TPEX": 891}
            )
        )
        self.assertTrue(
            service._catalog_matches_verified_baseline(
                {"TWSE": 1092, "TPEX": 891}
            )
        )

    def test_snapshot_deadline_returns_without_occupying_request_worker(self):
        release = threading.Event()
        service = _market_service(
            snapshot_deadline_seconds=0.05,
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
        )

        def blocking_build(now):
            del now
            release.wait(timeout=2)
            return {}

        try:
            with patch.object(service, "_build_snapshot", side_effect=blocking_build):
                started = time.monotonic()
                payload = service.snapshot()
                elapsed = time.monotonic() - started
                started = time.monotonic()
                cached = service.snapshot()
                cached_elapsed = time.monotonic() - started
        finally:
            release.set()

        self.assertLess(elapsed, 0.25)
        self.assertLess(cached_elapsed, 0.05)
        self.assertEqual("UNAVAILABLE", payload["status"])
        self.assertEqual("UNAVAILABLE", cached["status"])
        self.assertTrue(
            any("deadline exceeded" in error for error in payload["errors"])
        )

    def test_valuation_freshness_requires_completed_session_date(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )

        payload = service.snapshot()
        valuation = payload["source_status"]["valuation"]

        self.assertEqual("PARTIAL", valuation["status"])
        self.assertEqual("2026-07-29", valuation["expected_session_date"])
        self.assertEqual(
            {"TWSE": "2026-07-28", "TPEX": "2026-07-29"},
            valuation["effective_dates"],
        )
        self.assertEqual(["TPEX"], valuation["date_aligned_markets"])
        self.assertEqual(
            "2026-07-28",
            next(
                row["valuation_date"]
                for row in payload["full_market"]
                if row["symbol"] == "2330"
            ),
        )

    def test_partial_alert_sources_do_not_turn_unknown_into_false(self):
        cases = (
            (
                {
                    "status": "FRESH",
                    "partial": True,
                    "upstreams": [
                        {"id": "twse-disposition", "status": "FRESH"},
                        {"id": "tpex-disposition", "status": "UNAVAILABLE"},
                    ],
                },
                "PARTIAL",
            ),
            ({"status": "UNAVAILABLE"}, "UNAVAILABLE"),
        )
        for alert_source, expected_state in cases:
            with self.subTest(expected_state=expected_state):
                support = _support_fixture()
                support["source_status"]["alerts"] = alert_source
                service = _market_service(
                    fetch_json=_BreadthFetcher(),
                    clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
                    supporting_loader=lambda support=support: support,
                )

                payload = service.snapshot()
                by_symbol = {
                    row["symbol"]: row for row in payload["full_market"]
                }

                self.assertIsNone(by_symbol["6488"]["disposition"])
                self.assertEqual(expected_state, by_symbol["6488"]["alert_status"])
                self.assertIsNone(payload["coverage"]["active_alert_security_total"])
                self.assertFalse(
                    payload["source_status"]["alerts"]["authoritative"]
                )

    def test_notice_failure_does_not_disable_complete_disposition_feeds(self):
        support = _support_fixture()
        support["source_status"]["alerts"] = {
            "status": "FRESH",
            "partial": True,
            "upstreams": [
                {
                    "id": "twse-disposition",
                    "status": "FRESH",
                    "row_count": 16,
                    "latest_event_at": "2026-07-29",
                },
                {
                    "id": "tpex-disposition",
                    "status": "FRESH",
                    "row_count": 39,
                    "latest_event_at": "2026-07-29",
                },
                {
                    "id": "twse-notice",
                    "status": "UNAVAILABLE",
                    "row_count": 0,
                    "latest_event_at": "",
                },
                {
                    "id": "tpex-notice",
                    "status": "FRESH",
                    "row_count": 76,
                    "latest_event_at": "2026-07-29",
                },
            ],
        }
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["full_market"]}

        self.assertTrue(by_symbol["6488"]["disposition"])
        self.assertIsNone(by_symbol["6488"]["attention"])
        self.assertTrue(
            payload["source_status"]["disposition_alerts"]["authoritative"]
        )
        self.assertEqual(
            55,
            payload["source_status"]["disposition_alerts"]["row_count"],
        )
        self.assertEqual(
            "2026-07-29",
            payload["source_status"]["disposition_alerts"]["latest_event_at"],
        )
        self.assertFalse(
            payload["source_status"]["notice_alerts"]["authoritative"]
        )
        self.assertFalse(payload["source_status"]["alerts"]["authoritative"])
        self.assertEqual(1, payload["coverage"]["active_alert_security_total"])

    def test_partial_fund_flow_is_unknown_instead_of_no_row(self):
        support = _support_fixture()
        support["source_status"]["fund_flow"] = {
            "status": "EOD",
            "upstreams": [
                {"id": "twse-t86", "status": "EOD"},
                {"id": "tpex-3insti", "status": "STALE"},
            ],
        }
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()

        self.assertTrue(
            all(
                row["institutional_status"] == "PARTIAL"
                and row["institutional_net"] is None
                for row in payload["full_market"]
            )
        )
        self.assertIsNone(payload["coverage"]["institutional_total"])
        self.assertFalse(
            payload["source_status"]["fund_flow"]["authoritative"]
        )

    def test_fund_flow_requires_every_market_to_match_the_quote_session(self):
        support = _support_fixture()
        support["source_status"]["fund_flow"] = {
            "status": "EOD",
            "upstreams": [
                {
                    "id": "twse-t86",
                    "status": "EOD",
                    "latest_event_at": "2026-07-29",
                },
                {
                    "id": "tpex-3insti",
                    "status": "EOD",
                    "latest_event_at": "2026-07-28",
                },
            ],
        }
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=lambda: support,
        )

        payload = service.snapshot()

        self.assertFalse(
            payload["source_status"]["fund_flow"]["authoritative"]
        )
        self.assertFalse(
            payload["source_status"]["fund_flow"]["session_aligned"]
        )
        self.assertEqual(
            "2026-07-29",
            payload["source_status"]["fund_flow"]["required_event_date"],
        )
        self.assertIsNone(payload["coverage"]["institutional_total"])
        self.assertTrue(
            all(
                row["institutional_status"] == "PARTIAL"
                for row in payload["full_market"]
            )
        )

    def test_future_and_old_sessions_are_excluded_from_signals_and_coverage(self):
        cases = (
            ("20260730", "1150730", "FUTURE"),
            ("20260720", "1150720", "STALE"),
        )
        for twse_date, tpex_date, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                service = _market_service(
                    fetch_json=_BreadthFetcher(
                        twse_date=twse_date,
                        tpex_date=tpex_date,
                    ),
                    clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
                    supporting_loader=_support_fixture,
                )

                payload = service.snapshot()

                self.assertEqual("PARTIAL", payload["status"])
                self.assertFalse(payload["session_fresh"])
                self.assertEqual(0, payload["coverage"]["quoted_total"])
                self.assertEqual(0, payload["industry_summaries"][0]["quoted_count"])
                self.assertTrue(
                    all(
                        row["quote_status"] == expected_status
                        for row in payload["full_market"]
                    )
                )
                if expected_status == "FUTURE":
                    self.assertTrue(
                        all(row["price"] is None for row in payload["full_market"])
                    )

    def test_failed_refresh_uses_a_short_negative_cache(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )
        service.snapshot()
        service._cache_expires_at = 0.0

        with patch.object(
            service,
            "_build_snapshot",
            side_effect=OSError("upstream failed"),
        ) as build:
            first_fallback = service.snapshot()
            second_fallback = service.snapshot()

        self.assertEqual("STALE", first_fallback["status"])
        self.assertEqual("STALE", second_fallback["status"])
        self.assertEqual("STALE_FALLBACK+LIVE_PAGE", first_fallback["mode"])
        self.assertFalse(first_fallback["session_fresh"])
        self.assertEqual(0, first_fallback["coverage"]["quoted_total"])
        self.assertTrue(
            all(
                row["quote_status"] == "STALE"
                for row in first_fallback["full_market"]
            )
        )
        self.assertEqual(
            "STALE",
            first_fallback["source_status"]["quotes"]["status"],
        )
        self.assertEqual(1, build.call_count)

    def test_large_catalog_regression_does_not_overwrite_complete_cache(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )
        initial = service.snapshot()
        service._cache_payload["coverage"]["market_catalog_counts"] = {
            "TWSE": 100,
            "TPEX": 100,
        }
        service._cache_expires_at = 0.0
        regressed = copy.deepcopy(initial)
        regressed["coverage"]["market_catalog_counts"] = {
            "TWSE": 79,
            "TPEX": 100,
        }

        with patch.object(service, "_build_snapshot", return_value=regressed):
            fallback = service.snapshot()

        self.assertEqual("STALE", fallback["status"])
        self.assertEqual(
            {"TWSE": 100, "TPEX": 100},
            fallback["coverage"]["market_catalog_counts"],
        )
        self.assertTrue(
            any("regressed from 100 to 79" in error for error in fallback["errors"])
        )

    def test_optional_financial_components_report_per_market_partial_status(self):
        service = _market_service(
            fetch_json=_BreadthFetcher(
                empty_urls={
                    TPEX_FINANCIAL_URL,
                    TPEX_VALUATION_URL,
                    TPEX_REVENUE_URL,
                }
            ),
            clock=lambda: datetime(2026, 7, 29, 20, 0, tzinfo=TAIPEI),
            supporting_loader=_support_fixture,
        )

        payload = service.snapshot()

        for key in ("fundamentals", "valuation", "revenue"):
            self.assertEqual("PARTIAL", payload["source_status"][key]["status"])
            self.assertEqual(
                0,
                payload["source_status"][key]["market_counts"]["TPEX"],
            )
            for upstream in payload["source_status"][key]["upstreams"]:
                self.assertIn(upstream["market"].casefold(), upstream["label"].casefold())
                self.assertTrue(upstream["url"].startswith("https://"))

    def test_missing_quote_remains_missing_instead_of_zero(self):
        rows = build_industry_summaries(
            [
                {
                    "industry_name": "半導體業",
                    "quote_status": "MISSING",
                    "session_date": "",
                    "change_percent": None,
                }
            ],
            aggregate_session="2026-07-29",
        )

        self.assertEqual(1, rows[0]["stock_count"])
        self.assertEqual(0, rows[0]["quoted_count"])
        self.assertIsNone(rows[0]["average_change_percent"])
        self.assertIsNone(rows[0]["temperature"])

    def test_industry_summary_accepts_current_live_quotes(self):
        rows = build_industry_summaries(
            [
                {
                    "industry_name": "Semiconductor",
                    "quote_status": "LIVE",
                    "session_date": "2026-07-30",
                    "change_percent": 2.5,
                    "trade_value": 1000,
                }
            ],
            aggregate_session="2026-07-30",
        )

        self.assertEqual(1, rows[0]["quoted_count"])
        self.assertEqual(1, rows[0]["advance_count"])
        self.assertEqual(2.5, rows[0]["average_change_percent"])

    def test_parsers_reject_non_rows_and_preserve_signed_change(self):
        twse = parse_twse_rwd_quotes(_twse_rwd_fixture())
        tpex = parse_tpex_daily_quotes(
            [
                {
                    "Date": "1150729",
                    "SecuritiesCompanyCode": "6488",
                    "CompanyName": "環球晶",
                    "Close": "440",
                    "Change": "-10",
                    "Open": "450",
                    "High": "455",
                    "Low": "438",
                    "TradingShares": "--",
                    "TransactionAmount": "100",
                }
            ]
        )

        self.assertEqual(-80.0, twse[0]["change"])
        self.assertEqual(-10.0, tpex[0]["change"])
        self.assertIsNone(tpex[0]["volume"])
        self.assertEqual([], parse_twse_rwd_quotes({"stat": "查無資料"}))
        self.assertEqual([], parse_tpex_daily_quotes({"unexpected": True}))

    def test_holiday_parser_includes_makeup_holidays_but_not_special_open_days(self):
        closed = parse_twse_closed_dates(
            [
                {
                    "Name": "和平紀念日補假",
                    "Date": "1150227",
                    "Description": "",
                },
                {
                    "Name": "農曆春節前最後交易日",
                    "Date": "1150211",
                    "Description": "最後交易日",
                },
            ]
        )

        self.assertIn(date(2026, 2, 27), closed)
        self.assertNotIn(date(2026, 2, 11), closed)

    def test_manual_force_refresh_bypasses_the_success_cache(self):
        now = datetime(2026, 7, 29, 15, 0, tzinfo=TAIPEI)
        fetcher = _BreadthFetcher()
        service = MarketBreadthService(
            fetch_json=fetcher,
            clock=lambda: now,
            cache_seconds=300,
            minimum_catalog_counts={"TWSE": 1, "TPEX": 1},
        )

        first = service.snapshot()
        first_call_count = len(fetcher.calls)
        cached = service.snapshot()
        cached_call_count = len(fetcher.calls)
        refreshed = service.snapshot(force=True)

        self.assertEqual("EOD", first["status"])
        self.assertEqual(first_call_count, cached_call_count)
        self.assertGreater(len(fetcher.calls), cached_call_count)
        self.assertEqual("EOD", refreshed["status"])


if __name__ == "__main__":
    unittest.main()
