from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import badge, card, copy_button, esc

# This view is Tab 3 (產出與紀錄) of the redesigned dashboard. It replaces
# dashboard.py's five per-category output <section>s (研究備忘錄/研究包/Handoff
# Evidence Pack/個股報告/同業比較), its Workflow/批次/資料可信度/來源稽核 sections,
# `_market_data_section`, and the 常用指令 tool grid with card()-wrapped
# table-scroll/mini-table fragments matching Tasks 7-8's visual language.
#
# Field extraction is *ported* (duplicated, not imported) from dashboard.py's private
# renderers (`_report_rows`, `_comparison_rows`, `_memo_rows`, `_pack_rows`,
# `_handoff_pack_rows`, `_workflow_summary_rows`, `_batch_rows`,
# `_workflow_reliability_summary`, `_workflow_source_audit_section`,
# `_source_audit_components`, `_market_data_section`) -- importing from dashboard.py
# itself is exactly the import cycle labels.py/this package exist to avoid
# (dashboard.py will eventually import page.py -> views.* per Task 11).
#
# The watchlist CSV data-URI is copied verbatim from dashboard.py:327 rather than
# imported, per the same cycle-avoidance rule.
_WATCHLIST_TEMPLATE = "data:text/csv;charset=utf-8,stock_id%2Ccompany_name%0A2330%2C%E5%8F%B0%E7%A9%8D%E9%9B%BB%0A2303%2C%E8%81%AF%E9%9B%BB%0A"

_SINGLE_STOCK_COMMAND = "python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --output-dir dist"
_COMPARISON_COMMAND = "python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist"
_BATCH_COMMAND = "python -m taiwan_stock_analysis.cli batch watchlist.csv --output-dir batch-dist"

_BATCH_STATUS_TONES = {"ok": "ok", "error": "blocked"}
# Dual use: looked up both by reliability *metric key* (ok/warning/error/skipped) and
# by `data_reliability.overall_status`'s *value* -- both vocabularies coincide exactly.
_RELIABILITY_TONES = {"ok": "ok", "warning": "warn", "error": "blocked", "skipped": "info"}
_SOURCE_AUDIT_STATUS_TONES = {
    "manual_review": "blocked",
    "stale": "warn",
    "unknown": "info",
    "fresh": "ok",
    "ok": "ok",
    "error": "blocked",
    "warning": "warn",
}
_GATE_STATUS_TONES = {"ready": "ok", "needs_data": "warn"}


def _str(value: Any) -> str:
    return str(value) if value is not None else ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(container: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = container.get(key) if isinstance(container, dict) else None
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _list_value(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _link(path: Any, label: str = "") -> str:
    text = _str(path).strip()
    if not text:
        return "-"
    display = label or Path(text).name or text
    return f'<a href="{esc(text)}">{esc(display)}</a>'


def _table(headers: list[str], body_rows: str) -> str:
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    return (
        '<div class="table-scroll"><table class="mini-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div>"
    )


def _link_table_card(
    title: str,
    headers: list[str],
    entries: list[dict[str, Any]],
    row_fn: Callable[[dict[str, Any]], str],
    empty_message: str,
) -> str:
    if not entries:
        return card(title, f'<p class="out-empty">{esc(empty_message)}</p>')
    body_rows = "".join(row_fn(entry) for entry in entries)
    return card(title, _table(headers, body_rows))


# ---------------------------------------------------------------------------
# 產出檔案：個股報告 / 同業比較 / 研究備忘錄 / 研究包 / Handoff Evidence Pack
# ---------------------------------------------------------------------------


def _report_row(report: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{esc(report.get('stock_id', '-'))}</td>"
        f"<td>{_link(report.get('html_path'))}</td>"
        f"<td>{_link(report.get('json_path'))}</td>"
        "</tr>"
    )


def _reports_card(items: dict[str, Any]) -> str:
    return _link_table_card(
        "個股報告",
        ["股票代碼", "HTML", "JSON"],
        _rows(items, "reports"),
        _report_row,
        "尚未產生個股報告。請先執行單一個股、batch 或 workflow 指令。",
    )


def _comparison_output_row(comparison: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_link(comparison.get('html_path'))}</td>"
        f"<td>{_link(comparison.get('json_path'))}</td>"
        "</tr>"
    )


def _comparisons_card(items: dict[str, Any]) -> str:
    return _link_table_card(
        "同業比較",
        ["HTML", "JSON"],
        _rows(items, "comparisons"),
        _comparison_output_row,
        "尚未產生同業比較。至少兩檔成功分析後才會產生 comparison。",
    )


def _memo_row(output: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{esc(output.get('stock_id', '-'))}</td>"
        f"<td>{_link(output.get('markdown_path'))}</td>"
        f"<td>{_link(output.get('html_path'))}</td>"
        f"<td>{_link(output.get('summary_path'))}</td>"
        "</tr>"
    )


def _memos_card(items: dict[str, Any]) -> str:
    return _link_table_card(
        "研究備忘錄",
        ["股票代碼", "Markdown", "HTML", "摘要"],
        _rows(items, "memo_outputs"),
        _memo_row,
        "尚未產生研究備忘錄。",
    )


def _pack_row(output: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_link(output.get('markdown_path'))}</td>"
        f"<td>{_link(output.get('html_path'))}</td>"
        f"<td>{_link(output.get('summary_path'))}</td>"
        "</tr>"
    )


