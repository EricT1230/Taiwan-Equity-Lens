from __future__ import annotations

from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.page_script import SCRIPT
from taiwan_stock_analysis.dashboard_ui.theme import base_css, view_css
from taiwan_stock_analysis.dashboard_ui.views import (
    render_market_view,
    render_outputs_view,
    render_workbench_view,
)
from taiwan_stock_analysis.handoff import build_handoff_quality_gate

# Task 10: the page shell. Assembles the three render_*_view() fragments (Tasks
# 7-9) into one offline <!DOCTYPE html> document, derives the topbar's three
# status pills, and embeds the inline <script> (page_script.py).
#
# _first_valid_summary/_base_dir below are *ported* (duplicated, not imported)
# from views/workbench.py's identically-named private helpers -- same "ported
# not imported" convention documented throughout workbench.py/outputs.py, used
# here to avoid a page -> views-internal coupling for a five-line lookup.
# _run_id mirrors views/outputs.py's own private `_run_id(summary)` the same way.

TITLE = "台股基本面儀表板"
_BRAND = "台股研究鏡"
_TAB_LABELS = (("market", "市場總覽"), ("workbench", "研究工作台"), ("outputs", "產出與紀錄"))

# Ported from dashboard.py:_market_intelligence_report_html's freshness_text tuple
# (dashboard.py ~line 2663): `(("news","news"),("fund_flow","flow"),("industry_trend","price"))`.
# The freshness dict actually carries four keys (news/fund_flow/industry_trend/price)
# but the established dashboard.py convention only ever surfaces these three in a
# summary readout -- kept identical here for the topbar's three dots.
_FRESHNESS_KEYS = ("news", "fund_flow", "industry_trend")

