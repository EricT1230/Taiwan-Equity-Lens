from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.handoff import build_handoff_quality_gate, requires_handoff_evidence
from taiwan_stock_analysis.review_action_state import (
    ACTION_STATUSES,
    apply_review_action_state,
    build_review_action_state_report,
    load_review_action_state,
)


DashboardItems = dict[str, list[dict[str, Any]]]
REVIEW_ACTION_SEVERITIES = ("error", "stale", "unknown", "manual_review", "warning", "info")
REVIEW_ACTION_CATEGORIES = (
    "source_audit",
    "workflow",
    "reliability",
    "valuation",
    "research_quality",
    "fundamental_review",
)
REVIEW_ACTION_PRIORITIES = ("high", "medium", "low")
REVIEW_ACTION_STATUSES = ACTION_STATUSES
REVIEW_ACTION_STATUS_LABELS = {
    "open": "待處理",
    "done": "已完成",
    "deferred": "稍後處理",
    "ignored": "不處理",
}
REVIEW_ACTION_SEVERITY_LABELS = {
    "error": "錯誤",
    "stale": "資料過期",
    "unknown": "狀態不明",
    "manual_review": "需人工確認",
    "warning": "需注意",
    "info": "提醒",
}
REVIEW_ACTION_CATEGORY_LABELS = {
    "source_audit": "來源檢查",
    "workflow": "工作流程",
    "reliability": "資料可信度",
    "valuation": "估值",
    "research_quality": "研究品質",
}
REVIEW_ACTION_CATEGORY_LABELS["fundamental_review"] = "\u57fa\u672c\u9762\u5c08\u5bb6\u5be9\u67e5"
EXPERT_AGENT_LABELS = {
    "source_audit": "\u8cc7\u6599\u4f86\u6e90\u5c08\u5bb6",
    "workflow": "\u5de5\u4f5c\u6d41\u5065\u5eb7\u5c08\u5bb6",
    "reliability": "\u8cc7\u6599\u53ef\u4fe1\u5ea6\u5c08\u5bb6",
    "valuation": "\u4f30\u503c\u5047\u8a2d\u5c08\u5bb6",
    "research_quality": "\u7814\u7a76\u5b8c\u6574\u6027\u5c08\u5bb6",
    "fundamental_review": "\u57fa\u672c\u9762\u5c08\u5bb6\u5be9\u67e5",
}
REVIEW_ACTION_PRIORITY_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
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


