import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from taiwan_stock_analysis.official_market_cache import OfficialMarketCache
from taiwan_stock_analysis.official_snapshot_store import OfficialSnapshotStore


TAIPEI = timezone(timedelta(hours=8))


def _live_payload(now, *, status="EOD"):
    return {
        "schema_version": 1,
        "kind": "live_market_snapshot",
        "ok": True,
        "quotes_ok": True,
        "generated_at": now.isoformat(),
        "status": status,
        "provider": {
            "id": "fubon-neo",
            "label": "Fubon Neo",
            "mode": "PERSONAL_BROKER_SESSION",
        },
        "market": {"status": status, "as_of": now.isoformat()},
        "quotes": [
            {
                "symbol": "2330",
                "status": status,
                "price": 2420,
                "source": "Fubon Neo MarketData",
                "source_event_time": now.isoformat(),
            }
        ],
        "indices": [
            {
                "symbol": "t00",
                "status": status,
                "price": 35276.44,
                "source": "Fubon Neo MarketData",
                "source_event_time": now.isoformat(),
            },
            {
                "symbol": "o00",
                "status": status,
                "price": 302.12,
                "source": "Fubon Neo MarketData",
                "source_event_time": now.isoformat(),
            },
        ],
        "missing_symbols": [],
        "source_status": {
            "quotes": {
                "status": status,
                "fetched_at": now.isoformat(),
                "fallback": False,
                "upstreams": [
                    {
                        "id": "fubon-snapshot:TSE",
                        "status": status,
                        "row_count": 1,
                        "latest_event_at": now.isoformat(),
                    }
                ],
            }
        },
    }


def _breadth_payload(now, *, status="PARTIAL"):
    session_date = now.date().isoformat()
    return {
        "schema_version": 1,
        "kind": "market_breadth_snapshot",
        "ok": True,
        "cached": False,
        "generated_at": now.isoformat(),
        "status": status,
        "mode": "EOD_PARTIAL+LIVE_PAGE",
        "session_fresh": True,
        "live_session_fresh": False,
        "full_market": [
            {
                "symbol": "2330",
                "market": "TWSE",
                "quote_status": "EOD",
                "session_date": session_date,
                "quote_source": "TWSE MI_INDEX RWD",
                "price": 2420,
            },
            {
                "symbol": "6488",
                "market": "TPEX",
                "quote_status": "EOD",
                "session_date": session_date,
                "quote_source": "TPEx mainboard quotes",
                "price": 430,
            },
        ],
        "coverage": {
            "catalog_total": 2,
            "quoted_total": 2,
            "ratio": 1.0,
            "live_full_coverage": False,
        },
        "source_status": {
            "catalog": {
                "status": "FRESH",
                "row_count": 2,
                "upstreams": [
                    {"id": "twse-catalog", "status": "FRESH", "row_count": 1},
                    {"id": "tpex-catalog", "status": "FRESH", "row_count": 1},
                ],
            },
            "quotes": {
                "status": "EOD",
                "row_count": 2,
                "upstreams": [
                    {
                        "id": "twse-daily",
                        "status": "EOD",
                        "row_count": 1,
                        "session_date": session_date,
                    },
                    {
                        "id": "tpex-daily",
                        "status": "EOD",
                        "row_count": 1,
                        "session_date": session_date,
                    },
                ],
            },
            "calendar": {
                "status": "FRESH",
                "source": "TWSE holidaySchedule OpenAPI",
            },
        },
    }


