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

    def _write_research_summary(self, company_name="TSMC"):
        path = self.root / "research_summary.json"
        path.write_text(
            json.dumps(
                {
                    "counts": {"total": 2, "needs_attention": 1},
                    "research_state_counts": {"review": 1, "monitor": 1},
                    "priority_counts": {"high": 1, "medium": 1},
                    "items": [
                        {
                            "stock_id": "2330",
                            "company_name": company_name,
                            "research_state": "review",
                            "priority": "high",
                            "workflow_status": "ok",
                            "reliability_status": "warning",
                            "attention_reasons": ["data reliability is warning"],
                        },
                        {
                            "stock_id": "2303",
                            "company_name": "UMC",
                            "research_state": "monitor",
                            "priority": "medium",
                            "workflow_status": "warning",
                            "reliability_status": "ok",
                            "attention_reasons": [],
                        },
                    ],
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
