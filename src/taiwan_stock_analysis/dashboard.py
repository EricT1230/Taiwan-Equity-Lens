from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.review_action_state import (
    ACTION_STATUSES,
    load_review_action_state,
)
from taiwan_stock_analysis.dashboard_ui.labels import (
    REVIEW_ACTION_CATEGORY_LABELS,
    REVIEW_ACTION_PRIORITIES,
    REVIEW_ACTION_PRIORITY_LABELS,
    REVIEW_ACTION_SEVERITIES,
    REVIEW_ACTION_SEVERITY_LABELS,
    REVIEW_ACTION_STATUS_LABELS,
)
from taiwan_stock_analysis.dashboard_ui.page import render as _render_dashboard_page


DashboardItems = dict[str, list[dict[str, Any]]]
# REVIEW_ACTION_SEVERITIES/PRIORITIES/SEVERITY_LABELS/CATEGORY_LABELS/PRIORITY_LABELS/
# STATUS_LABELS are re-exported from dashboard_ui.labels (Task 8's leaf module) rather
# than redefined here, so both this module and dashboard_ui.views share one source of
# truth. dashboard_ui.labels has zero internal imports, so dashboard -> labels and
# dashboard -> page -> workbench -> labels both stay acyclic.
REVIEW_ACTION_CATEGORIES = (
    "source_audit",
    "workflow",
    "reliability",
    "valuation",
    "research_quality",
    "fundamental_review",
)
REVIEW_ACTION_STATUSES = ACTION_STATUSES
EXPERT_AGENT_LABELS = {
    "source_audit": "\u8cc7\u6599\u4f86\u6e90\u5c08\u5bb6",
    "workflow": "\u5de5\u4f5c\u6d41\u5065\u5eb7\u5c08\u5bb6",
    "reliability": "\u8cc7\u6599\u53ef\u4fe1\u5ea6\u5c08\u5bb6",
    "valuation": "\u4f30\u503c\u5047\u8a2d\u5c08\u5bb6",
    "research_quality": "\u7814\u7a76\u5b8c\u6574\u6027\u5c08\u5bb6",
    "fundamental_review": "\u57fa\u672c\u9762\u5c08\u5bb6\u5be9\u67e5",
}


def discover_dashboard_items(search_dirs: list[Path]) -> DashboardItems:
    items: DashboardItems = {
        "reports": [],
        "comparisons": [],
        "batch_summaries": [],
        "workflow_summaries": [],
        "research_summaries": [],
        "memo_outputs": [],
        "pack_outputs": [],
        "handoff_pack_outputs": [],
        "industry_trend_reports": [],
        "market_intelligence_reports": [],
        "market_data_reports": [],
    }
    for directory in search_dirs:
        if not directory.exists():
            continue

        for html_path in sorted(directory.glob("*_analysis.html")):
            stock_id = html_path.name.removesuffix("_analysis.html")
            json_path = html_path.with_name(f"{stock_id}_raw_data.json")
            items["reports"].append(
                {
                    "stock_id": stock_id,
                    "html_path": str(html_path),
                    "json_path": str(json_path) if json_path.exists() else "",
                }
            )

        comparison_html = directory / "comparison.html"
        comparison_json = directory / "comparison.json"
        if comparison_html.exists():
            items["comparisons"].append(
                {
                    "html_path": str(comparison_html),
                    "json_path": str(comparison_json) if comparison_json.exists() else "",
                }
            )

        batch_summary = directory / "batch_summary.json"
        if batch_summary.exists():
            try:
                payload = json.loads(batch_summary.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"results": [{"stock_id": "-", "status": "error", "error": "invalid JSON"}]}
            items["batch_summaries"].append({"path": str(batch_summary), "results": payload.get("results", [])})

        workflow_summary = directory / "workflow_summary.json"
        if workflow_summary.exists():
            try:
                payload = json.loads(workflow_summary.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"error": "invalid JSON"}
            if not isinstance(payload, dict):
                payload = {"error": "invalid JSON"}
            payload["path"] = str(workflow_summary)
            items["workflow_summaries"].append(payload)

        research_summary = directory / "research_summary.json"
        if research_summary.exists():
            try:
                payload = json.loads(research_summary.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"error": "invalid JSON"}
            if not isinstance(payload, dict):
                payload = {"error": "invalid JSON"}
            payload["path"] = str(research_summary)
            if not payload.get("error"):
                payload["base_dir"] = str(directory)
            state_path = directory / "review_action_state.json"
            if state_path.exists():
                state, warning = load_review_action_state(state_path)
                payload["review_action_state"] = state
                payload["review_action_state_path"] = str(state_path)
                if warning:
                    payload["review_action_state_warning"] = warning
            items["research_summaries"].append(payload)

        _discover_memo_outputs(directory, items)
        memos_dir = directory / "memos"
        if memos_dir.exists():
            _discover_memo_outputs(memos_dir, items)
        _discover_pack_outputs(directory, items)
        _discover_handoff_pack_outputs(directory, items)
        packs_dir = directory / "packs"
        if packs_dir.exists():
            _discover_pack_outputs(packs_dir, items)
        handoff_pack_dir = directory / "handoff-pack"
        if handoff_pack_dir.exists():
            _discover_handoff_pack_outputs(handoff_pack_dir, items)
        _discover_industry_trend_reports(directory, items)
        industry_trends_dir = directory / "industry-trends"
        if industry_trends_dir.exists():
            _discover_industry_trend_reports(industry_trends_dir, items)
        _discover_market_intelligence_reports(directory, items)
        market_intelligence_dir = directory / "market-intelligence"
        if market_intelligence_dir.exists():
            _discover_market_intelligence_reports(market_intelligence_dir, items)
        _discover_market_data_reports(directory, items)
        market_data_dir = directory / "market-data"
        if market_data_dir.exists():
            _discover_market_data_reports(market_data_dir, items)
    return items


