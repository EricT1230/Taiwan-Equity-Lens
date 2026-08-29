import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from taiwan_stock_analysis.official_snapshot_store import OfficialSnapshotStore


TAIPEI = timezone(timedelta(hours=8))


class OfficialSnapshotStoreTests(unittest.TestCase):
    def test_saved_official_snapshot_loads_only_as_explicit_stale_fallback(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        payload = {
            "schema_version": 1,
            "kind": "live_market_snapshot",
            "ok": True,
            "quotes_ok": True,
            "generated_at": now.isoformat(),
            "status": "EOD",
            "provider": {"label": "Fubon Neo", "mode": "PERSONAL_EOD"},
            "market": {
                "status": "EOD",
                "as_of": now.isoformat(),
                "coverage": True,
                "authoritative": True,
                "transport": {"transport_status": "CONNECTED"},
            },
            "quotes": [
                {
                    "symbol": "2330",
                    "status": "EOD",
                    "price": 2420,
                    "source_event_time": now.isoformat(),
                    "coverage_complete": True,
                    "authoritative": True,
                    "latest_event_at": now.isoformat(),
                    "source_status": {"status": "FRESH"},
                }
            ],
            "indices": [{"symbol": "t00", "status": "EOD", "price": 35276.44}],
            "source_status": {
                "quotes": {
                    "status": "EOD",
                    "coverage_status": "FULL",
                    "coverage_complete": True,
                    "authoritative": True,
                    "latest_event_at": now.isoformat(),
                    "market_statuses": {"TWSE": "EOD", "TPEX": "EOD"},
                    "statuses": {"primary": "EOD"},
                    "nested": [
                        {
                            "status": "FRESH",
                            "coverage": "FULL",
                            "authoritative": True,
                        }
                    ],
                }
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            store.save("live-market", payload)
            fallback = store.load_stale("live-market", reason="provider timeout")

        self.assertIsNotNone(fallback)
        self.assertEqual("STALE", fallback["status"])
        self.assertEqual("STALE", fallback["market"]["status"])
        self.assertEqual("STALE", fallback["quotes"][0]["status"])
        self.assertEqual("STALE", fallback["indices"][0]["status"])
        self.assertEqual(
            now.isoformat(),
            fallback["quotes"][0]["source_event_time"],
        )
        self.assertFalse(fallback["market"]["coverage"])
        self.assertFalse(fallback["market"]["authoritative"])
        self.assertEqual(
            "STALE",
            fallback["market"]["transport"]["transport_status"],
        )
        self.assertFalse(fallback["quotes"][0]["coverage_complete"])
        self.assertFalse(fallback["quotes"][0]["authoritative"])
        self.assertEqual(
            "STALE",
            fallback["quotes"][0]["source_status"]["status"],
        )
        quote_source = fallback["source_status"]["quotes"]
        self.assertEqual(now.isoformat(), quote_source["latest_event_at"])
        self.assertEqual("STALE", quote_source["status"])
        self.assertEqual("STALE", quote_source["coverage_status"])
        self.assertFalse(quote_source["coverage_complete"])
        self.assertFalse(quote_source["authoritative"])
        self.assertEqual(
            {"TWSE": "STALE", "TPEX": "STALE"},
            quote_source["market_statuses"],
        )
        self.assertEqual({"primary": "STALE"}, quote_source["statuses"])
        self.assertEqual("STALE", quote_source["nested"][0]["status"])
        self.assertEqual("STALE", quote_source["nested"][0]["coverage"])
        self.assertFalse(quote_source["nested"][0]["authoritative"])
        self.assertEqual("EOD", fallback["cache"]["original_status"])
        self.assertEqual(now.isoformat(), fallback["cache"]["original_generated_at"])
        self.assertEqual("provider timeout", fallback["cache"]["reason"])

    def test_snapshot_store_rejects_secrets_and_demo_markers_before_writing(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        rejected_payloads = (
            {"status": "EOD", "provider": {"sdk_token": "must-not-write"}},
            {"status": "EOD", "source": "synthetic-demo"},
            {"status": "EOD", "url": "https://example.com/news"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(root, clock=lambda: now)
            for payload in rejected_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        store.save("live-market", payload)
            self.assertEqual([], list(root.glob("*.json")))

    def test_plain_editorial_text_does_not_trigger_demo_provenance_filter(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        payload = {
            "status": "EOD",
            "news": [
                {
                    "title": "工廠短暫 offline 後恢復生產",
                    "summary": "測試 fixture 一詞出現在新聞正文，不代表資料來源。",
                    "source": "中央社",
                    "url": "https://www.cna.com.tw/news/aie/202608280001.aspx",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            output = store.save("live-market", payload)

        self.assertEqual("live-market.json", output.name)

    def test_normalized_secret_suffixes_are_rejected_without_blocking_market_fields(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        secret_payloads = (
            {"status": "EOD", "provider": {"oauthAccessToken": "secret"}},
            {"status": "EOD", "provider": {"nested_client_secret": "secret"}},
            {"status": "EOD", "provider": {"databasePassword": "secret"}},
            {"status": "EOD", "provider": {"refresh-token": "secret"}},
            {"status": "EOD", "provider": {"personalId": "secret"}},
            {"status": "EOD", "provider": {"serviceCredential": "secret"}},
            {"status": "EOD", "provider": {"signingPassphrase": "secret"}},
            {"status": "EOD", "provider": {"apiSecret": "secret"}},
            {"status": "EOD", "provider": {"secretKey": "secret"}},
            {"status": "EOD", "provider": {"sessionCookie": "secret"}},
        )
        public_market_payload = {
            "status": "EOD",
            "market": {
                "reference_price": 2420,
                "access_token_count": 0,
                "tokenized_volume": 12345,
                "client_secretary_note": "公開市場欄位，不是憑證",
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(root, clock=lambda: now)
            for index, payload in enumerate(secret_payloads):
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        store.save(f"secret-{index}", payload)
            output = store.save("public-market-fields", public_market_payload)

        self.assertEqual("public-market-fields.json", output.name)

    def test_dataset_name_cannot_escape_the_snapshot_root(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "cache"
            store = OfficialSnapshotStore(root, clock=lambda: now)
            with self.assertRaises(ValueError):
                store.save("../outside", {"status": "EOD"})

            self.assertFalse((Path(temp_dir) / "outside.json").exists())

    def test_cache_envelope_requires_timezone_aware_save_time(self):
        naive_now = datetime(2026, 8, 28, 14, 30)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(root, clock=lambda: naive_now)
            with self.assertRaises(ValueError):
                store.save("live-market", {"status": "EOD"})

            self.assertFalse((root / "live-market.json").exists())

    def test_tampered_snapshot_with_secret_or_demo_provenance_is_not_loaded(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        tampered_payloads = (
            {"status": "EOD", "provider": {"token": "not-safe"}},
            {"status": "EOD", "source": "offline-fixture"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(root, clock=lambda: now)
            for index, payload in enumerate(tampered_payloads):
                dataset = f"tampered-{index}"
                envelope = {
                    "schema_version": 1,
                    "kind": "official_snapshot_cache",
                    "dataset": dataset,
                    "saved_at": now.isoformat(),
                    "payload": payload,
                }
                (root / f"{dataset}.json").write_text(
                    json.dumps(envelope),
                    encoding="utf-8",
                )

                with self.subTest(payload=payload):
                    self.assertIsNone(
                        store.load_stale(dataset, reason="provider unavailable")
                    )

    def test_sensitive_fallback_reason_is_replaced_with_safe_code(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            store.save("live-market", {"status": "EOD"})
            fallback = store.load_stale(
                "live-market",
                reason=(
                    "Authorization: Bearer secret access_token=token "
                    "client_secret=client password=pw"
                ),
            )

        self.assertEqual("UPSTREAM_REASON_REDACTED", fallback["cache"]["reason"])
        serialized = str(fallback["cache"]).casefold()
        for forbidden in (
            "authorization",
            "bearer",
            "access_token",
            "client_secret",
            "password",
            "secret",
            "token",
            "client",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_breadth_cache_fallback_downgrades_derived_authority(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)
        payload = {
            "schema_version": 1,
            "kind": "market_breadth_snapshot",
            "ok": True,
            "generated_at": now.isoformat(),
            "status": "EOD",
            "mode": "EOD_FULL+LIVE_PAGE",
            "session_fresh": True,
            "live_session_fresh": False,
            "full_market": [
                {
                    "symbol": "2330",
                    "quote_status": "EOD",
                    "institutional_status": "MATCHED",
                }
            ],
            "source_status": {
                "quotes": {
                    "status": "EOD",
                    "coverage_status": "FULL",
                    "authoritative": True,
                }
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = OfficialSnapshotStore(Path(temp_dir), clock=lambda: now)
            store.save("market-breadth", payload)
            fallback = store.load_stale(
                "market-breadth",
                reason="official refresh failed",
            )

        self.assertEqual("STALE_FALLBACK+LIVE_PAGE", fallback["mode"])
        self.assertFalse(fallback["session_fresh"])
        self.assertFalse(fallback["live_session_fresh"])
        self.assertEqual("STALE", fallback["full_market"][0]["quote_status"])
        self.assertEqual(
            "STALE",
            fallback["full_market"][0]["institutional_status"],
        )
        self.assertEqual("STALE", fallback["source_status"]["quotes"]["status"])
        self.assertEqual(
            "STALE",
            fallback["source_status"]["quotes"]["coverage_status"],
        )
        self.assertFalse(
            fallback["source_status"]["quotes"]["authoritative"]
        )

    def test_snapshot_size_is_bounded_on_save_and_load(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(
                root,
                clock=lambda: now,
                max_bytes=256,
            )
            with self.assertRaises(ValueError):
                store.save("oversized-save", {"status": "EOD", "data": "x" * 512})

            (root / "oversized-load.json").write_text(
                "{" + " " * 512 + "}",
                encoding="utf-8",
            )
            self.assertIsNone(
                store.load_stale("oversized-load", reason="provider timeout")
            )

    def test_oversized_snapshot_is_rejected_from_stat_before_file_open(self):
        now = datetime(2026, 8, 28, 14, 30, tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(
                root,
                clock=lambda: now,
                max_bytes=256,
            )
            (root / "oversized-load.json").write_bytes(b"x" * 512)
            with patch.object(
                Path,
                "open",
                side_effect=AssertionError("oversized cache must not be opened"),
            ):
                loaded = store.load_stale(
                    "oversized-load",
                    reason="provider timeout",
                )

        self.assertIsNone(loaded)

    def test_snapshot_file_count_is_bounded_to_recent_datasets(self):
        tick = {"seconds": 0}

        def clock():
            tick["seconds"] += 1
            return datetime(2026, 8, 28, 14, 30, tick["seconds"], tzinfo=TAIPEI)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = OfficialSnapshotStore(root, clock=clock, max_files=2)
            store.save("first", {"status": "EOD"})
            store.save("second", {"status": "EOD"})
            store.save("third", {"status": "EOD"})

            names = sorted(path.name for path in root.glob("*.json"))

        self.assertEqual(["second.json", "third.json"], names)


if __name__ == "__main__":
    unittest.main()
