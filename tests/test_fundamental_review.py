import unittest

from taiwan_stock_analysis.fundamental_review import build_fundamental_review


class FundamentalReviewTests(unittest.TestCase):
    def test_build_fundamental_review_scores_expert_agents(self):
        review = build_fundamental_review(
            stock_id="2330",
            research_row={
                "thesis": "Leading foundry scale with durable customer relationships.",
                "key_risks": "Cycle downturn and margin compression.",
                "watch_triggers": "Monthly revenue and gross margin trend.",
            },
            analysis_payload={
                "years": ["2025", "2024", "2023"],
                "metrics_by_year": {
                    "2025": {
                        "roe": 30.0,
                        "gross_margin": 50.0,
                        "net_margin": 25.0,
                        "debt_ratio": 35.0,
                        "debt_to_equity": 55.0,
                        "operating_cash_flow": 320.0,
                        "net_income": 250.0,
                        "operating_cash_flow_to_net_income": 128.0,
                        "free_cash_flow_margin": 18.0,
                    }
                },
                "valuation": {
                    "scenario_summary": {
                        "margin_of_safety_percent": 20.0,
                        "fair_value_range": {"low": 80.0, "base": 120.0, "high": 170.0},
                        "valuation_confidence": {"score": 85, "label": "high"},
                    }
                },
            },
            source_status="available",
            reliability_status="ok",
        )

        self.assertEqual(review["style"], "buffett_value_review")
        self.assertEqual(review["verdict"], "ready_for_manual_review")
        self.assertGreaterEqual(review["score"], 80)
        self.assertEqual(
            sorted(review["agent_scores"]),
            ["bear_case_risk", "buffett_moat", "fundamental_quality", "valuation_margin_of_safety"],
        )
        self.assertIn("not investment advice", review["non_advice_notice"])

    def test_build_fundamental_review_marks_missing_analysis_incomplete(self):
        review = build_fundamental_review(
            stock_id="9999",
            research_row={},
            analysis_payload=None,
            source_status="missing",
            reliability_status="skipped",
        )

        self.assertEqual(review["verdict"], "incomplete")
        self.assertIsNone(review["score"])
        self.assertIn("Core financial analysis data is unavailable.", review["thesis_breakers"])

    def test_build_fundamental_review_surfaces_thesis_breakers(self):
        review = build_fundamental_review(
            stock_id="2303",
            research_row={"thesis": "", "key_risks": "", "watch_triggers": ""},
            analysis_payload={
                "years": ["2025"],
                "metrics_by_year": {
                    "2025": {
                        "roe": 8.0,
                        "gross_margin": 20.0,
                        "net_margin": 4.0,
                        "debt_ratio": 75.0,
                        "debt_to_equity": 160.0,
                        "operating_cash_flow": -20.0,
                        "net_income": 10.0,
                        "operating_cash_flow_to_net_income": -200.0,
                        "free_cash_flow_margin": -5.0,
                    }
                },
                "valuation": {},
            },
            source_status="available",
            reliability_status="warning",
        )

        self.assertEqual(review["verdict"], "needs_work")
        self.assertIn("Moat thesis is missing from the research row.", review["thesis_breakers"])
        self.assertIn("Bear case is missing from the research row.", review["thesis_breakers"])
        self.assertIn("Valuation scenario is unavailable.", review["thesis_breakers"])


if __name__ == "__main__":
    unittest.main()
