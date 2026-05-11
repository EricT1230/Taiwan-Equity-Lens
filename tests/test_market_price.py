import csv
import io
import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.market_price import (
    fetch_latest_close,
    fetch_twse_latest_close,
    load_analysis_enrichment,
    parse_tpex_daily_close,
    parse_twse_stock_day,
    write_valuation_template,
)


class MarketPriceTests(unittest.TestCase):
    def test_parse_twse_stock_day_uses_latest_valid_close(self):
        payload = {
            "stat": "OK",
            "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"],
            "data": [
                ["115/05/04", "10,000", "1,000,000", "100.00", "101.00", "99.00", "100.50"],
                ["115/05/05", "10,000", "1,010,000", "101.00", "102.00", "100.00", "--"],
                ["115/05/06", "10,000", "1,020,000", "102.00", "103.00", "101.00", "102.50"],
            ],
        }

        price = parse_twse_stock_day("2330", payload)

        self.assertEqual(price["stock_id"], "2330")
        self.assertEqual(price["price"], 102.5)
        self.assertEqual(price["price_date"], "115/05/06")
        self.assertEqual(price["price_source"], "TWSE_STOCK_DAY")
        self.assertEqual(price["warning"], "")

    def test_fetch_twse_latest_close_returns_warning_when_no_price(self):
        def fake_fetch(url: str) -> bytes:
            return '{"stat":"OK","fields":["日期","收盤價"],"data":[]}'.encode("utf-8")

        price = fetch_twse_latest_close("9999", date="20260510", fetch=fake_fetch)

        self.assertEqual(price["stock_id"], "9999")
        self.assertIsNone(price["price"])
        self.assertIn("no TWSE close price", price["warning"])

    def test_parse_tpex_daily_close_finds_stock_close_price(self):
        payload = {
            "date": "115/05/06",
            "aaData": [
                ["6187", "萬潤", "125.50", "+1.00", "124.00"],
                ["9999", "測試", "--", "", ""],
            ],
        }

        price = parse_tpex_daily_close("6187", payload)

        self.assertEqual(price["stock_id"], "6187")
        self.assertEqual(price["price"], 125.5)
        self.assertEqual(price["price_date"], "115/05/06")
        self.assertEqual(price["price_source"], "TPEX_DAILY_CLOSE")
        self.assertEqual(price["warning"], "")

    def test_parse_tpex_daily_close_uses_query_date_when_payload_date_missing(self):
        payload = {"aaData": [["6187", "萬潤", "125.50"]]}

        price = parse_tpex_daily_close("6187", payload, price_date="115/05/06")

        self.assertEqual(price["price"], 125.5)
        self.assertEqual(price["price_date"], "115/05/06")

    def test_fetch_latest_close_falls_back_to_tpex_when_twse_has_no_price(self):
        calls = []

        def fake_fetch(url: str) -> bytes:
            calls.append(url)
            if "twse.com.tw" in url:
                return '{"stat":"OK","fields":["日期","收盤價"],"data":[]}'.encode("utf-8")
            return json.dumps(
                {
                    "date": "115/05/06",
                    "aaData": [["6187", "萬潤", "125.50", "+1.00", "124.00"]],
                },
                ensure_ascii=False,
            ).encode("utf-8")

        price = fetch_latest_close("6187", date="20260506", fetch=fake_fetch)

        self.assertEqual(price["price"], 125.5)
        self.assertEqual(price["price_source"], "TPEX_DAILY_CLOSE")
        self.assertTrue(any("twse.com.tw" in call for call in calls))
        self.assertTrue(any("tpex.org.tw" in call for call in calls))

    def test_fetch_latest_close_falls_back_to_tpex_when_twse_fetch_fails(self):
        calls = []

        def fake_fetch(url: str) -> bytes:
            calls.append(url)
            if "twse.com.tw" in url:
                raise OSError("network down")
            return json.dumps(
                {
                    "date": "115/05/06",
                    "aaData": [["6187", "萬潤", "125.50", "+1.00", "124.00"]],
                },
                ensure_ascii=False,
            ).encode("utf-8")

        price = fetch_latest_close("6187", date="20260506", fetch=fake_fetch)

        self.assertEqual(price["price"], 125.5)
        self.assertEqual(price["price_source"], "TPEX_DAILY_CLOSE")
        self.assertEqual(price["warning"], "")
        self.assertTrue(any("twse.com.tw" in call for call in calls))
        self.assertTrue(any("tpex.org.tw" in call for call in calls))

    def test_fetch_latest_close_keeps_twse_when_twse_succeeds(self):
        calls = []

        def fake_fetch(url: str) -> bytes:
            calls.append(url)
            return json.dumps(
                {
                    "stat": "OK",
                    "fields": ["日期", "收盤價"],
                    "data": [["115/05/06", "1000.00"]],
                },
                ensure_ascii=False,
            ).encode("utf-8")

        price = fetch_latest_close("2330", date="20260506", fetch=fake_fetch)

        self.assertEqual(price["price"], 1000.0)
        self.assertEqual(price["price_source"], "TWSE_STOCK_DAY")
        self.assertEqual(len(calls), 1)
        self.assertIn("twse.com.tw", calls[0])

    def test_fetch_latest_close_combines_warnings_when_both_sources_fail(self):
        def fake_fetch(url: str) -> bytes:
            if "twse.com.tw" in url:
                return '{"stat":"OK","fields":["日期","收盤價"],"data":[]}'.encode("utf-8")
            return json.dumps({"date": "115/05/06", "aaData": []}).encode("utf-8")

        price = fetch_latest_close("9999", date="20260506", fetch=fake_fetch)

        self.assertIsNone(price["price"])
        self.assertIn("no TWSE close price", price["warning"])
        self.assertIn("no TPEx close price", price["warning"])

    def test_write_valuation_template_writes_price_rows_and_blank_assumptions(self):
        output = Path(".tmp-cli-test/valuation-template.csv")

        def fake_fetch_price(stock_id: str):
            if stock_id == "2330":
                return {
                    "stock_id": "2330",
                    "price": 1000.0,
                    "price_date": "115/05/06",
                    "price_source": "TWSE_STOCK_DAY",
                    "warning": "",
                }
            return {
                "stock_id": stock_id,
                "price": None,
                "price_date": "",
                "price_source": "TWSE_STOCK_DAY",
                "warning": "no TWSE close price",
            }

        write_valuation_template(["2330", "9999"], output, fetch_price=fake_fetch_price)

        reader = csv.DictReader(io.StringIO(output.read_text(encoding="utf-8")))
        self.assertEqual(
            reader.fieldnames,
            [
                "stock_id",
                "price",
                "book_value_per_share",
                "cash_dividend_per_share",
                "normalized_eps",
                "target_pe_low",
                "target_pe_base",
                "target_pe_high",
                "eps_growth_rate",
                "price_date",
                "price_source",
                "price_status",
                "price_status_message",
                "price_retry_hint",
                "warning",
            ],
        )
        rows = list(reader)
        self.assertEqual(rows[0]["stock_id"], "2330")
        self.assertEqual(rows[0]["price"], "1000.0")
        self.assertEqual(rows[0]["target_pe_base"], "")
        self.assertEqual(rows[1]["stock_id"], "9999")
        self.assertEqual(rows[1]["price"], "")
        self.assertEqual(rows[1]["warning"], "no TWSE close price")

    def test_write_valuation_template_records_price_reliability_for_twse_success(self):
        output = Path(".tmp-cli-test/valuation-template-twse-reliability.csv")

        write_valuation_template(
            ["2330"],
            output,
            fetch_price=lambda stock_id: {
                "stock_id": stock_id,
                "price": 1000.0,
                "price_date": "115/05/06",
                "price_source": "TWSE_STOCK_DAY",
                "warning": "",
            },
        )

        rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0]["price_status"], "ok")
        self.assertEqual(rows[0]["price_status_message"], "Latest close price loaded from TWSE.")
        self.assertEqual(rows[0]["price_retry_hint"], "")

    def test_write_valuation_template_records_price_reliability_for_tpex_fallback(self):
        output = Path(".tmp-cli-test/valuation-template-tpex-reliability.csv")

        write_valuation_template(
            ["6187"],
            output,
            fetch_price=lambda stock_id: {
                "stock_id": stock_id,
                "price": 125.5,
                "price_date": "115/05/06",
                "price_source": "TPEX_DAILY_CLOSE",
                "warning": "",
            },
        )

        rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0]["price_status"], "warning")
        self.assertEqual(
            rows[0]["price_status_message"],
            "TWSE price was unavailable; loaded latest close price from TPEx fallback.",
        )
        self.assertEqual(
            rows[0]["price_retry_hint"],
            "Run again after the next market data update or provide a valuation CSV manually.",
        )

    def test_write_valuation_template_records_price_reliability_when_no_price_available(self):
        output = Path(".tmp-cli-test/valuation-template-no-price-reliability.csv")

        write_valuation_template(
            ["9999"],
            output,
            fetch_price=lambda stock_id: {
                "stock_id": stock_id,
                "price": None,
                "price_date": "",
                "price_source": "TWSE_STOCK_DAY,TPEX_DAILY_CLOSE",
                "warning": "no TWSE close price; no TPEx close price",
            },
        )

        rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0]["price_status"], "warning")
        self.assertEqual(
            rows[0]["price_status_message"],
            "No market price was available from configured sources.",
        )
        self.assertEqual(
            rows[0]["price_retry_hint"],
            "Run again after the next market data update or provide a valuation CSV manually.",
        )

    def test_write_valuation_template_records_price_reliability_when_warning_has_price(self):
        output = Path(".tmp-cli-test/valuation-template-warning-with-price.csv")

        write_valuation_template(
            ["2330"],
            output,
            fetch_price=lambda stock_id: {
                "stock_id": stock_id,
                "price": 1000.0,
                "price_date": "115/05/06",
                "price_source": "TWSE_STOCK_DAY",
                "warning": "TWSE payload missing volume",
            },
        )

        rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0]["price_status"], "warning")
        self.assertEqual(
            rows[0]["price_status_message"],
            "Market price was loaded with warning: TWSE payload missing volume",
        )
        self.assertEqual(
            rows[0]["price_retry_hint"],
            "Run again after the next market data update or provide a valuation CSV manually.",
        )

    def test_load_analysis_enrichment_uses_eps_scenario_and_default_pe(self):
        analysis_dir = Path(".tmp-cli-test/analysis-enrichment")
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "2330_raw_data.json").write_text(
            json.dumps(
                {
                    "stock_id": "2330",
                    "years": ["2025", "2024"],
                    "valuation": {"eps_scenarios": {"base": 60.0}},
                    "metrics_by_year": {"2025": {"eps": 50.0}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        enrichment = load_analysis_enrichment("2330", analysis_dir)

        self.assertEqual(enrichment["normalized_eps"], 60.0)
        self.assertEqual(enrichment["target_pe_low"], 10.0)
        self.assertEqual(enrichment["target_pe_base"], 15.0)
        self.assertEqual(enrichment["target_pe_high"], 20.0)
        self.assertEqual(enrichment["warning"], "")

    def test_write_valuation_template_enriches_from_analysis_dir_and_warns_when_missing(self):
        output = Path(".tmp-cli-test/enriched-valuation-template.csv")
        analysis_dir = Path(".tmp-cli-test/enriched-analysis")
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "2330_raw_data.json").write_text(
            json.dumps(
                {
                    "years": ["2025"],
                    "valuation": {},
                    "metrics_by_year": {"2025": {"eps": 50.0}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        write_valuation_template(
            ["2330", "9999"],
            output,
            analysis_dir=analysis_dir,
            fetch_price=lambda stock_id: {
                "stock_id": stock_id,
                "price": 1000.0 if stock_id == "2330" else None,
                "price_date": "115/05/06" if stock_id == "2330" else "",
                "price_source": "TWSE_STOCK_DAY",
                "warning": "" if stock_id == "2330" else "no TWSE close price",
            },
        )

        rows = list(csv.DictReader(io.StringIO(output.read_text(encoding="utf-8"))))
        self.assertEqual(rows[0]["normalized_eps"], "50.0")
        self.assertEqual(rows[0]["target_pe_low"], "10.0")
        self.assertEqual(rows[0]["target_pe_base"], "15.0")
        self.assertEqual(rows[0]["target_pe_high"], "20.0")
        self.assertIn("analysis JSON not found", rows[1]["warning"])


if __name__ == "__main__":
    unittest.main()
