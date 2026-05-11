import json
import os
import unittest
from pathlib import Path

from taiwan_stock_analysis.cli import main, run


def goodinfo_html(rows: str) -> str:
    return f"""
<html><body>
  <table></table><table></table><table></table><table></table><table></table><table></table>
  <table>
    <tr><th>\u9805\u76ee</th><th>2024</th><th>%</th><th>2023</th><th>%</th></tr>
    {rows}
  </table>
</body></html>
"""


class CliTests(unittest.TestCase):
    def test_run_with_fixture_writes_json_and_html(self):
        root = Path(".tmp-cli-test")
        fixture_dir = root / "fixtures"
        output_dir = root / "dist"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "IS_YEAR.html").write_text(
            goodinfo_html(
                """
                <tr><td>\u71df\u696d\u6536\u5165\u5408\u8a08</td><td>1000</td><td>100</td><td>900</td><td>100</td></tr>
                <tr><td>\u71df\u696d\u6bdb\u5229\uff08\u6bdb\u640d\uff09</td><td>400</td><td>40</td><td>360</td><td>40</td></tr>
                <tr><td>\u71df\u696d\u5229\u76ca\uff08\u640d\u5931\uff09</td><td>250</td><td>25</td><td>200</td><td>22.2</td></tr>
                <tr><td>\u7a05\u5f8c\u6de8\u5229</td><td>200</td><td>20</td><td>180</td><td>20</td></tr>
                <tr><td>\u6bcf\u80a1\u7a05\u5f8c\u76c8\u9918(\u5143)</td><td>8.5</td><td></td><td>7.1</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )
        (fixture_dir / "BS_YEAR.html").write_text(
            goodinfo_html(
                """
                <tr><td>\u6d41\u52d5\u8cc7\u7522\u5408\u8a08</td><td>600</td><td></td><td>500</td><td></td></tr>
                <tr><td>\u6d41\u52d5\u8ca0\u50b5\u5408\u8a08</td><td>300</td><td></td><td>250</td><td></td></tr>
                <tr><td>\u8ca0\u50b5\u7e3d\u984d</td><td>500</td><td></td><td>450</td><td></td></tr>
                <tr><td>\u8cc7\u7522\u7e3d\u984d</td><td>1250</td><td></td><td>1100</td><td></td></tr>
                <tr><td>\u80a1\u6771\u6b0a\u76ca\u7e3d\u984d</td><td>750</td><td></td><td>650</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )
        (fixture_dir / "CF_YEAR.html").write_text(
            goodinfo_html(
                """
                <tr><td>\u71df\u696d\u6d3b\u52d5\u4e4b\u6de8\u73fe\u91d1\u6d41\u5165\uff08\u51fa\uff09</td><td>180</td><td></td><td>160</td><td></td></tr>
                <tr><td>\u56fa\u5b9a\u8cc7\u7522\uff08\u589e\u52a0\uff09\u6e1b\u5c11</td><td>-50</td><td></td><td>-40</td><td></td></tr>
                <tr><td>\u767c\u653e\u73fe\u91d1\u80a1\u5229</td><td>-30</td><td></td><td>-25</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )

        json_path, html_path = run(
            stock_id="2330",
            company_name="\u53f0\u7a4d\u96fb",
            output_dir=output_dir,
            fixture_dir=fixture_dir,
        )

        self.assertTrue(json_path.exists())
        self.assertTrue(html_path.exists())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["stock_id"], "2330")
        self.assertEqual(data["metrics_by_year"]["2024"]["gross_margin"], 40.0)
        self.assertIn("operations", data["insights"])
        self.assertTrue(data["insights"]["operations"])
        self.assertIn("total_score", data["scorecard"])
        self.assertIn("profitability", data["scorecard"]["dimensions"])
        self.assertIn("\u53f0\u7a4d\u96fb (2330)", html_path.read_text(encoding="utf-8"))

    def test_main_preserves_single_stock_cli_usage(self):
        root = Path(".tmp-cli-test")
        fixture_dir = root / "single-main-fixture"
        output_dir = root / "single-main-dist"
        self._write_fixture(fixture_dir, revenue=1000, gross_profit=500, net_income=250)

        exit_code = main([
            "2330",
            "--company-name",
            "台積電",
            "--fixture",
            str(fixture_dir),
            "--output-dir",
            str(output_dir),
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "2330_raw_data.json").exists())

    def test_main_accepts_valuation_csv_for_single_stock_report(self):
        root = Path(".tmp-cli-test")
        fixture_dir = root / "valuation-main-fixture"
        output_dir = root / "valuation-main-dist"
        valuation_csv = root / "valuation-inputs.csv"
        self._write_fixture(fixture_dir, revenue=1000, gross_profit=500, net_income=250)
        valuation_csv.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high,price_date,price_source,price_status,price_status_message,price_retry_hint,warning\n"
            "2330,1000,160,12,60,15,20,25,115/05/06,TPEX_DAILY_CLOSE,warning,TWSE price was unavailable; TPEx fallback was used.,Run again after the next market data update.,\n",
            encoding="utf-8",
        )

        exit_code = main([
            "2330",
            "--fixture",
            str(fixture_dir),
            "--output-dir",
            str(output_dir),
            "--valuation-csv",
            str(valuation_csv),
        ])

        self.assertEqual(exit_code, 0)
        data = json.loads((output_dir / "2330_raw_data.json").read_text(encoding="utf-8"))
        self.assertEqual(data["valuation"]["metrics"]["pe"], 100.0)
        self.assertEqual(data["metadata"]["reliability"][0]["status"], "warning")
        self.assertEqual(data["metadata"]["reliability"][0]["source"], "TPEX_DAILY_CLOSE")
        html = (output_dir / "2330_analysis.html").read_text(encoding="utf-8")
        self.assertIn("估值情境", html)
        self.assertIn("資料可信度", html)
        self.assertIn("TWSE price was unavailable", html)
        self.assertIn("估值情境", (output_dir / "2330_analysis.html").read_text(encoding="utf-8"))

    def test_main_surfaces_legacy_valuation_csv_warning_in_report(self):
        root = Path(".tmp-cli-test")
        fixture_dir = root / "legacy-valuation-warning-fixture"
        output_dir = root / "legacy-valuation-warning-dist"
        valuation_csv = root / "legacy-valuation-warning.csv"
        self._write_fixture(fixture_dir, revenue=1000, gross_profit=500, net_income=250)
        valuation_csv.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high,warning\n"
            "2330,1000,160,12,60,15,20,25,manual warning from legacy CSV\n",
            encoding="utf-8",
        )

        exit_code = main([
            "2330",
            "--fixture",
            str(fixture_dir),
            "--output-dir",
            str(output_dir),
            "--valuation-csv",
            str(valuation_csv),
        ])

        self.assertEqual(exit_code, 0)
        data = json.loads((output_dir / "2330_raw_data.json").read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["reliability"][0]["status"], "warning")
        self.assertIn("manual warning from legacy CSV", data["metadata"]["reliability"][0]["message"])
        self.assertIn("manual warning from legacy CSV", (output_dir / "2330_analysis.html").read_text(encoding="utf-8"))

    def test_main_dashboard_writes_static_index(self):
        root = Path(".tmp-cli-test")
        reports_dir = root / "dashboard-cli-reports"
        output_path = root / "dashboard-index.html"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "2330_analysis.html").write_text("<html>report</html>", encoding="utf-8")
        (reports_dir / "2330_raw_data.json").write_text('{"stock_id": "2330"}', encoding="utf-8")

        exit_code = main([
            "dashboard",
            "--scan-dir",
            str(reports_dir),
            "--output",
            str(output_path),
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("台股基本面儀表板", output_path.read_text(encoding="utf-8"))
        self.assertIn("2330_analysis.html", output_path.read_text(encoding="utf-8"))

    def test_main_dashboard_default_scan_includes_workflow_dist(self):
        cwd = Path.cwd()
        root = cwd / ".tmp-cli-test" / "dashboard-default-cwd"
        root.mkdir(parents=True, exist_ok=True)
        output_path = Path("dashboard-workflow-default.html")
        workflow_dist = Path("workflow-dist")
        exit_code = None
        os.chdir(root)
        try:
            workflow_dist.mkdir(exist_ok=True)
            (workflow_dist / "workflow_summary.json").write_text(
                json.dumps(
                    {
                        "watchlist_path": "watchlist.csv",
                        "stock_ids": ["2330"],
                        "successful_stock_ids": ["2330"],
                        "paths": {"valuation_csv": "workflow-dist/valuation.csv"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = main([
                "dashboard",
                "--output",
                str(output_path),
            ])
        finally:
            os.chdir(cwd)

        self.assertEqual(exit_code, 0)
        self.assertIn("workflow_summary.json", (root / output_path).read_text(encoding="utf-8"))

    def test_main_price_template_writes_valuation_csv(self):
        root = Path(".tmp-cli-test")
        output_path = root / "price-template.csv"

        exit_code = main([
            "price-template",
            "2330",
            "--output",
            str(output_path),
            "--offline",
        ])

        self.assertEqual(exit_code, 0)
        text = output_path.read_text(encoding="utf-8")
        self.assertIn("stock_id,price", text)
        self.assertIn("2330,", text)
        self.assertIn("offline mode", text)

    def test_main_price_template_accepts_analysis_dir_for_enrichment(self):
        root = Path(".tmp-cli-test")
        analysis_dir = root / "price-template-analysis"
        output_path = root / "price-template-enriched.csv"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "2330_raw_data.json").write_text(
            json.dumps(
                {
                    "years": ["2025"],
                    "valuation": {"eps_scenarios": {"base": 60.0}},
                    "metrics_by_year": {"2025": {"eps": 50.0}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = main([
            "price-template",
            "2330",
            "--output",
            str(output_path),
            "--analysis-dir",
            str(analysis_dir),
            "--offline",
        ])

        self.assertEqual(exit_code, 0)
        text = output_path.read_text(encoding="utf-8")
        self.assertIn(",60.0,10.0,15.0,20.0,", text)

    def test_run_compare_with_fixture_root_writes_comparison_outputs(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "compare-fixtures"
        output_dir = root / "compare-dist"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        self._write_fixture(fixture_root / "2303", revenue=800, gross_profit=240, net_income=120)

        from taiwan_stock_analysis.cli import run_compare

        json_path, html_path = run_compare(["2330", "2303"], output_dir=output_dir, fixture_root=fixture_root)

        comparison = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(comparison["rows"]), 2)
        self.assertEqual(comparison["rows"][0]["stock_id"], "2330")
        self.assertTrue(html_path.exists())
        self.assertIn("同業比較", html_path.read_text(encoding="utf-8"))

    def test_run_batch_records_per_stock_errors_without_stopping(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "batch-fixtures"
        output_dir = root / "batch-dist"
        watchlist = root / "watchlist.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        (fixture_root / "9999").mkdir(parents=True, exist_ok=True)
        watchlist.write_text("stock_id,company_name\n2330,台積電\n9999,壞資料\n", encoding="utf-8")

        from taiwan_stock_analysis.cli import run_batch

        summary_path = run_batch(watchlist, output_dir=output_dir, fixture_root=fixture_root)

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["results"][0]["stock_id"], "2330")
        self.assertEqual(summary["results"][0]["status"], "ok")
        self.assertIn("warning_count", summary["results"][0])
        self.assertIsInstance(summary["results"][0]["warning_count"], int)
        self.assertEqual(summary["results"][1]["stock_id"], "9999")
        self.assertEqual(summary["results"][1]["status"], "error")

    def test_run_batch_accepts_valuation_csv(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "batch-valuation-fixtures"
        output_dir = root / "batch-valuation-dist"
        watchlist = root / "batch-valuation-watchlist.csv"
        valuation_csv = root / "batch-valuation.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        watchlist.write_text("stock_id,company_name\n2330,Alpha\n", encoding="utf-8")
        valuation_csv.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high\n"
            "2330,100,50,2,10,8,12,16\n",
            encoding="utf-8",
        )

        from taiwan_stock_analysis.cli import run_batch

        summary_path = run_batch(
            watchlist,
            output_dir=output_dir,
            fixture_root=fixture_root,
            valuation_csv=valuation_csv,
        )

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        data = json.loads((output_dir / "2330_raw_data.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["results"][0]["status"], "ok")
        self.assertEqual(data["valuation"]["metrics"]["pe"], 10.0)

    def test_main_workflow_writes_summary(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "workflow-cli-fixtures"
        output_dir = root / "workflow-cli-dist"
        watchlist = root / "workflow-cli-watchlist.csv"
        valuation_csv = root / "workflow-cli-valuation.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        self._write_fixture(fixture_root / "2303", revenue=800, gross_profit=320, net_income=160)
        watchlist.write_text("stock_id,company_name\n2330,Alpha\n2303,Beta\n", encoding="utf-8")
        valuation_csv.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high\n"
            "2330,100,50,2,10,8,12,16\n"
            "2303,80,40,1.5,8,8,12,16\n",
            encoding="utf-8",
        )

        exit_code = main([
            "workflow",
            str(watchlist),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--valuation-csv",
            str(valuation_csv),
            "--offline-prices",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "workflow_summary.json").exists())
        self.assertTrue((output_dir / "dashboard.html").exists())
        self.assertTrue((output_dir / "comparison" / "comparison.json").exists())

    def _write_fixture(self, fixture_dir: Path, revenue: float, gross_profit: float, net_income: float) -> None:
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "IS_YEAR.html").write_text(
            goodinfo_html(
                f"""
                <tr><td>\u71df\u696d\u6536\u5165\u5408\u8a08</td><td>{revenue}</td><td>100</td><td>{revenue * 0.9}</td><td>100</td></tr>
                <tr><td>\u71df\u696d\u6bdb\u5229\uff08\u6bdb\u640d\uff09</td><td>{gross_profit}</td><td></td><td>{gross_profit * 0.9}</td><td></td></tr>
                <tr><td>\u7a05\u5f8c\u6de8\u5229</td><td>{net_income}</td><td></td><td>{net_income * 0.9}</td><td></td></tr>
                <tr><td>\u6bcf\u80a1\u7a05\u5f8c\u76c8\u9918(\u5143)</td><td>10</td><td></td><td>9</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )
        (fixture_dir / "BS_YEAR.html").write_text(
            goodinfo_html(
                """
                <tr><td>\u6d41\u52d5\u8cc7\u7522\u5408\u8a08</td><td>600</td><td></td><td>500</td><td></td></tr>
                <tr><td>\u6d41\u52d5\u8ca0\u50b5\u5408\u8a08</td><td>300</td><td></td><td>250</td><td></td></tr>
                <tr><td>\u8ca0\u50b5\u7e3d\u984d</td><td>500</td><td></td><td>450</td><td></td></tr>
                <tr><td>\u8cc7\u7522\u7e3d\u984d</td><td>1250</td><td></td><td>1100</td><td></td></tr>
                <tr><td>\u80a1\u6771\u6b0a\u76ca\u7e3d\u984d</td><td>750</td><td></td><td>650</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )
        (fixture_dir / "CF_YEAR.html").write_text(
            goodinfo_html(
                """
                <tr><td>\u71df\u696d\u6d3b\u52d5\u4e4b\u6de8\u73fe\u91d1\u6d41\u5165\uff08\u51fa\uff09</td><td>180</td><td></td><td>160</td><td></td></tr>
                <tr><td>\u56fa\u5b9a\u8cc7\u7522\uff08\u589e\u52a0\uff09\u6e1b\u5c11</td><td>-50</td><td></td><td>-40</td><td></td></tr>
                """
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
