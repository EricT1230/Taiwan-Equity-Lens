import unittest

from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view

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
