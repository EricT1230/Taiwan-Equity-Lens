import unittest

from taiwan_stock_analysis.insights import build_insights


class InsightTests(unittest.TestCase):
    def test_build_insights_generates_section_bullets_with_numbers(self):
        metrics_by_year = {
            "2025": {
                "revenue": 1200.0,
                "gross_margin": 55.0,
                "net_margin": 30.0,
                "eps": 12.0,
                "roe": 24.0,
                "current_ratio": 220.0,
                "debt_ratio": 35.0,
                "operating_cash_flow": 360.0,
                "free_cash_flow": 180.0,
                "revenue_cagr": 22.5,
                "operating_cash_flow_to_net_income": 120.0,
                "free_cash_flow_margin": 15.0,
                "debt_to_equity": 53.8,
                "payout_ratio": 40.0,
            },
            "2024": {
                "revenue": 1000.0,
                "gross_margin": 50.0,
                "net_margin": 25.0,
                "eps": 10.0,
                "roe": 20.0,
                "current_ratio": 200.0,
                "debt_ratio": 40.0,
                "operating_cash_flow": 250.0,
                "free_cash_flow": 100.0,
            },
            "2023": {
                "revenue": 800.0,
                "gross_margin": 45.0,
                "net_margin": 20.0,
                "eps": 8.0,
                "roe": 18.0,
                "current_ratio": 180.0,
                "debt_ratio": 45.0,
                "operating_cash_flow": 200.0,
                "free_cash_flow": 80.0,
            },
        }

        insights = build_insights(metrics_by_year, ["2025", "2024", "2023"])

        self.assertIn("operations", insights)
        self.assertIn("profitability", insights)
        self.assertIn("financial_health", insights)
        self.assertGreaterEqual(len(insights["operations"]), 3)
        self.assertTrue(any("20.0%" in bullet for bullet in insights["operations"]))
        self.assertTrue(any("55.0%" in bullet for bullet in insights["operations"]))
        self.assertTrue(any("CAGR" in bullet and "22.5%" in bullet for bullet in insights["operations"]))
        self.assertTrue(any("12.00" in bullet for bullet in insights["profitability"]))
        self.assertTrue(any("120.0%" in bullet for bullet in insights["profitability"]))
        self.assertTrue(any("220.0%" in bullet for bullet in insights["financial_health"]))
        self.assertTrue(any("53.8%" in bullet for bullet in insights["financial_health"]))


if __name__ == "__main__":
    unittest.main()
