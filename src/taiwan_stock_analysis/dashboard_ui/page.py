from __future__ import annotations

from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.page_script import SCRIPT
from taiwan_stock_analysis.dashboard_ui.product_data import market_snapshot
from taiwan_stock_analysis.dashboard_ui.theme import base_css, view_css
from taiwan_stock_analysis.dashboard_ui.views import (
    render_intelligence_view,
    render_market_view,
    render_overview_view,
    render_outputs_view,
    render_screener_view,
    render_strategy_view,
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

TITLE = "盤勢鏡｜台股即時研究桌面"
_BRAND = "盤勢鏡"
_TAB_LABELS = (
    ("overview", "今日總覽", "⌁"),
    ("market", "產業地圖", "▦"),
    ("screener", "智慧選股", "⌕"),
    ("intelligence", "市場情報", "◫"),
    ("strategy", "市場策略", "◎"),
    ("workbench", "研究工作台", "✓"),
    ("outputs", "資料與紀錄", "↗"),
)

# Ported from dashboard.py:_market_intelligence_report_html's freshness_text tuple
# (dashboard.py ~line 2663): `(("news","news"),("fund_flow","flow"),("industry_trend","price"))`.
# The freshness dict actually carries four keys (news/fund_flow/industry_trend/price)
# but the established dashboard.py convention only ever surfaces these three in a
# summary readout -- kept identical here for the topbar's three dots.
_FRESHNESS_KEYS = ("news", "fund_flow", "industry_trend")
_DATA_MODES = {"production", "demo"}

_DISCLAIMER = (
    "本儀表板僅協助整理研究流程與交接狀態，所有內容為研究過程紀錄，"
    "不構成投資建議、買賣建議或持倉建議。"
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalise_data_mode(value: str) -> str:
    mode = str(value or "").strip().casefold()
    if mode not in _DATA_MODES:
        raise ValueError("data_mode must be 'production' or 'demo'")
    return mode


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
    snapshot = market_snapshot(items)
    status_label = str(snapshot["delivery_status"])
    effective_fresh = snapshot["fresh_count"] == snapshot["fresh_total"]
    dots = []
    freshness = _dict(_first_mi_report(items).get("freshness"))
    labels = {"news": "新聞", "fund_flow": "法人", "industry_trend": "產業價格"}
    for key in _FRESHNESS_KEYS:
        source_fresh = str(_dict(freshness.get(key)).get("status") or "") == "fresh"
        tone = "ok" if effective_fresh and source_fresh else "warn"
        readable = "可用" if tone == "ok" else "需更新"
        dots.append(
            f'<span class="topbar-dot topbar-dot-{tone}" aria-hidden="true"></span>'
            f'<span class="sr-only">{esc(labels[key])}：{esc(readable)}；</span>'
        )
    pill_tone = "ok" if status_label == "EOD" and effective_fresh else "warn"
    return (
        f'<span class="ui-pill ui-pill-{pill_tone}" data-live-market-badge="true"'
        f' title="靜態研究快照；不是即時行情">{esc(status_label)} {"".join(dots)}</span>'
    )


def _run_id(items: dict[str, Any]) -> str:
    summaries = items.get("workflow_summaries")
    if not isinstance(summaries, list):
        summaries = []
    for summary in summaries:
        run_id = str(_dict(_dict(summary).get("run_metadata")).get("run_id") or "").strip()
        if run_id:
            return run_id
    research = _first_valid_summary(items)
    return str(_dict(_dict(research).get("run_metadata")).get("run_id") or "").strip()


def _source_mode(items: dict[str, Any]) -> str:
    # Best-effort only: there is no single top-level "source mode" field anywhere
    # in workflow_summary.json -- it only exists per-component nested inside
    # source_audit.items[].<component>.source_mode (see dashboard.py:5011 /
    # outputs.py:_source_audit_component_html). This scans for the first one
    # found (stable dict-insertion order) purely for the topbar's cosmetic
    # "研究資料 <id> · <mode>" caption; guarded to "" (omitted) when absent.
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


def _storage_namespace(items: dict[str, Any]) -> str:
    run_id = _run_id(items)
    if run_id:
        return run_id
    report = _first_mi_report(items)
    generated_at = str(report.get("generated_at") or "").strip()
    if generated_at:
        return generated_at
    summary = _first_valid_summary(items)
    summary = _dict(summary)
    base_dir = str(summary.get("base_dir") or "").strip()
    summary_path = str(summary.get("path") or "").strip()
    research_path = str(summary.get("research_path") or "").strip()
    summary_generated = str(_dict(summary.get("run_metadata")).get("generated_at") or "").strip()
    identity = "|".join(
        value for value in (base_dir, summary_path, research_path, summary_generated) if value
    )
    return identity or "unscoped"


def _brand(items: dict[str, Any]) -> str:
    meta_parts = []
    run_id = _run_id(items)
    if run_id:
        meta_parts.append(f"研究資料 {esc(run_id)}")
    source_mode = _source_mode(items)
    if source_mode:
        meta_parts.append(esc(source_mode))
    meta_html = f'<span class="mono">{" · ".join(meta_parts)}</span>' if meta_parts else ""
    return (
        '<div class="brand">'
        '<span class="brand-mark" aria-hidden="true">M</span>'
        f'<div><strong>{esc(_BRAND)}</strong><small>MARKET LENS</small>{meta_html}</div>'
        "</div>"
    )


def _topbar(items: dict[str, Any]) -> tuple[str, int]:
    gate_html, backlog_html, open_count = _gate_and_backlog_pills(items)
    freshness_html = _freshness_pill(items)
    html = (
        '<header class="topbar">'
        '<div class="topbar-heading"><span class="desk-kicker">TAIWAN EQUITY DESK</span>'
        '<strong data-page-title="true">今日總覽</strong></div>'
        '<div class="topbar-search"><span aria-hidden="true">⌕</span>'
        '<label class="sr-only" for="global-stock-search">搜尋股票</label>'
        '<input id="global-stock-search" type="search" data-global-search="true"'
        ' placeholder="搜尋股票、產業、題材  /"></div>'
        f'<div class="topbar-status">{gate_html}{backlog_html}{freshness_html}</div>'
        "</header>"
    )
    return html, open_count


def _tabs(open_count: int) -> str:
    count_html = f' <span class="mono ui-tab-count">{esc(open_count)}</span>' if open_count else ""
    buttons = []
    for key, label, icon in _TAB_LABELS:
        suffix = count_html if key == "workbench" else ""
        buttons.append(
            f'<button type="button" class="ui-tab" data-tab="{key}" data-tab-label="{esc(label)}">'
            f'<span class="ui-tab-icon" aria-hidden="true">{esc(icon)}</span>'
            f'<span>{esc(label)}{suffix}</span></button>'
        )
    return f'<nav class="ui-tabs" aria-label="主要功能">{"".join(buttons)}</nav>'


def _sidebar(items: dict[str, Any], open_count: int) -> str:
    return (
        '<aside class="side-rail">'
        f"{_brand(items)}"
        f"{_tabs(open_count)}"
        '<div class="side-rail-foot"><span class="side-live-dot" data-live-dot="true"></span>'
        '<div><strong data-live-provider-label="true">Research-grade</strong>'
        '<small data-live-provider-mode="true">來源 · 鮮度 · 品質閘門</small></div></div>'
        "</aside>"
    )


def _live_connection_bar(
    *,
    live_api_enabled: bool,
    force_refresh_enabled: bool,
) -> str:
    if not live_api_enabled:
        return (
            '<section class="live-connection live-connection-offline" aria-label="連線狀態">'
            '<div><span class="live-connection-dot"></span><strong>目前是靜態檔案</strong>'
            '<small>即時行情與消息需要透過 dashboard --serve 啟動。</small></div>'
            "</section>"
        )
    refresh_control = (
        '<button type="button" class="desk-link" data-live-refresh="true">立即更新</button>'
        if force_refresh_enabled
        else '<span class="desk-link" data-live-refresh-read-only="true">唯讀自動更新</span>'
    )
    return (
        '<section class="live-connection live-connection-loading" data-live-connection="true"'
        ' aria-label="即時資料連線狀態" aria-live="polite">'
        '<div><span class="live-connection-dot"></span>'
        '<strong data-live-connection-title="true">正在連接市場資料…</strong>'
        '<small data-live-connection-detail="true">等待行情、公告與法人資料</small></div>'
        '<div class="live-connection-actions">'
        '<span class="mono" data-live-countdown="true">--</span>'
        f"{refresh_control}"
        "</div></section>"
    )


def _admission_rejected_count(admission_summary: dict[str, Any] | None) -> int:
    if not isinstance(admission_summary, dict):
        return 0
    value = admission_summary.get("rejected_count", 0)
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _data_mode_banner(data_mode: str, *, rejected_count: int) -> str:
    if data_mode == "demo":
        return (
            '<section class="data-mode-banner data-mode-demo"'
            ' data-data-mode-badge="demo" data-admission-rejected-count="0"'
            ' role="alert" aria-label="示範資料警告">'
            '<strong>Demo 模式｜DEMO／示範資料，不可作投資依據</strong>'
            '<small>此頁可包含 fixture、offline 或 synthetic 範例，且不會成為正式資料的備援。</small>'
            "</section>"
        )
    rejected_note = (
        f"已封鎖 {rejected_count} 份未通過正式資料檢查的內容。"
        if rejected_count
        else "目前沒有內容被正式資料檢查封鎖。"
    )
    return (
        '<section class="data-mode-banner data-mode-production"'
        ' data-data-mode-badge="production"'
        f' data-admission-rejected-count="{rejected_count}" aria-label="資料模式">'
        '<strong>正式資料模式</strong>'
        '<small>只顯示通過正式來源、狀態與時間檢查的資料。'
        f"{rejected_note}</small>"
        "</section>"
    )


def _panels(
    items: dict[str, Any],
    *,
    action_api_enabled: bool,
    live_api_enabled: bool,
) -> str:
    overview_html = render_overview_view(items)
    market_html = render_market_view(items, live_api_enabled=live_api_enabled)
    screener_html = render_screener_view(items, live_api_enabled=live_api_enabled)
    intelligence_html = render_intelligence_view(items)
    strategy_html = render_strategy_view(items)
    workbench_html = render_workbench_view(items, action_api_enabled=action_api_enabled)
    outputs_html = render_outputs_view(items, action_api_enabled=action_api_enabled)
    return (
        f'<section class="ui-panel active" id="overview">{overview_html}</section>'
        f'<section class="ui-panel" id="market">{market_html}</section>'
        f'<section class="ui-panel" id="screener">{screener_html}</section>'
        f'<section class="ui-panel" id="intelligence">{intelligence_html}</section>'
        f'<section class="ui-panel" id="strategy">{strategy_html}</section>'
        f'<section class="ui-panel" id="workbench">{workbench_html}</section>'
        f'<section class="ui-panel" id="outputs">{outputs_html}</section>'
    )


def render(
    items: dict[str, Any],
    *,
    action_api_enabled: bool = False,
    live_api_enabled: bool | None = None,
    data_mode: str = "production",
    admission_summary: dict[str, Any] | None = None,
) -> str:
    safe_items = items if isinstance(items, dict) else {}
    safe_data_mode = _normalise_data_mode(data_mode)
    rejected_count = _admission_rejected_count(admission_summary)
    live_enabled = action_api_enabled if live_api_enabled is None else bool(live_api_enabled)
    topbar_html, open_count = _topbar(safe_items)
    sidebar_html = _sidebar(safe_items, open_count)
    panels_html = _panels(
        safe_items,
        action_api_enabled=action_api_enabled,
        live_api_enabled=live_enabled,
    )
    storage_namespace = _storage_namespace(safe_items)
    return (
        "<!DOCTYPE html>"
        '<html lang="zh-Hant">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{TITLE}</title>"
        f"<style>{base_css()}{view_css()}</style>"
        "</head>"
        f'<body data-storage-namespace="{esc(storage_namespace)}"'
        f' data-dashboard-mode="{safe_data_mode}"'
        f' data-data-mode="{safe_data_mode}"'
        f' data-admission-rejected-count="{rejected_count if safe_data_mode == "production" else 0}"'
        f' data-live-api-enabled="{"true" if live_enabled else "false"}">'
        '<div class="app-shell">'
        f"{sidebar_html}"
        '<main class="app-main">'
        f"{topbar_html}"
        f"{_data_mode_banner(safe_data_mode, rejected_count=rejected_count)}"
        f"{_live_connection_bar(live_api_enabled=live_enabled, force_refresh_enabled=action_api_enabled)}"
        f"{panels_html}"
        f'<footer class="disclaimer">{esc(_DISCLAIMER)}</footer>'
        "</main>"
        "</div>"
        '<div class="sr-only" role="status" aria-live="polite"'
        ' data-ui-live-status="true"></div>'
        f"{SCRIPT}"
        "</body>"
        "</html>"
    )
