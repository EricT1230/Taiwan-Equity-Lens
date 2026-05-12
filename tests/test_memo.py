import json
import shutil
import unittest
from pathlib import Path

from taiwan_stock_analysis.memo import (
    build_memo_context,
    render_memo_html,
    render_memo_markdown,
    write_memo,
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
        self.assertIn("## Research Metadata", markdown)
        self.assertIn("## Data Reliability", markdown)
        self.assertIn("## Latest Metrics Snapshot", markdown)
        self.assertIn("Revenue | 1,000.00", markdown)
        self.assertIn("## Valuation Context", markdown)
        self.assertIn("Target-price scenarios are research scenarios, not recommendations.", markdown)
        self.assertIn("## Quality Scorecard", markdown)
        self.assertIn("## Diagnostics", markdown)
        self.assertIn("- [ ] Review data reliability warning", markdown)
        self.assertIn("## Source Links", markdown)
        self.assertIn("This memo is research workflow support only", markdown)

    def test_render_memo_html_escapes_user_values(self):
        context = {
            **build_memo_context_from_payload(_analysis_payload(), self.tmp_dir),
            "research_item": {"company_name": "<TSMC>", "notes": "<script>alert(1)</script>"},
        }

        html = render_memo_html(context)

        self.assertIn("&lt;TSMC&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

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
