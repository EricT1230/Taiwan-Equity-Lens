import unittest

from taiwan_stock_analysis.metrics import calculate_metrics, find_field


class MetricsTests(unittest.TestCase):
    def test_find_field_matches_all_keywords(self):
        table = {
            "營業收入合計": {"2024": 1000.0},
            "每股稅後盈餘(元)": {"2024": 5.0},
        }

        self.assertEqual(find_field(table, "營業", "收入"), "營業收入合計")
        self.assertEqual(find_field(table, "每股", "盈餘"), "每股稅後盈餘(元)")
        self.assertIsNone(find_field(table, "不存在"))

    def test_calculate_metrics_derives_core_ratios_and_fcf(self):
        income = {
            "營業收入合計": {"2024": 1000.0},
            "營業毛利（毛損）": {"2024": 400.0},
            "營業利益（損失）": {"2024": 250.0},
            "稅後淨利": {"2024": 200.0},
            "推銷費用": {"2024": 60.0},
            "管理費用": {"2024": 40.0},
            "研究發展費用": {"2024": 100.0},
            "每股稅後盈餘(元)": {"2024": 8.5},
        }
        balance = {
            "流動資產合計": {"2024": 600.0},
            "流動負債合計": {"2024": 300.0},
            "負債總額": {"2024": 500.0},
            "資產總額": {"2024": 1250.0},
            "股東權益總額": {"2024": 750.0},
        }
        cash_flow = {
            "營業活動之淨現金流入（出）": {"2024": 180.0},
            "固定資產（增加）減少": {"2024": -50.0},
            "發放現金股利": {"2024": -30.0},
        }

        metrics = calculate_metrics(income, balance, cash_flow, ["2024"])

        self.assertEqual(metrics["2024"]["gross_margin"], 40.0)
        self.assertEqual(metrics["2024"]["op_margin"], 25.0)
        self.assertEqual(metrics["2024"]["net_margin"], 20.0)
        self.assertEqual(metrics["2024"]["sell_ratio"], 6.0)
        self.assertEqual(metrics["2024"]["admin_ratio"], 4.0)
        self.assertEqual(metrics["2024"]["rd_ratio"], 10.0)
        self.assertEqual(metrics["2024"]["total_opex_ratio"], 20.0)
        self.assertEqual(metrics["2024"]["current_ratio"], 200.0)
        self.assertEqual(metrics["2024"]["debt_ratio"], 40.0)
        self.assertAlmostEqual(metrics["2024"]["roe"], 26.6666666667)
        self.assertEqual(metrics["2024"]["roa"], 16.0)
        self.assertEqual(metrics["2024"]["free_cash_flow"], 130.0)
        self.assertEqual(metrics["2024"]["eps"], 8.5)
        self.assertEqual(metrics["2024"]["cash_dividend"], -30.0)

    def test_calculate_metrics_uses_fixed_asset_increase_decrease_for_capex(self):
        income = {"營業收入合計": {"2025": 1000.0}}
        balance = {}
        cash_flow = {
            "處分及報廢固定資產損失(利益)": {"2025": 15.81},
            "固定資產(增加)減少": {"2025": -12716.0},
            "營業活動之淨現金流入（出）": {"2025": 22750.0},
        }

        metrics = calculate_metrics(income, balance, cash_flow, ["2025"])

        self.assertEqual(metrics["2025"]["capex"], -12716.0)
        self.assertEqual(metrics["2025"]["free_cash_flow"], 10034.0)

    def test_calculate_metrics_adds_phase_two_quality_growth_and_leverage_metrics(self):
        income = {
            "\u71df\u696d\u6536\u5165\u5408\u8a08": {"2025": 1210.0, "2024": 1100.0, "2023": 1000.0},
            "\u7a05\u5f8c\u6de8\u5229": {"2025": 242.0, "2024": 220.0, "2023": 200.0},
            "\u6bcf\u80a1\u7a05\u5f8c\u76c8\u9918(\u5143)": {"2025": 12.1, "2024": 11.0, "2023": 10.0},
        }
        balance = {
            "\u73fe\u91d1\u53ca\u7d04\u7576\u73fe\u91d1": {"2025": 420.0, "2024": 360.0, "2023": 300.0},
            "\u6d41\u52d5\u8ca0\u50b5\u5408\u8a08": {"2025": 300.0, "2024": 300.0, "2023": 300.0},
            "\u8ca0\u50b5\u7e3d\u984d": {"2025": 500.0, "2024": 480.0, "2023": 450.0},
            "\u80a1\u6771\u6b0a\u76ca\u7e3d\u984d": {"2025": 1000.0, "2024": 900.0, "2023": 800.0},
        }
        cash_flow = {
            "\u71df\u696d\u6d3b\u52d5\u4e4b\u6de8\u73fe\u91d1\u6d41\u5165\uff08\u51fa\uff09": {
                "2025": 300.0,
                "2024": 260.0,
                "2023": 240.0,
            },
            "\u56fa\u5b9a\u8cc7\u7522(\u589e\u52a0)\u6e1b\u5c11": {"2025": -100.0, "2024": -90.0, "2023": -80.0},
            "\u767c\u653e\u73fe\u91d1\u80a1\u5229": {"2025": -120.0, "2024": -100.0, "2023": -90.0},
        }

        metrics = calculate_metrics(income, balance, cash_flow, ["2025", "2024", "2023"])

        self.assertAlmostEqual(metrics["2025"]["revenue_cagr"], 10.0)
        self.assertAlmostEqual(metrics["2025"]["eps_cagr"], 10.0)
        self.assertAlmostEqual(metrics["2025"]["equity_growth"], 11.1111111111)
        self.assertAlmostEqual(metrics["2025"]["operating_cash_flow_to_net_income"], 123.9669421488)
        self.assertAlmostEqual(metrics["2025"]["free_cash_flow_margin"], 16.5289256198)
        self.assertAlmostEqual(metrics["2025"]["payout_ratio"], 49.5867768595)
        self.assertEqual(metrics["2025"]["debt_to_equity"], 50.0)
        self.assertEqual(metrics["2025"]["cash_to_current_liabilities"], 140.0)

    def test_calculate_metrics_phase_two_metrics_preserve_missing_values(self):
        income = {
            "\u71df\u696d\u6536\u5165\u5408\u8a08": {"2025": 1000.0, "2024": 900.0},
            "\u7a05\u5f8c\u6de8\u5229": {"2025": 0.0, "2024": 100.0},
            "\u6bcf\u80a1\u7a05\u5f8c\u76c8\u9918(\u5143)": {"2025": 10.0, "2024": 0.0},
        }

        metrics = calculate_metrics(income, {}, {}, ["2025", "2024"])

        self.assertIsNone(metrics["2025"]["eps_cagr"])
        self.assertIsNone(metrics["2025"]["operating_cash_flow_to_net_income"])
        self.assertIsNone(metrics["2025"]["free_cash_flow_margin"])
        self.assertIsNone(metrics["2025"]["payout_ratio"])
        self.assertIsNone(metrics["2025"]["debt_to_equity"])
        self.assertIsNone(metrics["2025"]["cash_to_current_liabilities"])


if __name__ == "__main__":
    unittest.main()
