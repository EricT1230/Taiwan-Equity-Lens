import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from taiwan_stock_analysis.dashboard import render_dashboard_html
from taiwan_stock_analysis.dashboard_ui.page import render as render_page
from taiwan_stock_analysis.dashboard_ui.product_data import delivery_status, market_snapshot, stock_rows
from taiwan_stock_analysis.dashboard_ui.views.intelligence import render_intelligence_view
from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view
from taiwan_stock_analysis.dashboard_ui.views.overview import render_overview_view
from taiwan_stock_analysis.dashboard_ui.views.screener import render_screener_view
from taiwan_stock_analysis.dashboard_ui.views.strategy import render_strategy_view


ITEMS = {
    "market_intelligence_reports": [
        {
            "generated_at": "2026-07-29T14:30:00+08:00",
            "quality_gate": {"status": "ready", "blocker_count": 0},
            "freshness": {
                "news": {"status": "fresh"},
                "fund_flow": {"status": "fresh"},
                "industry_trend": {"status": "fresh"},
            },
            "industries": [
                {
                    "category": "半導體",
                    "stock_ids": ["2330"],
                    "sentiment": {"score_5d": 62.0, "change": 3.5},
                    "fund_flow": {"total_net": 1800},
                    "latest_news": [
                        {
                            "title": "AI 供應鏈事件",
                            "summary": "公司公告摘要",
                            "source": "TWSE",
                            "published_at": "2026-07-29T13:00:00+08:00",
                            "url": "https://example.com/news",
                            "matched_stock_ids": ["2330"],
                            "matched_categories": ["半導體"],
                        }
                    ],
                }
            ],
            "news": [
                {
                    "title": "AI 供應鏈事件",
                    "summary": "公司公告摘要",
                    "source": "TWSE",
                    "published_at": "2026-07-29T13:00:00+08:00",
                    "url": "https://example.com/news",
                    "matched_stock_ids": ["2330"],
                    "matched_categories": ["半導體"],
                }
            ],
        }
    ],
    "industry_trend_reports": [
        {
            "as_of_date": "2026-07-29",
            "categories": [
                {
                    "category": "半導體",
                    "average_return_5d": 4.2,
                    "average_return_1d": 1.0,
                    "average_return_20d": 8.0,
                }
            ],
        }
    ],
    "research_summaries": [
        {
            "path": "research_summary.json",
            "items": [
                {
                    "stock_id": "2330",
                    "company_name": "台積電",
                    "category": "半導體",
                    "official_market": "TWSE",
                    "priority": "high",
                    "research_state": "review",
                    "market_return_1d": "+1.0%",
                    "market_return_5d": "+4.2%",
                    "market_return_20d": "+8.0%",
                    "market_volume_signal": "量能擴張",
                    "thesis": "先進製程需求",
                    "key_risks": "資本支出與估值",
                    "reliability_status": "ok",
                    "fundamental_review": {
                        "score": 84,
                        "agent_scores": {
                            "buffett_moat": 90,
                            "fundamental_quality": 84,
                            "bear_case_risk": 72,
                            "valuation_margin_of_safety": 68,
                        },
                    },
                }
            ],
            "review_action_queue": [],
        }
    ],
    "workflow_summaries": [],
    "reports": [],
    "comparisons": [],
    "batch_summaries": [],
    "memo_outputs": [],
    "pack_outputs": [],
}


