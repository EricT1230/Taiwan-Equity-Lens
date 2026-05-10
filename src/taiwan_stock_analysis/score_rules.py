from __future__ import annotations

from typing import Any


Rule = dict[str, Any]


SCORE_RULES: dict[str, list[Rule]] = {
    "profitability": [
        {"metric": "roe", "label": "ROE", "excellent": 20.0, "good": 12.0, "direction": "higher"},
        {"metric": "roa", "label": "ROA", "excellent": 10.0, "good": 6.0, "direction": "higher"},
        {"metric": "gross_margin", "label": "毛利率", "excellent": 40.0, "good": 25.0, "direction": "higher"},
        {"metric": "net_margin", "label": "淨利率", "excellent": 20.0, "good": 10.0, "direction": "higher"},
    ],
    "growth": [
        {"metric": "revenue_cagr", "label": "營收 CAGR", "excellent": 15.0, "good": 5.0, "direction": "higher"},
        {"metric": "eps_cagr", "label": "EPS CAGR", "excellent": 15.0, "good": 5.0, "direction": "higher"},
        {"metric": "equity_growth", "label": "股東權益成長", "excellent": 10.0, "good": 3.0, "direction": "higher"},
    ],
    "financial_safety": [
        {"metric": "current_ratio", "label": "流動比率", "excellent": 200.0, "good": 150.0, "direction": "higher"},
        {"metric": "debt_ratio", "label": "負債比率", "excellent": 40.0, "good": 60.0, "direction": "lower"},
        {"metric": "debt_to_equity", "label": "負債權益比", "excellent": 60.0, "good": 100.0, "direction": "lower"},
    ],
    "cash_flow_quality": [
        {
            "metric": "operating_cash_flow_to_net_income",
            "label": "OCF / 淨利",
            "excellent": 120.0,
            "good": 80.0,
            "direction": "higher",
        },
        {"metric": "free_cash_flow_margin", "label": "FCF margin", "excellent": 15.0, "good": 5.0, "direction": "higher"},
    ],
    "dividend_quality": [
        {"metric": "payout_ratio", "label": "股利支付率", "excellent": 60.0, "good": 85.0, "direction": "lower"},
        {"metric": "free_cash_flow_margin", "label": "FCF margin", "excellent": 10.0, "good": 0.0, "direction": "higher"},
    ],
}


DIMENSION_LABELS = {
    "profitability": "獲利能力",
    "growth": "成長性",
    "financial_safety": "財務安全",
    "cash_flow_quality": "現金流品質",
    "dividend_quality": "股利品質",
}
