import unittest

from taiwan_stock_analysis.freshness import classify_freshness, summarize_source_audit


class FreshnessTests(unittest.TestCase):
    def test_classify_freshness_marks_fresh_and_stale(self):
        fresh = classify_freshness(
            generated_at="2026-05-10T00:00:00Z",
            now="2026-05-14T00:00:00Z",
            source_mode="live",
            stale_after_days=30,
        )
        stale = classify_freshness(
            generated_at="2026-03-01T00:00:00Z",
            now="2026-05-14T00:00:00Z",
            source_mode="live",
            stale_after_days=30,
        )

        self.assertEqual(fresh["status"], "fresh")
        self.assertEqual(fresh["age_days"], 4)
        self.assertEqual(stale["status"], "stale")
        self.assertGreater(stale["age_days"], 30)

    def test_classify_freshness_marks_unknown_and_manual_review(self):
        unknown = classify_freshness(
            generated_at="not-a-date",
            now="2026-05-14T00:00:00Z",
            source_mode="live",
            stale_after_days=30,
        )
        fixture = classify_freshness(
            generated_at="2026-05-14T00:00:00Z",
            now="2026-05-14T00:00:00Z",
            source_mode="fixture",
            stale_after_days=30,
        )

        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual(fixture["status"], "manual_review")
        self.assertIn("fixture", fixture["review_reason"])

    def test_summarize_source_audit_prioritizes_stale_unknown_manual_review(self):
        summary = summarize_source_audit(
            [
                {"status": "fresh"},
                {"status": "manual_review"},
                {"status": "stale"},
            ]
        )

        self.assertEqual(summary["status"], "stale")
        self.assertEqual(summary["counts"]["fresh"], 1)
        self.assertEqual(summary["counts"]["manual_review"], 1)
        self.assertEqual(summary["counts"]["stale"], 1)
