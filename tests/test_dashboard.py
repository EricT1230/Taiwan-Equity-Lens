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
                        "run_metadata": {"run_id": "run-dashboard-workflow"},
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
        self.assertIn("run-dashboard-workflow", html)
        self.assertIn("workflow-dist/valuation.csv", html)
        self.assertIn("fewer than two successful stocks", html)
        self.assertIn("2330", html)
        self.assertIn("資料可信度", html)
        self.assertIn("overall_status", html)
        self.assertIn("Source fetch failed", html)
        self.assertIn("Run the workflow again later", html)

    def test_render_dashboard_html_contains_source_audit(self):
        html = render_dashboard_html(
            {
                "workflow_summaries": [
                    {
                        "path": "research-dist/workflow_summary.json",
                        "source_audit": {
                            "status": "manual_review",
                            "counts": {"fresh": 0, "stale": 0, "unknown": 0, "manual_review": 2},
                            "items": [{"stock_id": "2330", "status": "manual_review"}],
                        },
                    }
                ],
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "research_summaries": [],
                "memos": [],
                "packs": [],
            }
        )

        self.assertIn("Source Audit", html)
        self.assertIn("manual_review", html)
        self.assertIn("2330", html)

    def test_render_dashboard_html_source_audit_counts_tolerate_mixed_key_types(self):
        html = render_dashboard_html(
            {
                "workflow_summaries": [
                    {
                        "path": "research-dist/workflow_summary.json",
                        "source_audit": {
                            "status": "manual_review",
                            "counts": {"fresh<": "1&", 5: 2},
                            "items": [],
                        },
                    }
                ],
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "research_summaries": [],
                "memos": [],
                "packs": [],
            }
        )

        self.assertIn("counts: 5: 2, fresh&lt;: 1&amp;", html)

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
                        "run_metadata": {"run_id": "run-dashboard-research"},
                        "artifact_registry": {
                            "dependencies": {
                                "workflow_summary": "research-dist/workflow_summary.json",
                            }
                        },
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
        self.assertIn("run-dashboard-research", html)
        self.assertIn("workflow dependency", html)
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

    def test_render_dashboard_html_contains_universe_review(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "counts": {"total": 3, "needs_attention": 2},
                        "universe_review": {
                            "counts": {
                                "total": 3,
                                "needs_attention": 2,
                                "high_priority_attention": 1,
                                "blocked": 1,
                                "new": 1,
                                "active_review": 1,
                            },
                            "category_counts": {
                                "Semiconductor": 2,
                                "Uncategorized": 1,
                            },
                            "state_counts": {"blocked": 1, "new": 1, "review": 1},
                            "priority_counts": {"high": 1, "medium": 2},
                            "review_buckets": {
                                "needs_attention": ["2330", "2303"],
                                "high_priority_attention": ["2330"],
                                "blocked": ["2303"],
                                "new": ["2454"],
                                "active_review": ["2330"],
                            },
                            "attention_queue": [
                                {
                                    "stock_id": "2330",
                                    "company_name": "TSMC",
                                    "category": "Semiconductor",
                                    "priority": "high",
                                    "research_state": "review",
                                    "workflow_status": "ok",
                                    "reliability_status": "warning",
                                    "attention_reasons": ["high priority attention"],
                                },
                                {
                                    "stock_id": "2303",
                                    "company_name": "UMC",
                                    "category": "Semiconductor",
                                    "priority": "medium",
                                    "research_state": "blocked",
                                    "workflow_status": "error",
                                    "reliability_status": "error",
                                    "attention_reasons": ["workflow failed"],
                                },
                            ],
                        },
                        "items": [],
                    }
                ],
            }
        )

        self.assertIn("Universe Review", html)
        self.assertIn("high priority attention", html)
        self.assertIn("Semiconductor: 2", html)
        self.assertIn("Uncategorized: 1", html)
        self.assertIn("2330", html)
        self.assertIn("2303", html)

    def test_render_dashboard_html_contains_review_actions(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {
                            "total_open": 2,
                            "by_category": {"source_audit": 1, "valuation": 1},
                            "by_severity": {"manual_review": 1, "warning": 1},
                        },
                        "review_action_queue": [
                            {
                                "stock_id": "2330",
                                "company_name": "TSMC",
                                "priority": "high",
                                "actions": [
                                    {
                                        "id": "source-audit-manual-review",
                                        "category": "source_audit",
                                        "severity": "manual_review",
                                        "message": "Review source audit: fixture source",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("Review Actions", html)
        self.assertIn('data-review-actions-section="true"', html)
        self.assertIn('data-review-filter="severity"', html)
        self.assertIn('data-review-filter="category"', html)
        self.assertIn('data-review-filter="priority"', html)
        self.assertIn('data-review-filter="status"', html)
        self.assertIn('data-review-filter="search"', html)
        self.assertIn('data-review-filter-reset="true"', html)
        self.assertIn('data-review-action-count="true"', html)
        self.assertIn("Showing 1 of 1 actions", html)
        self.assertIn("total open: 2", html)
        self.assertIn("state health: open: 1 done: 0 deferred: 0 ignored: 0", html)
        self.assertIn("stale state: 0", html)
        self.assertIn("last updated: -", html)
        self.assertIn("manual_review", html)
        self.assertIn("source_audit", html)
        self.assertIn("2330", html)
        self.assertIn("Review source audit: fixture source", html)
        self.assertIn('data-review-action-row="true"', html)
        self.assertIn('data-stock-id="2330"', html)
        self.assertIn('data-priority="high"', html)
        self.assertIn('data-status="open"', html)
        self.assertIn('data-severity="manual_review"', html)
        self.assertIn('data-category="source_audit"', html)
        self.assertIn('data-search-text="2330 high open manual_review source_audit review source audit fixture source"', html)
        self.assertIn("<th>commands</th>", html)
        self.assertIn('data-review-action-command="done"', html)
        self.assertIn('data-review-action-command="deferred"', html)
        self.assertIn('data-review-action-command="ignored"', html)
        self.assertIn('data-review-action-command="reopen"', html)
        self.assertIn("research action set research-dist/review_action_state.json 2330 source-audit-manual-review --status done", html)
        self.assertIn("research action set research-dist/review_action_state.json 2330 source-audit-manual-review --status open", html)

    def test_render_dashboard_html_escapes_review_actions(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {
                            "total_open": 1,
                            "by_category": {"source_audit": 1},
                            "by_severity": {"manual_review": 1},
                        },
                        "review_action_queue": [
                            {
                                "stock_id": "2330<script>",
                                "priority": "high",
                                "actions": [
                                    {
                                        "id": "x",
                                        "category": "source_audit",
                                        "severity": "manual_review",
                                        "message": "Review <source>",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("2330&lt;script&gt;", html)
        self.assertIn("Review &lt;source&gt;", html)
        self.assertIn('data-stock-id="2330&lt;script&gt;"', html)
        self.assertIn('data-status="open"', html)
        self.assertIn('data-search-text="2330&lt;script&gt; high open manual_review source_audit review &lt;source&gt;"', html)
        self.assertNotIn("2330<script>", html)
        self.assertNotIn("Review <source>", html)
        self.assertNotIn('data-stock-id="2330<script>"', html)
        self.assertNotIn('data-search-text="2330<script>', html)

    def test_discover_dashboard_items_loads_review_action_state(self):
        root = Path(".tmp-cli-test/dashboard-review-action-state")
        root.mkdir(parents=True, exist_ok=True)
        (root / "research_summary.json").write_text(
            json.dumps(
                {
                    "review_action_summary": {"total_open": 1},
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
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "review_action_state.json").write_text(
            json.dumps(
                {
                    "actions": {
                        "2330:workflow-error": {
                            "stock_id": "2330",
                            "action_id": "workflow-error",
                            "status": "done",
                            "note": "checked",
                            "updated_at": "2026-05-15T09:00:00Z",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        items = discover_dashboard_items([root])

        self.assertEqual(
            items["research_summaries"][0]["review_action_state"]["actions"]["2330:workflow-error"]["status"],
            "done",
        )
        self.assertEqual(items["research_summaries"][0]["review_action_state_path"], str(root / "review_action_state.json"))

    def test_render_dashboard_html_overlays_review_action_state(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {"total_open": 1},
                        "review_action_state": {
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
                                }
                            }
                        },
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
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("<th>status</th>", html)
        self.assertIn("<th>commands</th>", html)
        self.assertIn('data-status="done"', html)
        self.assertIn("state health: open: 0 done: 1 deferred: 0 ignored: 0", html)
        self.assertIn("stale state: 1", html)
        self.assertIn("last updated: 2026-05-15T10:00:00Z", html)
        self.assertNotIn("old-action", html)
        self.assertIn('data-review-filter="status"', html)
        self.assertIn("note: checked", html)
        self.assertIn("updated: 2026-05-15T09:00:00Z", html)

    def test_render_dashboard_html_quotes_review_action_commands(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research dist/research_summary.json",
                        "review_action_summary": {"total_open": 1},
                        "review_action_queue": [
                            {
                                "stock_id": "23 30's",
                                "priority": "high",
                                "actions": [
                                    {
                                        "id": "source action's",
                                        "category": "source_audit",
                                        "severity": "manual_review",
                                        "message": "Review <source>",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("research action set &#x27;research dist/review_action_state.json&#x27;", html)
        self.assertIn("&#x27;23 30&#x27;&#x27;s&#x27;", html)
        self.assertIn("&#x27;source action&#x27;&#x27;s&#x27;", html)
        self.assertNotIn("Review <source>", html)

    def test_render_dashboard_html_warns_for_invalid_review_action_state(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {"total_open": 1},
                        "review_action_state_warning": "Could not read review action state: invalid JSON",
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
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("Could not read review action state: invalid JSON", html)
        self.assertIn('data-status="open"', html)
        self.assertIn("state health: open: 1 done: 0 deferred: 0 ignored: 0", html)
        self.assertIn("stale state: 0", html)
        self.assertIn("last updated: -", html)

    def test_render_dashboard_html_omits_review_action_filters_for_legacy_summary(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "counts": {"total": 1, "needs_attention": 0},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertNotIn("Review Actions", html)
        self.assertNotIn('data-review-actions-section="true"', html)
        self.assertNotIn('data-review-filter="severity"', html)

    def test_render_dashboard_html_includes_review_action_filter_script(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {"total_open": 1},
                        "review_action_queue": [
                            {
                                "stock_id": "2330",
                                "priority": "high",
                                "actions": [
                                    {
                                        "id": "workflow-error",
                                        "category": "workflow",
                                        "severity": "error",
                                        "message": "Resolve workflow failure.",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                        "counts": {"total": 1, "needs_attention": 1},
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        self.assertIn("function initReviewActionFilters()", html)
        self.assertIn("No review actions match the current filters.", html)
        self.assertIn("data-review-action-empty", html)
        self.assertIn("data-review-filter-reset", html)
        self.assertIn("row.dataset.status", html)
        self.assertIn("row.dataset.searchText", html)
        self.assertIn("function initReviewActionCommandCopy()", html)
        self.assertIn("navigator.clipboard.writeText", html)
        self.assertIn("document.execCommand('copy')", html)
        self.assertIn('data-review-action-copy-status="true"', html)
        self.assertIn("Copy failed. Use the visible command text.", html)

    def test_render_dashboard_html_tolerates_legacy_summaries_without_traceability(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [
                    {
                        "path": "workflow-dist/workflow_summary.json",
                        "watchlist_path": "watchlist.csv",
                        "stock_ids": ["2330"],
                        "successful_stock_ids": ["2330"],
                        "paths": {},
                    }
                ],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "counts": {"total": 0, "needs_attention": 0},
                        "items": [],
                    }
                ],
            }
        )

        self.assertIn("workflow-dist/workflow_summary.json", html)
        self.assertIn("research-dist/research_summary.json", html)
        self.assertIn("total research items: 0", html)
        self.assertNotIn("Universe Review", html)

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
