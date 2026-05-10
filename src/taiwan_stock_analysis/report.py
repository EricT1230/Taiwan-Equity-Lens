from __future__ import annotations

import json
from dataclasses import asdict
from html import escape

from taiwan_stock_analysis.models import AnalysisResult


def format_number(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def _kpi_card(label: str, value: float | None, suffix: str = "") -> str:
    return (
        '<section class="kpi-card">'
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(format_number(value, suffix))}</strong>"
        "</section>"
    )


def _insight_list(items: list[str]) -> str:
    if not items:
        return "<p>目前資料不足以產生趨勢解讀。</p>"
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<ul>{rows}</ul>"


def _scorecard(scorecard: dict) -> str:
    if not scorecard:
        return ""
    total_score = scorecard.get("total_score")
    confidence = scorecard.get("confidence")
    dimensions = scorecard.get("dimensions", {})
    dimension_rows = []
    for dimension in dimensions.values():
        reasons = dimension.get("reasons", [])
        first_reason = reasons[0] if reasons else ""
        dimension_rows.append(
            "<tr>"
            f"<td>{escape(str(dimension.get('label', '-')))}</td>"
            f"<td>{escape(str(dimension.get('score') if dimension.get('score') is not None else '-'))}</td>"
            f"<td>{escape(str(dimension.get('confidence', '-')))}%</td>"
            f"<td>{escape(first_reason)}</td>"
            "</tr>"
        )
    return (
        '<section class="panel scorecard">'
        "<h2>基本面品質分數</h2>"
        f"<p><strong>{escape(str(total_score if total_score is not None else '-'))}</strong> / 100"
        f" | 信心 {escape(str(confidence if confidence is not None else '-'))}%</p>"
        "<table><thead><tr><th>構面</th><th>分數</th><th>信心</th><th>主要原因</th></tr></thead>"
        f"<tbody>{''.join(dimension_rows)}</tbody></table>"
        "<p class=\"disclaimer\">不含估值，僅供基本面研究參考。</p>"
        "</section>"
    )


def _valuation_context(valuation: dict) -> str:
    if not valuation:
        return ""
    metrics = valuation.get("metrics", {})
    target_prices = valuation.get("target_prices", {})
    target_rows = "".join(
        "<tr>"
        f"<td>{escape(label)}</td>"
        f"<td>{escape(format_number(row.get('eps')))}</td>"
        f"<td>{escape(format_number(row.get('target_pe')))}</td>"
        f"<td>{escape(format_number(row.get('target_price')))}</td>"
        f"<td>{escape(format_number(row.get('price_gap_percent'), '%'))}</td>"
        "</tr>"
        for key, label in (("low", "保守"), ("base", "基準"), ("high", "樂觀"))
        for row in [target_prices.get(key, {})]
    )
    target_table = ""
    if target_rows:
        target_table = (
            "<h3>EPS 情境與目標價</h3>"
            "<table><thead><tr><th>情境</th><th>EPS 情境</th><th>目標 PE</th><th>目標價</th><th>目標價差距</th></tr></thead>"
            f"<tbody>{target_rows}</tbody></table>"
        )
    return (
        '<section class="panel valuation">'
        "<h2>估值脈絡</h2>"
        f"<p>{escape(str(valuation.get('context', '估值資料不足。')))}</p>"
        "<table><thead><tr><th>項目</th><th>數值</th></tr></thead><tbody>"
        f"<tr><td>股價</td><td>{escape(format_number(metrics.get('price')))}</td></tr>"
        f"<tr><td>PE</td><td>{escape(format_number(metrics.get('pe')))}</td></tr>"
        f"<tr><td>PB</td><td>{escape(format_number(metrics.get('pb')))}</td></tr>"
        f"<tr><td>殖利率</td><td>{escape(format_number(metrics.get('dividend_yield'), '%'))}</td></tr>"
        f"<tr><td>保守情境</td><td>{escape(format_number(metrics.get('fair_value_low')))}</td></tr>"
        f"<tr><td>基準情境</td><td>{escape(format_number(metrics.get('fair_value_base')))}</td></tr>"
        f"<tr><td>樂觀情境</td><td>{escape(format_number(metrics.get('fair_value_high')))}</td></tr>"
        "</tbody></table>"
        f"{target_table}"
        "<p class=\"disclaimer\">估值與品質分數分開呈現，僅供研究脈絡。</p>"
        "</section>"
    )