def _packs_card(items: dict[str, Any]) -> str:
    return _link_table_card(
        "研究包",
        ["Markdown", "HTML", "摘要"],
        _rows(items, "pack_outputs"),
        _pack_row,
        "尚未產生研究包。",
    )


def _handoff_pack_row(output: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{esc(output.get('gate_status', '-'))}</td>"
        f"<td>{esc(output.get('ready', '-'))}</td>"
        f"<td>{esc(output.get('blocker_count', '-'))}</td>"
        f"<td>{esc(output.get('evidence_missing_count', '-'))}</td>"
        f"<td>{esc(output.get('invalid_evidence_count', '-'))}</td>"
        f"<td>{_link(output.get('markdown_path'))}</td>"
        f"<td>{_link(output.get('html_path'))}</td>"
        f"<td>{_link(output.get('summary_path'))}</td>"
        "</tr>"
    )


def _handoff_pack_card(items: dict[str, Any]) -> str:
    return _link_table_card(
        "Handoff Evidence Pack",
        ["Status", "Ready", "Blockers", "Missing evidence", "Invalid evidence", "Markdown", "HTML", "Summary"],
        _rows(items, "handoff_pack_outputs"),
        _handoff_pack_row,
        "尚未產生 Handoff Evidence Pack。",
    )


def _gate_tone(status: str) -> str:
    return {"ready": "ok", "blocked": "blocked"}.get(status, "warn")


def _intelligence_report_row(name: str, report: dict[str, Any], summary: str) -> str:
    gate = _dict(report.get("quality_gate"))
    status = _str(gate.get("status")) or "unknown"
    return (
        "<tr>"
        f"<td>{esc(name)}</td>"
        f"<td>{badge('gate: ' + status, tone=_gate_tone(status))}</td>"
        f"<td>{esc(summary)}</td>"
        f"<td>{_link(report.get('html_path'))}</td>"
        f"<td>{_link(report.get('markdown_path'))}</td>"
        f"<td>{_link(report.get('path'))}</td>"
        "</tr>"
    )


