from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


DISCLAIMER = (
    "This memo is research workflow support only and is not investment advice, "
    "a recommendation, or a decision label."
)


def build_memo_context(
    analysis_path,
    *,
    research_item=None,
    report_path=None,
    workflow_summary_path=None,
    research_summary_path=None,
) -> dict[str, Any]:
    path = Path(analysis_path)
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid analysis JSON: {path}") from exc

    if not isinstance(analysis, dict):
        raise ValueError(f"invalid analysis JSON: {path}")

    return {
        "analysis_path": str(path),
        "report_path": _path_or_missing(report_path),
        "workflow_summary_path": _path_or_missing(workflow_summary_path),
        "research_summary_path": _path_or_missing(research_summary_path),
        "research_item": research_item if isinstance(research_item, dict) else {},
        "analysis": analysis,
    }


def render_memo_markdown(context) -> str:
    ctx = _normalized_context(context)
    title = _title(ctx)

    sections = [
        f"# Research Memo: {_markdown_text(title)}",
        _metadata_markdown(ctx),
        _reliability_markdown(ctx),
        _metrics_markdown(ctx),
        _valuation_markdown(ctx),
        _scorecard_markdown(ctx),
        _diagnostics_markdown(ctx),
        _checklist_markdown(ctx),
        _sources_markdown(ctx),
        _disclaimer_markdown(),
    ]
    return "\n\n".join(sections) + "\n"


