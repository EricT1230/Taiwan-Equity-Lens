from __future__ import annotations

from taiwan_stock_analysis.models import MetricsByYear
from taiwan_stock_analysis.trends import cagr, yoy_change


Insights = dict[str, list[str]]


def _values(metrics_by_year: MetricsByYear, metric_name: str) -> dict[str, float | None]:
    return {year: metrics.get(metric_name) for year, metrics in metrics_by_year.items()}


def _fmt(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    if suffix == "%":
        return f"{value:.1f}%"
    return f"{value:,.2f}"


def _metric(metrics_by_year: MetricsByYear, year: str, metric_name: str) -> float | None:
    return metrics_by_year.get(year, {}).get(metric_name)


def _metric_or_trend_cagr(metrics_by_year: MetricsByYear, years: list[str], metric_name: str, raw_name: str) -> float | None:
    if not years:
        return None
    metric_value = _metric(metrics_by_year, years[0], metric_name)
    if metric_value is not None:
        return metric_value
    return cagr(_values(metrics_by_year, raw_name), years)


def build_insights(metrics_by_year: MetricsByYear, years: list[str]) -> Insights:
    if not years:
        return {"operations": [], "profitability": [], "financial_health": []}

    latest_year = years[0]
    revenue_yoy = yoy_change(_values(metrics_by_year, "revenue"), years)
    revenue_cagr = _metric_or_trend_cagr(metrics_by_year, years, "revenue_cagr", "revenue")
    eps_yoy = yoy_change(_values(metrics_by_year, "eps"), years)
    fcf_yoy = yoy_change(_values(metrics_by_year, "free_cash_flow"), years)

    operations = [
        f"{latest_year} 年營收 {_fmt(_metric(metrics_by_year, latest_year, 'revenue'))} 億元，YoY {_fmt(revenue_yoy, '%')}。",
        f"{latest_year} 年毛利率 {_fmt(_metric(metrics_by_year, latest_year, 'gross_margin'), '%')}，反映產品組合與成本控管表現。",
        f"近 {len(years)} 年營收 CAGR {_fmt(revenue_cagr, '%')}，可用來觀察中期成長速度。",
    ]

    profitability = [
        f"{latest_year} 年 EPS {_fmt(_metric(metrics_by_year, latest_year, 'eps'))} 元，YoY {_fmt(eps_yoy, '%')}。",
        f"{latest_year} 年淨利率 {_fmt(_metric(metrics_by_year, latest_year, 'net_margin'), '%')}，代表每 100 元營收轉成稅後淨利的能力。",
        f"{latest_year} 年 ROE {_fmt(_metric(metrics_by_year, latest_year, 'roe'), '%')}，衡量股東權益報酬效率。",
        f"{latest_year} 年 OCF / 淨利 {_fmt(_metric(metrics_by_year, latest_year, 'operating_cash_flow_to_net_income'), '%')}，觀察獲利是否有現金流支撐。",
    ]

    financial_health = [
        f"{latest_year} 年流動比率 {_fmt(_metric(metrics_by_year, latest_year, 'current_ratio'), '%')}，觀察短期償債緩衝。",
        f"{latest_year} 年負債比率 {_fmt(_metric(metrics_by_year, latest_year, 'debt_ratio'), '%')}，用來衡量資產結構風險。",
        f"{latest_year} 年負債權益比 {_fmt(_metric(metrics_by_year, latest_year, 'debt_to_equity'), '%')}，補充槓桿水位判斷。",
        f"{latest_year} 年自由現金流 {_fmt(_metric(metrics_by_year, latest_year, 'free_cash_flow'))} 億元，YoY {_fmt(fcf_yoy, '%')}；FCF margin {_fmt(_metric(metrics_by_year, latest_year, 'free_cash_flow_margin'), '%')}。",
    ]

    payout_ratio = _metric(metrics_by_year, latest_year, "payout_ratio")
    if payout_ratio is not None:
        financial_health.append(f"{latest_year} 年股利支付率 {_fmt(payout_ratio, '%')}，可觀察配息對獲利的消耗程度。")

    return {
        "operations": operations,
        "profitability": profitability,
        "financial_health": financial_health,
    }
