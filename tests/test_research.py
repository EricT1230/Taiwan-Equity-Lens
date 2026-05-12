import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.research import (
    ALLOWED_PRIORITIES,
    ALLOWED_STATES,
    RESEARCH_COLUMNS,
    build_research_summary,
    load_research_rows,
    write_research_summary,
    write_research_template,
    write_watchlist_from_research,
)


class ResearchTests(unittest.TestCase):
    def test_load_research_rows_applies_defaults(self):
        path = Path(".tmp-research-test/research.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,,,\n",
            encoding="utf-8",
        )

        rows = load_research_rows(path)

        self.assertEqual(rows[0]["stock_id"], "2330")
        self.assertEqual(rows[0]["priority"], "medium")
        self.assertEqual(rows[0]["research_state"], "new")

    def test_load_research_rows_normalizes_and_strips_values(self):
        path = Path(".tmp-research-test/normalized.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            " 2330 , TSMC , Semiconductor , HIGH , REVIEW , Check valuation \n",
            encoding="utf-8",
        )

        rows = load_research_rows(path)

        self.assertEqual(
            rows[0],
            {
                "stock_id": "2330",
                "company_name": "TSMC",
                "category": "Semiconductor",
                "priority": "high",
                "research_state": "review",
                "notes": "Check valuation",
            },
        )

    def test_load_research_rows_rejects_missing_stock_id_column(self):
        path = Path(".tmp-research-test/bad.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text("company_name\nTSMC\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "research CSV must include a stock_id column"):
            load_research_rows(path)

    def test_load_research_rows_rejects_blank_stock_id(self):
        path = Path(".tmp-research-test/blank-stock-id.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            ",TSMC,Semiconductor,high,review,\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "row 2 must include a stock_id"):
            load_research_rows(path)

    def test_load_research_rows_rejects_invalid_state_and_priority(self):
        path = Path(".tmp-research-test/invalid.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,urgent,maybe,\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "priority"):
            load_research_rows(path)

        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,maybe,\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "research_state"):
            load_research_rows(path)

    def test_constants_define_allowed_values(self):
        self.assertEqual(RESEARCH_COLUMNS, ["stock_id", "company_name", "category", "priority", "research_state", "notes"])
        self.assertEqual(ALLOWED_PRIORITIES, {"high", "medium", "low"})
        self.assertEqual(ALLOWED_STATES, {"new", "watching", "review", "done", "blocked"})

    def test_write_research_template_writes_expected_columns_and_samples(self):
        path = Path(".tmp-research-test/template.csv")
        path.parent.mkdir(exist_ok=True)

        write_research_template(path)

        rows = load_research_rows(path)
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertEqual(header, RESEARCH_COLUMNS)
        self.assertEqual([row["stock_id"] for row in rows], ["2330", "2303"])
        self.assertEqual([row["company_name"] for row in rows], ["TSMC", "UMC"])

    def test_write_watchlist_from_research_writes_stock_id_and_company_name(self):
        path = Path(".tmp-research-test/research-watchlist.csv")
        output = Path(".tmp-research-test/watchlist.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Check valuation\n",
            encoding="utf-8",
        )

        write_watchlist_from_research(path, output)

        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "stock_id,company_name\n2330,TSMC\n",
        )

    def test_build_research_summary_without_workflow_marks_skipped(self):
        path = Path(".tmp-research-test/summary-research.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Needs valuation\n",
            encoding="utf-8",
        )

        summary = build_research_summary(path, workflow_dir=Path(".tmp-research-test/missing-workflow"))

        self.assertEqual(summary["counts"]["total"], 1)
        self.assertEqual(summary["counts"]["by_state"], {"review": 1})
        self.assertEqual(summary["counts"]["by_priority"], {"high": 1})
        self.assertEqual(summary["counts"]["needs_attention"], 1)
        self.assertEqual(summary["items"][0]["workflow_status"], "skipped")
        self.assertEqual(summary["items"][0]["reliability_status"], "skipped")
        self.assertIn("research state requires review", summary["items"][0]["attention_reasons"])
        self.assertIn("workflow status is skipped", summary["items"][0]["attention_reasons"])

    def test_build_research_summary_uses_workflow_failures_and_reliability(self):
        root = Path(".tmp-research-test")
        research = root / "summary-with-workflow.csv"
        workflow_dir = root / "workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,medium,watching,\n"
            "9999,Broken,Test,low,blocked,Source failed\n",
            encoding="utf-8",
        )
        (workflow_dir / "workflow_summary.json").write_text(
            json.dumps(
                {
                    "successful_stock_ids": ["2330"],
                    "stock_failures": [
                        {"stock_id": "9999", "stage": "batch", "reason": "fixture missing"}
                    ],
                    "data_reliability": {"overall_status": "warning", "warning": 1, "error": 0},
                    "paths": {"dashboard": "workflow/dashboard.html"},
                }
            ),
            encoding="utf-8",
        )

        summary = build_research_summary(research, workflow_dir=workflow_dir)

        items = {item["stock_id"]: item for item in summary["items"]}
        self.assertEqual(items["2330"]["workflow_status"], "ok")
        self.assertEqual(items["2330"]["reliability_status"], "warning")
        self.assertIn("data reliability is warning", items["2330"]["attention_reasons"])
        self.assertEqual(items["9999"]["workflow_status"], "error")
        self.assertIn("workflow failed at batch: fixture missing", items["9999"]["attention_reasons"])
        self.assertEqual(summary["workflow_paths"], {"dashboard": "workflow/dashboard.html"})

    def test_build_research_summary_treats_invalid_workflow_json_as_skipped(self):
        root = Path(".tmp-research-test")
        research = root / "summary-invalid-workflow.csv"
        workflow_dir = root / "invalid-workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,low,watching,\n",
            encoding="utf-8",
        )
        (workflow_dir / "workflow_summary.json").write_text("{", encoding="utf-8")

        summary = build_research_summary(research, workflow_dir=workflow_dir)

        self.assertEqual(summary["items"][0]["workflow_status"], "skipped")
        self.assertEqual(summary["counts"]["needs_attention"], 1)

    def test_write_research_summary_writes_json(self):
        root = Path(".tmp-research-test")
        research = root / "write-summary.csv"
        output = root / "research_summary.json"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,medium,done,\n",
            encoding="utf-8",
        )

        result = write_research_summary(research, None, output)

        self.assertEqual(result, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["items"][0]["stock_id"], "2330")


if __name__ == "__main__":
    unittest.main()
