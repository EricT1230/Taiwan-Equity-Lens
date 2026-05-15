from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.traceability import build_artifact_registry, read_run_metadata


_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"invalid {label} JSON")
    return payload


def _display_path(path: Path | None) -> str:
    return str(path) if path is not None else ""


def _text(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _markdown_cell(value: Any, fallback: str = "-") -> str:
    text = _text(value, fallback)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _markdown_scalar(value: Any, fallback: str = "-") -> str:
    text = _markdown_cell(value, fallback)
    return "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text).strip() or fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _format_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "-"
    return ", ".join(str(item) for item in value)


def _has_research_value(item: dict[str, Any], key: str) -> bool:
    value = item.get(key)
    if value is None:
        return False
    if isinstance(value, list):
        return any(str(entry).strip() not in {"", "-"} for entry in value)
    return str(value).strip() not in {"", "-"}


def _research_quality_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    high_priority_missing_thesis = [
        str(item.get("stock_id"))
        for item in items
        if str(item.get("priority")).lower() == "high" and not _has_research_value(item, "thesis")
    ]
    high_priority_missing_follow_up = [
        str(item.get("stock_id"))
        for item in items
        if str(item.get("priority")).lower() == "high" and not _has_research_value(item, "follow_up_questions")
    ]
    return {
        "total": len(items),
        "with_thesis": sum(1 for item in items if _has_research_value(item, "thesis")),
        "with_watch_triggers": sum(1 for item in items if _has_research_value(item, "watch_triggers")),
        "with_follow_up_questions": sum(1 for item in items if _has_research_value(item, "follow_up_questions")),
        "high_priority_missing_thesis": sorted(high_priority_missing_thesis),
        "high_priority_missing_follow_up": sorted(high_priority_missing_follow_up),
    }


def _coverage_text(item: dict[str, Any], key: str) -> str:
    return "Yes" if _has_research_value(item, key) else "-"


def _review_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    reasons = item.get("attention_reasons", [])
    has_reasons = bool(reasons)
    priority = str(item.get("priority", "")).lower()
    stock_id = str(item.get("stock_id", ""))
    return (0 if has_reasons else 1, _PRIORITY_RANK.get(priority, len(_PRIORITY_RANK)), stock_id)


def _summary_counts(research_summary: dict[str, Any], top_level_key: str, nested_key: str) -> dict[str, Any]:
    top_level = _dict(research_summary.get(top_level_key))
    if top_level:
        return top_level
    return _dict(_dict(research_summary.get("counts")).get(nested_key))


def _source_audit_from(
    research_summary: dict[str, Any],
    workflow_summary: dict[str, Any],
) -> dict[str, Any]:
    research_source_audit = _dict(research_summary.get("source_audit"))
    if research_source_audit:
        return research_source_audit
    return _dict(workflow_summary.get("source_audit"))


def _source_audit_by_stock(source_audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items_by_stock: dict[str, dict[str, Any]] = {}
    raw_items = source_audit.get("items", [])
    if not isinstance(raw_items, list):
        return items_by_stock
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "").strip()
        if stock_id:
            items_by_stock[stock_id] = item
    return items_by_stock


def _source_audit_reasons(source_audit_item: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for component_name in ("financial_statement", "price"):
        component = source_audit_item.get(component_name)
        if not isinstance(component, dict):
            continue
        reason = _source_audit_reason(component)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def _source_audit_reason(component: dict[str, Any]) -> str:
    for key in ("review_reason", "reason"):
        raw_reason = component.get(key)
        if not isinstance(raw_reason, str):
            continue
        reason = raw_reason.strip()
        if reason:
            return reason
    return ""


def _clean_source_audit_reasons(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    reasons: list[str] = []
    for raw_reason in value:
        if not isinstance(raw_reason, str):
            continue
        reason = raw_reason.strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def build_pack_context(
    research_summary_path: Path,
    *,
    research_csv_path: Path,
    workflow_summary_path: Path | None = None,
    memo_summary_path: Path | None = None,
    dashboard_path: Path | None = None,
) -> dict[str, Any]:
    research_summary = _load_json(Path(research_summary_path), "research summary")
    workflow_summary = (
        _load_json(Path(workflow_summary_path), "workflow summary") if workflow_summary_path is not None else {}
    )
    memo_summary = _load_json(Path(memo_summary_path), "memo summary") if memo_summary_path is not None else {}
    source_audit = _source_audit_from(research_summary, workflow_summary)
    source_audit_items = _source_audit_by_stock(source_audit)

    memo_outputs: dict[str, dict[str, str]] = {}
    generated = memo_summary.get("generated", [])
    if isinstance(generated, list):
        for generated_item in generated:
            if not isinstance(generated_item, dict):
                continue
            stock_id = str(generated_item.get("stock_id", ""))
            if not stock_id:
                continue
            memo_outputs[stock_id] = {
                "memo_markdown_path": _text(generated_item.get("markdown_path")),
                "memo_html_path": _text(generated_item.get("html_path")),
            }

    items: list[dict[str, Any]] = []
    raw_items = research_summary.get("items", [])
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            stock_id = str(item.get("stock_id", ""))
            item["stock_id"] = stock_id
            item["company_name"] = _text(item.get("company_name"))
            item["research_state"] = _text(item.get("research_state"))
            item["priority"] = _text(item.get("priority"))
            item["workflow_status"] = _text(item.get("workflow_status"))
            item["reliability_status"] = _text(item.get("reliability_status"))
            source_audit_item = source_audit_items.get(stock_id, {})
            item["source_audit_status"] = _text(
                item.get("source_audit_status") or source_audit_item.get("status")
            )
            item["thesis"] = _text(item.get("thesis"))
            item["watch_triggers"] = _text(item.get("watch_triggers"))
            item["follow_up_questions"] = _text(item.get("follow_up_questions"))
            reasons = item.get("attention_reasons", [])
            item["attention_reasons"] = [str(reason) for reason in reasons] if isinstance(reasons, list) else []
            item["source_audit_reasons"] = _clean_source_audit_reasons(item.get("source_audit_reasons", []))
            if not item["source_audit_reasons"]:
                item["source_audit_reasons"] = _source_audit_reasons(source_audit_item)
            item.update(
                memo_outputs.get(
                    stock_id,
                    {"memo_markdown_path": "-", "memo_html_path": "-"},
                )
            )
            items.append(item)

    workflow_reliability = workflow_summary.get("data_reliability", {})
    if not isinstance(workflow_reliability, dict):
        workflow_reliability = {}

    return {
        "research_summary_path": str(research_summary_path),
        "research_csv_path": str(research_csv_path),
        "workflow_summary_path": _display_path(workflow_summary_path),
        "memo_summary_path": _display_path(memo_summary_path),
        "dashboard_path": _display_path(dashboard_path),
        "counts": research_summary.get("counts", {}),
        "research_state_counts": _summary_counts(research_summary, "research_state_counts", "by_state"),
        "priority_counts": _summary_counts(research_summary, "priority_counts", "by_priority"),
        "run_metadata": read_run_metadata(research_summary),
        "workflow_reliability": workflow_reliability,
        "source_audit": source_audit,
        "review_action_summary": _dict(research_summary.get("review_action_summary")),
        "review_action_queue": research_summary.get("review_action_queue", []),
        "workflow_summary": workflow_summary,
        "items": items,
        "review_queue": sorted(items, key=_review_sort_key),
        "research_quality": _research_quality_summary(items),
    }


def _format_counts(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "-"
    return ", ".join(f"{key}: {counts[key]}" for key in sorted(counts))


def _format_markdown_counts(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "-"
    return ", ".join(
        f"{_markdown_scalar(key)}: {_markdown_scalar(counts[key])}"
        for key in sorted(counts, key=lambda count_key: str(count_key))
    )


def _attention_text(item: dict[str, Any]) -> str:
    reasons = item.get("attention_reasons", [])
    if isinstance(reasons, list) and reasons:
        return "; ".join(str(reason) for reason in reasons)
    return "-"


def _review_action_markdown_rows(queue: Any) -> list[str]:
    if not isinstance(queue, list):
        return ["-"]
    rows: list[str] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            rows.append(
                " | ".join(
                    [
                        _markdown_cell(item.get("stock_id")),
                        _markdown_cell(item.get("priority")),
                        _markdown_cell(action.get("severity")),
                        _markdown_cell(action.get("category")),
                        _markdown_cell(action.get("message")),
                    ]
                )
            )
    return rows or ["-"]


def _review_action_html_rows(queue: Any) -> str:
    if not isinstance(queue, list):
        return '<tr><td colspan="5">-</td></tr>'
    rows: list[str] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            rows.append(
                "<tr>"
                f"<td>{escape(_text(item.get('stock_id')))}</td>"
                f"<td>{escape(_text(item.get('priority')))}</td>"
                f"<td>{escape(_text(action.get('severity')))}</td>"
                f"<td>{escape(_text(action.get('category')))}</td>"
                f"<td>{escape(_text(action.get('message')))}</td>"
                "</tr>"
            )
    return "".join(rows) or '<tr><td colspan="5">-</td></tr>'


def render_pack_markdown(context: dict[str, Any]) -> str:
    research_quality = _dict(context.get("research_quality"))
    source_audit = _dict(context.get("source_audit"))
    review_action_summary = _dict(context.get("review_action_summary"))
    overview_lines = [
        "# Research Pack",
        "",
        "## Run Overview",
        f"- Research CSV: {_text(context.get('research_csv_path'))}",
        f"- Research summary: {_text(context.get('research_summary_path'))}",
        f"- Totals: {_format_counts(context.get('counts'))}",
        f"- Research states: {_format_counts(context.get('research_state_counts'))}",
        f"- Priorities: {_format_counts(context.get('priority_counts'))}",
        "",
        "## Research Quality Overview",
        f"- With thesis: {_text(research_quality.get('with_thesis'))}",
        f"- With watch triggers: {_text(research_quality.get('with_watch_triggers'))}",
        f"- Follow-up coverage: {_text(research_quality.get('with_follow_up_questions'))}",
        f"- High-priority missing thesis: {_format_list(research_quality.get('high_priority_missing_thesis'))}",
        f"- High-priority missing follow-up: {_format_list(research_quality.get('high_priority_missing_follow_up'))}",
        "",
        "## Source Audit Overview",
        f"- Overall: {_markdown_scalar(source_audit.get('status'))}",
        f"- Counts: {_format_markdown_counts(source_audit.get('counts'))}",
        "",
        "## Review Action Checklist",
        f"- Total open: {_markdown_scalar(review_action_summary.get('total_open'))}",
        f"- By severity: {_format_markdown_counts(review_action_summary.get('by_severity'))}",
        f"- By category: {_format_markdown_counts(review_action_summary.get('by_category'))}",
        "",
        "| Stock | Priority | Severity | Category | Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    review_action_rows = _review_action_markdown_rows(context.get("review_action_queue"))

    reliability_lines = [
        "",
        "## Reliability Overview",
        f"- Workflow reliability: {_format_counts(context.get('workflow_reliability'))}",
        "",
        "## Priority Review Queue",
        "| Stock | Company | State | Priority | Workflow | Reliability | Attention |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    queue_rows = [
        " | ".join(
            [
                _text(item.get("stock_id")),
                _markdown_cell(item.get("company_name")),
                _markdown_cell(item.get("research_state")),
                _markdown_cell(item.get("priority")),
                _markdown_cell(item.get("workflow_status")),
                _markdown_cell(item.get("reliability_status")),
                _markdown_cell(_attention_text(item)),
            ]
        )
        for item in context.get("review_queue", [])
        if isinstance(item, dict)
    ]
    if not queue_rows:
        queue_rows.append("-")

    output_lines = [
        "",
        "## Generated Outputs",
        f"- Dashboard: {_text(context.get('dashboard_path'))}",
        f"- Workflow summary: {_text(context.get('workflow_summary_path'))}",
        f"- Research summary: {_text(context.get('research_summary_path'))}",
        f"- Memo summary: {_text(context.get('memo_summary_path'))}",
        "",
        "## Per-Stock Research Index",
        "| Stock | Company | Thesis | Follow-up | Memo Markdown | Memo HTML | Attention |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    index_rows = [
        " | ".join(
            [
                _markdown_cell(item.get("stock_id")),
                _markdown_cell(item.get("company_name")),
                _markdown_cell(_coverage_text(item, "thesis")),
                _markdown_cell(_coverage_text(item, "follow_up_questions")),
                _markdown_cell(item.get("memo_markdown_path")),
                _markdown_cell(item.get("memo_html_path")),
                _markdown_cell(_attention_text(item)),
            ]
        )
        for item in context.get("items", [])
        if isinstance(item, dict)
    ]
    if not index_rows:
        index_rows.append("-")

    closing_lines = [
        "",
        "## Review Checklist",
        "- [ ] Review warning and error counts before handoff",
        "- [ ] Confirm priority review items were read",
        "- [ ] Open memo and dashboard outputs as needed",
        "",
        "This pack is research workflow support only and is not investment advice.",
        "",
    ]
    return "\n".join(overview_lines + review_action_rows + reliability_lines + queue_rows + output_lines + index_rows + closing_lines)


def _html_list_item(label: str, value: Any) -> str:
    return f"<li><strong>{escape(label)}:</strong> {escape(_text(value))}</li>"


def render_pack_html(context: dict[str, Any]) -> str:
    research_quality = _dict(context.get("research_quality"))
    source_audit = _dict(context.get("source_audit"))
    review_action_summary = _dict(context.get("review_action_summary"))
    queue_rows = []
    for item in context.get("review_queue", []):
        if not isinstance(item, dict):
            continue
        queue_rows.append(
            "<tr>"
            f"<td>{escape(_text(item.get('stock_id')))}</td>"
            f"<td>{escape(_text(item.get('company_name')))}</td>"
            f"<td>{escape(_text(item.get('research_state')))}</td>"
            f"<td>{escape(_text(item.get('priority')))}</td>"
            f"<td>{escape(_text(item.get('workflow_status')))}</td>"
            f"<td>{escape(_text(item.get('reliability_status')))}</td>"
            f"<td>{escape(_attention_text(item))}</td>"
            "</tr>"
        )
    if not queue_rows:
        queue_rows.append('<tr><td colspan="7">-</td></tr>')

    index_rows = []
    for item in context.get("items", []):
        if not isinstance(item, dict):
            continue
        index_rows.append(
            "<tr>"
            f"<td>{escape(_text(item.get('stock_id')))}</td>"
            f"<td>{escape(_text(item.get('company_name')))}</td>"
            f"<td>{escape(_coverage_text(item, 'thesis'))}</td>"
            f"<td>{escape(_coverage_text(item, 'follow_up_questions'))}</td>"
            f"<td>{escape(_text(item.get('memo_markdown_path')))}</td>"
            f"<td>{escape(_text(item.get('memo_html_path')))}</td>"
            f"<td>{escape(_attention_text(item))}</td>"
            "</tr>"
        )
    if not index_rows:
        index_rows.append('<tr><td colspan="7">-</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Research Pack</title>
</head>
<body>
  <main>
    <h1>Research Pack</h1>
    <section>
      <h2>Run Overview</h2>
      <ul>
        {_html_list_item("Research CSV", context.get("research_csv_path"))}
        {_html_list_item("Research summary", context.get("research_summary_path"))}
        {_html_list_item("Totals", _format_counts(context.get("counts")))}
        {_html_list_item("Research states", _format_counts(context.get("research_state_counts")))}
        {_html_list_item("Priorities", _format_counts(context.get("priority_counts")))}
      </ul>
    </section>
    <section>
      <h2>Research Quality Overview</h2>
      <ul>
        {_html_list_item("With thesis", research_quality.get("with_thesis"))}
        {_html_list_item("With watch triggers", research_quality.get("with_watch_triggers"))}
        {_html_list_item("Follow-up coverage", research_quality.get("with_follow_up_questions"))}
        {_html_list_item("High-priority missing thesis", _format_list(research_quality.get("high_priority_missing_thesis")))}
        {_html_list_item("High-priority missing follow-up", _format_list(research_quality.get("high_priority_missing_follow_up")))}
      </ul>
    </section>
    <section>
      <h2>Source Audit Overview</h2>
      <ul>
        {_html_list_item("Overall", source_audit.get("status"))}
        {_html_list_item("Counts", _format_counts(source_audit.get("counts")))}
      </ul>
    </section>
    <section>
      <h2>Review Action Checklist</h2>
      <ul>
        {_html_list_item("Total open", review_action_summary.get("total_open"))}
        {_html_list_item("By severity", _format_counts(review_action_summary.get("by_severity")))}
        {_html_list_item("By category", _format_counts(review_action_summary.get("by_category")))}
      </ul>
      <table>
        <thead><tr><th>Stock</th><th>Priority</th><th>Severity</th><th>Category</th><th>Action</th></tr></thead>
        <tbody>{_review_action_html_rows(context.get("review_action_queue"))}</tbody>
      </table>
    </section>
    <section>
      <h2>Reliability Overview</h2>
      <ul>
        {_html_list_item("Workflow reliability", _format_counts(context.get("workflow_reliability")))}
      </ul>
    </section>
    <section>
      <h2>Priority Review Queue</h2>
      <table>
        <thead><tr><th>Stock</th><th>Company</th><th>State</th><th>Priority</th><th>Workflow</th><th>Reliability</th><th>Attention</th></tr></thead>
        <tbody>{"".join(queue_rows)}</tbody>
      </table>
    </section>
    <section>
      <h2>Generated Outputs</h2>
      <ul>
        {_html_list_item("Dashboard", context.get("dashboard_path"))}
        {_html_list_item("Workflow summary", context.get("workflow_summary_path"))}
        {_html_list_item("Research summary", context.get("research_summary_path"))}
        {_html_list_item("Memo summary", context.get("memo_summary_path"))}
      </ul>
    </section>
    <section>
      <h2>Per-Stock Research Index</h2>
      <table>
        <thead><tr><th>Stock</th><th>Company</th><th>Thesis</th><th>Follow-up</th><th>Memo Markdown</th><th>Memo HTML</th><th>Attention</th></tr></thead>
        <tbody>{"".join(index_rows)}</tbody>
      </table>
    </section>
    <section>
      <h2>Review Checklist</h2>
      <ul>
        <li>[ ] Review warning and error counts before handoff</li>
        <li>[ ] Confirm priority review items were read</li>
        <li>[ ] Open memo and dashboard outputs as needed</li>
      </ul>
    </section>
    <p>This pack is research workflow support only and is not investment advice.</p>
  </main>
</body>
</html>
"""


def write_research_pack(
    research_summary_path: Path,
    output_dir: Path,
    *,
    research_csv_path: Path,
    workflow_summary_path: Path | None = None,
    memo_summary_path: Path | None = None,
    dashboard_path: Path | None = None,
    output_format: str = "both",
) -> Path:
    context = build_pack_context(
        research_summary_path,
        research_csv_path=research_csv_path,
        workflow_summary_path=workflow_summary_path,
        memo_summary_path=memo_summary_path,
        dashboard_path=dashboard_path,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized_format = output_format.lower()
    if normalized_format not in {"both", "markdown", "html"}:
        raise ValueError("output_format must be 'both', 'markdown', or 'html'")

    markdown_path = output_dir / "research-pack.md"
    html_path = output_dir / "research-pack.html"
    if normalized_format in {"both", "markdown"}:
        markdown_path.write_text(render_pack_markdown(context), encoding="utf-8")
    if normalized_format in {"both", "html"}:
        html_path.write_text(render_pack_html(context), encoding="utf-8")

    warnings: list[str] = []
    if not context["workflow_summary_path"]:
        warnings.append("workflow summary not provided")
    if not context["memo_summary_path"]:
        warnings.append("memo summary not provided")

    summary_path = output_dir / "pack_summary.json"
    markdown_output = str(markdown_path) if normalized_format in {"both", "markdown"} else ""
    html_output = str(html_path) if normalized_format in {"both", "html"} else ""
    outputs = {}
    if markdown_output:
        outputs["markdown"] = markdown_output
    if html_output:
        outputs["html"] = html_output

    dependencies = {"research_summary": str(research_summary_path)}
    if workflow_summary_path is not None:
        dependencies["workflow_summary"] = str(workflow_summary_path)
    if memo_summary_path is not None:
        dependencies["memo_summary"] = str(memo_summary_path)

    summary_payload = {
        "output_dir": str(output_dir),
        "status": "ok",
        "warnings": warnings,
        "research_summary_path": str(research_summary_path),
        "research_csv_path": str(research_csv_path),
        "markdown_path": markdown_output,
        "html_path": html_output,
        "item_count": len(context["items"]),
        "review_queue_count": len(context["review_queue"]),
        "artifact_registry": build_artifact_registry(
            str(summary_path),
            dependencies=dependencies,
            outputs=outputs,
        ),
    }
    run_metadata = context["run_metadata"]
    if run_metadata:
        summary_payload["run_metadata"] = run_metadata

    summary_path.write_text(
        json.dumps(
            summary_payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary_path
