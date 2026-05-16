import json
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
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
    def test_main_doctor_release_returns_zero_for_current_metadata(self):
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["doctor", "release", "--version", "0.22.0"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Release readiness OK", output.getvalue())

    def test_main_doctor_release_returns_one_for_wrong_version(self):
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["doctor", "release", "--version", "999.0.0"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Release readiness failed", output.getvalue())

    def test_tests_workflow_uses_node24_compatible_actions(self):
        workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")

        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertNotIn("actions/checkout@v4", workflow)
        self.assertNotIn("actions/setup-python@v5", workflow)

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
        self.assertEqual(data["metadata"]["source_mode"], "fixture")
        self.assertEqual(data["metadata"]["source_review"]["status"], "manual_review")
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

    def test_main_research_init_writes_template(self):
        output = Path(".tmp-cli-test/research-template.csv")
        if output.exists():
            output.unlink()

        exit_code = main(["research", "init", "--output", str(output)])

        self.assertEqual(exit_code, 0)
        self.assertTrue(output.exists())
        self.assertIn(
            "stock_id,company_name,category,priority,research_state,notes",
            output.read_text(encoding="utf-8"),
        )

    def test_main_research_summary_writes_json(self):
        root = Path(".tmp-cli-test")
        research = root / "research-summary.csv"
        output = root / "research_summary.json"
        root.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Needs valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "summary",
            str(research),
            "--workflow-dir",
            str(root / "missing"),
            "--output",
            str(output),
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue(output.exists())
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["counts"]["total"], 1)
        self.assertEqual(payload["items"][0]["workflow_status"], "skipped")

    def test_main_memo_writes_markdown(self):
        root = Path(".tmp-cli-test")
        analysis_path = root / "memo-cli" / "2330_raw_data.json"
        output_path = root / "memo-cli" / "2330_memo.md"
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(json.dumps(_memo_analysis_payload()), encoding="utf-8")

        exit_code = main([
            "memo",
            str(analysis_path),
            "--output",
            str(output_path),
            "--format",
            "markdown",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.exists())
        self.assertIn("# Research Memo: 2330", output_path.read_text(encoding="utf-8"))

    def test_main_research_memo_writes_summary(self):
        root = Path(".tmp-cli-test")
        workflow_dir = root / "research-memo-dist"
        reports_dir = workflow_dir / "reports"
        output_dir = workflow_dir / "memos"
        research = root / "research-memo.csv"
        reports_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Track assumptions\n",
            encoding="utf-8",
        )
        (reports_dir / "2330_raw_data.json").write_text(json.dumps(_memo_analysis_payload()), encoding="utf-8")

        exit_code = main([
            "research",
            "memo",
            str(research),
            "--workflow-dir",
            str(workflow_dir),
            "--output-dir",
            str(output_dir),
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((workflow_dir / "research_summary.json").exists())
        self.assertTrue((output_dir / "2330_memo.md").exists())
        self.assertTrue((output_dir / "2330_memo.html").exists())
        summary = json.loads((output_dir / "memo_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["generated"][0]["stock_id"], "2330")

    def test_main_research_memo_defaults_output_dir_to_workflow_dir(self):
        root = Path(".tmp-cli-test")
        workflow_dir = root / "custom-research-memo-dist"
        reports_dir = workflow_dir / "reports"
        research = root / "custom-research-memo.csv"
        reports_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Track assumptions\n",
            encoding="utf-8",
        )
        (reports_dir / "2330_raw_data.json").write_text(json.dumps(_memo_analysis_payload()), encoding="utf-8")

        exit_code = main([
            "research",
            "memo",
            str(research),
            "--workflow-dir",
            str(workflow_dir),
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((workflow_dir / "memos" / "memo_summary.json").exists())
        self.assertFalse((Path("research-dist") / "memos" / "memo_summary.json").exists())

    def test_main_research_pack_writes_summary(self):
        root = Path(".tmp-cli-test")
        workflow_dir = root / "research-pack-dist"
        output_dir = workflow_dir / "packs"
        research = root / "research-pack.csv"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Track assumptions\n",
            encoding="utf-8",
        )
        (workflow_dir / "research_summary.json").write_text(
            json.dumps(
                {
                    "counts": {"total": 1, "needs_attention": 1},
                    "items": [
                        {
                            "stock_id": "2330",
                            "company_name": "TSMC",
                            "research_state": "review",
                            "priority": "high",
                            "workflow_status": "ok",
                            "reliability_status": "warning",
                            "attention_reasons": ["research state requires review"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "pack",
            str(research),
            "--workflow-dir",
            str(workflow_dir),
            "--output-dir",
            str(output_dir),
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "pack_summary.json").exists())
        self.assertTrue((output_dir / "research-pack.md").exists())
        self.assertTrue((output_dir / "research-pack.html").exists())

    def test_main_research_action_set_and_list_use_state_file(self):
        root = Path(".tmp-cli-test")
        state_path = root / "review_action_state.json"
        summary_path = root / "research-action-summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "review_action_queue": [
                        {
                            "stock_id": "2330",
                            "priority": "high",
                            "actions": [
                                {
                                    "id": "workflow-error",
                                    "category": "workflow",
                                    "severity": "error",
                                    "message": "Fix workflow.",
                                    "status": "open",
                                }
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        set_output = StringIO()
        with redirect_stdout(set_output):
            set_exit_code = main([
                "research",
                "action",
                "set",
                str(state_path),
                "2330",
                "workflow-error",
                "--status",
                "done",
                "--note",
                "checked",
            ])

        list_output = StringIO()
        with redirect_stdout(list_output):
            list_exit_code = main([
                "research",
                "action",
                "list",
                str(summary_path),
                "--state",
                str(state_path),
            ])

        self.assertEqual(set_exit_code, 0)
        self.assertEqual(list_exit_code, 0)
        self.assertTrue(state_path.exists())
        self.assertIn("Wrote", set_output.getvalue())
        self.assertIn("stock_id\tpriority\tstatus\tseverity\tcategory\taction_id\tmessage", list_output.getvalue())
        self.assertIn("2330\thigh\tdone\terror\tworkflow\tworkflow-error\tFix workflow.", list_output.getvalue())

    def test_main_research_action_set_backs_up_existing_state_file(self):
        root = Path(".tmp-cli-test/research-action-set-backup")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        for backup in root.glob("review_action_state.json.bak-*"):
            backup.unlink()
        original_state = {
            "actions": {
                "2330:workflow-error": {
                    "stock_id": "2330",
                    "action_id": "workflow-error",
                    "status": "open",
                    "note": "original",
                    "updated_at": "2026-05-15T09:00:00Z",
                }
            }
        }
        original_text = json.dumps(original_state, indent=2)
        state_path.write_text(original_text, encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "set",
                str(state_path),
                "2330",
                "workflow-error",
                "--status",
                "done",
            ])

        backups = list(root.glob("review_action_state.json.bak-*"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original_text)
        self.assertIn(f"Backup review action state: {backups[0]}", output.getvalue())
        self.assertIn("Wrote", output.getvalue())

    def test_main_research_action_set_does_not_backup_missing_or_invalid_state(self):
        root = Path(".tmp-cli-test/research-action-set-no-backup")
        root.mkdir(parents=True, exist_ok=True)
        missing_state_path = root / "missing_review_action_state.json"
        invalid_state_path = root / "invalid_review_action_state.json"
        for backup in root.glob("*.bak-*"):
            backup.unlink()
        if missing_state_path.exists():
            missing_state_path.unlink()
        invalid_state_path.write_text("{", encoding="utf-8")

        missing_output = StringIO()
        with redirect_stdout(missing_output):
            missing_exit_code = main([
                "research",
                "action",
                "set",
                str(missing_state_path),
                "2330",
                "workflow-error",
                "--status",
                "done",
            ])
        invalid_output = StringIO()
        with redirect_stdout(invalid_output):
            invalid_exit_code = main([
                "research",
                "action",
                "set",
                str(invalid_state_path),
                "2330",
                "workflow-error",
                "--status",
                "done",
            ])

        self.assertEqual(missing_exit_code, 0)
        self.assertNotIn("Backup review action state", missing_output.getvalue())
        self.assertEqual(invalid_exit_code, 1)
        self.assertEqual(invalid_state_path.read_text(encoding="utf-8"), "{")
        self.assertIn("Warning: Could not read review action state", invalid_output.getvalue())
        self.assertEqual(list(root.glob("*.bak-*")), [])

    def test_main_research_action_restore_backs_up_current_and_restores_backup(self):
        root = Path(".tmp-cli-test/research-action-restore")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        backup_path = root / "review_action_state.json.bak-source"
        for backup in root.glob("review_action_state.json.bak-*"):
            if backup != backup_path:
                backup.unlink()
        current_text = json.dumps(
            {
                "actions": {
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "done",
                        "note": "current",
                        "updated_at": "2026-05-15T09:00:00Z",
                    }
                }
            },
            indent=2,
        )
        restore_bytes = (
            b'{\r\n'
            b'  "actions": {\r\n'
            b'    "2330:workflow-error": {\r\n'
            b'      "stock_id": "2330",\r\n'
            b'      "action_id": "workflow-error",\r\n'
            b'      "status": "open",\r\n'
            b'      "note": "restore",\r\n'
            b'      "updated_at": "2026-05-15T08:00:00Z"\r\n'
            b'    }\r\n'
            b'  }\r\n'
            b'}\r\n'
        )
        state_path.write_text(current_text, encoding="utf-8")
        backup_path.write_bytes(restore_bytes)

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "restore", str(state_path), str(backup_path)])

        backups = [backup for backup in root.glob("review_action_state.json.bak-*") if backup != backup_path]
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), current_text)
        self.assertEqual(state_path.read_bytes(), restore_bytes)
        self.assertIn(f"Backup review action state: {backups[0]}", output.getvalue())
        self.assertIn(f"Restored review action state: {state_path}", output.getvalue())

    def test_main_research_action_restore_missing_target_prints_only_restore_line(self):
        root = Path(".tmp-cli-test/research-action-restore-missing-target")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        backup_path = root / "review_action_state.json.bak-source"
        if state_path.exists():
            state_path.unlink()
        for backup in root.glob("review_action_state.json.bak-*"):
            if backup != backup_path:
                backup.unlink()
        backup_path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "open",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "restore", str(state_path), str(backup_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(state_path.read_bytes(), backup_path.read_bytes())
        self.assertNotIn("Backup review action state", output.getvalue())
        self.assertIn(f"Restored review action state: {state_path}", output.getvalue())

    def test_main_research_action_restore_invalid_backup_returns_one_without_writing(self):
        root = Path(".tmp-cli-test/research-action-restore-invalid-backup")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        backup_path = root / "review_action_state.json.bak-source"
        current_text = json.dumps(
            {
                "actions": {
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "done",
                    }
                }
            }
        )
        state_path.write_text(current_text, encoding="utf-8")
        backup_path.write_text("{", encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "restore", str(state_path), str(backup_path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(state_path.read_text(encoding="utf-8"), current_text)
        self.assertIn("Warning: Could not read backup review action state", output.getvalue())

    def test_main_research_action_restore_invalid_current_returns_one_without_writing(self):
        root = Path(".tmp-cli-test/research-action-restore-invalid-current")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        backup_path = root / "review_action_state.json.bak-source"
        state_path.write_text("{", encoding="utf-8")
        backup_text = json.dumps(
            {
                "actions": {
                    "2330:workflow-error": {
                        "stock_id": "2330",
                        "action_id": "workflow-error",
                        "status": "open",
                    }
                }
            }
        )
        backup_path.write_text(backup_text, encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "restore", str(state_path), str(backup_path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(state_path.read_text(encoding="utf-8"), "{")
        self.assertEqual(backup_path.read_text(encoding="utf-8"), backup_text)
        self.assertIn("Warning: Could not read current review action state", output.getvalue())

    def test_main_research_action_backups_lists_text_rows_newest_first(self):
        root = Path(".tmp-cli-test/research-action-backups-text")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        for item in root.glob("*"):
            if item.is_file():
                item.unlink()
        older = root / "review_action_state.json.bak-20260516T173000Z"
        newer = root / "review_action_state.json.bak-20260516T180000Z"
        older.write_text("old", encoding="utf-8")
        newer.write_text("newer", encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "backups", str(state_path)])

        lines = output.getvalue().splitlines()
        self.assertEqual(exit_code, 0)
        self.assertEqual(lines[0], "created_at\tsize\tpath")
        self.assertEqual(lines[1], f"2026-05-16T18:00:00Z\t5\t{newer}")
        self.assertEqual(lines[2], f"2026-05-16T17:30:00Z\t3\t{older}")

    def test_main_research_action_backups_empty_output_prints_header(self):
        root = Path(".tmp-cli-test/research-action-backups-empty")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        for item in root.glob("*"):
            if item.is_file():
                item.unlink()

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "backups", str(state_path)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().splitlines(), ["created_at\tsize\tpath"])

    def test_main_research_action_backups_json_output_is_deterministic(self):
        root = Path(".tmp-cli-test/research-action-backups-json")
        root.mkdir(parents=True, exist_ok=True)
        state_path = root / "review_action_state.json"
        for item in root.glob("*"):
            if item.is_file():
                item.unlink()
        newer = root / "review_action_state.json.bak-20260516T180000Z"
        unknown = root / "review_action_state.json.bak-source"
        newer.write_text("newer", encoding="utf-8")
        unknown.write_text("unknown", encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "backups", str(state_path), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state_path"], str(state_path))
        self.assertEqual(
            payload["backups"],
            [
                {
                    "created_at": "2026-05-16T18:00:00Z",
                    "path": str(newer),
                    "size": 5,
                },
                {
                    "created_at": "unknown",
                    "path": str(unknown),
                    "size": 7,
                },
            ],
        )

    def test_main_research_action_report_uses_explicit_state_file(self):
        root = Path(".tmp-cli-test")
        state_path = root / "review_action_report_state.json"
        summary_path = root / "research-action-report-summary.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "done",
                            "note": "checked",
                            "updated_at": "2026-05-15T09:00:00Z",
                        },
                        "9999:old-action": {
                            "stock_id": "9999",
                            "action_id": "old-action",
                            "status": "ignored",
                            "note": "obsolete",
                            "updated_at": "2026-05-15T10:00:00Z",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "report",
                str(summary_path),
                "--state",
                str(state_path),
                "--next-open-limit",
                "1",
            ])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("total_actions: 2", text)
        self.assertIn("by_status: open=1 done=1 deferred=0 ignored=0", text)
        self.assertIn("stale_state: 1", text)
        self.assertIn("last_updated: 2026-05-15T10:00:00Z", text)
        self.assertIn("2330\thigh\twarning\tvaluation\tvaluation-unavailable\tCheck valuation.", text)
        self.assertIn("9999\tignored\told-action\t2026-05-15T10:00:00Z\tobsolete", text)

    def test_main_research_action_report_defaults_state_file(self):
        root = Path(".tmp-cli-test/research-action-report-default")
        root.mkdir(parents=True, exist_ok=True)
        summary_path = root / "research_summary.json"
        state_path = root / "review_action_state.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "deferred",
                            "updated_at": "2026-05-15T09:00:00Z",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "report", str(summary_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("by_status: open=1 done=0 deferred=1 ignored=0", output.getvalue())

    def test_main_research_action_report_warns_for_invalid_state(self):
        root = Path(".tmp-cli-test")
        summary_path = root / "research-action-report-invalid-summary.json"
        state_path = root / "review_action_report_invalid.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text("{", encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "report",
                str(summary_path),
                "--state",
                str(state_path),
            ])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Warning: Could not read review action state", text)
        self.assertIn("by_status: open=2 done=0 deferred=0 ignored=0", text)
        self.assertIn("stale_state: 0", text)

    def test_main_research_action_prune_stale_dry_run_does_not_write(self):
        root = Path(".tmp-cli-test")
        summary_path = root / "research-action-prune-summary.json"
        state_path = root / "review_action_prune_state.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_text = json.dumps(_review_action_state_with_stale_payload(), indent=2)
        state_path.write_text(state_text, encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "prune-stale",
                str(summary_path),
                "--state",
                str(state_path),
            ])

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(state_path.read_text(encoding="utf-8"), state_text)
        self.assertIn("stale_state: 1", text)
        self.assertIn("mode: dry-run", text)
        self.assertIn("9999\tignored\told-action\t2026-05-15T10:00:00Z\tobsolete", text)

    def test_main_research_action_prune_stale_write_removes_stale_entries(self):
        root = Path(".tmp-cli-test/research-action-prune-write")
        root.mkdir(parents=True, exist_ok=True)
        summary_path = root / "research-action-prune-write-summary.json"
        state_path = root / "review_action_prune_write_state.json"
        for backup in root.glob("review_action_prune_write_state.json.bak-*"):
            backup.unlink()
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        original_text = json.dumps(_review_action_state_with_stale_payload(), indent=2)
        state_path.write_text(original_text, encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "prune-stale",
                str(summary_path),
                "--state",
                str(state_path),
                "--write",
            ])

        state = json.loads(state_path.read_text(encoding="utf-8"))
        backups = list(root.glob("review_action_prune_write_state.json.bak-*"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original_text)
        self.assertIn(f"Backup review action state: {backups[0]}", output.getvalue())
        self.assertIn("Pruned 1 stale review action state entries", output.getvalue())
        self.assertEqual(list(state["actions"]), ["2330:workflow-error"])
        self.assertEqual(state["actions"]["2330:workflow-error"]["status"], "done")

    def test_main_research_action_prune_stale_defaults_state_file(self):
        root = Path(".tmp-cli-test/research-action-prune-default")
        root.mkdir(parents=True, exist_ok=True)
        summary_path = root / "research_summary.json"
        state_path = root / "review_action_state.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text(json.dumps(_review_action_state_with_stale_payload()), encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["research", "action", "prune-stale", str(summary_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("stale_state: 1", output.getvalue())

    def test_main_research_action_prune_stale_no_stale_and_missing_state(self):
        root = Path(".tmp-cli-test")
        summary_path = root / "research-action-prune-empty-summary.json"
        state_path = root / "review_action_prune_empty_state.json"
        missing_state_path = root / "review_action_prune_missing_state.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "done",
                            "updated_at": "2026-05-15T09:00:00Z",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        if missing_state_path.exists():
            missing_state_path.unlink()

        no_stale_output = StringIO()
        with redirect_stdout(no_stale_output):
            no_stale_exit_code = main([
                "research",
                "action",
                "prune-stale",
                str(summary_path),
                "--state",
                str(state_path),
                "--write",
            ])
        missing_output = StringIO()
        with redirect_stdout(missing_output):
            missing_exit_code = main([
                "research",
                "action",
                "prune-stale",
                str(summary_path),
                "--state",
                str(missing_state_path),
                "--write",
            ])

        self.assertEqual(no_stale_exit_code, 0)
        self.assertIn("Pruned 0 stale review action state entries", no_stale_output.getvalue())
        self.assertEqual(missing_exit_code, 0)
        self.assertIn("Pruned 0 stale review action state entries", missing_output.getvalue())
        self.assertFalse(missing_state_path.exists())

    def test_main_research_action_prune_stale_invalid_state_returns_one_without_writing(self):
        root = Path(".tmp-cli-test")
        summary_path = root / "research-action-prune-invalid-summary.json"
        state_path = root / "review_action_prune_invalid.json"
        summary_path.write_text(json.dumps(_review_action_summary_payload()), encoding="utf-8")
        state_path.write_text("{", encoding="utf-8")

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "research",
                "action",
                "prune-stale",
                str(summary_path),
                "--state",
                str(state_path),
                "--write",
            ])

        self.assertEqual(exit_code, 1)
        self.assertEqual(state_path.read_text(encoding="utf-8"), "{")
        self.assertIn("Warning: Could not read review action state", output.getvalue())

    def test_main_research_action_set_rejects_invalid_status(self):
        with self.assertRaises(SystemExit) as context:
            main([
                "research",
                "action",
                "set",
                ".tmp-cli-test/review_action_state_invalid.json",
                "2330",
                "workflow-error",
                "--status",
                "bad",
            ])

        self.assertEqual(context.exception.code, 2)

    def test_main_research_run_writes_workflow_and_research_summary(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "research-run-fixtures"
        output_dir = root / "research-run-dist"
        research = root / "research-run.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,Alpha,Semiconductor,medium,watching,Track valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "run",
            str(research),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--offline-prices",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "research_watchlist.csv").exists())
        self.assertTrue((output_dir / "workflow_summary.json").exists())
        self.assertTrue((output_dir / "research_summary.json").exists())
        summary = json.loads((output_dir / "research_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["items"][0]["stock_id"], "2330")
        self.assertEqual(summary["items"][0]["workflow_status"], "ok")

    def test_main_research_run_examples_offline_demo_writes_full_outputs(self):
        output_dir = Path(".tmp-cli-test/offline-demo-dist")

        exit_code = main([
            "research",
            "run",
            "examples/research.csv",
            "--fixture-root",
            "examples/fixtures",
            "--output-dir",
            str(output_dir),
            "--offline-prices",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "dashboard.html").exists())
        self.assertTrue((output_dir / "workflow_summary.json").exists())
        self.assertTrue((output_dir / "research_summary.json").exists())
        self.assertTrue((output_dir / "memos" / "memo_summary.json").exists())
        self.assertTrue((output_dir / "packs" / "pack_summary.json").exists())
        self.assertTrue((output_dir / "comparison" / "comparison.json").exists())
        self.assertTrue((output_dir / "comparison" / "comparison.html").exists())
        self.assertIn("Review Actions", (output_dir / "dashboard.html").read_text(encoding="utf-8"))

    def test_main_research_run_writes_memos_by_default(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "research-run-memos-fixtures"
        output_dir = root / "research-run-memos-dist"
        research = root / "research-run-memos.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,Alpha,Semiconductor,medium,watching,Track valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "run",
            str(research),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--offline-prices",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "memos" / "2330_memo.md").exists())
        self.assertTrue((output_dir / "memos" / "2330_memo.html").exists())
        summary = json.loads((output_dir / "memos" / "memo_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["generated"][0]["stock_id"], "2330")

    def test_main_research_run_writes_packs_by_default(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "research-run-packs-fixtures"
        output_dir = root / "research-run-packs-dist"
        research = root / "research-run-packs.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,Alpha,Semiconductor,medium,watching,Track valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "run",
            str(research),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--offline-prices",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "packs" / "pack_summary.json").exists())
        self.assertTrue((output_dir / "packs" / "research-pack.md").exists())
        self.assertTrue((output_dir / "packs" / "research-pack.html").exists())

    def test_main_research_run_skip_memos(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "research-run-skip-memos-fixtures"
        output_dir = root / "research-run-skip-memos-dist"
        research = root / "research-run-skip-memos.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,Alpha,Semiconductor,medium,watching,Track valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "run",
            str(research),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--offline-prices",
            "--skip-memos",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "research_summary.json").exists())
        self.assertFalse((output_dir / "memos" / "memo_summary.json").exists())

    def test_main_research_run_skip_packs(self):
        root = Path(".tmp-cli-test")
        fixture_root = root / "research-run-skip-packs-fixtures"
        output_dir = root / "research-run-skip-packs-dist"
        research = root / "research-run-skip-packs.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,Alpha,Semiconductor,medium,watching,Track valuation\n",
            encoding="utf-8",
        )

        exit_code = main([
            "research",
            "run",
            str(research),
            "--fixture-root",
            str(fixture_root),
            "--output-dir",
            str(output_dir),
            "--offline-prices",
            "--skip-packs",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue((output_dir / "research_summary.json").exists())
        self.assertFalse((output_dir / "packs" / "pack_summary.json").exists())

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


def _memo_analysis_payload():
    return {
        "stock_id": "2330",
        "years": ["2024"],
        "metrics_by_year": {"2024": {"revenue": 1000, "eps": 10}},
        "valuation": {
            "metrics": {"pe": 20},
            "target_prices": {"base": {"target_price": 200}},
            "assumptions": {"normalized_eps": "manual"},
        },
        "scorecard": {"total_score": 80, "confidence": 90, "dimensions": {}},
        "diagnostics": {"issues": []},
        "metadata": {"reliability": []},
    }


def _review_action_summary_payload():
    return {
        "review_action_queue": [
            {
                "stock_id": "2330",
                "priority": "high",
                "actions": [
                    {
                        "id": "workflow-error",
                        "category": "workflow",
                        "severity": "error",
                        "message": "Fix workflow.",
                        "status": "open",
                    },
                    {
                        "id": "valuation-unavailable",
                        "category": "valuation",
                        "severity": "warning",
                        "message": "Check valuation.",
                        "status": "open",
                    },
                ],
            }
        ]
    }


def _review_action_state_with_stale_payload():
    return {
        "version": 1,
        "actions": {
            "2330:workflow-error": {
                "stock_id": "2330",
                "action_id": "workflow-error",
                "status": "done",
                "note": "checked",
                "updated_at": "2026-05-15T09:00:00Z",
            },
            "9999:old-action": {
                "stock_id": "9999",
                "action_id": "old-action",
                "status": "ignored",
                "note": "obsolete",
                "updated_at": "2026-05-15T10:00:00Z",
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
