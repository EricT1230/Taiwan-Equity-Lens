import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from taiwan_stock_analysis.market_intelligence import (
    _http_post_form_json,
    build_market_intelligence_report,
    fetch_fund_flow_history,
    fetch_tpex_fund_flow_for_date,
    parse_tpex_fund_flow_payload,
    parse_twse_fund_flow_payload,
    fetch_twse_fund_flow_for_date,
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

    def test_load_fund_flow_rows_preserves_legacy_and_parses_optional_traded_shares(self):
        legacy_path = self.root / "legacy-fund-flow.csv"
        volume_path = self.root / "volume-fund-flow.csv"
        legacy_path.write_text(
            "date,stock_id,foreign_net,investment_trust_net,dealer_net,total_net,source\n"
            "2026-07-10,2330,1,2,3,6,fixture\n",
            encoding="utf-8",
        )
        volume_path.write_text(
            "date,stock_id,foreign_net,investment_trust_net,dealer_net,total_net,traded_shares,source\n"
            "2026-07-10,2330,1,2,3,6,37544470,fixture\n",
            encoding="utf-8",
        )

        legacy = load_fund_flow_rows(legacy_path)
        with_volume = load_fund_flow_rows(volume_path)

        self.assertIsNone(legacy[0]["traded_shares"])
        self.assertEqual(with_volume[0]["traded_shares"], 37544470.0)

    def test_parse_tpex_daily_trade_payload_uses_official_column_positions(self):
        payload = {
            "stat": "ok",
            "date": "20260716",
            "tables": [
                {
                    "data": [
                        [
                            "6223", "MPI", "0", "0", "1,000", "0", "0", "0",
                            "0", "0", "0", "0", "0", "-200", "0", "0", "0",
                            "0", "0", "0", "0", "0", "50", "850",
                        ]
                    ]
                },
                {"data": []},
            ],
        }

        rows = parse_tpex_fund_flow_payload(payload, date(2026, 7, 16))

        self.assertEqual(
            rows,
            [
                {
                    "date": "2026-07-16",
                    "stock_id": "6223",
                    "company_name": "MPI",
                    "foreign_net": 1000.0,
                    "investment_trust_net": -200.0,
                    "dealer_net": 50.0,
                    "total_net": 850.0,
                    "source": "TPEx dailyTrade",
                }
            ],
        )

    def test_parse_twse_t86_payload_uses_payload_date_and_official_fields(self):
        payload = {
            "stat": "OK",
            "date": "20260716",
            "fields": [
                "證券代號",
                "證券名稱",
                "外陸資買賣超股數(不含外資自營商)",
                "投信買賣超股數",
                "自營商買賣超股數",
                "三大法人買賣超股數",
            ],
            "data": [["2330", "TSMC", "1,000", "-200", "50", "850"]],
        }

        rows = parse_twse_fund_flow_payload(payload, date(2026, 7, 16))

        self.assertEqual(rows[0]["date"], "2026-07-16")
        self.assertEqual(rows[0]["stock_id"], "2330")
        self.assertEqual(rows[0]["foreign_net"], 1000.0)
        self.assertEqual(rows[0]["total_net"], 850.0)
        self.assertEqual(rows[0]["source"], "TWSE T86")

    def test_dated_fund_flow_parsers_reject_missing_invalid_or_mismatched_payload_dates(self):
        def twse_payload(payload_date):
            return {
                "stat": "OK",
                "date": payload_date,
                "fields": [
                    "證券代號",
                    "證券名稱",
                    "外陸資買賣超股數(不含外資自營商)",
                    "投信買賣超股數",
                    "自營商買賣超股數",
                    "三大法人買賣超股數",
                ],
                "data": [["2330", "TSMC", "1", "2", "3", "6"]],
            }

        def tpex_payload(payload_date):
            return {
                "stat": "ok",
                "date": payload_date,
                "tables": [
                    {
                        "data": [
                            [
                                "6223", "MPI", "0", "0", "1", "0", "0", "0",
                                "0", "0", "0", "0", "0", "2", "0", "0", "0",
                                "0", "0", "0", "0", "0", "3", "6",
                            ]
                        ]
                    }
                ],
            }

        for parser, payload_factory in (
            (parse_twse_fund_flow_payload, twse_payload),
            (parse_tpex_fund_flow_payload, tpex_payload),
        ):
            for payload_date in (
                None,
                "not-a-date",
                "20260715",
                "2026-07-16garbage",
                "2026-07-16T00:00:00",
                "20260716garbage",
                " 20260716 ",
            ):
                with self.subTest(parser=parser.__name__, payload_date=payload_date):
                    with self.assertRaisesRegex(ValueError, "date"):
                        parser(payload_factory(payload_date), date(2026, 7, 16))

    def test_dated_fund_flow_parsers_require_explicit_list_containers(self):
        twse_base = {
            "stat": "OK",
            "date": "20260716",
            "fields": [
                "證券代號",
                "證券名稱",
                "外陸資買賣超股數(不含外資自營商)",
                "投信買賣超股數",
                "自營商買賣超股數",
                "三大法人買賣超股數",
            ],
        }
        for label, data_value in (("missing", ...), ("null", None), ("wrong_type", {})):
            payload = dict(twse_base)
            if data_value is not ...:
                payload["data"] = data_value
            with self.subTest(parser="TWSE", container=label):
                with self.assertRaisesRegex(ValueError, "data"):
                    parse_twse_fund_flow_payload(payload, date(2026, 7, 16))

        twse_row = ["2330", "TSMC", "1", "2", "3", "6"]
        for label, fields_value in (("missing", ...), ("null", None), ("wrong_type", {})):
            payload = {"stat": "OK", "date": "20260716", "data": [twse_row]}
            if fields_value is not ...:
                payload["fields"] = fields_value
            with self.subTest(parser="TWSE", container=f"fields_{label}"):
                with self.assertRaisesRegex(ValueError, "fields"):
                    parse_twse_fund_flow_payload(payload, date(2026, 7, 16))

        tpex_base = {"stat": "ok", "date": "20260716"}
        invalid_tpex_tables = (
            ("missing_tables", ...),
            ("null_tables", None),
            ("wrong_tables_type", {}),
            ("missing_table0", []),
            ("null_table0", [None]),
            ("missing_data", [{}]),
            ("null_data", [{"data": None}]),
            ("wrong_data_type", [{"data": {}}]),
        )
        for label, tables_value in invalid_tpex_tables:
            payload = dict(tpex_base)
            if tables_value is not ...:
                payload["tables"] = tables_value
            with self.subTest(parser="TPEx", container=label):
                with self.assertRaisesRegex(ValueError, "tables|data"):
                    parse_tpex_fund_flow_payload(payload, date(2026, 7, 16))

        self.assertEqual(
            parse_twse_fund_flow_payload(
                {"stat": "OK", "date": "20260716", "data": []},
                date(2026, 7, 16),
            ),
            [],
        )
        self.assertEqual(
            parse_tpex_fund_flow_payload(
                dict(tpex_base, tables=[{"data": []}]),
                date(2026, 7, 16),
            ),
            [],
        )

    def test_dated_fund_flow_parsers_reject_missing_or_non_numeric_net_cells(self):
        twse_fields = [
            "證券代號",
            "證券名稱",
            "外陸資買賣超股數(不含外資自營商)",
            "投信買賣超股數",
            "自營商買賣超股數",
            "三大法人買賣超股數",
        ]
        tpex_base_row = [
            "6223", "MPI", "0", "0", "1", "0", "0", "0",
            "0", "0", "0", "0", "0", "2", "0", "0", "0",
            "0", "0", "0", "0", "0", "3", "6",
        ]
        parser_cases = (
            (
                parse_twse_fund_flow_payload,
                [2, 3, 4, 5],
                lambda row: {
                    "stat": "OK",
                    "date": "20260716",
                    "fields": twse_fields,
                    "data": [row],
                },
                ["2330", "TSMC", "1", "2", "3", "6"],
            ),
            (
                parse_tpex_fund_flow_payload,
                [4, 13, 22, 23],
                lambda row: {
                    "stat": "ok",
                    "date": "20260716",
                    "tables": [{"data": [row]}],
                },
                tpex_base_row,
            ),
        )

        for parser, indexes, payload_factory, base_row in parser_cases:
            for index in indexes:
                for invalid_value in (None, "", "not-a-number", "NaN", "inf"):
                    row = list(base_row)
                    row[index] = invalid_value
                    with self.subTest(
                        parser=parser.__name__,
                        index=index,
                        invalid_value=invalid_value,
                    ):
                        with self.assertRaises(ValueError):
                            parser(payload_factory(row), date(2026, 7, 16))
            with self.subTest(parser=parser.__name__, missing_column=True):
                with self.assertRaises(ValueError):
                    parser(payload_factory(list(base_row[:-1])), date(2026, 7, 16))
            with self.subTest(parser=parser.__name__, missing_row=True):
                with self.assertRaises(ValueError):
                    parser(payload_factory(None), date(2026, 7, 16))

    @patch("taiwan_stock_analysis.market_intelligence._http_json")
    def test_fetch_twse_fund_flow_for_date_uses_official_t86_query(self, http_json):
        http_json.return_value = {"stat": "NOT OK"}

        rows = fetch_twse_fund_flow_for_date(date(2026, 7, 16))

        self.assertEqual(rows, [])
        requested_url = http_json.call_args.args[0]
        self.assertTrue(requested_url.startswith("https://www.twse.com.tw/rwd/zh/fund/T86?"))
        self.assertIn("date=20260716", requested_url)
        self.assertIn("selectType=ALLBUT0999", requested_url)
        self.assertIn("response=json", requested_url)

    @patch("taiwan_stock_analysis.market_intelligence._http_post_form_json")
    def test_fetch_tpex_fund_flow_for_date_uses_official_daily_trade_form(self, post_json):
        post_json.return_value = {"stat": "not ok"}

        rows = fetch_tpex_fund_flow_for_date(date(2026, 7, 16))

        self.assertEqual(rows, [])
        post_json.assert_called_once_with(
            "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade",
            {
                "type": "Daily",
                "sect": "EW",
                "date": "2026/07/16",
                "response": "json",
            },
        )

    @patch("taiwan_stock_analysis.market_intelligence._open_url")
    def test_http_post_form_json_encodes_form_and_request_headers(self, open_url):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"stat":"ok"}'
        open_url.return_value = response

        payload = _http_post_form_json(
            "https://example.test/form",
            {"date": "2026/07/16", "response": "json"},
        )

        self.assertEqual(payload, {"stat": "ok"})
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/form")
        self.assertEqual(request.data, b"date=2026%2F07%2F16&response=json")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(request.get_header("User-agent"), "Taiwan-Equity-Lens/0.53")

    @patch("taiwan_stock_analysis.market_intelligence.fetch_tpex_fund_flow_for_date")
    @patch("taiwan_stock_analysis.market_intelligence.fetch_twse_fund_flow_for_date")
    def test_fund_flow_history_uses_independent_market_sessions_and_retains_errors(
        self,
        fetch_twse,
        fetch_tpex,
    ):
        def row(trade_date, stock_id, source, foreign_net=1.0):
            return {
                "date": trade_date.isoformat(),
                "stock_id": stock_id,
                "company_name": stock_id,
                "foreign_net": foreign_net,
                "investment_trust_net": 2.0,
                "dealer_net": 3.0,
                "total_net": foreign_net + 5.0,
                "source": source,
            }

        def twse_rows(trade_date):
            if trade_date == date(2026, 7, 16):
                return []
            if trade_date in {date(2026, 7, 17), date(2026, 7, 15), date(2026, 7, 14)}:
                result = row(trade_date, "2330", "TWSE T86")
                return [result, dict(result, foreign_net=9.0)] if trade_date.day == 17 else [result]
            return []

        def tpex_rows(trade_date):
            if trade_date == date(2026, 7, 16):
                return []
            if trade_date == date(2026, 7, 15):
                raise OSError("timeout")
            if trade_date in {date(2026, 7, 17), date(2026, 7, 14), date(2026, 7, 13)}:
                return [row(trade_date, "6223", "TPEx dailyTrade")]
            return []

        fetch_twse.side_effect = twse_rows
        fetch_tpex.side_effect = tpex_rows

        rows, errors = fetch_fund_flow_history(
            as_of="2026-07-17",
            session_count=3,
            max_calendar_days=10,
            markets=("TWSE", "TPEX"),
        )

        keys = [(item["date"], item["stock_id"], item["source"]) for item in rows]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {item["date"] for item in rows if item["source"] == "TWSE T86"},
            {"2026-07-14", "2026-07-15", "2026-07-17"},
        )
        self.assertEqual(
            {item["date"] for item in rows if item["source"] == "TPEx dailyTrade"},
            {"2026-07-13", "2026-07-14", "2026-07-17"},
        )
        self.assertEqual(
            next(item for item in rows if item["date"] == "2026-07-17" and item["stock_id"] == "2330")["foreign_net"],
            9.0,
        )
        self.assertEqual(errors, ["TPEX fund flow 2026-07-15: timeout"])
        self.assertNotIn(date(2026, 7, 13), [call.args[0] for call in fetch_twse.call_args_list])
        requested_dates = [call.args[0] for call in [*fetch_twse.call_args_list, *fetch_tpex.call_args_list]]
        self.assertTrue(all(item.weekday() < 5 for item in requested_dates))

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
