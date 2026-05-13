import json
import shutil
import unittest
from pathlib import Path

from taiwan_stock_analysis.memo import (
    build_memo_context,
    render_memo_html,
    render_memo_markdown,
    write_memo,
    write_research_memos,
)


class MemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(".tmp-memo-test")
        self.tmp_dir.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_render_memo_markdown_includes_sections_and_disclaimer(self):
        analysis_path = self.tmp_dir / "2330_raw_data.json"
        analysis_path.write_text(json.dumps(_analysis_payload()), encoding="utf-8")

        context = build_memo_context(
            analysis_path,
            research_item={
                "stock_id": "2330",
                "company_name": "TSMC",
                "category": "Semiconductor",
                "priority": "high",
                "research_state": "review",
                "notes": "Check assumptions",
                "workflow_status": "ok",
                "reliability_status": "warning",
                "attention_reasons": ["data reliability is warning"],
            },
            report_path=Path("dist/2330_analysis.html"),
            workflow_summary_path=Path("workflow_summary.json"),
            research_summary_path=Path("research_summary.json"),
        )

        markdown = render_memo_markdown(context)

        self.assertIn("# Research Memo: TSMC (2330)", markdown)
        self.assertIn("## Executive Summary", markdown)
        self.assertIn("## Research Metadata", markdown)
        self.assertIn("## Key Observations", markdown)
        self.assertIn("## Catalysts", markdown)
        self.assertIn("## Risks", markdown)
        self.assertIn("## Open Questions", markdown)
        self.assertIn("## Data Reliability", markdown)
        self.assertIn("## Latest Metrics Snapshot", markdown)
        self.assertIn("Revenue | 1,000.00", markdown)
        self.assertIn("## Valuation Context", markdown)
        self.assertIn("Target-price scenarios are research scenarios, not recommendations.", markdown)
        self.assertIn("## Quality Scorecard", markdown)
        self.assertIn("## Diagnostics", markdown)
        self.assertIn("## Next Research Actions", markdown)
        self.assertIn("### Data Checks", markdown)
        self.assertIn("### Valuation Checks", markdown)
        self.assertIn("### Thesis Checks", markdown)
        self.assertIn("- [ ] Review data reliability warning", markdown)
        self.assertIn("## Source Links", markdown)
        self.assertIn("This memo is research workflow support only", markdown)

    def test_render_memo_markdown_surfaces_risks_questions_and_actions(self):
        payload = _analysis_payload()
        payload["valuation"]["assumptions"] = {}
        context = {
            **build_memo_context_from_payload(payload, self.tmp_dir),
            "research_item": {
                "stock_id": "2330",
                "company_name": "TSMC",
                "research_state": "review",
                "reliability_status": "warning",
                "attention_reasons": ["manual follow-up"],
            },
        }

        markdown = render_memo_markdown(context)

        self.assertIn("## Risks", markdown)
        self.assertIn("Diagnostics reported", markdown)
        self.assertIn("Valuation assumptions need manual review.", markdown)
        self.assertIn("## Open Questions", markdown)
        self.assertIn("What data issue caused the current warning state?", markdown)
        self.assertIn("### Valuation Checks", markdown)

    def test_render_memo_markdown_uses_empty_states_when_optional_context_missing(self):
        payload = {"stock_id": "2330", "years": []}
        context = build_memo_context_from_payload(payload, self.tmp_dir)

        markdown = render_memo_markdown(context)

        self.assertIn("## Executive Summary", markdown)
        self.assertIn("-", markdown)
        self.assertIn("## Catalysts", markdown)
        self.assertIn("## Risks", markdown)

    def test_render_memo_html_escapes_user_values(self):
        context = {
            **build_memo_context_from_payload(_analysis_payload(), self.tmp_dir),
            "research_item": {"company_name": "<TSMC>", "notes": "<script>alert(1)</script>"},
        }

        html = render_memo_html(context)

        self.assertIn("&lt;TSMC&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("<h2>Executive Summary</h2>", html)
        self.assertIn("<h2>Key Observations</h2>", html)
        self.assertIn("<h2>Catalysts</h2>", html)
        self.assertIn("<h2>Risks</h2>", html)
        self.assertIn("<h2>Open Questions</h2>", html)
        self.assertIn("<h2>Next Research Actions</h2>", html)

    def test_render_memo_sections_follow_review_order(self):
        context = build_memo_context_from_payload(_analysis_payload(), self.tmp_dir)

        markdown = render_memo_markdown(context)
        html = render_memo_html(context)

        markdown_sections = [
            "## Executive Summary",
            "## Research Metadata",
            "## Key Observations",
            "## Catalysts",
            "## Risks",
            "## Open Questions",
            "## Latest Metrics Snapshot",
            "## Valuation Context",
            "## Quality Scorecard",
            "## Diagnostics",
            "## Next Research Actions",
            "## Source Links",
            "## Disclaimer",
        ]
        html_sections = [
            "<h2>Executive Summary</h2>",
            "<h2>Research Metadata</h2>",
            "<h2>Key Observations</h2>",
            "<h2>Catalysts</h2>",
            "<h2>Risks</h2>",
            "<h2>Open Questions</h2>",
            "<h2>Latest Metrics Snapshot</h2>",
            "<h2>Valuation Context</h2>",
            "<h2>Quality Scorecard</h2>",
            "<h2>Diagnostics</h2>",
            "<h2>Next Research Actions</h2>",
            "<h2>Source Links</h2>",
            "<h2>Disclaimer</h2>",
        ]

        self.assertEqual(sorted(markdown.find(section) for section in markdown_sections), [markdown.find(section) for section in markdown_sections])
        self.assertEqual(sorted(html.find(section) for section in html_sections), [html.find(section) for section in html_sections])

    def test_render_memo_markdown_escapes_html_and_normalizes_table_cells(self):
        payload = _analysis_payload()
        payload["diagnostics"] = {"issues": [{"level": "warning", "message": "<img src=x onerror=alert(1)>"}]}
        context = {
            **build_memo_context_from_payload(payload, self.tmp_dir),
            "research_item": {
                "stock_id": "2330",
                "company_name": "<TSMC>",
                "notes": "line one\nline two | with pipe",
                "attention_reasons": ["review <source>"],
            },
            "analysis_path": "memos/<raw>.json",
        }

        markdown = render_memo_markdown(context)

        self.assertIn("# Research Memo: &lt;TSMC&gt; (2330)", markdown)
        self.assertIn("line one line two \\| with pipe", markdown)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", markdown)
        self.assertIn("review &lt;source&gt;", markdown)
        self.assertIn("memos/&lt;raw&gt;.json", markdown)
        self.assertNotIn("<img src=x onerror=alert(1)>", markdown)

    def test_write_memo_writes_markdown_and_html(self):
        analysis_path = self.tmp_dir / "write_raw_data.json"
        markdown_path = self.tmp_dir / "write_memo.md"
        html_path = self.tmp_dir / "write_memo.html"
        analysis_path.write_text(json.dumps(_analysis_payload()), encoding="utf-8")

        markdown_result = write_memo(analysis_path, markdown_path, output_format="markdown")
        html_result = write_memo(analysis_path, html_path, output_format="html")

        self.assertEqual(markdown_path, markdown_result)
        self.assertEqual(html_path, html_result)
        self.assertIn("# Research Memo", markdown_path.read_text(encoding="utf-8"))
        self.assertIn("<!DOCTYPE html>", html_path.read_text(encoding="utf-8"))

    def test_build_memo_context_rejects_invalid_json(self):
        path = self.tmp_dir / "invalid.json"
        path.write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid analysis JSON"):
            build_memo_context(path)

    def test_write_research_memos_writes_outputs_and_summary(self):
        workflow_dir = self.tmp_dir / "workflow"
        reports_dir = workflow_dir / "reports"
        valuation_reports_dir = workflow_dir / "valuation-reports"
        output_dir = workflow_dir / "memos"
        reports_dir.mkdir(parents=True)
        valuation_reports_dir.mkdir(parents=True)
        (reports_dir / "2330_raw_data.json").write_text(json.dumps(_analysis_payload()), encoding="utf-8")
        fallback_payload = _analysis_payload()
        fallback_payload["stock_id"] = "2303"
        (valuation_reports_dir / "2303_raw_data.json").write_text(json.dumps(fallback_payload), encoding="utf-8")
        research_summary = workflow_dir / "research_summary.json"
        research_summary.write_text(
            json.dumps(
                {
                    "items": [
                        {"stock_id": "2330", "company_name": "TSMC", "research_state": "review"},
                        {"stock_id": "2303", "company_name": "UMC", "research_state": "watching"},
                        {"stock_id": "9999", "company_name": "Missing", "research_state": "new"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary_path = write_research_memos(research_summary, workflow_dir, output_dir)

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary_path, output_dir / "memo_summary.json")
        self.assertTrue((output_dir / "2330_memo.md").exists())
        self.assertTrue((output_dir / "2330_memo.html").exists())
        self.assertTrue((output_dir / "2303_memo.md").exists())
        self.assertTrue((output_dir / "2303_memo.html").exists())
        self.assertEqual(["2330", "2303"], [item["stock_id"] for item in summary["generated"]])
        self.assertEqual([{"stock_id": "9999", "reason": "analysis JSON not found"}], summary["skipped"])
        self.assertIn("markdown_path", summary["generated"][0])
        self.assertIn("html_path", summary["generated"][0])

    def test_write_research_memos_inherits_research_traceability(self):
        workflow_dir = self.tmp_dir / "traceable-workflow"
        reports_dir = workflow_dir / "reports"
        output_dir = workflow_dir / "memos"
        reports_dir.mkdir(parents=True)
        (reports_dir / "2330_raw_data.json").write_text(json.dumps(_analysis_payload()), encoding="utf-8")
        workflow_summary_path = workflow_dir / "workflow_summary.json"
        research_summary_path = workflow_dir / "research_summary.json"
        research_summary_path.write_text(
            json.dumps(
                {
                    "run_metadata": {
                        "run_id": "run-20260513-memo",
                        "generated_at": "2026-05-13T12:00:00Z",
                        "kind": "research",
                        "command": "research summarize",
                        "inputs": {"workflow_summary": str(workflow_summary_path)},
                        "output_root": str(workflow_dir),
                    },
                    "items": [{"stock_id": "2330", "company_name": "TSMC", "research_state": "review"}],
                }
            ),
            encoding="utf-8",
        )

        summary_path = write_research_memos(research_summary_path, workflow_dir, output_dir)

        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual("run-20260513-memo", payload["run_metadata"]["run_id"])
        self.assertEqual(str(summary_path), payload["artifact_registry"]["self"])
        self.assertEqual(
            {
                "workflow_summary": str(workflow_summary_path),
                "research_summary": str(research_summary_path),
            },
            payload["artifact_registry"]["dependencies"],
        )
        self.assertEqual(
            {
                "markdown": [str(output_dir / "2330_memo.md")],
                "html": [str(output_dir / "2330_memo.html")],
            },
            payload["artifact_registry"]["outputs"],
        )


def _analysis_payload():
    return {
        "stock_id": "2330",
        "years": ["2024"],
        "metrics_by_year": {
            "2024": {
                "revenue": 1000,
                "gross_margin": 50,
                "net_margin": 25,
                "roe": 30,
                "eps": 10,
                "debt_to_equity": 20,
                "free_cash_flow_margin": 15,
            }
        },
        "valuation": {
            "metrics": {"pe": 20, "pb": 5, "dividend_yield": 2},
            "target_prices": {
                "base": {"eps": 10, "target_pe": 20, "target_price": 200, "price_gap_percent": 5}
            },
            "assumptions": {"normalized_eps": "derived from latest EPS"},
        },
        "scorecard": {
            "total_score": 78,
            "confidence": 90,
            "dimensions": {
                "profitability": {"label": "Profitability", "score": 80, "confidence": 90}
            },
        },
        "diagnostics": {"issues": [{"level": "warning", "message": "Missing dividend"}]},
        "metadata": {
            "reliability": [
                {"stage": "price", "status": "warning", "message": "offline mode", "retry_hint": "rerun later"}
            ]
        },
    }


def build_memo_context_from_payload(payload, tmp_dir):
    path = tmp_dir / "context_raw_data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return build_memo_context(path)
