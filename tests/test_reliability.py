from __future__ import annotations

import unittest

from taiwan_stock_analysis.reliability import (
    ReliabilityStatus,
    build_retry_hint,
    summarize_reliability,
)


class ReliabilityTests(unittest.TestCase):
    def test_status_serializes_to_json_compatible_dict(self) -> None:
        status = ReliabilityStatus(
            stage="price",
            status="warning",
            source="TPEx",
            date="2026-05-08",
            message="TWSE price was unavailable; TPEx fallback was used.",
            retry_hint="Run again after the next market data update.",
            stock_id="2330",
        )

        self.assertEqual(
            status.to_dict(),
            {
                "stage": "price",
                "status": "warning",
                "source": "TPEx",
                "date": "2026-05-08",
                "message": "TWSE price was unavailable; TPEx fallback was used.",
                "retry_hint": "Run again after the next market data update.",
                "stock_id": "2330",
            },
        )

    def test_invalid_status_is_normalized_to_warning(self) -> None:
        status = ReliabilityStatus(stage="parse", status="unexpected", message="Unknown state")

        self.assertEqual(status.to_dict()["status"], "warning")

    def test_summarize_reliability_counts_statuses(self) -> None:
        statuses = [
            ReliabilityStatus(stage="fetch", status="ok", message="Fetched"),
            ReliabilityStatus(stage="price", status="warning", message="Fallback used"),
            ReliabilityStatus(stage="valuation", status="skipped", message="No CSV"),
            ReliabilityStatus(stage="report", status="error", message="Failed"),
        ]

        self.assertEqual(
            summarize_reliability(statuses),
            {
                "ok": 1,
                "warning": 1,
                "error": 1,
                "skipped": 1,
                "overall_status": "error",
            },
        )

    def test_summarize_reliability_marks_empty_statuses_as_skipped(self) -> None:
        self.assertEqual(
            summarize_reliability([]),
            {
                "ok": 0,
                "warning": 0,
                "error": 0,
                "skipped": 0,
                "overall_status": "skipped",
            },
        )

    def test_retry_hint_maps_common_stages(self) -> None:
        self.assertEqual(
            build_retry_hint("fetch"),
            "Run the workflow again later or use fixture data if the source is unavailable.",
        )
        self.assertEqual(
            build_retry_hint("comparison"),
            "Comparison needs at least two successful stock reports.",
        )
        self.assertEqual(
            build_retry_hint("unknown"),
            "Review the workflow summary and rerun the failed step.",
        )


if __name__ == "__main__":
    unittest.main()
