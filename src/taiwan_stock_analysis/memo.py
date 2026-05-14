from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.traceability import build_artifact_registry, read_run_metadata


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
        _executive_summary_markdown(ctx),
        _metadata_markdown(ctx),
        _thesis_snapshot_markdown(ctx),
        _observations_markdown(ctx),
        _catalysts_markdown(ctx),
        _risks_markdown(ctx),
        _open_questions_markdown(ctx),
        _reliability_markdown(ctx),
        _metrics_markdown(ctx),
        _valuation_markdown(ctx),
        _scorecard_markdown(ctx),
        _diagnostics_markdown(ctx),
        _next_actions_markdown(ctx),
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
    {_executive_summary_html(ctx)}
    {_metadata_html(ctx)}
    {_thesis_snapshot_html(ctx)}
    {_observations_html(ctx)}
    {_catalysts_html(ctx)}
    {_risks_html(ctx)}
    {_open_questions_html(ctx)}
    {_reliability_html(ctx)}
    {_metrics_html(ctx)}
    {_valuation_html(ctx)}
    {_scorecard_html(ctx)}
    {_diagnostics_html(ctx)}
    {_next_actions_html(ctx)}
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


def write_research_memos(
    research_summary_path: Path,
    workflow_dir: Path,
    output_dir: Path,
    *,
    output_format="both",
) -> Path:
    if output_format not in {"both", "markdown", "html"}:
        raise ValueError(f"unsupported memo output format: {output_format}")

    research_summary_path = Path(research_summary_path)
    workflow_dir = Path(workflow_dir)
    output_dir = Path(output_dir)
    payload = json.loads(research_summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid research summary JSON: {research_summary_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for item in _research_items(payload):
        stock_id = _text(item.get("stock_id")).strip()
        if stock_id == "-":
            skipped.append({"stock_id": "-", "reason": "stock_id missing"})
            continue

        analysis_path = _analysis_json_path(workflow_dir, stock_id)
        if analysis_path is None:
            skipped.append({"stock_id": stock_id, "reason": "analysis JSON not found"})
            continue

        report_path = analysis_path.with_name(f"{stock_id}_analysis.html")
        result: dict[str, str] = {"stock_id": stock_id}
        try:
            if output_format in {"both", "markdown"}:
                markdown_path = output_dir / f"{stock_id}_memo.md"
                write_memo(
                    analysis_path,
                    markdown_path,
                    output_format="markdown",
                    research_item=item,
                    report_path=report_path,
                    workflow_summary_path=workflow_dir / "workflow_summary.json",
                    research_summary_path=research_summary_path,
                )
                result["markdown_path"] = str(markdown_path)
            if output_format in {"both", "html"}:
                html_path = output_dir / f"{stock_id}_memo.html"
                write_memo(
                    analysis_path,
                    html_path,
                    output_format="html",
                    research_item=item,
                    report_path=report_path,
                    workflow_summary_path=workflow_dir / "workflow_summary.json",
                    research_summary_path=research_summary_path,
                )
                result["html_path"] = str(html_path)
        except Exception as exc:
            skipped.append({"stock_id": stock_id, "reason": str(exc)})
            continue
        generated.append(result)

    summary_path = output_dir / "memo_summary.json"
    summary = {
        "output_dir": str(output_dir),
        "generated": generated,
        "skipped": skipped,
        "artifact_registry": build_artifact_registry(
            str(summary_path),
            dependencies={
                "workflow_summary": str(workflow_dir / "workflow_summary.json"),
                "research_summary": str(research_summary_path),
            },
            outputs={
                "markdown": [
                    item["markdown_path"]
                    for item in generated
                    if "markdown_path" in item
                ],
                "html": [
                    item["html_path"]
                    for item in generated
                    if "html_path" in item
                ],
            },
        ),
    }
    run_metadata = read_run_metadata(payload)
    if run_metadata:
        summary["run_metadata"] = run_metadata
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def _research_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _analysis_json_path(workflow_dir: Path, stock_id: str) -> Path | None:
    for subdir in ("reports", "valuation-reports"):
        path = workflow_dir / subdir / f"{stock_id}_raw_data.json"
        if path.exists():
            return path
    return None


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


def _thesis_snapshot_markdown(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    rows = [
        ("Thesis", item.get("thesis")),
        ("Key risks", item.get("key_risks")),
        ("Watch triggers", item.get("watch_triggers")),
        ("Follow-up questions", item.get("follow_up_questions")),
    ]
    return "## Thesis Snapshot\n\n" + _markdown_table(("Field", "Value"), rows)


def _executive_summary_markdown(ctx: dict[str, Any]) -> str:
    return "## Executive Summary\n\n" + _markdown_bullets(_executive_summary_lines(ctx))


def _observations_markdown(ctx: dict[str, Any]) -> str:
    lines = ["## Key Observations"]
    for heading, items in _observation_groups(ctx).items():
        lines.extend(["", f"### {_markdown_text(heading)}", "", _markdown_bullets(items)])
    return "\n".join(lines)


def _catalysts_markdown(ctx: dict[str, Any]) -> str:
    return "## Catalysts\n\n" + _markdown_bullets(_catalyst_lines(ctx))


def _risks_markdown(ctx: dict[str, Any]) -> str:
    return "## Risks\n\n" + _markdown_bullets(_risk_lines(ctx))


def _open_questions_markdown(ctx: dict[str, Any]) -> str:
    return "## Open Questions\n\n" + _markdown_bullets(_open_question_lines(ctx))


def _next_actions_markdown(ctx: dict[str, Any]) -> str:
    lines = ["## Next Research Actions"]
    for heading, items in _next_action_groups(ctx).items():
        lines.extend(["", f"### {_markdown_text(heading)}", "", _markdown_bullets(items)])
    return "\n".join(lines)


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
    lines = [
        "## Valuation Context",
        "",
        _markdown_table(("Metric", "Value"), metric_rows),
        "",
        "Target-price scenarios are research scenarios, not recommendations.",
        "",
        _markdown_table(("Scenario", "EPS", "Target PE", "Target Price", "Price Gap"), target_rows),
    ]
    scenario_rows = _scenario_summary_rows(valuation)
    if scenario_rows:
        lines.extend(["", "### Scenario Summary", "", _markdown_table(("Field", "Value"), scenario_rows)])
    return "\n".join(lines)


def _scenario_summary_rows(valuation: dict[str, Any]) -> list[tuple[str, str]]:
    scenario_summary = _dict(valuation.get("scenario_summary"))
    if not scenario_summary:
        return []

    fair_value_range = _dict(scenario_summary.get("fair_value_range"))
    confidence = _dict(scenario_summary.get("valuation_confidence"))
    confidence_label = _text(confidence.get("label"))
    confidence_score = _number(confidence.get("score"))
    if confidence_label != "-" and confidence_score != "-":
        confidence_value = f"{confidence_label} (score {confidence_score})"
    elif confidence_label != "-":
        confidence_value = confidence_label
    else:
        confidence_value = confidence_score

    rows = [
        (
            "Fair-value range",
            "; ".join(
                [
                    f"Low: {_number(fair_value_range.get('low'))}",
                    f"Base: {_number(fair_value_range.get('base'))}",
                    f"High: {_number(fair_value_range.get('high'))}",
                ]
            ),
        ),
        ("Margin of safety", _number(scenario_summary.get("margin_of_safety_percent"), "%")),
        ("Valuation confidence", confidence_value),
    ]
    reasons = _join_values(confidence.get("reasons"))
    if reasons != "-":
        rows.append(("Confidence reasons", reasons))
    return rows


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


def _thesis_snapshot_html(ctx: dict[str, Any]) -> str:
    item = ctx["research_item"]
    rows = [
        ("Thesis", item.get("thesis")),
        ("Key risks", item.get("key_risks")),
        ("Watch triggers", item.get("watch_triggers")),
        ("Follow-up questions", item.get("follow_up_questions")),
    ]
    return _html_section("thesis-snapshot", "Thesis Snapshot", _html_table(("Field", "Value"), rows))


def _executive_summary_html(ctx: dict[str, Any]) -> str:
    return _html_section("executive-summary", "Executive Summary", _html_list(_executive_summary_lines(ctx)))


def _observations_html(ctx: dict[str, Any]) -> str:
    body = ""
    for heading, items in _observation_groups(ctx).items():
        body += f"<h3>{_e(heading)}</h3>{_html_list(items)}"
    return _html_section("key-observations", "Key Observations", body)


def _catalysts_html(ctx: dict[str, Any]) -> str:
    return _html_section("catalysts", "Catalysts", _html_list(_catalyst_lines(ctx)))


def _risks_html(ctx: dict[str, Any]) -> str:
    return _html_section("risks", "Risks", _html_list(_risk_lines(ctx)))


def _open_questions_html(ctx: dict[str, Any]) -> str:
    return _html_section("open-questions", "Open Questions", _html_list(_open_question_lines(ctx)))


def _next_actions_html(ctx: dict[str, Any]) -> str:
    body = ""
    for heading, items in _next_action_groups(ctx).items():
        body += f"<h3>{_e(heading)}</h3>{_html_list(items)}"
    return _html_section("next-research-actions", "Next Research Actions", body)


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
    scenario_summary_rows = _scenario_summary_rows(valuation)
    scenario_summary = ""
    if scenario_summary_rows:
        scenario_summary = "<h3>Scenario Summary</h3>" + _html_table(("Field", "Value"), scenario_summary_rows)
    body = (
        metric_table
        + "<p>Target-price scenarios are research scenarios, not recommendations.</p>"
        + scenario_table
        + scenario_summary
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


def _executive_summary_lines(ctx: dict[str, Any]) -> list[str]:
    latest_year, metrics = _latest_metrics(ctx)
    item = ctx["research_item"]
    lines: list[str] = []
    if latest_year != "-":
        lines.append(f"Latest metrics cover {latest_year}.")
    revenue = _number(metrics.get("revenue"))
    eps = _number(metrics.get("eps"))
    if revenue != "-" or eps != "-":
        lines.append(f"Latest snapshot: revenue {revenue}; EPS {eps}.")
    research_state = _text(item.get("research_state"))
    if research_state != "-":
        lines.append(f"Research state is {research_state}.")
    return lines or ["-"]


def _observation_groups(ctx: dict[str, Any]) -> dict[str, list[str]]:
    latest_year, metrics = _latest_metrics(ctx)
    diagnostics = _diagnostic_rows(ctx)
    metrics_lines: list[str] = []
    if latest_year != "-":
        metrics_lines.append(f"Latest reporting year: {latest_year}.")
    gross_margin = _number(metrics.get("gross_margin"), "%")
    roe = _number(metrics.get("roe"), "%")
    if gross_margin != "-" or roe != "-":
        metrics_lines.append(f"Profitability snapshot: gross margin {gross_margin}; ROE {roe}.")

    evidence_lines: list[str] = []
    if diagnostics != [("-", "-", "-", "-")]:
        evidence_lines.append(f"Diagnostics reported {len(diagnostics)} item(s) for review.")
    reasons = _join_values(ctx["research_item"].get("attention_reasons"))
    if reasons != "-":
        evidence_lines.append(f"Attention reasons: {reasons}.")

    return {
        "Operating Snapshot": metrics_lines or ["-"],
        "Review Signals": evidence_lines or ["-"],
    }


def _catalyst_lines(ctx: dict[str, Any]) -> list[str]:
    valuation = _dict(ctx["analysis"].get("valuation"))
    target_prices = _dict(valuation.get("target_prices"))
    scorecard = _dict(ctx["analysis"].get("scorecard"))
    lines: list[str] = []
    if target_prices:
        lines.append("Valuation scenarios are available for review.")
    confidence = _number(scorecard.get("confidence"), "%")
    if confidence != "-":
        lines.append(f"Scorecard confidence is {confidence}.")
    return lines or ["-"]


def _risk_lines(ctx: dict[str, Any]) -> list[str]:
    diagnostics = _diagnostic_rows(ctx)
    valuation = _dict(ctx["analysis"].get("valuation"))
    assumptions = _dict(valuation.get("assumptions"))
    reliability_status = _text(ctx["research_item"].get("reliability_status"))
    lines: list[str] = []
    if diagnostics != [("-", "-", "-", "-")]:
        lines.append(f"Diagnostics reported {len(diagnostics)} item(s) that need review.")
    if reliability_status in {"warning", "error"}:
        lines.append(f"Reliability status is {reliability_status}.")
    if not assumptions:
        lines.append("Valuation assumptions need manual review.")
    return lines or ["-"]


def _open_question_lines(ctx: dict[str, Any]) -> list[str]:
    valuation = _dict(ctx["analysis"].get("valuation"))
    assumptions = _dict(valuation.get("assumptions"))
    reliability_status = _text(ctx["research_item"].get("reliability_status"))
    lines: list[str] = []
    if reliability_status in {"warning", "error"}:
        lines.append("What data issue caused the current warning state?")
    if not assumptions:
        lines.append("Which valuation assumptions should be supplied before review?")
    return lines or ["-"]


def _next_action_groups(ctx: dict[str, Any]) -> dict[str, list[str]]:
    valuation = _dict(ctx["analysis"].get("valuation"))
    assumptions = _dict(valuation.get("assumptions"))
    target_prices = _dict(valuation.get("target_prices"))
    diagnostics = _diagnostic_rows(ctx)
    reliability_status = _text(ctx["research_item"].get("reliability_status"))

    data_checks: list[str] = []
    if reliability_status in {"warning", "error"}:
        data_checks.append("Trace the current reliability warning.")
    if diagnostics != [("-", "-", "-", "-")]:
        data_checks.append("Review reported diagnostics.")

    valuation_checks: list[str] = []
    if not assumptions:
        valuation_checks.append("Fill or verify valuation assumptions.")
    if not target_prices:
        valuation_checks.append("Confirm whether valuation scenarios are expected.")

    thesis_checks = ["Compare the memo against source filings and research notes."]
    return {
        "Data Checks": data_checks or ["-"],
        "Valuation Checks": valuation_checks or ["-"],
        "Thesis Checks": thesis_checks,
    }


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


def _markdown_bullets(items: list[str]) -> str:
    return "\n".join(f"- {_markdown_text(item)}" for item in (items or ["-"]))


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


def _html_list(items: list[str]) -> str:
    rendered_items = items or ["-"]
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in rendered_items) + "</ul>"


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
