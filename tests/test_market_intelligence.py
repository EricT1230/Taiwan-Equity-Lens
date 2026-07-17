import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from taiwan_stock_analysis.market_intelligence import (
    _event_link,
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
from taiwan_stock_analysis.sentiment_history import load_sentiment_history


class MarketIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _sentiment_fixture(self, *, include_fund_flow: bool = True):
        research = self.root / "sentiment-research.csv"
        trend_path = self.root / "sentiment-industry-trend.json"
        session_dates = [f"2026-07-{day:02d}" for day in range(1, 21)]
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,TSMC,Semiconductor,high,watching,,AI|chip\n"
            "2303,UMC,Semiconductor,medium,watching,,AI|foundry\n",
            encoding="utf-8",
        )
        trend_path.write_text(
            json.dumps(
                {
                    "as_of_date": "2026-07-20",
                    "session_dates": session_dates,
                    "categories": [
                        {
                            "category": "Semiconductor",
                            "direction": "up",
                            "rotation_phase": "leading",
                            "average_return_1d": 0.8,
                            "average_return_5d": 4.0,
                            "average_return_20d": 7.5,
                            "positive_breadth_5d": 0.75,
                            "positive_breadth_20d": 0.60,
                            "coverage_ratio_5d": 1.0,
                            "coverage_ratio_20d": 1.0,
                            "high_count_20d": 1,
                            "low_count_20d": 0,
                            "average_volume_ratio_5d": 1.5,
                            "covered_stock_ids": ["2303", "2330"],
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
                "published_at": f"2026-07-20T{10 - index:02d}:00:00+08:00",
                "title": f"AI 強勁成長 {index}",
                "summary": "chip 訂單增加",
                "url": f"https://example.test/sentiment/{index}",
                "source": f"fixture-{index}",
            }
            for index in range(5)
        ]
        flows = (
            [
                {
                    "date": trade_date,
                    "stock_id": stock_id,
                    "company_name": stock_id,
                    "foreign_net": 10.0,
                    "investment_trust_net": 2.0,
                    "dealer_net": -1.0,
                    "total_net": 11.0,
                    "traded_shares": 1000.0,
                    "source": "fixture",
                }
                for trade_date in session_dates
                for stock_id in ("2303", "2330")
            ]
            if include_fund_flow
            else []
        )
        return research, trend_path, news, flows

    @staticmethod
    def _prior_sentiment_rows():
        return [
            {
                "as_of_date": f"2026-07-{day:02d}",
                "category": "Semiconductor",
                "methodology_version": "industry-sentiment-v1",
                "status": "ready",
                "score_5d": score,
                "baseline_20d": score - 2.0,
                "change": 2.0,
                "breadth_5d": 0.70,
                "breadth_20d": 0.60,
                "rank": 1,
                "ranked_count": 1,
            }
            for day, score in ((18, 12.0), (19, 14.0))
        ]

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

        self.assertEqual(report["schema_version"], 2)
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

    def test_build_report_adds_complete_sentiment_with_strictly_prior_history(self):
        research, trend_path, news, flows = self._sentiment_fixture()

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
            sentiment_history_rows=self._prior_sentiment_rows(),
        )

        semiconductor = report["industries"][0]
        sentiment = semiconductor["sentiment"]
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(
            report["sentiment_methodology_version"],
            "industry-sentiment-v1",
        )
        self.assertEqual(sentiment["status"], "ready")
        self.assertEqual(sentiment["components"]["news"]["configured_weight"], 0.4)
        self.assertEqual(sentiment["components"]["price"]["configured_weight"], 0.3)
        self.assertEqual(
            sentiment["components"]["fund_flow"]["configured_weight"],
            0.3,
        )
        self.assertEqual(sentiment["rank"], 1)
        self.assertEqual(sentiment["ranked_count"], 1)
        self.assertEqual(sentiment["forecast"]["status"], "insufficient_history")
        self.assertIn(
            sentiment["cycle_phase"],
            {
                "overheating",
                "capitulation",
                "recovery",
                "ignition",
                "expansion",
                "cooling",
                "consolidation",
            },
        )
        self.assertEqual(
            semiconductor["market_trend"]["covered_stock_ids"],
            ["2303", "2330"],
        )
        self.assertEqual(len(report["fund_flows"]), 40)
        self.assertEqual(semiconductor["fund_flow"]["as_of_date"], "2026-07-20")
        self.assertEqual(semiconductor["fund_flow"]["stock_count"], 2)

    def test_build_report_renormalizes_two_components_without_fabricating_flow(self):
        research, trend_path, news, _ = self._sentiment_fixture(
            include_fund_flow=False
        )

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=[],
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )

        sentiment = report["industries"][0]["sentiment"]
        self.assertEqual(sentiment["status"], "partial")
        self.assertAlmostEqual(sentiment["effective_weights"]["news"], 4 / 7)
        self.assertAlmostEqual(sentiment["effective_weights"]["price"], 3 / 7)
        self.assertNotIn("fund_flow", sentiment["effective_weights"])
        self.assertIsNone(sentiment["components"]["fund_flow"]["score_5d"])
        self.assertTrue(
            any(
                "fund_flow removed from composite" in warning
                for warning in sentiment["warnings"]
            )
        )

    def test_category_price_freshness_requires_eighty_percent_in_both_windows(self):
        research = self.root / "coverage-research.csv"
        trend_path = self.root / "coverage-trend.json"
        session_dates = [f"2026-07-{day:02d}" for day in range(1, 21)]
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "1111,Low 5D Co,A Low 5D Coverage,high,watching,,LOW5\n"
            "2222,Low 20D Co,B Low 20D Coverage,high,watching,,LOW20\n"
            "3333,Missing Co,C Missing Coverage,high,watching,,MISSING\n"
            "4444,Invalid Co,D Invalid Coverage,high,watching,,INVALID\n"
            "5555,High Co,E Sufficient Coverage,high,watching,,HIGH\n",
            encoding="utf-8",
        )

        def category_trend(category, stock_id, coverage_5d, coverage_20d):
            return {
                "category": category,
                "direction": "up",
                "rotation_phase": "leading",
                "average_return_1d": 0.8,
                "average_return_5d": 4.0,
                "average_return_20d": 7.5,
                "positive_breadth_5d": 0.75,
                "positive_breadth_20d": 0.60,
                "coverage_ratio_5d": coverage_5d,
                "coverage_ratio_20d": coverage_20d,
                "high_count_20d": 1,
                "low_count_20d": 0,
                "average_volume_ratio_5d": 1.5,
                "covered_stock_ids": [stock_id],
                "coverage_count": 1,
                "stock_count": 1,
            }

        trend_path.write_text(
            json.dumps(
                {
                    "as_of_date": "2026-07-20",
                    "session_dates": session_dates,
                    "categories": [
                        category_trend(
                            "A Low 5D Coverage",
                            "1111",
                            0.20,
                            1.0,
                        ),
                        category_trend(
                            "B Low 20D Coverage",
                            "2222",
                            1.0,
                            0.20,
                        ),
                        category_trend(
                            "C Missing Coverage",
                            "3333",
                            None,
                            1.0,
                        ),
                        category_trend(
                            "D Invalid Coverage",
                            "4444",
                            1.0,
                            "invalid",
                        ),
                        category_trend(
                            "E Sufficient Coverage",
                            "5555",
                            1.0,
                            1.0,
                        ),
                    ],
                }
            ),
            encoding="utf-8",
        )
        news = [
            {
                "published_at": f"2026-07-20T{10 - index:02d}:00:00+08:00",
                "title": f"{alias} 強勁成長 {index}",
                "summary": "訂單增加",
                "url": f"https://example.test/{alias.casefold()}/{index}",
                "source": f"fixture-{index}",
            }
            for alias in ("LOW5", "LOW20", "MISSING", "INVALID", "HIGH")
            for index in range(5)
        ]

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=[],
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )

        industries = {row["category"]: row for row in report["industries"]}
        for category in (
            "A Low 5D Coverage",
            "B Low 20D Coverage",
            "C Missing Coverage",
            "D Invalid Coverage",
        ):
            with self.subTest(category=category):
                insufficient = industries[category]["sentiment"]
                self.assertIsNotNone(
                    insufficient["components"]["price"]["score_5d"]
                )
                self.assertEqual(
                    insufficient["components"]["price"]["freshness"]["status"],
                    "insufficient_category_price_coverage",
                )
                self.assertTrue(
                    any(
                        "insufficient category price coverage" in warning
                        for warning in insufficient["warnings"]
                    )
                )
                self.assertEqual(insufficient["status"], "insufficient_data")
                self.assertIsNone(insufficient["score_5d"])
                self.assertIsNone(insufficient["rank"])
        sufficient = industries["E Sufficient Coverage"]["sentiment"]
        self.assertEqual(sufficient["status"], "partial")
        self.assertIsNotNone(sufficient["score_5d"])
        self.assertEqual(sufficient["rank"], 1)
        self.assertEqual(sufficient["ranked_count"], 1)
        self.assertEqual(
            sufficient["components"]["price"]["freshness"]["status"],
            "fresh",
        )

    def test_sentiment_ranking_breaks_ties_by_industry_and_leaves_scoreless_last(self):
        research = self.root / "ranking-research.csv"
        trend_path = self.root / "ranking-trend.json"
        session_dates = [f"2026-07-{day:02d}" for day in range(1, 21)]
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "1111,Alpha Co,Alpha Industry,high,watching,,ALPHA\n"
            "2222,Beta Co,Beta Industry,high,watching,,BETA\n"
            "3333,Scoreless Co,Scoreless Industry,high,watching,,SCORELESS\n",
            encoding="utf-8",
        )

        def tied_trend(category, stock_id):
            return {
                "category": category,
                "direction": "up",
                "rotation_phase": "leading",
                "average_return_1d": 0.8,
                "average_return_5d": 4.0,
                "average_return_20d": 7.5,
                "positive_breadth_5d": 0.75,
                "positive_breadth_20d": 0.60,
                "coverage_ratio_5d": 1.0,
                "coverage_ratio_20d": 1.0,
                "high_count_20d": 1,
                "low_count_20d": 0,
                "average_volume_ratio_5d": 1.5,
                "covered_stock_ids": [stock_id],
                "coverage_count": 1,
                "stock_count": 1,
            }

        trend_path.write_text(
            json.dumps(
                {
                    "as_of_date": "2026-07-20",
                    "session_dates": session_dates,
                    "categories": [
                        tied_trend("Beta Industry", "2222"),
                        tied_trend("Alpha Industry", "1111"),
                    ],
                }
            ),
            encoding="utf-8",
        )
        news = [
            {
                "published_at": f"2026-07-20T{10 - index:02d}:00:00+08:00",
                "title": f"{alias} 強勁成長 {index}",
                "summary": "訂單增加",
                "url": f"https://example.test/{alias.casefold()}/{index}",
                "source": f"fixture-{index}",
            }
            for alias in ("ALPHA", "BETA")
            for index in range(5)
        ]

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=[],
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )

        self.assertEqual(
            [row["category"] for row in report["industries"]],
            ["Alpha Industry", "Beta Industry", "Scoreless Industry"],
        )
        alpha, beta, scoreless = report["industries"]
        self.assertEqual(
            alpha["sentiment"]["score_5d"],
            beta["sentiment"]["score_5d"],
        )
        self.assertEqual(alpha["sentiment"]["rank"], 1)
        self.assertEqual(beta["sentiment"]["rank"], 2)
        self.assertEqual(alpha["sentiment"]["ranked_count"], 2)
        self.assertEqual(beta["sentiment"]["ranked_count"], 2)
        self.assertIsNone(scoreless["sentiment"]["score_5d"])
        self.assertIsNone(scoreless["sentiment"]["rank"])
        self.assertEqual(scoreless["sentiment"]["ranked_count"], 2)

    def test_renderers_show_sentiment_evidence_and_experimental_boundaries(self):
        research, trend_path, news, flows = self._sentiment_fixture()
        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
            sentiment_history_rows=self._prior_sentiment_rows(),
        )
        sentiment = report["industries"][0]["sentiment"]

        markdown = render_market_intelligence_markdown(report)
        html = render_market_intelligence_html(report)

        for heading in (
            "Score (5D)",
            "Baseline (20D)",
            "Change",
            "Confidence",
            "Phase",
            "Forecast (experimental)",
            "Peak risk (experimental)",
            "Trough risk (experimental)",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("## Sentiment Evidence", markdown)
        self.assertIn("Reasons:", markdown)
        self.assertIn("Warnings:", markdown)
        self.assertIn("insufficient history", markdown)
        self.assertIn(
            "projection requires at least 20 valid snapshot days",
            markdown,
        )
        self.assertIn(
            "turning-risk diagnostics require at least 60 valid snapshot days",
            html,
        )
        for attribute in (
            "data-industry-sentiment",
            "data-industry-sentiment-score",
            "data-industry-sentiment-phase",
            "data-industry-sentiment-confidence",
            "data-industry-sentiment-forecast",
            "data-industry-turning-risk",
        ):
            self.assertIn(attribute, html)
        self.assertIn(
            f'data-industry-sentiment="{sentiment["status"]}"',
            html,
        )
        self.assertIn(
            f"Sentiment label:</strong> {sentiment['label']}",
            html,
        )
        self.assertIn("News contribution", html)
        self.assertIn("Price contribution", html)
        self.assertIn("Fund flow contribution", html)
        self.assertIn("experimental research aid", html)
        self.assertIn("insufficient history", html)

    def test_markdown_escapes_dynamic_text_without_changing_table_structure(self):
        research, trend_path, news, flows = self._sentiment_fixture()
        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )
        industry = report["industries"][0]
        sentiment = industry["sentiment"]
        industry["category"] = "AI | Semiconductor"
        industry["top_keywords"] = ["chip | foundry", r"safe\path"]
        industry["market_trend"]["direction"] = (
            "up | down\n| forged | table | row |"
        )
        sentiment["reasons"] = [
            "base reason\n- injected reason",
            "reason\r\n### injected reason heading",
        ]
        sentiment["warnings"] = [
            "base warning\r\n| injected | warning | row |",
            "warning\n## injected warning heading",
        ]
        report["quality_gate"]["blockers"] = [
            "blocked\n# injected blocker heading"
        ]
        report["non_advice_notice"] = "notice\n---\ninjected rule"

        markdown = render_market_intelligence_markdown(report)
        lines = markdown.splitlines()
        table_lines = [line for line in lines if line.startswith("|")]

        def unescaped_pipe_count(line):
            count = 0
            backslashes = 0
            for character in line:
                if character == "|" and backslashes % 2 == 0:
                    count += 1
                backslashes = backslashes + 1 if character == "\\" else 0
            return count

        self.assertEqual(len(table_lines), 3)
        self.assertTrue(
            all(unescaped_pipe_count(line) == 17 for line in table_lines)
        )
        self.assertIn(r"AI \| Semiconductor", markdown)
        self.assertIn(r"chip \| foundry", markdown)
        self.assertIn(r"safe\\path", markdown)
        self.assertFalse(
            any(
                line in {
                    "- injected reason",
                    "### injected reason heading",
                    "| injected | warning | row |",
                    "## injected warning heading",
                    "# injected blocker heading",
                    "---",
                }
                for line in lines
            )
        )

    def test_html_renders_available_forecast_intervals_and_risk_scores(self):
        research, trend_path, news, flows = self._sentiment_fixture()
        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )
        sentiment = report["industries"][0]["sentiment"]
        sentiment["forecast"] = {
            "status": "experimental",
            "forecast_1d": 12.5,
            "forecast_5d": 16.0,
            "interval_1d": [10.0, 15.0],
            "interval_5d": [8.0, 24.0],
            "warnings": ["experimental deterministic projection"],
        }
        sentiment["turning_risk"] = {
            "status": "experimental",
            "peak_risk": 72.0,
            "trough_risk": 18.0,
            "warnings": ["risk is not a calibrated probability"],
        }

        html = render_market_intelligence_html(report)

        self.assertIn("1D 12.5 [10.0, 15.0]", html)
        self.assertIn("5D 16.0 [8.0, 24.0]", html)
        self.assertIn("peak 72.0", html)
        self.assertIn("trough 18.0", html)
        self.assertIn("experimental deterministic projection", html)
        self.assertIn("not a calibrated probability", html)

    def test_renderers_preserve_legacy_industry_context_without_sentiment(self):
        legacy_report = {
            "generated_at": "2026-07-20T12:00:00+08:00",
            "quality_gate": {"status": "ready", "blockers": []},
            "coverage": {
                "news_mapped": 1,
                "news_total": 1,
                "stocks_with_fund_flow": 1,
                "stocks_total": 1,
                "industries_total": 1,
            },
            "industries": [
                {
                    "category": "Legacy Industry",
                    "market_trend": {
                        "direction": "up",
                        "rotation_phase": "leading",
                    },
                    "news_count": 1,
                    "top_keywords": ["legacy"],
                    "latest_news": [],
                    "fund_flow": {
                        "foreign_net": 1,
                        "investment_trust_net": 2,
                        "dealer_net": 3,
                        "total_net": 6,
                    },
                    "context": ["price direction: up"],
                }
            ],
            "non_advice_notice": "Research aid; not investment advice.",
        }

        markdown = render_market_intelligence_markdown(legacy_report)
        html = render_market_intelligence_html(legacy_report)

        self.assertIn("Legacy Industry", markdown)
        self.assertIn("Legacy Industry", html)
        self.assertIn("price direction: up", legacy_report["industries"][0]["context"])

    def test_event_links_allow_only_absolute_http_urls_with_valid_hosts(self):
        title = '<Unsafe & "event">'
        escaped_title = "&lt;Unsafe &amp; &quot;event&quot;&gt;"
        unsafe_urls = (
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "file:///C:/Windows/System32/calc.exe",
            "//example.test/scheme-relative",
            "/relative/path",
            "relative/path",
            "not a url",
            "https:///missing-host",
            "https://[invalid",
        )

        for url in unsafe_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    _event_link({"title": title, "url": url}),
                    escaped_title,
                )

        self.assertEqual(
            _event_link(
                {
                    "title": title,
                    "url": "https://example.test/news?left=1&right=2",
                }
            ),
            '<a href="https://example.test/news?left=1&amp;right=2">'
            + escaped_title
            + "</a>",
        )
        self.assertEqual(
            _event_link({"title": title, "url": "http://example.test/news"}),
            '<a href="http://example.test/news">' + escaped_title + "</a>",
        )

    def test_event_links_reject_malformed_http_hosts_and_authorities(self):
        escaped_title = "Unsafe event"
        overlong_label = "a" * 64
        overlong_dns_name = ".".join(["a" * 63] * 4)
        unsafe_urls = (
            "https://-bad-.example/news",
            "https://example..com/news",
            "https://exa_mple.com/news",
            "https://evil.com%00.example/news",
            "https://.example.com/news",
            "https://evil.\x00example/news",
            "https://evil.%0Aexample/news",
            "https://exa mple.com/news",
            "https://exa%20mple.com/news",
            "https://example.com/news\x00item",
            "https://example.com/news%09item",
            "https://example.com/news%7Fitem",
            f"https://{overlong_label}.example/news",
            f"https://{overlong_dns_name}/news",
            "https://999.999.999.999/news",
            "https://01.2.3.4/news",
            "https://1.2.3/news",
            "https://0x7f000001/news",
            "https://0x7f.0.0.1/news",
            "https://user@example.com/news",
            "https://user:secret@example.com/news",
            "https://@example.com/news",
            "https://example.com:/news",
            "https://example.com:bad/news",
            "https://example.com:65536/news",
            "https://[2001:db8:::1]/news",
            "https://2001:db8::1/news",
            "https://[v1.bad]/news",
        )

        for url in unsafe_urls:
            with self.subTest(url=repr(url)):
                self.assertEqual(
                    _event_link({"title": escaped_title, "url": url}),
                    escaped_title,
                )

    def test_event_links_accept_valid_dns_idn_and_ip_hosts_without_rewriting_href(self):
        title = "Valid event"
        valid_urls = (
            "https://sub-domain.example.test/news",
            "https://example.com./news",
            "https://例子.測試/新聞?left=1&right=2",
            "http://192.0.2.10:8080/news",
            "https://[2001:db8::1]:443/news",
        )

        for url in valid_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    _event_link({"title": title, "url": url}),
                    f'<a href="{url.replace("&", "&amp;")}">{title}</a>',
                )

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

    def test_write_report_upserts_same_day_history_before_registering_artifacts(self):
        research, trend_path, positive_news, flows = self._sentiment_fixture()
        output_dir = self.root / "sentiment-writer"
        history_path = output_dir / "industry_sentiment_history.csv"

        first_json_path = write_market_intelligence_report(
            research,
            output_dir,
            news_rows=positive_news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )
        first_payload = json.loads(first_json_path.read_text(encoding="utf-8"))
        first_score = first_payload["industries"][0]["sentiment"]["score_5d"]
        negative_news = [
            {
                **row,
                "title": f"AI 大幅衰退 {index}",
                "summary": "chip 訂單減少",
            }
            for index, row in enumerate(positive_news)
        ]

        second_json_path = write_market_intelligence_report(
            research,
            output_dir,
            news_rows=negative_news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend_path,
            as_of="2026-07-20T12:00:00+08:00",
        )

        second_payload = json.loads(second_json_path.read_text(encoding="utf-8"))
        second_score = second_payload["industries"][0]["sentiment"]["score_5d"]
        history_rows = load_sentiment_history(history_path)
        self.assertTrue(history_path.exists())
        self.assertEqual(len(history_rows), 1)
        self.assertNotEqual(first_score, second_score)
        self.assertEqual(history_rows[0]["score_5d"], second_score)
        self.assertEqual(
            second_payload["artifact_registry"]["outputs"]["sentiment_history"],
            str(history_path),
        )
        self.assertEqual(
            second_payload["artifact_registry"]["dependencies"]["sentiment_history"],
            str(history_path),
        )

    def test_write_report_propagates_history_failure_before_publishing_reports(self):
        research, trend_path, news, flows = self._sentiment_fixture()
        output_dir = self.root / "blocked-sentiment-writer"
        blocked_history_path = self.root / "history-is-a-directory"
        blocked_history_path.mkdir()

        with self.assertRaises(OSError):
            write_market_intelligence_report(
                research,
                output_dir,
                news_rows=news,
                fund_flow_rows=flows,
                industry_trend_report_path=trend_path,
                as_of="2026-07-20T12:00:00+08:00",
                sentiment_history_path=blocked_history_path,
            )

        self.assertFalse((output_dir / "market_intelligence_report.json").exists())
        self.assertFalse((output_dir / "market_intelligence_report.md").exists())
        self.assertFalse((output_dir / "market_intelligence_report.html").exists())

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
