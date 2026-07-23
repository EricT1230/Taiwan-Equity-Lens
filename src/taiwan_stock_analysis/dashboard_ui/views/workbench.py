from __future__ import annotations

from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard_ui.charts import progress_bar
from taiwan_stock_analysis.dashboard_ui.components import badge, card, copy_button, esc, pill
from taiwan_stock_analysis.dashboard_ui.labels import (
    REVIEW_ACTION_CATEGORY_LABELS,
    REVIEW_ACTION_PRIORITIES,
    REVIEW_ACTION_PRIORITY_LABELS,
    REVIEW_ACTION_SEVERITIES,
    REVIEW_ACTION_SEVERITY_LABELS,
    REVIEW_ACTION_STATUS_LABELS,
)
from taiwan_stock_analysis.handoff import build_handoff_quality_gate, requires_handoff_evidence
from taiwan_stock_analysis.review_action_state import (
    ACTION_STATUSES,
    apply_review_action_state,
    build_review_action_state_report,
)

# This view merges four old dashboard.py sections (expert console, Top-3 cards,
# evidence board, review-action table) into one flattened, sortable queue. Gate
# derivation (`build_handoff_quality_gate`) and evidence requirement
# (`requires_handoff_evidence`) are imported from `handoff.py` (no cycle risk --
# handoff.py has zero internal project imports beyond `review_action_state`).
# Field extraction and the CLI command format below are *ported* (duplicated, not
# imported) from `dashboard.py`'s private helpers -- importing from `dashboard.py`
# itself is what the leaf `dashboard_ui.labels` module exists to avoid.

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_TONES = {
    "manual_review": "blocked",
    "error": "blocked",
    "warning": "warn",
    "stale": "warn",
    "info": "info",
    "unknown": "info",
}
_PRIORITY_TONES = {"high": "blocked", "medium": "warn", "low": "info"}
# "open" is only looked up by _queue_status_line (Feature D) -- the per-row
# status badge in _queue_row_block never renders it (guarded by `!= "open"`),
# so adding this key cannot change any existing rendering.
_STATUS_TONES = {"open": "blocked", "done": "ok", "deferred": "warn", "ignored": "info"}
_RELIABILITY_TONES = {"warning": "warn", "error": "blocked", "stale": "warn", "unknown": "info", "ok": "ok"}
_ACTION_STATUS_BUTTONS = (("done", "標記完成"), ("deferred", "稍後處理"), ("ignored", "不處理"))
# Feature C (spec 3.3 "批次操作"): ported from dashboard.py:_review_action_bulk_tools
# (~line 2973-2981) -- same two bulk statuses/labels, no bulk "不處理" (matching the
# old toolbar exactly, which only ever offered done/deferred as bulk actions).
_BULK_STATUSES = (("done", "批次標記完成"), ("deferred", "批次稍後處理"))
_SAFE_ARG_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:/\\")