def render_dashboard_html(items: DashboardItems, *, action_api_enabled: bool = False) -> str:
    report_count = len(items.get("reports", []))
    comparison_count = len(items.get("comparisons", []))
    batch_results = _batch_results(items)
    batch_count = len(batch_results)
    batch_error_count = sum(1 for result in batch_results if result.get("status") == "error")
    workflow_count = len(items.get("workflow_summaries", []))
    research_summaries = items.get("research_summaries", [])
    memo_outputs = items.get("memo_outputs", [])
    pack_outputs = items.get("pack_outputs", [])
    handoff_pack_outputs = items.get("handoff_pack_outputs", [])
    watchlist_template = "data:text/csv;charset=utf-8,stock_id%2Ccompany_name%0A2330%2C%E5%8F%B0%E7%A9%8D%E9%9B%BB%0A2303%2C%E8%81%AF%E9%9B%BB%0A"
    action_api_flag = "true" if action_api_enabled else "false"

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>台股基本面儀表板</title>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; background: #f5f7fb; color: #172033; }}
    header {{ background: #12355b; color: white; padding: 28px 32px; }}
    header p {{ margin: 8px 0 0; color: #dbeafe; }}
    main {{ padding: 24px 32px; max-width: 1240px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #dde5f0; border-radius: 8px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06); }}
    h1, h2, h3 {{ margin-top: 0; }}
    h1 {{ margin-bottom: 0; font-size: 28px; }}
    h2 {{ font-size: 20px; }}
    h3 {{ font-size: 16px; }}
    a {{ color: #0f5aa8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .summary div {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; background: #fbfdff; }}
    .summary strong {{ display: block; font-size: 28px; color: #12355b; }}
    .summary span {{ color: #4b5563; }}
    .status-line {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 12px; }}
    .industry-map-lead {{ margin: 0 0 12px; color: #475569; max-width: 860px; }}
    .industry-map-summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 12px 0; }}
    .industry-map-summary-item {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 12px; background: #fbfdff; }}
    .industry-map-summary-item strong {{ display: block; color: #12355b; margin-bottom: 4px; }}
    .industry-map-workflow {{ display: grid; grid-template-columns: minmax(280px, 0.95fr) minmax(340px, 1.05fr); gap: 14px; align-items: start; margin-top: 12px; }}
    .industry-map-list {{ min-width: 0; }}
    .industry-map-controls {{ display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 0 0 12px; padding: 10px; border: 1px solid #d8dee8; border-radius: 8px; background: #fbfdff; }}
    .industry-map-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 12px; }}
    .industry-map-card {{ border: 1px solid #d8dee8; border-left: 6px solid #64748b; border-radius: 8px; padding: 14px; background: #ffffff; cursor: pointer; }}
    .industry-map-card:focus-visible, .industry-map-card.is-selected {{ outline: 3px solid #93c5fd; outline-offset: 2px; }}
    .industry-map-card[data-industry-map-status="blocked"] {{ border-left-color: #dc2626; background: #fffafa; }}
    .industry-map-card[data-industry-map-status="needs-review"] {{ border-left-color: #d97706; background: #fffdf7; }}
    .industry-map-card[data-industry-map-status="ready"] {{ border-left-color: #16a34a; background: #fbfffc; }}
    .industry-map-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; }}
    .industry-map-head h3 {{ margin: 0 0 8px; }}
    .industry-status-pill {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 700; background: #eef4fb; color: #12355b; white-space: nowrap; }}
    .industry-map-card[data-industry-map-status="blocked"] .industry-status-pill {{ background: #fee2e2; color: #991b1b; }}
    .industry-map-card[data-industry-map-status="needs-review"] .industry-status-pill {{ background: #fef3c7; color: #92400e; }}
    .industry-map-card[data-industry-map-status="ready"] .industry-status-pill {{ background: #dcfce7; color: #166534; }}
    .industry-pressure {{ height: 9px; border-radius: 999px; overflow: hidden; background: #e2e8f0; margin: 10px 0; }}
    .industry-pressure span {{ display: block; height: 100%; width: 0; background: #64748b; }}
    .industry-map-card[data-industry-map-status="blocked"] .industry-pressure span {{ background: #dc2626; }}
    .industry-map-card[data-industry-map-status="needs-review"] .industry-pressure span {{ background: #d97706; }}
    .industry-map-card[data-industry-map-status="ready"] .industry-pressure span {{ background: #16a34a; }}
    .industry-map-metrics {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 10px 0; }}
    .industry-map-metrics span {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; color: #475569; background: #fbfdff; }}
    .industry-map-metrics strong {{ display: block; color: #172033; font-size: 18px; }}
    .industry-market-overlay {{ border: 1px solid #cbd5e1; border-left: 5px solid #64748b; border-radius: 8px; padding: 10px; margin: 10px 0; background: #f8fafc; }}
    .industry-market-overlay[data-market-direction="up"] {{ border-left-color: #16a34a; background: #f7fef9; }}
    .industry-market-overlay[data-market-direction="down"] {{ border-left-color: #dc2626; background: #fffafa; }}
    .industry-market-overlay[data-market-direction="mixed"] {{ border-left-color: #7c3aed; background: #fbf8ff; }}
    .industry-market-overlay[data-market-direction="flat"] {{ border-left-color: #64748b; }}
    .industry-market-overlay[data-market-direction="missing"] {{ border-left-color: #d97706; background: #fffdf7; }}
    .industry-market-head {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-bottom: 8px; }}
    .industry-market-head strong {{ color: #12355b; }}
    .industry-market-note {{ margin: 6px 0 0; color: #475569; font-size: 13px; overflow-wrap: anywhere; }}
    .industry-map-actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .industry-map-note {{ margin: 12px 0 0; padding: 10px 12px; border: 1px solid #fde68a; border-radius: 8px; background: #fffbeb; color: #92400e; }}
    .industry-map-detail-panel {{ position: sticky; top: 12px; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px; background: #f8fafc; }}
    .industry-map-detail-header {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; margin-bottom: 8px; }}
    .industry-map-detail-header h3 {{ margin: 0; }}
    .industry-map-detail-panel h4 {{ margin: 12px 0 8px; }}
    .industry-map-next-action {{ border: 1px solid #bfdbfe; border-radius: 8px; padding: 10px; background: #eff6ff; color: #12355b; }}
    .industry-map-next-action strong {{ display: block; margin-bottom: 4px; }}
    .industry-map-detail-list {{ display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }}
    .industry-map-detail-task {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 10px; background: white; }}
    .industry-map-detail-task p {{ margin: 6px 0; }}
    .industry-map-task-head {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px; }}
    .industry-map-task-head strong {{ color: #172033; }}
    .industry-evidence-board {{ display: grid; gap: 10px; margin: 10px 0 12px; }}
    .industry-evidence-row {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 10px; background: white; }}
    .industry-evidence-row[data-industry-evidence-status="missing"] {{ border-left: 5px solid #d97706; }}
    .industry-evidence-row[data-industry-evidence-status="invalid"] {{ border-left: 5px solid #dc2626; }}
    .industry-evidence-row[data-industry-evidence-status="open"] {{ border-left: 5px solid #2563eb; }}
    .industry-evidence-row[data-industry-evidence-status="ready"] {{ border-left: 5px solid #16a34a; }}
    .industry-evidence-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; margin-bottom: 6px; }}
    .industry-evidence-head strong {{ color: #172033; }}
    .industry-evidence-next {{ margin: 6px 0; color: #12355b; }}
    .industry-evidence-path {{ margin: 6px 0; color: #475569; font-size: 13px; overflow-wrap: anywhere; }}
    .expert-console-grid {{ display: grid; grid-template-columns: minmax(220px, 0.9fr) minmax(320px, 1.6fr); gap: 14px; align-items: start; }}
    .expert-console-panel {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; background: #fbfdff; }}
    .expert-console-panel h3 {{ margin-bottom: 8px; }}
    .expert-console-readiness {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 5px 11px; font-size: 13px; font-weight: 700; background: #dcfce7; color: #166534; }}
    .expert-console-readiness.blocked {{ background: #fee2e2; color: #991b1b; }}
    .expert-console-actions {{ display: grid; gap: 10px; margin: 0; padding-left: 0; list-style: none; }}
    .expert-console-action {{ padding: 12px; border: 1px solid #d8dee8; border-radius: 8px; background: white; }}
    .expert-console-action p {{ margin: 6px 0; }}
    .expert-console-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 4px; }}
    .expert-console-task-title {{ display: block; margin: 4px 0 8px; color: #172033; }}
    .expert-console-task-copy strong {{ color: #12355b; }}
    .expert-console-controls, .expert-console-toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .expert-console-feedback {{ margin: 10px 0 0; padding: 9px 11px; border: 1px solid #cbd5e1; border-radius: 8px; background: white; color: #12355b; }}
    .expert-console-result {{ margin: 8px 0 0; color: #166534; font-size: 0.9rem; }}
    .next-action-workbench {{ margin: 0 0 12px; padding: 12px; border: 1px solid #bfdbfe; border-radius: 8px; background: #eff6ff; }}
    .next-action-workbench h4 {{ margin: 0 0 6px; font-size: 15px; color: #12355b; }}
    .next-action-workbench p {{ margin: 6px 0; }}
    .next-action-workbench[data-next-action-kind="ready"] {{ border-color: #86efac; background: #f0fdf4; }}
    .next-action-workbench[data-next-action-kind="repair"] {{ border-color: #fde68a; background: #fffbeb; }}
    .next-action-primary {{ font-weight: 700; }}
    .evidence-composer {{ margin-top: 12px; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; background: white; }}
    .evidence-composer h5 {{ margin: 0 0 8px; font-size: 14px; color: #12355b; }}
    .evidence-composer-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; }}
    .evidence-composer label {{ display: flex; flex-direction: column; gap: 4px; color: #475569; font-size: 13px; }}
    .evidence-composer input, .evidence-composer textarea {{ width: 100%; min-width: 0; margin: 0; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; font: inherit; }}
    .evidence-composer textarea {{ min-height: 72px; resize: vertical; }}
    .evidence-composer-result {{ margin: 8px 0 0; color: #166534; font-size: 0.9rem; }}
    .evidence-composer-result[data-evidence-quality-status="draft"] {{ color: #991b1b; }}
    .evidence-composer-result[data-evidence-quality-status="needs_review"] {{ color: #92400e; }}
    .evidence-quality-summary {{ margin: 8px 0 0; font-weight: 700; }}
    .evidence-quality-next {{ margin: 4px 0 0; color: #475569; }}
    .evidence-quality-checks {{ display: grid; gap: 5px; margin: 8px 0 0 18px; padding: 0; }}
    .evidence-quality-checks li[data-check-status="fail"] {{ color: #991b1b; }}
    .evidence-quality-checks li[data-check-status="warn"] {{ color: #92400e; }}
    .evidence-preview {{ margin-top: 8px; border: 1px solid #d8dee8; border-radius: 8px; padding: 8px; background: #f8fafc; color: #172033; }}
    .evidence-preview strong {{ display: block; margin-bottom: 4px; }}
    .evidence-preview pre {{ max-height: 220px; overflow: auto; margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }}
    .expert-console-next {{ display: inline-flex; align-items: center; gap: 6px; padding: 8px 11px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; color: #12355b; cursor: pointer; }}
    .expert-console-next:hover {{ background: #eef4fb; }}
    .expert-console-next[data-status-value="done"], .expert-console-next[data-expert-console-bulk-status="done"] {{ background: #dcfce7; border-color: #86efac; color: #166534; }}
    .expert-console-next[data-status-value="done"]:hover, .expert-console-next[data-expert-console-bulk-status="done"]:hover {{ background: #bbf7d0; }}
    .handoff-pack-workflow {{ margin-top: 12px; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; }}
    .handoff-pack-workflow h4 {{ margin: 0 0 8px; font-size: 15px; }}
    .handoff-pack-controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    .handoff-pack-result {{ margin: 9px 0 0; padding: 9px 11px; border: 1px solid #d8dee8; border-radius: 8px; background: white; color: #12355b; }}
    .handoff-pack-result ul, .handoff-pack-guidance ul {{ margin: 6px 0 0 18px; padding: 0; }}
    .handoff-pack-guidance {{ margin-top: 8px; color: #92400e; }}
    .expert-console-non-advice {{ margin: 12px 0 0; padding: 10px 12px; border: 1px solid #fde68a; border-radius: 8px; background: #fffbeb; color: #92400e; }}
    .review-action-highlight {{ outline: 3px solid #facc15; outline-offset: -3px; }}
    .review-action-filters {{ display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 0 0 12px; padding: 10px; border: 1px solid #d8dee8; border-radius: 8px; background: #fbfdff; }}
    .review-action-bulk-tools {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0 0 12px; padding: 10px; border: 1px solid #d8dee8; border-radius: 8px; background: #fbfdff; }}
    .review-action-bulk-tools label {{ display: inline-flex; align-items: center; gap: 6px; color: #4b5563; font-size: 13px; }}
    .review-action-bulk-tools button {{ padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; color: #12355b; cursor: pointer; }}
    .review-action-bulk-tools button:hover {{ background: #eef4fb; }}
    .review-action-bulk-tools button[data-review-action-bulk-status="done"] {{ background: #dcfce7; border-color: #86efac; color: #166534; }}
    .review-action-bulk-count {{ color: #4b5563; font-size: 13px; }}
    .review-action-select-cell {{ width: 36px; text-align: center; }}
    .filter-field {{ display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #4b5563; }}
    .filter-field select, .filter-field input {{ margin: 0; min-width: 150px; }}
    .filter-count {{ color: #4b5563; font-size: 13px; padding: 8px 0; }}
    button[data-review-filter-reset] {{ padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; color: #12355b; cursor: pointer; }}
    button[data-review-filter-reset]:hover {{ background: #eef4fb; }}
    .review-action-commands {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }}
    .review-action-command {{ padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; color: #12355b; cursor: pointer; font-size: 13px; min-width: 52px; }}
    .review-action-command[data-review-action-command="done"] {{ background: #dcfce7; border-color: #86efac; color: #166534; }}
    .review-action-command[data-review-action-command="ignored"] {{ color: #991b1b; border-color: #fecaca; }}
    .review-action-command:hover {{ background: #eef4fb; }}
    .review-action-command[data-review-action-command="done"]:hover {{ background: #bbf7d0; }}
    tr[data-status="open"] .review-action-command[data-review-action-command="reopen"] {{ display: none; }}
    tr:not([data-status="open"]) .review-action-command[data-review-action-command="done"],
    tr:not([data-status="open"]) .review-action-command[data-review-action-command="deferred"],
    tr:not([data-status="open"]) .review-action-command[data-review-action-command="ignored"] {{ display: none; }}
    .review-action-status {{ display: inline-block; border-radius: 999px; padding: 3px 9px; background: #eef4fb; color: #12355b; font-size: 12px; font-weight: 600; }}
    tr[data-status="done"] .review-action-status {{ background: #dcfce7; color: #166534; }}
    tr[data-status="deferred"] .review-action-status {{ background: #fef3c7; color: #92400e; }}
    tr[data-status="ignored"] .review-action-status {{ background: #fee2e2; color: #991b1b; }}
    .review-action-command-fallback {{ margin-top: 6px; padding: 8px; font-size: 12px; white-space: pre-wrap; }}
    .review-action-detail {{ margin-top: 8px; color: #475569; font-size: 13px; }}
    .review-action-detail summary {{ cursor: pointer; color: #0f5aa8; }}
    .review-action-api-result {{ display: none; margin: 0 0 12px; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; }}
    .review-action-api-result summary {{ cursor: pointer; padding: 10px 12px; color: #12355b; font-weight: 600; }}
    .review-action-result-summary {{ padding: 0 12px 12px; color: #172033; }}
    .review-action-api-result details {{ margin: 0 12px 12px; }}
    .review-action-api-result details summary {{ padding: 6px 0; font-size: 13px; color: #475569; }}
    .review-action-api-output {{ margin: 0; padding: 12px; background: #0f172a; color: #e5e7eb; border-radius: 0 0 8px 8px; overflow-x: auto; white-space: pre-wrap; }}
    .review-action-state-meta {{ color: #64748b; font-size: 12px; margin-top: 6px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; background: #eef4fb; color: #12355b; font-size: 13px; }}
    .badge.error {{ background: #fee2e2; color: #991b1b; }}
    .badge.ok {{ background: #dcfce7; color: #166534; }}
    .workflow-tools {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
    .tool {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; background: #fbfdff; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #e8eef7; color: #172033; }}
    .empty {{ color: #64748b; }}
    input {{ padding: 8px; margin: 0 8px 8px 0; border: 1px solid #cbd5e1; border-radius: 6px; min-width: 180px; }}
    code {{ display: block; margin-top: 12px; padding: 12px; background: #0f172a; color: #e5e7eb; border-radius: 6px; overflow-x: auto; }}
    @media (max-width: 720px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      .expert-console-grid {{ grid-template-columns: 1fr; }}
      .industry-map-workflow {{ grid-template-columns: 1fr; }}
      .industry-map-detail-panel {{ position: static; }}
      .industry-map-metrics {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>台股基本面儀表板</h1>
    <p>集中檢視個股報告、批次狀態、同業比較與 workflow 產物。</p>
  </header>
  <main>
    <section class="summary" aria-label="總覽">
      <div id="summaryReports"><strong>{report_count}</strong><span>個股報告</span></div>
      <div id="summaryComparisons"><strong>{comparison_count}</strong><span>同業比較</span></div>
      <div id="summaryBatchItems"><strong>{batch_count}</strong><span>批次筆數</span></div>
      <div id="summaryBatchErrors"><strong>{batch_error_count}</strong><span>失敗筆數</span></div>
      <div id="summaryWorkflows"><strong>{workflow_count}</strong><span>工作流程摘要</span></div>
    </section>
    {_expert_agent_console_section(research_summaries, action_api_enabled=action_api_enabled)}
    {_industry_rotation_map_section(research_summaries)}
    {_research_summary_section(research_summaries)}
    {_review_actions_section(research_summaries, action_api_enabled=action_api_enabled)}
    <section>
      <h2>研究備忘錄</h2>
      <table><thead><tr><th>股票代號</th><th>Markdown</th><th>HTML</th><th>摘要</th></tr></thead><tbody>{_memo_rows(memo_outputs)}</tbody></table>
    </section>
    <section>
      <h2>研究包</h2>
      <table><thead><tr><th>Markdown</th><th>HTML</th><th>摘要</th></tr></thead><tbody>{_pack_rows(pack_outputs)}</tbody></table>
    </section>
    <section data-handoff-evidence-pack-section="true">
      <h2>Handoff Evidence Pack</h2>
      <table><thead><tr><th>Status</th><th>Ready</th><th>Blockers</th><th>Missing evidence</th><th>Invalid evidence</th><th>Markdown</th><th>HTML</th><th>Summary</th></tr></thead><tbody>{_handoff_pack_rows(handoff_pack_outputs)}</tbody></table>
    </section>
    <section>
      <h2>資料可信度</h2>
      {_workflow_reliability_summary(items.get("workflow_summaries", []))}
    </section>
    {_workflow_source_audit_section(items.get("workflow_summaries", []))}
    <section>
      <h2>Workflow 狀態</h2>
      {_workflow_status_line(items.get("workflow_summaries", []))}
      <table><thead><tr><th>Summary</th><th>Run ID</th><th>Watchlist</th><th>成功股票</th><th>估值 CSV</th><th>Dashboard</th><th>同業比較</th><th>備註</th></tr></thead><tbody>{_workflow_summary_rows(items.get("workflow_summaries", []))}</tbody></table>
    </section>
    <section>
      <h2>批次狀態</h2>
      {_batch_status_line(batch_results)}
      <table><thead><tr><th>Summary</th><th>股票代碼</th><th>狀態</th><th>錯誤</th></tr></thead><tbody>{_batch_rows(items.get("batch_summaries", []))}</tbody></table>
    </section>
    <section>
      <h2>個股報告</h2>
      <table><thead><tr><th>股票代碼</th><th>HTML</th><th>JSON</th></tr></thead><tbody>{_report_rows(items.get("reports", []))}</tbody></table>
    </section>
    <section>
      <h2>同業比較</h2>
      <table><thead><tr><th>HTML</th><th>JSON</th></tr></thead><tbody>{_comparison_rows(items.get("comparisons", []))}</tbody></table>
    </section>
    <section>
      <h2>常用指令</h2>
      <div class="workflow-tools">
        <div class="tool">
          <h3>單一個股</h3>
          <input id="stockInput" placeholder="股票代碼，例如 2330">
          <input id="nameInput" placeholder="公司名稱，例如 台積電">
          <code id="commandOutput">python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --output-dir dist</code>
        </div>
        <div class="tool">
          <h3>同業比較</h3>
          <input id="compareInput" placeholder="2330 2303 2454">
          <code id="compareCommandOutput">python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist</code>
        </div>
        <div class="tool">
          <h3>批次分析</h3>
          <input id="batchPathInput" placeholder="watchlist.csv">
          <a id="watchlistTemplate" href="{watchlist_template}" download="watchlist-template.csv">下載 watchlist CSV 範本</a>
          <code id="batchCommandOutput">python -m taiwan_stock_analysis.cli batch watchlist.csv --output-dir batch-dist</code>
        </div>
      </div>
    </section>
  </main>
  <script>
    const stockInput = document.getElementById('stockInput');
    const nameInput = document.getElementById('nameInput');
    const commandOutput = document.getElementById('commandOutput');
    const compareInput = document.getElementById('compareInput');
    const compareCommandOutput = document.getElementById('compareCommandOutput');
    const batchPathInput = document.getElementById('batchPathInput');
    const batchCommandOutput = document.getElementById('batchCommandOutput');
    const reviewActionApiEnabled = {action_api_flag};
    const reviewActionStatusLabels = {{
      open: '待處理',
      done: '已完成',
      deferred: '稍後處理',
      ignored: '不處理',
    }};
    function reviewActionStatusLabel(status) {{
      return reviewActionStatusLabels[status] || status || '-';
    }}
    function attachExpertConsoleFocus(button) {{
        button.addEventListener('click', () => {{
          const sourcePath = button.dataset.expertConsoleSourcePath || '';
          const sections = Array.from(document.querySelectorAll('[data-review-actions-section="true"]'));
          const section = sections.find((candidate) => (candidate.dataset.reviewActionsSourcePath || '') === sourcePath) || sections[0];
          if (!section) {{
            return;
          }}
          const categoryFilter = section.querySelector('[data-review-filter="category"]');
          const statusFilter = section.querySelector('[data-review-filter="status"]');
          const searchFilter = section.querySelector('[data-review-filter="search"]');
          if (categoryFilter) {{
            categoryFilter.value = button.dataset.expertConsoleFocusCategory || 'all';
          }}
          if (statusFilter) {{
            statusFilter.value = 'open';
          }}
          if (searchFilter) {{
            searchFilter.value = button.dataset.expertConsoleFocusSearch || '';
          }}
          if (section.reviewActionApplyFilters) {{
            section.reviewActionApplyFilters();
          }}
          section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          const targetStockId = button.dataset.expertConsoleStockId || '';
          const targetActionId = button.dataset.expertConsoleActionId || '';
          const visibleRows = Array.from(section.querySelectorAll('[data-review-action-row="true"]'))
            .filter((row) => row.style.display !== 'none');
          const firstVisible = visibleRows.find((row) =>
            (row.dataset.stockId || '') === targetStockId && (row.dataset.actionId || '') === targetActionId
          ) || visibleRows[0];
          if (firstVisible) {{
            firstVisible.classList.add('review-action-highlight');
            const firstAction = firstVisible.querySelector('[data-review-action-command]');
            if (firstAction) {{
              firstAction.focus();
            }}
            window.setTimeout(() => firstVisible.classList.remove('review-action-highlight'), 1600);
          }}
        }});
    }}
    function initExpertConsoleFocus() {{
      document.querySelectorAll('[data-expert-console-focus-category]').forEach((button) => {{
        attachExpertConsoleFocus(button);
      }});
    }}
    function industryMapSectionForButton(button) {{
      const sourcePath = button.dataset.reviewActionsSourcePath || '';
      const sections = Array.from(document.querySelectorAll('[data-review-actions-section="true"]'));
      return sections.find((section) => (section.dataset.reviewActionsSourcePath || '') === sourcePath) || sections[0] || null;
    }}
    function industryMapSourceForElement(element) {{
      return element.closest('[data-industry-map-source="true"]') || document.querySelector('[data-industry-map-source="true"]');
    }}
    function selectIndustryMapDetail(card, options = {{}}) {{
      const source = industryMapSourceForElement(card);
      if (!source) {{
        return;
      }}
      const panel = source.querySelector('[data-industry-map-detail-panel="true"]');
      const detailId = card.dataset.industryMapDetailId || '';
      const template = source.querySelector('[data-industry-map-detail-template="' + detailId + '"]');
      if (!panel || !template) {{
        return;
      }}
      source.querySelectorAll('[data-industry-map-card="true"]').forEach((item) => {{
        item.classList.toggle('is-selected', item === card);
      }});
      panel.innerHTML = template.innerHTML;
      panel.dataset.industryMapDetailName = card.dataset.industryName || '';
      panel.querySelectorAll('[data-expert-console-action-command="true"]').forEach((button) => {{
        attachExpertConsoleCommand(button);
      }});
      if (options.scroll) {{
        panel.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }}
    function applyIndustryMapFilters(source) {{
      const statusFilter = source.querySelector('[data-industry-map-filter="status"]');
      const evidenceFilter = source.querySelector('[data-industry-map-filter="evidence"]');
      const marketFilter = source.querySelector('[data-industry-map-filter="market"]');
      const lensFilter = source.querySelector('[data-industry-map-filter="lens"]');
      const searchFilter = source.querySelector('[data-industry-map-filter="search"]');
      const status = statusFilter ? statusFilter.value : 'all';
      const evidence = evidenceFilter ? evidenceFilter.value : 'all';
      const market = marketFilter ? marketFilter.value : 'all';
      const lens = lensFilter ? lensFilter.value : 'all';
      const search = searchFilter ? searchFilter.value.trim().toLowerCase() : '';
      const cards = Array.from(source.querySelectorAll('[data-industry-map-card="true"]'));
      let visible = 0;
      let firstVisible = null;
      cards.forEach((card) => {{
        const cardStatus = card.dataset.industryMapStatus || '';
        const cardEvidence = card.dataset.industryMapEvidenceStatus || '';
        const cardMarket = card.dataset.industryMapMarketDirection || '';
        const cardLenses = (card.dataset.industryMapLenses || '').split(/\\s+/).filter(Boolean);
        const searchText = (card.dataset.industryMapSearchText || '').toLowerCase();
        const matches = (status === 'all' || cardStatus === status)
          && (evidence === 'all' || cardEvidence === evidence)
          && (market === 'all' || cardMarket === market)
          && (lens === 'all' || cardLenses.includes(lens))
          && (!search || searchText.includes(search));
        card.hidden = !matches;
        if (matches) {{
          visible += 1;
          firstVisible = firstVisible || card;
        }}
      }});
      const count = source.querySelector('[data-industry-map-count="true"]');
      if (count) {{
        count.textContent = `顯示 ${{visible}} / ${{cards.length}} 個產業`;
      }}
      const selected = source.querySelector('[data-industry-map-card="true"].is-selected');
      if (selected && selected.hidden) {{
        selected.classList.remove('is-selected');
      }}
      const active = source.querySelector('[data-industry-map-card="true"].is-selected');
      if (!active && firstVisible) {{
        selectIndustryMapDetail(firstVisible);
      }}
      if (!firstVisible) {{
        const panel = source.querySelector('[data-industry-map-detail-panel="true"]');
        if (panel) {{
          panel.innerHTML = '<p class="empty">沒有符合條件的產業，請放寬篩選。</p>';
        }}
      }}
    }}
    function initIndustryMapWorkflowControls() {{
      document.querySelectorAll('[data-industry-map-source="true"]').forEach((source) => {{
        source.querySelectorAll('[data-industry-map-filter]').forEach((input) => {{
          const eventName = input.tagName === 'INPUT' ? 'input' : 'change';
          input.addEventListener(eventName, () => applyIndustryMapFilters(source));
        }});
        const reset = source.querySelector('[data-industry-map-filter-reset="true"]');
        if (reset) {{
          reset.addEventListener('click', () => {{
            source.querySelectorAll('[data-industry-map-filter]').forEach((input) => {{
              input.value = 'all';
            }});
            const search = source.querySelector('[data-industry-map-filter="search"]');
            if (search) {{
              search.value = '';
            }}
            applyIndustryMapFilters(source);
          }});
        }}
        source.querySelectorAll('[data-industry-map-card="true"]').forEach((card) => {{
          card.addEventListener('click', (event) => {{
            if (event.target.closest('a, button, input, select, textarea')) {{
              return;
            }}
            selectIndustryMapDetail(card, {{ scroll: true }});
          }});
          card.addEventListener('keydown', (event) => {{
            if (event.key === 'Enter' || event.key === ' ') {{
              event.preventDefault();
              selectIndustryMapDetail(card, {{ scroll: true }});
            }}
          }});
        }});
        source.querySelectorAll('[data-industry-map-detail-target]').forEach((button) => {{
          button.addEventListener('click', () => {{
            const detailId = button.dataset.industryMapDetailTarget || '';
            const card = source.querySelector('[data-industry-map-detail-id="' + detailId + '"]');
            if (card) {{
              selectIndustryMapDetail(card, {{ scroll: true }});
            }}
          }});
        }});
        const firstCard = source.querySelector('[data-industry-map-card="true"]');
        if (firstCard) {{
          selectIndustryMapDetail(firstCard);
        }}
        applyIndustryMapFilters(source);
      }});
    }}
    function focusIndustryMapReviewAction(button) {{
      const section = industryMapSectionForButton(button);
      if (!section) {{
        return;
      }}
      const filterSelector = (name) => '[data-review-' + `filter="${{name}}"]`;
      const severityFilter = section.querySelector(filterSelector('severity'));
      const categoryFilter = section.querySelector(filterSelector('category'));
      const priorityFilter = section.querySelector(filterSelector('priority'));
      const statusFilter = section.querySelector(filterSelector('status'));
      const searchFilter = section.querySelector(filterSelector('search'));
      if (severityFilter) {{
        severityFilter.value = 'all';
      }}
      if (categoryFilter) {{
        categoryFilter.value = button.dataset.industryMapFocusCategory || 'all';
      }}
      if (priorityFilter) {{
        priorityFilter.value = 'all';
      }}
      if (statusFilter) {{
        statusFilter.value = 'open';
      }}
      if (searchFilter) {{
        searchFilter.value = button.dataset.industryMapFocusStock || '';
      }}
      if (section.reviewActionApplyFilters) {{
        section.reviewActionApplyFilters();
      }}
      section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      const targetStockId = button.dataset.industryMapFocusStock || '';
      const targetActionId = button.dataset.industryMapFocusAction || '';
      const visibleRows = Array.from(section.querySelectorAll('[data-review-action-row="true"]'))
        .filter((row) => row.style.display !== 'none');
      const firstVisible = visibleRows.find((row) =>
        (!targetStockId || (row.dataset.stockId || '') === targetStockId)
        && (!targetActionId || (row.dataset.actionId || '') === targetActionId)
      ) || visibleRows[0];
      if (firstVisible) {{
        firstVisible.classList.add('review-action-highlight');
        const firstAction = firstVisible.querySelector('[data-review-action-command]');
        if (firstAction) {{
          firstAction.focus();
        }}
        window.setTimeout(() => firstVisible.classList.remove('review-action-highlight'), 1600);
      }}
    }}
    function initIndustryMapControls() {{
      initIndustryMapWorkflowControls();
      document.addEventListener('click', (event) => {{
        const button = event.target.closest('[data-industry-map-focus-stock]');
        if (!button) {{
          return;
        }}
        focusIndustryMapReviewAction(button);
      }});
    }}
    function expertConsoleForSection(section) {{
      const sourcePath = section.dataset.reviewActionsSourcePath || '';
      return Array.from(document.querySelectorAll('[data-expert-console-source-path]'))
        .find((block) => (block.dataset.expertConsoleSourcePath || '') === sourcePath);
    }}
    function reviewActionSectionForButton(button) {{
      const directSection = button.closest('[data-review-actions-section="true"]');
      if (directSection) {{
        return directSection;
      }}
      const sourcePath = button.dataset.reviewActionsSourcePath || button.dataset.expertConsoleSourcePath || '';
      const sections = Array.from(document.querySelectorAll('[data-review-actions-section="true"]'));
      return sections.find((section) => (section.dataset.reviewActionsSourcePath || '') === sourcePath) || sections[0] || null;
    }}
    function reviewActionRowForButton(button, section) {{
      const directRow = button.closest('[data-review-action-row="true"]');
      if (directRow) {{
        return directRow;
      }}
      if (!section) {{
        return null;
      }}
      const stockId = button.dataset.stockId || button.dataset.expertConsoleStockId || '';
      const actionId = button.dataset.actionId || button.dataset.expertConsoleActionId || '';
      return Array.from(section.querySelectorAll('[data-review-action-row="true"]')).find((row) =>
        (row.dataset.stockId || '') === stockId && (row.dataset.actionId || '') === actionId
      ) || null;
    }}
    function expertConsoleFeedbackForButton(button) {{
      const consoleBlock = button.closest('[data-expert-console-source-path]');
      return consoleBlock ? consoleBlock.querySelector('[data-expert-console-feedback="true"]') : null;
    }}
    function expertConsoleTaskResultForButton(button) {{
      const task = button.closest('[data-expert-console-task="true"]');
      return task ? task.querySelector('[data-expert-console-task-result="true"]') : null;
    }}
    function nextActionWorkbenchForButton(button) {{
      return button.closest('[data-next-action-workbench="true"]')
        || button.closest('[data-expert-console-source-path]')?.querySelector('[data-next-action-workbench="true"]')
        || null;
    }}
    function updateNextActionWorkbench(button, result) {{
      const workbench = nextActionWorkbenchForButton(button);
      if (!workbench) {{
        return;
      }}
      const ready = Boolean(result.ready);
      workbench.dataset.nextActionKind = ready ? 'ready' : 'blocker';
      const byStatus = result.by_status || {{}};
      const openCount = result.open_count ?? byStatus.open ?? 0;
      const blockerCount = result.blocker_count ?? 0;
      const remaining = workbench.querySelector('[data-next-action-remaining="true"]');
      if (remaining) {{
        remaining.textContent = `Gate blockers ${{blockerCount}} / 未完成 ${{openCount}} / 缺證據 ${{result.evidence_missing_count ?? 0}} / 無效證據 ${{result.invalid_evidence_count ?? 0}}`;
      }}
      const resultBox = workbench.querySelector('[data-next-action-result="true"]');
      if (resultBox) {{
        const nextStep = result.next_step ? ` 下一步：${{result.next_step}}` : '';
        resultBox.textContent = `處理結果：${{result.stock_id}} / ${{result.action_id}} 已標記為${{reviewActionStatusLabel(result.status)}}；待處理剩 ${{openCount}} 件，Gate blocker 剩 ${{blockerCount}}。${{nextStep}}`;
      }}
      const primary = workbench.querySelector('[data-next-action-primary="true"][data-expert-console-action-command="true"]');
      if (primary && ready) {{
        primary.disabled = true;
        primary.textContent = '交付門檻已通過，請產出 Evidence Pack';
      }}
    }}
    function reviewActionRows(section) {{
      return Array.from(section.querySelectorAll('[data-review-action-row="true"]'));
    }}
    function reviewActionEvidenceMissing(row) {{
      if ((row.dataset.evidenceRequired || 'false') !== 'true') {{
        return false;
      }}
      const status = row.dataset.status || 'open';
      if (status === 'open') {{
        return false;
      }}
      return !((row.dataset.note || '').trim())
        || !((row.dataset.reviewer || '').trim())
        || !((row.dataset.evidenceUrl || '').trim())
        || !((row.dataset.updatedAt || '').trim());
    }}
    function syncExpertConsole(section) {{
      const consoleBlock = expertConsoleForSection(section);
      if (!consoleBlock) {{
        return;
      }}
      const rows = reviewActionRows(section);
      const openRows = rows.filter((row) => (row.dataset.status || 'open') === 'open');
      const evidenceMissingRows = rows.filter(reviewActionEvidenceMissing);
      const evidenceMissingCount = evidenceMissingRows.length;
      const staleNode = section.querySelector('[data-review-action-stale-count="true"]');
      const staleCount = Number(staleNode ? staleNode.dataset.reviewActionStaleCountValue || '0' : '0');
      const missingGateCount = Number(consoleBlock.dataset.expertConsoleMissingGateCount || '0');
      const blocked = openRows.length > 0 || evidenceMissingCount > 0 || staleCount > 0 || missingGateCount > 0;
      consoleBlock.dataset.expertConsoleHandoffStatus = blocked ? 'blocked' : 'ready';
      consoleBlock.dataset.expertConsoleOpenCount = String(openRows.length);
      consoleBlock.dataset.expertConsoleEvidenceMissingCount = String(evidenceMissingCount);
      consoleBlock.dataset.expertConsoleStaleCount = String(staleCount);
      consoleBlock.dataset.expertConsoleMissingGateCount = String(missingGateCount);
      const readiness = consoleBlock.querySelector('[data-expert-console-readiness="true"]');
      if (readiness) {{
        readiness.classList.toggle('blocked', blocked);
        readiness.classList.toggle('ready', !blocked);
        readiness.textContent = blocked
          ? `交接狀態：尚未可交接，原因：Handoff Gate 有 ${{openRows.length + evidenceMissingCount + staleCount + missingGateCount}} 件阻塞`
          : '交接狀態：可進入人工交付審查';
      }}
      const nextStep = consoleBlock.querySelector('[data-expert-console-next-step="true"]');
      if (nextStep) {{
        if (missingGateCount > 0) {{
          nextStep.textContent = '下一步：先重新產生 research_summary.json，避免靜默遺漏 handoff gate。';
        }} else if (openRows.length > 0) {{
          nextStep.textContent = '下一步：先處理 Top 3 阻塞事項，再回到審查動作表確認剩餘事項。';
        }} else if (evidenceMissingCount > 0) {{
          nextStep.textContent = '下一步：補齊 Top 3 的 note、reviewer、evidence URL，再重新檢查 handoff gate。';
        }} else if (staleCount > 0) {{
          nextStep.textContent = '下一步：先 prune stale review-action state，再重新執行 handoff gate。';
        }} else {{
          nextStep.textContent = '下一步：打開研究摘要、memo 與 pack，進行人工閱讀與簽核。';
        }}
      }}
      const toolbar = consoleBlock.querySelector('[data-expert-console-bulk="true"]');
      if (toolbar) {{
        toolbar.style.display = openRows.length > 0 ? 'flex' : 'none';
      }}
      if (openRows.length > 0) {{
        renderExpertConsoleActions(consoleBlock, openRows.slice(0, 3));
      }} else if (evidenceMissingRows.length > 0) {{
        renderExpertConsoleActions(consoleBlock, evidenceMissingRows.slice(0, 3));
      }} else if (staleCount > 0) {{
        renderExpertConsoleSystemBlocker(consoleBlock, `review_action_state.json 有 ${{staleCount}} 筆過期狀態，請先 prune stale state。`);
      }} else if (missingGateCount > 0) {{
        renderExpertConsoleSystemBlocker(consoleBlock, `Handoff Gate 有 ${{missingGateCount}} 筆結構阻塞，請重新產生 research_summary.json。`);
      }} else {{
        renderExpertConsoleActions(consoleBlock, []);
      }}
    }}
    function renderExpertConsoleActions(consoleBlock, openRows) {{
      const existing = consoleBlock.querySelector('[data-expert-console-top-actions="true"]');
      if (!existing) {{
        return;
      }}
      if (openRows.length === 0) {{
        const empty = document.createElement('p');
        empty.className = 'empty';
        empty.dataset.expertConsoleTopActions = 'true';
        empty.textContent = '目前沒有開啟的阻塞事項；下一步是進行人工閱讀與簽核。';
        existing.replaceWith(empty);
        return;
      }}
      const list = document.createElement('ol');
      list.className = 'expert-console-actions';
      list.dataset.expertConsoleTopActions = 'true';
      openRows.forEach((row) => list.appendChild(buildExpertConsoleAction(row, consoleBlock.dataset.expertConsoleSourcePath || '')));
      existing.replaceWith(list);
    }}
    function renderExpertConsoleSystemBlocker(consoleBlock, message) {{
      const existing = consoleBlock.querySelector('[data-expert-console-top-actions="true"]');
      if (!existing) {{
        return;
      }}
      const list = document.createElement('ol');
      list.className = 'expert-console-actions';
      list.dataset.expertConsoleTopActions = 'true';
      const item = document.createElement('li');
      item.className = 'expert-console-action';
      const meta = document.createElement('div');
      meta.className = 'expert-console-meta';
      appendExpertBadge(meta, '狀態一致性專家');
      appendExpertBadge(meta, '需注意');
      item.appendChild(meta);
      const title = document.createElement('strong');
      title.textContent = 'Handoff Gate';
      item.appendChild(title);
      const detail = document.createElement('p');
      detail.textContent = message;
      item.appendChild(detail);
      list.appendChild(item);
      existing.replaceWith(list);
    }}
    function appendExpertBadge(parent, text) {{
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = text || '-';
      parent.appendChild(badge);
    }}
    function buildExpertConsoleAction(row, sourcePath) {{
      const item = document.createElement('li');
      item.className = 'expert-console-action';
      item.dataset.expertConsoleTask = 'true';
      const meta = document.createElement('div');
      meta.className = 'expert-console-meta';
      appendExpertBadge(meta, row.dataset.expertLabel || row.dataset.categoryLabel || row.dataset.category || '-');
      appendExpertBadge(meta, row.dataset.severityLabel || row.dataset.severity || '-');
      appendExpertBadge(meta, row.dataset.priorityLabel || row.dataset.priority || '-');
      if ((row.dataset.evidenceRequired || 'false') === 'true') {{
        appendExpertBadge(meta, '需要交付證據');
      }}
      item.appendChild(meta);
      const title = document.createElement('strong');
      title.className = 'expert-console-task-title';
      const companyName = row.dataset.companyName || '';
      title.textContent = companyName ? `${{row.dataset.stockId || '-'}} ${{companyName}}` : (row.dataset.stockId || '-');
      item.appendChild(title);
      const message = document.createElement('p');
      message.className = 'expert-console-task-copy';
      const messageLabel = document.createElement('strong');
      messageLabel.textContent = '問題：';
      message.appendChild(messageLabel);
      message.appendChild(document.createTextNode(row.dataset.actionMessage || ''));
      item.appendChild(message);
      const next = document.createElement('p');
      next.className = 'expert-console-task-copy';
      const nextLabel = document.createElement('strong');
      nextLabel.textContent = '建議處理：';
      next.appendChild(nextLabel);
      next.appendChild(document.createTextNode('先確認這個阻塞，處理完可直接標記完成；需要保留但不阻塞時標記稍後處理。'));
      item.appendChild(next);
      if ((row.dataset.evidenceRequired || 'false') === 'true') {{
        const evidence = document.createElement('p');
        evidence.className = 'expert-console-task-copy';
        evidence.textContent = '交付證據：標記完成、稍後處理或忽略時，需要填 note、reviewer、evidence URL。';
        item.appendChild(evidence);
      }}
      const controls = document.createElement('div');
      controls.className = 'expert-console-controls';
      controls.appendChild(buildExpertConsoleCommand(row, sourcePath, 'done', '標記完成'));
      controls.appendChild(buildExpertConsoleCommand(row, sourcePath, 'deferred', '稍後處理'));
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'expert-console-next';
      button.dataset.expertConsoleSourcePath = sourcePath;
      button.dataset.expertConsoleStockId = row.dataset.stockId || '';
      button.dataset.expertConsoleActionId = row.dataset.actionId || '';
      button.dataset.expertConsoleFocusCategory = row.dataset.category || 'all';
      button.dataset.expertConsoleFocusSearch = (row.dataset.stockId || row.dataset.companyName || '').toLowerCase();
      button.textContent = '前往這個阻塞';
      attachExpertConsoleFocus(button);
      controls.appendChild(button);
      item.appendChild(controls);
      const result = document.createElement('p');
      result.className = 'expert-console-result';
      result.dataset.expertConsoleTaskResult = 'true';
      result.textContent = '處理結果：尚未處理';
      item.appendChild(result);
      return item;
    }}
    function buildExpertConsoleCommand(row, sourcePath, status, label) {{
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'expert-console-next';
      button.dataset.expertConsoleActionCommand = 'true';
      button.dataset.expertConsoleSourcePath = sourcePath;
      button.dataset.reviewActionsSourcePath = sourcePath;
      button.dataset.statePath = row.dataset.statePath || '';
      button.dataset.stockId = row.dataset.stockId || '';
      button.dataset.actionId = row.dataset.actionId || '';
      button.dataset.statusValue = status;
      button.dataset.evidenceRequired = row.dataset.evidenceRequired || 'false';
      button.dataset.note = row.dataset.note || '';
      button.dataset.reviewer = row.dataset.reviewer || '';
      button.dataset.evidenceUrl = row.dataset.evidenceUrl || '';
      button.dataset.updatedAt = row.dataset.updatedAt || '';
      button.dataset.expertConsoleStockId = row.dataset.stockId || '';
      button.dataset.expertConsoleActionId = row.dataset.actionId || '';
      button.dataset.command = row.querySelector(`[data-status-value="${{status}}"]`)?.dataset.command || '';
      button.textContent = label;
      attachExpertConsoleCommand(button);
      return button;
    }}
    function attachExpertConsoleCommand(button) {{
      button.addEventListener('click', async () => {{
        const feedback = expertConsoleFeedbackForButton(button);
        if (reviewActionApiEnabled) {{
          await updateReviewActionState(button, feedback);
          return;
        }}
        const command = button.dataset.command || '';
        if (!command) {{
          if (feedback) {{
            feedback.textContent = '找不到可複製的處理指令，請前往審查列處理。';
          }}
          const taskResult = expertConsoleTaskResultForButton(button);
          if (taskResult) {{
            taskResult.textContent = '處理結果：找不到可複製的處理指令。';
          }}
          return;
        }}
        try {{
          await copyText(command);
          if (feedback) {{
            feedback.textContent = `已複製 ${{button.textContent}} 指令；執行後請重新整理或重新產生 dashboard。`;
          }}
          const taskResult = expertConsoleTaskResultForButton(button);
          if (taskResult) {{
            taskResult.textContent = `處理結果：已複製標記為${{reviewActionStatusLabel(button.dataset.statusValue || '')}}的指令。`;
          }}
        }} catch (error) {{
          if (feedback) {{
            feedback.textContent = '複製失敗，請前往審查列使用畫面上的指令文字。';
          }}
          const taskResult = expertConsoleTaskResultForButton(button);
          if (taskResult) {{
            taskResult.textContent = '處理結果：複製失敗。';
          }}
        }}
      }});
    }}
    function initExpertConsoleActionControls() {{
      document.querySelectorAll('[data-expert-console-action-command="true"]').forEach((button) => {{
        attachExpertConsoleCommand(button);
      }});
    }}
    function initExpertConsoleBulkControls() {{
      document.querySelectorAll('[data-expert-console-bulk-status]').forEach((button) => {{
        button.addEventListener('click', async () => {{
          const consoleBlock = button.closest('[data-expert-console-source-path]');
          if (!consoleBlock) {{
            return;
          }}
          const feedback = consoleBlock.querySelector('[data-expert-console-feedback="true"]');
          const status = button.dataset.expertConsoleBulkStatus || '';
          const actionButtons = Array.from(consoleBlock.querySelectorAll(`[data-expert-console-action-command="true"][data-status-value="${{status}}"]`));
          if (actionButtons.length === 0) {{
            if (feedback) {{
              feedback.textContent = '目前 Top 3 沒有可直接處理的審查列，請先查看 Gate 提示。';
            }}
            return;
          }}
          if (reviewActionApiEnabled) {{
            button.disabled = true;
            if (feedback) {{
              feedback.textContent = `正在處理 Top 3：${{reviewActionStatusLabel(status)}}...`;
            }}
            try {{
              let succeeded = 0;
              for (const actionButton of actionButtons) {{
                const updated = await updateReviewActionState(actionButton, feedback, {{ bulk: true }});
                if (updated) {{
                  succeeded += 1;
                }}
              }}
              if (feedback) {{
                feedback.textContent = succeeded === actionButtons.length
                  ? `Top 3 已處理 ${{succeeded}} 筆為${{reviewActionStatusLabel(status)}}。`
                  : `Top 3 僅處理 ${{succeeded}} / ${{actionButtons.length}} 筆，請查看各任務處理結果。`;
              }}
            }} finally {{
              button.disabled = false;
            }}
            return;
          }}
          const commands = actionButtons.map((actionButton) => actionButton.dataset.command || '').filter(Boolean);
          try {{
            await copyText(commands.join('\\n'));
            if (feedback) {{
              feedback.textContent = `已複製 Top 3 的 ${{commands.length}} 筆${{reviewActionStatusLabel(status)}}指令。`;
            }}
            actionButtons.forEach((actionButton) => {{
              const taskResult = expertConsoleTaskResultForButton(actionButton);
              if (taskResult) {{
                taskResult.textContent = `處理結果：已複製標記為${{reviewActionStatusLabel(status)}}的指令。`;
              }}
            }});
          }} catch (error) {{
            if (feedback) {{
              feedback.textContent = 'Top 3 指令複製失敗，請前往審查列使用各列指令。';
            }}
            actionButtons.forEach((actionButton) => {{
              const taskResult = expertConsoleTaskResultForButton(actionButton);
              if (taskResult) {{
                taskResult.textContent = '處理結果：Top 3 指令複製失敗。';
              }}
            }});
          }}
        }});
      }});
    }}
    function initReviewActionFilters() {{
      const sectionSelector = '[data-review-actions-' + 'section="true"]';
      const filterSelector = (name) => '[data-review-' + `filter="${{name}}"]`;
      document.querySelectorAll(sectionSelector).forEach((section) => {{
        const severityFilter = section.querySelector(filterSelector('severity'));
        const categoryFilter = section.querySelector(filterSelector('category'));
        const priorityFilter = section.querySelector(filterSelector('priority'));
        const statusFilter = section.querySelector(filterSelector('status'));
        const searchFilter = section.querySelector(filterSelector('search'));
        const resetButton = section.querySelector('[data-review-filter-reset="true"]');
        const countLabel = section.querySelector('[data-review-action-count="true"]');
        const tbody = section.querySelector('tbody');
        if (!severityFilter || !categoryFilter || !priorityFilter || !statusFilter || !searchFilter || !resetButton || !countLabel || !tbody) {{
          return;
        }}
        const rows = Array.from(section.querySelectorAll('[data-review-action-row="true"]'));
        const emptyRow = document.createElement('tr');
        emptyRow.setAttribute('data-review-action-empty', 'true');
        emptyRow.innerHTML = '<td colspan="8" class="empty">沒有符合目前篩選條件的審查動作。</td>';
        function selectedValue(control) {{
          return control.value || 'all';
        }}
        function applyFilters() {{
          const severity = selectedValue(severityFilter);
          const category = selectedValue(categoryFilter);
          const priority = selectedValue(priorityFilter);
          const status = selectedValue(statusFilter);
          const query = searchFilter.value.trim().toLowerCase();
          let visible = 0;
          rows.forEach((row) => {{
            const matchesSeverity = severity === 'all' || row.dataset.severity === severity;
            const matchesCategory = category === 'all' || row.dataset.category === category;
            const matchesPriority = priority === 'all' || row.dataset.priority === priority;
            const matchesStatus = status === 'all' || row.dataset.status === status;
            const matchesSearch = !query || (row.dataset.searchText || '').includes(query);
            const shouldShow = matchesSeverity && matchesCategory && matchesPriority && matchesStatus && matchesSearch;
            row.style.display = shouldShow ? '' : 'none';
            if (shouldShow) {{
              visible += 1;
            }}
          }});
          countLabel.textContent = `顯示 ${{visible}} / ${{rows.length}} 個動作`;
          if (visible === 0 && rows.length > 0) {{
            if (!emptyRow.parentElement) {{
              tbody.appendChild(emptyRow);
            }}
          }} else if (emptyRow.parentElement) {{
            emptyRow.remove();
          }}
          updateReviewActionBulkSelection(section);
        }}
        section.reviewActionApplyFilters = applyFilters;
        [severityFilter, categoryFilter, priorityFilter, statusFilter].forEach((control) => {{
          control.addEventListener('change', applyFilters);
        }});
        searchFilter.addEventListener('input', applyFilters);
        resetButton.addEventListener('click', () => {{
          severityFilter.value = 'all';
          categoryFilter.value = 'all';
          priorityFilter.value = 'all';
          statusFilter.value = 'open';
          searchFilter.value = '';
          applyFilters();
        }});
        statusFilter.value = 'open';
        applyFilters();
      }});
    }}
    function initReviewActionCommandCopy() {{
      const sectionSelector = '[data-review-actions-' + 'section="true"]';
      document.querySelectorAll(sectionSelector).forEach((section) => {{
        const copyStatus = section.querySelector('[data-review-action-copy-status="true"]');
        section.querySelectorAll('[data-command]').forEach((button) => {{
          button.addEventListener('click', async () => {{
            if (reviewActionApiEnabled) {{
              await updateReviewActionState(button, copyStatus);
              return;
            }}
            const command = button.dataset.command || '';
            if (!command) {{
              return;
            }}
            try {{
              if (navigator.clipboard && navigator.clipboard.writeText) {{
                await navigator.clipboard.writeText(command);
              }} else {{
                const textarea = document.createElement('textarea');
                textarea.value = command;
                textarea.setAttribute('readonly', 'true');
                textarea.style.position = 'fixed';
                textarea.style.left = '-9999px';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
              }}
              if (copyStatus) {{
                const label = button.dataset.reviewActionCommand || 'command';
                const row = button.closest('[data-review-action-row="true"]');
                const stockId = row ? row.dataset.stockId : '';
                copyStatus.textContent = `已複製 ${{label}} 指令${{stockId ? `：${{stockId}}` : ''}}`;
              }}
            }} catch (error) {{
              if (copyStatus) {{
                copyStatus.textContent = '複製失敗，請使用畫面上的指令文字。';
              }}
            }}
          }});
        }});
      }});
    }}
    function reviewActionVisibleRows(section) {{
      return Array.from(section.querySelectorAll('[data-review-action-row="true"]')).filter((row) => row.style.display !== 'none');
    }}
    function reviewActionSelectedRows(section) {{
      return reviewActionVisibleRows(section).filter((row) => {{
        const checkbox = row.querySelector('[data-review-action-select-row="true"]');
        return checkbox && checkbox.checked;
      }});
    }}
    function updateReviewActionBulkSelection(section) {{
      const selected = reviewActionSelectedRows(section);
      const countLabel = section.querySelector('[data-review-action-bulk-count="true"]');
      if (countLabel) {{
        countLabel.textContent = `已選取 ${{selected.length}} 筆`;
      }}
      const selectVisible = section.querySelector('[data-review-action-select-visible="true"]');
      if (selectVisible) {{
        const visibleRows = reviewActionVisibleRows(section);
        selectVisible.checked = visibleRows.length > 0 && selected.length === visibleRows.length;
        selectVisible.indeterminate = selected.length > 0 && selected.length < visibleRows.length;
      }}
    }}
    async function copyText(text) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        await navigator.clipboard.writeText(text);
        return;
      }}
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      textarea.remove();
    }}
    function initReviewActionBulkControls() {{
      document.querySelectorAll('[data-review-actions-section="true"]').forEach((section) => {{
        const copyStatus = section.querySelector('[data-review-action-copy-status="true"]');
        const selectVisible = section.querySelector('[data-review-action-select-visible="true"]');
        if (selectVisible) {{
          selectVisible.addEventListener('change', () => {{
            reviewActionVisibleRows(section).forEach((row) => {{
              const checkbox = row.querySelector('[data-review-action-select-row="true"]');
              if (checkbox) {{
                checkbox.checked = selectVisible.checked;
              }}
            }});
            updateReviewActionBulkSelection(section);
          }});
        }}
        section.querySelectorAll('[data-review-action-select-row="true"]').forEach((checkbox) => {{
          checkbox.addEventListener('change', () => updateReviewActionBulkSelection(section));
        }});
        section.querySelectorAll('[data-review-action-bulk-status]').forEach((button) => {{
          button.addEventListener('click', async () => {{
            const status = button.dataset.reviewActionBulkStatus || '';
            const selectedRows = reviewActionSelectedRows(section);
            if (selectedRows.length === 0) {{
              if (copyStatus) {{
                copyStatus.textContent = '請先勾選要批次處理的事項。';
              }}
              return;
            }}
            const actionButtons = selectedRows
              .map((row) => row.querySelector(`[data-status-value="${{status}}"]`))
              .filter(Boolean);
            if (reviewActionApiEnabled) {{
              button.disabled = true;
              if (copyStatus) {{
                copyStatus.textContent = `正在批次更新 ${{actionButtons.length}} 筆...`;
              }}
              try {{
                let succeeded = 0;
                for (const actionButton of actionButtons) {{
                  const updated = await updateReviewActionState(actionButton, copyStatus, {{ bulk: true }});
                  if (updated) {{
                    succeeded += 1;
                  }}
                  const row = actionButton.closest('[data-review-action-row="true"]');
                  const checkbox = row ? row.querySelector('[data-review-action-select-row="true"]') : null;
                  if (checkbox) {{
                    checkbox.checked = false;
                  }}
                }}
                if (copyStatus) {{
                  copyStatus.textContent = succeeded === actionButtons.length
                    ? `已批次更新 ${{succeeded}} 筆為${{reviewActionStatusLabel(status)}}。`
                    : `僅批次更新 ${{succeeded}} / ${{actionButtons.length}} 筆，請查看失敗列。`;
                }}
              }} finally {{
                button.disabled = false;
                updateReviewActionBulkSelection(section);
              }}
              return;
            }}
            const commands = actionButtons.map((actionButton) => actionButton.dataset.command || '').filter(Boolean);
            try {{
              await copyText(commands.join('\\n'));
              if (copyStatus) {{
                copyStatus.textContent = `已複製 ${{commands.length}} 筆${{reviewActionStatusLabel(status)}}指令。`;
              }}
            }} catch (error) {{
              if (copyStatus) {{
                copyStatus.textContent = '批次複製失敗，請使用各列的指令文字。';
              }}
            }}
          }});
        }});
        updateReviewActionBulkSelection(section);
      }});
    }}
    function collectReviewActionEvidence(button, row) {{
      if ((button.dataset.evidenceRequired || 'false') !== 'true') {{
        return {{}};
      }}
      const status = button.dataset.statusValue || '';
      if (status === 'open') {{
        return {{}};
      }}
      const currentNote = (button.dataset.note || (row ? row.dataset.note : '') || '').trim();
      const currentReviewer = (button.dataset.reviewer || (row ? row.dataset.reviewer : '') || '').trim();
      const currentEvidenceUrl = (button.dataset.evidenceUrl || (row ? row.dataset.evidenceUrl : '') || '').trim();
      const note = window.prompt('請輸入處理證據 note', currentNote);
      if (note === null || !note.trim()) {{
        return null;
      }}
      const reviewer = window.prompt('請輸入 reviewer', currentReviewer);
      if (reviewer === null || !reviewer.trim()) {{
        return null;
      }}
      const evidenceUrl = window.prompt('請輸入 evidence URL 或檔案路徑', currentEvidenceUrl);
      if (evidenceUrl === null || !evidenceUrl.trim()) {{
        return null;
      }}
      return {{
        note: note.trim(),
        reviewer: reviewer.trim(),
        evidence_url: evidenceUrl.trim(),
      }};
    }}
    function applyReviewActionApiResult(button, payload, result, options = {{}}) {{
      const section = reviewActionSectionForButton(button);
      const row = reviewActionRowForButton(button, section);
      if (row) {{
        row.dataset.status = result.status || payload.status;
        row.dataset.note = result.note || payload.note || '';
        row.dataset.reviewer = result.reviewer || payload.reviewer || '';
        row.dataset.evidenceUrl = result.evidence_url || payload.evidence_url || '';
        row.dataset.updatedAt = result.updated_at || result.last_updated || row.dataset.updatedAt || '';
        const statusCell = row.querySelector('[data-review-action-status-cell="true"]');
        if (statusCell) {{
          statusCell.textContent = reviewActionStatusLabel(result.status || payload.status);
        }}
        const stateMeta = row.querySelector('[data-review-action-state-meta="true"]');
        if (stateMeta) {{
          const bits = [];
          if (row.dataset.note) {{
            bits.push(`note: ${{row.dataset.note}}`);
          }}
          if (row.dataset.reviewer) {{
            bits.push(`reviewer: ${{row.dataset.reviewer}}`);
          }}
          if (row.dataset.evidenceUrl) {{
            bits.push(`evidence: ${{row.dataset.evidenceUrl}}`);
          }}
          if (row.dataset.updatedAt) {{
            bits.push(`updated: ${{row.dataset.updatedAt}}`);
          }}
          stateMeta.textContent = bits.join(' | ');
        }}
      }}
      updateReviewActionSummary(button, result);
      const taskResult = expertConsoleTaskResultForButton(button);
      if (taskResult && !options.keepTaskResult) {{
        const byStatus = result.by_status || {{}};
        const openCount = result.open_count ?? byStatus.open ?? 0;
        const blockerCount = result.blocker_count ?? '-';
        taskResult.textContent = `處理結果：已標記為${{reviewActionStatusLabel(result.status || payload.status)}}；待處理剩 ${{openCount}} 件，Gate blocker 剩 ${{blockerCount}}。`;
      }}
      updateNextActionWorkbench(button, result);
      if (!options.skipDetail) {{
        showReviewActionApiResult(button, result);
      }}
      if (section && section.reviewActionApplyFilters) {{
        section.reviewActionApplyFilters();
      }}
      if (section) {{
        syncExpertConsole(section);
      }}
      return {{ section, row }};
    }}
    async function updateReviewActionState(button, copyStatus, options = {{}}) {{
      const payload = {{
        state_path: button.dataset.statePath || '',
        stock_id: button.dataset.stockId || '',
        action_id: button.dataset.actionId || '',
        status: button.dataset.statusValue || '',
      }};
      if (!payload.state_path || !payload.stock_id || !payload.action_id || !payload.status) {{
        if (copyStatus) {{
          copyStatus.textContent = '狀態更新失敗：缺少必要資料。';
        }}
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = '處理結果：缺少必要資料，未更新。';
        }}
        return false;
      }}
      const section = reviewActionSectionForButton(button);
      const row = reviewActionRowForButton(button, section);
      const evidence = collectReviewActionEvidence(button, row);
      if (evidence === null) {{
        if (copyStatus) {{
          copyStatus.textContent = '需要 note、reviewer、evidence URL 才能更新這個交付前 blocker。';
        }}
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = '處理結果：尚未更新，缺少交付證據。';
        }}
        return false;
      }}
      Object.assign(payload, evidence);
      if (payload.status === 'ignored' && !window.confirm('確定要把這筆標記為不處理嗎？')) {{
        return false;
      }}
      button.disabled = true;
      if (copyStatus) {{
        copyStatus.textContent = '正在更新狀態...';
      }}
      try {{
        const response = await fetch('/api/review-actions/set', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const result = await response.json();
        if (!response.ok || !result.ok) {{
          throw new Error(result.error || `HTTP ${{response.status}}`);
        }}
        applyReviewActionApiResult(button, payload, result, {{ skipDetail: options.bulk }});
        if (copyStatus && !options.bulk) {{
          const backupText = result.backup_path ? `，已建立備份` : '';
          const categoryLabel = row ? row.dataset.categoryLabel || row.dataset.category || payload.action_id : payload.action_id;
          copyStatus.textContent = `已更新：${{payload.stock_id}} 的 ${{categoryLabel}}已標記為${{reviewActionStatusLabel(result.status || payload.status)}}${{backupText}}`;
        }}
        return true;
      }} catch (error) {{
        if (copyStatus) {{
          copyStatus.textContent = `狀態更新失敗：${{error.message}}`;
        }}
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = `處理結果：更新失敗，${{error.message}}`;
        }}
        return false;
      }} finally {{
        button.disabled = false;
      }}
    }}
    function updateReviewActionSummary(button, result) {{
      const section = reviewActionSectionForButton(button);
      if (!section) {{
        return;
      }}
      const byStatus = result.by_status || {{}};
      const rows = Array.from(section.querySelectorAll('[data-review-action-row="true"]'));
      const total = rows.length;
      const openTotal = section.querySelector('[data-review-action-open-total="true"]');
      if (openTotal) {{
        openTotal.textContent = `待處理 ${{byStatus.open || 0}} / 全部 ${{total}}`;
      }}
      const stateHealth = section.querySelector('[data-review-action-state-health="true"]');
      if (stateHealth) {{
        stateHealth.textContent = `已完成 ${{byStatus.done || 0}} / 稍後 ${{byStatus.deferred || 0}} / 不處理 ${{byStatus.ignored || 0}}`;
      }}
      const staleState = section.querySelector('[data-review-action-stale-count="true"]');
      if (staleState) {{
        staleState.dataset.reviewActionStaleCountValue = String(result.stale_count ?? 0);
        staleState.textContent = `過期狀態 ${{result.stale_count ?? 0}}`;
      }}
      const lastUpdated = section.querySelector('[data-review-action-last-updated="true"]');
      if (lastUpdated) {{
        lastUpdated.textContent = `最後更新：${{result.last_updated || '-'}}`;
      }}
    }}
    function showReviewActionApiResult(button, result) {{
      const section = reviewActionSectionForButton(button);
      const detail = section ? section.querySelector('[data-review-action-api-result="true"]') : null;
      const summary = detail ? detail.querySelector('[data-review-action-result-summary="true"]') : null;
      const output = detail ? detail.querySelector('[data-review-action-api-output="true"]') : null;
      if (!output) {{
        return;
      }}
      detail.style.display = 'block';
      detail.open = true;
      if (summary) {{
        const byStatus = result.by_status || {{}};
        const row = reviewActionRowForButton(button, section);
        const categoryLabel = row ? row.dataset.categoryLabel || row.dataset.category || result.action_id : result.action_id;
        summary.textContent = `已將 ${{result.stock_id}} 的 ${{categoryLabel}}標記為${{reviewActionStatusLabel(result.status)}}，待處理剩 ${{byStatus.open || 0}} 件。`;
      }}
      output.textContent = JSON.stringify(result, null, 2);
    }}
    function evidenceComposerField(composer, selector) {{
      const field = composer ? composer.querySelector(selector) : null;
      return field ? field.value.trim() : '';
    }}
    function evidenceQualityLabel(status) {{
      if (status === 'handoff_ready') {{
        return '可交付';
      }}
      if (status === 'needs_review') {{
        return '需要再審查';
      }}
      if (status === 'draft') {{
        return '草稿';
      }}
      return '未知';
    }}
    function renderEvidenceComposerResult(container, result) {{
      if (!container) {{
        return;
      }}
      const quality = result.evidence_quality || {{}};
      const preview = result.evidence_preview || {{}};
      const checks = Array.isArray(quality.checks) ? quality.checks : [];
      const status = quality.status || 'unknown';
      container.textContent = '';
      container.dataset.evidenceQualityStatus = status;

      const summary = document.createElement('p');
      summary.className = 'evidence-quality-summary';
      summary.textContent = '已建立證據：' + (result.evidence_url || '-') + '；Reviewer Confidence（審查信心）：' + evidenceQualityLabel(status) + '。';
      container.appendChild(summary);

      const nextStep = document.createElement('p');
      nextStep.className = 'evidence-quality-next';
      nextStep.textContent = quality.next_step || '請先檢查證據預覽再交付。';
      container.appendChild(nextStep);

      const checkList = document.createElement('ul');
      checkList.className = 'evidence-quality-checks';
      checkList.dataset.evidenceQualityChecks = 'true';
      checks.forEach((check) => {{
        const item = document.createElement('li');
        item.dataset.checkStatus = check.status || 'unknown';
        item.textContent = (check.label || check.id || 'check') + ': ' + (check.status || 'unknown') + ' - ' + (check.message || '');
        checkList.appendChild(item);
      }});
      container.appendChild(checkList);

      const previewBox = document.createElement('div');
      previewBox.className = 'evidence-preview';
      previewBox.dataset.evidencePreview = 'true';
      const previewTitle = document.createElement('strong');
      previewTitle.textContent = 'Evidence Preview（證據預覽）';
      previewBox.appendChild(previewTitle);
      const previewPath = document.createElement('p');
      previewPath.textContent = preview.path || result.evidence_path || result.evidence_url || '-';
      previewBox.appendChild(previewPath);
      const previewContent = document.createElement('pre');
      previewContent.dataset.evidencePreviewContent = 'true';
      previewContent.textContent = preview.excerpt || '沒有回傳證據預覽。';
      previewBox.appendChild(previewContent);
      container.appendChild(previewBox);
    }}
    async function submitEvidenceComposer(button) {{
      const composer = button.closest('[data-evidence-composer="true"]');
      const resultBox = composer ? composer.querySelector('[data-evidence-composer-result="true"]') : null;
      const payload = {{
        state_path: button.dataset.statePath || '',
        stock_id: button.dataset.stockId || '',
        action_id: button.dataset.actionId || '',
        status: button.dataset.statusValue || 'done',
        note: evidenceComposerField(composer, '[data-evidence-composer-note="true"]'),
        reviewer: evidenceComposerField(composer, '[data-evidence-composer-reviewer="true"]'),
        evidence_url: evidenceComposerField(composer, '[data-evidence-composer-url="true"]'),
        evidence_summary: evidenceComposerField(composer, '[data-evidence-composer-summary="true"]'),
        overwrite: true,
      }};
      const missing = [];
      if (!payload.note) {{
        missing.push('note');
      }}
      if (!payload.reviewer) {{
        missing.push('reviewer');
      }}
      if (!payload.evidence_url) {{
        missing.push('evidence path');
      }}
      if (!payload.evidence_summary) {{
        missing.push('evidence summary');
      }}
      if (!payload.state_path || !payload.stock_id || !payload.action_id || missing.length > 0) {{
        if (resultBox) {{
          resultBox.textContent = `缺少必要資料：${{missing.join(', ') || 'state/action'}}。`;
        }}
        return;
      }}
      button.disabled = true;
      if (resultBox) {{
        resultBox.textContent = '正在建立證據檔並更新 blocker...';
      }}
      try {{
        const response = await fetch('/api/evidence/compose-and-set', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload),
        }});
        const result = await response.json();
        if (!response.ok || !result.ok) {{
          throw new Error(result.error || `HTTP ${{response.status}}`);
        }}
        applyReviewActionApiResult(button, payload, result, {{ keepTaskResult: true }});
        const byStatus = result.by_status || {{}};
        const openCount = result.open_count ?? byStatus.open ?? 0;
        const blockerCount = result.blocker_count ?? 0;
        if (resultBox) {{
          renderEvidenceComposerResult(resultBox, result);
        }}
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = `處理結果：已建立 evidence stub 並標記為${{reviewActionStatusLabel(result.status || payload.status)}}；Reviewer Confidence ${{evidenceQualityLabel(result.reviewer_confidence_status || (result.evidence_quality || {{}}).status)}}；待處理 ${{openCount}} 件，Gate blocker ${{blockerCount}} 件。`;
        }}
      }} catch (error) {{
        if (resultBox) {{
          resultBox.textContent = `建立證據失敗：${{error.message}}`;
        }}
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = `處理結果：建立證據失敗，${{error.message}}`;
        }}
      }} finally {{
        button.disabled = false;
      }}
    }}
    function initEvidenceComposerControls() {{
      document.querySelectorAll('[data-evidence-composer-submit="true"]').forEach((button) => {{
        button.addEventListener('click', () => submitEvidenceComposer(button));
      }});
    }}
    function handoffPackResultForButton(button) {{
      const panel = button.closest('[data-handoff-pack-workflow="true"]');
      return panel ? panel.querySelector('[data-handoff-pack-result="true"]') : null;
    }}
    function renderHandoffPackResult(container, result) {{
      if (!container) {{
        return;
      }}
      container.textContent = '';
      const summary = document.createElement('p');
      const readyLabel = result.ready ? 'ready' : 'blocked';
      summary.textContent = `Evidence Pack 已產出：${{readyLabel}}，blockers ${{result.blocker_count ?? 0}}，缺證據 ${{result.evidence_missing_count ?? 0}}，無效證據 ${{result.invalid_evidence_count ?? 0}}。`;
      container.appendChild(summary);
      const list = document.createElement('ul');
      [
        ['Markdown', result.markdown_path],
        ['HTML', result.html_path],
        ['Summary JSON', result.summary_path],
      ].forEach(([label, path]) => {{
        if (!path) {{
          return;
        }}
        const item = document.createElement('li');
        item.textContent = `${{label}}: ${{path}}`;
        list.appendChild(item);
      }});
      if (list.children.length > 0) {{
        container.appendChild(list);
      }}
    }}
    async function writeHandoffPack(button) {{
      const resultBox = handoffPackResultForButton(button);
      if (reviewActionApiEnabled) {{
        const payload = {{
          research_summary_path: button.dataset.researchSummaryPath || '',
          state_path: button.dataset.statePath || '',
          output_dir: button.dataset.outputDir || '',
          format: 'both',
          blocker_limit: 10,
        }};
        if (!payload.research_summary_path || !payload.output_dir) {{
          if (resultBox) {{
            resultBox.textContent = '缺少 research summary 或 output dir，請重新產生 dashboard。';
          }}
          return;
        }}
        button.disabled = true;
        if (resultBox) {{
          resultBox.textContent = '正在產出 Handoff Evidence Pack...';
        }}
        try {{
          const response = await fetch('/api/handoff-pack/write', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload),
          }});
          const result = await response.json();
          if (!response.ok || !result.ok) {{
            throw new Error(result.error || `HTTP ${{response.status}}`);
          }}
          renderHandoffPackResult(resultBox, result);
        }} catch (error) {{
          if (resultBox) {{
            resultBox.textContent = `Evidence Pack 產出失敗：${{error.message}}`;
          }}
        }} finally {{
          button.disabled = false;
        }}
        return;
      }}
      const command = button.dataset.command || '';
      if (!command) {{
        if (resultBox) {{
          resultBox.textContent = '找不到可複製的 handoff-pack 指令。';
        }}
        return;
      }}
      try {{
        await copyText(command);
        if (resultBox) {{
          resultBox.textContent = '已複製 Evidence Pack 產出指令；在 PowerShell 執行後重新整理 dashboard。';
        }}
      }} catch (error) {{
        if (resultBox) {{
          resultBox.textContent = '指令複製失敗，請展開下方 CLI 指令手動執行。';
        }}
      }}
    }}
    function initHandoffPackControls() {{
      document.querySelectorAll('[data-handoff-pack-write="true"]').forEach((button) => {{
        button.addEventListener('click', () => writeHandoffPack(button));
      }});
    }}
    function updateCommand() {{
      const stock = stockInput.value || '2330';
      const name = nameInput.value || '台積電';
      commandOutput.textContent = `python -m taiwan_stock_analysis.cli ${{stock}} --company-name ${{name}} --output-dir dist`;
    }}
    function updateCompareCommand() {{
      const stocks = compareInput.value || '2330 2303 2454';
      compareCommandOutput.textContent = `python -m taiwan_stock_analysis.cli compare ${{stocks}} --output-dir compare-dist`;
    }}
    function updateBatchCommand() {{
      const path = batchPathInput.value || 'watchlist.csv';
      batchCommandOutput.textContent = `python -m taiwan_stock_analysis.cli batch ${{path}} --output-dir batch-dist`;
    }}
    if (stockInput && nameInput && compareInput && batchPathInput) {{
      stockInput.addEventListener('input', updateCommand);
      nameInput.addEventListener('input', updateCommand);
      compareInput.addEventListener('input', updateCompareCommand);
      batchPathInput.addEventListener('input', updateBatchCommand);
    }}
    initExpertConsoleFocus();
    initExpertConsoleActionControls();
    initExpertConsoleBulkControls();
    initEvidenceComposerControls();
    initHandoffPackControls();
    initReviewActionFilters();
    initIndustryMapControls();
    initReviewActionCommandCopy();
    initReviewActionBulkControls();
  </script>
</body>
</html>
"""


def _batch_results(items: DashboardItems) -> list[dict[str, Any]]:
    return [
        result
        for summary in items.get("batch_summaries", [])
        for result in summary.get("results", [])
        if isinstance(result, dict)
    ]


def _expert_agent_console_section(research_summaries: list[dict[str, Any]], *, action_api_enabled: bool = False) -> str:
    if not research_summaries:
        return ""

    blocks: list[str] = []
    for summary in research_summaries:
        if not isinstance(summary, dict) or summary.get("error"):
            continue
        blocks.append(_expert_console_summary_block(summary, action_api_enabled=action_api_enabled))

    if not blocks:
        return ""
    return (
        '<section data-expert-agent-console="true">'
        "<h2>\u5c08\u5bb6 Agent Console</h2>"
        f"{''.join(blocks)}"
        '<p class="expert-console-non-advice" data-expert-console-non-advice="true">'
        "\u6b64\u5100\u8868\u677f\u50c5\u5354\u52a9\u6574\u7406\u7814\u7a76\u6d41\u7a0b\u8207\u5f85\u67e5\u4e8b\u9805\uff0c"
        "\u4e0d\u69cb\u6210\u6295\u8cc7\u5efa\u8b70\u3001\u8cb7\u8ce3\u5efa\u8b70\u6216\u6301\u5009\u5efa\u8b70\u3002"
        "</p>"
        "</section>"
    )


def _expert_console_summary_block(summary: dict[str, Any], *, action_api_enabled: bool = False) -> str:
    state = _dict_value(summary.get("review_action_state"))
    gate = build_handoff_quality_gate(
        summary,
        state,
        blocker_limit=3,
        evidence_base_dir=_research_summary_base_dir(summary),
    )
    blockers = gate.get("top_blockers", [])
    top_blockers = blockers if isinstance(blockers, list) else []
    total_actions = int(gate.get("total_actions") or 0)
    ready = bool(gate.get("ready"))
    blocker_count = int(gate.get("blocker_count") or 0)
    open_count = int(gate.get("open_count") or 0)
    evidence_missing_count = int(gate.get("evidence_missing_count") or 0)
    invalid_evidence_count = int(gate.get("invalid_evidence_count") or 0)
    stale_count = int(gate.get("stale_state_count") or 0)
    missing_gate_count = int(gate.get("missing_gate_action_count") or 0)
    readiness_class = "ready" if ready else "blocked"
    readiness_text = (
        "\u4ea4\u63a5\u72c0\u614b\uff1a\u53ef\u9032\u5165\u4eba\u5de5\u4ea4\u4ed8\u5be9\u67e5"
        if ready
        else f"\u4ea4\u63a5\u72c0\u614b\uff1a\u5c1a\u672a\u53ef\u4ea4\u63a5\uff0c\u539f\u56e0\uff1aHandoff Gate \u6709 {blocker_count} \u4ef6\u963b\u585e"
    )
    source_path = str(summary.get("path") or "")
    state_path = _review_action_state_path(summary)
    source_link = _link(source_path, Path(source_path).name or "research_summary.json")
    next_step = str(gate.get("next_step") or "")
    sync_note = _expert_console_sync_note(top_blockers, action_api_enabled)
    toolbar = _expert_console_toolbar(top_blockers)
    pack_workflow = _handoff_pack_workflow(summary, gate, state_path, action_api_enabled=action_api_enabled)
    next_action_workbench = _next_action_workbench(
        summary,
        gate,
        top_blockers,
        source_path,
        state_path,
        action_api_enabled=action_api_enabled,
    )
    feedback_text = "等待處理 Top 3 阻塞事項。" if top_blockers else "目前沒有 Top 3 阻塞事項。"
    escaped_source_path = escape(source_path)
    return (
        f'<div class="expert-console-grid" data-expert-console-source-path="{escaped_source_path}"'
        f' data-expert-console-handoff-status="{escape(str(gate.get("status") or ""))}"'
        f' data-expert-console-open-count="{escape(str(open_count))}"'
        f' data-expert-console-evidence-missing-count="{escape(str(evidence_missing_count))}"'
        f' data-expert-console-invalid-evidence-count="{escape(str(invalid_evidence_count))}"'
        f' data-expert-console-stale-count="{escape(str(stale_count))}"'
        f' data-expert-console-missing-gate-count="{escape(str(missing_gate_count))}">'
        '<div class="expert-console-panel">'
        "<h3>\u7814\u7a76\u4ea4\u4ed8\u72c0\u614b</h3>"
        f"{next_action_workbench}"
        f'<p><span class="expert-console-readiness {readiness_class}" '
        f'data-expert-console-readiness="true">{escape(readiness_text)}</span></p>'
        f'<p class="status-line"><span class="badge">\u4f86\u6e90\uff1a{source_link}</span>'
        f'<span class="badge">\u5be9\u67e5\u52d5\u4f5c\uff1a{escape(str(total_actions))}</span>'
        f'<span class="badge">Gate \u963b\u585e\uff1a{escape(str(blocker_count))}</span>'
        f'<span class="badge">\u7f3a\u5c11\u8b49\u64da\uff1a{escape(str(evidence_missing_count))}</span>'
        f'<span class="badge">\u7121\u6548\u8b49\u64da\uff1a{escape(str(invalid_evidence_count))}</span></p>'
        f'<p data-expert-console-next-step="true">{escape(next_step)}</p>'
        f"{toolbar}"
        f'<p class="expert-console-feedback" data-expert-console-feedback="true">{escape(feedback_text)}</p>'
        f"{sync_note}"
        f"{pack_workflow}"
        "</div>"
        '<div class="expert-console-panel">'
        "<h3>\u512a\u5148\u8655\u7406\u7684 3 \u4ef6\u5f85\u67e5\u4e8b\u9805</h3>"
        f"{_expert_console_action_list(top_blockers, source_path, state_path)}"
        "</div>"
        "</div>"
    )


def _next_action_workbench(
    summary: dict[str, Any],
    gate: dict[str, Any],
    top_blockers: list[Any],
    source_path: str,
    state_path: str,
    *,
    action_api_enabled: bool = False,
) -> str:
    ready = bool(gate.get("ready"))
    blocker_count = int(gate.get("blocker_count") or 0)
    open_count = int(gate.get("open_count") or 0)
    evidence_missing_count = int(gate.get("evidence_missing_count") or 0)
    invalid_evidence_count = int(gate.get("invalid_evidence_count") or 0)
    next_step = str(gate.get("next_step") or "")
    primary_blocker: dict[str, Any] | None = None
    if ready:
        kind = "ready"
        title = "交付門檻已通過"
        guidance = "建議主按鈕：產出 Evidence Pack，讓人工簽核者先看同一份交付證據。"
        primary = _next_action_pack_button(summary, state_path, action_api_enabled=action_api_enabled)
    else:
        primary_blocker = _next_action_primary_blocker(top_blockers)
        if primary_blocker:
            kind = "blocker"
            stock_id = str(primary_blocker.get("stock_id") or "-")
            action_id = str(primary_blocker.get("action_id") or "-")
            title = f"{stock_id} / {action_id}"
            guidance = "建議主按鈕：先處理最高優先阻塞；完成後 Console 會顯示剩餘阻塞與下一步。"
            primary = _next_action_blocker_button(primary_blocker, source_path, state_path)
        else:
            kind = "repair"
            title = "Gate 結構需要修復"
            guidance = next_step or "先修正 research summary 或 review-action state，再重新檢查 handoff gate。"
            primary = (
                '<button type="button" class="expert-console-next next-action-primary" '
                'data-next-action-primary="true" disabled>依照修復說明處理</button>'
            )
    evidence_composer = (
        _evidence_composer(summary, primary_blocker, source_path, state_path)
        if primary_blocker
        and action_api_enabled
        and requires_handoff_evidence(str(primary_blocker.get("action_id") or ""))
        else ""
    )
    return (
        '<div class="next-action-workbench" data-next-action-workbench="true"'
        f' data-next-action-kind="{escape(kind)}" data-expert-console-task="true" data-handoff-pack-workflow="true">'
        "<h4>下一步工作台</h4>"
        f'<p><strong>{escape(title)}</strong></p>'
        f"<p>{escape(guidance)}</p>"
        '<p class="status-line" data-next-action-remaining="true">'
        f'<span class="badge">Gate blockers {escape(str(blocker_count))}</span>'
        f'<span class="badge">未完成 {escape(str(open_count))}</span>'
        f'<span class="badge">缺證據 {escape(str(evidence_missing_count))}</span>'
        f'<span class="badge">無效證據 {escape(str(invalid_evidence_count))}</span>'
        "</p>"
        '<div class="expert-console-controls">'
        f"{primary}"
        "</div>"
        f"{evidence_composer}"
        '<p class="expert-console-result" data-next-action-result="true" '
        'data-handoff-pack-result="true" data-expert-console-task-result="true">'
        "處理結果：等待按下建議主按鈕。"
        "</p>"
        "</div>"
    )


def _next_action_primary_blocker(top_blockers: list[Any]) -> dict[str, Any] | None:
    for blocker in top_blockers:
        if not isinstance(blocker, dict):
            continue
        if str(blocker.get("focus_available", "true")).lower() != "true":
            continue
        if str(blocker.get("stock_id") or "").strip() and str(blocker.get("action_id") or "").strip():
            return blocker
    return None


def _next_action_blocker_button(action: dict[str, Any], source_path: str, state_path: str) -> str:
    button = _expert_console_action_button(
        {key: str(value) for key, value in action.items()},
        source_path,
        state_path,
        "done",
        "處理最高優先阻塞",
    )
    button = button.replace('class="expert-console-next"', 'class="expert-console-next next-action-primary"', 1)
    return button.replace(
        'data-expert-console-action-command="true"',
        'data-expert-console-action-command="true" data-next-action-primary="true"',
        1,
    )


def _evidence_composer(
    summary: dict[str, Any],
    action: dict[str, Any],
    source_path: str,
    state_path: str,
) -> str:
    stock_id = str(action.get("stock_id") or "")
    action_id = str(action.get("action_id") or "")
    message = str(action.get("message") or "")
    note = str(action.get("note") or "").strip() or f"Reviewed handoff blocker: {message}"
    reviewer = str(action.get("reviewer") or "").strip() or "handoff-reviewer"
    evidence_url = str(action.get("evidence_url") or "").strip() or _suggested_evidence_path(summary, stock_id, action_id)
    evidence_summary = message or "Summarize the manual review evidence for this handoff blocker."
    return (
        '<div class="evidence-composer" data-evidence-composer="true"'
        f' data-review-actions-source-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-stock-id="{escape(stock_id)}"'
        f' data-action-id="{escape(action_id)}">'
        "<h5>交付證據 Composer</h5>"
        "<p>在 dashboard 內建立 evidence markdown，並同步把這個 blocker 標記完成；內容僅供研究交付，不構成投資建議。</p>"
        '<div class="evidence-composer-grid">'
        '<label>note'
        f'<textarea data-evidence-composer-note="true">{escape(note)}</textarea>'
        "</label>"
        '<label>reviewer'
        f'<input data-evidence-composer-reviewer="true" value="{escape(reviewer)}">'
        "</label>"
        '<label>evidence file'
        f'<input data-evidence-composer-url="true" value="{escape(evidence_url)}">'
        "</label>"
        '<label>evidence summary'
        f'<textarea data-evidence-composer-summary="true">{escape(evidence_summary)}</textarea>'
        "</label>"
        "</div>"
        '<div class="expert-console-controls">'
        '<button type="button" class="expert-console-next next-action-primary"'
        ' data-evidence-composer-submit="true"'
        f' data-review-actions-source-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-stock-id="{escape(stock_id)}"'
        f' data-action-id="{escape(action_id)}"'
        ' data-status-value="done">'
        "建立證據並標記完成"
        "</button>"
        "</div>"
        '<div class="evidence-composer-result" data-evidence-composer-result="true"'
        ' data-evidence-quality-status="unknown">'
        '<p class="evidence-quality-summary">Reviewer Confidence（審查信心）：未知。</p>'
        '<p class="evidence-quality-next">證據檔尚未建立。</p>'
        '<ul class="evidence-quality-checks" data-evidence-quality-checks="true"></ul>'
        '<div class="evidence-preview" data-evidence-preview="true">'
        "<strong>Evidence Preview（證據預覽）</strong>"
        '<p data-evidence-preview-content="true">尚無證據預覽。</p>'
        "</div>"
        "</div>"
        "</div>"
    )


def _next_action_pack_button(
    summary: dict[str, Any],
    state_path: str,
    *,
    action_api_enabled: bool = False,
) -> str:
    source_path = str(summary.get("path") or "")
    output_dir = _handoff_pack_output_dir(summary)
    command = _handoff_pack_command(source_path, state_path, output_dir)
    button_label = "\u7522\u51fa Evidence Pack"
    return (
        '<button type="button" class="expert-console-next next-action-primary" '
        'data-next-action-primary="true" data-handoff-pack-write="true"'
        f' data-research-summary-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-output-dir="{escape(output_dir)}"'
        f' data-command="{escape(command)}">{escape(button_label)}</button>'
    )


def _handoff_pack_workflow(
    summary: dict[str, Any],
    gate: dict[str, Any],
    state_path: str,
    *,
    action_api_enabled: bool = False,
) -> str:
    source_path = str(summary.get("path") or "")
    output_dir = _handoff_pack_output_dir(summary)
    command = _handoff_pack_command(source_path, state_path, output_dir)
    button_label = "\u7522\u51fa Evidence Pack" if action_api_enabled else "\u8907\u88fd Evidence Pack \u6307\u4ee4"
    mode_label = (
        "\u76ee\u524d\u662f API \u6a21\u5f0f\uff1a\u6309\u9215\u6703\u76f4\u63a5\u7522\u51fa handoff-pack \u6a94\u6848\u3002"
        if action_api_enabled
        else "\u76ee\u524d\u662f\u975c\u614b\u6a21\u5f0f\uff1a\u6309\u9215\u6703\u8907\u88fd CLI \u6307\u4ee4\u3002"
    )
    return (
        '<div class="handoff-pack-workflow" data-handoff-pack-workflow="true">'
        "<h4>\u4ea4\u4ed8 Evidence Pack</h4>"
        f'<p class="status-line"><span class="badge">output: {escape(output_dir)}</span>'
        f'<span class="badge">gate: {escape(str(gate.get("status", "-")))}</span></p>'
        f'<p>{escape(mode_label)}</p>'
        f"{_handoff_pack_evidence_guidance(gate, summary)}"
        '<div class="handoff-pack-controls">'
        '<button type="button" class="expert-console-next" data-handoff-pack-write="true"'
        f' data-research-summary-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-output-dir="{escape(output_dir)}"'
        f' data-command="{escape(command)}">{escape(button_label)}</button>'
        "</div>"
        '<details class="review-action-detail">'
        "<summary>CLI</summary>"
        f'<code class="review-action-command-fallback">{escape(command)}</code>'
        "</details>"
        '<div class="handoff-pack-result" data-handoff-pack-result="true">'
        "\u8655\u7406\u7d50\u679c\uff1a\u5c1a\u672a\u7522\u51fa\u3002"
        "</div>"
        "</div>"
    )


def _handoff_pack_evidence_guidance(gate: dict[str, Any], summary: dict[str, Any]) -> str:
    blockers = gate.get("blockers", [])
    evidence_blockers = [
        blocker
        for blocker in (blockers if isinstance(blockers, list) else [])
        if isinstance(blocker, dict) and blocker.get("kind") in {"missing_evidence", "invalid_evidence"}
    ]
    if not evidence_blockers:
        return '<p class="handoff-pack-guidance" data-handoff-pack-evidence-guidance="true">\u9700\u88dc\u8b49\u64da\uff1a0\u3002</p>'

    rows: list[str] = []
    for blocker in evidence_blockers[:5]:
        stock_id = str(blocker.get("stock_id") or "-")
        action_id = str(blocker.get("action_id") or "-")
        suggested_path = _suggested_evidence_path(summary, stock_id, action_id)
        if blocker.get("kind") == "missing_evidence":
            missing = str(blocker.get("missing_evidence_fields") or "note, reviewer, evidence_url")
            detail = f"{stock_id} {action_id}: \u88dc {missing}\uff1b\u5efa\u8b70\u6a94\u6848 {suggested_path}"
        else:
            current = str(blocker.get("evidence_url") or "-")
            detail = f"{stock_id} {action_id}: \u76ee\u524d evidence {current} \u7121\u6548\uff1b\u5efa\u7acb\u6a94\u6848\u6216\u6539\u7528 {suggested_path}"
        rows.append(f"<li>{escape(detail)}</li>")
    return (
        '<div class="handoff-pack-guidance" data-handoff-pack-evidence-guidance="true">'
        "<strong>\u7f3a\u8b49\u64da\u512a\u5148\u88dc\u4ef6</strong>"
        f"<ul>{''.join(rows)}</ul>"
        "</div>"
    )


def _handoff_pack_command(research_summary_path: str, state_path: str, output_dir: str) -> str:
    args = [
        "python",
        "-m",
        "taiwan_stock_analysis.cli",
        "research",
        "handoff-pack",
        research_summary_path or "research_summary.json",
        "--state",
        state_path or "review_action_state.json",
        "--output-dir",
        output_dir or "handoff-pack",
    ]
    return " ".join(_powershell_arg(arg) for arg in args)


def _handoff_pack_output_dir(summary: dict[str, Any]) -> str:
    source_path = str(summary.get("path") or "").strip()
    if source_path:
        return (Path(source_path).parent / "handoff-pack").as_posix()
    base_dir = str(summary.get("base_dir") or "").strip()
    if base_dir:
        return (Path(base_dir) / "handoff-pack").as_posix()
    return "handoff-pack"


def _research_summary_base_dir(summary: dict[str, Any]) -> Path | None:
    base_dir = str(summary.get("base_dir") or "").strip()
    return Path(base_dir) if base_dir else None


def _suggested_evidence_path(summary: dict[str, Any], stock_id: str, action_id: str) -> str:
    source_path = str(summary.get("path") or "").strip()
    base = Path(source_path).parent if source_path else Path(str(summary.get("base_dir") or "."))
    safe_stock = "".join(char if char.isalnum() or char in "-_" else "-" for char in stock_id or "stock")
    safe_action = "".join(char if char.isalnum() or char in "-_" else "-" for char in action_id or "action")
    return (base / "evidence" / f"{safe_stock}-{safe_action}.md").as_posix()


def _expert_console_open_actions(action_queue: list[Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        item_actions = item.get("actions", [])
        if not isinstance(item_actions, list):
            continue
        stock_id = str(item.get("stock_id") or "-")
        company_name = str(item.get("company_name") or "")
        priority = str(item.get("priority") or "")
        for action in item_actions:
            if not isinstance(action, dict):
                continue
            status = str(action.get("status") or "open")
            if status != "open":
                continue
            category = str(action.get("category") or "")
            severity = str(action.get("severity") or "")
            message = str(action.get("message") or "")
            actions.append(
                {
                    "stock_id": stock_id,
                    "company_name": company_name,
                    "priority": priority,
                    "category": category,
                    "severity": severity,
                    "message": _review_action_user_message(action, message),
                    "action_id": str(action.get("id") or ""),
                    "expert_label": _expert_agent_label(category),
                }
            )
    return actions


def _expert_console_sync_note(open_actions: list[dict[str, str]], action_api_enabled: bool) -> str:
    if not open_actions:
        return ""
    if action_api_enabled:
        message = (
            "\u76ee\u524d\u662f API \u6a21\u5f0f\uff1a\u6a19\u8a18\u5b8c\u6210\u6216\u7a0d\u5f8c\u8655\u7406\u5f8c\uff0c"
            "Console \u6703\u5373\u6642\u91cd\u7b97\u4ea4\u63a5\u72c0\u614b\u8207 Top 3\u3002"
        )
        return f'<p class="empty" data-expert-console-sync-note="true">{escape(message)}</p>'
    return (
        '<p class="empty" data-expert-console-refresh-note="true">'
        "\u5b8c\u6210\u6216\u7a0d\u5f8c\u8655\u7406\u5be9\u67e5\u52d5\u4f5c\u5f8c\uff0c"
        "\u8acb\u91cd\u65b0\u6574\u7406\u9801\u9762\u6216\u91cd\u65b0\u7522\u751f dashboard \u4ee5\u91cd\u7b97\u4ea4\u63a5\u72c0\u614b\u8207 Top 3\u3002"
        "</p>"
    )


def _expert_console_toolbar(actions: list[dict[str, str]]) -> str:
    direct_actions = [
        action
        for action in actions
        if action.get("focus_available", "true") == "true" and action.get("action_id") and action.get("stock_id")
    ]
    if not direct_actions:
        return ""
    return (
        '<div class="expert-console-toolbar" data-expert-console-bulk="true">'
        '<button type="button" class="expert-console-next" data-expert-console-bulk-status="done">Top 3 標記完成</button>'
        '<button type="button" class="expert-console-next" data-expert-console-bulk-status="deferred">Top 3 稍後處理</button>'
        "</div>"
    )


def _expert_console_action_list(actions: list[dict[str, str]], source_path: str, state_path: str) -> str:
    if not actions:
        return (
            '<p class="empty" data-expert-console-top-actions="true">'
            "\u76ee\u524d\u6c92\u6709\u958b\u555f\u7684\u963b\u585e\u4e8b\u9805\uff1b\u4e0b\u4e00\u6b65\u662f\u9032\u884c\u4eba\u5de5\u95b1\u8b80\u8207\u7c3d\u6838\u3002"
            "</p>"
        )
    return (
        '<ol class="expert-console-actions" data-expert-console-top-actions="true">'
        f"{''.join(_expert_console_action_item(action, source_path, state_path) for action in actions)}"
        "</ol>"
    )


def _expert_console_action_item(action: dict[str, str], source_path: str, state_path: str) -> str:
    stock_id = action.get("stock_id", "-")
    company_name = action.get("company_name", "")
    category = action.get("category", "")
    severity = action.get("severity", "")
    priority = action.get("priority", "")
    action_id = action.get("action_id", "")
    evidence_required = requires_handoff_evidence(action_id)
    focus_available = action.get("focus_available", "true") == "true" and bool(action_id)
    focus_search = _expert_console_focus_search(action)
    title = stock_id if not company_name else f"{stock_id} {company_name}"
    next_copy = (
        "先確認這個阻塞，處理完可直接標記完成；需要保留但不阻塞時標記稍後處理。"
        if focus_available
        else action.get("next_step", "請執行 handoff doctor 後重新產生 dashboard。")
    )
    if evidence_required and action.get("kind") == "missing_evidence":
        next_copy = "\u88dc\u9f4a note\u3001reviewer\u3001evidence URL \u5f8c\u518d\u66f4\u65b0\u72c0\u614b\u3002"
    focus_control = (
        '<button type="button" class="expert-console-next"'
        f' data-expert-console-source-path="{escape(source_path)}"'
        f' data-expert-console-stock-id="{escape(stock_id)}"'
        f' data-expert-console-action-id="{escape(action_id)}"'
        f' data-expert-console-focus-category="{escape(category)}"'
        f' data-expert-console-focus-search="{escape(focus_search)}">'
        "\u524d\u5f80\u9019\u500b\u963b\u585e"
        "</button>"
        if focus_available
        else ""
    )
    task_controls = (
        '<div class="expert-console-controls">'
        f'{_expert_console_action_button(action, source_path, state_path, "done", "標記完成")}'
        f'{_expert_console_action_button(action, source_path, state_path, "deferred", "稍後處理")}'
        f"{focus_control}"
        "</div>"
        if focus_available
        else ""
    )
    evidence_badge = '<span class="badge">\u9700\u8981\u4ea4\u4ed8\u8b49\u64da</span>' if evidence_required else ""
    evidence_copy = '<p class="expert-console-task-copy">\u4ea4\u4ed8\u8b49\u64da\uff1a\u9700\u8981 note\u3001reviewer\u3001evidence URL\u3002</p>' if evidence_required else ""
    return (
        '<li class="expert-console-action" data-expert-console-task="true">'
        '<div class="expert-console-meta">'
        f'<span class="badge">{escape(action.get("expert_label") or _expert_agent_label(category))}</span>'
        f'<span class="badge">{escape(_review_label(severity, REVIEW_ACTION_SEVERITY_LABELS))}</span>'
        f'<span class="badge">{escape(_review_label(priority, REVIEW_ACTION_PRIORITY_LABELS))}</span>'
        f"{evidence_badge}"
        "</div>"
        f'<strong class="expert-console-task-title">{escape(title)}</strong>'
        f'<p class="expert-console-task-copy"><strong>問題：</strong>{escape(action.get("message", ""))}</p>'
        f'<p class="expert-console-task-copy" data-expert-console-next-copy="true"><strong>建議處理：</strong>{escape(next_copy)}</p>'
        f"{evidence_copy}"
        f"{task_controls}"
        '<p class="expert-console-result" data-expert-console-task-result="true">處理結果：尚未處理</p>'
        "</li>"
    )


def _expert_console_action_button(
    action: dict[str, str],
    source_path: str,
    state_path: str,
    status: str,
    label: str,
) -> str:
    stock_id = action.get("stock_id", "")
    action_id = action.get("action_id", "")
    evidence_required = requires_handoff_evidence(action_id)
    command = _review_action_state_command(state_path, stock_id, action_id, status)
    return (
        '<button type="button" class="expert-console-next" data-expert-console-action-command="true"'
        f' data-expert-console-source-path="{escape(source_path)}"'
        f' data-review-actions-source-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-stock-id="{escape(stock_id)}"'
        f' data-action-id="{escape(action_id)}"'
        f' data-status-value="{escape(status)}"'
        f' data-evidence-required="{str(evidence_required).lower()}"'
        f' data-note="{escape(action.get("note", ""))}"'
        f' data-reviewer="{escape(action.get("reviewer", ""))}"'
        f' data-evidence-url="{escape(action.get("evidence_url", ""))}"'
        f' data-updated-at="{escape(action.get("updated_at", ""))}"'
        f' data-expert-console-stock-id="{escape(stock_id)}"'
        f' data-expert-console-action-id="{escape(action_id)}"'
        f' data-command="{escape(command)}">'
        f"{escape(label)}"
        "</button>"
    )


def _expert_console_focus_search(action: dict[str, str]) -> str:
    stock_id = str(action.get("stock_id") or "").strip()
    if stock_id and stock_id != "-":
        return stock_id.lower()
    company_name = str(action.get("company_name") or "").strip()
    if company_name:
        return company_name.lower()
    return str(action.get("message") or "").strip().lower()


def _expert_agent_label(category: str) -> str:
    if category in EXPERT_AGENT_LABELS:
        return EXPERT_AGENT_LABELS[category]
    return _review_label(category, REVIEW_ACTION_CATEGORY_LABELS)


def _industry_rotation_map_section(research_summaries: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for summary in research_summaries:
        if not isinstance(summary, dict) or summary.get("error"):
            continue
        block = _industry_map_source_block(summary)
        if block:
            blocks.append(block)

    if not blocks:
        return ""
    return (
        '<section data-industry-rotation-map="true">'
        "<h2>產業輪動地圖</h2>"
        '<p class="industry-map-lead">'
        "用產業分類整理研究交付壓力、證據缺口與專家阻塞，幫助先處理最卡住的研究包；"
        "這裡的顏色與排序只代表 handoff gate 狀態，不代表產業強弱或買賣方向。"
        "</p>"
        f"{''.join(blocks)}"
        '<p class="industry-map-note" data-industry-map-non-advice="true">'
        "本圖用於研究交付排程、證據覆核與 blocker triage；"
        "不構成買賣、持有、目標價或配置建議。"
        "</p>"
        "</section>"
    )


def _industry_map_source_block(summary: dict[str, Any]) -> str:
    entries = _industry_map_entries(summary)
    if not entries:
        return ""

    source_path = str(summary.get("path") or "")
    state = _dict_value(summary.get("review_action_state"))
    gate = build_handoff_quality_gate(
        summary,
        state,
        blocker_limit=3,
        evidence_base_dir=_research_summary_base_dir(summary),
    )
    blocked_industries = sum(1 for entry in entries if entry["status"] == "blocked")
    evidence_gap_total = sum(int(entry["evidence_missing_count"]) for entry in entries)
    top_lens = _industry_map_top_lens(entries)
    market_summary = _industry_map_market_summary(entries)
    handoff_text = "可交接" if gate.get("ready") else "尚未可交接"
    next_step = str(gate.get("next_step") or "-")
    state_path = _review_action_state_path(summary)
    card_html: list[str] = []
    detail_templates: list[str] = []
    for index, entry in enumerate(entries):
        detail_id = f"industry-detail-{index}"
        card_html.append(_industry_map_card(entry, source_path, detail_id))
        detail_templates.append(_industry_map_detail_template(entry, source_path, state_path, detail_id))
    initial_detail = _industry_map_detail_body(entries[0], source_path, state_path) if entries else ""

    return (
        '<div class="industry-map-source" data-industry-map-source="true">'
        f"<p>{_link(source_path, Path(source_path).name or 'research_summary.json')}</p>"
        '<div class="industry-map-summary">'
        '<div class="industry-map-summary-item"><strong>可否交接</strong>'
        f"<span>{escape(handoff_text)}</span></div>"
        '<div class="industry-map-summary-item"><strong>最大阻塞來源</strong>'
        f"<span>{escape(top_lens)}</span></div>"
        '<div class="industry-map-summary-item"><strong>\u5e02\u5834\u8f2a\u52d5 overlay</strong>'
        f"<span>{escape(market_summary)}</span></div>"
        '<div class="industry-map-summary-item"><strong>最短修復路徑</strong>'
        f"<span>{escape(next_step)}</span></div>"
        '<div class="industry-map-summary-item"><strong>需優先處理</strong>'
        f"<span>{escape(str(blocked_industries))} 個產業，{escape(str(evidence_gap_total))} 件待補交付證據</span></div>"
        "</div>"
        '<div class="industry-map-workflow" data-industry-map-workflow="true">'
        '<div class="industry-map-list">'
        f"{_industry_map_filter_bar(len(entries))}"
        '<div class="industry-map-grid" data-industry-map-grid="true">'
        f"{''.join(card_html)}"
        "</div>"
        "</div>"
        '<aside class="industry-map-detail-panel" data-industry-map-detail-panel="true" aria-live="polite">'
        f"{initial_detail}"
        "</aside>"
        "</div>"
        '<div class="industry-map-detail-templates" hidden>'
        f"{''.join(detail_templates)}"
        "</div>"
        "</div>"
    )


def _industry_map_entries(summary: dict[str, Any]) -> list[dict[str, Any]]:
    stock_lookup = _industry_stock_lookup(summary)
    groups: dict[str, dict[str, Any]] = {}

    def group_for(category: str) -> dict[str, Any]:
        clean_category = category.strip() or "未分類"
        if clean_category not in groups:
            groups[clean_category] = {
                "category": clean_category,
                "stocks": {},
                "high_priority_stocks": set(),
                "attention_stocks": set(),
                "blocker_count": 0,
                "open_count": 0,
                "evidence_missing_count": 0,
                "invalid_evidence_count": 0,
                "stale_count": 0,
                "missing_gate_count": 0,
                "lens_counts": {},
                "top_blockers": [],
                "evidence_rows": {},
                "market_stock_ids": set(),
                "market_available_count": 0,
                "market_returns": {"1d": [], "5d": [], "20d": []},
                "market_notes": [],
                "market_volume_signals": [],
                "market_direction_counts": {},
            }
        return groups[clean_category]

    for stock_id, record in stock_lookup.items():
        group = group_for(str(record.get("category") or "未分類"))
        _industry_add_stock(group, stock_id, record)

    source_queue = summary.get("review_action_queue", [])
    queue = source_queue if isinstance(source_queue, list) else []
    state = _dict_value(summary.get("review_action_state"))
    overlaid_queue = apply_review_action_state(queue, state)
    for item in overlaid_queue:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "-")
        record = _industry_record_for_action_item(stock_lookup, item)
        group = group_for(str(record.get("category") or "未分類"))
        _industry_add_stock(group, stock_id, record)
        evidence_row = _industry_stock_evidence_row(group, stock_id, record)
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            status = str(action.get("status") or "open")
            action_id = str(action.get("id") or "")
            category = str(action.get("category") or "")
            evidence_row["action_count"] = int(evidence_row["action_count"]) + 1
            if status == "open":
                group["open_count"] = int(group["open_count"]) + 1
                evidence_row["open_count"] = int(evidence_row["open_count"]) + 1
            if requires_handoff_evidence(action_id):
                evidence_row["evidence_required_count"] = int(evidence_row["evidence_required_count"]) + 1
                if status != "open" and _industry_action_has_handoff_evidence(action):
                    evidence_row["evidence_filled_count"] = int(evidence_row["evidence_filled_count"]) + 1
            _industry_evidence_row_set_focus(evidence_row, action_id, category, action)

    gate = build_handoff_quality_gate(
        summary,
        state,
        blocker_limit=999,
        evidence_base_dir=_research_summary_base_dir(summary),
    )
    blockers_value = gate.get("blockers", [])
    blockers = blockers_value if isinstance(blockers_value, list) else []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        stock_id = str(blocker.get("stock_id") or "-")
        record = stock_lookup.get(stock_id, {})
        category = str(record.get("category") or "未分類")
        group = group_for(category)
        if stock_id and stock_id != "-":
            _industry_add_stock(
                group,
                stock_id,
                {
                    "company_name": str(blocker.get("company_name") or record.get("company_name") or ""),
                    "priority": str(blocker.get("priority") or record.get("priority") or ""),
                    "attention_reasons": record.get("attention_reasons", []),
                },
            )
        evidence_row = _industry_stock_evidence_row(group, stock_id, record)
        _industry_evidence_row_add_blocker(summary, evidence_row, blocker)
        group["blocker_count"] = int(group["blocker_count"]) + 1
        kind = str(blocker.get("kind") or "")
        if kind == "missing_evidence":
            group["evidence_missing_count"] = int(group["evidence_missing_count"]) + 1
        elif kind == "invalid_evidence":
            group["invalid_evidence_count"] = int(group["invalid_evidence_count"]) + 1
        elif kind == "stale_state":
            group["stale_count"] = int(group["stale_count"]) + 1
        elif kind == "missing_gate_action":
            group["missing_gate_count"] = int(group["missing_gate_count"]) + 1
        lens = str(blocker.get("category") or "")
        if lens:
            lens_counts = group["lens_counts"]
            lens_counts[lens] = int(lens_counts.get(lens, 0)) + 1
        top_blockers = group["top_blockers"]
        if len(top_blockers) < 3:
            top_blockers.append(blocker)

    entries: list[dict[str, Any]] = []
    max_score = 1
    for group in groups.values():
        stock_count = len(group["stocks"])
        high_priority_count = len(group["high_priority_stocks"])
        attention_count = len(group["attention_stocks"])
        score = (
            int(group["blocker_count"]) * 4
            + int(group["evidence_missing_count"]) * 2
            + int(group["invalid_evidence_count"]) * 2
            + int(group["stale_count"]) * 2
            + attention_count
            + high_priority_count
        )
        max_score = max(max_score, score)
        status = "ready"
        if int(group["blocker_count"]) > 0:
            status = "blocked"
        elif attention_count > 0 or high_priority_count > 0:
            status = "needs-review"
        entry = {
            "category": group["category"],
            "stock_count": stock_count,
            "high_priority_count": high_priority_count,
            "attention_count": attention_count,
            "blocker_count": int(group["blocker_count"]),
            "open_count": int(group["open_count"]),
            "evidence_missing_count": int(group["evidence_missing_count"]),
            "invalid_evidence_count": int(group["invalid_evidence_count"]),
            "stale_count": int(group["stale_count"]),
            "missing_gate_count": int(group["missing_gate_count"]),
            "lens_counts": group["lens_counts"],
            "top_blockers": group["top_blockers"],
            "evidence_rows": _industry_evidence_rows(group["evidence_rows"]),
            "market_overlay": _industry_market_overlay(group),
            "sample_stocks": _industry_sample_stocks(group["stocks"]),
            "score": score,
            "status": status,
            "pressure": 0,
        }
        entries.append(entry)

    for entry in entries:
        score = int(entry["score"])
        entry["pressure"] = 5 if score <= 0 else max(12, min(100, round(score / max_score * 100)))

    return sorted(entries, key=lambda entry: (-int(entry["score"]), str(entry["category"])))


def _industry_stock_lookup(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in _industry_summary_items(summary):
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "").strip()
        if not stock_id:
            continue
        record = records.setdefault(stock_id, {})
        record["category"] = str(item.get("category") or record.get("category") or "未分類")
        record["company_name"] = str(item.get("company_name") or record.get("company_name") or "")
        record["priority"] = str(item.get("priority") or record.get("priority") or "")
        reasons = item.get("attention_reasons", record.get("attention_reasons", []))
        record["attention_reasons"] = reasons if isinstance(reasons, list) else [str(reasons)]
        market_rotation = item.get("market_rotation")
        if isinstance(market_rotation, dict):
            record["market_rotation"] = market_rotation
    return records


def _industry_summary_items(summary: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    source_items = summary.get("items", [])
    if isinstance(source_items, list):
        items.extend(source_items)
    universe_review = summary.get("universe_review", {})
    if isinstance(universe_review, dict):
        queue = universe_review.get("attention_queue", [])
        if isinstance(queue, list):
            items.extend(queue)
    return items


def _industry_record_for_action_item(stock_lookup: dict[str, dict[str, Any]], item: dict[str, Any]) -> dict[str, Any]:
    stock_id = str(item.get("stock_id") or "")
    record = dict(stock_lookup.get(stock_id, {}))
    record.setdefault("category", "未分類")
    record.setdefault("company_name", str(item.get("company_name") or ""))
    record.setdefault("priority", str(item.get("priority") or ""))
    record.setdefault("attention_reasons", [])
    return record


def _industry_add_stock(group: dict[str, Any], stock_id: str, record: dict[str, Any]) -> None:
    if not stock_id or stock_id == "-":
        return
    stocks = group["stocks"]
    stocks[stock_id] = str(record.get("company_name") or stocks.get(stock_id) or "")
    if str(record.get("priority") or "") == "high":
        group["high_priority_stocks"].add(stock_id)
    reasons = record.get("attention_reasons", [])
    if isinstance(reasons, list) and any(str(reason).strip() for reason in reasons):
        group["attention_stocks"].add(stock_id)
    _industry_add_market_rotation(group, stock_id, record)
    _industry_stock_evidence_row(group, stock_id, record)


def _industry_add_market_rotation(group: dict[str, Any], stock_id: str, record: dict[str, Any]) -> None:
    seen = group["market_stock_ids"]
    if stock_id in seen:
        return
    seen.add(stock_id)
    rotation = record.get("market_rotation")
    if not isinstance(rotation, dict):
        rotation = {}
    status = str(rotation.get("status") or "")
    direction = str(rotation.get("direction") or "")
    has_data = status == "available" or any(
        _market_float(rotation.get(key)) is not None for key in ("return_1d", "return_5d", "return_20d")
    ) or bool(str(rotation.get("volume_signal") or "").strip() or str(rotation.get("note") or "").strip())
    if has_data:
        group["market_available_count"] = int(group["market_available_count"]) + 1
    else:
        direction = "missing"
    returns = group["market_returns"]
    returns["1d"].append(_market_float(rotation.get("return_1d")))
    returns["5d"].append(_market_float(rotation.get("return_5d")))
    returns["20d"].append(_market_float(rotation.get("return_20d")))
    note = str(rotation.get("note") or "").strip()
    if has_data and len(group["market_notes"]) < 4:
        return_20d = _market_return_text(rotation.get("return_20d"))
        note_parts = [f"{stock_id}: 20D {return_20d}"]
        if note:
            note_parts.append(note)
        group["market_notes"].append(" - ".join(note_parts))
    volume_signal = str(rotation.get("volume_signal") or "").strip()
    if volume_signal and volume_signal not in group["market_volume_signals"]:
        group["market_volume_signals"].append(volume_signal)
    clean_direction = direction if direction in {"up", "down", "flat", "mixed", "missing"} else "missing"
    direction_counts = group["market_direction_counts"]
    direction_counts[clean_direction] = int(direction_counts.get(clean_direction, 0)) + 1


def _industry_market_overlay(group: dict[str, Any]) -> dict[str, Any]:
    stock_count = len(group["market_stock_ids"])
    coverage_count = int(group["market_available_count"])
    average_return_1d = _market_average(group["market_returns"]["1d"])
    average_return_5d = _market_average(group["market_returns"]["5d"])
    average_return_20d = _market_average(group["market_returns"]["20d"])
    direction = _industry_market_direction(
        _dict_value(group.get("market_direction_counts")),
        average_return_20d,
        average_return_5d,
        average_return_1d,
    )
    return {
        "status": "available" if coverage_count > 0 else "missing",
        "direction": direction,
        "stock_count": stock_count,
        "coverage_count": coverage_count,
        "missing_count": max(0, stock_count - coverage_count),
        "average_return_1d": average_return_1d,
        "average_return_5d": average_return_5d,
        "average_return_20d": average_return_20d,
        "volume_signals": list(group["market_volume_signals"])[:3],
        "notes": list(group["market_notes"])[:3],
    }


def _industry_market_direction(
    direction_counts: dict[str, Any],
    average_return_20d: float | None,
    average_return_5d: float | None,
    average_return_1d: float | None,
) -> str:
    available_directions = {
        str(direction)
        for direction, count in direction_counts.items()
        if str(direction) != "missing" and int(count or 0) > 0
    }
    if "up" in available_directions and "down" in available_directions:
        return "mixed"
    value = average_return_20d
    if value is None:
        value = average_return_5d
    if value is None:
        value = average_return_1d
    if value is None:
        return "missing"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _market_average(values: list[Any]) -> float | None:
    numbers = [value for value in (_market_float(value) for value in values) if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 2)


def _market_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    normalized = text.removesuffix("%").replace(",", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def _market_return_text(value: Any) -> str:
    number = _market_float(value)
    if number is None:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _market_direction_label(direction: str) -> str:
    labels = {
        "up": "\u8f2a\u52d5\u504f\u5f37",
        "down": "\u8f2a\u52d5\u504f\u5f31",
        "mixed": "\u8f2a\u52d5\u5206\u6b67",
        "flat": "\u8f2a\u52d5\u6301\u5e73",
        "missing": "\u5e02\u5834\u8cc7\u6599\u7f3a\u53e3",
    }
    return labels.get(direction, direction or "-")


def _industry_stock_evidence_row(group: dict[str, Any], stock_id: str, record: dict[str, Any]) -> dict[str, Any]:
    rows = group["evidence_rows"]
    row = rows.setdefault(
        stock_id,
        {
            "stock_id": stock_id,
            "company_name": "",
            "priority": "",
            "action_count": 0,
            "evidence_required_count": 0,
            "evidence_filled_count": 0,
            "open_count": 0,
            "blocker_count": 0,
            "open_blocker_count": 0,
            "missing_evidence_count": 0,
            "invalid_evidence_count": 0,
            "stale_count": 0,
            "missing_gate_count": 0,
            "missing_fields": set(),
            "suggested_paths": [],
            "lens_counts": {},
            "focus_action_id": "",
            "focus_category": "all",
            "focus_note": "",
            "focus_reviewer": "",
            "focus_evidence_url": "",
            "focus_updated_at": "",
        },
    )
    company_name = str(record.get("company_name") or "")
    priority = str(record.get("priority") or "")
    if company_name:
        row["company_name"] = company_name
    if priority:
        row["priority"] = priority
    return row


def _industry_action_has_handoff_evidence(action: dict[str, Any]) -> bool:
    return all(str(action.get(field) or "").strip() for field in ("note", "reviewer", "evidence_url", "updated_at"))


def _industry_evidence_row_set_focus(
    row: dict[str, Any],
    action_id: str,
    category: str,
    action: dict[str, Any],
) -> None:
    if row.get("focus_action_id") or not action_id:
        return
    row["focus_action_id"] = action_id
    row["focus_category"] = category or "all"
    row["focus_note"] = str(action.get("note") or "")
    row["focus_reviewer"] = str(action.get("reviewer") or "")
    row["focus_evidence_url"] = str(action.get("evidence_url") or "")
    row["focus_updated_at"] = str(action.get("updated_at") or "")


def _industry_evidence_row_add_blocker(
    summary: dict[str, Any],
    row: dict[str, Any],
    blocker: dict[str, Any],
) -> None:
    row["blocker_count"] = int(row["blocker_count"]) + 1
    kind = str(blocker.get("kind") or "")
    category = str(blocker.get("category") or "")
    action_id = str(blocker.get("action_id") or "")
    if kind == "open_action":
        row["open_blocker_count"] = int(row["open_blocker_count"]) + 1
    elif kind == "missing_evidence":
        row["missing_evidence_count"] = int(row["missing_evidence_count"]) + 1
        missing = str(blocker.get("missing_evidence_fields") or "")
        row["missing_fields"].update(field.strip() for field in missing.split(",") if field.strip())
        row["suggested_paths"].append(_suggested_evidence_path(summary, str(row["stock_id"]), action_id))
    elif kind == "invalid_evidence":
        row["invalid_evidence_count"] = int(row["invalid_evidence_count"]) + 1
        row["suggested_paths"].append(_suggested_evidence_path(summary, str(row["stock_id"]), action_id))
    elif kind == "stale_state":
        row["stale_count"] = int(row["stale_count"]) + 1
    elif kind == "missing_gate_action":
        row["missing_gate_count"] = int(row["missing_gate_count"]) + 1
    if category:
        lens_counts = row["lens_counts"]
        lens_counts[category] = int(lens_counts.get(category, 0)) + 1
    if action_id:
        row["focus_action_id"] = row.get("focus_action_id") or action_id
        row["focus_category"] = row.get("focus_category") or category or "all"
        row["focus_note"] = row.get("focus_note") or str(blocker.get("note") or "")
        row["focus_reviewer"] = row.get("focus_reviewer") or str(blocker.get("reviewer") or "")
        row["focus_evidence_url"] = row.get("focus_evidence_url") or str(blocker.get("evidence_url") or "")
        row["focus_updated_at"] = row.get("focus_updated_at") or str(blocker.get("updated_at") or "")


def _industry_evidence_rows(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows.values():
        normalized_row = dict(row)
        normalized_row["missing_fields"] = sorted(str(field) for field in row.get("missing_fields", set()))
        normalized_row["suggested_paths"] = [
            str(path) for path in row.get("suggested_paths", []) if str(path).strip()
        ]
        normalized_row["status"] = _industry_evidence_row_status(normalized_row)
        normalized.append(normalized_row)
    status_order = {"invalid": 0, "missing": 1, "open": 2, "ready": 3}
    return sorted(
        normalized,
        key=lambda row: (
            status_order.get(str(row["status"]), 9),
            -int(row.get("blocker_count") or 0),
            str(row.get("stock_id") or ""),
        ),
    )


def _industry_evidence_row_status(row: dict[str, Any]) -> str:
    if int(row.get("invalid_evidence_count") or 0) > 0:
        return "invalid"
    if int(row.get("missing_evidence_count") or 0) > 0:
        return "missing"
    if int(row.get("open_blocker_count") or 0) > 0 or int(row.get("open_count") or 0) > 0:
        return "open"
    return "ready"

def _industry_map_card(entry: dict[str, Any], source_path: str, detail_id: str) -> str:
    category = str(entry["category"])
    status = str(entry["status"])
    status_label = _industry_status_label(entry)
    pressure = int(entry["pressure"])
    lens_counts = entry.get("lens_counts", {})
    lens_summary = _count_pairs(lens_counts if isinstance(lens_counts, dict) else {}, REVIEW_ACTION_CATEGORY_LABELS)
    sample_stocks = _list_value(entry.get("sample_stocks"))
    focus = _industry_map_focus(entry)
    evidence_status = _industry_map_evidence_status(entry)
    market_overlay = _dict_value(entry.get("market_overlay"))
    market_direction = str(market_overlay.get("direction") or "missing")
    market_status = str(market_overlay.get("status") or "missing")
    lens_keys = " ".join(sorted(str(key) for key in lens_counts)) if isinstance(lens_counts, dict) else ""
    search_text = _industry_map_search_text(entry)
    focus_button = ""
    if focus:
        focus_button = (
            '<button type="button" class="expert-console-next" data-industry-map-focus-stock="'
            f'{escape(focus.get("stock_id", ""))}"'
            f' data-industry-map-focus-action="{escape(focus.get("action_id", ""))}"'
            f' data-industry-map-focus-category="{escape(focus.get("category", "all"))}"'
            f' data-review-actions-source-path="{escape(source_path)}">\u524d\u5f80\u7b2c\u4e00\u500b\u963b\u585e</button>'
        )
    detail_button = (
        '<button type="button" class="expert-console-next" data-industry-map-detail-target="'
        f'{escape(detail_id)}">\u67e5\u770b\u7522\u696d\u4efb\u52d9</button>'
    )
    sample_text = ", ".join(sample_stocks) if sample_stocks else "-"
    blocker_copy = _industry_blocker_copy(entry)
    return (
        '<article class="industry-map-card" data-industry-map-card="true"'
        f' data-industry-map-status="{escape(status)}"'
        f' data-industry-map-evidence-status="{escape(evidence_status)}"'
        f' data-industry-map-market-direction="{escape(market_direction)}"'
        f' data-industry-map-market-status="{escape(market_status)}"'
        f' data-industry-map-lenses="{escape(lens_keys)}"'
        f' data-industry-map-search-text="{escape(search_text)}"'
        f' data-industry-map-detail-id="{escape(detail_id)}"'
        f' data-industry-name="{escape(category)}"'
        f' tabindex="0" aria-label="{escape(_industry_map_card_aria(entry))}">'
        '<div class="industry-map-head">'
        f"<h3>{escape(category)}</h3>"
        f'<span class="industry-status-pill">{escape(status_label)}</span>'
        "</div>"
        f'<p class="industry-map-lead">{escape(blocker_copy)}</p>'
        f'<div class="industry-pressure" aria-label="research pressure {escape(str(pressure))}">'
        f'<span style="width: {escape(str(pressure))}%"></span></div>'
        f'{_industry_market_overlay_block(market_overlay)}'
        '<div class="industry-map-metrics">'
        f'<span><strong>{escape(str(entry["stock_count"]))}</strong>\u80a1\u7968</span>'
        f'<span><strong>{escape(str(entry["blocker_count"]))}</strong>blockers</span>'
        f'<span><strong>{escape(str(entry["evidence_missing_count"]))}</strong>\u7f3a\u8b49\u64da</span>'
        f'<span><strong>{escape(str(entry["open_count"]))}</strong>\u672a\u5b8c\u6210</span>'
        "</div>"
        '<p class="status-line">'
        f'<span class="badge">\u9ad8\u512a\u5148 {escape(str(entry["high_priority_count"]))}</span>'
        f'<span class="badge">\u9700\u95dc\u6ce8 {escape(str(entry["attention_count"]))}</span>'
        f'<span class="badge">\u7121\u6548\u8b49\u64da {escape(str(entry["invalid_evidence_count"]))}</span>'
        f'<span class="badge">stale state {escape(str(entry["stale_count"]))}</span>'
        "</p>"
        f'<p class="status-line"><span class="badge">\u5c08\u5bb6 blockers\uff1a{lens_summary}</span></p>'
        f'<p class="empty">\u6a23\u672c\u80a1\u7968\uff1a{escape(sample_text)}</p>'
        f'<div class="industry-map-actions">{detail_button}{focus_button}</div>'
        "</article>"
    )


def _industry_map_filter_bar(total_entries: int) -> str:
    status_options = [
        ("all", "\u5168\u90e8\u72c0\u614b"),
        ("blocked", "\u6709\u963b\u585e"),
        ("needs-review", "\u9700\u8907\u6838"),
        ("ready", "\u53ef\u95b1\u8b80"),
    ]
    evidence_options = [
        ("all", "\u5168\u90e8\u8b49\u64da"),
        ("missing", "\u7f3a\u4ea4\u4ed8\u8b49\u64da"),
        ("invalid", "\u8b49\u64da\u8def\u5f91\u7121\u6548"),
        ("clean", "\u8b49\u64da\u7121\u963b\u585e"),
    ]
    market_options = [
        ("all", "\u5168\u90e8\u8f2a\u52d5"),
        ("up", "\u8f2a\u52d5\u504f\u5f37"),
        ("down", "\u8f2a\u52d5\u504f\u5f31"),
        ("mixed", "\u8f2a\u52d5\u5206\u6b67"),
        ("flat", "\u8f2a\u52d5\u6301\u5e73"),
        ("missing", "\u5e02\u5834\u8cc7\u6599\u7f3a\u53e3"),
    ]
    lens_labels = dict(REVIEW_ACTION_CATEGORY_LABELS)
    lens_labels["state"] = "\u72c0\u614b\u6a94\u5c08\u5bb6"
    lens_options = [("all", "\u5168\u90e8\u5c08\u5bb6")]
    lens_options.extend((key, _review_label(key, lens_labels)) for key in (*REVIEW_ACTION_CATEGORIES, "state"))
    status_label = "\u72c0\u614b"
    evidence_label = "\u8b49\u64da"
    market_label = "\u5e02\u5834\u8f2a\u52d5"
    lens_label = "\u5c08\u5bb6"

    def select(name: str, label: str, options: list[tuple[str, str]]) -> str:
        option_html = "".join(
            f'<option value="{escape(value)}">{escape(text)}</option>' for value, text in options
        )
        return (
            '<label class="filter-field">'
            f"<span>{escape(label)}</span>"
            f'<select data-industry-map-filter="{escape(name)}">{option_html}</select>'
            "</label>"
        )

    return (
        '<div class="industry-map-controls" data-industry-map-filter-bar="true">'
        f'{select("status", status_label, status_options)}'
        f'{select("evidence", evidence_label, evidence_options)}'
        f'{select("market", market_label, market_options)}'
        f'{select("lens", lens_label, lens_options)}'
        '<label class="filter-field"><span>\u641c\u5c0b</span>'
        '<input data-industry-map-filter="search" type="search" placeholder="\u7522\u696d\u3001\u80a1\u7968\u3001\u4efb\u52d9">'
        "</label>"
        '<button type="button" data-industry-map-filter-reset="true">\u91cd\u8a2d</button>'
        f'<span class="filter-count" data-industry-map-count="true">\u986f\u793a {total_entries} / {total_entries} \u500b\u7522\u696d</span>'
        "</div>"
    )


def _industry_map_detail_template(entry: dict[str, Any], source_path: str, state_path: str, detail_id: str) -> str:
    return (
        '<div class="industry-map-detail-template"'
        f' data-industry-map-detail-template="{escape(detail_id)}" hidden>'
        f"{_industry_map_detail_body(entry, source_path, state_path)}"
        "</div>"
    )


def _industry_map_detail_body(entry: dict[str, Any], source_path: str, state_path: str) -> str:
    category = str(entry["category"])
    status_label = _industry_status_label(entry)
    lens_counts = entry.get("lens_counts", {})
    lens_summary = _count_pairs(lens_counts if isinstance(lens_counts, dict) else {}, REVIEW_ACTION_CATEGORY_LABELS)
    return (
        '<div class="industry-map-detail-header">'
        "<div>"
        '<p class="empty">\u7522\u696d\u5de5\u4f5c\u6d41</p>'
        f"<h3>{escape(category)}</h3>"
        "</div>"
        f'<span class="industry-status-pill">{escape(status_label)}</span>'
        "</div>"
        '<p class="industry-map-next-action" data-industry-map-next-action="true">'
        f"<strong>\u4e0b\u4e00\u500b\u6309\u9215</strong>{escape(_industry_map_next_action(entry))}</p>"
        '<div class="industry-map-metrics">'
        f'<span><strong>{escape(str(entry["blocker_count"]))}</strong>gate blockers</span>'
        f'<span><strong>{escape(str(entry["evidence_missing_count"]))}</strong>\u7f3a\u4ea4\u4ed8\u8b49\u64da</span>'
        f'<span><strong>{escape(str(entry["invalid_evidence_count"]))}</strong>\u7121\u6548\u8b49\u64da</span>'
        f'<span><strong>{escape(str(entry["open_count"]))}</strong>\u672a\u5b8c\u6210\u4efb\u52d9</span>'
        "</div>"
        f'<p class="status-line"><span class="badge">\u5c08\u5bb6\u963b\u585e\uff1a{lens_summary}</span></p>'
        "<h4>\u5e02\u5834\u8f2a\u52d5 overlay</h4>"
        f"{_industry_market_overlay_block(_dict_value(entry.get('market_overlay')))}"
        "<h4>\u7522\u696d\u8b49\u64da\u770b\u677f</h4>"
        f"{_industry_map_evidence_board(entry, source_path, state_path)}"
        "<h4>Top blockers</h4>"
        f"{_industry_map_detail_tasks(entry, source_path)}"
        '<p class="industry-map-note" data-industry-map-non-advice="true">'
        "\u9019\u88e1\u53ea\u662f\u4ea4\u4ed8\u54c1\u8cea\u8207\u8b49\u64da\u6aa2\u67e5\u5de5\u4f5c\u6d41\uff0c\u4e0d\u69cb\u6210\u6295\u8cc7\u5efa\u8b70\u3002"
        "</p>"
    )


def _industry_market_overlay_block(market_overlay: dict[str, Any]) -> str:
    direction = str(market_overlay.get("direction") or "missing")
    status = str(market_overlay.get("status") or "missing")
    label = _market_direction_label(direction)
    stock_count = int(market_overlay.get("stock_count") or 0)
    coverage_count = int(market_overlay.get("coverage_count") or 0)
    missing_count = int(market_overlay.get("missing_count") or max(0, stock_count - coverage_count))
    volume_signals = _list_value(market_overlay.get("volume_signals"))
    notes = _list_value(market_overlay.get("notes"))
    volume_text = ", ".join(volume_signals) if volume_signals else "-"
    note_text = " | ".join(notes) if notes else (
        "\u8acb\u5728 research CSV \u88dc market_return_1d/5d/20d\u3001"
        "market_volume_signal \u6216 market_rotation_note\u3002"
    )
    return (
        '<div class="industry-market-overlay" data-industry-market-overlay="true"'
        f' data-market-direction="{escape(direction)}"'
        f' data-market-status="{escape(status)}">'
        '<div class="industry-market-head">'
        "<strong>\u5e02\u5834\u8f2a\u52d5 overlay</strong>"
        f'<span class="industry-status-pill">{escape(label)}</span>'
        "</div>"
        '<div class="industry-map-metrics">'
        f'<span><strong>{escape(_market_return_text(market_overlay.get("average_return_20d")))}</strong>20D</span>'
        f'<span><strong>{escape(_market_return_text(market_overlay.get("average_return_5d")))}</strong>5D</span>'
        f'<span><strong>{escape(_market_return_text(market_overlay.get("average_return_1d")))}</strong>1D</span>'
        f'<span><strong>{escape(str(coverage_count))}/{escape(str(stock_count))}</strong>\u5e02\u5834\u8cc7\u6599</span>'
        "</div>"
        f'<p class="industry-market-note"><strong>\u91cf\u80fd\uff1a</strong>{escape(volume_text)}</p>'
        f'<p class="industry-market-note"><strong>\u8f2a\u52d5\u5099\u8a3b\uff1a</strong>{escape(note_text)}</p>'
        f'<p class="industry-market-note"><strong>\u7f3a\u53e3\uff1a</strong>{escape(str(missing_count))} \u6a94\u5c1a\u672a\u63d0\u4f9b\u5e02\u5834 overlay \u8cc7\u6599\u3002</p>'
        "</div>"
    )


def _industry_map_evidence_board(entry: dict[str, Any], source_path: str, state_path: str) -> str:
    rows = entry.get("evidence_rows", [])
    if not isinstance(rows, list) or not rows:
        return '<p class="empty" data-industry-evidence-board="true">\u6c92\u6709\u53ef\u986f\u793a\u7684\u80a1\u7968\u8b49\u64da\u72c0\u614b\u3002</p>'
    return (
        '<div class="industry-evidence-board" data-industry-evidence-board="true">'
        f"{''.join(_industry_map_evidence_row(row, source_path, state_path) for row in rows[:8] if isinstance(row, dict))}"
        "</div>"
    )


def _industry_map_evidence_row(row: dict[str, Any], source_path: str, state_path: str) -> str:
    stock_id = str(row.get("stock_id") or "-")
    company_name = str(row.get("company_name") or "")
    stock_label = stock_id if not company_name else f"{stock_id} {company_name}"
    status = str(row.get("status") or "ready")
    status_label = _industry_evidence_status_label(status)
    missing_fields = _list_value(row.get("missing_fields"))
    missing_text = ", ".join(missing_fields) if missing_fields else "-"
    suggested_paths = _list_value(row.get("suggested_paths"))
    suggested_path = suggested_paths[0] if suggested_paths else "-"
    next_copy = _industry_evidence_next_step(row)
    focus_button = _industry_map_evidence_focus_button(row, source_path)
    action_buttons = _industry_map_evidence_action_buttons(row, source_path, state_path)
    return (
        '<div class="industry-evidence-row" data-industry-evidence-row="true"'
        f' data-industry-evidence-status="{escape(status)}"'
        f' data-industry-evidence-stock-id="{escape(stock_id)}"'
        f' data-industry-evidence-suggested-path="{escape(suggested_path)}"'
        ' data-expert-console-task="true">'
        '<div class="industry-evidence-head">'
        f"<strong>{escape(stock_label)}</strong>"
        f'<span class="industry-status-pill">{escape(status_label)}</span>'
        "</div>"
        '<p class="status-line">'
        f'<span class="badge">\u9700\u8b49\u64da {escape(str(row.get("evidence_required_count", 0)))}</span>'
        f'<span class="badge">\u5df2\u586b {escape(str(row.get("evidence_filled_count", 0)))}</span>'
        f'<span class="badge">\u5f85\u88dc {escape(str(row.get("missing_evidence_count", 0)))}</span>'
        f'<span class="badge">\u7121\u6548 {escape(str(row.get("invalid_evidence_count", 0)))}</span>'
        f'<span class="badge">\u672a\u5b8c\u6210 {escape(str(row.get("open_count", 0)))}</span>'
        "</p>"
        f'<p class="industry-evidence-next"><strong>\u4e0b\u4e00\u6b65\uff1a</strong>{escape(next_copy)}</p>'
        f'<p class="industry-evidence-path"><strong>\u7f3a\u6b04\u4f4d\uff1a</strong>{escape(missing_text)}</p>'
        f'<p class="industry-evidence-path"><strong>\u5efa\u8b70\u8b49\u64da\u6a94\uff1a</strong>{escape(suggested_path)}</p>'
        f'<div class="industry-map-actions">{focus_button}{action_buttons}</div>'
        '<p class="expert-console-result" data-expert-console-task-result="true">\u8655\u7406\u7d50\u679c\uff1a\u5c1a\u672a\u8655\u7406</p>'
        "</div>"
    )


def _industry_map_evidence_focus_button(row: dict[str, Any], source_path: str) -> str:
    stock_id = str(row.get("stock_id") or "").strip()
    action_id = str(row.get("focus_action_id") or "").strip()
    if not stock_id or stock_id == "-" or not action_id:
        return ""
    return (
        '<button type="button" class="expert-console-next" data-industry-map-focus-stock="'
        f'{escape(stock_id)}"'
        f' data-industry-map-focus-action="{escape(action_id)}"'
        f' data-industry-map-focus-category="{escape(str(row.get("focus_category") or "all"))}"'
        f' data-review-actions-source-path="{escape(source_path)}">\u524d\u5f80\u5be9\u67e5\u52d5\u4f5c</button>'
    )


def _industry_map_evidence_action_buttons(row: dict[str, Any], source_path: str, state_path: str) -> str:
    stock_id = str(row.get("stock_id") or "").strip()
    action_id = str(row.get("focus_action_id") or "").strip()
    if not stock_id or stock_id == "-" or not action_id:
        return ""
    action = {
        "stock_id": stock_id,
        "action_id": action_id,
        "category": str(row.get("focus_category") or "all"),
        "note": str(row.get("focus_note") or ""),
        "reviewer": str(row.get("focus_reviewer") or ""),
        "evidence_url": str(row.get("focus_evidence_url") or ""),
        "updated_at": str(row.get("focus_updated_at") or ""),
    }
    done_label = "\u88dc\u8b49\u4e26\u6a19\u8a18\u5b8c\u6210"
    deferred_label = "\u7a0d\u5f8c\u88dc\u8b49"
    return (
        f'{_expert_console_action_button(action, source_path, state_path, "done", done_label)}'
        f'{_expert_console_action_button(action, source_path, state_path, "deferred", deferred_label)}'
    )


def _industry_evidence_status_label(status: str) -> str:
    labels = {
        "invalid": "\u8b49\u64da\u7121\u6548",
        "missing": "\u5f85\u88dc\u8b49\u64da",
        "open": "\u5f85\u8655\u7406\u52d5\u4f5c",
        "ready": "\u8b49\u64da\u53ef\u4ea4\u4ed8",
    }
    return labels.get(status, status or "-")


def _industry_evidence_next_step(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "")
    if status == "invalid":
        return "\u4fee\u6b63 evidence URL \u6216\u5efa\u7acb\u5efa\u8b70\u8b49\u64da\u6a94\u5f8c\uff0c\u91cd\u8dd1 handoff gate\u3002"
    if status == "missing":
        return "\u88dc note\u3001reviewer\u3001evidence URL\uff0c\u7136\u5f8c\u5728 dashboard \u6216 CLI \u6a19\u8a18\u8655\u7406\u7d50\u679c\u3002"
    if status == "open":
        return "\u5148\u8655\u7406\u672a\u5b8c\u6210\u7684 Review Actions\uff0c\u518d\u88dc\u4ea4\u4ed8\u8b49\u64da\u3002"
    if int(row.get("evidence_required_count") or 0) == 0:
        return "\u76ee\u524d\u6c92\u6709\u9700\u88dc\u7684\u4ea4\u4ed8\u8b49\u64da\u52d5\u4f5c\u3002"
    return "\u8b49\u64da\u6b04\u4f4d\u5df2\u586b\uff1b\u4e0b\u4e00\u6b65\u662f\u4eba\u5de5\u95b1\u8b80\u8207\u7c3d\u6838\u3002"


def _industry_map_detail_tasks(entry: dict[str, Any], source_path: str) -> str:
    blockers = entry.get("top_blockers", [])
    if not isinstance(blockers, list) or not blockers:
        return '<p class="empty">\u76ee\u524d\u6c92\u6709 gate blocker\uff0c\u53ef\u9032\u5165\u4eba\u5de5\u95b1\u8b80\u8207\u7c3d\u6838\u3002</p>'

    rows: list[str] = []
    for blocker in blockers[:3]:
        if not isinstance(blocker, dict):
            continue
        stock_id = str(blocker.get("stock_id") or "-")
        company_name = str(blocker.get("company_name") or "")
        stock_label = stock_id if not company_name else f"{stock_id} {company_name}"
        category = str(blocker.get("category") or "")
        severity = str(blocker.get("severity") or "")
        expert_label = str(blocker.get("expert_label") or _review_label(category, REVIEW_ACTION_CATEGORY_LABELS))
        message = str(blocker.get("message") or "")
        next_step = str(blocker.get("next_step") or "")
        rows.append(
            '<li class="industry-map-detail-task" data-industry-map-task="true">'
            '<div class="industry-map-task-head">'
            f"<strong>{escape(stock_label)}</strong>"
            f'<span class="badge">{escape(expert_label)}</span>'
            f'<span class="badge">{escape(_review_label(severity, REVIEW_ACTION_SEVERITY_LABELS))}</span>'
            "</div>"
            f"<p>{escape(message)}</p>"
            f"<p><strong>\u5efa\u8b70\u52d5\u4f5c\uff1a</strong>{escape(next_step)}</p>"
            '<div class="industry-map-actions">'
            f'{_industry_map_blocker_focus_button(blocker, source_path)}'
            "</div>"
            "</li>"
        )
    if not rows:
        return '<p class="empty">\u76ee\u524d\u6c92\u6709\u53ef\u986f\u793a\u7684 blocker\u3002</p>'
    return f'<ol class="industry-map-detail-list">{"".join(rows)}</ol>'


def _industry_map_blocker_focus_button(blocker: dict[str, Any], source_path: str) -> str:
    focus_available = str(blocker.get("focus_available", "true")).lower() == "true"
    stock_id = str(blocker.get("stock_id") or "").strip()
    if not focus_available or not stock_id or stock_id == "-":
        return '<span class="empty">\u9700\u5148\u91cd\u65b0\u7522\u751f research summary \u6216\u4fee\u6b63 state sidecar\u3002</span>'
    return (
        '<button type="button" class="expert-console-next" data-industry-map-focus-stock="'
        f'{escape(stock_id)}"'
        f' data-industry-map-focus-action="{escape(str(blocker.get("action_id") or ""))}"'
        f' data-industry-map-focus-category="{escape(str(blocker.get("category") or "all"))}"'
        f' data-review-actions-source-path="{escape(source_path)}">\u524d\u5f80\u5be9\u67e5\u52d5\u4f5c</button>'
    )


def _industry_map_evidence_status(entry: dict[str, Any]) -> str:
    if int(entry["invalid_evidence_count"]) > 0:
        return "invalid"
    if int(entry["evidence_missing_count"]) > 0:
        return "missing"
    return "clean"


def _industry_map_next_action(entry: dict[str, Any]) -> str:
    if int(entry["evidence_missing_count"]) > 0:
        return "\u5148\u88dc\u4ea4\u4ed8\u8b49\u64da\u6b04\u4f4d note\u3001reviewer\u3001evidence URL\u3002"
    if int(entry["invalid_evidence_count"]) > 0:
        return "\u5148\u4fee\u6b63\u7121\u6548 evidence \u8def\u5f91\u6216\u6539\u7528\u53ef\u958b\u555f\u7684 URL\u3002"
    if int(entry["stale_count"]) > 0:
        return "\u5148\u6e05\u7406 stale review-action state\uff0c\u518d\u91cd\u8dd1 handoff gate\u3002"
    if int(entry["blocker_count"]) > 0 or int(entry["open_count"]) > 0:
        return "\u5148\u8655\u7406 Top blockers\uff0c\u518d\u56de\u5230 Review Actions \u78ba\u8a8d\u72c0\u614b\u3002"
    if str(entry["status"]) == "needs-review":
        return "\u5148\u5b8c\u6210\u4eba\u5de5\u8907\u6838\uff0c\u518d\u7522\u751f Evidence Pack\u3002"
    return "\u53ef\u9032\u5165\u4eba\u5de5\u95b1\u8b80\u8207\u7c3d\u6838\uff1b\u8acb\u4fdd\u6301\u975e\u6295\u8cc7\u5efa\u8b70\u908a\u754c\u3002"


def _industry_map_search_text(entry: dict[str, Any]) -> str:
    parts = [
        str(entry.get("category") or ""),
        str(entry.get("status") or ""),
        _industry_status_label(entry),
        _industry_blocker_copy(entry),
        _industry_map_next_action(entry),
    ]
    parts.extend(_list_value(entry.get("sample_stocks")))
    market_overlay = _dict_value(entry.get("market_overlay"))
    if market_overlay:
        parts.append(str(market_overlay.get("status") or ""))
        parts.append(str(market_overlay.get("direction") or ""))
        parts.append(_market_direction_label(str(market_overlay.get("direction") or "")))
        for key in ("average_return_1d", "average_return_5d", "average_return_20d"):
            parts.append(_market_return_text(market_overlay.get(key)))
        parts.extend(_list_value(market_overlay.get("volume_signals")))
        parts.extend(_list_value(market_overlay.get("notes")))
    lens_counts = entry.get("lens_counts", {})
    if isinstance(lens_counts, dict):
        for lens in lens_counts:
            parts.append(str(lens))
            parts.append(_review_label(str(lens), REVIEW_ACTION_CATEGORY_LABELS))
    blockers = entry.get("top_blockers", [])
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, dict):
                continue
            for key in ("kind", "stock_id", "company_name", "category", "expert_label", "action_id", "message", "next_step"):
                parts.append(str(blocker.get(key) or ""))
    evidence_rows = entry.get("evidence_rows", [])
    if isinstance(evidence_rows, list):
        for row in evidence_rows:
            if not isinstance(row, dict):
                continue
            for key in ("stock_id", "company_name", "status", "focus_action_id"):
                parts.append(str(row.get(key) or ""))
            parts.extend(_list_value(row.get("missing_fields")))
            parts.extend(_list_value(row.get("suggested_paths")))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _industry_map_card_aria(entry: dict[str, Any]) -> str:
    return f"\u67e5\u770b {entry['category']} \u7522\u696d\u5de5\u4f5c\u6d41\u8a73\u60c5"


def _industry_status_label(entry: dict[str, Any]) -> str:
    if entry["status"] == "blocked":
        if int(entry["evidence_missing_count"]) > 0:
            return "交付阻塞：待補證據"
        return "交付阻塞高"
    if entry["status"] == "needs-review":
        return "需人工複核"
    return "交付可讀"


def _industry_blocker_copy(entry: dict[str, Any]) -> str:
    category = str(entry["category"])
    if int(entry["blocker_count"]) > 0:
        lens_counts = entry.get("lens_counts", {})
        lens_text = _industry_lens_text(lens_counts if isinstance(lens_counts, dict) else {})
        return f"{category} 研究包目前較不適合交付，主因：{lens_text}。"
    if int(entry["attention_count"]) > 0:
        return f"{category} 有需關注研究項目，適合先完成人工複核再交付。"
    return f"{category} 目前沒有 gate 阻塞；下一步是人工閱讀與簽核。"


def _industry_lens_text(counts: dict[str, Any]) -> str:
    if not counts:
        return "-"
    pairs = sorted(((str(key), str(value)) for key, value in counts.items()), key=lambda item: item[0])
    return ", ".join(f"{_review_label(key, REVIEW_ACTION_CATEGORY_LABELS)}: {value}" for key, value in pairs)


def _industry_sample_stocks(stocks: dict[str, str]) -> list[str]:
    samples = []
    for stock_id, company_name in sorted(stocks.items())[:5]:
        label = stock_id if not company_name else f"{stock_id} {company_name}"
        samples.append(label)
    return samples


def _industry_map_focus(entry: dict[str, Any]) -> dict[str, str]:
    blockers = entry.get("top_blockers", [])
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, dict):
                continue
            stock_id = str(blocker.get("stock_id") or "").strip()
            if not stock_id or stock_id == "-":
                continue
            return {
                "stock_id": stock_id,
                "action_id": str(blocker.get("action_id") or ""),
                "category": str(blocker.get("category") or "all"),
            }
    samples = _list_value(entry.get("sample_stocks"))
    if samples:
        return {"stock_id": samples[0].split()[0], "action_id": "", "category": "all"}
    return {}


def _industry_map_top_lens(entries: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for entry in entries:
        lens_counts = entry.get("lens_counts", {})
        if not isinstance(lens_counts, dict):
            continue
        for lens, value in lens_counts.items():
            counts[str(lens)] = counts.get(str(lens), 0) + int(value)
    if not counts:
        return "-"
    lens, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return f"{_review_label(lens, REVIEW_ACTION_CATEGORY_LABELS)} {count} 件"


def _industry_map_market_summary(entries: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for entry in entries:
        overlay = _dict_value(entry.get("market_overlay"))
        direction = str(overlay.get("direction") or "missing")
        counts[direction] = counts.get(direction, 0) + 1
    if not counts:
        return "\u5c1a\u672a\u63d0\u4f9b\u5e02\u5834 overlay \u8cc7\u6599"
    order = ["up", "down", "mixed", "flat", "missing"]
    return " / ".join(
        f"{_market_direction_label(direction)} {counts[direction]}"
        for direction in order
        if counts.get(direction, 0) > 0
    )


def _research_summary_section(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return '<section><h2>研究工作台</h2><p class="empty">尚無 research summary</p></section>'

    sections: list[str] = []
    for summary in summaries:
        if summary.get("error"):
            sections.append(
                "<div>"
                f"<p>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</p>"
                f'<p class="empty">Research summary error: {escape(str(summary.get("error")))}</p>'
                "</div>"
            )
            continue

        counts = summary.get("counts", {})
        counts = counts if isinstance(counts, dict) else {}
        total = counts.get("total", 0)
        needs_attention = counts.get("needs_attention", 0)
        by_state = _dict_value(counts.get("by_state"))
        by_priority = _dict_value(counts.get("by_priority"))
        items = summary.get("items", [])
        item_rows = _research_item_rows(items if isinstance(items, list) else [])
        related_links = _research_related_links(summary)
        traceability = _research_traceability_line(summary)
        universe_review = _universe_review_section(summary)
        sections.append(
            "<div>"
            f"<p>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</p>"
            f"{traceability}"
            f"{related_links}"
            '<p class="status-line">'
            f'<span class="badge">total research items: {escape(str(total))}</span>'
            f'<span class="badge error">needs attention: {escape(str(needs_attention))}</span>'
            f'<span class="badge">state counts: {_count_pairs(by_state)}</span>'
            f'<span class="badge">priority counts: {_count_pairs(by_priority)}</span>'
            "</p>"
            f"{universe_review}"
            "<table><thead><tr><th>stock_id</th><th>company_name</th><th>priority</th><th>research_state</th>"
            "<th>workflow_status</th><th>reliability_status</th><th>attention_reasons</th></tr></thead>"
            f"<tbody>{item_rows}</tbody></table>"
            "</div>"
        )
    return f"<section><h2>研究工作台</h2>{''.join(sections)}</section>"


def _universe_review_section(summary: dict[str, Any]) -> str:
    review = summary.get("universe_review")
    if not isinstance(review, dict):
        return ""

    counts = _dict_value(review.get("counts"))
    category_counts = _dict_value(review.get("category_counts"))
    state_counts = _dict_value(review.get("state_counts"))
    priority_counts = _dict_value(review.get("priority_counts"))
    review_buckets = _dict_value(review.get("review_buckets"))
    queue = review.get("attention_queue", [])
    queue_items = queue if isinstance(queue, list) else []

    bucket_badges = []
    for bucket, stock_ids in sorted(review_buckets.items()):
        ids = _list_value(stock_ids)
        bucket_badges.append(
            f'<span class="badge">{escape(str(bucket).replace("_", " "))}: {escape(", ".join(ids) or "-")}</span>'
        )
    bucket_html = "".join(bucket_badges) or '<span class="badge">review buckets: -</span>'

    return (
        '<div class="tool">'
        "<h3>研究池檢視</h3>"
        f'<p class="status-line">{_universe_count_badges(counts)}</p>'
        '<p class="status-line">'
        f'<span class="badge">category counts: {_count_pairs(category_counts)}</span>'
        f'<span class="badge">state counts: {_count_pairs(state_counts)}</span>'
        f'<span class="badge">priority counts: {_count_pairs(priority_counts)}</span>'
        "</p>"
        f'<p class="status-line">{bucket_html}</p>'
        "<table><thead><tr><th>stock_id</th><th>company_name</th><th>category</th><th>priority</th>"
        "<th>research_state</th><th>workflow_status</th><th>reliability_status</th><th>attention_reasons</th></tr></thead>"
        f"<tbody>{_universe_attention_rows(queue_items)}</tbody></table>"
        "</div>"
    )


def _universe_attention_rows(queue: list[Any]) -> str:
    rows: list[str] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        reasons = item.get("attention_reasons", [])
        if isinstance(reasons, list):
            reasons_text = ", ".join(str(reason) for reason in reasons)
        else:
            reasons_text = str(reasons)
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('stock_id', '-')))}</td>"
            f"<td>{escape(str(item.get('company_name', '')))}</td>"
            f"<td>{escape(str(item.get('category', '')))}</td>"
            f"<td>{escape(str(item.get('priority', '')))}</td>"
            f"<td>{escape(str(item.get('research_state', '')))}</td>"
            f"<td>{escape(str(item.get('workflow_status', '')))}</td>"
            f"<td>{escape(str(item.get('reliability_status', '')))}</td>"
            f"<td>{escape(reasons_text)}</td>"
            "</tr>"
        )
    return "".join(rows) or _empty_row(8, "No universe attention queue items")


def _review_actions_section(research_summaries: list[dict[str, Any]], *, action_api_enabled: bool = False) -> str:
    sections: list[str] = []
    for summary in research_summaries:
        if not isinstance(summary, dict) or summary.get("error"):
            continue
        action_summary = _dict_value(summary.get("review_action_summary"))
        action_queue = summary.get("review_action_queue", [])
        if not action_summary and not action_queue:
            continue
        source_queue = action_queue if isinstance(action_queue, list) else []
        state = _dict_value(summary.get("review_action_state"))
        overlaid_queue = apply_review_action_state(source_queue, state)
        state_report = build_review_action_state_report(source_queue, state)
        state_path = _review_action_state_path(summary)
        rows = _review_action_rows(overlaid_queue, state_path)
        total_rows = _review_action_row_count(overlaid_queue)
        by_status = _dict_value(state_report.get("by_status"))
        state_warning = str(summary.get("review_action_state_warning") or "")
        source_path = str(summary.get("path", ""))
        sections.append(
            '<div data-review-actions-section="true"'
            f' data-review-actions-source-path="{escape(source_path)}">'
            f"<p>{_link(source_path, Path(source_path).name)}</p>"
            '<p class="status-line">'
            f'<span class="badge" data-review-action-open-total="true">待處理 {escape(str(by_status.get("open", 0)))} / 全部 {escape(str(total_rows))}</span>'
            f'<span class="badge">重要性：{_count_pairs(_dict_value(action_summary.get("by_severity")), REVIEW_ACTION_SEVERITY_LABELS)}</span>'
            f'<span class="badge">類別：{_count_pairs(_dict_value(action_summary.get("by_category")), REVIEW_ACTION_CATEGORY_LABELS)}</span>'
            f'<span class="badge" data-review-action-state-health="true">{_review_action_status_pairs(by_status)}</span>'
            f'<span class="badge" data-review-action-stale-count="true" data-review-action-stale-count-value="{escape(str(state_report.get("stale_count", 0)))}">過期狀態 {escape(str(state_report.get("stale_count", 0)))}</span>'
            f'<span class="badge" data-review-action-last-updated="true">最後更新：{escape(str(state_report.get("last_updated", "-")))}</span>'
            "</p>"
            f"{_review_action_state_warning(state_warning)}"
            f"{_review_action_filter_bar(total_rows)}"
            f"{_review_action_bulk_tools()}"
            f"{_review_action_mode_notice(action_api_enabled)}"
            '<p class="status-line"><span class="badge" data-review-action-copy-status="true">請選擇每筆事項的處理結果</span></p>'
            '<details class="review-action-api-result" data-review-action-api-result="true" aria-live="polite">'
            '<summary>更新結果</summary>'
            '<div class="review-action-result-summary" data-review-action-result-summary="true"></div>'
            '<details><summary>技術詳細資訊</summary>'
            '<pre class="review-action-api-output" data-review-action-api-output="true"></pre>'
            '</details>'
            '</details>'
            '<table><thead><tr><th class="review-action-select-cell">選取</th><th>股票代號</th><th>優先度</th><th>狀態</th><th>嚴重度</th><th>類別</th><th>待處理事項</th><th>操作</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
            "</div>"
        )
    if not sections:
        return ""
    return f"<section><h2>審查動作</h2>{''.join(sections)}</section>"


def _review_action_row_count(action_queue: list[Any]) -> int:
    count = 0
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if isinstance(actions, list):
            count += sum(1 for action in actions if isinstance(action, dict))
    return count


def _review_action_rows(action_queue: list[Any], state_path: str = "review_action_state.json") -> str:
    rows: list[str] = []
    for item in action_queue:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "-")
        company_name = str(item.get("company_name") or "")
        priority = str(item.get("priority") or "-")
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            severity = str(action.get("severity") or "-")
            category = str(action.get("category") or "-")
            status = str(action.get("status") or "open")
            action_id = str(action.get("id") or "")
            message = str(action.get("message") or "-")
            note = str(action.get("note") or "").strip()
            reviewer = str(action.get("reviewer") or "").strip()
            evidence_url = str(action.get("evidence_url") or "").strip()
            updated_at = str(action.get("updated_at") or "").strip()
            evidence_required = requires_handoff_evidence(action_id)
            priority_label = _review_label(priority, REVIEW_ACTION_PRIORITY_LABELS)
            status_label = _review_label(status, REVIEW_ACTION_STATUS_LABELS)
            severity_label = _review_label(severity, REVIEW_ACTION_SEVERITY_LABELS)
            category_label = _review_label(category, REVIEW_ACTION_CATEGORY_LABELS)
            expert_label = _expert_agent_label(category)
            user_message = _review_action_user_message(action, message)
            search_text = _review_metadata_text(
                stock_id,
                priority,
                priority_label,
                status,
                status_label,
                severity,
                severity_label,
                category,
                category_label,
                message,
                user_message,
                note,
                reviewer,
                evidence_url,
                updated_at,
                "evidence required" if evidence_required else "",
            )
            rows.append(
                '<tr data-review-action-row="true"'
                f' data-stock-id="{escape(stock_id)}"'
                f' data-company-name="{escape(company_name)}"'
                f' data-priority="{escape(priority)}"'
                f' data-priority-label="{escape(priority_label)}"'
                f' data-status="{escape(status)}"'
                f' data-severity="{escape(severity)}"'
                f' data-severity-label="{escape(severity_label)}"'
                f' data-category="{escape(category)}"'
                f' data-category-label="{escape(category_label)}"'
                f' data-expert-label="{escape(expert_label)}"'
                f' data-action-id="{escape(action_id)}"'
                f' data-action-message="{escape(user_message)}"'
                f' data-note="{escape(note)}"'
                f' data-reviewer="{escape(reviewer)}"'
                f' data-evidence-url="{escape(evidence_url)}"'
                f' data-updated-at="{escape(updated_at)}"'
                f' data-evidence-required="{str(evidence_required).lower()}"'
                f' data-search-text="{escape(search_text)}">'
                '<td class="review-action-select-cell"><input type="checkbox" data-review-action-select-row="true" aria-label="選取審查動作"></td>'
                f"<td>{escape(stock_id)}</td>"
                f"<td>{escape(priority_label)}</td>"
                f'<td><span class="review-action-status" data-review-action-status-cell="true">{escape(status_label)}</span></td>'
                f"<td>{escape(severity_label)}</td>"
                f"<td>{escape(category_label)}</td>"
                f"<td>{escape(user_message)}{_review_action_state_metadata(action, evidence_required=evidence_required)}</td>"
                f"<td>{_review_action_command_cell(state_path, stock_id, action_id, evidence_required=evidence_required)}</td>"
                "</tr>"
            )
    return "".join(rows) or _empty_row(8, "沒有審查動作")


def _universe_count_badges(counts: dict[str, Any]) -> str:
    if not counts:
        return '<span class="badge">universe counts: -</span>'
    return "".join(
        f'<span class="badge">{escape(str(key).replace("_", " "))}: {escape(str(value))}</span>'
        for key, value in sorted(counts.items())
    )


def _research_related_links(summary: dict[str, Any]) -> str:
    links = []
    workflow_summary_path = str(summary.get("workflow_summary_path") or "")
    if workflow_summary_path:
        links.append(_link(workflow_summary_path, "workflow_summary.json"))

    workflow_paths = summary.get("workflow_paths", {})
    if isinstance(workflow_paths, dict):
        dashboard_path = str(workflow_paths.get("dashboard") or "")
        if dashboard_path:
            links.append(_link(dashboard_path, Path(dashboard_path).name or "dashboard"))
        batch_summary = str(workflow_paths.get("batch_summary") or "")
        if batch_summary:
            links.append(_link(batch_summary, Path(batch_summary).name or "batch_summary"))
        valuation_summary = str(workflow_paths.get("valuation_batch_summary") or "")
        if valuation_summary:
            links.append(_link(valuation_summary, Path(valuation_summary).name or "valuation_batch_summary"))
        comparison = workflow_paths.get("comparison", {})
        if isinstance(comparison, dict):
            comparison_html = str(comparison.get("html") or "")
            if comparison_html:
                links.append(_link(comparison_html, Path(comparison_html).name or "comparison"))

    if not links:
        return ""
    return f'<p class="status-line">{" ".join(links)}</p>'


def _research_traceability_line(summary: dict[str, Any]) -> str:
    labels: list[str] = []
    run_id = _run_id(summary)
    if run_id:
        labels.append(f'<span class="badge">run id: {escape(run_id)}</span>')

    dependency_path = _workflow_dependency(summary)
    if dependency_path:
        labels.append(
            '<span class="badge">'
            f'workflow dependency: {_link(dependency_path, Path(dependency_path).name or dependency_path)}'
            "</span>"
        )

    if not labels:
        return ""
    return f'<p class="status-line">{" ".join(labels)}</p>'


def _research_item_rows(items: list[Any]) -> str:
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reasons = item.get("attention_reasons", [])
        if isinstance(reasons, list):
            reasons_text = ", ".join(str(reason) for reason in reasons)
        else:
            reasons_text = str(reasons)
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('stock_id', '-')))}</td>"
            f"<td>{escape(str(item.get('company_name', '')))}</td>"
            f"<td>{escape(str(item.get('priority', '')))}</td>"
            f"<td>{escape(str(item.get('research_state', '')))}</td>"
            f"<td>{escape(str(item.get('workflow_status', '')))}</td>"
            f"<td>{escape(str(item.get('reliability_status', '')))}</td>"
            f"<td>{escape(reasons_text)}</td>"
            "</tr>"
        )
    return "".join(rows) or _empty_row(7, "尚無 research items")


def _memo_rows(memo_outputs: list[dict[str, Any]]) -> str:
    if not memo_outputs:
        return _empty_row(4, "尚無 research memo outputs")
    return "".join(
        "<tr>"
        f"<td>{escape(str(output.get('stock_id', '-')))}</td>"
        f"<td>{_link(str(output.get('markdown_path', '')), Path(str(output.get('markdown_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('html_path', '')), Path(str(output.get('html_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('summary_path', '')), Path(str(output.get('summary_path', ''))).name)}</td>"
        "</tr>"
        for output in memo_outputs
    )


def _pack_rows(pack_outputs: list[dict[str, Any]]) -> str:
    if not pack_outputs:
        return _empty_row(3, "No research pack outputs")
    return "".join(
        "<tr>"
        f"<td>{_link(str(output.get('markdown_path', '')), Path(str(output.get('markdown_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('html_path', '')), Path(str(output.get('html_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('summary_path', '')), Path(str(output.get('summary_path', ''))).name)}</td>"
        "</tr>"
        for output in pack_outputs
    )


def _handoff_pack_rows(pack_outputs: list[dict[str, Any]]) -> str:
    if not pack_outputs:
        return _empty_row(8, "No handoff evidence pack outputs")
    return "".join(
        "<tr>"
        f"<td>{escape(str(output.get('gate_status', '-')))}</td>"
        f"<td>{escape(str(output.get('ready', '-')))}</td>"
        f"<td>{escape(str(output.get('blocker_count', '-')))}</td>"
        f"<td>{escape(str(output.get('evidence_missing_count', '-')))}</td>"
        f"<td>{escape(str(output.get('invalid_evidence_count', '-')))}</td>"
        f"<td>{_link(str(output.get('markdown_path', '')), Path(str(output.get('markdown_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('html_path', '')), Path(str(output.get('html_path', ''))).name)}</td>"
        f"<td>{_link(str(output.get('summary_path', '')), Path(str(output.get('summary_path', ''))).name)}</td>"
        "</tr>"
        for output in pack_outputs
    )


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _review_label(value: str, labels: dict[str, str]) -> str:
    return labels.get(value, value.replace("_", " ") if value else "-")


def _count_pairs(counts: dict[str, Any], labels: dict[str, str] | None = None) -> str:
    if not counts:
        return "-"
    pairs = sorted(((str(key), str(value)) for key, value in counts.items()), key=lambda item: item[0])
    return ", ".join(f"{escape(_review_label(key, labels or {}))}: {escape(value)}" for key, value in pairs)


def _review_action_status_pairs(counts: dict[str, Any]) -> str:
    if not counts:
        return "-"
    return " / ".join(
        f"{REVIEW_ACTION_STATUS_LABELS.get(status, status)} {escape(str(counts.get(status, 0)))}"
        for status in ("done", "deferred", "ignored")
    )


def _review_filter_select(
    label: str,
    name: str,
    options: tuple[str, ...],
    labels: dict[str, str] | None = None,
    default: str = "all",
) -> str:
    option_html = [f'<option value="all"{_selected_attr(default, "all")}>全部</option>']
    option_html.extend(
        f'<option value="{escape(option)}"{_selected_attr(default, option)}>{escape(_review_label(option, labels or {}))}</option>'
        for option in options
    )
    return (
        '<label class="filter-field">'
        f"<span>{escape(label)}</span>"
        f'<select data-review-filter="{escape(name)}">{"".join(option_html)}</select>'
        "</label>"
    )


def _selected_attr(selected: str, value: str) -> str:
    return ' selected' if selected == value else ""


def _review_action_filter_bar(total_rows: int) -> str:
    return (
        '<div class="review-action-filters" data-review-filter-bar="true">'
        f'{_review_filter_select("重要性", "severity", REVIEW_ACTION_SEVERITIES, REVIEW_ACTION_SEVERITY_LABELS)}'
        f'{_review_filter_select("類別", "category", REVIEW_ACTION_CATEGORIES, REVIEW_ACTION_CATEGORY_LABELS)}'
        f'{_review_filter_select("優先度", "priority", REVIEW_ACTION_PRIORITIES, REVIEW_ACTION_PRIORITY_LABELS)}'
        f'{_review_filter_select("狀態", "status", REVIEW_ACTION_STATUSES, REVIEW_ACTION_STATUS_LABELS, default="open")}'
        '<label class="filter-field"><span>搜尋</span>'
        '<input data-review-filter="search" type="search" placeholder="股票、類別、動作">'
        "</label>"
        '<button type="button" data-review-filter-reset="true">重設</button>'
        f'<span class="filter-count" data-review-action-count="true">顯示待處理 / 全部 {total_rows} 件</span>'
        "</div>"
    )


def _review_action_bulk_tools() -> str:
    return (
        '<div class="review-action-bulk-tools" data-review-action-bulk-tools="true">'
        '<label><input type="checkbox" data-review-action-select-visible="true">選取目前顯示</label>'
        '<button type="button" data-review-action-bulk-status="done">批次標記完成</button>'
        '<button type="button" data-review-action-bulk-status="deferred">批次稍後處理</button>'
        '<span class="review-action-bulk-count" data-review-action-bulk-count="true">已選取 0 筆</span>'
        "</div>"
    )


def _review_action_mode_notice(action_api_enabled: bool) -> str:
    if action_api_enabled:
        message = (
            "\u76ee\u524d\u662f API \u6a21\u5f0f\uff1a\u6309\u9215\u6703\u66f4\u65b0 review_action_state.json\uff0c"
            "\u4e26\u5728\u4e0b\u65b9\u8f38\u51fa\u7d50\u679c\u3002"
        )
    else:
        message = (
            "\u76ee\u524d\u662f\u975c\u614b\u6a21\u5f0f\uff1a\u6309\u9215\u6703\u8907\u88fd CLI \u6307\u4ee4\uff0c"
            "\u9700\u5728 PowerShell \u57f7\u884c\u5f8c\u624d\u6703\u66f4\u65b0\u72c0\u614b\u3002"
        )
    return f'<p class="status-line"><span class="badge" data-review-action-mode-notice="true">{escape(message)}</span></p>'


def _review_metadata_text(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        text = str(value or "").strip().lower()
        for punctuation in (":", ".", ",", ";"):
            text = text.replace(punctuation, " ")
        if text:
            parts.append(" ".join(text.split()))
    return " ".join(parts)


def _review_action_user_message(action: dict[str, Any], fallback: str) -> str:
    action_id = str(action.get("id") or "")
    if action_id.startswith("source-audit"):
        return "來源檢查需要確認：請查看來源稽核區塊，確認資料來源與離線/過期狀態可接受後按「標記完成」。"
    if action_id.startswith("workflow"):
        return "工作流程需要處理：請查看 Workflow 狀態，修正失敗或確認 fallback 輸出可用後按「標記完成」。"
    if action_id.startswith("reliability"):
        return "資料可信度有警示：請查看資料可信度區塊，確認可交接後按「標記完成」。"
    if action_id == "valuation-unavailable":
        return "估值輸出缺失：請補跑估值或確認本次不需要估值，確認後按「標記完成」。"
    if action_id == "research-state-blocked":
        return "研究項目被封鎖：請解除 blocker 或補齊原因後按「標記完成」。"
    if action_id == "research-state-new":
        return "新研究項目尚未分類：請確認研究狀態與優先度後按「標記完成」。"
    if action_id == "research-state-review":
        return "研究項目仍在審查：請完成主動審查檢查後按「標記完成」。"
    if action_id == "research-quality-missing-thesis":
        return "高優先研究缺少 thesis：請補上投資假說或確認暫不需要後按「標記完成」。"
    if action_id == "research-quality-missing-follow-up":
        return "高優先研究缺少追蹤問題：請補上後續追蹤問題或確認暫不需要後按「標記完成」。"
    return fallback


def _review_action_state_warning(warning: str) -> str:
    if not warning:
        return ""
    return f'<p class="status-line"><span class="badge error">{escape(warning)}</span></p>'


def _review_action_state_path(summary: dict[str, Any]) -> str:
    state_path = str(summary.get("review_action_state_path") or "")
    if state_path:
        return state_path.replace("\\", "/")
    summary_path = str(summary.get("path") or "")
    if not summary_path:
        return "review_action_state.json"
    return Path(summary_path).with_name("review_action_state.json").as_posix()


def _review_action_state_metadata(action: dict[str, Any], *, evidence_required: bool = False) -> str:
    details = []
    note = str(action.get("note") or "").strip()
    reviewer = str(action.get("reviewer") or "").strip()
    evidence_url = str(action.get("evidence_url") or "").strip()
    updated_at = str(action.get("updated_at") or "").strip()
    if evidence_required:
        details.append("\u9700\u8981\u4ea4\u4ed8\u8b49\u64da\uff1anote / reviewer / evidence URL")
    if note:
        details.append(f"備註：{escape(note)}")
    if note:
        details[-1] = f"note: {escape(note)}"
    if reviewer:
        details.append(f"reviewer: {escape(reviewer)}")
    if evidence_url:
        details.append(f"evidence: {escape(evidence_url)}")
    if updated_at:
        details.append(f"更新：{escape(updated_at)}")
    if updated_at:
        details[-1] = f"updated: {escape(updated_at)}"
    if not details:
        return ""
    return f'<div class="review-action-state-meta" data-review-action-state-meta="true">{" | ".join(details)}</div>'


def _review_action_command_cell(state_path: str, stock_id: str, action_id: str, *, evidence_required: bool = False) -> str:
    if not action_id:
        return "-"
    commands = [
        ("done", "done", "標記完成"),
        ("deferred", "deferred", "稍後處理"),
        ("ignored", "ignored", "不處理"),
        ("reopen", "open", "重新開啟"),
    ]
    buttons = []
    fallback_lines = []
    for action_name, status, display_label in commands:
        command = _review_action_state_command(state_path, stock_id, action_id, status)
        fallback_lines.append(command)
        buttons.append(
            '<button type="button" class="review-action-command"'
            f' data-review-action-command="{escape(action_name)}"'
            f' data-state-path="{escape(state_path)}"'
            f' data-stock-id="{escape(stock_id)}"'
            f' data-action-id="{escape(action_id)}"'
            f' data-status-value="{escape(status)}"'
            f' data-evidence-required="{str(evidence_required).lower()}"'
            f' data-command="{escape(command)}">'
            f"{escape(display_label)}"
            "</button>"
        )
    evidence_hint = (
        '<p class="review-action-state-meta">\u9700\u8981\u4ea4\u4ed8\u8b49\u64da\u6642\uff0cCLI \u8acb\u52a0\uff1a'
        '--note "..." --reviewer "..." --evidence-url "..."</p>'
        if evidence_required
        else ""
    )
    return (
        f'<div class="review-action-commands">{"".join(buttons)}</div>'
        '<details class="review-action-detail">'
        '<summary>指令 / API 詳細資訊</summary>'
        f'<code class="review-action-command-fallback">{escape(os.linesep.join(fallback_lines))}</code>'
        f"{evidence_hint}"
        '</details>'
    )


def _review_action_state_command(state_path: str, stock_id: str, action_id: str, status: str) -> str:
    args = [
        "python",
        "-m",
        "taiwan_stock_analysis.cli",
        "research",
        "action",
        "set",
        state_path,
        stock_id,
        action_id,
        "--status",
        status,
    ]
    return " ".join(_powershell_arg(arg) for arg in args)


def _powershell_arg(value: object) -> str:
    text = str(value)
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:/\\")
    if text and all(char in safe_chars for char in text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _report_rows(reports: list[dict[str, Any]]) -> str:
    if not reports:
        return _empty_row(3, "尚無個股報告。請先執行單一個股、batch 或 workflow 指令。")
    return "".join(
        "<tr>"
        f"<td>{escape(str(report.get('stock_id', '-')))}</td>"
        f"<td>{_link(str(report.get('html_path', '')), Path(str(report.get('html_path', ''))).name)}</td>"
        f"<td>{_link(str(report.get('json_path', '')), Path(str(report.get('json_path', ''))).name)}</td>"
        "</tr>"
        for report in reports
    )


def _comparison_rows(comparisons: list[dict[str, Any]]) -> str:
    if not comparisons:
        return _empty_row(2, "尚無同業比較。至少兩檔成功分析後才會產生 comparison。")
    return "".join(
        "<tr>"
        f"<td>{_link(str(comparison.get('html_path', '')), Path(str(comparison.get('html_path', ''))).name)}</td>"
        f"<td>{_link(str(comparison.get('json_path', '')), Path(str(comparison.get('json_path', ''))).name)}</td>"
        "</tr>"
        for comparison in comparisons
    )


def _batch_rows(batch_summaries: list[dict[str, Any]]) -> str:
    if not batch_summaries:
        return _empty_row(4, "尚無批次結果。請先執行 batch 或 workflow 指令。")

    rows = []
    for summary in batch_summaries:
        results = summary.get("results", [])
        if not isinstance(results, list) or not results:
            rows.append(
                "<tr>"
                f"<td>{escape(str(summary.get('path', '-')))}</td>"
                '<td colspan="3" class="empty">尚無批次結果。</td>'
                "</tr>"
            )
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            rows.append(
                "<tr>"
                f"<td>{escape(str(summary.get('path', '')))}</td>"
                f"<td>{escape(str(result.get('stock_id', '-')))}</td>"
                f"<td>{_status_badge(str(result.get('status', '-')))}</td>"
                f"<td>{escape(str(result.get('error', '')))}</td>"
                "</tr>"
            )
    return "".join(rows) or _empty_row(4, "尚無批次結果。")


def _workflow_summary_rows(workflow_summaries: list[dict[str, Any]]) -> str:
    if not workflow_summaries:
        return _empty_row(8, "尚無 workflow summary。執行 workflow 後會顯示 watchlist、估值 CSV 與比較結果。")

    rows = []
    for summary in workflow_summaries:
        paths = summary.get("paths", {})
        paths = paths if isinstance(paths, dict) else {}
        comparison = paths.get("comparison", {})
        comparison = comparison if isinstance(comparison, dict) else {}
        successful_stock_ids = _list_value(summary.get("successful_stock_ids"))
        stock_ids = _list_value(summary.get("stock_ids"))
        note = summary.get("error") or _comparison_note(summary, comparison)
        rows.append(
            "<tr>"
            f"<td>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</td>"
            f"<td>{escape(_run_id(summary) or '-')}</td>"
            f"<td>{escape(str(summary.get('watchlist_path', '')))}</td>"
            f"<td>成功 {len(successful_stock_ids)} / {len(stock_ids)}<br>{escape(', '.join(successful_stock_ids) or '-')}</td>"
            f"<td>{_link(str(paths.get('valuation_csv', '')), Path(str(paths.get('valuation_csv', ''))).name)}</td>"
            f"<td>{_link(str(paths.get('dashboard', '')), Path(str(paths.get('dashboard', ''))).name)}</td>"
            f"<td>{_comparison_link(comparison)}</td>"
            f"<td>{escape(str(note))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _workflow_status_line(workflow_summaries: list[dict[str, Any]]) -> str:
    if not workflow_summaries:
        return '<p class="status-line"><span class="badge">尚無 workflow summary</span></p>'
    latest = workflow_summaries[-1]
    if latest.get("error"):
        return f'<p class="status-line"><span class="badge error">Workflow summary 錯誤：{escape(str(latest.get("error")))}</span></p>'
    stock_ids = _list_value(latest.get("stock_ids"))
    successful_stock_ids = _list_value(latest.get("successful_stock_ids"))
    skipped = str(latest.get("comparison_skipped_reason") or "").strip()
    comparison_class = "error" if skipped else "ok"
    comparison_text = "同業比較略過" if skipped else "同業比較已產生或等待資料"
    return (
        '<p class="status-line">'
        f'<span class="badge ok">成功 {len(successful_stock_ids)} / {len(stock_ids)}</span>'
        f'<span class="badge">估值 CSV：{_yes_no(bool(_workflow_paths(latest).get("valuation_csv")))}</span>'
        f'<span class="badge {comparison_class}">{comparison_text}</span>'
        "</p>"
    )


def _workflow_reliability_summary(workflow_summaries: list[dict[str, Any]]) -> str:
    if not workflow_summaries:
        return '<p class="empty">尚未找到資料可信度摘要。</p>'
    sections: list[str] = []
    for summary in workflow_summaries:
        if summary.get("error"):
            sections.append(f'<p class="empty">Workflow summary 讀取失敗：{escape(str(summary.get("error")))}</p>')
            continue
        reliability = summary.get("data_reliability", {})
        reliability = reliability if isinstance(reliability, dict) else {}
        failures = summary.get("stock_failures", [])
        counts = "".join(
            f"<li><strong>{escape(key)}</strong>: {escape(str(reliability.get(key, 0)))}</li>"
            for key in ["overall_status", "ok", "warning", "error", "skipped"]
        )
        failure_rows: list[str] = []
        if isinstance(failures, list):
            for failure in failures:
                if not isinstance(failure, dict):
                    continue
                failure_rows.append(
                    "<tr>"
                    f"<td>{escape(str(failure.get('stock_id', '')))}</td>"
                    f"<td>{escape(str(failure.get('stage', '')))}</td>"
                    f"<td>{escape(str(failure.get('reason', '')))}</td>"
                    f"<td>{escape(str(failure.get('retry_hint', '')))}</td>"
                    "</tr>"
                )
        failure_body = "".join(failure_rows) or _empty_row(4, "沒有失敗股票。")
        sections.append(
            "<div>"
            f"<p>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</p>"
            f"<ul>{counts}</ul>"
            "<table><thead><tr><th>股票</th><th>階段</th><th>原因</th><th>建議</th></tr></thead>"
            f"<tbody>{failure_body}</tbody></table>"
            "</div>"
        )
    return "".join(sections)


def _workflow_source_audit_section(workflow_summaries: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for summary in workflow_summaries:
        audit = summary.get("source_audit")
        if not isinstance(audit, dict):
            continue
        counts = _dict_value(audit.get("counts"))
        items = audit.get("items", [])
        item_rows = _source_audit_item_rows(items if isinstance(items, list) else [])
        sections.append(
            "<div>"
            f"<p>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</p>"
            '<p class="status-line">'
            f'<span class="badge">overall: {escape(str(audit.get("status", "unknown") or "unknown"))}</span>'
            f'<span class="badge">counts: {_count_pairs(counts)}</span>'
            "</p>"
            "<table><thead><tr><th>stock_id</th><th>status</th><th>components</th></tr></thead>"
            f"<tbody>{item_rows}</tbody></table>"
            "</div>"
        )
    if not sections:
        return ""
    return f"<section><h2>來源稽核</h2>{''.join(sections)}</section>"


def _source_audit_item_rows(items: list[Any]) -> str:
    rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('stock_id', '-')))}</td>"
            f"<td>{_status_badge(str(item.get('status', 'unknown') or 'unknown'))}</td>"
            f"<td>{_source_audit_components(item)}</td>"
            "</tr>"
        )
    return "".join(rows) or _empty_row(3, "No source audit items")


def _source_audit_components(item: dict[str, Any]) -> str:
    components: list[str] = []
    for name, value in item.items():
        if name in {"stock_id", "status"} or not isinstance(value, dict):
            continue
        status = str(value.get("status") or "")
        source_mode = str(value.get("source_mode") or "")
        reason = str(value.get("review_reason") or value.get("reason") or "")
        details = [part for part in [status, source_mode, reason] if part]
        label = escape(str(name).replace("_", " "))
        text = escape(" | ".join(details) or "-")
        components.append(f"<div><strong>{label}</strong>: {text}</div>")
    return "".join(components) or "-"


def _batch_status_line(batch_results: list[dict[str, Any]]) -> str:
    if not batch_results:
        return '<p class="status-line"><span class="badge">尚無批次結果</span></p>'
    ok_count = sum(1 for result in batch_results if result.get("status") == "ok")
    error_count = sum(1 for result in batch_results if result.get("status") == "error")
    return (
        '<p class="status-line">'
        f'<span class="badge ok">成功 {ok_count}</span>'
        f'<span class="badge error">失敗 {error_count}</span>'
        f'<span class="badge">總計 {len(batch_results)}</span>'
        "</p>"
    )


def _workflow_paths(summary: dict[str, Any]) -> dict[str, Any]:
    paths = summary.get("paths", {})
    return paths if isinstance(paths, dict) else {}


def _run_id(summary: dict[str, Any]) -> str:
    metadata = summary.get("run_metadata", {})
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("run_id") or "")


def _workflow_dependency(summary: dict[str, Any]) -> str:
    registry = summary.get("artifact_registry", {})
    if not isinstance(registry, dict):
        return ""
    dependencies = registry.get("dependencies", {})
    if not isinstance(dependencies, dict):
        return ""
    return str(dependencies.get("workflow_summary") or "")


def _comparison_link(comparison: dict[str, Any]) -> str:
    html = str(comparison.get("html", ""))
    json_path = str(comparison.get("json", ""))
    links = [_link(html, Path(html).name), _link(json_path, Path(json_path).name)]
    links = [link for link in links if link != "-"]
    return " / ".join(links) if links else "-"


def _comparison_note(summary: dict[str, Any], comparison: dict[str, Any]) -> str:
    skipped = str(summary.get("comparison_skipped_reason") or "").strip()
    if skipped:
        return f"同業比較略過：{skipped}"
    if comparison:
        return "同業比較已產生"
    return ""


def _status_badge(status: str) -> str:
    if status == "ok":
        return '<span class="badge ok">成功</span>'
    if status == "error":
        return '<span class="badge error">失敗</span>'
    return f'<span class="badge">{escape(status or "-")}</span>'


def _empty_row(colspan: int, message: str) -> str:
    return f'<tr><td colspan="{colspan}" class="empty">{escape(message)}</td></tr>'


def _link(path: str, label: str) -> str:
    if not path:
        return "-"
    return f'<a href="{escape(path)}">{escape(label or path)}</a>'


def _list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _yes_no(value: bool) -> str:
    return "有" if value else "無"


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


def _relativize_fields(target: dict[str, Any], fields: list[str], base_dir: Path) -> None:
    for field in fields:
        value = target.get(field)
        if not isinstance(value, str) or not value:
            continue
        target[field] = os.path.relpath(Path(value).resolve(), base_dir.resolve()).replace(os.sep, "/")
