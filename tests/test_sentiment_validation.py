import csv
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from taiwan_stock_analysis.sentiment_history import (
    SENTIMENT_HISTORY_COLUMNS,
    load_sentiment_history,
    upsert_sentiment_snapshots,
)
from taiwan_stock_analysis.sentiment_validation import (
    build_sentiment_validation_report,
    label_turning_events,
    walk_forward_predictions,
    write_sentiment_validation_report,
)


class SentimentTurningLabelTests(unittest.TestCase):
    @staticmethod
    def rows(
        scores: list[float],
        *,
        category: str = "Semiconductor",
        methodology_version: str = "industry-sentiment-v1",
    ) -> list[dict[str, object]]:
        start = date(2026, 1, 1)
        return [
            {
                "as_of_date": (start + timedelta(days=index)).isoformat(),
                "category": category,
                "methodology_version": methodology_version,
                "score_5d": score,
            }
            for index, score in enumerate(scores)
        ]

    def test_labels_one_local_peak_with_full_window_and_forward_fall(self) -> None:
        rows = self.rows(
            [40, 45, 50, 55, 60, 65, 66, 67, 68, 70, 80, 70, 68, 66, 65, 64, 65, 66, 67, 68, 69]
        )

        labels = label_turning_events(rows)

        self.assertEqual(
            [row["as_of_date"] for row in labels if row["peak_label"]],
            ["2026-01-11"],
        )
        self.assertEqual(
            [row["as_of_date"] for row in labels if row["trough_label"]],
            [],
        )

    def test_labels_one_local_trough_with_full_window_and_forward_rise(self) -> None:
        rows = self.rows(
            [60, 55, 50, 45, 40, 35, 34, 33, 32, 30, 20, 30, 32, 34, 35, 36, 35, 34, 33, 32, 31]
        )

        labels = label_turning_events(rows)

        self.assertEqual(
            [row["as_of_date"] for row in labels if row["peak_label"]],
            [],
        )
        self.assertEqual(
            [row["as_of_date"] for row in labels if row["trough_label"]],
            ["2026-01-11"],
        )

    def test_first_and_last_five_sessions_cannot_be_labeled(self) -> None:
        rows = self.rows(
            [100, 20, 20, 20, 20, 30, 30, 30, 30, 30, 40, 30, 30, 30, 30, 20, 20, 20, 20, 20, 100]
        )

        labels = label_turning_events(rows)

        boundary_rows = labels[:5] + labels[-5:]
        self.assertTrue(
            all(
                not row["peak_label"] and not row["trough_label"]
                for row in boundary_rows
            )
        )
        self.assertEqual(
            [row["label_window_complete"] for row in labels],
            [False] * 5 + [True] * 11 + [False] * 5,
        )

    def test_tied_plateau_labels_only_earliest_peak(self) -> None:
        rows = self.rows(
            [40, 45, 50, 55, 60, 65, 66, 67, 68, 70, 80, 80, 70, 68, 66, 64, 65, 66, 67, 68, 69]
        )

        labels = label_turning_events(rows)

        self.assertEqual(
            [row["as_of_date"] for row in labels if row["peak_label"]],
            ["2026-01-11"],
        )

    def test_grouping_is_exact_and_each_group_is_sorted_by_iso_date(self) -> None:
        peak_rows = self.rows(
            [40, 45, 50, 55, 60, 65, 66, 67, 68, 70, 80, 70, 68, 66, 65, 64, 65, 66, 67, 68, 69],
            category="Semiconductor",
        )
        trough_rows = self.rows(
            [60, 55, 50, 45, 40, 35, 34, 33, 32, 30, 20, 30, 32, 34, 35, 36, 35, 34, 33, 32, 31],
            category="Semiconductor ",
        )

        labels = label_turning_events(reversed(peak_rows + trough_rows))

        self.assertEqual(
            [
                (row["category"], row["as_of_date"])
                for row in labels
                if row["peak_label"] or row["trough_label"]
            ],
            [
                ("Semiconductor", "2026-01-11"),
                ("Semiconductor ", "2026-01-11"),
            ],
        )


