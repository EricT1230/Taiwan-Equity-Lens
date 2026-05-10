import unittest


from taiwan_stock_analysis.models import AnalysisResult


class AnalysisResultTests(unittest.TestCase):
    def test_analysis_result_exposes_core_sections(self):
        result = AnalysisResult(stock_id="2330", years=["2024"])

        self.assertEqual(result.stock_id, "2330")
        self.assertEqual(result.years, ["2024"])
        self.assertEqual(result.income_statement, {})
        self.assertEqual(result.balance_sheet, {})
        self.assertEqual(result.cash_flow, {})
        self.assertEqual(result.metrics_by_year, {})
        self.assertEqual(result.insights, {})
        self.assertEqual(result.scorecard, {})
        self.assertEqual(result.valuation, {})
        self.assertEqual(result.diagnostics, {})
        self.assertEqual(result.metadata, {})
        self.assertEqual(result.verification, {})


if __name__ == "__main__":
    unittest.main()