def _discover_memo_outputs(directory: Path, items: DashboardItems) -> None:
    memo_summary = directory / "memo_summary.json"
    memo_summary_path = str(memo_summary) if memo_summary.exists() else ""
    memo_paths: dict[str, dict[str, Any]] = {}
    for markdown_path in sorted(directory.glob("*_memo.md")):
        stock_id = markdown_path.name.removesuffix("_memo.md")
        memo_paths.setdefault(stock_id, {"stock_id": stock_id})["markdown_path"] = str(markdown_path)
    for html_path in sorted(directory.glob("*_memo.html")):
        stock_id = html_path.name.removesuffix("_memo.html")
        memo_paths.setdefault(stock_id, {"stock_id": stock_id})["html_path"] = str(html_path)

    if memo_paths:
        for stock_id in sorted(memo_paths):
            output = memo_paths[stock_id]
            output.setdefault("markdown_path", "")
            output.setdefault("html_path", "")
            output["summary_path"] = memo_summary_path
            items["memo_outputs"].append(output)
    elif memo_summary_path:
        items["memo_outputs"].append(
            {"stock_id": "-", "markdown_path": "", "html_path": "", "summary_path": memo_summary_path}
        )


def _discover_pack_outputs(directory: Path, items: DashboardItems) -> None:
    markdown_path = directory / "research-pack.md"
    html_path = directory / "research-pack.html"
    summary_path = directory / "pack_summary.json"
    if not any(path.exists() for path in [markdown_path, html_path, summary_path]):
        return
    items["pack_outputs"].append(
        {
            "markdown_path": str(markdown_path) if markdown_path.exists() else "",
            "html_path": str(html_path) if html_path.exists() else "",
            "summary_path": str(summary_path) if summary_path.exists() else "",
        }
    )


def _discover_handoff_pack_outputs(directory: Path, items: DashboardItems) -> None:
    markdown_path = directory / "handoff-pack.md"
    html_path = directory / "handoff-pack.html"
    summary_path = directory / "handoff_pack_summary.json"
    if not any(path.exists() for path in [markdown_path, html_path, summary_path]):
        return
    payload: dict[str, Any] = {}
    if summary_path.exists():
        try:
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {"status": "invalid JSON"}
        payload = loaded if isinstance(loaded, dict) else {"status": "invalid JSON"}
    items["handoff_pack_outputs"].append(
        {
            "markdown_path": str(markdown_path) if markdown_path.exists() else "",
            "html_path": str(html_path) if html_path.exists() else "",
            "summary_path": str(summary_path) if summary_path.exists() else "",
            "gate_status": str(payload.get("gate_status") or payload.get("status") or "-"),
            "ready": str(payload.get("ready") if "ready" in payload else "-"),
            "blocker_count": str(payload.get("blocker_count", "-")),
            "evidence_missing_count": str(payload.get("evidence_missing_count", "-")),
            "invalid_evidence_count": str(payload.get("invalid_evidence_count", "-")),
        }
    )