def _intelligence_reports_card(items: dict[str, Any]) -> str:
    # Spec §10 "MI 與產業趨勢報告連結及 gate chips": discover_dashboard_items
    # collects these reports' paths + quality_gate/coverage, but no other view links
    # to them. Surface them here in the 產出與紀錄 tab.
    rows: list[str] = []
    for report in _rows(items, "market_intelligence_reports"):
        coverage = _dict(report.get("coverage"))
        summary = (
            f"news {_str(coverage.get('news_mapped', 0))}/{_str(coverage.get('news_total', 0))}"
            f" · fund-flow {_str(coverage.get('stocks_with_fund_flow', 0))}/{_str(coverage.get('stocks_total', 0))}"
        )
        rows.append(_intelligence_report_row("Market Intelligence", report, summary))
    for report in _rows(items, "industry_trend_reports"):
        coverage = _dict(report.get("coverage"))
        as_of = _str(report.get("as_of_date"))
        price = f"price {_str(coverage.get('stocks_with_price_history', 0))}/{_str(coverage.get('stocks_total', 0))}"
        summary = f"as of {as_of} · {price}" if as_of else price
        rows.append(_intelligence_report_row("Industry Trend", report, summary))
    if not rows:
        return card(
            "市場情報與產業趨勢報告",
            '<p class="out-empty">尚未產生市場情報或產業趨勢報告。</p>',
        )
    headers = ["報告", "品質", "覆蓋", "HTML", "Markdown", "JSON"]
    return card("市場情報與產業趨勢報告", _table(headers, "".join(rows)))


def _files_section(items: dict[str, Any]) -> str:
    cards = (
        _reports_card(items)
        + _comparisons_card(items)
        + _intelligence_reports_card(items)
        + _memos_card(items)
        + _packs_card(items)
        + _handoff_pack_card(items)
    )
    return f'<section class="out-section" data-outputs-files-section="true"><h2>產出檔案</h2>{cards}</section>'


# ---------------------------------------------------------------------------
# 狀態紀錄：Workflow 狀態 / 批次狀態 / 資料可信度 / 來源稽核
# ---------------------------------------------------------------------------


def _run_id(summary: dict[str, Any]) -> str:
    return _str(_dict(summary.get("run_metadata")).get("run_id"))


def _comparison_note(summary: dict[str, Any], comparison: dict[str, Any]) -> str:
    skipped = _str(summary.get("comparison_skipped_reason")).strip()
    if skipped:
        return f"同業比較略過：{skipped}"
    if comparison:
        return "同業比較已產生"
    return ""


def _comparison_link(comparison: dict[str, Any]) -> str:
    links = [link for link in (_link(comparison.get("html")), _link(comparison.get("json"))) if link != "-"]
    return " / ".join(links) if links else "-"


def _workflow_row(summary: dict[str, Any]) -> str:
    paths = _dict(summary.get("paths"))
    comparison = _dict(paths.get("comparison"))
    successful = _list_value(summary.get("successful_stock_ids"))
    stock_ids = _list_value(summary.get("stock_ids"))
    note = _str(summary.get("error")) or _comparison_note(summary, comparison)
    return (
        "<tr>"
        f"<td>{_link(summary.get('path'))}</td>"
        f"<td>{esc(_run_id(summary) or '-')}</td>"
        f"<td>{esc(summary.get('watchlist_path') or '-')}</td>"
        f"<td>成功 {len(successful)} / {len(stock_ids)}<br>{esc(', '.join(successful) or '-')}</td>"
        f"<td>{_link(paths.get('valuation_csv'))}</td>"
        f"<td>{_link(paths.get('dashboard'))}</td>"
        f"<td>{_comparison_link(comparison)}</td>"
        f"<td>{esc(note)}</td>"
        "</tr>"
    )


def _workflow_card(items: dict[str, Any]) -> str:
    summaries = _rows(items, "workflow_summaries")
    if not summaries:
        return card(
            "Workflow 狀態",
            '<p class="out-empty">尚未有 workflow summary。執行 workflow 後會顯示 watchlist、估值 CSV 與比較結果。</p>',
        )
    headers = ["Summary", "Run ID", "Watchlist", "成功股票", "估值 CSV", "Dashboard", "同業比較", "備註"]
    body_rows = "".join(_workflow_row(summary) for summary in summaries)
    return card("Workflow 狀態", _table(headers, body_rows))