_DISCLAIMER = (
    "本儀表板僅協助整理研究流程與交接狀態，所有內容為研究過程紀錄，"
    "不構成投資建議、買賣建議或持倉建議。"
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_valid_summary(items: dict[str, Any]) -> dict[str, Any] | None:
    summaries = items.get("research_summaries")
    if not isinstance(summaries, list):
        return None
    for summary in summaries:
        if isinstance(summary, dict) and not summary.get("error"):
            return summary
    return None


def _base_dir(summary: dict[str, Any]) -> Path | None:
    base_dir = str(summary.get("base_dir") or "").strip()
    return Path(base_dir) if base_dir else None


def _gate_and_backlog_pills(items: dict[str, Any]) -> tuple[str, str, int]:
    summary = _first_valid_summary(items)
    if summary is None:
        gate_html = f'<span id="topbar-gate-pill">{pill("交接 Gate：尚無資料", tone="info")}</span>'
        backlog_html = f'<span id="topbar-backlog-pill">{pill("待辦 0", tone="info")}</span>'
        return gate_html, backlog_html, 0

    state = summary.get("review_action_state")
    state = state if isinstance(state, dict) else None
    gate = build_handoff_quality_gate(summary, state, blocker_limit=3, evidence_base_dir=_base_dir(summary))
    ready = bool(gate.get("ready"))
    blocker_count = int(gate.get("blocker_count") or 0)
    open_count = int(gate.get("open_count") or 0)

    gate_text = "可交接" if ready else f"交接 Gate：阻塞 {blocker_count} 件"
    gate_html = f'<span id="topbar-gate-pill">{pill(gate_text, tone="ok" if ready else "blocked")}</span>'
    backlog_html = f'<span id="topbar-backlog-pill">{pill(f"待辦 {open_count}", tone="info")}</span>'
    return gate_html, backlog_html, open_count


def _first_mi_report(items: dict[str, Any]) -> dict[str, Any]:
    reports = items.get("market_intelligence_reports")
    if not isinstance(reports, list) or not reports:
        return {}
    report = reports[0]
    if not isinstance(report, dict) or report.get("error"):
        return {}
    return report


def _freshness_pill(items: dict[str, Any]) -> str:
    freshness = _dict(_first_mi_report(items).get("freshness"))
    dots = []
    for key in _FRESHNESS_KEYS:
        status = str(_dict(freshness.get(key)).get("status") or "")
        tone = "ok" if status == "fresh" else "warn"
        dots.append(f'<span class="topbar-dot topbar-dot-{tone}"></span>')
    return f'<span class="ui-pill ui-pill-info">鮮度 {"".join(dots)}</span>'


def _run_id(items: dict[str, Any]) -> str:
    summaries = items.get("workflow_summaries")
    if not isinstance(summaries, list):
        return ""
    for summary in summaries:
        run_id = str(_dict(_dict(summary).get("run_metadata")).get("run_id") or "").strip()
        if run_id:
            return run_id
    return ""


def _source_mode(items: dict[str, Any]) -> str:
    # Best-effort only: there is no single top-level "source mode" field anywhere
    # in workflow_summary.json -- it only exists per-component nested inside
    # source_audit.items[].<component>.source_mode (see dashboard.py:5011 /
    # outputs.py:_source_audit_component_html). This scans for the first one
    # found (stable dict-insertion order) purely for the topbar's cosmetic
    # "run <id> · <mode>" caption; guarded to "" (omitted) when absent.
    summaries = items.get("workflow_summaries")
    if not isinstance(summaries, list):
        return ""
    for summary in summaries:
        entries = _dict(_dict(summary).get("source_audit")).get("items")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key, value in entry.items():
                if key in {"stock_id", "status"} or not isinstance(value, dict):
                    continue
                mode = str(value.get("source_mode") or "").strip()
                if mode:
                    return mode
    return ""


def _brand(items: dict[str, Any]) -> str:
    meta_parts = []
    run_id = _run_id(items)
    if run_id:
        meta_parts.append(f"run {esc(run_id)}")
    source_mode = _source_mode(items)
    if source_mode:
        meta_parts.append(esc(source_mode))
    meta_html = f'<span class="mono">{" · ".join(meta_parts)}</span>' if meta_parts else ""
    return f'<div class="brand"><strong>{esc(_BRAND)}</strong>{meta_html}</div>'


def _topbar(items: dict[str, Any]) -> tuple[str, int]:
    gate_html, backlog_html, open_count = _gate_and_backlog_pills(items)
    freshness_html = _freshness_pill(items)
    html = (
        '<header class="topbar">'
        f"{_brand(items)}"
        f'<div class="topbar-status">{gate_html}{backlog_html}{freshness_html}</div>'
        "</header>"
    )
    return html, open_count


def _tabs(open_count: int) -> str:
    count_html = f' <span class="mono ui-tab-count">{esc(open_count)}</span>' if open_count else ""
    buttons = []
    for key, label in _TAB_LABELS:
        suffix = count_html if key == "workbench" else ""
        buttons.append(f'<button type="button" class="ui-tab" data-tab="{key}">{esc(label)}{suffix}</button>')
    return f'<nav class="ui-tabs">{"".join(buttons)}</nav>'


def _panels(items: dict[str, Any], *, action_api_enabled: bool) -> str:
    market_html = render_market_view(items)
    workbench_html = render_workbench_view(items, action_api_enabled=action_api_enabled)
    outputs_html = render_outputs_view(items, action_api_enabled=action_api_enabled)
    return (
        f'<section class="ui-panel active" id="market">{market_html}</section>'
        f'<section class="ui-panel" id="workbench">{workbench_html}</section>'
        f'<section class="ui-panel" id="outputs">{outputs_html}</section>'
    )


def render(items: dict[str, Any], *, action_api_enabled: bool = False) -> str:
    safe_items = items if isinstance(items, dict) else {}
    topbar_html, open_count = _topbar(safe_items)
    tabs_html = _tabs(open_count)
    panels_html = _panels(safe_items, action_api_enabled=action_api_enabled)
    return (
        "<!DOCTYPE html>"
        '<html lang="zh-Hant">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{TITLE}</title>"
        f"<style>{base_css()}{view_css()}</style>"
        "</head>"
        "<body>"
        f"{topbar_html}"
        f"{tabs_html}"
        f"{panels_html}"
        f'<footer class="disclaimer">{esc(_DISCLAIMER)}</footer>'
        f"{SCRIPT}"
        "</body>"
        "</html>"
    )
