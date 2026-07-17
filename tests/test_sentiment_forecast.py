from datetime import date, timedelta
import math
from statistics import median
import unittest

import taiwan_stock_analysis.sentiment_forecast as sentiment_forecast
from taiwan_stock_analysis.sentiment_forecast import (
    RISK_FAMILY_MAXIMUMS,
    calculate_turning_risk,
    project_sentiment,
)


def _score_rows(
    count: int,
    *,
    start: float = -20.0,
    step: float = 1.0,
) -> list[dict[str, object]]:
    first_date = date(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for index in range(count):
        score = start + step * index
        rows.append(
            {
                "as_of_date": (first_date + timedelta(days=index)).isoformat(),
                "methodology_version": "industry-sentiment-v1",
                "score_5d": score,
                "baseline_20d": score,
                "rank": 4,
                "ranked_count": 8,
            }
        )
    return rows


def _weighted_slope_for_spec(values: list[float]) -> float:
    x_values = [float(index) for index in range(len(values))]
    weights = [
        0.5 ** ((len(values) - 1 - index) / 3.0)
        for index in range(len(values))
    ]
    weight_sum = sum(weights)
    x_mean = sum(
        weight * value for weight, value in zip(weights, x_values)
    ) / weight_sum
    y_mean = sum(
        weight * value for weight, value in zip(weights, values)
    ) / weight_sum
    return sum(
        weight * (x_value - x_mean) * (y_value - y_mean)
        for weight, x_value, y_value in zip(weights, x_values, values)
    ) / sum(
        weight * (x_value - x_mean) ** 2
        for weight, x_value in zip(weights, x_values)
    )


class SentimentProjectionTests(unittest.TestCase):
    def test_projection_history_gate_is_literal(self) -> None:
        insufficient = project_sentiment(_score_rows(19))
        ready = project_sentiment(_score_rows(20))

        self.assertEqual(insufficient["status"], "insufficient_history")
        self.assertEqual(insufficient["history_days"], 19)
        self.assertIsNone(insufficient["forecast_1d"])
        self.assertIsNone(insufficient["forecast_5d"])
        self.assertEqual(ready["status"], "experimental")
        self.assertEqual(ready["history_days"], 20)
        self.assertIsNotNone(ready["forecast_1d"])
        self.assertIsNotNone(ready["forecast_5d"])

    def test_linear_projection_uses_weighted_slope_and_mean_reversion(self) -> None:
        rows = _score_rows(20, start=-18.0, step=2.0)
        rows[-1]["baseline_20d"] = 10.0

        projection = project_sentiment(rows)

        self.assertAlmostEqual(projection["forecast_slope_10d"], 2.0)
        self.assertAlmostEqual(projection["daily_step"], 1.25)
        self.assertAlmostEqual(projection["forecast_1d"], 21.25)
        self.assertAlmostEqual(projection["forecast_5d"], 26.25)

    def test_projection_clamps_point_forecasts_to_score_bounds(self) -> None:
        projection = project_sentiment(_score_rows(20, start=62.0, step=2.0))

        self.assertAlmostEqual(projection["forecast_1d"], 100.0)
        self.assertAlmostEqual(projection["forecast_5d"], 100.0)

    def test_constant_sequence_has_zero_width_residual_intervals(self) -> None:
        projection = project_sentiment(_score_rows(20, start=25.0, step=0.0))

        self.assertEqual(projection["residual_count"], 10)
        self.assertAlmostEqual(projection["robust_sigma"], 0.0)
        self.assertEqual(
            projection["interval_1d"],
            [projection["forecast_1d"], projection["forecast_1d"]],
        )
        self.assertEqual(
            projection["interval_5d"],
            [projection["forecast_5d"], projection["forecast_5d"]],
        )

    def test_twenty_rows_produce_ten_strictly_prior_one_step_residuals(self) -> None:
        scores = [
            0.0,
            1.0,
            4.0,
            2.0,
            7.0,
            3.0,
            9.0,
            4.0,
            12.0,
            5.0,
            15.0,
            6.0,
            18.0,
            7.0,
            21.0,
            8.0,
            24.0,
            9.0,
            27.0,
            10.0,
        ]
        rows = _score_rows(20, start=0.0, step=0.0)
        for row, score in zip(rows, scores, strict=True):
            row["score_5d"] = score
            row["baseline_20d"] = score

        residuals = []
        for index in range(10, len(scores)):
            prior_scores = scores[index - 10 : index]
            prior_step = 0.70 * _weighted_slope_for_spec(prior_scores)
            residuals.append(scores[index] - (scores[index - 1] + prior_step))
        residual_median = median(residuals)
        expected_sigma = 1.4826 * median(
            abs(value - residual_median) for value in residuals
        )

        projection = project_sentiment(rows)

        self.assertEqual(projection["residual_count"], 10)
        self.assertAlmostEqual(projection["robust_sigma"], expected_sigma)
        self.assertAlmostEqual(
            projection["interval_1d"][0],
            max(-100.0, projection["forecast_1d"] - 1.96 * expected_sigma),
        )
        self.assertAlmostEqual(
            projection["interval_5d"][1],
            min(
                100.0,
                projection["forecast_5d"]
                + 1.96 * expected_sigma * math.sqrt(5.0),
            ),
        )


class TurningRiskGateTests(unittest.TestCase):
    def test_turning_risk_history_gate_is_literal(self) -> None:
        insufficient = calculate_turning_risk(_score_rows(59))
        ready = calculate_turning_risk(_score_rows(60))

        self.assertEqual(insufficient["status"], "insufficient_history")
        self.assertEqual(insufficient["history_days"], 59)
        self.assertEqual(
            set(insufficient["diagnostics"]["peak"]),
            set(RISK_FAMILY_MAXIMUMS),
        )
        self.assertTrue(
            all(
                contribution == 0.0
                for contribution in insufficient["diagnostics"]["trough"].values()
            )
        )
        self.assertEqual(ready["status"], "experimental")
        self.assertEqual(ready["history_days"], 60)
        self.assertIsNone(ready["calibrated_probability"])


class TurningRiskDiagnosticTests(unittest.TestCase):
    @staticmethod
    def risk_rows(direction: str) -> list[dict[str, object]]:
        if direction == "peak":
            rows = _score_rows(60, start=-30.0, step=0.5)
            final_scores = [30.0, 45.0, 60.0, 75.0, 76.0, 77.0]
            rank = 1
            current_fields = {
                "breadth_5d": 0.50,
                "breadth_20d": 0.80,
                "fund_flow_score_5d": 0.0,
                "fund_flow_score_20d": 50.0,
                "news_positive_topic_concentration_5d": 0.65,
                "news_negative_topic_concentration_5d": 0.10,
                "volume_ratio_5d": 2.0,
                "price_return_5d": 1.0,
            }
        elif direction == "trough":
            rows = _score_rows(60, start=30.0, step=-0.5)
            final_scores = [-30.0, -45.0, -60.0, -75.0, -76.0, -77.0]
            rank = 8
            current_fields = {
                "breadth_5d": 0.80,
                "breadth_20d": 0.50,
                "fund_flow_score_5d": 50.0,
                "fund_flow_score_20d": 0.0,
                "news_positive_topic_concentration_5d": 0.10,
                "news_negative_topic_concentration_5d": 0.65,
                "volume_ratio_5d": 2.0,
                "price_return_5d": -1.0,
            }
        else:
            raise ValueError(f"unsupported direction: {direction}")

        for row, score in zip(rows[-6:], final_scores, strict=True):
            row["score_5d"] = score
            row["baseline_20d"] = score
        for row in rows[-5:]:
            row["rank"] = rank
        rows[-1].update(current_fields)
        return rows

    def test_peak_diagnostics_produce_near_term_shadow_risk(self) -> None:
        risk = calculate_turning_risk(self.risk_rows("peak"))

        self.assertGreaterEqual(risk["peak_risk"], 70.0)
        self.assertEqual(risk["direction"], "peak")
        self.assertEqual(risk["window"], "1_to_3_days")
        self.assertIsNone(risk["calibrated_probability"])
        self.assertEqual(risk["diagnostics"]["peak"]["breadth"], 20.0)
        self.assertEqual(risk["diagnostics"]["peak"]["flow"], 15.0)
        self.assertEqual(risk["diagnostics"]["peak"]["crowding"], 15.0)
        self.assertEqual(risk["diagnostics"]["trough"]["breadth"], 0.0)
        self.assertEqual(set(risk["diagnostics"]["peak"]), set(RISK_FAMILY_MAXIMUMS))
        self.assertTrue(
            all(
                risk["diagnostics"]["peak"][family] <= maximum
                for family, maximum in RISK_FAMILY_MAXIMUMS.items()
            )
        )

    def test_trough_diagnostics_mirror_peak_risk(self) -> None:
        risk = calculate_turning_risk(self.risk_rows("trough"))

        self.assertGreaterEqual(risk["trough_risk"], 70.0)
        self.assertEqual(risk["direction"], "trough")
        self.assertEqual(risk["window"], "1_to_3_days")
        self.assertEqual(risk["diagnostics"]["trough"]["breadth"], 20.0)
        self.assertEqual(risk["diagnostics"]["trough"]["flow"], 15.0)
        self.assertEqual(risk["diagnostics"]["trough"]["crowding"], 15.0)
        self.assertEqual(risk["diagnostics"]["peak"]["breadth"], 0.0)
        self.assertEqual(set(risk["diagnostics"]["trough"]), set(RISK_FAMILY_MAXIMUMS))

    def test_missing_breadth_and_flow_are_absent_families_with_warnings(self) -> None:
        rows = self.risk_rows("peak")
        for field in (
            "breadth_5d",
            "breadth_20d",
            "fund_flow_score_5d",
            "fund_flow_score_20d",
        ):
            rows[-1].pop(field)

        risk = calculate_turning_risk(rows)

        self.assertEqual(risk["diagnostics"]["peak"]["breadth"], 0.0)
        self.assertEqual(risk["diagnostics"]["trough"]["breadth"], 0.0)
        self.assertEqual(risk["diagnostics"]["peak"]["flow"], 0.0)
        self.assertEqual(risk["diagnostics"]["trough"]["flow"], 0.0)
        self.assertTrue(any("breadth" in warning for warning in risk["warnings"]))
        self.assertTrue(any("flow" in warning for warning in risk["warnings"]))

    def test_both_sides_above_fifty_force_regime_uncertainty(self) -> None:
        direction, window, warnings = sentiment_forecast._resolve_turning_signal(
            peak_risk=75.0,
            peak_agreeing_families=3,
            trough_risk=60.0,
            trough_agreeing_families=2,
        )

        self.assertEqual(direction, "unclear")
        self.assertEqual(window, "unclear")
        self.assertIn(
            "regime uncertainty: peak and trough diagnostics conflict",
            warnings,
        )


if __name__ == "__main__":
    unittest.main()
