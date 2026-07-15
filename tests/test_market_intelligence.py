import json
import unittest
from pathlib import Path
from unittest.mock import patch

from taiwan_stock_analysis.market_intelligence import (
    build_market_intelligence_report,
    fetch_twse_fund_flow,
    fetch_twse_news,
    fetch_tpex_fund_flow,
    load_fund_flow_rows,
    load_news_rows,
    render_market_intelligence_html,
    render_market_intelligence_markdown,
    write_market_intelligence_report,
)


class MarketIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp-market-intelligence-test")
        self.root.mkdir(parents=True, exist_ok=True)

    def test_load_csv_inputs_normalizes_news_and_fund_flow(self):
        news_path = self.root / "news.csv"
        flow_path = self.root / "fund-flow.csv"
        news_path.write_text(
            "published_at,title,summary,url,source\n"
            "2026-07-11T08:00:00+08:00,台積電 AI 伺服器需求增溫,先進製程受關注,https://example.test/a,fixture\n",
            encoding="utf-8",
        )
        flow_path.write_text(
            "date,stock_id,company_name,foreign_net,investment_trust_net,dealer_net,total_net,source\n"
            "2026-07-10,2330,台積電,1,000,20,-10,1010,fixture\n".replace("1,000", '"1,000"'),
            encoding="utf-8",
        )

        news = load_news_rows(news_path)
        flows = load_fund_flow_rows(flow_path)

        self.assertEqual(news[0]["title"], "台積電 AI 伺服器需求增溫")
        self.assertEqual(news[0]["source"], "fixture")
        self.assertEqual(flows[0]["stock_id"], "2330")
        self.assertEqual(flows[0]["foreign_net"], 1000.0)
        self.assertEqual(flows[0]["total_net"], 1010.0)

    def test_build_report_combines_trend_news_keywords_and_fund_flow(self):
        research = self.root / "research.csv"
        trend_path = self.root / "industry_trend_report.json"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,TSMC,Semiconductor,high,watching,,台積電|晶圓代工|AI|伺服器\n"
            "2303,UMC,Semiconductor,medium,watching,,聯電|成熟製程\n"
            "1504,TECO,Electric Machinery,medium,watching,,東元|重電\n",
            encoding="utf-8",
        )
        trend_path.write_text(
            json.dumps(
                {
                    "as_of_date": "2026-07-10",
                    "categories": [
                        {
                            "category": "Semiconductor",
                            "direction": "up",
                            "rotation_phase": "leading",
                            "average_return_5d": 3.2,
                            "average_return_20d": 8.4,
                            "coverage_count": 2,
                            "stock_count": 2,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        news = [
            {
                "published_at": "2026-07-11T10:00:00+08:00",
                "title": "台積電 AI 伺服器帶動先進製程需求",
                "summary": "晶圓代工供應鏈關注資本支出",
                "url": "https://example.test/one",
                "source": "fixture",
            },
            {
                "published_at": "2026-07-11T09:00:00+08:00",
                "title": "AI 伺服器需求升溫 聯電成熟製程同步觀察",
                "summary": "",
                "url": "https://example.test/two",
                "source": "fixture",
            },
            {
                "published_at": "2026-07-11T08:00:00+08:00",
                "title": "國際原油價格整理",
                "summary": "",
                "url": "https://example.test/unmapped",
                "source": "fixture",
            },
        ]
        flows = [
            {
                "date": "2026-07-10",
                "stock_id": "2330",
                "company_name": "台積電",
                "foreign_net": 1000,
                "investment_trust_net": 200,
                "dealer_net": -50,
                "total_net": 1150,
                "source": "fixture",
            },
            {
                "date": "2026-07-10",
                "stock_id": "2303",
                "company_name": "聯電",
                "foreign_net": -100,
                "investment_trust_net": 50,
                "dealer_net": 25,
                "total_net": -25,
                "source": "fixture",
            },
        ]

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-12T12:00:00+08:00",
        )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["quality_gate"]["status"], "ready")
        self.assertEqual(report["coverage"]["news_total"], 3)
        self.assertEqual(report["coverage"]["news_mapped"], 2)
        self.assertEqual(report["coverage"]["stocks_with_fund_flow"], 2)
        industries = {row["category"]: row for row in report["industries"]}
        semiconductor = industries["Semiconductor"]
        self.assertEqual(semiconductor["market_trend"]["direction"], "up")
        self.assertEqual(semiconductor["news_count"], 2)
        self.assertIn("AI", semiconductor["top_keywords"])
        self.assertIn("伺服器", semiconductor["top_keywords"])
        self.assertEqual(semiconductor["fund_flow"]["foreign_net"], 900)
        self.assertEqual(semiconductor["fund_flow"]["total_net"], 1125)
        self.assertEqual(semiconductor["fund_flow"]["direction"], "net_inflow")

    def test_quality_gate_blocks_missing_or_stale_sources(self):
        research = self.root / "stale-research.csv"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,TSMC,Semiconductor,high,watching,,台積電\n",
            encoding="utf-8",
        )

        report = build_market_intelligence_report(
            research,
            news_rows=[
                {
                    "published_at": "2026-06-01",
                    "title": "台積電新聞",
                    "summary": "",
                    "url": "",
                    "source": "fixture",
                }
            ],
            fund_flow_rows=[],
            as_of="2026-07-12T12:00:00+08:00",
            source_errors=["news feed timeout"],
        )

        self.assertEqual(report["quality_gate"]["status"], "needs_data")
        self.assertIn("stale news data", report["quality_gate"]["blockers"])
        self.assertIn("missing fund flow data", report["quality_gate"]["blockers"])
        self.assertIn("missing industry trend data", report["quality_gate"]["blockers"])
        self.assertIn("source error: news feed timeout", report["quality_gate"]["blockers"])
        self.assertEqual(report["source_errors"], ["news feed timeout"])

    @patch("taiwan_stock_analysis.market_intelligence._http_json")
    def test_official_twse_adapters_normalize_news_and_t86(self, http_json):
        http_json.side_effect = [
            [{"Title": "證交所新聞", "Url": "https://example.test/news", "Date": "1150709"}],
            {
                "stat": "OK",
                "date": "20260709",
                "fields": [
                    "證券代號",
                    "證券名稱",
                    "外陸資買賣超股數(不含外資自營商)",
                    "投信買賣超股數",
                    "自營商買賣超股數",
                    "三大法人買賣超股數",
                ],
                "data": [["2330", "台積電", "1,000", "200", "-50", "1,150"]],
            },
        ]

        news = fetch_twse_news()
        flows = fetch_twse_fund_flow(as_of="2026-07-09", lookback_days=1)

        self.assertEqual(news[0]["published_at"][:10], "2026-07-09")
        self.assertEqual(news[0]["source"], "TWSE News OpenAPI")
        self.assertEqual(flows[0]["date"], "2026-07-09")
        self.assertEqual(flows[0]["foreign_net"], 1000.0)
        self.assertEqual(flows[0]["source"], "TWSE T86")

    @patch("taiwan_stock_analysis.market_intelligence._http_json")
    def test_tpex_fund_flow_adapter_normalizes_official_fields(self, http_json):
        http_json.return_value = [
            {
                "Date": "1150709",
                "SecuritiesCompanyCode": "6223",
                "CompanyName": "旺矽",
                "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference": "1000",
                "SecuritiesInvestmentTrustCompanies-Difference": "-200",
                "Dealers-Difference": "50",
                "TotalDifference": "850",
            }
        ]

        rows = fetch_tpex_fund_flow()

        self.assertEqual(rows[0]["date"], "2026-07-09")
        self.assertEqual(rows[0]["stock_id"], "6223")
        self.assertEqual(rows[0]["foreign_net"], 1000.0)
        self.assertEqual(rows[0]["total_net"], 850.0)
        self.assertEqual(rows[0]["source"], "TPEx 3insti daily trading")

    def test_write_report_outputs_traceable_json_markdown_and_html(self):
        research = self.root / "write-research.csv"
        trend = self.root / "write-trend.json"
        output_dir = self.root / "market-intelligence"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,TSMC,Semiconductor,high,watching,,台積電\n",
            encoding="utf-8",
        )
        trend.write_text(
            json.dumps({"as_of_date": "2026-07-10", "categories": []}),
            encoding="utf-8",
        )
        news = [{"published_at": "2026-07-11", "title": "台積電新聞", "source": "fixture"}]
        flows = [
            {
                "date": "2026-07-10",
                "stock_id": "2330",
                "foreign_net": 1,
                "investment_trust_net": 2,
                "dealer_net": 3,
                "total_net": 6,
                "source": "fixture",
            }
        ]

        json_path = write_market_intelligence_report(
            research,
            output_dir,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend,
            as_of="2026-07-12T12:00:00+08:00",
            dependencies={"news_csv_1": "news.csv", "fund_flow_csv_1": "flow.csv"},
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertTrue((output_dir / "market_intelligence_report.md").exists())
        self.assertTrue((output_dir / "market_intelligence_report.html").exists())
        self.assertEqual(payload["artifact_registry"]["dependencies"]["research_csv"], str(research))
        self.assertEqual(payload["artifact_registry"]["dependencies"]["news_csv_1"], "news.csv")
        self.assertIn("Market Intelligence Industry Map", render_market_intelligence_markdown(payload))
        self.assertIn('data-market-intelligence-report="true"', render_market_intelligence_html(payload))
        self.assertIn("not investment advice", render_market_intelligence_html(payload))


if __name__ == "__main__":
    unittest.main()