class SentimentWalkForwardTests(unittest.TestCase):
    @staticmethod
    def rows(count: int) -> list[dict[str, object]]:
        start = date(2026, 1, 1)
        return [
            {
                "as_of_date": (start + timedelta(days=index)).isoformat(),
                "category": "Semiconductor",
                "methodology_version": "industry-sentiment-v1",
                "score_5d": float(index % 40),
            }
            for index in range(count)
        ]

    def test_each_prediction_uses_only_current_and_prior_feature_rows(self) -> None:
        calls: list[list[dict[str, object]]] = []

        def recording_risk(
            feature_rows: list[dict[str, object]],
        ) -> dict[str, float]:
            calls.append(feature_rows)
            return {"peak_risk": 80.0, "trough_risk": 20.0}

        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            side_effect=recording_risk,
        ):
            predictions = walk_forward_predictions(reversed(self.rows(62)))

        self.assertEqual([len(rows) for rows in calls], [60, 61, 62])
        self.assertEqual(len(predictions), 3)
        for prediction, feature_rows in zip(predictions, calls, strict=True):
            prediction_date = prediction["as_of_date"]
            self.assertLessEqual(
                max(str(row["as_of_date"]) for row in feature_rows),
                prediction_date,
            )
            self.assertEqual(prediction["feature_max_date"], prediction_date)
            self.assertTrue(prediction["no_lookahead"])
            self.assertTrue(
                all(
                    "peak_label" not in row
                    and "trough_label" not in row
                    and "label_window_complete" not in row
                    for row in feature_rows
                )
            )

    def test_risk_percentages_are_joined_to_future_labels_as_probabilities(self) -> None:
        rows = self.rows(70)
        rows[64]["score_5d"] = 80.0
        rows[65]["score_5d"] = 60.0
        rows[66]["score_5d"] = 59.0
        rows[67]["score_5d"] = 58.0
        rows[68]["score_5d"] = 57.0
        rows[69]["score_5d"] = 56.0

        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            return_value={"peak_risk": 80.0, "trough_risk": 20.0},
        ):
            predictions = walk_forward_predictions(rows)

        center = next(row for row in predictions if row["as_of_date"] == "2026-03-06")
        self.assertEqual(center["peak_probability"], 0.8)
        self.assertEqual(center["trough_probability"], 0.2)
        self.assertTrue(center["peak_label"])
        self.assertFalse(center["trough_label"])


class SentimentValidationReportTests(unittest.TestCase):
    @staticmethod
    def cycle_rows(cycles: int) -> list[dict[str, object]]:
        scores = [50, 56, 62, 68, 74, 80, 74, 68, 62, 56, 50, 44, 38, 32, 26, 20, 26, 32, 38, 44]
        values = scores * cycles + scores[:5]
        start = date(2024, 1, 1)
        return [
            {
                "as_of_date": (start + timedelta(days=index)).isoformat(),
                "category": "Semiconductor",
                "methodology_version": "industry-sentiment-v1",
                "score_5d": float(score),
            }
            for index, score in enumerate(values)
        ]

    @staticmethod
    def informative_risk(
        feature_rows: list[dict[str, object]],
    ) -> dict[str, float]:
        score = feature_rows[-1]["score_5d"]
        return {
            "peak_risk": 90.0 if score == 80.0 else 10.0,
            "trough_risk": 90.0 if score == 20.0 else 10.0,
        }

    def test_short_history_fails_minimum_sessions_and_stays_experimental(self) -> None:
        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            side_effect=self.informative_risk,
        ):
            report = build_sentiment_validation_report(self.cycle_rows(5))

        self.assertEqual(report["status"], "experimental")
        self.assertFalse(report["promotion_ready"])
        self.assertFalse(report["promotion_checks"]["minimum_sessions"])
        self.assertIn("minimum_sessions", report["failed_checks"])
        self.assertEqual(
            set(report["promotion_checks"]),
            {
                "minimum_sessions",
                "minimum_peak_events",
                "minimum_trough_events",
                "no_lookahead",
                "peak_brier_beats_baseline",
                "trough_brier_beats_baseline",
                "two_stable_holdouts",
            },
        )

    def test_final_five_predictions_are_excluded_from_evaluation_universe(self) -> None:
        rows = SentimentWalkForwardTests.rows(65)
        rows[54]["score_5d"] = 60.0
        rows[55]["score_5d"] = 65.0
        rows[56]["score_5d"] = 70.0
        rows[57]["score_5d"] = 75.0
        rows[58]["score_5d"] = 79.0
        rows[59]["score_5d"] = 80.0
        rows[60]["score_5d"] = 70.0
        rows[61]["score_5d"] = 68.0
        rows[62]["score_5d"] = 66.0
        rows[63]["score_5d"] = 65.0
        rows[64]["score_5d"] = 64.0

        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            return_value={"peak_risk": 90.0, "trough_risk": 10.0},
        ):
            predictions = walk_forward_predictions(rows)
            report = build_sentiment_validation_report(rows)

        self.assertEqual(len(predictions), 6)
        self.assertEqual(
            [row["label_window_complete"] for row in predictions],
            [True, False, False, False, False, False],
        )
        self.assertEqual(report["prediction_count"], 6)
        self.assertEqual(report["leakage_audit"]["prediction_count"], 6)
        self.assertEqual(report["metrics"]["peak"]["observation_count"], 1)
        self.assertEqual(report["metrics"]["trough"]["observation_count"], 1)
        self.assertEqual(report["peak_event_count"], 1)
        self.assertEqual(report["trough_event_count"], 0)
        self.assertEqual(
            report["metrics"]["peak"]["thresholds"]["0.50"]
            ["predicted_positive_count"],
            1,
        )
        self.assertEqual(
            sum(row["observation_count"] for row in report["holdouts"]),
            1,
        )

    def test_informative_large_walk_forward_report_passes_mechanical_gates(self) -> None:
        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            side_effect=self.informative_risk,
        ):
            report = build_sentiment_validation_report(self.cycle_rows(33))

        self.assertEqual(report["status"], "experimental")
        self.assertTrue(report["promotion_ready"])
        self.assertEqual(report["failed_checks"], [])
        self.assertEqual(report["session_count"], 665)
        self.assertEqual(report["peak_event_count"], 30)
        self.assertEqual(report["trough_event_count"], 30)
        self.assertTrue(report["leakage_audit"]["no_lookahead"])
        self.assertEqual(len(report["holdouts"]), 2)
        self.assertTrue(all(row["stable"] for row in report["holdouts"]))
        self.assertLess(
            report["metrics"]["peak"]["brier_score"],
            report["metrics"]["peak"]["unconditional_brier_score"],
        )
        self.assertLess(
            report["metrics"]["trough"]["brier_score"],
            report["metrics"]["trough"]["unconditional_brier_score"],
        )
        for target in ("peak", "trough"):
            for threshold in ("0.50", "0.70"):
                self.assertEqual(
                    report["metrics"][target]["thresholds"][threshold]["precision"],
                    1.0,
                )
                self.assertEqual(
                    report["metrics"][target]["thresholds"][threshold]["recall"],
                    1.0,
                )

        first, second = report["holdouts"]
        self.assertLess(first["end_date"], second["start_date"])
        self.assertTrue(all(report["promotion_checks"].values()))


