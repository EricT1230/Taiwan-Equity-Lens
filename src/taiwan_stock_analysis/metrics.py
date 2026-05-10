from __future__ import annotations

from taiwan_stock_analysis.models import FinancialTable, MetricsByYear


def find_field(table: FinancialTable, *keywords: str) -> str | None:
    for field_name in table:
        if all(keyword in field_name for keyword in keywords):
            return field_name
    return None


def get_value(table: FinancialTable, field_name: str | None, year: str) -> float | None:
    if field_name is None:
        return None
    return table.get(field_name, {}).get(year)


def safe_percent(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator * 100


def add_values(*values: float | None) -> float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def abs_value(value: float | None) -> float | None:
    if value is None:
        return None
    return abs(value)


def growth_rate(latest: float | None, previous: float | None) -> float | None:
    if latest is None or previous in {None, 0}:
        return None
    return (latest - previous) / previous * 100


def series_cagr(values_by_year: dict[str, float | None], years: list[str], start_index: int = 0) -> float | None:
    available = [
        (year, values_by_year.get(year))
        for year in years[start_index:]
        if values_by_year.get(year) is not None
    ]
    if len(available) < 2:
        return None

    latest_year, latest = available[0]
    oldest_year, oldest = available[-1]
    if latest is None or oldest is None or latest < 0 or oldest <= 0:
        return None

    years_delta = abs(int(latest_year) - int(oldest_year))
    if years_delta == 0:
        return None
    return ((latest / oldest) ** (1 / years_delta) - 1) * 100


def calculate_metrics(
    income_statement: FinancialTable,
    balance_sheet: FinancialTable,
    cash_flow: FinancialTable,
    years: list[str],
) -> MetricsByYear:
    revenue_key = find_field(income_statement, "營業", "收入")
    gross_key = find_field(income_statement, "毛利")
    op_income_key = find_field(income_statement, "營業利益")
    net_income_key = find_field(income_statement, "稅後淨利")
    sell_key = find_field(income_statement, "推銷")
    admin_key = find_field(income_statement, "管理")
    rd_key = find_field(income_statement, "研究")
    eps_key = find_field(income_statement, "每股", "盈餘")

    current_assets_key = find_field(balance_sheet, "流動資產", "合計")
    current_liabilities_key = find_field(balance_sheet, "流動負債", "合計")
    total_liabilities_key = find_field(balance_sheet, "負債總額")
    total_assets_key = find_field(balance_sheet, "資產總額")
    equity_key = find_field(balance_sheet, "股東權益", "總額")
    cash_key = find_field(balance_sheet, "現金", "約當")

    operating_cf_key = find_field(cash_flow, "營業活動", "淨現金")
    capex_key = find_field(cash_flow, "固定資產", "增加", "減少")
    cash_dividend_key = find_field(cash_flow, "現金股利")

    metrics: MetricsByYear = {}
    revenue_by_year = income_statement.get(revenue_key, {}) if revenue_key else {}
    eps_by_year = income_statement.get(eps_key, {}) if eps_key else {}

    for year_index, year in enumerate(years):
        revenue = get_value(income_statement, revenue_key, year)
        gross_profit = get_value(income_statement, gross_key, year)
        op_income = get_value(income_statement, op_income_key, year)
        net_income = get_value(income_statement, net_income_key, year)
        sell_expense = get_value(income_statement, sell_key, year)
        admin_expense = get_value(income_statement, admin_key, year)
        rd_expense = get_value(income_statement, rd_key, year)
        current_assets = get_value(balance_sheet, current_assets_key, year)
        current_liabilities = get_value(balance_sheet, current_liabilities_key, year)
        total_liabilities = get_value(balance_sheet, total_liabilities_key, year)
        total_assets = get_value(balance_sheet, total_assets_key, year)
        equity = get_value(balance_sheet, equity_key, year)
        previous_equity = (
            get_value(balance_sheet, equity_key, years[year_index + 1])
            if year_index + 1 < len(years)
            else None
        )
        cash = get_value(balance_sheet, cash_key, year)
        operating_cf = get_value(cash_flow, operating_cf_key, year)
        capex = get_value(cash_flow, capex_key, year)
        cash_dividend = get_value(cash_flow, cash_dividend_key, year)

        total_opex = add_values(sell_expense, admin_expense, rd_expense)
        free_cash_flow = add_values(operating_cf, capex)

        metrics[year] = {
            "revenue": revenue,
            "gross_profit": gross_profit,
            "op_income": op_income,
            "net_income": net_income,
            "sell_expense": sell_expense,
            "admin_expense": admin_expense,
            "rd_expense": rd_expense,
            "eps": get_value(income_statement, eps_key, year),
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "total_liabilities": total_liabilities,
            "total_assets": total_assets,
            "equity": equity,
            "cash": cash,
            "gross_margin": safe_percent(gross_profit, revenue),
            "op_margin": safe_percent(op_income, revenue),
            "net_margin": safe_percent(net_income, revenue),
            "sell_ratio": safe_percent(sell_expense, revenue),
            "admin_ratio": safe_percent(admin_expense, revenue),
            "rd_ratio": safe_percent(rd_expense, revenue),
            "total_opex_ratio": safe_percent(total_opex, revenue),
            "current_ratio": safe_percent(current_assets, current_liabilities),
            "debt_ratio": safe_percent(total_liabilities, total_assets),
            "debt_to_equity": safe_percent(total_liabilities, equity),
            "cash_to_current_liabilities": safe_percent(cash, current_liabilities),
            "roe": safe_percent(net_income, equity),
            "roa": safe_percent(net_income, total_assets),
            "revenue_cagr": series_cagr(revenue_by_year, years, year_index),
            "eps_cagr": series_cagr(eps_by_year, years, year_index),
            "equity_growth": growth_rate(equity, previous_equity),
            "operating_cash_flow_to_net_income": safe_percent(operating_cf, net_income),
            "operating_cash_flow": operating_cf,
            "capex": capex,
            "free_cash_flow": free_cash_flow,
            "free_cash_flow_margin": safe_percent(free_cash_flow, revenue),
            "cash_dividend": cash_dividend,
            "payout_ratio": safe_percent(abs_value(cash_dividend), net_income),
        }

    return metrics
