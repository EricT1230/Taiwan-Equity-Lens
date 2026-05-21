from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.handoff import (
    NON_ADVICE_NOTICE,
    build_handoff_quality_gate,
    requires_handoff_evidence,
    validate_handoff_evidence_url,
)
from taiwan_stock_analysis.review_action_state import (
    apply_review_action_state,
    load_review_action_state,
    review_action_rows,
)
from taiwan_stock_analysis.traceability import build_artifact_registry, read_run_metadata


def build_handoff_pack_context(
    research_summary_path: Path,
    *,
    state_path: Path | None = None,
    blocker_limit: int = 10,
) -> dict[str, Any]:
    research_summary_path = Path(research_summary_path)
    payload = _load_json(research_summary_path, "research summary")
    resolved_state_path = state_path or (research_summary_path.parent / "review_action_state.json")
    state, state_warning = load_review_action_state(resolved_state_path)
    evidence_base_dir = research_summary_path.parent
    gate = build_handoff_quality_gate(
        payload,
        state,
        blocker_limit=blocker_limit,
        evidence_base_dir=evidence_base_dir,
    )
    queue = payload.get("review_action_queue", [])
    overlaid_queue = apply_review_action_state(queue if isinstance(queue, list) else [], state)
    rows = review_action_rows(overlaid_queue)
    evidence_rows = [
        _evidence_row(row, evidence_base_dir)
        for row in rows
        if requires_handoff_evidence(row.get("action_id")) and row.get("status") != "open"
    ]
    open_rows = [row for row in rows if row.get("status") == "open"]
    warnings = [state_warning] if state_warning else []
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "research_summary_path": str(research_summary_path),
        "state_path": str(resolved_state_path),
        "gate": gate,
        "open_rows": open_rows,
        "evidence_rows": evidence_rows,
        "warnings": warnings,
        "run_metadata": read_run_metadata(payload),
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def render_handoff_pack_markdown(context: dict[str, Any]) -> str:
    gate = _dict(context.get("gate"))
    lines = [
        "# Handoff Evidence Pack",
        "",
        "## Gate Summary",
        f"- Status: {_md(gate.get('status'))}",
        f"- Ready: {_md(gate.get('ready'))}",
        f"- Open review actions: {_md(gate.get('open_count', 0))}",
        f"- Evidence-required gaps: {_md(gate.get('evidence_missing_count', 0))}",
        f"- Invalid evidence refs: {_md(gate.get('invalid_evidence_count', 0))}",
        f"- Stale state entries: {_md(gate.get('stale_state_count', 0))}",
        f"- Missing gate actions: {_md(gate.get('missing_gate_action_count', 0))}",
        f"- Next step: {_md(gate.get('next_step'))}",
        "",
        "## Top Blockers",
        "| Stock | Priority | Expert | Kind | Action | Message | Next step |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    blockers = gate.get("top_blockers", [])
    if isinstance(blockers, list) and blockers:
        for blocker in blockers:
            if not isinstance(blocker, dict):
                continue
            lines.append(
                " | ".join(
                    [
                        _md(blocker.get("stock_id")),
                        _md(blocker.get("priority")),
                        _md(blocker.get("expert_label")),
                        _md(blocker.get("kind")),
                        _md(blocker.get("action_id")),
                        _md(blocker.get("message")),
                        _md(blocker.get("next_step")),
                    ]
                )
            )
    else:
        lines.append("- | - | - | - | - | - | -")

    lines.extend(
        [
            "",
            "## Evidence Ledger",
            "| Stock | Action | Status | Reviewer | Updated | Evidence | Evidence status | Note |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    evidence_rows = context.get("evidence_rows", [])
    if isinstance(evidence_rows, list) and evidence_rows:
        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            lines.append(
                " | ".join(
                    [
                        _md(row.get("stock_id")),
                        _md(row.get("action_id")),
                        _md(row.get("status")),
                        _md(row.get("reviewer")),
                        _md(row.get("updated_at")),
                        _md(row.get("evidence_url")),
                        _md(row.get("evidence_status")),
                        _md(row.get("note")),
                    ]
                )
            )
    else:
        lines.append("- | - | - | - | - | - | - | -")

    lines.extend(
        [
            "",
            "## Source Files",
            f"- Research summary: {_md(context.get('research_summary_path'))}",
            f"- Review action state: {_md(context.get('state_path'))}",
            "",
            "## Notice",
            _md(context.get("non_advice_notice")),
            "",
        ]
    )
    return "\n".join(lines)


def render_handoff_pack_html(context: dict[str, Any]) -> str:
    gate = _dict(context.get("gate"))
    blockers = gate.get("top_blockers", [])
    evidence_rows = context.get("evidence_rows", [])
    blocker_rows = _html_rows(
        blockers if isinstance(blockers, list) else [],
        ["stock_id", "priority", "expert_label", "kind", "action_id", "message", "next_step"],
        7,
    )
    evidence_html_rows = _html_rows(
        evidence_rows if isinstance(evidence_rows, list) else [],
        ["stock_id", "action_id", "status", "reviewer", "updated_at", "evidence_url", "evidence_status", "note"],
        8,
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Handoff Evidence Pack</title>
</head>
<body>
  <main>
    <h1>Handoff Evidence Pack</h1>
    <section>
      <h2>Gate Summary</h2>
      <ul>
        <li><strong>Status:</strong> {escape(_text(gate.get("status")))}</li>
        <li><strong>Ready:</strong> {escape(_text(gate.get("ready")))}</li>
        <li><strong>Open review actions:</strong> {escape(_text(gate.get("open_count", 0)))}</li>
        <li><strong>Evidence-required gaps:</strong> {escape(_text(gate.get("evidence_missing_count", 0)))}</li>
        <li><strong>Invalid evidence refs:</strong> {escape(_text(gate.get("invalid_evidence_count", 0)))}</li>
        <li><strong>Stale state entries:</strong> {escape(_text(gate.get("stale_state_count", 0)))}</li>
        <li><strong>Missing gate actions:</strong> {escape(_text(gate.get("missing_gate_action_count", 0)))}</li>
        <li><strong>Next step:</strong> {escape(_text(gate.get("next_step")))}</li>
      </ul>
    </section>
    <section>
      <h2>Top Blockers</h2>
      <table>
        <thead><tr><th>Stock</th><th>Priority</th><th>Expert</th><th>Kind</th><th>Action</th><th>Message</th><th>Next step</th></tr></thead>
        <tbody>{blocker_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Evidence Ledger</h2>
      <table>
        <thead><tr><th>Stock</th><th>Action</th><th>Status</th><th>Reviewer</th><th>Updated</th><th>Evidence</th><th>Evidence status</th><th>Note</th></tr></thead>
        <tbody>{evidence_html_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Source Files</h2>
      <ul>
        <li><strong>Research summary:</strong> {escape(_text(context.get("research_summary_path")))}</li>
        <li><strong>Review action state:</strong> {escape(_text(context.get("state_path")))}</li>
      </ul>
    </section>
    <p>{escape(_text(context.get("non_advice_notice")))}</p>
  </main>
</body>
</html>
"""


def write_handoff_evidence_pack(
    research_summary_path: Path,
    output_dir: Path,
    *,
    state_path: Path | None = None,
    output_format: str = "both",
    blocker_limit: int = 10,
) -> Path:
    context = build_handoff_pack_context(
        research_summary_path,
        state_path=state_path,
        blocker_limit=blocker_limit,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_format = output_format.lower()
    if normalized_format not in {"both", "markdown", "html"}:
        raise ValueError("output_format must be 'both', 'markdown', or 'html'")

    markdown_path = output_dir / "handoff-pack.md"
    html_path = output_dir / "handoff-pack.html"
    if normalized_format in {"both", "markdown"}:
        markdown_path.write_text(render_handoff_pack_markdown(context), encoding="utf-8")
    if normalized_format in {"both", "html"}:
        html_path.write_text(render_handoff_pack_html(context), encoding="utf-8")

    outputs = {}
    if normalized_format in {"both", "markdown"}:
        outputs["markdown"] = str(markdown_path)
    if normalized_format in {"both", "html"}:
        outputs["html"] = str(html_path)

    summary_path = output_dir / "handoff_pack_summary.json"
    gate = _dict(context.get("gate"))
    summary_payload: dict[str, Any] = {
        "output_dir": str(output_dir),
        "status": "ok",
        "gate_status": gate.get("status", "blocked"),
        "ready": bool(gate.get("ready")),
        "warnings": context.get("warnings", []),
        "research_summary_path": str(research_summary_path),
        "state_path": context.get("state_path", ""),
        "markdown_path": outputs.get("markdown", ""),
        "html_path": outputs.get("html", ""),
        "open_count": gate.get("open_count", 0),
        "evidence_missing_count": gate.get("evidence_missing_count", 0),
        "invalid_evidence_count": gate.get("invalid_evidence_count", 0),
        "blocker_count": gate.get("blocker_count", 0),
        "evidence_row_count": len(context.get("evidence_rows", [])),
        "artifact_registry": build_artifact_registry(
            str(summary_path),
            dependencies={
                "research_summary": str(research_summary_path),
                "review_action_state": str(context.get("state_path", "")),
            },
            outputs=outputs,
        ),
    }
    run_metadata = context.get("run_metadata")
    if run_metadata:
        summary_payload["run_metadata"] = run_metadata

    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def _evidence_row(row: dict[str, str], base_dir: Path) -> dict[str, str]:
    output = dict(row)
    missing_fields = [
        field
        for field in ("note", "reviewer", "evidence_url", "updated_at")
        if not _text(row.get(field), "").strip()
    ]
    if missing_fields:
        output["evidence_status"] = "missing: " + ", ".join(missing_fields)
        return output
    ok, reason = validate_handoff_evidence_url(row.get("evidence_url"), base_dir)
    output["evidence_status"] = "ok" if ok else f"invalid: {reason}"
    return output


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid {label} JSON")
    return payload


def _html_rows(rows: list[Any], keys: list[str], colspan: int) -> str:
    html_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        html_rows.append("<tr>" + "".join(f"<td>{escape(_text(row.get(key)))}</td>" for key in keys) + "</tr>")
    return "".join(html_rows) or f'<tr><td colspan="{colspan}">-</td></tr>'


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _md(value: Any) -> str:
    return (
        _text(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
    )
