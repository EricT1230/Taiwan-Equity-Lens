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
        workflow = root / "workflow"
        invalid_workflow = root / "invalid-workflow"
        reports.mkdir(parents=True, exist_ok=True)
        compare.mkdir(parents=True, exist_ok=True)
        batch.mkdir(parents=True, exist_ok=True)
        workflow.mkdir(parents=True, exist_ok=True)
        invalid_workflow.mkdir(parents=True, exist_ok=True)
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
        (workflow / "workflow_summary.json").write_text(
            json.dumps(
                {
                    "watchlist_path": "watchlist.csv",
                    "stock_ids": ["2330", "2303"],
                    "successful_stock_ids": ["2330"],
                    "paths": {
                        "valuation_csv": "workflow-dist/valuation.csv",
                        "dashboard": "workflow-dist/dashboard.html",
                    },
                    "comparison_skipped_reason": "fewer than two successful stocks",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (invalid_workflow / "workflow_summary.json").write_text("{", encoding="utf-8")

        items = discover_dashboard_items([reports, compare, batch, workflow, invalid_workflow])

        self.assertEqual(items["reports"][0]["stock_id"], "2330")
        self.assertEqual(items["comparisons"][0]["html_path"], str(compare / "comparison.html"))
        self.assertEqual(items["batch_summaries"][0]["results"][1]["status"], "error")
        self.assertEqual(items["workflow_summaries"][0]["path"], str(workflow / "workflow_summary.json"))
        self.assertEqual(items["workflow_summaries"][0]["successful_stock_ids"], ["2330"])
        self.assertEqual(items["workflow_summaries"][1]["error"], "invalid JSON")

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
                "workflow_summaries": [],
            }
        )

        self.assertIn("台股基本面儀表板", html)
        self.assertIn("常用指令", html)
        self.assertIn("2330_analysis.html", html)
        self.assertIn("comparison.html", html)
        self.assertIn("missing fixture", html)
        self.assertIn("失敗", html)
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
                "workflow_summaries": [
                    {
                        "path": "workflow-dist/workflow_summary.json",
                        "watchlist_path": "watchlist.csv",
                        "stock_ids": ["2330", "2303"],
                        "successful_stock_ids": ["2330"],
                        "paths": {
                            "valuation_csv": "workflow-dist/valuation.csv",
                            "dashboard": "workflow-dist/dashboard.html",
                            "comparison": {},
                        },
                        "generated_valuation_template": True,
                        "comparison_skipped_reason": "fewer than two successful stocks",
                        "data_reliability": {
                            "ok": 2,
                            "warning": 1,
                            "error": 1,
                            "skipped": 1,
                            "overall_status": "error",
                        },
                        "stock_failures": [
                            {
                                "stock_id": "2303",
                                "stage": "batch",
                                "reason": "Source fetch failed.",
                                "retry_hint": "Run the workflow again later or use fixture data if the source is unavailable.",
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn("summaryReports", html)
        self.assertIn(">2</strong><span>個股報告</span>", html)
        self.assertIn(">1</strong><span>同業比較</span>", html)
        self.assertIn(">2</strong><span>批次筆數</span>", html)
        self.assertIn(">1</strong><span>失敗筆數</span>", html)
        self.assertIn("compareInput", html)
        self.assertIn("batchPathInput", html)
        self.assertIn("watchlistTemplate", html)
        self.assertIn("data:text/csv", html)
        self.assertIn("python -m taiwan_stock_analysis.cli compare", html)
        self.assertIn("python -m taiwan_stock_analysis.cli batch", html)
        self.assertIn("Workflow 狀態", html)
        self.assertIn("成功 1 / 2", html)
        self.assertIn("同業比較略過", html)
        self.assertIn('class="badge error">同業比較略過', html)
        self.assertIn("workflow-dist/workflow_summary.json", html)
        self.assertIn("workflow-dist/valuation.csv", html)
        self.assertIn("fewer than two successful stocks", html)
        self.assertIn("2330", html)
        self.assertIn("資料可信度", html)
        self.assertIn("overall_status", html)
        self.assertIn("Source fetch failed", html)
        self.assertIn("Run the workflow again later", html)

    def test_render_dashboard_html_shows_clear_empty_states(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
            }
        )

        self.assertIn("尚無個股報告", html)
        self.assertIn("尚無同業比較", html)
        self.assertIn("尚無批次結果", html)
        self.assertIn("尚無 workflow summary", html)

    def test_render_dashboard_html_shows_invalid_workflow_summary_status(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [{"path": "workflow_summary.json", "error": "invalid JSON"}],
            }
        )

        self.assertIn('class="badge error">Workflow summary 錯誤：invalid JSON', html)

    def test_discover_dashboard_items_finds_research_summaries(self):
        root = Path(".tmp-cli-test/dashboard-research")
        valid = root / "valid"
        invalid = root / "invalid"
        non_dict = root / "non-dict"
        valid.mkdir(parents=True, exist_ok=True)
        invalid.mkdir(parents=True, exist_ok=True)
        non_dict.mkdir(parents=True, exist_ok=True)
        (valid / "research_summary.json").write_text(
            json.dumps(
                {
                    "counts": {
                        "total": 2,
                        "needs_attention": 1,
                        "by_state": {"review": 1, "watching": 1},
                        "by_priority": {"high": 1, "medium": 1},
                    },
                    "items": [{"stock_id": "2330", "company_name": "TSMC"}],
                }
            ),
            encoding="utf-8",
        )
        (invalid / "research_summary.json").write_text("{", encoding="utf-8")
        (non_dict / "research_summary.json").write_text("[1, 2]", encoding="utf-8")

        items = discover_dashboard_items([valid, invalid, non_dict])

        self.assertIn("research_summaries", items)
        self.assertEqual(items["research_summaries"][0]["path"], str(valid / "research_summary.json"))
        self.assertEqual(items["research_summaries"][0]["counts"]["total"], 2)
        self.assertEqual(
            items["research_summaries"][1],
            {"path": str(invalid / "research_summary.json"), "error": "invalid JSON"},
        )
        self.assertEqual(
            items["research_summaries"][2],
            {"path": str(non_dict / "research_summary.json"), "error": "invalid JSON"},
        )

    def test_discover_dashboard_items_finds_memo_outputs(self):
        root = Path(".tmp-cli-test/dashboard-memos")
        memos = root / "memos"
        memos.mkdir(parents=True, exist_ok=True)
        (memos / "2330_memo.md").write_text("# Research Memo", encoding="utf-8")
        (memos / "2330_memo.html").write_text("<html>memo</html>", encoding="utf-8")
        (memos / "memo_summary.json").write_text('{"generated": []}', encoding="utf-8")

        items = discover_dashboard_items([root])

        self.assertIn("memo_outputs", items)
        self.assertEqual(
            items["memo_outputs"],
            [
                {
                    "stock_id": "2330",
                    "markdown_path": str(memos / "2330_memo.md"),
                    "html_path": str(memos / "2330_memo.html"),
                    "summary_path": str(memos / "memo_summary.json"),
                }
            ],
        )

    def test_discover_dashboard_items_finds_pack_outputs(self):
        root = Path(".tmp-cli-test/dashboard-packs")
        packs = root / "packs"
        packs.mkdir(parents=True, exist_ok=True)
        (packs / "research-pack.md").write_text("# Research Pack", encoding="utf-8")
        (packs / "research-pack.html").write_text("<html>pack</html>", encoding="utf-8")
        (packs / "pack_summary.json").write_text('{"status": "ok"}', encoding="utf-8")

        items = discover_dashboard_items([root])

        self.assertIn("pack_outputs", items)
        self.assertEqual(
            items["pack_outputs"],
            [
                {
                    "markdown_path": str(packs / "research-pack.md"),
                    "html_path": str(packs / "research-pack.html"),
                    "summary_path": str(packs / "pack_summary.json"),
                }
            ],
        )

    def test_render_dashboard_html_contains_research_summary(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "workflow_summary_path": "research-dist/workflow_summary.json",
                        "workflow_paths": {
                            "batch_summary": "research-dist/reports/batch_summary.json",
                            "valuation_batch_summary": "research-dist/valuation-reports/batch_summary.json",
                            "dashboard": "research-dist/dashboard.html",
                            "comparison": {"html": "research-dist/comparison/comparison.html"},
                        },
                        "counts": {
                            "total": 2,
                            "needs_attention": 1,
                            "by_state": {"review": 1, "watching": 1},
                            "by_priority": {"high": 1, "medium": 1},
                        },
                        "items": [
                            {
                                "stock_id": "2330",
                                "company_name": "TSMC <Leader>",
                                "priority": "high",
                                "research_state": "review",
                                "workflow_status": "ok",
                                "reliability_status": "warning",
                                "attention_reasons": ["research state requires review"],
                            },
                            {
                                "stock_id": "2303",
                                "company_name": "UMC",
                                "priority": "medium",
                                "research_state": "watching",
                                "workflow_status": "skipped",
                                "reliability_status": "skipped",
                                "attention_reasons": [],
                            },
                        ],
                    }
                ],
            }
        )

        self.assertIn("研究工作台", html)
        self.assertIn("needs attention", html)
        self.assertIn("research-dist/workflow_summary.json", html)
        self.assertIn("research-dist/dashboard.html", html)
        self.assertIn("research-dist/reports/batch_summary.json", html)
        self.assertIn("research-dist/valuation-reports/batch_summary.json", html)
        self.assertIn("research-dist/comparison/comparison.html", html)
        self.assertIn("2330", html)
        self.assertIn("TSMC &lt;Leader&gt;", html)
        self.assertIn("review: 1", html)
        self.assertIn("high: 1", html)
        self.assertIn("research state requires review", html)

    def test_render_dashboard_html_shows_research_empty_state(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
            }
        )

        self.assertIn("研究工作台", html)
        self.assertIn("尚無 research summary", html)

    def test_render_dashboard_html_shows_invalid_research_summary(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [{"path": "research_summary.json", "error": "invalid JSON"}],
            }
        )

        self.assertIn("research_summary.json", html)
        self.assertIn("invalid JSON", html)

    def test_render_dashboard_html_contains_memo_outputs(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "memo_outputs": [
                    {
                        "stock_id": "2330",
                        "markdown_path": "research-dist/memos/2330_memo.md",
                        "html_path": "research-dist/memos/2330_memo.html",
                        "summary_path": "research-dist/memos/memo_summary.json",
                    }
                ],
            }
        )

        self.assertIn("Research Memos", html)
        self.assertIn("2330_memo.md", html)
        self.assertIn("2330_memo.html", html)
        self.assertIn("memo_summary.json", html)

    def test_render_dashboard_html_contains_pack_outputs(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "memo_outputs": [],
                "pack_outputs": [
                    {
                        "markdown_path": "research-dist/packs/research-pack.md",
                        "html_path": "research-dist/packs/research-pack.html",
                        "summary_path": "research-dist/packs/pack_summary.json",
                    }
                ],
            }
        )

        self.assertIn("Research Packs", html)
        self.assertIn("research-pack.md", html)
        self.assertIn("research-pack.html", html)
        self.assertIn("pack_summary.json", html)


if __name__ == "__main__":
    unittest.main()
