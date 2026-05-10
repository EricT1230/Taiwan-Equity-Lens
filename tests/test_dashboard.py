import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard import discover_dashboard_items, render_dashboard_html


class DashboardTests(unittest.TestCase):
    def test_discover_dashboard_items_finds_reports_comparisons_and_batch_errors(self):
        root = Path(".tmp-cli-test/dashboard")
        reports = root / "reports"
        compare = root / "compare"
        batch = root / "batch"
        reports.mkdir(parents=True, exist_ok=True)
        compare.mkdir(parents=True, exist_ok=True)
        batch.mkdir(parents=True, exist_ok=True)
        (reports / "2330_analysis.html").write_text("<html>report</html>", encoding="utf-8")
        (reports / "2330_raw_data.json").write_text('{"stock_id": "2330"}', encoding="utf-8")
        (compare / "comparison.html").write_text("<html>compare</html>", encoding="utf-8")
        (compare / "comparison.json").write_text('{"rows": []}', encoding="utf-8")
        (batch / "batch_summary.json").write_text(
            json.dumps(
                {
                    "results": [
                        {"stock_id": "2330", "status": "ok"},
                        {"stock_id": "9999", "status": "error", "error": "missing fixture"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        items = discover_dashboard_items([reports, compare, batch])

        self.assertEqual(items["reports"][0]["stock_id"], "2330")
        self.assertEqual(items["comparisons"][0]["html_path"], str(compare / "comparison.html"))
        self.assertEqual(items["batch_summaries"][0]["results"][1]["status"], "error")

    def test_render_dashboard_html_contains_report_links_error_status_and_command_builder(self):
        html = render_dashboard_html(
            {
                "reports": [
                    {
                        "stock_id": "2330",
                        "html_path": "dist/2330_analysis.html",
                        "json_path": "dist/2330_raw_data.json",
                    }
                ],
                "comparisons": [
                    {
                        "html_path": "compare-dist/comparison.html",
                        "json_path": "compare-dist/comparison.json",
                    }
                ],
                "batch_summaries": [
                    {
                        "path": "batch-dist/batch_summary.json",
                        "results": [
                            {"stock_id": "9999", "status": "error", "error": "missing fixture"}
                        ],
                    }
                ],
            }
        )

        self.assertIn("台股基本面工具", html)
        self.assertIn("2330_analysis.html", html)
        self.assertIn("comparison.html", html)
        self.assertIn("missing fixture", html)
        self.assertIn("stockInput", html)
        self.assertIn("python -m taiwan_stock_analysis.cli", html)

    def test_render_dashboard_html_contains_workflow_summary_and_batch_tools(self):
        html = render_dashboard_html(
            {
                "reports": [
                    {"stock_id": "2330", "html_path": "dist/2330_analysis.html", "json_path": ""},
                    {"stock_id": "2303", "html_path": "dist/2303_analysis.html", "json_path": ""},
                ],
                "comparisons": [
                    {"html_path": "compare-dist/comparison.html", "json_path": "compare-dist/comparison.json"}
                ],
                "batch_summaries": [
                    {
                        "path": "batch-dist/batch_summary.json",
                        "results": [
                            {"stock_id": "2330", "status": "ok"},
                            {"stock_id": "9999", "status": "error", "error": "missing fixture"},
                        ],
                    }
                ],
            }
        )

        self.assertIn("summaryReports", html)
        self.assertIn(">2</strong><span>單股報表</span>", html)
        self.assertIn(">1</strong><span>同業比較</span>", html)
        self.assertIn(">2</strong><span>批次項目</span>", html)
        self.assertIn(">1</strong><span>批次錯誤</span>", html)
        self.assertIn("compareInput", html)
        self.assertIn("batchPathInput", html)
        self.assertIn("watchlistTemplate", html)
        self.assertIn("data:text/csv", html)
        self.assertIn("python -m taiwan_stock_analysis.cli compare", html)
        self.assertIn("python -m taiwan_stock_analysis.cli batch", html)


if __name__ == "__main__":
    unittest.main()
