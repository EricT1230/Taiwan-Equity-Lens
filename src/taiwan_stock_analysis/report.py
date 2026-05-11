from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from typing import Any

from taiwan_stock_analysis.models import AnalysisResult


def format_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def render_html_report(result: AnalysisResult, company_name: str | None = None) -> str:
    latest_year = result.years[0] if result.years else ""
    latest_metrics = result.metrics_by_year.get(latest_year, {})
    title_name = company_name or result.stock_id
    source_urls = result.metadata.get("source_urls", {})
    income_url = str(source_urls.get("income_statement", "")) if isinstance(source_urls, dict) else ""
    mops_url = str(result.metadata.get("mops_url", ""))
    embedded_json = json.dumps(asdict(result), ensure_ascii=False, indent=2).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title_name)} ({escape(result.stock_id)}) 基本面分析報告</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; background: #f5f7fb; color: #172033; }}
    header {{ background: #12355b; color: white; padding: 28px 32px; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    header p {{ margin: 0; color: #dbeafe; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 32px; background: white; border-bottom: 1px solid #d8dee8; }}
    nav a {{ color: #12355b; text-decoration: none; font-weight: 700; padding: 8px 10px; }}
    main {{ padding: 24px 32px; max-width: 1240px; margin: 0 auto; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .kpi-card {{ background: white; border: 1px solid #dde5f0; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06); }}
    .kpi-card span {{ display: block; color: #64748b; font-size: 13px; margin-bottom: 8px; }}
    .kpi-card strong {{ font-size: 22px; }}
    section.panel {{ background: white; border: 1px solid #dde5f0; border-radius: 8px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06); }}
    section.panel ul {{ margin: 10px 0 0; padding-left: 22px; }}
    section.panel li {{ margin: 6px 0; line-height: 1.55; }}
    h2 {{ margin-top: 0; font-size: 20px; }}
    h3 {{ font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #e8eef7; color: #172033; }}
    .scorecard strong {{ font-size: 30px; color: #12355b; }}
    .disclaimer, .empty {{ color: #64748b; font-size: 13px; }}
    .links a {{ color: #1d4ed8; margin-right: 16px; }}
    pre {{ overflow: auto; background: #0f172a; color: #e5e7eb; padding: 16px; border-radius: 8px; }}
    @media (max-width: 720px) {{
      header, nav, main {{ padding-left: 16px; padding-right: 16px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title_name)} ({escape(result.stock_id)}) 基本面分析報告</h1>
    <p>資料來源：{escape(str(result.metadata.get("source", "Goodinfo.tw")))} | 年度：{escape(", ".join(result.years) or "-")}</p>
  </header>
  <nav aria-label="報告導覽">
    <a href="#scorecard">品質分數</a>
    <a href="#valuation">估值情境</a>
    <a href="#diagnostics">資料品質</a>
    <a href="#reliability">資料可信度</a>
    <a href="#operations">營運概況</a>
    <a href="#profitability">獲利能力</a>
    <a href="#financial-health">財務體質</a>
  </nav>
  <main>
    <div class="kpis">
      {_kpi_card("營收", latest_metrics.get("revenue"))}
      {_kpi_card("營收 CAGR", latest_metrics.get("revenue_cagr"), "%")}
      {_kpi_card("毛利率", latest_metrics.get("gross_margin"), "%")}
      {_kpi_card("淨利率", latest_metrics.get("net_margin"), "%")}
      {_kpi_card("ROE", latest_metrics.get("roe"), "%")}
      {_kpi_card("營業現金流 / 淨利", latest_metrics.get("operating_cash_flow_to_net_income"), "%")}
      {_kpi_card("自由現金流率", latest_metrics.get("free_cash_flow_margin"), "%")}
      {_kpi_card("流動比率", latest_metrics.get("current_ratio"), "%")}
      {_kpi_card("負債權益比", latest_metrics.get("debt_to_equity"), "%")}
    </div>
    {_scorecard(result.scorecard)}
    {_valuation_context(result.valuation)}
    {_diagnostics_panel(result.diagnostics)}
    {_reliability_panel(result)}
    {_insight_panel("operations", "營運概況", result.insights.get("operations", []))}
    {_insight_panel("profitability", "獲利能力", result.insights.get("profitability", []))}
    {_insight_panel("financial-health", "財務體質", result.insights.get("financial_health", []))}
    {_source_links(income_url, mops_url)}
    <script type="application/json" id="analysis-data">{embedded_json}</script>
  </main>
</body>
</html>
"""


def _kpi_card(label: str, value: float | None, suffix: str = "") -> str:
    return (
        '<section class="kpi-card">'
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(format_number(value, suffix))}</strong>"
        "</section>"
    )


def _insight_panel(section_id: str, title: str, items: list[str]) -> str:
    return (
        f'<section id="{escape(section_id)}" class="panel">'
        f"<h2>{escape(title)}</h2>"
        "<h3>重點觀察</h3>"
        f"{_insight_list(items)}"
        "</section>"
    )


def _insight_list(items: list[str]) -> str:
    if not items:
        return '<p class="empty">目前沒有足夠資料產生這個區塊的觀察。</p>'
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<ul>{rows}</ul>"


def _scorecard(scorecard: dict[str, Any]) -> str:
    if not scorecard:
        return _empty_panel("scorecard", "品質分數", "目前沒有品質分數資料。")
    total_score = scorecard.get("total_score")
    confidence = scorecard.get("confidence")
    dimensions = scorecard.get("dimensions", {})
    dimension_rows = []
    for dimension in dimensions.values() if isinstance(dimensions, dict) else []:
        if not isinstance(dimension, dict):
            continue
        reasons = dimension.get("reasons", [])
        first_reason = reasons[0] if isinstance(reasons, list) and reasons else ""
        dimension_rows.append(
            "<tr>"
            f"<td>{escape(str(dimension.get('label', '-')))}</td>"
            f"<td>{escape(str(dimension.get('score') if dimension.get('score') is not None else '-'))}</td>"
            f"<td>{escape(str(dimension.get('confidence', '-')))}%</td>"
            f"<td>{escape(str(first_reason))}</td>"
            "</tr>"
        )
    rows = "".join(dimension_rows) or _empty_row(4, "目前沒有分項評分資料。")
    return (
        '<section id="scorecard" class="panel scorecard">'
        "<h2>品質分數</h2>"
        f"<p><strong>{escape(str(total_score if total_score is not None else '-'))}</strong> / 100"
        f" | 信心度 {escape(str(confidence if confidence is not None else '-'))}%</p>"
        "<table><thead><tr><th>面向</th><th>分數</th><th>信心度</th><th>主要原因</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        '<p class="disclaimer">品質分數只反映基本面條件，不包含估值，也不是投資建議。</p>'
        "</section>"
    )


def _valuation_context(valuation: dict[str, Any]) -> str:
    if not valuation:
        return _empty_panel("valuation", "估值情境", "尚未提供估值 CSV，因此沒有估值情境。")
    metrics = valuation.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}
    target_prices = valuation.get("target_prices", {})
    target_prices = target_prices if isinstance(target_prices, dict) else {}
    target_rows = "".join(
        "<tr>"
        f"<td>{escape(label)}</td>"
        f"<td>{escape(format_number(row.get('eps')))}</td>"
        f"<td>{escape(format_number(row.get('target_pe')))}</td>"
        f"<td>{escape(format_number(row.get('target_price')))}</td>"
        f"<td>{escape(format_number(row.get('price_gap_percent'), '%'))}</td>"
        "</tr>"
        for key, label in (("low", "保守"), ("base", "基準"), ("high", "樂觀"))
        for row in [target_prices.get(key, {}) if isinstance(target_prices.get(key, {}), dict) else {}]
    )
    target_table = (
        "<h3>EPS 與目標價情境</h3>"
        "<table><thead><tr><th>情境</th><th>EPS</th><th>目標 PE</th><th>目標價</th><th>與現價差距</th></tr></thead>"
        f"<tbody>{target_rows or _empty_row(5, '目前沒有目標價情境資料。')}</tbody></table>"
    )
    return (
        '<section id="valuation" class="panel valuation">'
        "<h2>估值情境</h2>"
        f"<p>{escape(str(valuation.get('context', '估值資料僅供研究情境參考。')))}</p>"
        "<table><thead><tr><th>項目</th><th>數值</th></tr></thead><tbody>"
        f"<tr><td>股價</td><td>{escape(format_number(metrics.get('price')))}</td></tr>"
        f"<tr><td>PE</td><td>{escape(format_number(metrics.get('pe')))}</td></tr>"
        f"<tr><td>PB</td><td>{escape(format_number(metrics.get('pb')))}</td></tr>"
        f"<tr><td>現金殖利率</td><td>{escape(format_number(metrics.get('dividend_yield'), '%'))}</td></tr>"
        f"<tr><td>保守公允價</td><td>{escape(format_number(metrics.get('fair_value_low')))}</td></tr>"
        f"<tr><td>基準公允價</td><td>{escape(format_number(metrics.get('fair_value_base')))}</td></tr>"
        f"<tr><td>樂觀公允價</td><td>{escape(format_number(metrics.get('fair_value_high')))}</td></tr>"
        "</tbody></table>"
        f"{target_table}"
        '<p class="disclaimer">估值情境只呈現輸入假設下的研究結果，不構成投資建議。</p>'
        "</section>"
    )


def _diagnostics_panel(diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return _empty_panel("diagnostics", "資料品質", "目前沒有資料品質診斷。")
    issues = diagnostics.get("issues", [])
    issues = issues if isinstance(issues, list) else []
    if not issues:
        return (
            '<section id="diagnostics" class="panel diagnostics">'
            "<h2>資料品質</h2>"
            '<p class="empty">目前未發現需要提醒的資料品質問題。</p>'
            "</section>"
        )
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(issue.get('level', '-')) if isinstance(issue, dict) else '-')}</td>"
        f"<td>{escape(str(issue.get('category', '-')) if isinstance(issue, dict) else '-')}</td>"
        f"<td>{escape(str(issue.get('field', '-')) if isinstance(issue, dict) else '-')}</td>"
        f"<td>{escape(str(issue.get('message', '-')) if isinstance(issue, dict) else '-')}</td>"
        "</tr>"
        for issue in issues
    )
    return (
        '<section id="diagnostics" class="panel diagnostics">'
        "<h2>資料品質</h2>"
        f"<p>共有 {escape(str(diagnostics.get('issue_count', len(issues))))} 個資料品質提醒。</p>"
        "<table><thead><tr><th>等級</th><th>類別</th><th>欄位</th><th>訊息</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "</section>"
    )


def _reliability_panel(result: AnalysisResult) -> str:
    statuses = result.metadata.get("reliability", [])
    assumptions = result.valuation.get("assumptions", {}) if result.valuation else {}
    status_rows: list[str] = []
    if isinstance(statuses, list):
        for status in statuses:
            if not isinstance(status, dict):
                continue
            status_rows.append(
                "<tr>"
                f"<td>{escape(str(status.get('stage', '')))}</td>"
                f"<td>{escape(str(status.get('status', '')))}</td>"
                f"<td>{escape(str(status.get('source', '')))}</td>"
                f"<td>{escape(str(status.get('date', '')))}</td>"
                f"<td>{escape(str(status.get('message', '')))}</td>"
                f"<td>{escape(str(status.get('retry_hint', '')))}</td>"
                "</tr>"
            )
    rows = "".join(status_rows) or _empty_row(6, "目前沒有資料可信度警告。")
    assumption_items: list[str] = []
    if isinstance(assumptions, dict):
        for key, value in assumptions.items():
            assumption_items.append(f"<li><strong>{escape(str(key))}</strong>: {escape(str(value))}</li>")
    assumptions_html = "".join(assumption_items) or '<li class="empty">未提供估值假設。</li>'
    return (
        '<section id="reliability" class="panel reliability">'
        "<h2>資料可信度</h2>"
        "<table><thead><tr><th>階段</th><th>狀態</th><th>來源</th><th>日期</th><th>說明</th><th>建議</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<h3>估值假設</h3>"
        f"<ul>{assumptions_html}</ul>"
        "</section>"
    )


def _source_links(income_url: str, mops_url: str) -> str:
    return (
        '<section class="panel links">'
        "<h2>資料來源連結</h2>"
        f"{_source_link(income_url, 'Goodinfo.tw')}"
        f"{_source_link(mops_url, '公開資訊觀測站 MOPS')}"
        "</section>"
    )


def _source_link(url: str, label: str) -> str:
    if not url:
        return f'<span class="empty">{escape(label)} 連結未提供</span>'
    return f'<a href="{escape(url)}">{escape(label)}</a>'


def _empty_panel(section_id: str, title: str, message: str) -> str:
    return f'<section id="{escape(section_id)}" class="panel"><h2>{escape(title)}</h2><p class="empty">{escape(message)}</p></section>'


def _empty_row(colspan: int, message: str) -> str:
    return f'<tr><td colspan="{colspan}" class="empty">{escape(message)}</td></tr>'