class SentimentValidationWriterTests(unittest.TestCase):
    @staticmethod
    def history_row(as_of_date: str) -> dict[str, object]:
        row: dict[str, object] = {field: None for field in SENTIMENT_HISTORY_COLUMNS}
        row.update(
            {
                "as_of_date": as_of_date,
                "category": "半導體",
                "methodology_version": "industry-sentiment-v1",
                "status": "ready",
                "score_5d": 50.0,
            }
        )
        return row

    def test_writer_loads_history_and_emits_sorted_traceable_utf8_json(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            history_path = root / "產業情緒.csv"
            output_path = root / "nested" / "validation.json"
            upsert_sentiment_snapshots(
                history_path,
                [self.history_row("2026-07-17")],
            )

            report = write_sentiment_validation_report(history_path, output_path)

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report, payload)
            self.assertEqual(payload["history_path"], str(history_path))
            self.assertEqual(payload["status"], "experimental")
            self.assertIn("產業情緒.csv", output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            self.assertTrue(output_path.parent.is_dir())
            self.assertTrue(
                all(
                    "peak_label" not in row and "trough_label" not in row
                    for row in load_sentiment_history(history_path)
                )
            )


class SentimentValidationDuplicateTests(unittest.TestCase):
    def test_identical_duplicates_including_final_row_collapse_once(self) -> None:
        rows = SentimentWalkForwardTests.rows(65)
        duplicated = [*rows, dict(rows[10]), dict(rows[-1])]
        original = [dict(row) for row in duplicated]

        with patch(
            "taiwan_stock_analysis.sentiment_validation.calculate_turning_risk",
            return_value={"peak_risk": 20.0, "trough_risk": 20.0},
        ):
            labels = label_turning_events(duplicated)
            predictions = walk_forward_predictions(duplicated)
            report = build_sentiment_validation_report(duplicated)

        prediction_keys = [
            (
                row["as_of_date"],
                row["category"],
                row["methodology_version"],
            )
            for row in predictions
        ]
        self.assertEqual(len(labels), 65)
        self.assertEqual(len(predictions), 6)
        self.assertEqual(len(prediction_keys), len(set(prediction_keys)))
        self.assertEqual(report["session_count"], 65)
        self.assertEqual(report["prediction_count"], 6)
        self.assertEqual(duplicated, original)

    def test_conflicting_final_duplicate_raises_with_composite_key(self) -> None:
        rows = SentimentWalkForwardTests.rows(65)
        conflict = dict(rows[-1])
        conflict["score_5d"] = 99.0
        duplicated = [*rows, conflict]
        expected = (
            r"conflicting duplicate.*composite key.*2026-03-06.*"
            r"Semiconductor.*industry-sentiment-v1"
        )

        for operation in (
            label_turning_events,
            walk_forward_predictions,
            build_sentiment_validation_report,
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, expected):
                    operation(duplicated)

    def test_writer_propagates_conflicting_duplicate_failure(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            history_path = root / "industry_sentiment_history.csv"
            output_path = root / "validation.json"
            first = SentimentValidationWriterTests.history_row("2026-07-17")
            conflict = dict(first)
            conflict["score_5d"] = 60.0
            with history_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=SENTIMENT_HISTORY_COLUMNS)
                writer.writeheader()
                writer.writerows([first, conflict])

            with self.assertRaisesRegex(
                ValueError,
                r"conflicting duplicate.*composite key.*2026-07-17.*半導體.*industry-sentiment-v1",
            ):
                write_sentiment_validation_report(history_path, output_path)

            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
