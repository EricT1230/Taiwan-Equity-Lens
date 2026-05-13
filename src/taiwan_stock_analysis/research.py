from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.traceability import build_artifact_registry, read_run_metadata


RESEARCH_COLUMNS = ["stock_id", "company_name", "category", "priority", "research_state", "notes"]
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_STATES = {"new", "watching", "review", "done", "blocked"}


def load_research_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "stock_id" not in fieldnames:
            raise ValueError("research CSV must include a stock_id column")

        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=2):
            stock_id = (row.get("stock_id") or "").strip()
            if not stock_id:
                raise ValueError(f"research CSV row {index} must include a stock_id")

            priority = _normalized_choice(row, "priority", "medium")
            if priority not in ALLOWED_PRIORITIES:
                allowed = ", ".join(sorted(ALLOWED_PRIORITIES))
                raise ValueError(
                    f"research CSV row {index} has invalid priority '{priority}'. Allowed: {allowed}"
                )

            research_state = _normalized_choice(row, "research_state", "new")
            if research_state not in ALLOWED_STATES:
                allowed = ", ".join(sorted(ALLOWED_STATES))
                raise ValueError(
                    f"research CSV row {index} has invalid research_state '{research_state}'. Allowed: {allowed}"
                )

            rows.append(
                {
                    "stock_id": stock_id,
                    "company_name": (row.get("company_name") or "").strip(),
                    "category": (row.get("category") or "").strip(),
                    "priority": priority,
                    "research_state": research_state,
                    "notes": (row.get("notes") or "").strip(),
                }
            )
        return rows


def write_research_template(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "stock_id": "2330",
                "company_name": "TSMC",
                "category": "Semiconductor",
                "priority": "high",
                "research_state": "review",
                "notes": "Add valuation assumptions before final review",
            }
        )
        writer.writerow(
            {
                "stock_id": "2303",
                "company_name": "UMC",
                "category": "Semiconductor",
                "priority": "medium",
                "research_state": "watching",
                "notes": "Track workflow warnings",
            }
        )
    return path


def write_watchlist_from_research(research_path: Path, output_path: Path) -> Path:
    rows = load_research_rows(research_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["stock_id", "company_name"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"stock_id": row["stock_id"], "company_name": row["company_name"]})
    return output_path


def build_research_summary(research_path: Path, workflow_dir: Path | None = None) -> dict[str, Any]:
    rows = load_research_rows(research_path)
    workflow_summary_path = (workflow_dir / "workflow_summary.json") if workflow_dir is not None else None
    workflow_payload = _load_workflow_summary(workflow_summary_path)
    successful_stock_ids = {
        str(stock_id)
        for stock_id in workflow_payload.get("successful_stock_ids", [])
    } if workflow_payload else set()
    failures = _workflow_failures_by_stock(workflow_payload)
    reliability_status = _aggregate_reliability_status(workflow_payload)

    items: list[dict[str, Any]] = []
    for row in rows:
        stock_id = row["stock_id"]
        workflow_status = _stock_workflow_status(
            stock_id=stock_id,
            successful_stock_ids=successful_stock_ids,
            failures=failures,
            workflow_payload=workflow_payload,
        )
        attention_reasons = _attention_reasons(
            row=row,
            workflow_status=workflow_status,
            failures=failures.get(stock_id, []),
            reliability_status=reliability_status,
            workflow_payload=workflow_payload,
        )
        items.append(
            {
                **row,
                "workflow_status": workflow_status,
                "reliability_status": reliability_status,
                "attention_reasons": attention_reasons,
            }
        )

    summary = {
        "research_path": str(research_path),
        "workflow_summary_path": str(workflow_summary_path) if workflow_summary_path is not None else "",
        "counts": {
            "total": len(items),
            "by_state": dict(Counter(item["research_state"] for item in items)),
            "by_priority": dict(Counter(item["priority"] for item in items)),
            "needs_attention": sum(1 for item in items if item["attention_reasons"]),
        },
        "items": items,
        "workflow_paths": workflow_payload.get("paths", {}) if workflow_payload else {},
    }
    run_metadata = read_run_metadata(workflow_payload)
    if run_metadata:
        summary["run_metadata"] = run_metadata
    return summary


