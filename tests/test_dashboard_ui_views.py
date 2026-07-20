import unittest

from taiwan_stock_analysis.dashboard_ui.page import render as render_page
from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view
from taiwan_stock_analysis.dashboard_ui.views.outputs import render_outputs_view
from taiwan_stock_analysis.dashboard_ui.views.workbench import render_workbench_view

# Fixture shape mirrors what dashboard.py's `_discover_market_intelligence_reports` /
# `_discover_industry_trend_reports` actually produce: a flat report dict (no
# `{"report": {...}}` wrapper) merged with path/markdown_path/html_path, using the
# real field names from market_intelligence_report.json / industry_trend_report.json
# (category, top_keywords, latest_news, fund_flow.*_net, sentiment.change,
# sentiment.cycle_phase, sentiment.components.*.contribution_5d, direction vs
# rotation_phase, average_return_1d/5d/20d, leading_stocks/lagging_stocks as
# {stock_id, company_name, return_20d} objects). See task-7-report.md for the
# before/after reconciliation against the brief's assumed field names.
_MI = {
    "market_intelligence_reports": [
        {
            "path": ".tmp/market-intelligence/market_intelligence_report.json",
            "markdown_path": "",
            "html_path": "",
            "quality_gate": {"status": "ready", "blocker_count": 0, "blockers": []},
            "freshness": {
                "news": {"status": "fresh"},
                "fund_flow": {"status": "fresh"},
                "industry_trend": {"status": "fresh"},
                "price": {"status": "fresh"},
            },
            "industries": [
                {
                    "category": "Semiconductor",
                    "stock_ids": ["2330", "2303"],
                    "news_count": 2,
                    "top_keywords": ["AI", "CoWoS"],
                    "latest_news": [
                        {"title": "台積電 AI 伺服器需求", "url": "https://example.com/a"},
                    ],
                    "fund_flow": {
                        "foreign_net": 5900,
                        "investment_trust_net": 3850,
                        "dealer_net": -800,
                        "total_net": 8950,
                    },
                    "sentiment": {
                        "status": "ready",
                        "score_5d": 29.1,
                        "baseline_20d": 30.6,
                        "change": -1.5,
                        "cycle_phase": "consolidation",
                        "confidence": "low",
                        "components": {
                            "news": {"contribution_5d": 0.0},
                            "price": {"contribution_5d": 2.5},
                            "fund_flow": {"contribution_5d": 26.6},
                        },
                    },
                }
            ],
        }
    ],
    "industry_trend_reports": [
        {
            "path": ".tmp/industry-trends/industry_trend_report.json",
            "markdown_path": "",
            "html_path": "",
            "as_of_date": "2026-07-10",
            "categories": [
                {
                    "category": "Semiconductor",
                    "direction": "mixed",
                    "rotation_phase": "divergent",
                    "average_return_1d": 0.1,
                    "average_return_5d": 0.8,
                    "average_return_20d": 3.5,
                    "leading_stocks": [
                        {"stock_id": "2330", "company_name": "台積電", "return_20d": 11.1},
                    ],
                    "lagging_stocks": [
                        {"stock_id": "2303", "company_name": "聯電", "return_20d": -4.0},
                    ],
                }
            ],
        }
    ],
}


class MarketViewTests(unittest.TestCase):
    def test_renders_sentiment_chart_and_components(self):
        html = render_market_view(_MI)
        self.assertIn("Semiconductor", html)
        self.assertIn("chart-spark", html)                 # sparkline
        self.assertEqual(html.count("chart-contrib-row"), 3)
        self.assertIn("29.1", html)
        self.assertIn("資料完整", html)                     # sentiment.status "ready" -> label

    def test_fund_flow_uses_market_up_down_grammar(self):
        html = render_market_view(_MI)
        self.assertIn("+5,900", html)                      # foreign buy, formatted
        self.assertIn("-800", html)                        # dealer sell
        self.assertIn("chart-hbar-fill up", html)
        self.assertIn("chart-hbar-fill down", html)

    def test_keywords_and_news_link_escaped_and_safe(self):
        html = render_market_view(_MI)
        self.assertIn("CoWoS", html)
        self.assertIn("https://example.com/a", html)

    def test_empty_items_render_placeholder_not_error(self):
        html = render_market_view({})
        self.assertIn("尚未", html)                         # 空態文字


