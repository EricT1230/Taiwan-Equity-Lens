import unittest
from pathlib import Path

from taiwan_stock_analysis.price_data import load_price_data
from taiwan_stock_analysis.valuation import build_valuation, calculate_valuation


class ValuationTests(unittest.TestCase):
    def test_load_price_data_reads_stock_inputs_from_csv(self):
        path = Path(".tmp-cli-test/valuation.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high,eps_growth_rate\n"
            "2330,1000,160,12,60,15,20,25,10\n",
            encoding="utf-8",
        )

        data = load_price_data(path)

        self.assertEqual(data["2330"]["price"], 1000.0)
        self.assertEqual(data["2330"]["book_value_per_share"], 160.0)
        self.assertEqual(data["2330"]["target_pe_base"], 20.0)
        self.assertEqual(data["2330"]["eps_growth_rate"], 10.0)

    def test_calculate_valuation_computes_pe_pb_yield_and_pe_scenarios(self):
        valuation = calculate_valuation(
            price=1000.0,
            eps=50.0,
            book_value_per_share=160.0,
            cash_dividend_per_share=12.0,
            normalized_eps=60.0,
            target_pe_low=15.0,
            target_pe_base=20.0,
            target_pe_high=25.0,
        )

        self.assertEqual(valuation["pe"], 20.0)
        self.assertEqual(valuation["pb"], 6.25)
        self.assertEqual(valuation["dividend_yield"], 1.2)
        self.assertEqual(valuation["fair_value_low"], 900.0)
        self.assertEqual(valuation["fair_value_base"], 1200.0)
        self.assertEqual(valuation["fair_value_high"], 1500.0)
        self.assertEqual(valuation["price_to_base_fair_value"], 83.33333333333334)

    def test_calculate_valuation_preserves_missing_values(self):
        valuation = calculate_valuation(
            price=1000.0,
            eps=None,
            book_value_per_share=0.0,
            cash_dividend_per_share=None,
            normalized_eps=None,
            target_pe_low=15.0,
            target_pe_base=20.0,
            target_pe_high=25.0,
        )

        self.assertIsNone(valuation["pe"])
        self.assertIsNone(valuation["pb"])
        self.assertIsNone(valuation["dividend_yield"])
        self.assertIsNone(valuation["fair_value_base"])

    def test_build_valuation_combines_metrics_and_price_inputs_without_advice_words(self):
        valuation = build_valuation(
            stock_id="2330",
            metrics_by_year={"2025": {"eps": 50.0}},
            years=["2025"],
            price_inputs={
                "price": 1000.0,
                "book_value_per_share": 160.0,
                "cash_dividend_per_share": 12.0,
                "normalized_eps": 60.0,
                "target_pe_low": 15.0,
                "target_pe_base": 20.0,
                "target_pe_high": 25.0,
            },
        )

        self.assertEqual(valuation["latest_year"], "2025")
        self.assertEqual(valuation["metrics"]["pe"], 20.0)
        self.assertIn("高品質", valuation["context"])
        flattened = str(valuation)
        self.assertNotIn("買進", flattened)
        self.assertNotIn("賣出", flattened)

    def test_build_valuation_derives_eps_scenarios_and_target_price_gaps(self):
        valuation = build_valuation(
            stock_id="2330",
            metrics_by_year={
                "2025": {"eps": 50.0},
                "2024": {"eps": 40.0},
                "2023": {"eps": 30.0},
            },
            years=["2025", "2024", "2023"],
            price_inputs={
                "price": 1000.0,
                "target_pe_low": 15.0,
                "target_pe_base": 20.0,
                "target_pe_high": 25.0,
                "eps_growth_rate": 10.0,
            },
        )

        self.assertEqual(valuation["eps_scenarios"]["conservative"], 40.0)
        self.assertEqual(valuation["eps_scenarios"]["base"], 50.0)
        self.assertEqual(valuation["eps_scenarios"]["optimistic"], 55.0)
        self.assertEqual(valuation["target_prices"]["low"]["target_price"], 600.0)
        self.assertEqual(valuation["target_prices"]["base"]["target_price"], 1000.0)
        self.assertEqual(valuation["target_prices"]["high"]["target_price"], 1375.0)
        self.assertEqual(valuation["target_prices"]["low"]["price_gap_percent"], -40.0)
        self.assertEqual(valuation["target_prices"]["base"]["price_gap_percent"], 0.0)
        self.assertEqual(valuation["target_prices"]["high"]["price_gap_percent"], 37.5)


if __name__ == "__main__":
    unittest.main()
