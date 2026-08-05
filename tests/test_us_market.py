import threading
import time
import unittest
from datetime import datetime, timezone

from taiwan_stock_analysis.us_market import (
    FINRA_SHORT_VOLUME_URL,
    NASDAQ_LISTED_URL,
    NASDAQ_OTHER_LISTED_URL,
    USMarketService,
    parse_finra_short_volume,
    parse_nasdaq_listed,
    parse_other_listed,
)


NASDAQ_LISTED_FIXTURE = """\
Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. Common Stock|Q|N|N|100|N|N
QQQ|Invesco QQQ Trust|Q|N|N|100|Y|N
TEST|Test Security|S|Y|N|100|N|N
File Creation Time: 0730202601:15|||||||
"""

OTHER_LISTED_FIXTURE = """\
ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.A|Berkshire Hathaway Class A|N|BRK.A|N|1|N|BRK/A
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
ZZTEST|Test Security|A|ZZTEST|N|100|Y|ZZTEST
File Creation Time: 0730202601:16|||||||
"""

FINRA_FIXTURE = """\
Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20260728|AAPL|400|5|1000|B,Q,N
20260728|BRK/A|2|0|10|N
20260728|BAD SYMBOL|1|0|2|Q
"""


class _USFetcher:
    def __init__(self):
        self.calls = []
        self.fail = False

    def __call__(self, url):
        self.calls.append(url)
        if self.fail:
            raise OSError("fixture outage")
        if url == NASDAQ_LISTED_URL:
            return NASDAQ_LISTED_FIXTURE
        if url == NASDAQ_OTHER_LISTED_URL:
            return OTHER_LISTED_FIXTURE
        if url == FINRA_SHORT_VOLUME_URL.format(session="20260729"):
            raise OSError("not posted")
        if url == FINRA_SHORT_VOLUME_URL.format(session="20260728"):
            return FINRA_FIXTURE
        raise AssertionError(f"unexpected URL: {url}")


