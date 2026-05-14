import json
import unittest
from pathlib import Path

from taiwan_stock_analysis.pack import (
    build_pack_context,
    render_pack_html,
    render_pack_markdown,
    write_research_pack,
)


class ResearchPackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".tmp-pack-test")
        self.root.mkdir(exist_ok=True)

    def test_render_pack_markdown_includes_review_sections_and_disclaimer(self):
        context = build_pack_context(
            self._write_research_summary(),
            research_csv_path=Path("research.csv"),
            workflow_summary_path=self._write_workflow_summary(),
            memo_summary_path=self._write_memo_summary(),
            dashboard_path=Path("research-dist/dashboard.html"),
        )

        markdown = render_pack_markdown(context)

        self.assertIn("# Research Pack", markdown)
        self.assertIn("## Run Overview", markdown)
        self.assertIn("## Reliability Overview", markdown)
        self.assertIn("## Priority Review Queue", markdown)
        self.assertIn("2330 | TSMC | review | high", markdown)
        self.assertIn("## Generated Outputs", markdown)
        self.assertIn("## Per-Stock Research Index", markdown)
        self.assertIn("- [ ] Review warning and error counts before handoff", markdown)
        self.assertIn("This pack is research workflow support only", markdown)

    def test_render_pack_html_escapes_user_values(self):
        research_summary = self._write_research_summary(company_name="<TSMC>")
        context = build_pack_context(research_summary, research_csv_path=Path("research.csv"))

        html = render_pack_html(context)

        self.assertIn("&lt;TSMC&gt;", html)
        self.assertNotIn("<TSMC>", html)

    def test_render_pack_markdown_normalizes_table_cells(self):
        research_summary = self._write_research_summary(company_name="TSMC | Core\nResearch")
        context = build_pack_context(research_summary, research_csv_path=Path("research.csv"))

        markdown = render_pack_markdown(context)

        self.assertIn("TSMC \\| Core Research", markdown)
        self.assertNotIn("TSMC | Core\nResearch", markdown)

    def test_build_pack_context_summarizes_research_quality_coverage(self):
        research_summary = self._write_research_summary(
            extra_items=[
                {
                    "stock_id": "2303",
                    "company_name": "UMC",
                    "priority": "high",
                    "thesis": "",
                    "follow_up_questions": "",
                },
            ]
        )

        context = build_pack_context(research_summary, research_csv_path=Path("research.csv"))

        self.assertEqual(context["research_quality"]["with_thesis"], 1)
        self.assertEqual(context["research_quality"]["with_watch_triggers"], 1)
        self.assertEqual(context["research_quality"]["with_follow_up_questions"], 1)
        self.assertEqual(context["research_quality"]["high_priority_missing_follow_up"], ["2303"])

    def test_render_pack_markdown_includes_research_quality_overview(self):
        context = build_pack_context(self._write_research_summary(), research_csv_path=Path("research.csv"))

        markdown = render_pack_markdown(context)

        self.assertIn("## Research Quality Overview", markdown)
        self.assertIn("With thesis", markdown)
        self.assertIn("Follow-up coverage", markdown)

    def test_build_pack_context_tolerates_missing_optional_inputs(self):
        context = build_pack_context(self._write_research_summary(), research_csv_path=Path("research.csv"))

        self.assertEqual("", context["workflow_summary_path"])
        self.assertEqual("", context["memo_summary_path"])
        self.assertEqual("-", context["items"][0]["memo_markdown_path"])

    def test_build_pack_context_rejects_invalid_research_summary(self):
        path = self.root / "invalid_research_summary.json"
        path.write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid research summary JSON"):
            build_pack_context(path, research_csv_path=Path("research.csv"))

    def test_write_research_pack_writes_markdown_html_and_summary(self):
        output_dir = self.root / "packs"
        summary_path = write_research_pack(
            self._write_research_summary(),
            output_dir,
            research_csv_path=Path("research.csv"),
            workflow_summary_path=self._write_workflow_summary(),
            memo_summary_path=self._write_memo_summary(),
            dashboard_path=Path("research-dist/dashboard.html"),
        )

        self.assertEqual(output_dir / "pack_summary.json", summary_path)
        self.assertTrue((output_dir / "research-pack.md").exists())
        self.assertTrue((output_dir / "research-pack.html").exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual("ok", payload["status"])
        self.assertEqual([], payload["warnings"])

    def test_write_research_pack_inherits_traceability_from_research_summary(self):
        output_dir = self.root / "traceable-packs"
        research_summary_path = self._write_research_summary()
        workflow_summary_path = self._write_workflow_summary()
        memo_summary_path = self._write_memo_summary()

        summary_path = write_research_pack(
            research_summary_path,
            output_dir,
            research_csv_path=Path("research.csv"),
            workflow_summary_path=workflow_summary_path,
            memo_summary_path=memo_summary_path,
        )

        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual("run-20260513-pack", payload["run_metadata"]["run_id"])
        self.assertEqual(str(summary_path), payload["artifact_registry"]["self"])
        self.assertEqual(
            {
                "research_summary": str(research_summary_path),
                "workflow_summary": str(workflow_summary_path),
                "memo_summary": str(memo_summary_path),
            },
            payload["artifact_registry"]["dependencies"],
        )
        self.assertEqual(
            {
                "markdown": str(output_dir / "research-pack.md"),
                "html": str(output_dir / "research-pack.html"),
            },
            payload["artifact_registry"]["outputs"],
        )

    def _write_research_summary(self, company_name="TSMC", extra_items=None):
        path = self.root / "research_summary.json"
        items = [
            {
                "stock_id": "2330",
                "company_name": company_name,
                "research_state": "review",
                "priority": "high",
                "workflow_status": "ok",
                "reliability_status": "warning",
                "attention_reasons": ["data reliability is warning"],
                "thesis": "Leading foundry scale",
                "key_risks": "Cycle downturn",
                "watch_triggers": "Revenue inflection",
                "follow_up_questions": "What drives margin expansion?",
            }
        ]
        if extra_items:
            items.extend(extra_items)
        research_state_counts = {}
        priority_counts = {}
        for item in items:
            research_state = item.get("research_state", "-")
            priority = item.get("priority", "-")
            research_state_counts[research_state] = research_state_counts.get(research_state, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        path.write_text(
            json.dumps(
                {
                    "run_metadata": {
                        "run_id": "run-20260513-pack",
                        "generated_at": "2026-05-13T12:00:00Z",
                        "kind": "research",
                        "command": "research summarize",
                        "inputs": {"workflow_summary": "workflow_summary.json"},
                        "output_root": "research-dist",
                    },
                    "counts": {
                        "total": len(items),
                        "needs_attention": sum(1 for item in items if item.get("attention_reasons")),
                    },
                    "research_state_counts": research_state_counts,
                    "priority_counts": priority_counts,
                    "items": items,
                }
            ),
            encoding="utf-8",
        )
        return path

    def _write_workflow_summary(self):
        path = self.root / "workflow_summary.json"
        path.write_text(
            json.dumps({"data_reliability": {"ok": 1, "warning": 1, "error": 0, "skipped": 0}}),
            encoding="utf-8",
        )
        return path

    def _write_memo_summary(self):
        path = self.root / "memo_summary.json"
        path.write_text(
            json.dumps(
                {
                    "generated": [
                        {
                            "stock_id": "2330",
                            "markdown_path": "research-dist/memos/2330_memo.md",
                            "html_path": "research-dist/memos/2330_memo.html",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path