def _str(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    # Ported from dashboard.py:_dict_value (~line 2909).
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _base_dir(summary: dict[str, Any]) -> Path | None:
    base_dir = _str(summary.get("base_dir"))
    return Path(base_dir) if base_dir else None


def _state_path(summary: dict[str, Any]) -> str:
    # Ported from dashboard.py:_review_action_state_path. `review_action_state_path`
    # is only present when discover_dashboard_items found an existing sidecar file
    # on disk; otherwise derive the conventional sibling path from the summary's
    # own `path`.
    state_path = _str(summary.get("review_action_state_path"))
    if state_path:
        return state_path.replace("\\", "/")
    source_path = _str(summary.get("path"))
    if not source_path:
        return "review_action_state.json"
    return Path(source_path).with_name("review_action_state.json").as_posix()


def _handoff_pack_output_dir(summary: dict[str, Any]) -> str:
    # Ported from dashboard.py:_handoff_pack_output_dir.
    source_path = _str(summary.get("path"))
    if source_path:
        return (Path(source_path).parent / "handoff-pack").as_posix()
    base_dir = _str(summary.get("base_dir"))
    if base_dir:
        return (Path(base_dir) / "handoff-pack").as_posix()
    return "handoff-pack"


def _powershell_arg(value: object) -> str:
    # Ported from dashboard.py:_powershell_arg.
    text = str(value)
    if text and all(char in _SAFE_ARG_CHARS for char in text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _review_action_command(state_path: str, stock_id: str, action_id: str, status: str) -> str:
    # Ported from dashboard.py:_review_action_state_command.
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


def _handoff_pack_command(source_path: str, state_path: str, output_dir: str) -> str:
    # Ported from dashboard.py:_handoff_pack_command.
    args = [
        "python",
        "-m",
        "taiwan_stock_analysis.cli",
        "research",
        "handoff-pack",
        source_path or "research_summary.json",
        "--state",
        state_path or "review_action_state.json",
        "--output-dir",
        output_dir or "handoff-pack",
    ]
    return " ".join(_powershell_arg(arg) for arg in args)


def _first_valid_summary(summaries: list[Any]) -> dict[str, Any] | None:
    for summary in summaries:
        if isinstance(summary, dict) and not summary.get("error"):
            return summary
    return None


def _flatten_rows(queue: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in queue:
        if not isinstance(group, dict):
            continue
        stock_id = _str(group.get("stock_id")) or "-"
        priority = _str(group.get("priority"))
        actions = group.get("actions")
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            rows.append(
                {
                    "stock_id": stock_id,
                    "priority": priority,
                    "action_id": _str(action.get("id")),
                    "category": _str(action.get("category")),
                    "severity": _str(action.get("severity")),
                    "message": _str(action.get("message")),
                    "status": _str(action.get("status")) or "open",
                    "note": _str(action.get("note")),
                    "reviewer": _str(action.get("reviewer")),
                    "evidence_url": _str(action.get("evidence_url")),
                }
            )
    return rows


def _row_sort_key(row: dict[str, str]) -> tuple[int, int]:
    priority_rank = _PRIORITY_RANK.get(row["priority"], 9)
    severity = row["severity"]
    severity_rank = (
        REVIEW_ACTION_SEVERITIES.index(severity) if severity in REVIEW_ACTION_SEVERITIES else len(REVIEW_ACTION_SEVERITIES)
    )
    return (priority_rank, severity_rank)


def _gate_card(
    gate: dict[str, Any],
    rows: list[dict[str, str]],
    source_path: str,
    state_path: str,
    summary: dict[str, Any],
    *,
    action_api_enabled: bool,
) -> str:
    total = len(rows)
    done = sum(1 for row in rows if row["status"] != "open")
    blocker_count = int(gate.get("blocker_count") or 0)
    ready = bool(gate.get("ready"))
    tone = "ok" if ready else "blocked"
    readiness = "交付門檻已通過" if ready else f"尚有 {blocker_count} 件待交接阻塞"
    next_href = "#wb-row-0" if rows else "#"

    pack_command = _handoff_pack_command(source_path, state_path, _handoff_pack_output_dir(summary))
    if action_api_enabled:
        pack_button = (
            '<button type="button" class="ui-btn primary" data-action-api="handoff-pack"'
            f' data-source-path="{esc(source_path)}" data-state-path="{esc(state_path)}">'
            "產出 Evidence Pack</button>"
        )
    else:
        pack_button = (
            f'<button type="button" class="ui-btn primary" data-copy="{esc(pack_command)}">' "產出 Evidence Pack</button>"
        )

    body = (
        '<div class="wb-gate-row">'
        f'<span class="wb-gate-stat"><strong id="wb-gate-blockers">{esc(blocker_count)}</strong> 件阻塞</span>'
        # Stable ids below are resync hooks for served-mode JS (page_script.py):
        # after a review-actions/set POST, the topbar pill updates immediately,
        # but without these the gate card itself kept showing stale numbers.
        f"{progress_bar(done, total, container_id='wb-gate-progress')}"
        f'<span class="wb-gate-stat mono" id="wb-gate-processed">{esc(done)} / {esc(total)} 已處理</span>'
        f'<span id="wb-gate-readiness">{pill(readiness, tone=tone)}</span>'
        "</div>"
        '<div class="wb-gate-actions">'
        f'<a class="ui-btn primary" href="{next_href}">⚡ 處理建議下一步</a>'
        f"{pack_button}"
        "</div>"
    )
    return card("交接 GATE", body)


def _filter_select(name: str, placeholder: str, options: Any, labels: dict[str, str]) -> str:
    opts = [f'<option value="all">{esc(placeholder)}：全部</option>']
    for option in options:
        label = labels.get(option, option)
        opts.append(f'<option value="{esc(option)}">{esc(label)}</option>')
    joined = "".join(opts)
    return f'<select data-queue-filter="{esc(name)}">{joined}</select>'


def _filters_bar() -> str:
    severity_select = _filter_select("severity", "嚴重度", REVIEW_ACTION_SEVERITIES, REVIEW_ACTION_SEVERITY_LABELS)
    category_select = _filter_select("category", "類別", REVIEW_ACTION_CATEGORY_LABELS.keys(), REVIEW_ACTION_CATEGORY_LABELS)
    priority_select = _filter_select("priority", "優先度", REVIEW_ACTION_PRIORITIES, REVIEW_ACTION_PRIORITY_LABELS)
    status_select = _filter_select("status", "狀態", REVIEW_ACTION_STATUS_LABELS.keys(), REVIEW_ACTION_STATUS_LABELS)
    return (
        '<div class="filters">'
        f"{severity_select}{category_select}{priority_select}{status_select}"
        '<input type="search" data-queue-filter="search" placeholder="搜尋事項、股票代號…">'
        "</div>"
    )


def _row_action_button(
    row: dict[str, str],
    source_path: str,
    state_path: str,
    status: str,
    label: str,
    *,
    action_api_enabled: bool,
) -> str:
    stock_id = row["stock_id"]
    action_id = row["action_id"]
    if action_api_enabled:
        return (
            '<button type="button" class="ui-btn" data-action-api="review-action"'
            f' data-source-path="{esc(source_path)}" data-state-path="{esc(state_path)}"'
            f' data-stock="{esc(stock_id)}" data-action-id="{esc(action_id)}"'
            f' data-status="{esc(status)}">{esc(label)}</button>'
        )
    command = _review_action_command(state_path, stock_id, action_id, status)
    return copy_button(label, command)


def _queue_expand_block(
    row: dict[str, str],
    row_id: str,
    is_next: bool,
    source_path: str,
    state_path: str,
    *,
    action_api_enabled: bool,
) -> str:
    message = row["message"]
    note = row["note"]
    reviewer = row["reviewer"]
    evidence_url = row["evidence_url"]

    evidence_html = ""
    if requires_handoff_evidence(row["action_id"]):
        evidence_html = (
            '<p class="wb-evidence-hint">交付證據（高風險事項必填）：</p>'
            '<div class="queue-evidence">'
            f'<input placeholder="note：處理說明" value="{esc(note)}">'
            f'<input placeholder="reviewer：覆核人" value="{esc(reviewer)}">'
            f'<input placeholder="evidence：檔案路徑或 URL" value="{esc(evidence_url)}">'
            "</div>"
        )
    action_buttons = "".join(
        _row_action_button(row, source_path, state_path, status, label, action_api_enabled=action_api_enabled)
        for status, label in _ACTION_STATUS_BUTTONS
    )
    cli_hint = "API 模式：按下即時更新狀態" if action_api_enabled else "靜態模式：按下後複製 CLI 指令"
    hidden_attr = "" if is_next else " hidden"
    return (
        f'<div class="queue-expand" data-expand-for="{esc(row_id)}"{hidden_attr}>'
        f'<p><strong>問題全文：</strong>{esc(message)}</p>'
        f"{evidence_html}"
        f'<div class="wb-actions-row">{action_buttons}'
        f'<span class="wb-cli mono">{esc(cli_hint)}</span>'
        "</div>"
        "</div>"
    )


def _row_select_checkbox(row: dict[str, str], state_path: str, *, action_api_enabled: bool) -> str:
    # Feature C (spec 3.3 "批次操作"): select checkbox ported from
    # dashboard.py:_review_action_rows's select-cell (~line 2771). The old
    # markup put stock_id/action_id only on the parent <tr> and let the bulk
    # JS look them up via closest("tr"); here the checkbox carries them
    # directly since .queue-expand is a DOM *sibling* of .queue-row (not a
    # child -- see _queue_row_block), so there is no single ancestor to read
    # both from.
    #
    # Static mode additionally pre-bakes each bulk status's CLI command onto
    # the checkbox (reusing _review_action_command, the exact same builder the
    # per-row buttons use) so the bulk-copy JS never has to reconstruct a
    # command string client-side -- it only ever joins already-rendered text.
    stock_id = row["stock_id"]
    action_id = row["action_id"]
    command_attrs = ""
    if not action_api_enabled:
        command_attrs = "".join(
            f' data-command-{status}="{esc(_review_action_command(state_path, stock_id, action_id, status))}"'
            for status, _label in _BULK_STATUSES
        )
    return (
        '<span class="wb-select-cell">'
        '<input type="checkbox" class="wb-row-select" data-queue-select="true"'
        f' data-stock="{esc(stock_id)}" data-action-id="{esc(action_id)}"'
        f"{command_attrs}"
        ' aria-label="選取審查動作">'
        "</span>"
    )


def _queue_row_block(
    row: dict[str, str],
    index: int,
    source_path: str,
    state_path: str,
    *,
    action_api_enabled: bool,
) -> str:
    row_id = f"wb-row-{index}"
    is_next = index == 0
    stock_id = row["stock_id"]
    priority = row["priority"]
    severity = row["severity"]
    category = row["category"]
    status = row["status"]
    message = row["message"]

    row_class = "queue-row next" if is_next else "queue-row"
    priority_badge = badge(
        REVIEW_ACTION_PRIORITY_LABELS.get(priority, priority or "-"), tone=_PRIORITY_TONES.get(priority, "info")
    )
    severity_badge = badge(
        REVIEW_ACTION_SEVERITY_LABELS.get(severity, severity or "-"), tone=_SEVERITY_TONES.get(severity, "info")
    )
    category_label = REVIEW_ACTION_CATEGORY_LABELS.get(category, category or "-")
    status_badge = ""
    if status != "open":
        status_badge = badge(REVIEW_ACTION_STATUS_LABELS.get(status, status), tone=_STATUS_TONES.get(status, "info"))
    next_tag = '<span class="wb-next-tag">建議下一步</span>' if is_next else ""
    toggle_label = "收合 ▲" if is_next else "展開 ▼"
    toggle_button = f'<button type="button" class="ui-btn" data-queue-toggle="{esc(row_id)}">{esc(toggle_label)}</button>'
    next_indicator = "▶" if is_next else ""
    select_checkbox = _row_select_checkbox(row, state_path, action_api_enabled=action_api_enabled)

    row_html = (
        f'<div class="{row_class}" id="{esc(row_id)}"'
        f' data-stock="{esc(stock_id)}" data-priority="{esc(priority)}"'
        f' data-severity="{esc(severity)}" data-category="{esc(category)}"'
        f' data-status="{esc(status)}">'
        f"{select_checkbox}"
        f'<span class="wb-next-indicator">{next_indicator}</span>'
        f'<span class="mono">{esc(stock_id)}</span>'
        f"<span>{priority_badge}</span>"
        f"<span>{severity_badge}</span>"
        f"<span>{esc(category_label)}</span>"
        f"<span>{esc(message)}</span>"
        f'<span class="wb-actions">{status_badge}{next_tag}{toggle_button}</span>'
        "</div>"
    )
    expand_html = _queue_expand_block(row, row_id, is_next, source_path, state_path, action_api_enabled=action_api_enabled)
    return row_html + expand_html


def _queue_status_line(state_report: dict[str, Any]) -> str:
    # Feature D (spec 3.3 "狀態資訊"): ported vocabulary from
    # dashboard.py:_review_action_status_pairs (~line 2924) and the
    # status-line badges in _review_actions_section (~line 2664-2669) -- same
    # REVIEW_ACTION_STATUS_LABELS text and the same 過期狀態/最後更新 phrasing,
    # regrouped into one badge per status (this view's badge() idiom) instead
    # of the old single "/"-joined string. Data source is
    # review_action_state.build_review_action_state_report, which already
    # degrades to a dense all-zero by_status and a "-" last_updated when there
    # is no state sidecar -- _dict/_int/_str below are belt-and-suspenders in
    # case that shape ever drifts, not because the real callers can send junk.
    by_status = _dict(state_report.get("by_status"))
    status_badges = "".join(
        badge(
            f"{REVIEW_ACTION_STATUS_LABELS.get(status, status)} {_int(by_status.get(status))}",
            tone=_STATUS_TONES.get(status, "info"),
        )
        for status in ACTION_STATUSES
    )
    stale_count = _int(state_report.get("stale_count"))
    stale_badge = badge(f"過期狀態 {stale_count}", tone="warn" if stale_count else "info")
    last_updated = _str(state_report.get("last_updated")) or "-"
    updated_badge = badge(f"最後更新：{last_updated}", tone="info")
    return f'<div class="wb-status-line">{status_badges}{stale_badge}{updated_badge}</div>'


def _bulk_tools_bar(state_path: str, *, action_api_enabled: bool) -> str:
    # Feature C (spec 3.3 "批次操作"): ported from
    # dashboard.py:_review_action_bulk_tools (~line 2973-2981) -- same labels
    # (選取目前顯示 / 批次標記完成 / 批次稍後處理 / 已選取 N 筆). Served-mode buttons
    # reuse the page-wide data-action-api dispatch convention
    # (page_script.py:initActionApi) with a new "bulk-review-action" kind,
    # carrying the same state_path the per-row served buttons already emit
    # (_row_action_button); static-mode buttons carry no data-action-api and
    # are driven entirely by each selected row's own data-command-<status>
    # attribute from _row_select_checkbox.
    buttons: list[str] = []
    for status, label in _BULK_STATUSES:
        if action_api_enabled:
            buttons.append(
                '<button type="button" class="ui-btn" data-action-api="bulk-review-action"'
                f' data-queue-bulk-status="{esc(status)}" data-state-path="{esc(state_path)}">{esc(label)}</button>'
            )
        else:
            buttons.append(
                f'<button type="button" class="ui-btn" data-queue-bulk-status="{esc(status)}">{esc(label)}</button>'
            )
    return (
        '<div class="wb-bulk-tools" data-queue-bulk-tools="true">'
        '<label class="wb-bulk-select-all">'
        '<input type="checkbox" data-queue-select-visible="true">選取目前顯示'
        "</label>"
        f'{"".join(buttons)}'
        '<span class="wb-bulk-count" data-queue-bulk-count="true">已選取 0 筆</span>'
        "</div>"
    )


def _queue_card(
    rows: list[dict[str, str]],
    source_path: str,
    state_path: str,
    state_report: dict[str, Any],
    *,
    action_api_enabled: bool,
) -> str:
    if not rows:
        return card("審查佇列", '<p class="wb-empty">目前無待辦。</p>')

    header = (
        '<div class="queue-row head">'
        "<span></span><span></span><span>股票</span><span>優先</span><span>嚴重度</span>"
        "<span>類別</span><span>事項</span><span>操作</span>"
        "</div>"
    )
    blocks = "".join(
        _queue_row_block(row, index, source_path, state_path, action_api_enabled=action_api_enabled)
        for index, row in enumerate(rows)
    )
    note = f'<p class="wb-queue-note">共 {esc(len(rows))} 筆（依優先度 → 嚴重度排序）。</p>'
    body = (
        f"{_queue_status_line(state_report)}"
        f"{_filters_bar()}"
        f"{_bulk_tools_bar(state_path, action_api_enabled=action_api_enabled)}"
        f'<div class="queue">{header}{blocks}</div>'
        f"{note}"
    )
    return card("審查佇列", body)


def _report_link_index(entries: Any, *, path_field: str) -> dict[str, str]:
    index: dict[str, str] = {}
    if not isinstance(entries, list):
        return index
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        stock_id = _str(entry.get("stock_id"))
        path = _str(entry.get(path_field))
        if stock_id and path:
            index[stock_id] = path
    return index


def _pool_row(entry: dict[str, Any], report_links: dict[str, str], memo_links: dict[str, str]) -> str:
    stock_id = _str(entry.get("stock_id")) or "-"
    company_name = _str(entry.get("company_name"))
    stock_text = stock_id if not company_name else f"{stock_id} {company_name}"
    priority = _str(entry.get("priority"))
    research_state = _str(entry.get("research_state")) or "-"
    reliability = _str(entry.get("reliability_status"))
    reasons = entry.get("attention_reasons")

    priority_badge = badge(
        REVIEW_ACTION_PRIORITY_LABELS.get(priority, priority or "-"), tone=_PRIORITY_TONES.get(priority, "info")
    )
    reliability_label = REVIEW_ACTION_SEVERITY_LABELS.get(reliability, reliability or "-")
    reliability_badge = badge(reliability_label, tone=_RELIABILITY_TONES.get(reliability, "info"))
    reasons_text = " · ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else ""

    links: list[str] = []
    report_path = report_links.get(stock_id, "")
    if report_path:
        links.append(f'<a href="{esc(report_path)}">分析</a>')
    memo_path = memo_links.get(stock_id, "")
    if memo_path:
        links.append(f'<a href="{esc(memo_path)}">備忘錄</a>')
    links_html = " · ".join(links) if links else "-"

    return (
        "<tr>"
        f'<td class="mono">{esc(stock_text)}</td>'
        f"<td>{priority_badge}</td>"
        f"<td>{esc(research_state)}</td>"
        f"<td>{reliability_badge}</td>"
        f"<td>{esc(reasons_text) if reasons_text else '-'}</td>"
        f"<td>{links_html}</td>"
        "</tr>"
    )


def _pool_card(pool: list[Any], dashboard_items: dict[str, Any]) -> str:
    entries = [entry for entry in pool if isinstance(entry, dict)]
    if not entries:
        return card("研究池", '<p class="wb-empty">尚無研究項目。</p>')
    report_links = _report_link_index(dashboard_items.get("reports"), path_field="html_path")
    memo_links = _report_link_index(dashboard_items.get("memo_outputs"), path_field="html_path")
    rows_html = "".join(_pool_row(entry, report_links, memo_links) for entry in entries)
    body = (
        '<div class="table-scroll">'
        '<table class="mini-table">'
        "<thead><tr><th>股票</th><th>優先</th><th>研究狀態</th><th>可信度</th><th>注意原因</th><th>報告</th></tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        "</div>"
    )
    return card("研究池", body)


def render_workbench_view(items: dict[str, Any], *, action_api_enabled: bool = False) -> str:
    summaries = items.get("research_summaries")
    summary = _first_valid_summary(summaries if isinstance(summaries, list) else [])
    if summary is None:
        return card("研究工作台", '<p class="wb-empty">尚無 research summary。</p>')

    state = summary.get("review_action_state")
    state = state if isinstance(state, dict) else None
    raw_queue = summary.get("review_action_queue")
    raw_queue = raw_queue if isinstance(raw_queue, list) else []
    pool = summary.get("items")
    pool = pool if isinstance(pool, list) else []

    gate = build_handoff_quality_gate(summary, state, blocker_limit=3, evidence_base_dir=_base_dir(summary))
    source_path = _str(summary.get("path"))
    state_path = _state_path(summary)

    overlaid_queue = apply_review_action_state(raw_queue, state)
    rows = _flatten_rows(overlaid_queue)
    rows.sort(key=_row_sort_key)
    # Feature D: build_review_action_state_report takes the *raw* (non-overlaid)
    # queue -- it overlays state internally -- and reports counts/staleness/
    # last-updated in one call; see review_action_state.py.
    state_report = _dict(build_review_action_state_report(raw_queue, state))

    gate_card = _gate_card(gate, rows, source_path, state_path, summary, action_api_enabled=action_api_enabled)
    queue_card = _queue_card(rows, source_path, state_path, state_report, action_api_enabled=action_api_enabled)
    pool_card = _pool_card(pool, items)
    return gate_card + queue_card + pool_card