class USMarketServiceTests(unittest.TestCase):
    def test_parsers_reject_test_rows_and_keep_official_metadata(self):
        nasdaq, nasdaq_created = parse_nasdaq_listed(NASDAQ_LISTED_FIXTURE)
        other, other_created = parse_other_listed(OTHER_LISTED_FIXTURE)
        short = parse_finra_short_volume(FINRA_FIXTURE)

        self.assertEqual(["AAPL", "QQQ"], [row["symbol"] for row in nasdaq])
        self.assertEqual(["BRK/A", "SPY"], [row["symbol"] for row in other])
        self.assertEqual("0730202601:15", nasdaq_created)
        self.assertEqual("0730202601:16", other_created)
        self.assertEqual(["AAPL", "BRK/A"], [row["symbol"] for row in short])
        self.assertEqual("2026-07-28", short[0]["date"])
        self.assertTrue(nasdaq[1]["is_etf"])
        self.assertEqual("NYSE", other[0]["exchange"])

    def test_builds_cached_us_directory_with_finra_short_activity(self):
        fetcher = _USFetcher()
        service = USMarketService(
            fetch_text=fetcher,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=4,
        )

        first = service.snapshot()
        cached = service.snapshot()
        by_symbol = {row["symbol"]: row for row in first["rows"]}

        self.assertTrue(first["ok"])
        self.assertEqual("EOD_REFERENCE", first["status"])
        self.assertEqual("2026-07-28", first["session_date"])
        self.assertEqual(4, first["row_count"])
        self.assertEqual(2, first["short_volume_row_count"])
        self.assertEqual(2, first["short_volume_source_row_count"])
        self.assertEqual(2, first["short_volume_joined_row_count"])
        self.assertEqual(0, first["short_volume_unmatched_row_count"])
        self.assertEqual(40.0, by_symbol["AAPL"]["short_volume_ratio"])
        self.assertEqual(20.0, by_symbol["BRK/A"]["short_volume_ratio"])
        self.assertEqual("NO_ROW", by_symbol["QQQ"]["short_volume_status"])
        self.assertIsNone(by_symbol["AAPL"]["price"])
        self.assertEqual("NOT_CONNECTED", by_symbol["AAPL"]["quote_status"])
        self.assertEqual(
            "EOD",
            first["source_status"]["short_volume"]["status"],
        )
        self.assertEqual(
            "source_rows",
            first["source_status"]["short_volume"]["row_count_semantics"],
        )
        self.assertEqual(
            "NOT_CONNECTED",
            first["source_status"]["prices"]["status"],
        )
        self.assertTrue(cached["cached"])
        self.assertEqual(4, len(fetcher.calls))
        self.assertTrue(service.health()["ok"])
        self.assertFalse(service.health()["price_provider_configured"])

    def test_stale_cache_is_preserved_on_upstream_failure(self):
        fetcher = _USFetcher()
        service = USMarketService(
            fetch_text=fetcher,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=4,
        )
        initial = service.snapshot()
        service._cache_expires_at = 0.0
        fetcher.fail = True
        stale = service.snapshot()

        self.assertEqual("EOD_REFERENCE", initial["status"])
        self.assertEqual("STALE", stale["status"])
        self.assertEqual(4, stale["row_count"])
        self.assertEqual(
            "STALE",
            stale["source_status"]["directory"]["status"],
        )
        self.assertEqual(
            "STALE",
            next(
                row
                for row in stale["rows"]
                if row["symbol"] == "AAPL"
            )["short_volume_status"],
        )
        self.assertTrue(any("fixture outage" in error for error in stale["errors"]))

    def test_joins_class_preferred_and_warrant_symbol_variants(self):
        other_fixture = """\
ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BRK.A|Berkshire Hathaway Class A|N|BRK.A|N|1|N|BRK.A
BAC.PB|Bank of America Preferred B|N|BAC.PB|N|100|N|BAC.PB
FOO.WS|Foo Warrants|A|FOO.WS|N|100|N|FOO.WS
File Creation Time: 0730202601:16|||||||
"""
        short_fixture = """\
Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20260728|BRK/A|2|0|10|N
20260728|BACPB|30|0|100|N
20260728|FOOWS|8|0|20|N
20260728|UNMATCHED|1|0|2|Q
"""

        def fetch(url):
            if url == NASDAQ_LISTED_URL:
                return NASDAQ_LISTED_FIXTURE
            if url == NASDAQ_OTHER_LISTED_URL:
                return other_fixture
            if url == FINRA_SHORT_VOLUME_URL.format(session="20260729"):
                raise OSError("not posted")
            if url == FINRA_SHORT_VOLUME_URL.format(session="20260728"):
                return short_fixture
            raise AssertionError(f"unexpected URL: {url}")

        service = USMarketService(
            fetch_text=fetch,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=5,
        )

        payload = service.snapshot()
        by_symbol = {row["symbol"]: row for row in payload["rows"]}

        self.assertEqual(4, payload["short_volume_source_row_count"])
        self.assertEqual(3, payload["short_volume_joined_row_count"])
        self.assertEqual(1, payload["short_volume_unmatched_row_count"])
        self.assertEqual(20.0, by_symbol["BRK.A"]["short_volume_ratio"])
        self.assertEqual(30.0, by_symbol["BAC.PB"]["short_volume_ratio"])
        self.assertEqual(40.0, by_symbol["FOO.WS"]["short_volume_ratio"])
        self.assertEqual(
            ["UNMATCHED"],
            payload["source_status"]["short_volume"][
                "unmatched_symbol_sample"
            ],
        )

    def test_incomplete_directory_fails_closed(self):
        service = USMarketService(
            fetch_text=lambda url: NASDAQ_LISTED_FIXTURE,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=10,
        )

        failed = service.snapshot()

        self.assertFalse(failed["ok"])
        self.assertEqual("UNAVAILABLE", failed["status"])
        self.assertEqual([], failed["rows"])

    def test_snapshot_deadline_returns_bounded_unavailable_payload(self):
        release = threading.Event()

        def blocking_fetch(url):
            del url
            release.wait(timeout=2)
            return ""

        service = USMarketService(
            fetch_text=blocking_fetch,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=1,
            snapshot_deadline_seconds=0.05,
        )
        try:
            started = time.monotonic()
            payload = service.snapshot()
            elapsed = time.monotonic() - started
        finally:
            release.set()

        self.assertLess(elapsed, 0.25)
        self.assertEqual("UNAVAILABLE", payload["status"])
        self.assertTrue(
            any("deadline exceeded" in error for error in payload["errors"])
        )

    def test_deadline_prevents_follow_up_requests_after_blocking_fetch_returns(self):
        release = threading.Event()
        calls = []

        def blocking_fetch(url):
            calls.append(url)
            release.wait(timeout=2)
            return NASDAQ_LISTED_FIXTURE

        service = USMarketService(
            fetch_text=blocking_fetch,
            clock=lambda: datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc),
            minimum_directory_rows=1,
            snapshot_deadline_seconds=0.05,
        )
        payload = service.snapshot()
        release.set()
        time.sleep(0.08)

        self.assertEqual("UNAVAILABLE", payload["status"])
        self.assertEqual([NASDAQ_LISTED_URL], calls)