# Fixture shape mirrors what `discover_dashboard_items` (dashboard.py:69-145) actually
# produces: each entry in `items["research_summaries"]` is the *flat parsed*
# research_summary.json merged with a `path` key (the summary file's own path) and,
# only when a `review_action_state.json` sidecar already exists on disk, a
# `review_action_state_path` key (omitted here to exercise the fallback derivation).
#
# The task-8 brief's fixture assumed a shape that does not exist in the real JSON:
# there is no top-level `handoff_gate`, no flat `review_actions[]`, no
# `research_pool[]`, and actions key off `id` (not `action_id`). Verified against
# `.tmp-v053-preview/research_summary.json`. The real shape instead:
#   - nests actions per stock inside `review_action_queue[].actions[]`, each row
#     carrying only its own `id`/`category`/`severity`/`message`/`status` -- the
#     view must flatten this itself, attaching the parent group's `stock_id` /
#     `company_name` / `priority` to every action row;
#   - keeps the research pool in `items[]` (not `research_pool[]`);
#   - has no `handoff_gate` at all -- it is *derived* by
#     `handoff.build_handoff_quality_gate(summary, state)` from `review_action_queue`
#     + `items`;
#   - has no `requires_evidence` field -- also derived, via
#     `handoff.requires_handoff_evidence(action_id)`.
# See task-8-report.md for the full before/after reconciliation table.
#
# `fundamental_review` below is trimmed to just the fields
# `handoff._expected_action_ids` actually inspects (`verdict`, `score`,
# `thesis_breakers`, `questions`) -- the real file also carries a large `agents`
# breakdown that nothing in the gate-derivation or render path reads. Every other
# field that `_expected_action_ids`/`_missing_gate_action_blockers` cross-checks
# against `review_action_queue` (`source_audit_status`, `workflow_status`,
# `reliability_status`, `attention_reasons`, `research_state`, `priority`, `thesis`,
# `follow_up_questions`) is copied verbatim from the real fixture file, so
# `build_handoff_quality_gate` does not synthesize any *extra* "missing gate action"
# blockers beyond the 11 real open actions -- keeping `total_open` == 11 exact and
# matching the design mockup (`.superpowers/brainstorm/.../workbench.html`).
_RS = {
    "research_summaries": [
        {
            "path": ".tmp-v053-preview/research_summary.json",
            "items": [
                {
                    "stock_id": "2330",
                    "company_name": "TSMC",
                    "priority": "high",
                    "research_state": "review",
                    "thesis": "Leading foundry scale",
                    "follow_up_questions": "Are EPS assumptions current?",
                    "workflow_status": "ok",
                    "reliability_status": "warning",
                    "attention_reasons": [
                        "research state requires review",
                        "valuation output is unavailable or skipped",
                        "data reliability is warning",
                    ],
                    "source_audit_status": "manual_review",
                    "fundamental_review": {
                        "verdict": "needs_work",
                        "score": 88,
                        "thesis_breakers": ["Downside scenario is larger than upside scenario."],
                        "questions": [
                            "Review moat durability manually because fewer than three years of metrics are available."
                        ],
                    },
                },
                {
                    "stock_id": "2303",
                    "company_name": "UMC",
                    "priority": "medium",
                    "research_state": "watching",
                    "thesis": "Cyclical recovery optionality",
                    "follow_up_questions": "Which assumptions need confirmation?",
                    "workflow_status": "ok",
                    "reliability_status": "warning",
                    "attention_reasons": [
                        "valuation output is unavailable or skipped",
                        "data reliability is warning",
                    ],
                    "source_audit_status": "manual_review",
                    "fundamental_review": {
                        "verdict": "needs_work",
                        "score": 80,
                        "thesis_breakers": ["Downside scenario is larger than upside scenario."],
                        "questions": [
                            "Review moat durability manually because fewer than three years of metrics are available."
                        ],
                    },
                },
            ],
            "review_action_summary": {
                "total_open": 11,
                "by_category": {
                    "fundamental_review": 4,
                    "reliability": 2,
                    "research_quality": 1,
                    "source_audit": 2,
                    "valuation": 2,
                },
                "by_severity": {"manual_review": 4, "warning": 4, "info": 3},
            },
            "review_action_queue": [
                {
                    "stock_id": "2330",
                    "company_name": "TSMC",
                    "priority": "high",
                    "actions": [
                        {
                            "id": "fundamental-review-thesis-breakers",
                            "category": "fundamental_review",
                            "severity": "manual_review",
                            "message": "請確認基本面專家提出的 thesis breaker：Downside scenario is larger than upside scenario.",
                            "status": "open",
                        },
                        {
                            "id": "source-audit-manual-review",
                            "category": "source_audit",
                            "severity": "manual_review",
                            "message": "Review source audit: fixture source requires manual review; offline mode",
                            "status": "open",
                        },
                        {
                            "id": "reliability-warning",
                            "category": "reliability",
                            "severity": "warning",
                            "message": "Inspect data reliability warning before handoff.",
                            "status": "open",
                        },
                        {
                            "id": "valuation-unavailable",
                            "category": "valuation",
                            "severity": "warning",
                            "message": "Complete or verify valuation output before handoff.",
                            "status": "open",
                        },
                        {
                            "id": "fundamental-review-manual-check",
                            "category": "fundamental_review",
                            "severity": "info",
                            "message": "請回覆基本面專家審查問題，再進入最終交付。",
                            "status": "open",
                        },
                        {
                            "id": "research-state-review",
                            "category": "research_quality",
                            "severity": "info",
                            "message": "Complete active review checks for this item.",
                            "status": "open",
                        },
                    ],
                },
                {
                    "stock_id": "2303",
                    "company_name": "UMC",
                    "priority": "medium",
                    "actions": [
                        {
                            "id": "fundamental-review-thesis-breakers",
                            "category": "fundamental_review",
                            "severity": "manual_review",
                            "message": "請確認基本面專家提出的 thesis breaker：Downside scenario is larger than upside scenario.",
                            "status": "open",
                        },
                        {
                            "id": "source-audit-manual-review",
                            "category": "source_audit",
                            "severity": "manual_review",
                            "message": "Review source audit: fixture source requires manual review; offline mode",
                            "status": "open",
                        },
                        {
                            "id": "reliability-warning",
                            "category": "reliability",
                            "severity": "warning",
                            "message": "Inspect data reliability warning before handoff.",
                            "status": "open",
                        },
                        {
                            "id": "valuation-unavailable",
                            "category": "valuation",
                            "severity": "warning",
                            "message": "Complete or verify valuation output before handoff.",
                            "status": "open",
                        },
                        {
                            "id": "fundamental-review-manual-check",
                            "category": "fundamental_review",
                            "severity": "info",
                            "message": "請回覆基本面專家審查問題，再進入最終交付。",
                            "status": "open",
                        },
                    ],
                },
            ],
        }
    ],
    # Cross-referenced by the research-pool table's report/memo links (only 2330 has
    # both, so the fixture also exercises the "-" fallback for 2303).
    "reports": [
        {"stock_id": "2330", "html_path": ".tmp-v053-preview/reports/2330_analysis.html", "json_path": ""},
    ],
    "memo_outputs": [
        {"stock_id": "2330", "markdown_path": "", "html_path": ".tmp-v053-preview/memos/2330_memo.html", "summary_path": ""},
    ],
}


