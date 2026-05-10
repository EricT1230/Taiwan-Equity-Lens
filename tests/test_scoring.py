import unittest

from taiwan_stock_analysis.scoring import build_scorecard, score_dimension


class ScoringTests(unittest.TestCase):
    def test_score_dimension_averages_available_rule_scores_and_records_confidence(self):
        result = score_dimension(
            "profitability",
            {"roe": 24.0, "roa": 12.0, "gross_margin": None, "net_margin": 22.0},
            [
                {"metric": "roe", "label": "ROE", "excellent": 20.0, "good": 12.0, "direction": "higher"},
                {"metric": "roa", "label": "ROA", "excellent": 10.0, "good": 6.0, "direction": "higher"},
                {"metric": "gross_margin", "label": "毛利率", "excellent": 40.0, "good": 25.0, "direction": "higher"},
                {"metric": "net_margin", "label": "淨利率", "excellent": 20.0, "good": 10.0, "direction": "higher"},
            ],
        )

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["confidence"], 75)
        self.assertTrue(any("ROE" in reason for reason in result["reasons"]))
        self.assertTrue(any("毛利率缺資料" in reason for reason in result["reasons"]))

    def test_build_scorecard_returns_five_dimensions_total_score_and_no_advice_words(self):
        metrics_by_year = {
            "2025": {
                "roe": 28.0,
                "roa": 18.0,
                "gross_margin": 55.0,
                "net_margin": 30.0,
                "revenue_cagr": 18.0,
                "eps_cagr": 16.0,
                "equity_growth": 12.0,
                "current_ratio": 220.0,
                "debt_ratio": 35.0,
                "debt_to_equity": 54.0,
                "operating_cash_flow_to_net_income": 130.0,
                "free_cash_flow_margin": 20.0,
                "payout_ratio": 45.0,
            }
        }

        scorecard = build_scorecard(metrics_by_year, ["2025"])

        self.assertEqual(scorecard["latest_year"], "2025")
        self.assertIn("profitability", scorecard["dimensions"])
        self.assertIn("growth", scorecard["dimensions"])
        self.assertIn("financial_safety", scorecard["dimensions"])
        self.assertIn("cash_flow_quality", scorecard["dimensions"])
        self.assertIn("dividend_quality", scorecard["dimensions"])
        self.assertGreaterEqual(scorecard["total_score"], 80)
        self.assertIn("valuation_excluded", scorecard["disclaimer"])
        flattened = str(scorecard)
        self.assertNotIn("買進", flattened)
        self.assertNotIn("賣出", flattened)

    def test_build_scorecard_lowers_confidence_when_data_is_missing(self):
        scorecard = build_scorecard({"2025": {"roe": 20.0}}, ["2025"])

        self.assertLess(scorecard["confidence"], 50)
        self.assertLess(scorecard["dimensions"]["growth"]["confidence"], 50)
        self.assertTrue(scorecard["dimensions"]["growth"]["reasons"])


if __name__ == "__main__":
    unittest.main()