def _diagnostics_panel(diagnostics: dict) -> str:
    if not diagnostics:
        return ""
    issues = diagnostics.get("issues", [])
    if not issues:
        return (
            '<section class="panel diagnostics">'
            "<h2>資料品質診斷</h2>"
            "<p>未偵測到主要資料品質警示。</p>"
            "</section>"
        )
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(issue.get('level', '-')))}</td>"
        f"<td>{escape(str(issue.get('category', '-')))}</td>"
        f"<td>{escape(str(issue.get('field', '-')))}</td>"
        f"<td>{escape(str(issue.get('message', '-')))}</td>"
        "</tr>"
        for issue in issues
    )
    return (
        '<section class="panel diagnostics">'
        "<h2>資料品質診斷</h2>"
        f"<p>共 {escape(str(diagnostics.get('issue_count', len(issues))))} 項資料品質警示。</p>"
        "<table><thead><tr><th>等級</th><th>類別</th><th>欄位</th><th>說明</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "</section>"
    )


def render_html_report(result: AnalysisResult, company_name: str | None = None) -> str:
    latest_year = result.years[0] if result.years else ""
    latest_metrics = result.metrics_by_year.get(latest_year, {})
    title_name = company_name or result.stock_id
    source_urls = result.metadata.get("source_urls", {})
    income_url = ""
    if isinstance(source_urls, dict):
        income_url = str(source_urls.get("income_statement", ""))
    mops_url = str(result.metadata.get("mops_url", ""))
    embedded_json = json.dumps(asdict(result), ensure_ascii=False, indent=2).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title_name)} ({escape(result.stock_id)}) 財務分析</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js"></script>
  <style>
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif; background: #f6f8fb; color: #1f2937; }}
    header {{ background: #12355b; color: white; padding: 24px 32px; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    header p {{ margin: 0; color: #dbeafe; }}
    nav {{ display: flex; gap: 8px; padding: 12px 32px; background: white; border-bottom: 1px solid #d8dee8; }}
    nav a {{ color: #12355b; text-decoration: none; font-weight: 700; padding: 8px 10px; }}
    main {{ padding: 24px 32px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .kpi-card {{ background: white; border-left: 4px solid #2563eb; border-radius: 8px; padding: 16px; box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08); }}
    .kpi-card span {{ display: block; color: #64748b; font-size: 13px; margin-bottom: 8px; }}
    .kpi-card strong {{ font-size: 22px; }}
    section.panel {{ background: white; border-radius: 8px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08); }}
    section.panel ul {{ margin: 10px 0 0; padding-left: 22px; }}
    section.panel li {{ margin: 6px 0; line-height: 1.55; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 10px; text-align: left; }}
    th {{ background: #e8eef7; }}
    .scorecard strong {{ font-size: 30px; color: #12355b; }}
    .disclaimer {{ color: #64748b; font-size: 13px; }}
    .links a {{ color: #1d4ed8; margin-right: 16px; }}
    pre {{ overflow: auto; background: #0f172a; color: #e5e7eb; padding: 16px; border-radius: 8px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title_name)} ({escape(result.stock_id)}) 財務分析儀表板</h1>
    <p>資料來源：{escape(str(result.metadata.get("source", "Goodinfo.tw")))} | 分析年度：{escape(", ".join(result.years))}</p>
  </header>
  <nav aria-label="分析分頁">
    <a href="#ops">經營分析</a>
    <a href="#profit">獲利分析</a>
    <a href="#finance">財務健全度</a>
  </nav>
  <main>
    <div class="kpis">
      {_kpi_card("營收", latest_metrics.get("revenue"))}
      {_kpi_card("營收 CAGR", latest_metrics.get("revenue_cagr"), "%")}
      {_kpi_card("毛利率", latest_metrics.get("gross_margin"), "%")}
      {_kpi_card("淨利率", latest_metrics.get("net_margin"), "%")}
      {_kpi_card("ROE", latest_metrics.get("roe"), "%")}
      {_kpi_card("OCF / 淨利", latest_metrics.get("operating_cash_flow_to_net_income"), "%")}
      {_kpi_card("FCF Margin", latest_metrics.get("free_cash_flow_margin"), "%")}
      {_kpi_card("流動比率", latest_metrics.get("current_ratio"), "%")}
      {_kpi_card("負債權益比", latest_metrics.get("debt_to_equity"), "%")}
    </div>
    {_scorecard(result.scorecard)}
    {_valuation_context(result.valuation)}
    {_diagnostics_panel(result.diagnostics)}
    <section id="ops" class="panel"><h2>經營分析</h2><h3>趨勢解讀</h3>{_insight_list(result.insights.get("operations", []))}</section>
    <section id="profit" class="panel"><h2>獲利分析</h2><h3>趨勢解讀</h3>{_insight_list(result.insights.get("profitability", []))}</section>
    <section id="finance" class="panel"><h2>財務健全度</h2><h3>趨勢解讀</h3>{_insight_list(result.insights.get("financial_health", []))}</section>
    <section class="panel links">
      <h2>資料來源與核對</h2>
      <a href="{escape(income_url)}">Goodinfo.tw</a>
      <a href="{escape(mops_url)}">MOPS 官方申報</a>
    </section>
    <script type="application/json" id="analysis-data">{embedded_json}</script>
  </main>
</body>
</html>
"""
