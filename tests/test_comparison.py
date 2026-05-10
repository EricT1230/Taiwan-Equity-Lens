import unittest

from taiwan_stock_analysis.comparison import compare_results
from taiwan_stock_analysis.models import AnalysisResult
from taiwan_stock_analysis.report_compare import render_comparison_html


def result(stock_id: str, metrics: dict[str, float | None]) -> AnalysisResult:
    return AnalysisResult(stock_id=stock_id, years=["2025"], metrics_by_year={"2025": metrics})


class ComparisonTests(unittest.TestCase):
    def test_compare_results_aligns_latest_metrics_and_ranks_dimensions(self):
        comparison = compare_results(
            [
                result(
                    "2330",
                    {
                        "gross_margin": 60.0,
                        "roe": 30.0,
                        "revenue_cagr": 20.0,
                        "debt_ratio": 30.0,
                        "free_cash_flow_margin": 25.0,
                        "operating_cash_flow_to_net_income": 130.0,
                    },
                ),
                result(
                    "2303",
                    {
                        "gross_margin": 45.0,
                        "roe": 18.0,
                        "revenue_cagr": 12.0,
                        "debt_ratio": 55.0,
                        "free_cash_flow_margin": 10.0,
                        "operating_cash_flow_to_net_income": 90.0,
                    },
                ),
                result(
                    "2454",
                    {
                        "gross_margin": None,
                        "roe": 22.0,
                        "revenue_cagr": 15.0,
                        "debt_ratio": 20.0,
                        "free_cash_flow_margin": None,
                        "operating_cash_flow_to_net_income": 110.0,
                    },
                ),
            ]
        )

        rows = {row["stock_id"]: row for row in comparison["rows"]}
        self.assertEqual(rows["2330"]["gross_margin_rank"], 1)
        self.assertEqual(rows["2454"]["debt_ratio_rank"], 1)
        self.assertIsNone(rows["2454"]["gross_margin_rank"])
        self.assertEqual(comparison["dimensions"][0]["metric"], "gross_margin")

    def test_render_comparison_html_contains_ranked_table_and_embedded_json(self):
        comparison = compare_results(
            [
                result("2330", {"gross_margin": 60.0, "debt_ratio": 30.0}),
                result("2303", {"gross_margin": 45.0, "debt_ratio": 55.0}),
            ]
        )

        html = render_comparison_html(comparison)

        self.assertIn("同業比較", html)
        self.assertIn("2330", html)
        self.assertIn("毛利率", html)
        self.assertIn("application/json", html)


if __name__ == "__main__":
    unittest.main()
