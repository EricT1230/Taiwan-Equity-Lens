import unittest

from taiwan_stock_analysis.diagnostics import build_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_build_diagnostics_flags_insufficient_years_missing_fields_and_metrics(self):
        diagnostics = build_diagnostics(
            years=["2024", "2023"],
            income_statement={"營業收入合計": {"2024": 1000.0}},
            balance_sheet={"流動資產合計": {"2024": 600.0}},
            cash_flow={},
            metrics_by_year={"2024": {"revenue": 1000.0, "net_income": 200.0}},
        )

        messages = [issue["message"] for issue in diagnostics["issues"]]

        self.assertGreaterEqual(diagnostics["issue_count"], 4)
        self.assertTrue(any("分析年度少於 3 年" in message for message in messages))
        self.assertTrue(any("資產負債表" in message for message in messages))
        self.assertTrue(any("現金流量表" in message for message in messages))
        self.assertTrue(any("free_cash_flow_margin" in issue["field"] for issue in diagnostics["issues"]))

    def test_build_diagnostics_flags_cash_flow_conflict(self):
        diagnostics = build_diagnostics(
            years=["2024", "2023", "2022"],
            income_statement={
                "營業收入合計": {"2024": 1000.0},
                "稅後淨利": {"2024": 200.0},
                "每股稅後盈餘(元)": {"2024": 10.0},
            },
            balance_sheet={
                "流動資產合計": {"2024": 600.0},
                "流動負債合計": {"2024": 300.0},
                "負債總額": {"2024": 500.0},
                "股東權益總額": {"2024": 750.0},
            },
            cash_flow={"營業活動之淨現金流入（出）": {"2024": -50.0}},
            metrics_by_year={
                "2024": {
                    "revenue": 1000.0,
                    "net_income": 200.0,
                    "eps": 10.0,
                    "roe": 20.0,
                    "free_cash_flow_margin": -8.0,
                    "debt_ratio": 40.0,
                    "operating_cash_flow": -50.0,
                }
            },
        )

        self.assertTrue(
            any(issue["category"] == "cash_flow" for issue in diagnostics["issues"])
        )


if __name__ == "__main__":
    unittest.main()