def _batch_result_row(summary_path: str, result: dict[str, Any]) -> str:
    status = _str(result.get("status"))
    return (
        "<tr>"
        f"<td>{esc(summary_path)}</td>"
        f"<td>{esc(result.get('stock_id', '-'))}</td>"
        f"<td>{badge(status or '-', tone=_BATCH_STATUS_TONES.get(status, 'info'))}</td>"
        f"<td>{esc(result.get('error', ''))}</td>"
        "</tr>"
    )


def _batch_card(items: dict[str, Any]) -> str:
    summaries = _rows(items, "batch_summaries")
    if not summaries:
        return card("批次狀態", '<p class="out-empty">尚未有批次結果。請先執行 batch 或 workflow 指令。</p>')

    body_rows: list[str] = []
    ok_count = 0
    error_count = 0
    total_count = 0
    for summary in summaries:
        summary_path = _str(summary.get("path"))
        results = summary.get("results")
        results = [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []
        if not results:
            body_rows.append(
                f'<tr><td>{esc(summary_path)}</td><td colspan="3" class="out-empty-cell">尚無批次結果。</td></tr>'
            )
            continue
        for result in results:
            total_count += 1
            status = _str(result.get("status"))
            if status == "ok":
                ok_count += 1
            elif status == "error":
                error_count += 1
            body_rows.append(_batch_result_row(summary_path, result))

    badges = (
        '<div class="out-badges">'
        f'{badge(f"成功 {ok_count}", tone="ok")}'
        f'{badge(f"失敗 {error_count}", tone="blocked" if error_count else "info")}'
        f'{badge(f"總計 {total_count}", tone="info")}'
        "</div>"
    )
    headers = ["Summary", "股票代碼", "狀態", "錯誤"]
    return card("批次狀態", badges + _table(headers, "".join(body_rows)))


def _reliability_badges(reliability: dict[str, Any]) -> str:
    overall = _str(reliability.get("overall_status")) or "-"
    parts = [badge(f"整體：{overall}", tone=_RELIABILITY_TONES.get(overall, "info"))]
    for key, label in (("ok", "OK"), ("warning", "警示"), ("error", "錯誤"), ("skipped", "略過")):
        parts.append(badge(f"{label} {reliability.get(key, 0)}", tone=_RELIABILITY_TONES.get(key, "info")))
    return f'<div class="out-badges">{"".join(parts)}</div>'


def _failure_row(failure: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{esc(failure.get('stock_id', ''))}</td>"
        f"<td>{esc(failure.get('stage', ''))}</td>"
        f"<td>{esc(failure.get('reason', ''))}</td>"
        f"<td>{esc(failure.get('retry_hint', ''))}</td>"
        "</tr>"
    )


def _reliability_block(summary: dict[str, Any]) -> str:
    if summary.get("error"):
        return f'<p class="out-empty">Workflow summary 讀取失敗：{esc(summary.get("error"))}</p>'
    reliability = _dict(summary.get("data_reliability"))
    failures = summary.get("stock_failures")
    failures = [row for row in failures if isinstance(row, dict)] if isinstance(failures, list) else []
    failure_rows = "".join(_failure_row(failure) for failure in failures) or (
        '<tr><td colspan="4" class="out-empty-cell">沒有失敗股票。</td></tr>'
    )
    headers = ["股票", "階段", "原因", "建議"]
    return f'<p>{_link(summary.get("path"))}</p>{_reliability_badges(reliability)}{_table(headers, failure_rows)}'


def _reliability_card(items: dict[str, Any]) -> str:
    summaries = _rows(items, "workflow_summaries")
    if not summaries:
        return card("資料可信度", '<p class="out-empty">尚未有資料可信度摘要。</p>')
    return card("資料可信度", "".join(_reliability_block(summary) for summary in summaries))


def _source_audit_component_html(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for name, value in item.items():
        if name in {"stock_id", "status"} or not isinstance(value, dict):
            continue
        status = _str(value.get("status"))
        source_mode = _str(value.get("source_mode"))
        reason = _str(value.get("review_reason") or value.get("reason"))
        detail = " | ".join(part for part in (status, source_mode, reason) if part) or "-"
        parts.append(f"<div><strong>{esc(name.replace('_', ' '))}</strong>: {esc(detail)}</div>")
    return "".join(parts) or "-"


def _source_audit_item_row(item: dict[str, Any]) -> str:
    status = _str(item.get("status")) or "unknown"
    return (
        "<tr>"
        f"<td>{esc(item.get('stock_id', '-'))}</td>"
        f"<td>{badge(status, tone=_SOURCE_AUDIT_STATUS_TONES.get(status, 'info'))}</td>"
        f"<td>{_source_audit_component_html(item)}</td>"
        "</tr>"
    )


def _source_audit_counts_text(counts: dict[str, Any]) -> str:
    if not counts:
        return "-"
    pairs = sorted(((str(key), str(value)) for key, value in counts.items()), key=lambda pair: pair[0])
    return ", ".join(f"{esc(key.replace('_', ' '))}: {esc(value)}" for key, value in pairs)


def _source_audit_block(summary: dict[str, Any]) -> str:
    audit = summary.get("source_audit")
    if not isinstance(audit, dict):
        return ""
    counts = _dict(audit.get("counts"))
    entries = audit.get("items")
    entries = [row for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
    status = _str(audit.get("status")) or "unknown"
    body_rows = "".join(_source_audit_item_row(entry) for entry in entries) or (
        '<tr><td colspan="3" class="out-empty-cell">尚無來源稽核項目。</td></tr>'
    )
    badges = (
        '<div class="out-badges">'
        f'{badge(f"整體：{status}", tone=_SOURCE_AUDIT_STATUS_TONES.get(status, "info"))}'
        # _source_audit_counts_text() already HTML-escapes each key/value pair itself
        # (same contract as the ported dashboard.py:_count_pairs) -- do not re-esc() it.
        f"<span>{_source_audit_counts_text(counts)}</span>"
        "</div>"
    )
    headers = ["股票代碼", "狀態", "檢查項目"]
    return f'<p>{_link(summary.get("path"))}</p>{badges}{_table(headers, body_rows)}'


def _source_audit_card(items: dict[str, Any]) -> str:
    summaries = _rows(items, "workflow_summaries")
    blocks = [block for block in (_source_audit_block(summary) for summary in summaries) if block]
    if not blocks:
        return card("來源稽核", '<p class="out-empty">尚未有來源稽核資料。</p>')
    return card("來源稽核", "".join(blocks))


def _status_section(items: dict[str, Any]) -> str:
    cards = _workflow_card(items) + _batch_card(items) + _reliability_card(items) + _source_audit_card(items)
    return f'<section class="out-section" data-outputs-status-section="true"><h2>狀態紀錄</h2>{cards}</section>'


# ---------------------------------------------------------------------------
# Market data bundle -- only rendered when market_data_reports is non-empty
# (unlike the four status tables above, which always render a placeholder).
# ---------------------------------------------------------------------------


def _market_data_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{esc(item.get('stock_id', '-'))}</td>"
        f"<td>{esc(item.get('market', '-'))}</td>"
        f"<td>{esc(item.get('industry_name', '-'))}</td>"
        f"<td>{esc(item.get('price_points', 0))}</td>"
        f"<td>{esc(item.get('price_latest_date', '-'))}</td>"
        f"<td>{'有' if item.get('fund_flow_available') else '無'}</td>"
        "</tr>"
    )


def _market_data_blockers(gate: dict[str, Any]) -> str:
    blockers = gate.get("blockers")
    if not isinstance(blockers, list) or not blockers:
        return ""
    items_html = "".join(f"<li>{esc(value)}</li>" for value in blockers[:8])
    return f"<details><summary>Data blockers</summary><ul>{items_html}</ul></details>"


def _market_data_block(report: dict[str, Any]) -> str:
    title = f"Market Data — {_str(report.get('as_of_date')) or '-'}"
    if report.get("error"):
        body = (
            f'<p>{_link(report.get("path"), "market_data_report.json")}</p>'
            f'<p class="out-empty">{esc(report.get("error"))}</p>'
        )
        return card(title, body)

    coverage = _dict(report.get("coverage"))
    gate = _dict(report.get("quality_gate"))
    entries = report.get("items")
    entries = [row for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
    body_rows = "".join(_market_data_row(entry) for entry in entries) or (
        '<tr><td colspan="6" class="out-empty-cell">尚無官方市場資料列。</td></tr>'
    )
    gate_status = _str(gate.get("status")) or "-"
    stocks_total = coverage.get("stocks_total", 0)
    badges = (
        '<div class="out-badges">'
        f'{badge(f"quality gate: {gate_status}", tone=_GATE_STATUS_TONES.get(gate_status, "info"))}'
        f'<span>as of {esc(report.get("as_of_date", "-"))}</span>'
        f'<span>profiles {esc(coverage.get("official_profile_count", 0))} / {esc(stocks_total)}</span>'
        f'<span>price ready {esc(coverage.get("price_ready_count", 0))} / {esc(stocks_total)}</span>'
        f'<span>fund flow {esc(coverage.get("fund_flow_count", 0))} / {esc(stocks_total)}</span>'
        "</div>"
    )
    headers = ["股票", "市場別", "官方產業", "價格筆數", "最新日期", "法人流向"]
    links = (
        f'<p>{_link(report.get("path"), "market_data_report.json")} '
        f'{_link(report.get("markdown_path"), "Markdown report")}</p>'
    )
    body = links + badges + _table(headers, body_rows) + _market_data_blockers(gate)
    return card(title, body)


def _market_data_section(items: dict[str, Any]) -> str:
    reports = _rows(items, "market_data_reports")
    if not reports:
        return ""
    blocks = "".join(_market_data_block(report) for report in reports)
    return (
        '<section class="out-section" data-outputs-market-data-section="true">'
        "<h2>Official Market Data / 上市櫃產業與行情覆蓋</h2>"
        f"{blocks}"
        "</section>"
    )


# ---------------------------------------------------------------------------
# 常用指令：單一個股 / 同業比較 / 批次分析
# ---------------------------------------------------------------------------


def _command_card(title: str, command: str, extra_html: str = "") -> str:
    body = f'<code class="out-command-code mono">{esc(command)}</code>{extra_html}{copy_button("複製指令", command)}'
    return card(title, body)


def _commands_section() -> str:
    watchlist_link = (
        f'<a class="ui-btn" href="{esc(_WATCHLIST_TEMPLATE)}" download="watchlist-template.csv">'
        "下載 watchlist CSV 範本</a>"
    )
    cards = (
        _command_card("單一個股", _SINGLE_STOCK_COMMAND)
        + _command_card("同業比較", _COMPARISON_COMMAND)
        + _command_card("批次分析", _BATCH_COMMAND, watchlist_link)
    )
    return f'<section class="out-section" data-outputs-commands-section="true"><h2>常用指令</h2>{cards}</section>'


def render_outputs_view(items: dict[str, Any], *, action_api_enabled: bool = False) -> str:
    # action_api_enabled is accepted for signature parity with render_market_view /
    # render_workbench_view (Task 10's page shell calls all three views uniformly).
    # Nothing in this view branches on served vs. static mode: every action here is
    # either a read-only record table or a generic CLI-template copy button, not a
    # stateful review-action/handoff-pack call -- that served-API surface lives in
    # views.workbench.
    del action_api_enabled
    header = (
        '<header class="product-page-head"><div><span class="desk-kicker">TRACEABILITY</span>'
        '<h1>資料與紀錄</h1><p>檢查來源、產出路徑、覆蓋率與可重現指令。</p></div></header>'
    )
    return header + _files_section(items) + _status_section(items) + _market_data_section(items) + _commands_section()
