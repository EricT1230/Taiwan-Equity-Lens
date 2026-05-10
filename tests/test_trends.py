import unittest

from taiwan_stock_analysis.trends import cagr, classify_trend, yoy_change


class TrendTests(unittest.TestCase):
    def test_yoy_change_uses_latest_and_previous_year(self):
        values = {"2025": 120.0, "2024": 100.0, "2023": 80.0}

        self.assertEqual(yoy_change(values, ["2025", "2024", "2023"]), 20.0)

    def test_yoy_change_returns_none_for_missing_or_zero_previous_value(self):
        self.assertIsNone(yoy_change({"2025": 120.0}, ["2025", "2024"]))
        self.assertIsNone(yoy_change({"2025": 120.0, "2024": 0.0}, ["2025", "2024"]))

    def test_cagr_uses_oldest_and_latest_positive_values(self):
        result = cagr({"2025": 121.0, "2024": 110.0, "2023": 100.0}, ["2025", "2024", "2023"])

        self.assertAlmostEqual(result, 10.0)

    def test_cagr_returns_none_when_base_is_not_positive(self):
        self.assertIsNone(cagr({"2025": 121.0, "2023": 0.0}, ["2025", "2024", "2023"]))
        self.assertIsNone(cagr({"2025": 121.0}, ["2025", "2024", "2023"]))

    def test_classify_trend_labels_common_sequences(self):
        self.assertEqual(classify_trend([80.0, 100.0, 120.0]), "improving")
        self.assertEqual(classify_trend([120.0, 100.0, 80.0]), "worsening")
        self.assertEqual(classify_trend([100.0, 101.0, 100.5]), "stable")
        self.assertEqual(classify_trend([100.0, 130.0, 90.0]), "volatile")
        self.assertEqual(classify_trend([100.0]), "insufficient")


if __name__ == "__main__":
    unittest.main()
