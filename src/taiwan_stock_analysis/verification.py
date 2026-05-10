from __future__ import annotations

from taiwan_stock_analysis.models import MetricsByYear


def sanity_check(metrics_by_year: MetricsByYear, years: list[str]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for year in years:
        metrics = metrics_by_year.get(year, {})
        gross_margin = metrics.get("gross_margin")
        if gross_margin is not None and gross_margin > 100:
            warnings.append(
                {
                    "level": "error",
                    "field": f"{year} 毛利率",
                    "msg": f"{gross_margin:.1f}% 超過 100%，數據可能有誤",
                }
            )

        current_ratio = metrics.get("current_ratio")
        if current_ratio is not None and current_ratio < 0:
            warnings.append(
                {
                    "level": "error",
                    "field": f"{year} 流動比率",
                    "msg": f"{current_ratio:.1f}% 為負值，請檢查資產負債表數據",
                }
            )

        debt_ratio = metrics.get("debt_ratio")
        if debt_ratio is not None and debt_ratio > 100:
            warnings.append(
                {
                    "level": "warn",
                    "field": f"{year} 負債比率",
                    "msg": f"{debt_ratio:.1f}% 超過 100%，請確認公司產業與會計項目",
                }
            )

    return warnings


def build_verification(metrics_by_year: MetricsByYear, years: list[str]) -> dict[str, object]:
    warnings = sanity_check(metrics_by_year, years)
    return {
        "sanity": warnings,
        "sanity_pass": all(warning["level"] != "error" for warning in warnings),
    }
