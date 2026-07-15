import csv
import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from taiwan_stock_analysis.market_data_importer import (
    build_official_profiles,
    parse_tpex_price_payload,
    parse_twse_price_payload,
    write_market_data_bundle,
)


class MarketDataImporterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp-market-data-importer-test")
        self.root.mkdir(parents=True, exist_ok=True)

    def test_build_official_profiles_joins_twse_and_tpex_industry_names(self):
        profiles = build_official_profiles(
            [
                {
                    "出表日期": "1150710",
                    "公司代號": "2330",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                    "公司簡稱": "台積電",
                    "產業別": "24",
                }
            ],
            [{"公司代號": "2330", "產業別": "半導體業"}],
            [
                {
                    "Date": "1150711",
                    "SecuritiesCompanyCode": "6223",
                    "CompanyName": "旺矽科技股份有限公司",
                    "CompanyAbbreviation": "旺矽",
                    "SecuritiesIndustryCode": "24",
                }
            ],
            [{"SecuritiesCompanyCode": "6223", "產業別": "半導體業"}],
        )

        by_stock = {row["stock_id"]: row for row in profiles}
        self.assertEqual(by_stock["2330"]["market"], "TWSE")
        self.assertEqual(by_stock["2330"]["industry_name"], "半導體業")
        self.assertEqual(by_stock["2330"]["snapshot_date"], "2026-07-10")
        self.assertEqual(by_stock["6223"]["market"], "TPEX")
        self.assertEqual(by_stock["6223"]["industry_code"], "24")

    def test_parse_twse_price_payload_normalizes_roc_date_and_shares(self):
        payload = {
            "stat": "OK",
            "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價"],
            "data": [["115/07/09", "37,544,470", "1", "1", "1", "1", "2,505.00"]],
        }

        rows = parse_twse_price_payload(payload, "2330")

        self.assertEqual(rows[0]["date"], "2026-07-09")
        self.assertEqual(rows[0]["close"], 2505.0)
        self.assertEqual(rows[0]["volume"], 37544470.0)
        self.assertEqual(rows[0]["source"], "TWSE STOCK_DAY")

    def test_parse_tpex_price_payload_converts_lots_to_share_equivalent(self):
        payload = {
            "tables": [
                {
                    "fields": ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤"],
                    "data": [["115/07/09", "711", "1", "1", "1", "1", "7,080.00"]],
                }
            ]
        }

        rows = parse_tpex_price_payload(payload, "6223")

        self.assertEqual(rows[0]["date"], "2026-07-09")
        self.assertEqual(rows[0]["close"], 7080.0)
        self.assertEqual(rows[0]["volume"], 711000.0)
        self.assertEqual(rows[0]["source"], "TPEx tradingStock")

    def test_write_market_data_bundle_writes_ready_cross_market_outputs(self):
        research = self.root / "research.csv"
        output_dir = self.root / "bundle"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,TSMC,,high,watching,,台積電|AI\n"
            "6223,MPI,Uncategorized,medium,watching,,旺矽|半導體\n",
            encoding="utf-8",
        )
        profiles = [
            {
                "stock_id": "2330",
                "company_name": "台灣積體電路製造股份有限公司",
                "company_abbreviation": "台積電",
                "market": "TWSE",
                "industry_code": "24",
                "industry_name": "半導體業",
                "snapshot_date": "2026-07-10",
                "source": "TWSE OpenAPI",
            },
            {
                "stock_id": "6223",
                "company_name": "旺矽科技股份有限公司",
                "company_abbreviation": "旺矽",
                "market": "TPEX",
                "industry_code": "24",
                "industry_name": "半導體業",
                "snapshot_date": "2026-07-11",
                "source": "TPEx OpenAPI",
            },
        ]

        def fake_prices(stock_id, market, **kwargs):
            start = date(2026, 6, 9)
            return [
                {
                    "stock_id": stock_id,
                    "date": (start + timedelta(days=index)).isoformat(),
                    "close": 100.0 + index,
                    "volume": 1000.0 + index,
                    "source": market,
                }
                for index in range(21)
            ]

        twse_flow = [
            {
                "date": "2026-07-09",
                "stock_id": "2330",
                "company_name": "台積電",
                "foreign_net": 1,
                "investment_trust_net": 2,
                "dealer_net": 3,
                "total_net": 6,
                "source": "TWSE T86",
            }
        ]
        tpex_flow = [
            {
                "date": "2026-07-09",
                "stock_id": "6223",
                "company_name": "旺矽",
                "foreign_net": 4,
                "investment_trust_net": 5,
                "dealer_net": 6,
                "total_net": 15,
                "source": "TPEx 3insti daily trading",
            }
        ]

        with (
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_official_profiles",
                return_value=(profiles, []),
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_price_history",
                side_effect=fake_prices,
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_twse_fund_flow",
                return_value=twse_flow,
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_tpex_fund_flow",
                return_value=tpex_flow,
            ),
        ):
            outputs = write_market_data_bundle(
                research,
                output_dir,
                as_of="2026-07-12",
                history_months=2,
            )

        report = json.loads(outputs["report"].read_text(encoding="utf-8"))
        self.assertEqual(report["quality_gate"]["status"], "ready")
        self.assertEqual(report["coverage"]["twse_count"], 1)
        self.assertEqual(report["coverage"]["tpex_count"], 1)
        self.assertEqual(report["coverage"]["price_ready_count"], 2)
        self.assertEqual(report["coverage"]["fund_flow_count"], 2)
        self.assertTrue(outputs["price_history"].exists())
        self.assertTrue(outputs["fund_flow"].exists())
        self.assertTrue(outputs["official_universe"].exists())
        with outputs["research_csv"].open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["category"] for row in rows], ["半導體業", "半導體業"])
        self.assertEqual([row["official_market"] for row in rows], ["TWSE", "TPEX"])


if __name__ == "__main__":
    unittest.main()