def write_research_summary(research_path: Path, workflow_dir: Path | None, output_path: Path) -> Path:
    summary = build_research_summary(research_path, workflow_dir=workflow_dir)
    workflow_summary_path = (workflow_dir / "workflow_summary.json") if workflow_dir is not None else None
    dependencies = {}
    if workflow_summary_path is not None:
        dependencies["workflow_summary"] = str(workflow_summary_path)
    summary["artifact_registry"] = build_artifact_registry(
        str(output_path),
        dependencies=dependencies,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _normalized_choice(row: dict[str, str], field: str, default: str) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        return default
    return value.lower()


def _load_workflow_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _workflow_failures_by_stock(workflow_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    failures: dict[str, list[dict[str, Any]]] = {}
    raw_failures = workflow_payload.get("stock_failures", []) if workflow_payload else []
    if not isinstance(raw_failures, list):
        return failures
    for failure in raw_failures:
        if not isinstance(failure, dict):
            continue
        stock_id = str(failure.get("stock_id") or "").strip()
        if not stock_id:
            continue
        failures.setdefault(stock_id, []).append(failure)
    return failures


def _aggregate_reliability_status(workflow_payload: dict[str, Any]) -> str:
    if not workflow_payload:
        return "skipped"
    reliability = workflow_payload.get("data_reliability", {})
    if isinstance(reliability, dict):
        status = reliability.get("overall_status") or reliability.get("status")
        if status in {"ok", "warning", "error", "skipped"}:
            return str(status)
        if int(reliability.get("error", 0) or 0) > 0:
            return "error"
        if int(reliability.get("warning", 0) or 0) > 0:
            return "warning"
        if int(reliability.get("skipped", 0) or 0) > 0:
            return "skipped"
    return "ok"


def _stock_workflow_status(
    *,
    stock_id: str,
    successful_stock_ids: set[str],
    failures: dict[str, list[dict[str, Any]]],
    workflow_payload: dict[str, Any],
) -> str:
    if stock_id in failures:
        return "error"
    if not workflow_payload:
        return "skipped"
    if stock_id in successful_stock_ids:
        return "ok"
    return "warning"


def _attention_reasons(
    *,
    row: dict[str, str],
    workflow_status: str,
    failures: list[dict[str, Any]],
    reliability_status: str,
    workflow_payload: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if row["research_state"] in {"new", "review", "blocked"}:
        reasons.append("research state requires review")
    for failure in failures:
        stage = str(failure.get("stage") or "workflow").strip() or "workflow"
        reason = str(failure.get("reason") or "unknown reason").strip() or "unknown reason"
        reasons.append(f"workflow failed at {stage}: {reason}")
    if not failures and workflow_status in {"warning", "skipped"}:
        reasons.append(f"workflow status is {workflow_status}")
    if _valuation_status(workflow_payload) in {"warning", "skipped"}:
        reasons.append("valuation output is unavailable or skipped")
    if reliability_status in {"warning", "error"}:
        reasons.append(f"data reliability is {reliability_status}")
    return reasons


def _valuation_status(workflow_payload: dict[str, Any]) -> str:
    if not workflow_payload:
        return "skipped"
    step_statuses = workflow_payload.get("step_statuses", {})
    if isinstance(step_statuses, dict):
        valuation = step_statuses.get("valuation", {})
        if isinstance(valuation, dict):
            status = valuation.get("status")
            if status in {"ok", "warning", "error", "skipped"}:
                return str(status)
    paths = workflow_payload.get("paths", {})
    if isinstance(paths, dict) and paths.get("valuation_batch_summary"):
        return "ok"
    return "skipped"