class WorkbenchViewTests(unittest.TestCase):
    def test_gate_card_shows_blocker_count_and_progress(self):
        html = render_workbench_view(_RS)
        self.assertIn("11", html)
        self.assertIn("chart-progress", html)
        self.assertIn("處理建議下一步", html)
        self.assertIn("產出 Evidence Pack", html)

    def test_single_queue_first_row_is_next_action_high_priority_first(self):
        html = render_workbench_view(_RS)
        self.assertEqual(html.count('class="queue"'), 1)
        self.assertNotEqual(html.find("queue-row next"), -1)
        self.assertLess(html.find("2330"), html.find("2303"))   # high before medium
        self.assertIn("建議下一步", html)

    def test_rows_carry_filter_data_attributes(self):
        html = render_workbench_view(_RS)
        self.assertIn('data-priority="high"', html)
        self.assertIn('data-category="fundamental_review"', html)
        self.assertIn('data-severity="manual_review"', html)
        self.assertIn('data-stock="2330"', html)
        self.assertIn('data-status="open"', html)

    def test_expand_row_has_evidence_inputs_and_actions(self):
        html = render_workbench_view(_RS)
        self.assertIn("queue-expand", html)
        self.assertIn("reviewer", html)
        self.assertIn("標記完成", html)
        self.assertIn("稍後處理", html)
        self.assertIn("不處理", html)

    def test_static_mode_uses_data_copy_served_mode_uses_action_api(self):
        static_html = render_workbench_view(_RS, action_api_enabled=False)
        self.assertIn("data-copy", static_html)
        api_html = render_workbench_view(_RS, action_api_enabled=True)
        self.assertIn("data-action-api", api_html)
        self.assertIn("data-action-id", api_html)
        self.assertIn("data-status", api_html)

    def test_research_pool_is_a_single_mini_table_with_links(self):
        html = render_workbench_view(_RS)
        self.assertEqual(html.count('class="mini-table"'), 1)
        self.assertIn(".tmp-v053-preview/reports/2330_analysis.html", html)
        self.assertIn(".tmp-v053-preview/memos/2330_memo.html", html)

    def test_no_open_actions_shows_empty_state_and_ok_gate(self):
        empty = {
            "research_summaries": [
                {
                    "path": ".tmp-empty/research_summary.json",
                    "items": [],
                    "review_action_summary": {"total_open": 0, "by_category": {}, "by_severity": {}},
                    "review_action_queue": [],
                }
            ]
        }
        html = render_workbench_view(empty)
        self.assertIn("無待辦", html)
        self.assertIn("ui-pill-ok", html)


