import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from taiwan_stock_analysis.industry_trends import write_industry_trend_report
from taiwan_stock_analysis.market_data_importer import (
    _optional_number,
    parse_tpex_price_payload,
    parse_twse_price_payload,
    write_market_data_bundle,
)
from taiwan_stock_analysis.market_intelligence import (
    _load_trend_report,
    build_market_intelligence_report,
    load_fund_flow_rows,
    write_market_intelligence_report,
)
from taiwan_stock_analysis.sentiment_validation import write_sentiment_validation_report


AS_OF = datetime(2026, 7, 18, 18, tzinfo=timezone(timedelta(hours=8)))


def assert_finite_tree(test_case: unittest.TestCase, value: object, path: str = "report") -> None:
    if isinstance(value, float):
        test_case.assertTrue(math.isfinite(value), f"{path} contains a non-finite float")
    elif isinstance(value, dict):
        for key, item in value.items():
            assert_finite_tree(test_case, item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_finite_tree(test_case, item, f"{path}[{index}]")


class OfficialPriceNonfiniteBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_optional_number_never_returns_nonfinite_values(self) -> None:
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                self.assertIsNone(_optional_number(value))

    def test_official_price_payload_rejects_nonfinite_required_and_optional_numbers(self) -> None:
        payloads = (
            (
                parse_twse_price_payload,
                {
                    "stat": "OK",
                    "fields": ["日期", "成交股數", "收盤價"],
                    "data": [["115/07/09", "100", "NaN"]],
                },
                "close",
            ),
            (
                parse_twse_price_payload,
                {
                    "stat": "OK",
                    "fields": ["日期", "成交股數", "收盤價"],
                    "data": [["115/07/09", "Infinity", "100"]],
                },
                "volume",
            ),
            (
                parse_tpex_price_payload,
                {
                    "tables": [
                        {
                            "fields": ["日期", "成交張數", "收盤"],
                            "data": [["115/07/09", "100", "-Infinity"]],
                        }
                    ]
                },
                "close",
            ),
        )
        for parser, payload, field in payloads:
            with self.subTest(parser=parser.__name__, field=field):
                with self.assertRaisesRegex(ValueError, rf"official price payload row 1.*{field}"):
                    parser(payload, "2330")

    def test_official_payload_nonfinite_becomes_a_source_error_without_nonfinite_artifacts(self) -> None:
        research = self.root / "research.csv"
        output_dir = self.root / "bundle"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,Fixture,Semiconductor,high,watching,,chip\n",
            encoding="utf-8",
        )
        invalid_price_payload = {
            "stat": "OK",
            "fields": ["日期", "成交股數", "收盤價"],
            "data": [["115/07/09", "100", "NaN"]],
        }
        profile = {
            "stock_id": "2330",
            "company_name": "Fixture",
            "company_abbreviation": "Fixture",
            "market": "TWSE",
            "industry_code": "24",
            "industry_name": "Semiconductor",
            "snapshot_date": "2026-07-09",
            "source": "TWSE OpenAPI",
        }

        with (
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_official_profiles",
                return_value=([profile], []),
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_fund_flow_history",
                return_value=([], []),
            ),
            patch("taiwan_stock_analysis.market_data_importer._http_json", return_value=invalid_price_payload),
        ):
            outputs = write_market_data_bundle(
                research, output_dir, as_of="2026-07-12", history_months=1
            )

        report = json.loads(outputs["report"].read_text(encoding="utf-8"))
        self.assertTrue(any("price history 2330" in error for error in report["source_errors"]))
        self.assertNotIn("nan", outputs["price_history"].read_text(encoding="utf-8").lower())
        assert_finite_tree(self, report)
        json.dumps(report, allow_nan=False)


class FundFlowAndTrendArtifactBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _write_fund_flow(self, field: str, value: str) -> Path:
        path = self.root / f"fund-flow-{field}.csv"
        row = {
            "foreign_net": "1",
            "investment_trust_net": "2",
            "dealer_net": "3",
            "total_net": "6",
            "traded_shares": "100",
        }
        row[field] = value
        path.write_text(
            "date,stock_id,foreign_net,investment_trust_net,dealer_net,total_net,traded_shares,source\n"
            f"2026-07-18,2330,{row['foreign_net']},{row['investment_trust_net']},{row['dealer_net']},{row['total_net']},{row['traded_shares']},fixture\n",
            encoding="utf-8",
        )
        return path

    def test_fund_flow_csv_rejects_nonfinite_every_numeric_column_with_context(self) -> None:
        for field in (
            "foreign_net",
            "investment_trust_net",
            "dealer_net",
            "total_net",
            "traded_shares",
        ):
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, rf"row 2.*{field}"):
                        load_fund_flow_rows(self._write_fund_flow(field, value))

    def test_trend_artifact_rejects_json_constants_overflow_and_invalid_encoding(self) -> None:
        cases = {
            "nan.json": '{"categories":[{"average_return_20d":NaN}]}',
            "infinity.json": '{"categories":[{"average_return_20d":Infinity}]}',
            "negative-infinity.json": '{"categories":[{"average_return_20d":-Infinity}]}',
            "overflow.json": '{"categories":[{"average_return_20d":1e9999}]}',
        }
        for filename, content in cases.items():
            with self.subTest(path=filename):
                path = self.root / filename
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "invalid industry trend report"):
                    _load_trend_report(path)

        invalid_encoding = self.root / "invalid-encoding.json"
        invalid_encoding.write_bytes(b'{"categories": "\xff"}')
        with self.assertRaisesRegex(ValueError, "invalid industry trend report"):
            _load_trend_report(invalid_encoding)


class NoPartialNonfinitePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _market_intelligence_inputs(self) -> tuple[Path, Path, list[dict[str, object]], list[dict[str, object]]]:
        research = self.root / "research.csv"
        trend = self.root / "trend.json"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,Fixture,Semiconductor,high,watching,,chip\n",
            encoding="utf-8",
        )
        trend.write_text(
            json.dumps(
                {
                    "as_of_date": "2026-07-18",
                    "session_dates": ["2026-07-17", "2026-07-18"],
                    "categories": [
                        {
                            "category": "Semiconductor",
                            "average_return_1d": 1.0,
                            "average_return_5d": 2.0,
                            "average_return_20d": 3.0,
                            "positive_breadth_5d": 1.0,
                            "positive_breadth_20d": 1.0,
                            "coverage_ratio_5d": 1.0,
                            "coverage_ratio_20d": 1.0,
                            "average_volume_ratio_5d": 1.0,
                            "covered_stock_ids": ["2330"],
                        }
                    ],
                    "stock_trends": [],
                }
            ),
            encoding="utf-8",
        )
        news = [
            {
                "published_at": (AS_OF - timedelta(minutes=index)).isoformat(),
                "title": f"chip story {index}",
                "summary": "",
                "url": f"https://example.test/{index}",
                "source": "fixture",
            }
            for index in range(5)
        ]
        flows = [
            {
                "date": day,
                "stock_id": "2330",
                "foreign_net": 1.0,
                "investment_trust_net": 2.0,
                "dealer_net": 3.0,
                "total_net": 6.0,
                "traded_shares": 100.0,
                "source": "fixture",
            }
            for day in ("2026-07-17", "2026-07-18")
        ]
        return research, trend, news, flows

    def test_market_intelligence_rejects_nonfinite_external_flow_and_returns_a_strict_json_report_for_valid_inputs(self) -> None:
        research, trend, news, flows = self._market_intelligence_inputs()
        flows[0]["foreign_net"] = float("nan")
        with self.assertRaisesRegex(ValueError, r"fund flow.*foreign_net"):
            build_market_intelligence_report(
                research,
                news_rows=news,
                fund_flow_rows=flows,
                industry_trend_report_path=trend,
                as_of=AS_OF,
            )

        flows[0]["foreign_net"] = 1.0
        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend,
            as_of=AS_OF,
        )
        assert_finite_tree(self, report)
        json.dumps(report, allow_nan=False)

    def test_trend_nonfinite_fails_before_market_intelligence_history_or_reports_exist(self) -> None:
        research, trend, news, flows = self._market_intelligence_inputs()
        trend.write_text(
            '{"as_of_date":"2026-07-18","session_dates":["2026-07-18"],"categories":[{"category":"Semiconductor","average_return_20d":NaN}]}',
            encoding="utf-8",
        )
        output_dir = self.root / "market-intelligence"

        with self.assertRaisesRegex(ValueError, "invalid industry trend report"):
            write_market_intelligence_report(
                research,
                output_dir,
                news_rows=news,
                fund_flow_rows=flows,
                industry_trend_report_path=trend,
                as_of=AS_OF,
            )

        self.assertFalse((output_dir / "market_intelligence_report.json").exists())
        self.assertFalse((output_dir / "market_intelligence_report.md").exists())
        self.assertFalse((output_dir / "market_intelligence_report.html").exists())
        self.assertFalse((output_dir / "industry_sentiment_history.csv").exists())

    def test_json_writers_fail_before_any_json_markdown_html_or_history_publication(self) -> None:
        research, trend, news, flows = self._market_intelligence_inputs()
        market_output = self.root / "market-intelligence"
        with patch(
            "taiwan_stock_analysis.market_intelligence.merge_traceability",
            side_effect=lambda report, **_kwargs: {**report, "injected": float("nan")},
        ):
            with self.assertRaisesRegex(ValueError, "non-finite"):
                write_market_intelligence_report(
                    research,
                    market_output,
                    news_rows=news,
                    fund_flow_rows=flows,
                    industry_trend_report_path=trend,
                    as_of=AS_OF,
                )
        for filename in (
            "market_intelligence_report.json",
            "market_intelligence_report.md",
            "market_intelligence_report.html",
            "industry_sentiment_history.csv",
        ):
            self.assertFalse((market_output / filename).exists(), filename)

        trend_output = self.root / "industry-trend"
        with patch(
            "taiwan_stock_analysis.industry_trends.build_industry_trend_report",
            return_value={"injected": float("nan")},
        ):
            with self.assertRaisesRegex(ValueError, "non-finite"):
                write_industry_trend_report(research, self.root / "prices.csv", trend_output)
        for filename in ("industry_trend_report.json", "industry_trend_report.md", "industry_trend_report.html"):
            self.assertFalse((trend_output / filename).exists(), filename)

        validation_output = self.root / "validation" / "report.json"
        with patch(
            "taiwan_stock_analysis.sentiment_validation.build_sentiment_validation_report",
            return_value={"injected": float("nan")},
        ):
            with self.assertRaisesRegex(ValueError, "non-finite"):
                write_sentiment_validation_report(self.root / "missing-history.csv", validation_output)
        self.assertFalse(validation_output.exists())

        importer_output = self.root / "market-data"
        with (
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_official_profiles",
                return_value=([], []),
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.fetch_fund_flow_history",
                return_value=([], []),
            ),
            patch(
                "taiwan_stock_analysis.market_data_importer.build_market_data_report",
                return_value={"injected": float("nan")},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "non-finite"):
                write_market_data_bundle(research, importer_output, as_of="2026-07-18")
        for filename in (
            "market_data_report.json",
            "market_data_report.md",
            "official_universe.csv",
            "research_official.csv",
            "industry_price_history.csv",
            "fund_flow.csv",
        ):
            self.assertFalse((importer_output / filename).exists(), filename)


if __name__ == "__main__":
    unittest.main()