def mixed_mode_items() -> dict[str, list[dict[str, object]]]:
    demo_report = {
        "kind": "market_intelligence_report",
        "path": "examples/DEMO_SENTINEL_PATH.json",
        "generated_at": "2026-08-28T06:00:00Z",
        "provenance": {
            "source": "TWSE",
            "status": "EOD",
            "observed_at": "2026-08-28T06:00:00Z",
        },
        "news": [
            {
                "title": "DEMO_SENTINEL_NEWS",
                "summary": "Demo-only story",
                "source": "synthetic-demo",
                "source_mode": "fixture",
                "published_at": "2026-08-28T05:00:00Z",
                "url": "https://example.com/DEMO_SENTINEL_URL",
            }
        ],
    }
    official_report = {
        "kind": "market_intelligence_report",
        "generated_at": "2026-08-28T06:00:00Z",
        "provenance": {
            "source": "TWSE",
            "status": "EOD",
            "observed_at": "2026-08-28T06:00:00Z",
        },
        "news": [
            {
                "title": "OFFICIAL_SENTINEL_NEWS",
                "summary": "Official exchange story",
                "source": "TWSE",
                "published_at": "2026-08-28T05:00:00Z",
                "url": "https://www.twse.com.tw/OFFICIAL_SENTINEL_URL",
            }
        ],
    }
    return {
        "market_intelligence_reports": [demo_report, official_report],
        "industry_trend_reports": [],
        "research_summaries": [],
        "workflow_summaries": [],
        "reports": [],
        "comparisons": [],
        "batch_summaries": [],
        "memo_outputs": [],
        "pack_outputs": [],
        "handoff_pack_outputs": [],
        "market_data_reports": [],
    }


