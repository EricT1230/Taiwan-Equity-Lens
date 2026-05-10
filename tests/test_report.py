import unittest

from taiwan_stock_analysis.models import AnalysisResult
from taiwan_stock_analysis.report import render_html_report


class ReportTests(unittest.TestCase):
    def test_render_html_report_contains_tabs_kpis_sources_and_json(self):
        result = AnalysisResult(
            stock_id="2330",
            years=["2024", "2023"],
            metrics_by_year={
                "2024": {
                    "revenue": 1000.0,
                    "gross_margin": 40.0,
                    "net_margin": 20.0,
                    "roe": 26.67,
                    "current_ratio": 200.0,
                    "revenue_cagr": 12.5,
                    "operating_cash_flow_to_net_income": 130.0,
                    "free_cash_flow_margin": 15.0,
                    "debt_to_equity": 50.0,
                }
            },
            insights={
                "operations": ["2024 年營收 1,000.00 億元，YoY 10.0%。"],
                "profitability": ["2024 年 EPS 10.00 元，YoY 5.0%。"],
                "financial_health": ["2024 年流動比率 200.0%，觀察短期償債緩衝。"],
            },
            scorecard={
                "latest_year": "2024",
                "total_score": 88,
                "confidence": 90,
                "dimensions": {
                    "profitability": {
                        "label": "獲利能力",
                        "score": 92,
                        "confidence": 100,
                        "reasons": ["ROE 26.7% 達優秀區間"],
                    },
                    "growth": {
                        "label": "成長性",
                        "score": 80,
                        "confidence": 75,
                        "reasons": ["營收 CAGR 12.5% 達穩健區間"],
                    },
                },
                "disclaimer": "valuation_excluded: fundamental quality score excludes valuation and is not investment advice.",
            },
            valuation={
                "latest_year": "2024",
                "eps_scenarios": {
                    "conservative": 45.0,
                    "base": 60.0,
                    "optimistic": 66.0,
                },
                "target_prices": {
                    "low": {"eps": 45.0, "target_pe": 15.0, "target_price": 675.0, "price_gap_percent": -32.5},
                    "base": {"eps": 60.0, "target_pe": 20.0, "target_price": 1200.0, "price_gap_percent": 20.0},
                    "high": {"eps": 66.0, "target_pe": 25.0, "target_price": 1650.0, "price_gap_percent": 65.0},
                },
                "metrics": {
                    "price": 1000.0,
                    "pe": 20.0,
                    "pb": 6.25,
                    "dividend_yield": 1.2,
                    "fair_value_low": 900.0,
                    "fair_value_base": 1200.0,
                    "fair_value_high": 1500.0,
                    "price_to_base_fair_value": 83.33,
                },
                "context": "高品質且價格低於基準情境，可進一步研究估值假設。",
                "disclaimer": "valuation_context_only",
            },
            diagnostics={
                "issue_count": 1,
                "issues": [
                    {
                        "level": "warn",
                        "category": "metrics",
                        "field": "2024 free_cash_flow_margin",
                        "message": "2024 年缺少 FCF Margin，現金流品質判讀信心較低",
                    }
                ],
            },
            metadata={
                "source": "Goodinfo.tw",
                "source_urls": {
                    "income_statement": "https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=IS_YEAR&STOCK_ID=2330"
                },
                "mops_url": "https://mops.twse.com.tw/mops/web/t05st01?co_id=2330",
            },
            verification={"sanity_pass": True, "sanity": []},
        )

        html = render_html_report(result, company_name="台積電")

        self.assertIn("台積電 (2330)", html)
        self.assertIn("經營分析", html)
        self.assertIn("獲利分析", html)
        self.assertIn("財務健全度", html)
        self.assertIn("營收", html)
        self.assertIn("1,000.00", html)
        self.assertIn("營收 CAGR", html)
        self.assertIn("12.50%", html)
        self.assertIn("OCF / 淨利", html)
        self.assertIn("130.00%", html)
        self.assertIn("FCF Margin", html)
        self.assertIn("負債權益比", html)
        self.assertIn("基本面品質分數", html)
        self.assertIn("88", html)
        self.assertIn("獲利能力", html)
        self.assertIn("不含估值", html)
        self.assertIn("估值脈絡", html)
        self.assertIn("資料品質診斷", html)
        self.assertIn("現金流品質判讀信心較低", html)
        self.assertIn("PE", html)
        self.assertIn("EPS 情境", html)
        self.assertIn("目標價差距", html)
        self.assertIn("1,200.00", html)
        self.assertIn("20.00", html)
        self.assertIn("基準情境", html)
        self.assertNotIn("買進", html)
        self.assertNotIn("賣出", html)
        self.assertNotIn("買賣建議", html)
        self.assertIn("Goodinfo.tw", html)
        self.assertIn("mops.twse.com.tw", html)
        self.assertIn("趨勢解讀", html)
        self.assertIn("2024 年營收 1,000.00 億元", html)
        self.assertIn("2024 年 EPS 10.00 元", html)
        self.assertIn("application/json", html)
        self.assertIn('"stock_id": "2330"', html)


if __name__ == "__main__":
    unittest.main()
