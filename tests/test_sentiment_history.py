import csv
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

from taiwan_stock_analysis.sentiment_history import (
    SENTIMENT_HISTORY_COLUMNS,
    history_for_category,
    load_sentiment_history,
    sentiment_snapshot_from_industry,
    upsert_sentiment_snapshots,
)


class SentimentHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "industry_sentiment_history.csv"

    @staticmethod
    def snapshot(
        *,
        as_of_date: str,
        category: str,
        methodology_version: str = "industry-sentiment-v1",
        score_5d: float = 20.0,
    ) -> dict[str, object]:
        return {
            "as_of_date": as_of_date,
            "category": category,
            "methodology_version": methodology_version,
            "status": "ready",
            "score_5d": score_5d,
            "baseline_20d": 10.0,
            "change": 10.0,
            "news_score_5d": 15.0,
            "price_score_5d": 25.0,
            "fund_flow_score_5d": 20.0,
            "fund_flow_score_20d": 18.0,
            "price_return_5d": 1.5,
            "breadth_5d": 0.65,
            "breadth_20d": 0.55,
            "volume_ratio_5d": 1.2,
            "flow_persistence_5d": 0.4,
            "news_novelty_5d": 0.8,
            "news_topic_concentration_5d": 0.3,
            "news_positive_topic_concentration_5d": 0.4,
            "news_negative_topic_concentration_5d": 0.5,
            "rank": 2,
            "ranked_count": 8,
            "cycle_phase": "expansion",
            "confidence": "high",
        }

    def test_missing_history_file_returns_empty_list(self) -> None:
        self.assertEqual(load_sentiment_history(self.path), [])

    def test_upsert_round_trips_replaces_and_sorts_snapshots(self) -> None:
        upsert_sentiment_snapshots(
            self.path,
            [
                self.snapshot(
                    as_of_date="2026-07-16",
                    category="Semiconductor",
                    score_5d=20.0,
                ),
                self.snapshot(
                    as_of_date="2026-07-15",
                    category="Electric Machinery",
                    score_5d=10.0,
                ),
            ],
        )
        upsert_sentiment_snapshots(
            self.path,
            [
                self.snapshot(
                    as_of_date="2026-07-16",
                    category="Semiconductor",
                    score_5d=42.0,
                )
            ],
        )

        rows = load_sentiment_history(self.path)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["category"], "Electric Machinery")
        self.assertEqual(rows[1]["score_5d"], 42.0)
        self.assertEqual(list(rows[0]), SENTIMENT_HISTORY_COLUMNS)
        self.assertIsInstance(rows[1]["score_5d"], float)
        self.assertIsInstance(rows[1]["rank"], int)

    def test_history_for_category_excludes_current_and_future_rows(self) -> None:
        rows = [
            self.snapshot(
                as_of_date="2026-07-16",
                category="Semiconductor",
            ),
            self.snapshot(
                as_of_date="2026-07-17",
                category="Semiconductor",
            ),
            self.snapshot(
                as_of_date="2026-07-18",
                category="Semiconductor",
            ),
            self.snapshot(
                as_of_date="2026-07-15",
                category="Semiconductor",
                methodology_version="industry-sentiment-v0",
            ),
        ]

        history = history_for_category(
            reversed(rows),
            category="Semiconductor",
            methodology_version="industry-sentiment-v1",
            as_of_date="2026-07-17",
        )

        self.assertEqual([row["as_of_date"] for row in history], ["2026-07-16"])

    def test_malformed_numeric_value_identifies_path_and_row(self) -> None:
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SENTIMENT_HISTORY_COLUMNS)
            writer.writeheader()
            row = self.snapshot(as_of_date="2026-07-16", category="Semiconductor")
            row["score_5d"] = "not-a-number"
            writer.writerow(row)

        with self.assertRaisesRegex(
            ValueError, rf"{re.escape(str(self.path))}.*row 2.*score_5d"
        ):
            load_sentiment_history(self.path)

    def test_snapshot_copies_only_stable_analytical_fields(self) -> None:
        industry = {
            "category": "Semiconductor",
            "market_trend": {
                "average_return_5d": 1.5,
                "unrelated_market_detail": "discarded",
            },
            "sentiment": {
                "methodology_version": "industry-sentiment-v1",
                "status": "ready",
                "score_5d": 20.0,
                "baseline_20d": 10.0,
                "change": 10.0,
                "rank": 2,
                "ranked_count": 8,
                "cycle_phase": "expansion",
                "confidence": "high",
                "reasons": ["must not persist"],
                "warnings": ["must not persist"],
                "forecast": {"must_not": "persist"},
                "components": {
                    "news": {
                        "score_5d": 15.0,
                        "novelty": 0.8,
                        "topic_concentration": 0.3,
                        "positive_topic_concentration": 0.4,
                        "negative_topic_concentration": 0.5,
                        "article_scores": [{"title": "must not persist"}],
                    },
                    "price": {
                        "score_5d": 25.0,
                        "breadth_5d": 0.65,
                        "breadth_20d": 0.55,
                        "volume_ratio_5d": 1.2,
                    },
                    "fund_flow": {
                        "score_5d": 20.0,
                        "score_20d": 18.0,
                        "persistence_5d": 0.4,
                    },
                },
            },
        }

        snapshot = sentiment_snapshot_from_industry("2026-07-17", industry)

        self.assertEqual(snapshot, self.snapshot(
            as_of_date="2026-07-17", category="Semiconductor"
        ))
        self.assertEqual(set(snapshot), set(SENTIMENT_HISTORY_COLUMNS))


if __name__ == "__main__":
    unittest.main()