def _breadth_payload_with_official_event_sources(now):
    payload = _breadth_payload(now)
    fetched_at = now.isoformat()
    session_date = now.date().isoformat()
    payload["source_status"].update(
        {
            "alerts": {
                "authoritative": True,
                "cached": True,
                "coverage_status": "COMPLETE",
                "fallback": False,
                "fetched_at": fetched_at,
                "latest_event_at": session_date,
                "partial": False,
                "status": "FRESH",
                "transport_status": "FRESH",
                "upstreams": [
                    {
                        "id": "twse-disposition",
                        "latest_event_at": session_date,
                        "row_count": 4,
                        "status": "FRESH",
                    },
                    {
                        "id": "tpex-notice",
                        "latest_event_at": session_date,
                        "row_count": 50,
                        "status": "FRESH",
                    },
                ],
            },
            "disposition_alerts": {
                "authoritative": True,
                "cached": True,
                "coverage_status": "COMPLETE",
                "fallback": False,
                "fetched_at": fetched_at,
                "latest_event_at": session_date,
                "partial": False,
                "row_count": 30,
                "status": "FRESH",
                "transport_status": "FRESH",
                "upstreams": [
                    {
                        "id": "twse-disposition",
                        "latest_event_at": session_date,
                        "row_count": 4,
                        "status": "FRESH",
                    },
                    {
                        "id": "tpex-disposition",
                        "latest_event_at": session_date,
                        "row_count": 26,
                        "status": "FRESH",
                    },
                ],
            },
            "fund_flow": {
                "authoritative": True,
                "cached": True,
                "coverage_status": "COMPLETE",
                "fallback": False,
                "fetched_at": fetched_at,
                "latest_event_at": session_date,
                "partial": False,
                "required_event_date": session_date,
                "session_aligned": True,
                "status": "EOD",
                "transport_status": "EOD",
                "upstreams": [
                    {
                        "id": "twse-t86",
                        "latest_event_at": session_date,
                        "row_count": 1326,
                        "status": "EOD",
                    },
                    {
                        "id": "tpex-3insti",
                        "latest_event_at": session_date,
                        "row_count": 917,
                        "status": "EOD",
                    },
                ],
            },
            "notice_alerts": {
                "authoritative": True,
                "cached": True,
                "coverage_status": "COMPLETE",
                "fallback": False,
                "fetched_at": fetched_at,
                "latest_event_at": session_date,
                "partial": False,
                "row_count": 50,
                "status": "FRESH",
                "transport_status": "FRESH",
                "upstreams": [
                    {
                        "id": "tpex-notice",
                        "latest_event_at": session_date,
                        "row_count": 50,
                        "status": "FRESH",
                    }
                ],
            },
        }
    )
    return payload


def _live_payload_with_official_event_sources(now):
    payload = _live_payload(now)
    payload["cached"] = False
    supporting_sources = _breadth_payload_with_official_event_sources(now)[
        "source_status"
    ]
    for component in (
        "alerts",
        "disposition_alerts",
        "fund_flow",
        "notice_alerts",
    ):
        payload["source_status"][component] = supporting_sources[component]
    return payload


