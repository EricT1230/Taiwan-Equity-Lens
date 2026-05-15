import json
import unittest
from pathlib import Path

import taiwan_stock_analysis.research as research_module
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
                "thesis": "",
                "key_risks": "",
                "watch_triggers": "",
                "follow_up_questions": "",
            },
        )

    def test_load_research_rows_reads_research_quality_fields(self):
        path = Path(".tmp-research-test/research-quality.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes,thesis,key_risks,watch_triggers,follow_up_questions\n"
            "2330,TSMC,Semiconductor,high,review,Review valuation,Leading foundry scale,FX and cycle risk,Monthly revenue inflection,What drives next margin step?\n",
            encoding="utf-8",
        )

        rows = load_research_rows(path)

        self.assertEqual(rows[0]["thesis"], "Leading foundry scale")
        self.assertEqual(rows[0]["key_risks"], "FX and cycle risk")
        self.assertEqual(rows[0]["watch_triggers"], "Monthly revenue inflection")
        self.assertEqual(rows[0]["follow_up_questions"], "What drives next margin step?")

    def test_load_research_rows_defaults_missing_research_quality_fields(self):
        path = Path(".tmp-research-test/legacy-research.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2303,UMC,Semiconductor,medium,watching,Track warnings\n",
            encoding="utf-8",
        )

        rows = load_research_rows(path)

        self.assertEqual(rows[0]["thesis"], "")
        self.assertEqual(rows[0]["key_risks"], "")
        self.assertEqual(rows[0]["watch_triggers"], "")
        self.assertEqual(rows[0]["follow_up_questions"], "")

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
        self.assertEqual(
            RESEARCH_COLUMNS,
            [
                "stock_id",
                "company_name",
                "category",
                "priority",
                "research_state",
                "notes",
                "thesis",
                "key_risks",
                "watch_triggers",
                "follow_up_questions",
            ],
        )
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

    def test_build_research_summary_includes_source_audit_from_workflow(self):
        root = Path(".tmp-research-test")
        research = root / "summary-source-audit.csv"
        workflow_dir = root / "source-audit-workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,medium,watching,\n",
            encoding="utf-8",
        )
        source_audit = {
            "status": "manual_review",
            "counts": {"fresh": 0, "stale": 0, "unknown": 0, "manual_review": 1},
            "items": [
                {
                    "stock_id": "2330",
                    "status": "manual_review",
                    "financial_statement": {
                        "review_reason": " fixture source ",
                        "reason": {"bad": True},
                    },
                    "price": {"review_reason": "fixture source", "reason": ["bad"]},
                }
            ],
        }
        (workflow_dir / "workflow_summary.json").write_text(
            json.dumps({"successful_stock_ids": ["2330"], "source_audit": source_audit}),
            encoding="utf-8",
        )

        summary = build_research_summary(research, workflow_dir=workflow_dir)

        item = summary["items"][0]
        self.assertEqual(source_audit, summary["source_audit"])
        self.assertEqual("manual_review", item["source_audit_status"])
        self.assertEqual(["fixture source"], item["source_audit_reasons"])

    def test_build_research_summary_adds_review_actions_and_queue(self):
        root = Path(".tmp-research-test")
        research = root / "summary-review-actions.csv"
        workflow_dir = root / "review-actions-workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,thesis,key_risks,watch_triggers,follow_up_questions\n"
            "2330,TSMC,Semiconductor,high,review,Needs review,,FX risk,Revenue trigger,\n"
            "2303,UMC,Semiconductor,medium,watching,Track warnings,UMC thesis,,Utilization?,What margin is assumed?\n",
            encoding="utf-8",
        )
        (workflow_dir / "workflow_summary.json").write_text(
            json.dumps(
                {
                    "successful_stock_ids": ["2330", "2303"],
                    "data_reliability": {"overall_status": "warning", "warning": 1, "error": 0},
                    "step_statuses": {"valuation": {"status": "warning"}},
                    "source_audit": {
                        "status": "manual_review",
                        "items": [
                            {
                                "stock_id": "2330",
                                "status": "manual_review",
                                "financial_statement": {"review_reason": "fixture source requires manual review"},
                                "price": {"review_reason": "offline mode"},
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        summary = build_research_summary(research, workflow_dir=workflow_dir)

        items = {item["stock_id"]: item for item in summary["items"]}
        item_2330_action_ids = [action["id"] for action in items["2330"]["review_actions"]]
        self.assertIn("source-audit-manual-review", item_2330_action_ids)
        self.assertIn("research-quality-missing-thesis", item_2330_action_ids)
        self.assertIn("research-quality-missing-follow-up", item_2330_action_ids)
        self.assertEqual(summary["review_action_summary"]["total_open"], 9)
        self.assertEqual(summary["review_action_summary"]["by_category"]["source_audit"], 2)
        self.assertEqual(summary["review_action_summary"]["by_severity"]["unknown"], 1)
        self.assertEqual(summary["review_action_queue"][0]["stock_id"], "2303")
        self.assertEqual(summary["review_action_queue"][0]["actions"][0]["id"], "source-audit-unknown")

    def test_build_research_summary_review_actions_handles_missing_workflow(self):
        path = Path(".tmp-research-test/review-actions-no-workflow.csv")
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,medium,watching,\n",
            encoding="utf-8",
        )

        summary = build_research_summary(
            path,
            workflow_dir=Path(".tmp-research-test/missing-review-action-workflow"),
        )

        actions = summary["items"][0]["review_actions"]
        self.assertEqual(actions[0]["id"], "valuation-unavailable")
        self.assertEqual(actions[1]["id"], "workflow-skipped")
        self.assertEqual(actions[1]["category"], "workflow")
        self.assertEqual(actions[1]["severity"], "info")
        self.assertEqual(summary["review_action_summary"]["total_open"], 2)

    def test_build_research_summary_includes_universe_review_counts_and_buckets(self):
        root = Path(".tmp-research-test")
        research = root / "summary-universe-review.csv"
        workflow_dir = root / "universe-review-workflow"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,high,review,Needs final review\n"
            "2303,UMC,Semiconductor,medium,watching,\n"
            "9999,Broken,,high,blocked,Source failed\n"
            "1111,NewCo,Finance,low,new,Add notes\n",
            encoding="utf-8",
        )
        (workflow_dir / "workflow_summary.json").write_text(
            json.dumps(
                {
                    "successful_stock_ids": ["2330", "2303", "1111"],
                    "stock_failures": [
                        {"stock_id": "9999", "stage": "batch", "reason": "fixture missing"}
                    ],
                    "data_reliability": {"overall_status": "ok"},
                    "paths": {"valuation_batch_summary": "workflow/valuation.json"},
                }
            ),
            encoding="utf-8",
        )

        summary = build_research_summary(research, workflow_dir=workflow_dir)

        self.assertIn("universe_review", summary)
        review = summary["universe_review"]
        self.assertEqual(
            review["category_counts"],
            {"Finance": 1, "Semiconductor": 2, "Uncategorized": 1},
        )
        self.assertEqual(
            review["counts"],
            {
                "total": 4,
                "needs_attention": 3,
                "high_priority_attention": 2,
                "blocked": 1,
                "new": 1,
                "active_review": 1,
            },
        )
        self.assertEqual(review["state_counts"], {"blocked": 1, "new": 1, "review": 1, "watching": 1})
        self.assertEqual(review["priority_counts"], {"high": 2, "low": 1, "medium": 1})
        self.assertEqual(review["review_buckets"]["needs_attention"], ["1111", "2330", "9999"])
        self.assertEqual(review["review_buckets"]["high_priority_attention"], ["2330", "9999"])
        self.assertEqual(review["review_buckets"]["blocked"], ["9999"])
        self.assertEqual(review["review_buckets"]["new"], ["1111"])
        self.assertEqual(review["review_buckets"]["active_review"], ["2330"])

    def test_build_universe_review_sorts_attention_queue_by_status_priority_and_stock_id(self):
        builder = getattr(research_module, "build_universe_review", None)
        self.assertIsNotNone(builder)

        review = builder(
            [
                {
                    "stock_id": "3001",
                    "company_name": "Low Error",
                    "category": "Test",
                    "priority": "low",
                    "research_state": "watching",
                    "workflow_status": "error",
                    "attention_reasons": ["workflow failed"],
                },
                {
                    "stock_id": "2001",
                    "company_name": "High Warning",
                    "category": "Test",
                    "priority": "high",
                    "research_state": "watching",
                    "workflow_status": "warning",
                    "attention_reasons": ["workflow status is warning"],
                },
                {
                    "stock_id": "1001",
                    "company_name": "High OK",
                    "category": "Test",
                    "priority": "high",
                    "research_state": "review",
                    "workflow_status": "ok",
                    "attention_reasons": ["research state requires review"],
                },
            ]
        )

        self.assertEqual(
            [item["stock_id"] for item in review["attention_queue"]],
            ["3001", "2001", "1001"],
        )

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

    def test_write_research_summary_inherits_workflow_traceability(self):
        root = Path(".tmp-research-test")
        research = root / "traceable-research.csv"
        workflow_dir = root / "traceable-workflow"
        output = root / "traceable-research-summary.json"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes\n"
            "2330,TSMC,Semiconductor,medium,done,\n",
            encoding="utf-8",
        )
        workflow_summary_path = workflow_dir / "workflow_summary.json"
        workflow_summary_path.write_text(
            json.dumps(
                {
                    "run_metadata": {
                        "run_id": "run-20260513-research",
                        "generated_at": "2026-05-13T12:00:00Z",
                        "kind": "workflow",
                        "command": "workflow run",
                        "inputs": {"watchlist": "watchlist.csv"},
                        "output_root": str(workflow_dir),
                    }
                }
            ),
            encoding="utf-8",
        )

        write_research_summary(research, workflow_dir, output)

        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("run-20260513-research", payload["run_metadata"]["run_id"])
        self.assertEqual(str(output), payload["artifact_registry"]["self"])
        self.assertEqual(
            {"workflow_summary": str(workflow_summary_path)},
            payload["artifact_registry"]["dependencies"],
        )


if __name__ == "__main__":
    unittest.main()
