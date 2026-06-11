import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.industry_trends import (
    NON_ADVICE_NOTICE,
    build_industry_trend_report,
    load_price_history_rows,
    render_industry_trend_html,
    render_industry_trend_markdown,
    write_industry_trend_report,
)


class IndustryTrendTests(unittest.TestCase):
    def test_load_price_history_rows_normalizes_required_fields(self):
        root = Path(".tmp-industry-trends-test")
        price_history = root / "price-history.csv"
        root.mkdir(parents=True, exist_ok=True)
        price_history.write_text(
            "stock_id,date,close,volume,source\n"
            " 2330 , 2026-05-01 , 900 , 1000 , fixture \n",
            encoding="utf-8",
        )

        rows = load_price_history_rows(price_history)

        self.assertEqual(
            rows,
            [
                {
                    "stock_id": "2330",
                    "date": "2026-05-01",
                    "close": 900.0,
                    "volume": 1000.0,
                    "source": "fixture",
                }
            ],
        )

    def test_build_industry_trend_report_aggregates_sector_rotation(self):
        root = Path(".tmp-industry-trends-test/aggregate")
        research = root / "research.csv"
        price_history = root / "industry-price-history.csv"
        root.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,watching,\n"
            "2303,UMC,Semiconductor,medium,watching,\n"
            "1504,TECO,Electric Machinery,medium,watching,\n",
            encoding="utf-8",
        )
        _write_price_history(
            price_history,
            {
                "2330": [100 + index for index in range(21)],
                "2303": [80 - (index * 0.5) for index in range(21)],
            },
        )

        report = build_industry_trend_report(research, price_history)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["research_path"], str(research))
        self.assertEqual(report["price_history_path"], str(price_history))
        self.assertEqual(report["coverage"]["stocks_total"], 3)
        self.assertEqual(report["coverage"]["stocks_with_price_history"], 2)
        self.assertEqual(report["coverage"]["missing_price_history"], 1)
        self.assertEqual(report["quality_gate"]["status"], "needs_data")
        self.assertEqual(report["quality_gate"]["blocker_count"], 1)
        self.assertIn("1504", report["quality_gate"]["blockers"][0])

        stock_trends = {item["stock_id"]: item for item in report["stock_trends"]}
        self.assertEqual(stock_trends["2330"]["status"], "available")
        self.assertEqual(stock_trends["2330"]["return_20d"], 20.0)
        self.assertEqual(stock_trends["2330"]["direction"], "up")
        self.assertEqual(stock_trends["2330"]["volume_signal"], "expanding")
        self.assertEqual(stock_trends["1504"]["status"], "missing_price_history")

        categories = {item["category"]: item for item in report["categories"]}
        semiconductor = categories["Semiconductor"]
        self.assertEqual(semiconductor["stock_count"], 2)
        self.assertEqual(semiconductor["coverage_count"], 2)
        self.assertEqual(semiconductor["missing_count"], 0)
        self.assertEqual(semiconductor["average_return_20d"], 3.75)
        self.assertEqual(semiconductor["direction"], "mixed")
        self.assertEqual(semiconductor["leading_stocks"][0]["stock_id"], "2330")
        self.assertEqual(semiconductor["lagging_stocks"][0]["stock_id"], "2303")
        self.assertEqual(report["non_advice_notice"], NON_ADVICE_NOTICE)

    def test_write_industry_trend_report_writes_json_markdown_and_html(self):
        root = Path(".tmp-industry-trends-test/write")
        research = root / "research.csv"
        price_history = root / "industry-price-history.csv"
        output_dir = root / "industry-trends"
        root.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,watching,\n",
            encoding="utf-8",
        )
        _write_price_history(price_history, {"2330": [100 + index for index in range(21)]})

        summary_path = write_industry_trend_report(research, price_history, output_dir)

        self.assertEqual(summary_path, output_dir / "industry_trend_report.json")
        self.assertTrue(summary_path.exists())
        self.assertTrue((output_dir / "industry_trend_report.md").exists())
        self.assertTrue((output_dir / "industry_trend_report.html").exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["quality_gate"]["status"], "ready")
        self.assertEqual(payload["artifact_registry"]["self"], str(summary_path))
        self.assertEqual(payload["artifact_registry"]["dependencies"]["research_csv"], str(research))
        self.assertEqual(payload["artifact_registry"]["dependencies"]["price_history"], str(price_history))

        markdown = render_industry_trend_markdown(payload)
        html = render_industry_trend_html(payload)
        self.assertIn("Industry Trend Report", markdown)
        self.assertIn("Non-Advice Boundary", markdown)
        self.assertIn('data-industry-trend-report="true"', html)
        self.assertIn("not investment advice", html)

    def test_build_industry_trend_report_rejects_missing_columns(self):
        root = Path(".tmp-industry-trends-test/bad")
        research = root / "research.csv"
        price_history = root / "bad-price-history.csv"
        root.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,watching,\n",
            encoding="utf-8",
        )
        price_history.write_text("stock_id,date\n2330,2026-05-01\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "price history CSV must include"):
            build_industry_trend_report(research, price_history)


def _write_price_history(path: Path, closes_by_stock: dict[str, list[float]]) -> None:
    dates = [
        "2026-05-01",
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
        "2026-05-08",
        "2026-05-11",
        "2026-05-12",
        "2026-05-13",
        "2026-05-14",
        "2026-05-15",
        "2026-05-18",
        "2026-05-19",
        "2026-05-20",
        "2026-05-21",
        "2026-05-22",
        "2026-05-25",
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["stock_id,date,close,volume,source"]
    for stock_id, closes in closes_by_stock.items():
        for index, close in enumerate(closes):
            volume = 1000 + index * 20
            if stock_id == "2330" and index == len(closes) - 1:
                volume = 1800
            lines.append(f"{stock_id},{dates[index]},{close},{volume},fixture")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