class OfficialMarketCacheTests(unittest.TestCase):
    def test_live_refresh_uses_explicit_stale_cache_after_provider_failure(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            live = cache.refresh_live(["2330"], lambda: _live_payload(now))
            fallback = cache.refresh_live(
                ["2330"],
                lambda: (_ for _ in ()).throw(TimeoutError("provider timeout")),
            )

        self.assertEqual("EOD", live["status"])
        self.assertEqual("STALE", fallback["status"])
        self.assertFalse(fallback["quotes_ok"])
        self.assertTrue(fallback["cache"]["fallback"])
        self.assertEqual("UPSTREAM_TIMEOUT", fallback["cache"]["reason"])

    def test_live_cache_key_is_stable_for_equivalent_symbol_sets(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2454", "2330", "2330"], lambda: _live_payload(now))
            fallback = cache.load_stale_live(
                ["2330", "2454"],
                reason="manual fallback",
            )

        self.assertIsNotNone(fallback)
        self.assertEqual("STALE", fallback["status"])

    def test_force_live_with_official_date_only_events_is_persisted(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        payload = _live_payload_with_official_event_sources(now)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = OfficialMarketCache(
                OfficialSnapshotStore(root, clock=lambda: now)
            )
            result = cache.refresh_live(
                ["2330", "2454", "2317"],
                lambda: payload,
            )
            fallback = cache.load_stale_live(
                ["2317", "2330", "2454"],
                reason="runtime restart",
            )

            self.assertFalse(result["cached"])
            self.assertEqual(1, len(list(root.glob("live-market-*.json"))))

        self.assertIsNotNone(fallback)
        self.assertEqual("STALE", fallback["status"])
        self.assertEqual(
            "2026-08-28",
            fallback["source_status"]["alerts"]["latest_event_at"],
        )

    def test_live_official_date_only_event_rejects_naive_and_future_values(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)

        for invalid_value in ("2026-08-28T00:00:00", "2026-08-29"):
            with (
                self.subTest(value=invalid_value),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                payload = _live_payload_with_official_event_sources(now)
                payload["source_status"]["fund_flow"]["upstreams"][0][
                    "latest_event_at"
                ] = invalid_value
                cache = OfficialMarketCache(
                    OfficialSnapshotStore(root, clock=lambda: now)
                )
                result = cache.refresh_live(["2330"], lambda: payload)

                self.assertEqual("EOD", result["status"])
                self.assertFalse(list(root.glob("live-market-*.json")))

    def test_live_date_only_event_is_not_allowed_for_wrong_component(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        payload = _live_payload_with_official_event_sources(now)
        payload["source_status"]["quotes"]["upstreams"][0][
            "latest_event_at"
        ] = now.date().isoformat()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = OfficialMarketCache(
                OfficialSnapshotStore(root, clock=lambda: now)
            )
            result = cache.refresh_live(["2330"], lambda: payload)
            self.assertFalse(list(root.glob("live-market-*.json")))

        self.assertEqual("EOD", result["status"])

    def test_unavailable_live_payload_does_not_replace_last_official_snapshot(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        unavailable = {
            "schema_version": 1,
            "kind": "live_market_snapshot",
            "ok": False,
            "quotes_ok": False,
            "generated_at": now.isoformat(),
            "status": "UNAVAILABLE",
            "quotes": [],
            "indices": [],
            "missing_symbols": ["2330"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: unavailable)
            fallback = cache.load_stale_live(["2330"], reason="check cache")

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])
        self.assertEqual(2420, fallback["quotes"][0]["price"])

    def test_live_payload_with_naive_generated_time_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["generated_at"] = "2026-08-28T14:31:00"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_with_naive_observation_time_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["quotes"][0]["source_event_time"] = "2026-08-28T14:31:00"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_with_stale_nested_quote_source_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["source_status"]["quotes"]["status"] = "STALE"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_with_stale_quote_upstream_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["source_status"]["quotes"]["upstreams"][0][
            "status"
        ] = "STALE"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_with_unrecognized_provenance_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["provider"]["id"] = "unknown-vendor"
        invalid["source_status"]["quotes"]["upstreams"][0][
            "id"
        ] = "unknown-vendor:quotes"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_missing_required_market_contract_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid.pop("market")
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_requires_explicit_empty_missing_symbol_list(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["missing_symbols"] = None
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_requires_consistent_nested_status_contract(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["market"]["status"] = "LIVE"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_missing_required_benchmark_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["indices"] = invalid["indices"][:1]
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_missing_quote_observation_time_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["quotes"][0]["source_event_time"] = ""
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_non_finite_or_unbounded_live_price_cannot_interrupt_fallback(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["quotes"][0]["price"] = 10**10000

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_live_payload_missing_source_fetch_time_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["source_status"]["quotes"]["fetched_at"] = ""
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])

    def test_breadth_refresh_falls_back_only_after_cacheable_official_payload(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        payload = _breadth_payload(now)

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: payload)
            fallback = cache.refresh_breadth(
                lambda: (_ for _ in ()).throw(RuntimeError("TWSE unavailable"))
            )

        self.assertEqual("STALE", fallback["status"])
        self.assertEqual("STALE_FALLBACK+LIVE_PAGE", fallback["mode"])
        self.assertEqual("UPSTREAM_FAILURE", fallback["cache"]["reason"])

    def test_force_breadth_with_official_date_only_events_is_persisted(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        payload = _breadth_payload_with_official_event_sources(now)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = OfficialMarketCache(
                OfficialSnapshotStore(root, clock=lambda: now)
            )
            result = cache.refresh_breadth(lambda: payload)
            fallback = cache.load_stale_breadth(reason="runtime restart")

            self.assertFalse(result["cached"])
            self.assertTrue((root / "market-breadth.json").is_file())

        self.assertIsNotNone(fallback)
        self.assertEqual("STALE", fallback["status"])
        self.assertEqual(
            "2026-08-28",
            fallback["source_status"]["fund_flow"]["latest_event_at"],
        )

    def test_official_date_only_event_must_be_exact_valid_and_not_future(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        invalid_values = (
            "2026-08-28T00:00:00",
            "20260828",
            "28/08/2026",
            "2026-08-29",
            "2026-02-30",
        )

        for invalid_value in invalid_values:
            with (
                self.subTest(value=invalid_value),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                payload = _breadth_payload_with_official_event_sources(now)
                payload["source_status"]["alerts"]["upstreams"][0][
                    "latest_event_at"
                ] = invalid_value
                cache = OfficialMarketCache(
                    OfficialSnapshotStore(root, clock=lambda: now)
                )
                result = cache.refresh_breadth(lambda: payload)

                self.assertEqual("PARTIAL", result["status"])
                self.assertFalse((root / "market-breadth.json").exists())

    def test_date_only_event_time_is_not_allowed_for_quote_source(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        payload = _breadth_payload(now)
        payload["source_status"]["quotes"]["upstreams"][0][
            "latest_event_at"
        ] = now.date().isoformat()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = OfficialMarketCache(
                OfficialSnapshotStore(root, clock=lambda: now)
            )
            result = cache.refresh_breadth(lambda: payload)
            self.assertFalse((root / "market-breadth.json").exists())

        self.assertEqual("PARTIAL", result["status"])

    def test_valid_service_cached_breadth_is_current_without_disk_rewrite(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        service_cached = _breadth_payload(now)
        service_cached["cached"] = True
        service_cached["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "market-breadth.json"
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            saved_before = snapshot_path.read_bytes()
            result = cache.refresh_breadth(lambda: service_cached)
            saved_after = snapshot_path.read_bytes()

        self.assertIs(service_cached, result)
        self.assertEqual("PARTIAL", result["status"])
        self.assertNotIn("cache", result)
        self.assertEqual(999, result["full_market"][0]["price"])
        self.assertEqual(saved_before, saved_after)

    def test_invalid_service_cached_breadth_uses_stale_disk_fallback(self):
        now = datetime(2026, 8, 28, 19, 38, tzinfo=TAIPEI)
        invalid_cached = _breadth_payload(now)
        invalid_cached["cached"] = True
        invalid_cached["source_status"]["quotes"]["status"] = "STALE"
        invalid_cached["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid_cached)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_mopsfin_provenance_is_accepted_as_official_source(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        payload = _breadth_payload(now)
        payload["source_status"]["fundamentals"] = {
            "status": "FRESH",
            "upstreams": [
                {
                    "id": "mopsfin_t187ap14_L",
                    "status": "FRESH",
                    "row_count": 1,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: payload)
            fallback = cache.refresh_breadth(
                lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))
            )

        self.assertEqual("STALE", fallback["status"])
        self.assertEqual(2420, fallback["full_market"][0]["price"])

    def test_breadth_payload_with_naive_generated_time_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["generated_at"] = "2026-08-28T14:31:00"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_with_stale_nested_quotes_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["quotes"]["status"] = "STALE"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_with_stale_quote_upstream_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["quotes"]["upstreams"][0][
            "status"
        ] = "STALE"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_with_unrecognized_nested_source_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["quotes"]["upstreams"][0][
            "id"
        ] = "unknown-daily"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_source_name_containing_exchange_token_is_not_automatically_official(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["quotes"]["upstreams"][0][
            "id"
        ] = "unlicensed-twse-clone"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_malformed_source_url_is_rejected_without_interrupting_fallback(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["quotes"]["upstreams"][0]["id"] = "http://["
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_with_unrecognized_active_component_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["source_status"]["calendar"]["source"] = "unknown calendar"
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_missing_coverage_contract_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid.pop("coverage")
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_requires_current_session_contract(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["session_fresh"] = False
        invalid["full_market"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_breadth_payload_without_market_rows_does_not_replace_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["full_market"] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            result = cache.refresh_breadth(lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["full_market"][0]["price"])

    def test_provider_exception_is_preserved_when_no_cache_exists(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            with self.assertRaisesRegex(RuntimeError, "first failure"):
                cache.refresh_breadth(
                    lambda: (_ for _ in ()).throw(RuntimeError("first failure"))
                )

    def test_provider_exception_details_never_enter_fallback_reason(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        secret_message = (
            "Authorization: Bearer top-secret "
            "access_token=token-value client_secret=client-value password=pw"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            fallback = cache.refresh_breadth(
                lambda: (_ for _ in ()).throw(RuntimeError(secret_message))
            )

        self.assertEqual("UPSTREAM_FAILURE", fallback["cache"]["reason"])
        serialized = str(fallback["cache"]).casefold()
        for forbidden in (
            "authorization",
            "bearer",
            "access_token",
            "client_secret",
            "password",
            "top-secret",
            "token-value",
            "client-value",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_invalid_payload_status_never_enters_fallback_reason(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _breadth_payload(now)
        invalid["status"] = "Authorization: Bearer top-secret"

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_breadth(lambda: _breadth_payload(now))
            fallback = cache.refresh_breadth(lambda: invalid)

        self.assertEqual(
            "UPSTREAM_CONTRACT_INVALID",
            fallback["cache"]["reason"],
        )
        self.assertNotIn("top-secret", str(fallback["cache"]))

    def test_secret_bearing_live_payload_cannot_replace_valid_cache(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        invalid = _live_payload(now)
        invalid["provider"]["access_token"] = "top-secret"
        invalid["quotes"][0]["price"] = 999

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            cache.refresh_live(["2330"], lambda: _live_payload(now))
            result = cache.refresh_live(["2330"], lambda: invalid)

        self.assertEqual("STALE", result["status"])
        self.assertEqual(2420, result["quotes"][0]["price"])
        self.assertEqual("CACHE_PAYLOAD_REJECTED", result["cache"]["reason"])
        self.assertNotIn("top-secret", str(result))

    def test_malformed_nested_live_contract_is_not_cached_or_raised(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        malformed = _live_payload(now)
        malformed["source_status"] = None
        malformed["cache"] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = OfficialMarketCache(
                OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            )
            result = cache.refresh_live(["2330"], lambda: malformed)
            fallback = cache.load_stale_live(
                ["2330"],
                reason="must not exist",
            )

        self.assertIs(malformed, result)
        self.assertIsNone(fallback)


if __name__ == "__main__":
    unittest.main()