# Fixture shape mirrors what `discover_dashboard_items` (dashboard.py:69-311) actually
# produces for Tab 3's five output-file link categories, four status/record tables, and
# the optional market-data bundle. Verified field-by-field against:
#   - .tmp-v053-preview/workflow_summary.json for workflow_summaries[] -- watchlist_path/
#     stock_ids/successful_stock_ids/paths.{batch_summary,valuation_csv,
#     valuation_batch_summary,comparison.{json,html},dashboard}/comparison_skipped_reason/
#     source_audit.{status,counts,items[].{stock_id,status,<component>.{status,
#     source_mode,review_reason}}}/data_reliability.{ok,warning,error,skipped,
#     overall_status}/stock_failures/run_metadata.run_id.
#   - .tmp-v053-preview/reports/batch_summary.json for batch_summaries[].results[] --
#     {stock_id,status,json_path,html_path}, plus a synthetic error row (status=error,
#     error=<message>) matching dashboard.py's own batch-error fixture shape.
#   - .tmp-v053-preview/memos/memo_summary.json cross-checked against
#     dashboard.py:_discover_memo_outputs (174-195), which reshapes it per-stock into
#     items["memo_outputs"] = [{stock_id, markdown_path, html_path, summary_path}, ...]
#     -- NOT the raw memo_summary.json shape (its own generated[]/skipped[]/
#     artifact_registry keys never reach items["memo_outputs"]).
#   - dashboard.py:_discover_pack_outputs (198-210) / _discover_handoff_pack_outputs
#     (213-237) for pack_outputs[] = {markdown_path, html_path, summary_path} and
#     handoff_pack_outputs[] = {..., gate_status, ready, blocker_count,
#     evidence_missing_count, invalid_evidence_count}. Neither a packs/ pack_summary.json
#     with a companion handoff-pack/ dir, nor any handoff-pack/ dir at all, is checked in
#     under .tmp-v053-preview, so the handoff_pack_outputs shape is reconstructed from the
#     discover code + tests/test_dashboard.py:test_render_dashboard_html_contains_handoff_
#     evidence_pack_outputs (2124-2153), not a file read.
#   - tests/test_dashboard.py:test_discover_and_render_dashboard_market_data_report
#     (664-717) for market_data_reports[] -- as_of_date/quality_gate.{status,blockers}/
#     coverage.{stocks_total,official_profile_count,price_ready_count,fund_flow_count}/
#     items[].{stock_id,market,industry_name,price_points,price_latest_date,
#     fund_flow_available}. Also no market-data/ dir checked in under .tmp-v053-preview.
#
# The brief's Step 1 fixture undershoots this: its `workflow_summaries` entry carries
# only `path`/`successful_stock_ids`, omitting `source_audit`/`data_reliability`/`paths`/
# `run_metadata` entirely -- which would leave two of the four required status tables
# (資料可信度/來源稽核) only ever exercising their empty-state branch. Extended below to a
# real-shape fixture per the task instructions, while keeping the brief's four test
# method bodies unchanged (they still pass against the richer fixture).
_OUT = {
    "reports": [
        {
            "stock_id": "2330",
            "html_path": ".tmp-v053-preview\\reports\\2330_analysis.html",
            "json_path": ".tmp-v053-preview\\reports\\2330_raw_data.json",
        },
    ],
    "comparisons": [
        {
            "html_path": ".tmp-v053-preview\\comparison\\comparison.html",
            "json_path": ".tmp-v053-preview\\comparison\\comparison.json",
        }
    ],
    "memo_outputs": [
        {
            "stock_id": "2330",
            "markdown_path": ".tmp-v053-preview\\memos\\2330_memo.md",
            "html_path": ".tmp-v053-preview\\memos\\2330_memo.html",
            "summary_path": ".tmp-v053-preview\\memos\\memo_summary.json",
        },
    ],
    "pack_outputs": [
        {
            "markdown_path": ".tmp-v053-preview\\packs\\research-pack.md",
            "html_path": ".tmp-v053-preview\\packs\\research-pack.html",
            "summary_path": ".tmp-v053-preview\\packs\\pack_summary.json",
        }
    ],
    "handoff_pack_outputs": [
        {
            "markdown_path": ".tmp-v053-preview\\handoff-pack\\handoff-pack.md",
            "html_path": ".tmp-v053-preview\\handoff-pack\\handoff-pack.html",
            "summary_path": ".tmp-v053-preview\\handoff-pack\\handoff_pack_summary.json",
            "gate_status": "ready",
            "ready": "True",
            "blocker_count": "0",
            "evidence_missing_count": "0",
            "invalid_evidence_count": "0",
        }
    ],
    "workflow_summaries": [
        {
            "path": ".tmp-v053-preview\\workflow_summary.json",
            "watchlist_path": ".tmp-v053-preview\\research_watchlist.csv",
            "stock_ids": ["2330", "2303"],
            "successful_stock_ids": ["2330", "2303"],
            "paths": {
                "batch_summary": ".tmp-v053-preview\\reports\\batch_summary.json",
                "valuation_csv": ".tmp-v053-preview\\valuation.csv",
                "valuation_batch_summary": ".tmp-v053-preview\\valuation-reports\\batch_summary.json",
                "comparison": {
                    "json": ".tmp-v053-preview\\comparison\\comparison.json",
                    "html": ".tmp-v053-preview\\comparison\\comparison.html",
                },
                "dashboard": ".tmp-v053-preview\\dashboard.html",
            },
            "comparison_skipped_reason": "",
            "data_reliability": {"ok": 2, "warning": 4, "error": 0, "skipped": 0, "overall_status": "warning"},
            "stock_failures": [],
            "source_audit": {
                "status": "manual_review",
                "counts": {"fresh": 0, "stale": 0, "unknown": 0, "manual_review": 2},
                "items": [
                    {
                        "stock_id": "2330",
                        "status": "manual_review",
                        "financial_statement": {
                            "status": "manual_review",
                            "source_mode": "fixture",
                            "review_reason": "fixture source requires manual review",
                        },
                        "price": {
                            "status": "manual_review",
                            "source_mode": "offline",
                            "review_reason": "offline mode",
                        },
                    },
                ],
            },
            "run_metadata": {"run_id": "workflow-20260717T195312Z"},
        }
    ],
    "batch_summaries": [
        {
            "path": ".tmp-v053-preview\\reports\\batch_summary.json",
            "results": [
                {
                    "stock_id": "2330",
                    "status": "ok",
                    "json_path": ".tmp-v053-preview\\reports\\2330_raw_data.json",
                    "html_path": ".tmp-v053-preview\\reports\\2330_analysis.html",
                },
                {"stock_id": "9999", "status": "error", "error": "missing fixture"},
            ],
        }
    ],
    "market_data_reports": [
        {
            "path": ".tmp-market-data\\market_data_report.json",
            "markdown_path": ".tmp-market-data\\market_data_report.md",
            "as_of_date": "2026-07-12",
            "quality_gate": {"status": "ready", "blockers": []},
            "coverage": {
                "stocks_total": 2,
                "official_profile_count": 2,
                "price_ready_count": 2,
                "fund_flow_count": 2,
            },
            "items": [
                {
                    "stock_id": "6223",
                    "market": "TPEX",
                    "industry_name": "半導體業",
                    "price_points": 42,
                    "price_latest_date": "2026-07-09",
                    "fund_flow_available": True,
                }
            ],
        }
    ],
}


