from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from taiwan_stock_analysis.dashboard_data_policy import admit_dashboard_items


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def official_report() -> dict[str, object]:
    return {
        "kind": "market_intelligence_report",
        "provenance": {
            "source": "TWSE",
            "status": "EOD",
            "observed_at": "2026-08-28T06:00:00Z",
        },
    }


class DashboardDataPolicyTests(unittest.TestCase):
    def test_valid_official_artifact_is_admitted_and_key_shape_is_preserved(self) -> None:
        report = official_report()
        items = {
            "market_intelligence_reports": [report],
            "research_summaries": [],
        }

        admitted, summary = admit_dashboard_items(
            items,
            now=NOW,
            max_age=timedelta(days=1),
        )

        self.assertEqual(list(items), list(admitted))
        self.assertEqual([report], admitted["market_intelligence_reports"])
        self.assertEqual([], admitted["research_summaries"])
        self.assertEqual(1, summary["admitted_count"])
        self.assertEqual(0, summary["rejected_count"])
        self.assertEqual([], summary["rejections"])

    def test_nested_demo_contamination_is_rejected_with_structured_reasons(self) -> None:
        contaminations = (
            ("fixture", {"source_audit": {"financial": {"source_mode": "fixture"}}}, "forbidden_data_mode"),
            ("offline", {"inputs": [{"source_mode": "offline"}]}, "forbidden_data_mode"),
            ("synthetic", {"news": [{"source": "synthetic-demo"}]}, "forbidden_data_source"),
            ("example-domain", {"news": [{"url": "https://example.com/story"}]}, "example_reference"),
            ("example-path", {"run_metadata": {"input_path": "examples/prices.json"}}, "example_reference"),
        )

        for label, contamination, expected_code in contaminations:
            with self.subTest(label=label):
                report = official_report()
                report.update(deepcopy(contamination))
                items = {"market_intelligence_reports": [report], "research_summaries": []}

                admitted, summary = admit_dashboard_items(
                    items,
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([], admitted["market_intelligence_reports"])
                self.assertEqual([], admitted["research_summaries"])
                self.assertEqual(0, summary["admitted_count"])
                self.assertEqual(1, summary["rejected_count"])
                rejection = summary["rejections"][0]
                self.assertEqual("market_intelligence_reports", rejection["collection"])
                self.assertEqual(0, rejection["index"])
                self.assertIn(expected_code, {reason["code"] for reason in rejection["reasons"]})
                self.assertEqual(1, summary["by_reason"][expected_code])

    def test_nested_editorial_news_requires_source_time_and_http_original_link(self) -> None:
        valid_news = {
            "source": "TWSE",
            "published_at": "2026-08-28T05:00:00Z",
            "url": "https://www.twse.com.tw/news/official",
            "title": "可追溯新聞",
        }
        for missing_key in ("source", "published_at", "url"):
            with self.subTest(missing_key=missing_key):
                report = official_report()
                row = deepcopy(valid_news)
                row.pop(missing_key)
                report["news"] = [row]

                admitted, summary = admit_dashboard_items(
                    {"market_intelligence_reports": [report]},
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([], admitted["market_intelligence_reports"])
                self.assertEqual(1, summary["by_reason"]["invalid_news_contract"])

        report = official_report()
        report["news"] = [valid_news]
        admitted, summary = admit_dashboard_items(
            {"market_intelligence_reports": [report]},
            now=NOW,
            max_age=timedelta(days=1),
        )
        self.assertEqual([report], admitted["market_intelligence_reports"])
        self.assertEqual(0, summary["rejected_count"])

    def test_missing_or_unrecognised_provenance_fails_closed(self) -> None:
        cases = (
            ("missing-provenance", None, "missing_provenance"),
            ("invalid-provenance", "TWSE", "missing_provenance"),
            (
                "missing-source",
                {"status": "EOD", "observed_at": "2026-08-28T06:00:00Z"},
                "missing_source",
            ),
            (
                "missing-status",
                {"source": "TWSE", "observed_at": "2026-08-28T06:00:00Z"},
                "missing_status",
            ),
            (
                "missing-time",
                {"source": "TWSE", "status": "EOD"},
                "missing_observation_time",
            ),
            (
                "unrecognised-source",
                {
                    "source": "unlicensed-blog",
                    "status": "EOD",
                    "observed_at": "2026-08-28T06:00:00Z",
                },
                "unrecognised_source",
            ),
            (
                "invalid-status",
                {
                    "source": "TWSE",
                    "status": "UNKNOWN",
                    "observed_at": "2026-08-28T06:00:00Z",
                },
                "invalid_status",
            ),
        )

        for label, provenance, expected_code in cases:
            with self.subTest(label=label):
                report = official_report()
                if provenance is None:
                    report.pop("provenance")
                else:
                    report["provenance"] = provenance

                admitted, summary = admit_dashboard_items(
                    {"reports": [report]},
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([], admitted["reports"])
                self.assertEqual(1, summary["rejected_count"])
                codes = {reason["code"] for reason in summary["rejections"][0]["reasons"]}
                self.assertIn(expected_code, codes)

    def test_all_recognised_official_sources_are_admitted(self) -> None:
        for source in ("Fubon", "TWSE", "TPEx", "MOPS"):
            with self.subTest(source=source):
                report = official_report()
                report["provenance"]["source"] = source

                admitted, summary = admit_dashboard_items(
                    {"reports": [report]},
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([report], admitted["reports"])
                self.assertEqual(0, summary["rejected_count"])

    def test_stale_future_and_invalid_observation_times_are_rejected(self) -> None:
        cases = (
            ("stale", "2026-08-27T11:59:59Z", "stale_observation_time"),
            ("future", "2026-08-28T12:06:00Z", "future_observation_time"),
            ("malformed", "not-a-time", "invalid_observation_time"),
            ("timezone-missing", "2026-08-28T06:00:00", "invalid_observation_time"),
        )

        for label, observed_at, expected_code in cases:
            with self.subTest(label=label):
                report = official_report()
                report["provenance"]["observed_at"] = observed_at

                admitted, summary = admit_dashboard_items(
                    {"reports": [report]},
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([], admitted["reports"])
                self.assertEqual(1, summary["rejected_count"])
                reasons = summary["rejections"][0]["reasons"]
                self.assertIn(expected_code, {reason["code"] for reason in reasons})
                self.assertEqual(1, summary["by_reason"][expected_code])

    def test_observation_time_at_exact_age_and_future_tolerance_boundaries_is_admitted(self) -> None:
        for observed_at in ("2026-08-27T12:00:00Z", "2026-08-28T12:05:00Z"):
            with self.subTest(observed_at=observed_at):
                report = official_report()
                report["provenance"]["observed_at"] = observed_at

                admitted, summary = admit_dashboard_items(
                    {"reports": [report]},
                    now=NOW,
                    max_age=timedelta(days=1),
                )

                self.assertEqual([report], admitted["reports"])
                self.assertEqual(0, summary["rejected_count"])

    def test_mixed_siblings_are_decided_independently_and_input_is_not_mutated(self) -> None:
        official = official_report()
        contaminated = official_report()
        contaminated.update(
            {
                "title": "DEMO_SENTINEL_MUST_NOT_LEAK",
                "news": [
                    {
                        "source_mode": "fixture",
                        "url": "https://example.com/demo-sentinel",
                    }
                ],
            }
        )
        stale = official_report()
        stale["provenance"]["observed_at"] = "2026-08-20T06:00:00Z"
        items = {
            "market_intelligence_reports": [official, contaminated, stale],
            "research_summaries": [],
        }
        original = deepcopy(items)

        admitted, summary = admit_dashboard_items(
            items,
            now=NOW,
            max_age=timedelta(days=1),
        )

        self.assertEqual(original, items)
        self.assertEqual([official], admitted["market_intelligence_reports"])
        self.assertEqual([], admitted["research_summaries"])
        self.assertEqual([1, 2], [row["index"] for row in summary["rejections"]])
        self.assertEqual(
            {
                "market_intelligence_reports": {"admitted": 1, "rejected": 2},
                "research_summaries": {"admitted": 0, "rejected": 0},
            },
            summary["by_collection"],
        )
        self.assertNotIn("DEMO_SENTINEL_MUST_NOT_LEAK", str(summary))
        self.assertNotIn("https://example.com/demo-sentinel", str(summary))


if __name__ == "__main__":
    unittest.main()
