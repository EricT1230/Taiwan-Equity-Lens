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
        self.assertIn('data-copy="python -m taiwan_stock_analysis.cli 2330', html)
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

        self.assertIn("個股報告", html)
        self.assertIn("2330_analysis.html", html)
        self.assertIn("2303_analysis.html", html)
        self.assertIn("同業比較", html)
        self.assertIn("missing fixture", html)
        self.assertIn("失敗 1", html)
        self.assertIn("成功 1", html)
        self.assertIn("data:text/csv", html)
        self.assertIn("python -m taiwan_stock_analysis.cli compare", html)
        self.assertIn("python -m taiwan_stock_analysis.cli batch", html)
        self.assertIn("Workflow 狀態", html)
        self.assertIn("成功 1 / 2", html)
        self.assertIn("同業比較略過：fewer than two successful stocks", html)
        self.assertIn("workflow-dist/workflow_summary.json", html)
        self.assertIn("run-dashboard-workflow", html)
        self.assertIn("workflow-dist/valuation.csv", html)
        self.assertIn("2330", html)
        self.assertIn("資料可信度", html)
        self.assertIn("整體：error", html)
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

        self.assertIn("來源稽核", html)
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

        self.assertIn("來源稽核", html)
        self.assertIn("5: 2, fresh&lt;: 1&amp;", html)

    def test_render_dashboard_html_shows_clear_empty_states(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
            }
        )

        self.assertIn("尚未產生個股報告", html)
        self.assertIn("尚未產生同業比較", html)
        self.assertIn("尚未有批次結果", html)
        self.assertIn("尚未有 workflow summary", html)

    def test_render_dashboard_html_shows_invalid_workflow_summary_status(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [{"path": "workflow_summary.json", "error": "invalid JSON"}],
            }
        )

        self.assertIn("Workflow 狀態", html)
        self.assertIn("workflow_summary.json", html)
        self.assertIn("<td>invalid JSON</td>", html)

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

    def test_discover_dashboard_items_finds_industry_trend_reports(self):
        root = Path(".tmp-cli-test/dashboard-industry-trends")
        trend_dir = root / "industry-trends"
        trend_dir.mkdir(parents=True, exist_ok=True)
        (trend_dir / "industry_trend_report.json").write_text(
            json.dumps(
                {
                    "quality_gate": {"status": "ready"},
                    "coverage": {"stocks_total": 2, "stocks_with_price_history": 2},
                    "categories": [{"category": "Semiconductor", "direction": "up"}],
                }
            ),
            encoding="utf-8",
        )
        (trend_dir / "industry_trend_report.md").write_text("# Industry Trend Report", encoding="utf-8")
        (trend_dir / "industry_trend_report.html").write_text("<html>trend</html>", encoding="utf-8")

        items = discover_dashboard_items([root])

        self.assertIn("industry_trend_reports", items)
        self.assertEqual(len(items["industry_trend_reports"]), 1)
        report = items["industry_trend_reports"][0]
        self.assertEqual(report["path"], str(trend_dir / "industry_trend_report.json"))
        self.assertEqual(report["markdown_path"], str(trend_dir / "industry_trend_report.md"))
        self.assertEqual(report["html_path"], str(trend_dir / "industry_trend_report.html"))
        self.assertEqual(report["quality_gate"]["status"], "ready")

    def test_render_dashboard_html_contains_industry_trend_report(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "industry_trend_reports": [
                    {
                        "path": "research-dist/industry-trends/industry_trend_report.json",
                        "markdown_path": "research-dist/industry-trends/industry_trend_report.md",
                        "html_path": "research-dist/industry-trends/industry_trend_report.html",
                        "as_of_date": "2026-05-29",
                        "coverage": {
                            "stocks_total": 2,
                            "stocks_with_price_history": 2,
                            "missing_price_history": 0,
                        },
                        "quality_gate": {
                            "status": "ready",
                            "next_action": "Review the strongest and weakest sector trend evidence.",
                        },
                        "categories": [
                            {
                                "category": "Semiconductor",
                                "direction": "up",
                                "rotation_phase": "leading",
                                "stock_count": 2,
                                "coverage_count": 2,
                                "missing_count": 0,
                                "average_return_1d": 0.5,
                                "average_return_5d": 2.5,
                                "average_return_20d": 8.0,
                                "average_volume_ratio_5d": 1.3,
                                "leading_stocks": [{"stock_id": "2330", "return_20d": 12.0}],
                                "lagging_stocks": [{"stock_id": "2303", "return_20d": 2.0}],
                            }
                        ],
                        "non_advice_notice": "This output is not investment advice.",
                    }
                ],
            }
        )

        self.assertIn('data-market-rotation-section="true"', html)
        self.assertIn("<h4>Semiconductor</h4>", html)
        self.assertIn("輪動偏強", html)  # direction "up" localized
        self.assertIn("leading", html)  # rotation_phase raw text
        self.assertIn("20D", html)
        self.assertIn("+8.0%", html)
        self.assertIn("2330", html)
        self.assertIn("+12.0%", html)
        self.assertIn("2303", html)
        self.assertIn("+2.0%", html)

    def test_discover_dashboard_items_finds_market_intelligence_report(self):
        root = Path(".tmp-cli-test/dashboard-market-intelligence")
        report_dir = root / "market-intelligence"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "market_intelligence_report.json").write_text(
            json.dumps(
                {
                    "quality_gate": {"status": "ready"},
                    "coverage": {"industries_total": 1},
                    "industries": [{"category": "Semiconductor"}],
                }
            ),
            encoding="utf-8",
        )
        (report_dir / "market_intelligence_report.md").write_text("# report", encoding="utf-8")
        (report_dir / "market_intelligence_report.html").write_text("<html></html>", encoding="utf-8")

        items = discover_dashboard_items([root])

        self.assertEqual(len(items["market_intelligence_reports"]), 1)
        report = items["market_intelligence_reports"][0]
        self.assertEqual(report["path"], str(report_dir / "market_intelligence_report.json"))
        self.assertEqual(report["quality_gate"]["status"], "ready")

    def test_render_dashboard_html_contains_market_intelligence_map(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "market_intelligence_reports": [
                    {
                        "path": "research-dist/market-intelligence/market_intelligence_report.json",
                        "markdown_path": "research-dist/market-intelligence/market_intelligence_report.md",
                        "html_path": "research-dist/market-intelligence/market_intelligence_report.html",
                        "quality_gate": {"status": "ready", "blockers": []},
                        "freshness": {
                            "news": {"status": "fresh"},
                            "fund_flow": {"status": "fresh"},
                            "industry_trend": {"status": "fresh"},
                        },
                        "coverage": {
                            "news_total": 2,
                            "news_mapped": 2,
                            "stocks_total": 2,
                            "stocks_with_fund_flow": 2,
                            "industries_total": 1,
                        },
                        "industries": [
                            {
                                "category": "Legacy Partial <script>alert(1)</script>",
                                "market_trend": {"direction": "mixed"},
                                "news_count": 0,
                                "top_keywords": [],
                                "fund_flow": {"direction": "missing"},
                                "latest_news": [],
                                "sentiment": {
                                    "status": "partial",
                                    "score_5d": None,
                                    "baseline_20d": None,
                                    "change": None,
                                    "temperature": "stable",
                                    "label": "neutral",
                                    "cycle_phase": "insufficient_history",
                                    "confidence": "medium",
                                    "components": {
                                        "news": {
                                            "configured_weight": 0.4,
                                            "effective_weight": 0.5714,
                                            "contribution_5d": None,
                                        }
                                    },
                                    "forecast": {
                                        "status": "insufficient_history",
                                        "forecast_1d": None,
                                        "forecast_5d": None,
                                        "warnings": [],
                                    },
                                    "turning_risk": {
                                        "status": "insufficient_history",
                                        "peak_risk": None,
                                        "trough_risk": None,
                                        "warnings": [],
                                    },
                                    "reasons": [],
                                    "warnings": [
                                        "fund_flow removed <img src=x onerror=alert(1)>"
                                    ],
                                },
                            },
                            {
                                "category": "Semiconductor",
                                "market_trend": {"direction": "up"},
                                "news_count": 2,
                                "top_keywords": ["AI", "伺服器"],
                                "fund_flow": {
                                    "foreign_net": 1000,
                                    "investment_trust_net": 200,
                                    "dealer_net": -50,
                                    "total_net": 1150,
                                    "direction": "net_inflow",
                                },
                                "latest_news": [
                                    {
                                        "title": "台積電 AI 伺服器需求增溫",
                                        "url": "https://example.test/news",
                                    }
                                ],
                                "sentiment": {
                                    "status": "ready",
                                    "score_5d": 34.2,
                                    "baseline_20d": 21.0,
                                    "change": 13.2,
                                    "temperature": "warming",
                                    "label": "optimistic",
                                    "cycle_phase": "expansion",
                                    "confidence": "high",
                                    "components": {
                                        "news": {
                                            "configured_weight": 0.4,
                                            "effective_weight": 0.4,
                                            "contribution_5d": 12.5,
                                        },
                                        "price": {
                                            "configured_weight": 0.3,
                                            "effective_weight": 0.3,
                                            "contribution_5d": 10.2,
                                        },
                                        "fund_flow": {
                                            "configured_weight": 0.3,
                                            "effective_weight": 0.3,
                                            "contribution_5d": 11.5,
                                        },
                                    },
                                    "forecast": {
                                        "status": "experimental",
                                        "forecast_1d": 35.5,
                                        "forecast_5d": 40.0,
                                        "interval_1d": [31.0, 40.0],
                                        "interval_5d": [20.0, 60.0],
                                        "warnings": ["forecast warning"],
                                    },
                                    "turning_risk": {
                                        "status": "experimental",
                                        "peak_risk": 72.0,
                                        "trough_risk": 18.0,
                                        "warnings": ["turning warning"],
                                    },
                                    "reasons": [
                                        "news contribution +12.5",
                                        "price contribution +10.2",
                                        "flow contribution +11.5",
                                        "fourth reason must be omitted",
                                    ],
                                    "warnings": ["confidence warning"],
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn('data-market-sentiment-section="true"', html)
        self.assertIn("<h4>Semiconductor</h4>", html)
        self.assertIn("台積電 AI 伺服器需求增溫", html)
        self.assertIn("1,150", html)
        self.assertIn('<span class="mkt-score mono">34.2</span>', html)
        self.assertIn('<span class="mkt-delta mono up">+13.2</span>', html)
        self.assertIn("20D 基準 21.0", html)
        self.assertIn("資料完整", html)  # sentiment.status "ready"
        self.assertIn("擴張", html)  # cycle_phase "expansion" localized
        self.assertIn("信心：高", html)
        self.assertIn("chart-spark", html)
        self.assertEqual(html.count('class="chart-contrib-row"'), 6)  # 3 rows x 2 industries
        self.assertIn("AI", html)
        self.assertIn("伺服器", html)
        self.assertIn('data-market-rotation-section="true"', html)
        self.assertIn("尚未產生產業輪動報告", html)  # no industry_trend_reports supplied
        # Partial/insufficient-history industry: status + phase localize, sparkline
        # falls back to the "insufficient history" placeholder.
        self.assertIn("資料不完整", html)
        self.assertIn("歷史資料不足", html)
        self.assertIn("信心：中", html)
        # Escaping: hostile category name is neutralized either way.
        self.assertIn("Legacy Partial &lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x onerror=alert(1)>", html)
        self.assertNotIn("<canvas", html)
        # Default sort still favors industries with a real score over ones without.
        self.assertLess(
            html.index("<h4>Semiconductor</h4>"),
            html.index("<h4>Legacy Partial"),
        )
        self.assertNotIn("<canvas", html)

    def test_discover_and_render_dashboard_market_data_report(self):
        root = Path(".tmp-cli-test/dashboard-market-data")
        report_dir = root / "market-data"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "market_data_report.json").write_text(
            json.dumps(
                {
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
            ),
            encoding="utf-8",
        )
        (report_dir / "market_data_report.md").write_text("# report", encoding="utf-8")

        items = discover_dashboard_items([root])
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "market_data_reports": items["market_data_reports"],
            }
        )

        self.assertEqual(len(items["market_data_reports"]), 1)
        self.assertIn('data-outputs-market-data-section="true"', html)
        self.assertIn("Market Data — 2026-07-12", html)
        self.assertIn("quality gate: ready", html)
        self.assertIn('class="table-scroll"', html)
        self.assertIn('class="mini-table"', html)
        self.assertIn(".table-scroll { overflow-x: auto; }", html)
        self.assertIn("TPEX", html)
        self.assertIn("半導體業", html)
        self.assertIn("42", html)

    def test_render_dashboard_localizes_consolidation_sentiment_phase(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "market_intelligence_reports": [
                    {
                        "quality_gate": {"status": "ready", "blockers": []},
                        "industries": [
                            {
                                "category": "Semiconductor",
                                "sentiment": {
                                    "status": "ready",
                                    "score_5d": 0.0,
                                    "baseline_20d": 0.0,
                                    "change": 0.0,
                                    "temperature": "stable",
                                    "label": "neutral",
                                    "cycle_phase": "consolidation",
                                    "confidence": "high",
                                    "components": {},
                                    "forecast": {
                                        "status": "insufficient_history",
                                        "warnings": [],
                                    },
                                    "turning_risk": {
                                        "status": "insufficient_history",
                                        "warnings": [],
                                    },
                                    "reasons": [],
                                    "warnings": [],
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn('<span class="ui-pill ui-pill-info">盤整</span>', html)
        self.assertNotIn("consolidation", html)

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

        # NOTE: research-summary-level traceability (run_metadata.run_id,
        # artifact_registry, workflow_summary_path/workflow_paths, counts) is no
        # longer surfaced anywhere in the redesigned dashboard -- only the flat
        # `items[]` research pool survives, via the workbench's single 研究池 table
        # (flagged as a concern in the task-11 report). This fixture keeps those
        # untouched fields to prove they don't break rendering; the assertions
        # below cover what the pool table actually renders.
        self.assertIn("研究工作台", html)
        self.assertIn("2330", html)
        self.assertIn("TSMC &lt;Leader&gt;", html)
        self.assertNotIn("TSMC <Leader>", html)
        self.assertIn("research state requires review", html)
        self.assertIn('<span class="ui-badge ui-badge-blocked">高</span>', html)  # priority "high"
        self.assertIn("2303", html)
        self.assertIn("UMC", html)
        self.assertIn(">watching<", html)

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
                            "by_category": {"fundamental_review": 1, "source_audit": 1, "valuation": 1},
                            "by_severity": {"manual_review": 1, "warning": 2},
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
                                    },
                                    {
                                        "id": "fundamental-review-low-quality",
                                        "category": "fundamental_review",
                                        "severity": "warning",
                                        "message": "Review weak expert fundamental checks before handoff.",
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

        # NOTE: bulk select/mark tools, the state-health/stale-count/last-updated
        # summary line, and the "重新開啟" (reopen) action are not present anywhere
        # in the redesigned workbench queue -- flagged as concerns in the task-11
        # report (§10 of the design spec calls for preserving 狀態計數與 stale 提示
        # and batch operations, but views/workbench.py does not implement them).
        self.assertIn("交接 GATE", html)
        self.assertIn("審查佇列", html)
        self.assertIn('<strong id="wb-gate-blockers">2</strong>', html)
        self.assertIn("尚有 2 件待交接阻塞", html)
        self.assertIn('data-queue-filter="severity"', html)
        self.assertIn('data-queue-filter="category"', html)
        self.assertIn('data-queue-filter="priority"', html)
        self.assertIn('data-queue-filter="status"', html)
        self.assertIn('data-queue-filter="search"', html)
        self.assertIn("共 2 筆（依優先度 → 嚴重度排序）。", html)
        self.assertIn("需人工確認", html)
        self.assertIn("來源檢查", html)
        self.assertIn("2330", html)
        self.assertIn("Review source audit: fixture source", html)
        self.assertIn('class="queue-row next"', html)
        self.assertIn('data-stock="2330"', html)
        self.assertIn('data-priority="high"', html)
        self.assertIn('data-status="open"', html)
        self.assertIn('data-severity="manual_review"', html)
        self.assertIn('data-category="source_audit"', html)
        self.assertIn('data-category="fundamental_review"', html)
        self.assertIn("基本面專家審查", html)
        self.assertIn("fundamental-review-low-quality", html)
        self.assertIn('class="queue-expand"', html)
        self.assertIn('data-expand-for="wb-row-0"', html)
        self.assertIn(">標記完成</button>", html)
        self.assertIn(">稍後處理</button>", html)
        self.assertIn(">不處理</button>", html)
        self.assertIn("靜態模式：按下後複製 CLI 指令", html)
        self.assertIn(
            "research action set research-dist/review_action_state.json 2330 "
            "source-audit-manual-review --status done",
            html,
        )
        self.assertIn(
            "research action set research-dist/review_action_state.json 2330 "
            "fundamental-review-low-quality --status deferred",
            html,
        )

    def test_render_dashboard_html_contains_expert_agent_console_guided_flow(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_state": {
                            "version": 1,
                            "actions": {
                                "2330:source-audit-manual-review": {
                                    "status": "done",
                                    "updated_at": "2026-05-20T01:00:00Z",
                                }
                            },
                        },
                        "review_action_summary": {
                            "total_open": 4,
                            "by_category": {
                                "source_audit": 1,
                                "fundamental_review": 1,
                                "reliability": 1,
                                "valuation": 1,
                            },
                            "by_severity": {"manual_review": 1, "warning": 3},
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
                                    },
                                    {
                                        "id": "fundamental-review-low-quality",
                                        "category": "fundamental_review",
                                        "severity": "warning",
                                        "message": "Review weak expert fundamental checks before handoff.",
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
                                ],
                            }
                        ],
                        "items": [],
                    }
                ],
                "memo_outputs": [],
                "pack_outputs": [],
            }
        )

        # The old expert-console guided flow (Top 3, focus-jump, bulk controls) is
        # merged away per design spec §3.5 -- what survives is the unified queue's
        # gate card (same blocker math from handoff.py) + its top "next" row.
        self.assertIn("交接 GATE", html)
        self.assertIn('<strong id="wb-gate-blockers">4</strong>', html)
        self.assertIn("1 / 4 已處理", html)
        self.assertIn("尚有 4 件待交接阻塞", html)
        self.assertIn("產出 Evidence Pack", html)
        self.assertIn(
            'data-copy="python -m taiwan_stock_analysis.cli research handoff-pack '
            "research-dist/research_summary.json --state research-dist/review_action_state.json "
            '--output-dir research-dist/handoff-pack"',
            html,
        )
        self.assertIn("審查佇列", html)
        self.assertIn('class="queue-row next"', html)
        self.assertIn('data-status="done"', html)  # state overlay marks source-audit-manual-review done
        self.assertIn('<span class="ui-badge ui-badge-ok">已完成</span>', html)
        self.assertIn('<span class="wb-next-tag">建議下一步</span>', html)
        self.assertIn("基本面專家審查", html)
        self.assertIn("資料可信度", html)
        self.assertIn("估值", html)
        self.assertIn("共 4 筆（依優先度 → 嚴重度排序）。", html)
        self.assertIn(
            "research action set research-dist/review_action_state.json 2330 "
            "fundamental-review-low-quality --status done",
            html,
        )
        self.assertIn("研究池", html)
        self.assertIn("尚無研究項目", html)

    def test_render_dashboard_html_expert_console_targets_same_category_action_id(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_summary": {"total_open": 2},
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
                                        "message": "Review thesis breakers.",
                                        "status": "open",
                                    },
                                    {
                                        "id": "fundamental-review-manual-check",
                                        "category": "fundamental_review",
                                        "severity": "info",
                                        "message": "Review manual questions.",
                                        "status": "open",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            action_api_enabled=True,
        )

        # The old expert-console "jump to this exact action id" focus/targeting JS
        # is gone (merged away per §3.5), but the underlying structural guarantee
        # it depended on must still hold: two actions in the same category on the
        # same stock become two distinct, independently addressable queue rows --
        # not merged or deduped by category.
        self.assertEqual(html.count('data-category="fundamental_review"'), 2)
        self.assertIn('data-action-id="fundamental-review-thesis-breakers"', html)
        self.assertIn('data-action-id="fundamental-review-manual-check"', html)
        self.assertIn("Review thesis breakers.", html)
        self.assertIn("Review manual questions.", html)

    def test_render_dashboard_html_expert_console_ready_when_all_actions_handled(self):
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
                            "version": 1,
                            "actions": {
                                "2330:workflow-error": {
                                    "status": "done",
                                    "note": "resolved workflow failure",
                                    "reviewer": "workflow-lead",
                                    "evidence_url": "research-dist/evidence/2330-workflow.md",
                                    "updated_at": "2026-05-20T01:00:00Z",
                                }
                            },
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
                                        "message": "Resolve workflow failure before handoff.",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn('<span class="ui-pill ui-pill-ok">交付門檻已通過</span>', html)
        self.assertIn('<strong id="wb-gate-blockers">0</strong>', html)
        self.assertIn("1 / 1 已處理", html)
        self.assertIn("產出 Evidence Pack", html)
        self.assertIn('<span class="ui-badge ui-badge-ok">已完成</span>', html)
        self.assertIn("resolved workflow failure", html)  # evidence note surfaces in the input value
        self.assertIn("workflow-lead", html)

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
                                "company_name": "Co <Name>",
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
        self.assertIn('data-stock="2330&lt;script&gt;"', html)
        self.assertIn("來源檢查", html)
        self.assertIn('data-status="open"', html)
        self.assertIn(
            "research action set research-dist/review_action_state.json "
            "&#x27;2330&lt;script&gt;&#x27; x --status done",
            html,
        )
        self.assertNotIn("2330<script>", html)
        self.assertNotIn("Co <Name>", html)
        self.assertNotIn("Review <source>", html)
        self.assertNotIn('data-stock="2330<script>"', html)

    def test_render_dashboard_html_can_enable_review_action_api(self):
        items = {
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
                                    "message": "Fix workflow.",
                                    "status": "open",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        static_html = render_dashboard_html(items, action_api_enabled=False)
        api_html = render_dashboard_html(items, action_api_enabled=True)

        self.assertNotIn('data-action-api="review-action"', static_html)
        self.assertIn("靜態模式：按下後複製 CLI 指令", static_html)

        self.assertIn('data-action-api="review-action"', api_html)
        self.assertIn('data-action-api="handoff-pack"', api_html)
        self.assertIn('data-source-path="research-dist/research_summary.json"', api_html)
        self.assertIn('data-state-path="research-dist/review_action_state.json"', api_html)
        self.assertIn('data-stock="2330"', api_html)
        self.assertIn('data-action-id="workflow-error"', api_html)
        self.assertIn('data-status="done"', api_html)
        self.assertIn("API 模式：按下即時更新狀態", api_html)
        self.assertNotIn("靜態模式：按下後複製 CLI 指令", api_html)
        self.assertIn('postJson("/api/review-actions/set"', api_html)

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

        # NOTE: the per-item "過期狀態"/"最後更新" state-health line and the stale
        # state's own blocker message text ("review_action_state.json 有過期項目：...")
        # are no longer surfaced anywhere in the redesigned workbench -- only the
        # aggregate blocker COUNT is shown (flagged as a concern in the task-11
        # report). handoff.py's blocker math is otherwise unchanged: the done
        # action is missing reviewer/evidence_url (1 evidence blocker) and
        # 9999:old-action has no matching queue row (1 stale blocker) = 2 total.
        self.assertIn('<strong id="wb-gate-blockers">2</strong>', html)
        self.assertIn("1 / 1 已處理", html)
        self.assertIn("尚有 2 件待交接阻塞", html)
        self.assertIn('data-status="done"', html)
        self.assertIn('<span class="ui-badge ui-badge-ok">已完成</span>', html)
        self.assertIn('data-priority="high"', html)
        self.assertIn('data-severity="error"', html)
        self.assertIn("工作流程", html)
        self.assertIn('placeholder="note：處理說明" value="checked"', html)

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

        # NOTE: review_action_state_warning is no longer surfaced anywhere in the
        # redesigned workbench (flagged as a concern in the task-11 report). This
        # now verifies the dashboard degrades gracefully -- falls back to "no
        # state overlay" so the action stays open -- instead of crashing when
        # only the warning field (and no actual state dict) is present.
        self.assertIn('data-status="open"', html)
        self.assertIn('<strong id="wb-gate-blockers">1</strong>', html)
        self.assertIn("尚有 1 件待交接阻塞", html)
        self.assertIn("工作流程", html)
        self.assertIn("Fix workflow.", html)

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

        self.assertNotIn('<div data-review-actions-section="true">', html)
        self.assertNotIn('data-review-filter="severity"', html)

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
        self.assertIn("研究工作台", html)
        self.assertIn("尚無研究項目", html)  # pool renders empty state, not an error

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

        # NOTE: an error'd research_summaries entry is treated the same as "no
        # research summary" by the redesigned workbench -- the specific path/error
        # text is no longer surfaced anywhere (flagged as a concern in the task-11
        # report). This now verifies the render degrades to the graceful empty
        # state instead of crashing or showing stale/wrong data.
        self.assertIn("研究工作台", html)
        self.assertIn("尚無 research summary", html)

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

        self.assertIn("研究備忘錄", html)
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

        self.assertIn("研究包", html)
        self.assertIn("research-pack.md", html)
        self.assertIn("research-pack.html", html)
        self.assertIn("pack_summary.json", html)

    def test_render_dashboard_html_contains_handoff_evidence_pack_outputs(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "memo_outputs": [],
                "pack_outputs": [],
                "handoff_pack_outputs": [
                    {
                        "markdown_path": "research-dist/handoff-pack/handoff-pack.md",
                        "html_path": "research-dist/handoff-pack/handoff-pack.html",
                        "summary_path": "research-dist/handoff-pack/handoff_pack_summary.json",
                        "gate_status": "ready",
                        "ready": "True",
                        "blocker_count": "0",
                        "evidence_missing_count": "0",
                        "invalid_evidence_count": "0",
                    }
                ],
            }
        )

        self.assertIn('data-outputs-files-section="true"', html)
        self.assertIn("Handoff Evidence Pack", html)
        self.assertIn("handoff-pack.md", html)
        self.assertIn("handoff-pack.html", html)
        self.assertIn("handoff_pack_summary.json", html)
        self.assertIn("ready", html)

    def test_render_dashboard_html_contains_handoff_pack_workflow_guidance(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_state": {
                            "version": 1,
                            "actions": {
                                "2330:reliability-warning": {
                                    "status": "done",
                                    "note": "checked reliability warning",
                                    "updated_at": "2026-05-20T01:00:00Z",
                                }
                            },
                        },
                        "review_action_queue": [
                            {
                                "stock_id": "2330",
                                "priority": "high",
                                "actions": [
                                    {
                                        "id": "reliability-warning",
                                        "category": "reliability",
                                        "severity": "warning",
                                        "message": "Inspect data reliability warning before handoff.",
                                        "status": "open",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        self.assertIn('<strong id="wb-gate-blockers">1</strong>', html)
        self.assertIn("產出 Evidence Pack", html)
        self.assertIn("research-dist/handoff-pack", html)
        self.assertIn(
            "research handoff-pack research-dist/research_summary.json "
            "--state research-dist/review_action_state.json --output-dir research-dist/handoff-pack",
            html,
        )
        self.assertIn("交付證據（高風險事項必填）：", html)
        self.assertIn('placeholder="reviewer：覆核人"', html)
        self.assertIn('placeholder="evidence：檔案路徑或 URL"', html)
        self.assertIn('value="checked reliability warning"', html)

    def test_render_dashboard_html_contains_api_handoff_pack_writer(self):
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [
                    {
                        "path": "research-dist/research_summary.json",
                        "review_action_queue": [],
                    }
                ],
            },
            action_api_enabled=True,
        )

        self.assertIn('data-action-api="handoff-pack"', html)
        self.assertIn("產出 Evidence Pack", html)
        self.assertIn('data-source-path="research-dist/research_summary.json"', html)
        self.assertIn('data-state-path="research-dist/review_action_state.json"', html)
        self.assertIn('postJson("/api/handoff-pack/write"', html)


if __name__ == "__main__":
    unittest.main()
