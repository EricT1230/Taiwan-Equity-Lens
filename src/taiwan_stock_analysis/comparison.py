from __future__ import annotations

from dataclasses import asdict
from typing import Any

from taiwan_stock_analysis.models import AnalysisResult


DIMENSIONS: list[dict[str, Any]] = [
    {"metric": "gross_margin", "label": "毛利率", "higher_is_better": True},
    {"metric": "roe", "label": "ROE", "higher_is_better": True},
    {"metric": "revenue_cagr", "label": "營收 CAGR", "higher_is_better": True},
    {"metric": "debt_ratio", "label": "負債比率", "higher_is_better": False},
    {"metric": "free_cash_flow_margin", "label": "FCF Margin", "higher_is_better": True},
    {"metric": "operating_cash_flow_to_net_income", "label": "OCF / 淨利", "higher_is_better": True},
]


def _latest_metrics(result: AnalysisResult) -> dict[str, float | None]:
    latest_year = result.years[0] if result.years else ""
    return result.metrics_by_year.get(latest_year, {})


def _rank(rows: list[dict[str, Any]], metric: str, higher_is_better: bool) -> None:
    valid_rows = [row for row in rows if row.get(metric) is not None]
    valid_rows.sort(key=lambda row: row[metric], reverse=higher_is_better)
    for index, row in enumerate(valid_rows, start=1):
        row[f"{metric}_rank"] = index
    for row in rows:
        row.setdefault(f"{metric}_rank", None)


def compare_results(results: list[AnalysisResult]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for result in results:
        latest_year = result.years[0] if result.years else None
        metrics = _latest_metrics(result)
        row: dict[str, Any] = {
            "stock_id": result.stock_id,
            "latest_year": latest_year,
            "verification": result.verification,
        }
        for dimension in DIMENSIONS:
            row[dimension["metric"]] = metrics.get(dimension["metric"])
        rows.append(row)

    for dimension in DIMENSIONS:
        _rank(rows, dimension["metric"], bool(dimension["higher_is_better"]))

    return {
        "dimensions": DIMENSIONS,
        "rows": rows,
        "source_results": [asdict(result) for result in results],
    }
