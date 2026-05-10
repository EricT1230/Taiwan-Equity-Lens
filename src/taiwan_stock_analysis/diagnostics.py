from __future__ import annotations

from taiwan_stock_analysis.models import FinancialTable, MetricsByYear


CORE_FIELDS = {
    "income_statement": {
        "label": "損益表",
        "fields": {
            "revenue": ("營業收入",),
            "net_income": ("稅後淨利",),
            "eps": ("每股稅後盈餘",),
        },
    },
    "balance_sheet": {
        "label": "資產負債表",
        "fields": {
            "current_assets": ("流動資產",),
            "current_liabilities": ("流動負債",),
            "total_liabilities": ("負債總額",),
            "equity": ("股東權益",),
        },
    },
    "cash_flow": {
        "label": "現金流量表",
        "fields": {
            "operating_cash_flow": ("營業活動", "現金流"),
        },
    },
}

CORE_METRICS = (
    "revenue",
    "net_income",
    "eps",
    "roe",
    "free_cash_flow_margin",
    "debt_ratio",
    "operating_cash_flow_to_net_income",
)


def _issue(level: str, category: str, field: str, message: str) -> dict[str, str]:
    return {"level": level, "category": category, "field": field, "message": message}


def _has_field(table: FinancialTable, keywords: tuple[str, ...]) -> bool:
    return any(all(keyword in row_name for keyword in keywords) for row_name in table)


def _missing_table_field_issues(
    table_name: str,
    table: FinancialTable,
) -> list[dict[str, str]]:
    config = CORE_FIELDS[table_name]
    issues = []
    for field_key, keywords in config["fields"].items():
        if not _has_field(table, keywords):
            issues.append(
                _issue(
                    "warn",
                    "source_data",
                    f"{table_name}.{field_key}",
                    f"{config['label']}缺少 {field_key} 相關欄位，部分分析信心較低",
                )
            )
    return issues


def build_diagnostics(
    years: list[str],
    income_statement: FinancialTable,
    balance_sheet: FinancialTable,
    cash_flow: FinancialTable,
    metrics_by_year: MetricsByYear,
) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    if len(years) < 3:
        issues.append(
            _issue(
                "warn",
                "coverage",
                "years",
                f"分析年度少於 3 年，目前只有 {len(years)} 年，長期趨勢判讀信心較低",
            )
        )

    issues.extend(_missing_table_field_issues("income_statement", income_statement))
    issues.extend(_missing_table_field_issues("balance_sheet", balance_sheet))
    issues.extend(_missing_table_field_issues("cash_flow", cash_flow))

    latest_year = years[0] if years else ""
    latest_metrics = metrics_by_year.get(latest_year, {})
    for metric in CORE_METRICS:
        if latest_metrics.get(metric) is None:
            issues.append(
                _issue(
                    "warn",
                    "metrics",
                    f"{latest_year} {metric}".strip(),
                    f"{latest_year} 年缺少 {metric}，相關判讀信心較低".strip(),
                )
            )

    net_income = latest_metrics.get("net_income")
    operating_cash_flow = latest_metrics.get("operating_cash_flow")
    if (
        latest_year
        and net_income is not None
        and operating_cash_flow is not None
        and net_income > 0
        and operating_cash_flow < 0
    ):
        issues.append(
            _issue(
                "warn",
                "cash_flow",
                f"{latest_year} operating_cash_flow",
                f"{latest_year} 年淨利為正但營業現金流為負，盈餘品質需要進一步檢查",
            )
        )

    return {"issue_count": len(issues), "issues": issues}