class ProductDataTests(unittest.TestCase):
    def test_market_snapshot_derives_regime_and_freshness(self):
        snapshot = market_snapshot(
            ITEMS,
            now=datetime(2026, 7, 29, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(snapshot["regime"], "偏多擴散")
        self.assertEqual(snapshot["fresh_count"], 3)
        self.assertEqual(snapshot["industry_count"], 1)
        self.assertEqual(snapshot["delivery_status"], "EOD")

    def test_market_snapshot_uses_minus_100_to_100_sentiment_contract(self):
        items = deepcopy(ITEMS)
        items["market_intelligence_reports"][0]["industries"][0]["sentiment"]["score_5d"] = 29.0
        snapshot = market_snapshot(
            items,
            now=datetime(2026, 7, 29, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(snapshot["regime"], "偏多擴散")
        self.assertEqual(snapshot["temperature"], 64.5)

    def test_market_snapshot_fails_closed_for_stale_or_malformed_gate(self):
        items = deepcopy(ITEMS)
        items["market_intelligence_reports"][0]["quality_gate"]["blocker_count"] = "unknown"
        snapshot = market_snapshot(
            items,
            now=datetime(2026, 8, 2, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(snapshot["regime"], "資料已過期")
        self.assertEqual(snapshot["delivery_status"], "STALE")
        self.assertEqual(snapshot["fresh_count"], 0)
        self.assertEqual(snapshot["blocker_count"], 0)

    def test_delivery_status_keeps_friday_eod_valid_over_weekend(self):
        status = delivery_status(
            "2026-07-31T20:00:00+08:00",
            now=datetime(2026, 8, 2, 12, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(status, "EOD")

    def test_delivery_status_maps_preclose_generation_to_previous_session(self):
        status = delivery_status(
            "2026-08-03T12:00:00+08:00",
            now=datetime(2026, 8, 3, 20, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(status, "STALE")

    def test_delivery_status_keeps_post_close_snapshot_valid_after_20_00(self):
        status = delivery_status(
            "2026-08-03T14:30:00+08:00",
            now=datetime(2026, 8, 3, 20, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertEqual(status, "EOD")

    def test_stock_rows_explain_bull_classification(self):
        rows = stock_rows(ITEMS)
        self.assertEqual(rows[0]["stock_id"], "2330")
        self.assertIn("bull", rows[0]["tags"])
        self.assertEqual(rows[0]["score"], 84)
        self.assertIn("5D 報酬", rows[0]["reasons"]["bull"])

    def test_unknown_market_and_missing_returns_do_not_invent_us_or_bear(self):
        items = deepcopy(ITEMS)
        stock = items["research_summaries"][0]["items"][0]
        stock.update(
            {
                "stock_id": "UNKNOWN",
                "official_market": "",
                "market_return_1d": "",
                "market_return_5d": "",
                "market_return_20d": "",
                "priority": "medium",
            }
        )
        rows = stock_rows(items)
        self.assertEqual(rows[0]["market"], "未確認")
        self.assertNotIn("us", rows[0]["tags"])
        self.assertNotIn("bear", rows[0]["tags"])

    def test_flat_twenty_day_return_remains_directionally_unclassified(self):
        items = deepcopy(ITEMS)
        stock = items["research_summaries"][0]["items"][0]
        stock.update(
            {
                "market_return_5d": "",
                "market_return_20d": "0%",
                "priority": "medium",
            }
        )
        tags = stock_rows(items)[0]["tags"]
        self.assertNotIn("bull", tags)
        self.assertNotIn("bear", tags)

    def test_missing_fund_flow_stays_missing_instead_of_zero(self):
        items = deepcopy(ITEMS)
        items["market_intelligence_reports"][0]["industries"][0].pop("fund_flow")
        snapshot = market_snapshot(
            items,
            now=datetime(2026, 7, 29, 15, 0, tzinfo=timezone(timedelta(hours=8))),
        )
        self.assertIsNone(snapshot["flow_total"])


class ProductViewTests(unittest.TestCase):
    def test_production_render_admits_official_sibling_and_removes_demo_content(self):
        html = render_dashboard_html(
            mixed_mode_items(),
            data_mode="production",
            now=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIn('data-data-mode="production"', html)
        self.assertIn('data-admission-rejected-count="1"', html)
        self.assertIn("OFFICIAL_SENTINEL_NEWS", html)
        self.assertNotIn("DEMO_SENTINEL_NEWS", html)
        self.assertNotIn("DEMO_SENTINEL_PATH", html)
        self.assertNotIn("DEMO_SENTINEL_URL", html)

    def test_demo_render_preserves_demo_content_and_has_visible_mode_label(self):
        html = render_dashboard_html(
            mixed_mode_items(),
            data_mode="demo",
            now=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIn('data-data-mode="demo"', html)
        self.assertIn('data-admission-rejected-count="0"', html)
        self.assertIn("Demo 模式", html)
        self.assertIn("DEMO_SENTINEL_NEWS", html)
        self.assertIn("DEMO_SENTINEL_URL", html)

    def test_production_render_uses_injected_now_for_freshness(self):
        items = mixed_mode_items()
        items["market_intelligence_reports"] = [items["market_intelligence_reports"][1]]

        html = render_dashboard_html(
            items,
            data_mode="production",
            now=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc),
        )

        self.assertIn('data-data-mode="production"', html)
        self.assertIn('data-admission-rejected-count="1"', html)
        self.assertNotIn("OFFICIAL_SENTINEL_NEWS", html)
        self.assertNotIn("OFFICIAL_SENTINEL_URL", html)

    def test_overview_renders_guided_flow_and_source_time(self):
        html = render_overview_view(ITEMS)
        self.assertIn("今天只做三件事", html)
        self.assertIn("看氣氛", html)
        self.assertIn("2026-07-29 14:30", html)
        self.assertIn('data-jump-tab="screener"', html)
        self.assertIn("1,800 股", html)
        self.assertNotIn("1,800 張", html)

    def test_screener_has_required_product_filters_and_traceability_note(self):
        html = render_screener_view(ITEMS)
        for label in ("上漲", "下跌", "處置", "選產業", "美股"):
            self.assertIn(label, html)
        self.assertIn('data-stock-key="2330"', html)
        self.assertIn('data-base-screener-tags=', html)
        self.assertIn('data-live-stock-price="true"', html)
        self.assertIn('data-screener-reason="true"', html)
        self.assertIn("5D 報酬 +4.2%", html)
        self.assertIn("每個命中都要能追溯", html)
        self.assertIn("不構成買賣建議", html)
        self.assertIn("FINRA 場外短售成交比不是 short interest", html)

    def test_connected_screener_does_not_publish_fixture_history_as_current(self):
        html = render_screener_view(ITEMS, live_api_enabled=True)
        self.assertNotIn("5D 報酬 +4.2%", html)
        self.assertNotIn(">+4.2%<", html)
        self.assertNotIn(">+8.0%<", html)
        self.assertIn("未接妥正式歷史行情前", html)
        self.assertIn('data-live-stock-change="true">--</span>', html)

    def test_connected_market_view_blocks_synthetic_reports(self):
        html = render_market_view(ITEMS, live_api_enabled=True)
        self.assertIn("已封鎖合成示範資料", html)
        self.assertIn("已封鎖範例價格序列", html)
        self.assertNotIn("https://example.com/news", html)

    def test_intelligence_has_news_fundamentals_and_local_note(self):
        html = render_intelligence_view(ITEMS)
        self.assertIn("新聞與事件", html)
        self.assertIn("財報與研究摘要", html)
        self.assertIn("研究資料：", html)
        self.assertIn("分數只代表檢查完成度與規則結果", html)
        self.assertIn('data-market-note="true"', html)
        self.assertIn("AI 供應鏈事件", html)

    def test_strategy_discloses_requirements_and_invalidation(self):
        html = render_strategy_view(ITEMS)
        self.assertIn("啟用前提", html)
        self.assertIn("失效條件", html)
        self.assertIn("成本與偏誤", html)
        self.assertIn("不是黑箱明牌", html)
        self.assertIn('data-live-strategy-gate="true"', html)
        self.assertIn('data-live-strategy-mode="true"', html)
        self.assertIn('data-strategy-research-mode="true"', html)
        self.assertIn("研究：", html)

    def test_strategy_does_not_pass_a_missing_gate(self):
        self.assertIn("尚無資料品質 Gate", render_strategy_view({}))
        self.assertNotIn("Gate 已通過", render_strategy_view({}))

    def test_full_page_has_original_workbench_and_new_product_shell(self):
        html = render_page(ITEMS)
        self.assertIn("盤勢鏡", html)
        self.assertIn('id="overview"', html)
        self.assertIn('id="market"', html)
        self.assertIn('id="screener"', html)
        self.assertIn('id="intelligence"', html)
        self.assertIn('id="strategy"', html)
        self.assertIn('id="workbench"', html)
        self.assertIn('id="outputs"', html)
        self.assertIn('var DEFAULT_TAB = "overview"', html)
        self.assertIn('data-storage-namespace="2026-07-29T14:30:00+08:00"', html)
        self.assertIn('storageKey("market-note")', html)
        self.assertIn('data-live-api-enabled="false"', html)
        self.assertIn("目前是靜態檔案", html)

    def test_served_page_connects_same_origin_live_market_api(self):
        html = render_page(ITEMS, action_api_enabled=True)
        self.assertIn('data-live-api-enabled="true"', html)
        self.assertIn('data-live-connection="true"', html)
        self.assertIn("/api/live/snapshot?symbols=", html)
        self.assertIn("今日收盤行情可用", html)
        self.assertIn("data-research-gate-ready", html)
        self.assertIn("部分自選行情未取得", html)
        self.assertIn("snapshot.missing_symbols", html)
        self.assertIn("自選行情只完成部分同步", html)
        self.assertIn("quoteComplete", html)
        self.assertIn("symbols.slice(0, liveSymbolLimit)", html)
        self.assertIn('response.headers.get("Retry-After")', html)
        self.assertIn("if (document.hidden)", html)
        self.assertIn("分頁隱藏，已暫停更新", html)
        self.assertIn("initLiveMarket();", html)

    def test_research_only_run_id_namespaces_local_storage(self):
        items = deepcopy(ITEMS)
        items["market_intelligence_reports"] = []
        items["research_summaries"][0]["run_metadata"] = {"run_id": "research-run-42"}
        html = render_page(items)
        self.assertIn('data-storage-namespace="research-run-42"', html)


if __name__ == "__main__":
    unittest.main()
