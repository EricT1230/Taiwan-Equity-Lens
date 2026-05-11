import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.workflow import run_watchlist_workflow


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


class WorkflowTests(unittest.TestCase):
    def test_run_watchlist_workflow_writes_outputs_and_uses_valuation_csv(self):
        root = Path(".tmp-workflow-test")
        fixture_root = root / "fixtures"
        output_dir = root / "workflow-dist"
        watchlist = root / "watchlist.csv"
        valuation_csv = root / "valuation-inputs.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        self._write_fixture(fixture_root / "2303", revenue=800, gross_profit=320, net_income=160)
        watchlist.write_text("stock_id,company_name\n2330,Alpha\n2303,Beta\n", encoding="utf-8")
        valuation_csv.write_text(
            "stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high\n"
            "2330,100,50,2,10,8,12,16\n"
            "2303,80,40,1.5,8,8,12,16\n",
            encoding="utf-8",
        )

        summary_path = run_watchlist_workflow(
            watchlist,
            output_dir,
            fixture_root=fixture_root,
            offline_prices=True,
            valuation_csv=valuation_csv,
        )

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        dashboard_html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
        valuation_data = json.loads(
            (output_dir / "valuation-reports" / "2330_raw_data.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["successful_stock_ids"], ["2330", "2303"])
        self.assertEqual(summary["paths"]["valuation_csv"], str(valuation_csv))
        self.assertFalse(summary["generated_valuation_template"])
        self.assertEqual(summary["step_statuses"]["batch"]["status"], "ok")
        self.assertEqual(summary["step_statuses"]["valuation"]["status"], "ok")
        self.assertEqual(summary["step_statuses"]["comparison"]["status"], "ok")
        self.assertEqual(summary["step_statuses"]["dashboard"]["status"], "ok")
        self.assertEqual(summary["data_reliability"]["overall_status"], "ok")
        self.assertEqual(summary["stock_failures"], [])
        self.assertTrue((output_dir / "reports" / "batch_summary.json").exists())
        self.assertTrue((output_dir / "valuation-reports" / "batch_summary.json").exists())
        self.assertTrue((output_dir / "comparison" / "comparison.json").exists())
        self.assertTrue((output_dir / "comparison" / "comparison.html").exists())
        self.assertTrue((output_dir / "dashboard.html").exists())
        self.assertEqual(valuation_data["valuation"]["metrics"]["pe"], 10.0)
        self.assertIn('href="workflow_summary.json"', dashboard_html)
        self.assertIn(str(watchlist), dashboard_html)
        self.assertIn("valuation-inputs.csv", dashboard_html)
        self.assertNotIn("workflow-dist/workflow-dist", dashboard_html.replace("\\", "/"))
        self.assertIn("台股基本面儀表板", dashboard_html)
        self.assertNotIn("?啗", dashboard_html)

    def test_run_watchlist_workflow_skips_comparison_when_fewer_than_two_successes(self):
        root = Path(".tmp-workflow-test")
        fixture_root = root / "partial-fixtures"
        output_dir = root / "partial-workflow-dist"
        watchlist = root / "partial-watchlist.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        (fixture_root / "9999").mkdir(parents=True, exist_ok=True)
        watchlist.write_text("stock_id,company_name\n2330,Alpha\n9999,Broken\n", encoding="utf-8")

        summary_path = run_watchlist_workflow(
            watchlist,
            output_dir,
            fixture_root=fixture_root,
            offline_prices=True,
        )

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        valuation_text = (output_dir / "valuation.csv").read_text(encoding="utf-8")
        self.assertEqual(summary["successful_stock_ids"], ["2330"])
        self.assertEqual(summary["comparison_skipped_reason"], "fewer than two successful stocks")
        self.assertEqual(summary["step_statuses"]["batch"]["status"], "warning")
        self.assertEqual(summary["step_statuses"]["valuation"]["status"], "warning")
        self.assertEqual(summary["step_statuses"]["comparison"]["status"], "skipped")
        self.assertIn("at least two successful stock reports", summary["step_statuses"]["comparison"]["retry_hint"])
        self.assertEqual(summary["data_reliability"]["overall_status"], "warning")
        self.assertEqual(len(summary["stock_failures"]), 2)
        stock_failure = summary["stock_failures"][0]
        self.assertEqual(stock_failure["stock_id"], "9999")
        self.assertEqual(stock_failure["stage"], "batch")
        self.assertIn("IS_YEAR.html", stock_failure["reason"])
        self.assertEqual(stock_failure["retry_hint"], "Review the workflow summary and rerun the failed step.")
        valuation_failure = summary["stock_failures"][1]
        self.assertEqual(valuation_failure["stock_id"], "9999")
        self.assertEqual(valuation_failure["stage"], "valuation")
        self.assertIn("IS_YEAR.html", valuation_failure["reason"])
        self.assertEqual(
            valuation_failure["retry_hint"],
            "Provide price and assumption fields in the valuation CSV.",
        )
        self.assertTrue((output_dir / "dashboard.html").exists())
        self.assertFalse((output_dir / "comparison" / "comparison.json").exists())
        self.assertIn("offline mode", valuation_text)

    def test_run_watchlist_workflow_cleans_stale_valuation_csv(self):
        root = Path(".tmp-workflow-test")
        fixture_root = root / "cleanup-fixtures"
        output_dir = root / "cleanup-workflow-dist"
        watchlist = root / "cleanup-watchlist.csv"
        self._write_fixture(fixture_root / "2330", revenue=1000, gross_profit=500, net_income=250)
        watchlist.write_text("stock_id,company_name\n2330,Alpha\n", encoding="utf-8")

        run_watchlist_workflow(
            watchlist,
            output_dir,
            fixture_root=fixture_root,
            offline_prices=True,
        )
        self.assertTrue((output_dir / "valuation.csv").exists())

        run_watchlist_workflow(
            watchlist,
            output_dir,
            fixture_root=fixture_root,
            offline_prices=True,
            include_valuation=False,
        )

        self.assertFalse((output_dir / "valuation.csv").exists())
        summary = json.loads((output_dir / "workflow_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["step_statuses"]["valuation"]["status"], "skipped")

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
