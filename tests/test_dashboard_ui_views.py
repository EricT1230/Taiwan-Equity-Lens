import copy
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
                        # Real shape verified in .tmp-v053-preview/market-intelligence/
                        # market_intelligence_report.json: the demo hits status
                        # "insufficient_history" with every numeric field null.
                        "forecast": {
                            "status": "insufficient_history",
                            "history_days": 1,
                            "forecast_1d": None,
                            "forecast_5d": None,
                            "interval_1d": None,
                            "interval_5d": None,
                        },
                        "turning_risk": {
                            "status": "insufficient_history",
                            "history_days": 1,
                            "peak_risk": None,
                            "trough_risk": None,
                            "direction": "unclear",
                            "window": "unclear",
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

    # -- Feature A: sentiment forecast + turning-risk (spec 3.2, ported from
    # dashboard.py:1230/_market_intelligence_forecast and
    # dashboard.py:1250/_market_intelligence_turning_risk) -------------------

    def test_forecast_and_turning_risk_render_insufficient_history_placeholder(self):
        # _MI's sentiment already carries the exact real shape verified in
        # .tmp-v053-preview/market-intelligence/market_intelligence_report.json --
        # both sub-reports at status "insufficient_history" with null numerics.
        # This is what the demo data actually hits, so it must render correctly.
        html = render_market_view(_MI)
        self.assertIn("情緒預測", html)
        self.assertIn("轉折風險", html)
        # 4 = 2 blocks x 2 occurrences each (once inside the bilingual "insufficient
        # history / 歷史資料不足" status pill, once in the plain-text placeholder) --
        # matches old dashboard.py's identical redundancy between
        # _market_intelligence_experimental_status() and the forecast/risk text.
        self.assertEqual(html.count("歷史資料不足"), 4)
        self.assertEqual(html.count("insufficient history / 歷史資料不足"), 2)  # ported experimental marker

    def test_forecast_and_turning_risk_missing_key_renders_dash_not_error(self):
        # Distinct from "insufficient_history": a sentiment payload that omits the
        # forecast/turning_risk keys entirely (status falls back to "missing" per
        # dashboard.py:1230/1250) must still degrade to "-" without raising.
        data = copy.deepcopy(_MI)
        sentiment = data["market_intelligence_reports"][0]["industries"][0]["sentiment"]
        del sentiment["forecast"]
        del sentiment["turning_risk"]
        html = render_market_view(data)
        self.assertIn("情緒預測", html)
        self.assertIn("轉折風險", html)

    def test_forecast_and_turning_risk_render_real_numbers(self):
        data = copy.deepcopy(_MI)
        sentiment = data["market_intelligence_reports"][0]["industries"][0]["sentiment"]
        sentiment["forecast"] = {
            "status": "experimental",
            "history_days": 42,
            "forecast_1d": 31.2,
            "forecast_5d": 35.8,
            "interval_1d": [28.4, 34.0],
            "interval_5d": [30.1, 41.5],
        }
        sentiment["turning_risk"] = {
            "status": "experimental",
            "history_days": 64,
            "peak_risk": 62.5,
            "trough_risk": 18.0,
            "direction": "peak",
            "window": "1_to_3_days",
        }
        html = render_market_view(data)
        self.assertIn("experimental / 實驗訊號", html)
        self.assertIn("1D 31.2 [28.4, 34.0]", html)
        self.assertIn("5D 35.8 [30.1, 41.5]", html)
        self.assertIn("高點 62.5", html)
        self.assertIn("低點 18.0", html)
        self.assertIn("高點", html)          # turning_risk.direction "peak" -> label
        self.assertIn("1-3 天", html)        # turning_risk.window "1_to_3_days" -> label

    # -- Feature B: industry sort control (spec 3.2, ported from
    # dashboard.py:1002-1009 select markup + dashboard.py:1104
    # _market_intelligence_industry_sort_key's confidence_order) -------------

    def test_industry_sort_control_renders_ported_options(self):
        html = render_market_view(_MI)
        self.assertIn('data-industry-sentiment-sort="true"', html)
        self.assertIn('aria-label="產業情緒排序"', html)
        self.assertIn('<option value="score" selected>目前 5D 分數</option>', html)
        self.assertIn('<option value="change">升溫／降溫變化</option>', html)
        self.assertIn('<option value="peak_risk">高點風險</option>', html)
        self.assertIn('<option value="trough_risk">低點風險</option>', html)
        self.assertIn('<option value="confidence">信心</option>', html)

    def test_industry_card_carries_sort_data_attributes(self):
        html = render_market_view(_MI)
        # data-sentiment-category, not data-category -- workbench.py's queue rows
        # already own that shorter name for an unrelated review-action category enum
        # (see WorkbenchViewTests.test_rows_carry_filter_data_attributes).
        self.assertIn('data-sentiment-category="Semiconductor"', html)
        self.assertIn('data-sentiment-score="29.1"', html)
        self.assertIn('data-sentiment-change="-1.5"', html)
        self.assertIn('data-confidence-order="1"', html)   # confidence "low" -> 1
        # _MI's turning_risk is insufficient_history (peak/trough both null) --
        # missing risk values must still emit the attribute (as "-") so the client
        # sort's NaN-to--Infinity fallback has something to read.
        self.assertIn('data-peak-risk="-"', html)
        self.assertIn('data-trough-risk="-"', html)


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

    def test_gate_card_has_stable_resync_ids(self):
        # Regression: served-mode JS (page_script.py:syncGateCard) needs these
        # hooks to resync the gate card after a review-actions/set POST, or it
        # keeps showing stale numbers next to an updated topbar pill (Bug 2).
        html = render_workbench_view(_RS)
        self.assertIn('id="wb-gate-blockers"', html)
        self.assertIn('id="wb-gate-progress"', html)
        self.assertIn('id="wb-gate-processed"', html)
        self.assertIn('id="wb-gate-readiness"', html)

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

    # -- Feature C: bulk queue operations (spec 3.3 "批次操作", ported from
    # dashboard.py:_review_action_bulk_tools ~2973 / _review_action_rows'
    # select checkbox ~2771) -----------------------------------------------

    def test_queue_rows_carry_select_checkboxes_with_identifiers(self):
        html = render_workbench_view(_RS)
        # 11 flattened action rows total (6 for 2330 + 5 for 2303, matching
        # review_action_summary.total_open) -- one select checkbox each.
        self.assertEqual(html.count('data-queue-select="true"'), 11)
        self.assertIn(
            'data-queue-select="true" data-stock="2330"'
            ' data-action-id="fundamental-review-thesis-breakers"',
            html,
        )

    # -- CRITICAL fix: bulk/single-row evidence-wipe guards need to know, per
    # row, whether the action requires handoff evidence and whether evidence
    # is already stored -- ported from handoff.py's requires_handoff_evidence
    # (already imported in workbench.py) plus the state-overlaid row fields. --

    def test_queue_row_carries_requires_evidence_and_has_evidence_flags(self):
        html = render_workbench_view(_RS)
        # _RS carries no review_action_state sidecar, so nothing has stored
        # evidence yet. fundamental-review-thesis-breakers IS in
        # handoff.EVIDENCE_REQUIRED_ACTION_IDS; research-state-review is NOT.
        self.assertIn(
            'data-stock="2330" data-priority="high"'
            ' data-severity="manual_review" data-category="fundamental_review"'
            ' data-status="open" data-requires-evidence="true"'
            ' data-has-evidence="false">',
            html,
        )
        self.assertIn(
            'data-stock="2330" data-priority="high"'
            ' data-severity="info" data-category="research_quality"'
            ' data-status="open" data-requires-evidence="false"'
            ' data-has-evidence="false">',
            html,
        )

    def test_queue_row_has_evidence_true_only_when_all_three_fields_stored(self):
        data = copy.deepcopy(_RS)
        data["research_summaries"][0]["review_action_state"] = {
            "version": 1,
            "actions": {
                "2330:fundamental-review-thesis-breakers": {
                    "stock_id": "2330",
                    "action_id": "fundamental-review-thesis-breakers",
                    "status": "done",
                    "note": "checked",
                    "reviewer": "alice",
                    "evidence_url": "evidence/2330.md",
                    "updated_at": "2026-07-20T09:00:00Z",
                },
                # Partial evidence (missing evidence_url) must NOT count as
                # "has evidence" -- matches handoff._missing_evidence_fields,
                # which treats any missing field as a blocker.
                "2303:fundamental-review-thesis-breakers": {
                    "stock_id": "2303",
                    "action_id": "fundamental-review-thesis-breakers",
                    "status": "done",
                    "note": "checked",
                    "reviewer": "alice",
                    "evidence_url": "",
                    "updated_at": "2026-07-20T09:00:00Z",
                },
            },
        }
        html = render_workbench_view(data)
        self.assertIn(
            'data-stock="2330" data-priority="high"'
            ' data-severity="manual_review" data-category="fundamental_review"'
            ' data-status="done" data-requires-evidence="true"'
            ' data-has-evidence="true">',
            html,
        )
        self.assertIn(
            'data-stock="2303" data-priority="medium"'
            ' data-severity="manual_review" data-category="fundamental_review"'
            ' data-status="done" data-requires-evidence="true"'
            ' data-has-evidence="false">',
            html,
        )

    def test_bulk_toolbar_renders_ported_controls_and_count(self):
        html = render_workbench_view(_RS)
        self.assertIn('data-queue-bulk-tools="true"', html)
        self.assertIn("選取目前顯示", html)          # ported label, dashboard.py:2976
        self.assertIn("批次標記完成", html)          # ported label, dashboard.py:2977
        self.assertIn("批次稍後處理", html)          # ported label, dashboard.py:2978
        self.assertIn("已選取 0 筆", html)           # ported count wording, dashboard.py:2979

    def test_bulk_controls_static_mode_copy_wiring_served_mode_api_hooks(self):
        static_html = render_workbench_view(_RS, action_api_enabled=False)
        # Static mode: each row's checkbox carries pre-baked multi-line-ready
        # CLI commands (same format as _review_action_command) for both bulk
        # statuses; bulk buttons carry no action-api hook.
        self.assertIn('data-command-done="', static_html)
        self.assertIn('data-command-deferred="', static_html)
        self.assertIn(
            "python -m taiwan_stock_analysis.cli research action set",
            static_html,
        )
        self.assertNotIn('data-action-api="bulk-review-action"', static_html)

        api_html = render_workbench_view(_RS, action_api_enabled=True)
        self.assertIn('data-action-api="bulk-review-action"', api_html)
        self.assertIn('data-queue-bulk-status="done"', api_html)
        self.assertIn('data-queue-bulk-status="deferred"', api_html)
        self.assertNotIn("data-command-done", api_html)
        self.assertNotIn("data-command-deferred", api_html)

    # -- Feature D: 狀態資訊 stale count + last-updated (spec 3.3, ported
    # vocabulary from dashboard.py:_review_action_status_pairs ~2924 and the
    # status-line badges in _review_actions_section ~2664-2669) ------------

    def test_status_line_shows_four_counts_stale_and_last_updated_placeholder(self):
        # _RS carries no review_action_state sidecar at all -> every action is
        # "open" and last_updated must degrade to the "-" placeholder, never
        # "None" or a crash.
        html = render_workbench_view(_RS)
        self.assertIn("待處理 11", html)
        self.assertIn("已完成 0", html)
        self.assertIn("稍後處理 0", html)
        self.assertIn("不處理 0", html)
        self.assertIn("過期狀態 0", html)
        self.assertIn("最後更新：-", html)
        self.assertNotIn("None", html)

    def test_status_line_shows_real_state_counts_stale_and_timestamp(self):
        data = copy.deepcopy(_RS)
        data["research_summaries"][0]["review_action_state"] = {
            "version": 1,
            "actions": {
                "2330:fundamental-review-thesis-breakers": {
                    "stock_id": "2330",
                    "action_id": "fundamental-review-thesis-breakers",
                    "status": "done",
                    "note": "",
                    "reviewer": "",
                    "evidence_url": "",
                    "updated_at": "2026-07-20T09:00:00Z",
                },
                # Stale: this stock/action pair no longer appears in
                # review_action_queue, so it must be counted as stale rather
                # than silently overlaid.
                "2330:retired-action": {
                    "stock_id": "2330",
                    "action_id": "retired-action",
                    "status": "done",
                    "note": "",
                    "reviewer": "",
                    "evidence_url": "",
                    "updated_at": "2026-07-21T09:00:00Z",
                },
            },
        }
        html = render_workbench_view(data)
        self.assertIn("待處理 10", html)
        self.assertIn("已完成 1", html)
        self.assertIn("過期狀態 1", html)
        self.assertIn("最後更新：2026-07-21T09:00:00Z", html)


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

    def test_hidden_queue_row_css_hides_paired_expand(self):
        # Regression: workbench.py emits .queue-expand as the immediate next
        # sibling of its .queue-row. Filtering only toggled .hidden on the row
        # itself, leaving an expanded row's detail panel floating after the
        # row disappeared (Bug 1). Fixed via an adjacent-sibling CSS rule.
        html = render_page(self._items())
        self.assertIn(".queue-row.hidden + .queue-expand", html)

    def test_inline_script_has_bulk_and_single_row_evidence_guards(self):
        # CRITICAL fix regression test: the shipped inline <script> must read
        # the new per-row evidence flags and refuse to silently drop evidence-
        # required rows -- both the bulk skip-and-report path and the single-
        # row served refuse-and-flash path (restoring the pre-redesign guard
        # message).
        html = render_page(self._items())
        self.assertIn("data-requires-evidence", html)
        self.assertIn("data-has-evidence", html)
        self.assertIn("筆需要交付證據，已略過", html)
        self.assertIn("需要 note、reviewer、evidence URL 才能更新這個交付前 blocker。", html)