def render_memo_html(context) -> str:
    ctx = _normalized_context(context)
    title = _title(ctx)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Research Memo: {_e(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f8fb; color: #182234; }}
    header {{ background: #12355b; color: white; padding: 28px 32px; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px 32px; }}
    section {{ background: white; border: 1px solid #dbe3ef; border-radius: 8px; padding: 18px; margin-bottom: 18px; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid #dbe3ef; padding: 9px; text-align: left; vertical-align: top; }}
    th {{ background: #edf2f8; }}
    ul {{ padding-left: 22px; }}
    .disclaimer {{ color: #64748b; }}
    @media (max-width: 720px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Research Memo: {_e(title)}</h1>
  </header>
  <main>
    {_metadata_html(ctx)}
    {_reliability_html(ctx)}
    {_metrics_html(ctx)}
    {_valuation_html(ctx)}
    {_scorecard_html(ctx)}
    {_diagnostics_html(ctx)}
    {_checklist_html(ctx)}
    {_sources_html(ctx)}
    <section class="disclaimer" id="disclaimer">
      <h2>Disclaimer</h2>
      <p>{_e(DISCLAIMER)}</p>
    </section>
  </main>
</body>
</html>
"""


def write_memo(
    analysis_path,
    output_path,
    *,
    output_format="markdown",
    research_item=None,
    report_path=None,
    workflow_summary_path=None,
    research_summary_path=None,
) -> Path:
    context = build_memo_context(
        analysis_path,
        research_item=research_item,
        report_path=report_path,
        workflow_summary_path=workflow_summary_path,
        research_summary_path=research_summary_path,
    )
    if output_format == "markdown":
        content = render_memo_markdown(context)
    elif output_format == "html":
        content = render_memo_html(context)
    else:
        raise ValueError(f"unsupported memo output format: {output_format}")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _normalized_context(context) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    analysis = context.get("analysis", {})
    research_item = context.get("research_item", {})
    return {
        **context,
        "analysis": analysis if isinstance(analysis, dict) else {},
        "research_item": research_item if isinstance(research_item, dict) else {},
    }


def _title(ctx: dict[str, Any]) -> str:
    analysis = ctx["analysis"]
    research_item = ctx["research_item"]
    stock_id = _text(research_item.get("stock_id") or analysis.get("stock_id"))
    company_name = _text(research_item.get("company_name"))
    if company_name != "-" and stock_id != "-":
        return f"{company_name} ({stock_id})"
    if stock_id != "-":
        return stock_id
    return "-"


def _metadata_markdown(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    rows = [
        ("Stock ID", item.get("stock_id") or ctx["analysis"].get("stock_id")),
        ("Company Name", item.get("company_name")),
        ("Category", item.get("category")),
        ("Priority", item.get("priority")),
        ("Research State", item.get("research_state")),
        ("Notes", item.get("notes")),
    ]
    return "## Research Metadata\n\n" + _markdown_table(("Field", "Value"), rows)


def _reliability_markdown(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    rows = [
        ("Workflow Status", item.get("workflow_status")),
        ("Reliability Status", item.get("reliability_status")),
        ("Attention Reasons", _join_values(item.get("attention_reasons"))),
    ]
    lines = ["## Data Reliability", "", _markdown_table(("Field", "Value"), rows)]
    statuses = _reliability_statuses(ctx)
    status_rows = [
        (
            status.get("stage"),
            status.get("status"),
            status.get("message"),
            status.get("retry_hint"),
        )
        for status in statuses
    ]
    lines.extend(["", "### Data Warnings", "", _markdown_table(("Stage", "Status", "Message", "Retry Hint"), status_rows)])
    return "\n".join(lines)


def _metrics_markdown(ctx: dict[str, Any]) -> str:
    latest_year, metrics = _latest_metrics(ctx)
    rows = [
        ("Latest Year", latest_year),
        ("Revenue", _number(metrics.get("revenue"))),
        ("Gross Margin", _number(metrics.get("gross_margin"), "%")),
        ("Net Margin", _number(metrics.get("net_margin"), "%")),
        ("ROE", _number(metrics.get("roe"), "%")),
        ("EPS", _number(metrics.get("eps"))),
        ("Debt-to-Equity", _number(metrics.get("debt_to_equity"), "%")),
        ("Free-Cash-Flow Margin", _number(metrics.get("free_cash_flow_margin"), "%")),
    ]
    return "## Latest Metrics Snapshot\n\n" + _markdown_table(("Metric", "Value"), rows)


def _valuation_markdown(ctx: dict[str, Any]) -> str:
    valuation = _dict(ctx["analysis"].get("valuation"))
    metrics = _dict(valuation.get("metrics"))
    assumptions = _dict(valuation.get("assumptions"))
    target_prices = _dict(valuation.get("target_prices"))
    metric_rows = [
        ("PE", _number(metrics.get("pe"))),
        ("PB", _number(metrics.get("pb"))),
        ("Dividend Yield", _number(metrics.get("dividend_yield"), "%")),
        ("EPS Assumptions", _join_key_values(assumptions)),
    ]
    target_rows = []
    for scenario in sorted(target_prices):
        row = _dict(target_prices.get(scenario))
        target_rows.append(
            (
                f"{scenario} scenario",
                _number(row.get("eps")),
                _number(row.get("target_pe")),
                _number(row.get("target_price")),
                _number(row.get("price_gap_percent"), "%"),
            )
        )
    if not target_rows:
        target_rows.append(("-", "-", "-", "-", "-"))
    return "\n".join(
        [
            "## Valuation Context",
            "",
            _markdown_table(("Metric", "Value"), metric_rows),
            "",
            "Target-price scenarios are research scenarios, not recommendations.",
            "",
            _markdown_table(("Scenario", "EPS", "Target PE", "Target Price", "Price Gap"), target_rows),
        ]
    )


def _scorecard_markdown(ctx: dict[str, Any]) -> str:
    scorecard = _dict(ctx["analysis"].get("scorecard"))
    dimensions = _dict(scorecard.get("dimensions"))
    rows = [
        ("Total Score", _text(scorecard.get("total_score"))),
        ("Confidence", _number(scorecard.get("confidence"), "%")),
    ]
    dimension_rows = []
    for key in sorted(dimensions):
        dimension = _dict(dimensions.get(key))
        dimension_rows.append(
            (
                dimension.get("label") or key,
                _text(dimension.get("score")),
                _number(dimension.get("confidence"), "%"),
            )
        )
    if not dimension_rows:
        dimension_rows.append(("-", "-", "-"))
    return "\n".join(
        [
            "## Quality Scorecard",
            "",
            _markdown_table(("Field", "Value"), rows),
            "",
            _markdown_table(("Dimension", "Score", "Confidence"), dimension_rows),
        ]
    )


def _diagnostics_markdown(ctx: dict[str, Any]) -> str:
    rows = _diagnostic_rows(ctx)
    return "## Diagnostics\n\n" + _markdown_table(("Level", "Category", "Field", "Message"), rows)


def _checklist_markdown(ctx: dict[str, Any]) -> str:
    return "## Review Checklist\n\n" + "\n".join(f"- [ ] {_markdown_text(item)}" for item in _checklist(ctx))


def _sources_markdown(ctx: dict[str, Any]) -> str:
    rows = [
        ("Analysis JSON", ctx.get("analysis_path")),
        ("Report HTML", ctx.get("report_path")),
        ("Workflow Summary", ctx.get("workflow_summary_path")),
        ("Research Summary", ctx.get("research_summary_path")),
    ]
    return "## Source Links\n\n" + _markdown_table(("Source", "Path"), rows)


def _disclaimer_markdown() -> str:
    return f"## Disclaimer\n\n{_markdown_text(DISCLAIMER)}"


def _metadata_html(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    rows = [
        ("Stock ID", item.get("stock_id") or ctx["analysis"].get("stock_id")),
        ("Company Name", item.get("company_name")),
        ("Category", item.get("category")),
        ("Priority", item.get("priority")),
        ("Research State", item.get("research_state")),
        ("Notes", item.get("notes")),
    ]
    return _html_section("research-metadata", "Research Metadata", _html_table(("Field", "Value"), rows))


def _reliability_html(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    summary = _html_table(
        ("Field", "Value"),
        [
            ("Workflow Status", item.get("workflow_status")),
            ("Reliability Status", item.get("reliability_status")),
            ("Attention Reasons", _join_values(item.get("attention_reasons"))),
        ],
    )
    status_rows = [
        (status.get("stage"), status.get("status"), status.get("message"), status.get("retry_hint"))
        for status in _reliability_statuses(ctx)
    ]
    warnings = _html_table(("Stage", "Status", "Message", "Retry Hint"), status_rows)
    return _html_section("data-reliability", "Data Reliability", summary + "<h3>Data Warnings</h3>" + warnings)


def _metrics_html(ctx: dict[str, Any]) -> str:
    latest_year, metrics = _latest_metrics(ctx)
    rows = [
        ("Latest Year", latest_year),
        ("Revenue", _number(metrics.get("revenue"))),
        ("Gross Margin", _number(metrics.get("gross_margin"), "%")),
        ("Net Margin", _number(metrics.get("net_margin"), "%")),
        ("ROE", _number(metrics.get("roe"), "%")),
        ("EPS", _number(metrics.get("eps"))),
        ("Debt-to-Equity", _number(metrics.get("debt_to_equity"), "%")),
        ("Free-Cash-Flow Margin", _number(metrics.get("free_cash_flow_margin"), "%")),
    ]
    return _html_section("latest-metrics-snapshot", "Latest Metrics Snapshot", _html_table(("Metric", "Value"), rows))


def _valuation_html(ctx: dict[str, Any]) -> str:
    valuation = _dict(ctx["analysis"].get("valuation"))
    metrics = _dict(valuation.get("metrics"))
    assumptions = _dict(valuation.get("assumptions"))
    target_prices = _dict(valuation.get("target_prices"))
    metric_table = _html_table(
        ("Metric", "Value"),
        [
            ("PE", _number(metrics.get("pe"))),
            ("PB", _number(metrics.get("pb"))),
            ("Dividend Yield", _number(metrics.get("dividend_yield"), "%")),
            ("EPS Assumptions", _join_key_values(assumptions)),
        ],
    )
    target_rows = []
    for scenario in sorted(target_prices):
        row = _dict(target_prices.get(scenario))
        target_rows.append(
            (
                f"{scenario} scenario",
                _number(row.get("eps")),
                _number(row.get("target_pe")),
                _number(row.get("target_price")),
                _number(row.get("price_gap_percent"), "%"),
            )
        )
    scenario_table = _html_table(("Scenario", "EPS", "Target PE", "Target Price", "Price Gap"), target_rows)
    body = (
        metric_table
        + "<p>Target-price scenarios are research scenarios, not recommendations.</p>"
        + scenario_table
    )
    return _html_section("valuation-context", "Valuation Context", body)


def _scorecard_html(ctx: dict[str, Any]) -> str:
    scorecard = _dict(ctx["analysis"].get("scorecard"))
    dimensions = _dict(scorecard.get("dimensions"))
    summary = _html_table(
        ("Field", "Value"),
        [
            ("Total Score", _text(scorecard.get("total_score"))),
            ("Confidence", _number(scorecard.get("confidence"), "%")),
        ],
    )
    dimension_rows = []
    for key in sorted(dimensions):
        dimension = _dict(dimensions.get(key))
        dimension_rows.append((dimension.get("label") or key, _text(dimension.get("score")), _number(dimension.get("confidence"), "%")))
    return _html_section(
        "quality-scorecard",
        "Quality Scorecard",
        summary + _html_table(("Dimension", "Score", "Confidence"), dimension_rows),
    )


def _diagnostics_html(ctx: dict[str, Any]) -> str:
    return _html_section(
        "diagnostics",
        "Diagnostics",
        _html_table(("Level", "Category", "Field", "Message"), _diagnostic_rows(ctx)),
    )


def _checklist_html(ctx: dict[str, Any]) -> str:
    items = "".join(f"<li>{_e(item)}</li>" for item in _checklist(ctx))
    return _html_section("review-checklist", "Review Checklist", f"<ul>{items}</ul>")


def _sources_html(ctx: dict[str, Any]) -> str:
    rows = [
        ("Analysis JSON", ctx.get("analysis_path")),
        ("Report HTML", ctx.get("report_path")),
        ("Workflow Summary", ctx.get("workflow_summary_path")),
        ("Research Summary", ctx.get("research_summary_path")),
    ]
    return _html_section("source-links", "Source Links", _html_table(("Source", "Path"), rows))


def _html_section(section_id: str, title: str, body: str) -> str:
    return f'<section id="{_e(section_id)}"><h2>{_e(title)}</h2>{body}</section>'


def _latest_metrics(ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    analysis = ctx["analysis"]
    years = analysis.get("years", [])
    latest_year = str(years[0]) if isinstance(years, list) and years else "-"
    metrics_by_year = _dict(analysis.get("metrics_by_year"))
    return latest_year, _dict(metrics_by_year.get(latest_year))


def _reliability_statuses(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(ctx["analysis"].get("metadata"))
    statuses = metadata.get("reliability", [])
    if not isinstance(statuses, list):
        return []
    return [status for status in statuses if isinstance(status, dict)]


def _diagnostic_rows(ctx: dict[str, Any]) -> list[tuple[Any, ...]]:
    diagnostics = _dict(ctx["analysis"].get("diagnostics"))
    issues = diagnostics.get("issues", [])
    rows = []
    if isinstance(issues, list):
        for issue in issues:
            issue = _dict(issue)
            rows.append((issue.get("level"), issue.get("category"), issue.get("field"), issue.get("message")))
    return rows or [("-", "-", "-", "-")]


def _checklist(ctx: dict[str, Any]) -> list[str]:
    item = ctx["research_item"]
    statuses = _reliability_statuses(ctx)
    reliability_status = item.get("reliability_status")
    has_reliability_warning = reliability_status in {"warning", "error"} or any(
        status.get("status") in {"warning", "error"} for status in statuses
    )
    valuation = _dict(ctx["analysis"].get("valuation"))
    assumptions = _dict(valuation.get("assumptions"))
    target_prices = _dict(valuation.get("target_prices"))
    has_diagnostics = _diagnostic_rows(ctx) != [("-", "-", "-", "-")]

    items: list[str] = []
    if has_reliability_warning:
        items.append("Review data reliability warning")
    if not assumptions or not target_prices:
        items.append("Verify missing valuation assumptions")
    if has_diagnostics:
        items.append("Inspect diagnostics warnings")
    items.append("Review source filings manually")
    items.append("Confirm research state and notes")
    return items


def _markdown_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    rendered_rows = rows or [tuple("-" for _ in headers)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rendered_rows:
        padded = list(row) + ["-"] * (len(headers) - len(row))
        lines.append("| " + " | ".join(_markdown_cell(value) for value in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _markdown_text(value).replace("|", "\\|")


def _markdown_text(value: Any) -> str:
    text = _text(value)
    if text == "-":
        return text
    normalized = " ".join(text.split())
    return (
        normalized
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _html_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    rendered_rows = rows or [tuple("-" for _ in headers)]
    header_html = "".join(f"<th>{_e(header)}</th>" for header in headers)
    body_html = ""
    for row in rendered_rows:
        padded = list(row) + ["-"] * (len(headers) - len(row))
        body_html += "<tr>" + "".join(f"<td>{_e(_text(value))}</td>" for value in padded[: len(headers)]) + "</tr>"
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _join_values(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_text(item) for item in value if _text(item) != "-") or "-"
    return _text(value)


def _join_key_values(value: dict[str, Any]) -> str:
    parts = [f"{key}: {_text(value[key])}" for key in sorted(value)]
    return "; ".join(parts) or "-"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.2f}{suffix}"
    return _text(value)


def _text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _path_or_missing(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(Path(value))


def _e(value: Any) -> str:
    return escape(_text(value), quote=True)