class OutputsViewTests(unittest.TestCase):
    def test_lists_report_and_comparison_links(self):
        html = render_outputs_view(_OUT)
        self.assertIn("2330_analysis.html", html)
        self.assertIn("comparison.html", html)

    def test_includes_command_snippets_with_copy_and_watchlist_template(self):
        html = render_outputs_view(_OUT)
        self.assertIn("data-copy", html)
        self.assertIn("data:text/csv", html)
        self.assertIn("python -m taiwan_stock_analysis.cli", html)

    def test_status_tables_scroll_wrapped(self):
        html = render_outputs_view(_OUT)
        self.assertIn("table-scroll", html)
        self.assertIn("mini-table", html)

    def test_empty_items_render_placeholders(self):
        html = render_outputs_view({})
        self.assertIn("尚未", html)

    def test_memo_pack_and_handoff_pack_links_present(self):
        html = render_outputs_view(_OUT)
        self.assertIn("2330_memo.html", html)
        self.assertIn("research-pack.html", html)
        self.assertIn("handoff-pack.html", html)
        self.assertIn("ready", html)  # handoff_pack_outputs[0].gate_status

    def test_reliability_and_source_audit_tables_show_real_fields(self):
        html = render_outputs_view(_OUT)
        self.assertIn("warning", html)  # data_reliability.overall_status
        self.assertIn("manual_review", html)  # source_audit.status / items[].status
        self.assertIn("fixture source requires manual review", html)  # component review_reason

    def test_batch_table_shows_ok_and_error_rows(self):
        html = render_outputs_view(_OUT)
        self.assertIn("9999", html)
        self.assertIn("missing fixture", html)

    def test_market_data_table_present_when_data_exists_and_omitted_when_absent(self):
        html = render_outputs_view(_OUT)
        self.assertIn("TPEX", html)
        self.assertIn("半導體業", html)

        without_market_data = dict(_OUT)
        without_market_data.pop("market_data_reports")
        omitted_html = render_outputs_view(without_market_data)
        self.assertNotIn("TPEX", omitted_html)
        self.assertNotIn("data-outputs-market-data-section", omitted_html)

    def test_required_status_tables_show_placeholder_not_omitted_when_empty(self):
        # Workflow/batch/reliability/source-audit must each still render a 「尚未」
        # placeholder when their upstream list is empty -- unlike market_data_reports,
        # which the brief explicitly scopes as "present only when data exists" and is
        # entirely omitted (see test above) rather than shown with a placeholder.
        html = render_outputs_view({"reports": [{"stock_id": "2330", "html_path": "x.html", "json_path": ""}]})
        self.assertGreaterEqual(html.count("尚未"), 4)
        self.assertNotIn("data-outputs-market-data-section", html)

    def test_escapes_hostile_values(self):
        hostile = {
            "reports": [{"stock_id": "<script>evil</script>", "html_path": 'a"b.html', "json_path": ""}],
            "workflow_summaries": [
                {
                    "path": "workflow_summary.json",
                    "source_audit": {"status": "ok", "counts": {"fresh<": "1&", 5: 2}, "items": []},
                }
            ],
        }
        html = render_outputs_view(hostile)
        self.assertNotIn("<script>evil</script>", html)
        self.assertIn("&lt;script&gt;evil&lt;/script&gt;", html)
        self.assertIn("fresh&lt;: 1&amp;", html)


class PageTests(unittest.TestCase):
    def _items(self):
        d = {}
        d.update(_MI)
        d.update(_RS)
        d.update(_OUT)
        return d

    def test_full_document_structure(self):
        html = render_page(self._items())
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>台股基本面儀表板</title>", html)
        self.assertEqual(html.count('class="ui-tab"'), 3)
        self.assertIn('class="ui-panel active"', html)      # market default

    def test_single_disclaimer(self):
        self.assertEqual(render_page(self._items()).count("不構成投資建議"), 1)

    def test_topbar_status_pills_present(self):
        html = render_page(self._items())
        self.assertIn("交接", html)
        self.assertIn("待辦", html)

    def test_offline_no_external_asset_tags(self):
        html = render_page(self._items())
        self.assertNotIn("cdn", html.lower())
        self.assertNotIn("<link", html)
        self.assertNotIn("googleapis", html)

    def test_inline_script_has_tab_and_copy_handlers(self):
        html = render_page(self._items())
        self.assertIn("<script>", html)
        self.assertIn("data-copy", html)
        self.assertIn("ui-tab", html)