def _discover_industry_trend_reports(directory: Path, items: DashboardItems) -> None:
    summary_path = directory / "industry_trend_report.json"
    if not summary_path.exists():
        return
    existing_paths = {
        str(report.get("path") or "")
        for report in items.get("industry_trend_reports", [])
        if isinstance(report, dict)
    }
    if str(summary_path) in existing_paths:
        return
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"error": "invalid JSON"}
    if not isinstance(payload, dict):
        payload = {"error": "invalid JSON"}
    payload["path"] = str(summary_path)
    markdown_path = directory / "industry_trend_report.md"
    html_path = directory / "industry_trend_report.html"
    payload["markdown_path"] = str(markdown_path) if markdown_path.exists() else ""
    payload["html_path"] = str(html_path) if html_path.exists() else ""
    items["industry_trend_reports"].append(payload)


def _discover_market_intelligence_reports(directory: Path, items: DashboardItems) -> None:
    summary_path = directory / "market_intelligence_report.json"
    if not summary_path.exists():
        return
    existing_paths = {
        str(report.get("path") or "")
        for report in items.get("market_intelligence_reports", [])
        if isinstance(report, dict)
    }
    if str(summary_path) in existing_paths:
        return
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"error": "invalid JSON"}
    if not isinstance(payload, dict):
        payload = {"error": "invalid JSON"}
    payload["path"] = str(summary_path)
    markdown_path = directory / "market_intelligence_report.md"
    html_path = directory / "market_intelligence_report.html"
    payload["markdown_path"] = str(markdown_path) if markdown_path.exists() else ""
    payload["html_path"] = str(html_path) if html_path.exists() else ""
    items["market_intelligence_reports"].append(payload)


def _discover_market_data_reports(directory: Path, items: DashboardItems) -> None:
    report_path = directory / "market_data_report.json"
    if not report_path.exists():
        return
    existing = {
        str(report.get("path") or "")
        for report in items.get("market_data_reports", [])
        if isinstance(report, dict)
    }
    if str(report_path) in existing:
        return
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {"error": "invalid JSON"}
    if not isinstance(payload, dict):
        payload = {"error": "invalid JSON"}
    payload["path"] = str(report_path)
    markdown_path = directory / "market_data_report.md"
    payload["markdown_path"] = str(markdown_path) if markdown_path.exists() else ""
    items["market_data_reports"].append(payload)


def render_dashboard_html(items: DashboardItems, *, action_api_enabled: bool = False) -> str:
    return _render_dashboard_page(items, action_api_enabled=action_api_enabled)


def write_dashboard_index(search_dirs: list[Path], output_path: Path, *, action_api_enabled: bool = False) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    items = discover_dashboard_items(search_dirs)
    _make_links_relative(items, output_path.parent)
    output_path.write_text(render_dashboard_html(items, action_api_enabled=action_api_enabled), encoding="utf-8")
    return output_path


def _make_links_relative(items: DashboardItems, base_dir: Path) -> None:
    for report in items.get("reports", []):
        _relativize_fields(report, ["html_path", "json_path"], base_dir)
    for comparison in items.get("comparisons", []):
        _relativize_fields(comparison, ["html_path", "json_path"], base_dir)
    for summary in items.get("batch_summaries", []):
        _relativize_fields(summary, ["path"], base_dir)
    for summary in items.get("workflow_summaries", []):
        _relativize_fields(summary, ["path"], base_dir)
        paths = summary.get("paths", {})
        if isinstance(paths, dict):
            _relativize_fields(paths, ["batch_summary", "valuation_csv", "valuation_batch_summary", "dashboard"], base_dir)
            comparison = paths.get("comparison", {})
            if isinstance(comparison, dict):
                _relativize_fields(comparison, ["html", "json"], base_dir)
    for summary in items.get("research_summaries", []):
        _relativize_fields(summary, ["path", "review_action_state_path"], base_dir)
    for output in items.get("memo_outputs", []):
        _relativize_fields(output, ["markdown_path", "html_path", "summary_path"], base_dir)
    for output in items.get("pack_outputs", []):
        _relativize_fields(output, ["markdown_path", "html_path", "summary_path"], base_dir)
    for output in items.get("handoff_pack_outputs", []):
        _relativize_fields(output, ["markdown_path", "html_path", "summary_path"], base_dir)
    for report in items.get("industry_trend_reports", []):
        _relativize_fields(report, ["path", "markdown_path", "html_path"], base_dir)
    for report in items.get("market_intelligence_reports", []):
        _relativize_fields(report, ["path", "markdown_path", "html_path"], base_dir)
    for report in items.get("market_data_reports", []):
        _relativize_fields(report, ["path", "markdown_path"], base_dir)


def _relativize_fields(target: dict[str, Any], fields: list[str], base_dir: Path) -> None:
    for field in fields:
        value = target.get(field)
        if not isinstance(value, str) or not value:
            continue
        target[field] = os.path.relpath(Path(value).resolve(), base_dir.resolve()).replace(os.sep, "/")
