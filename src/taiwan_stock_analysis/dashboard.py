from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.handoff import build_handoff_quality_gate
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
        packs_dir = directory / "packs"
        if packs_dir.exists():
            _discover_pack_outputs(packs_dir, items)
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
    .expert-console-next {{ display: inline-flex; align-items: center; gap: 6px; padding: 8px 11px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; color: #12355b; cursor: pointer; }}
    .expert-console-next:hover {{ background: #eef4fb; }}
    .expert-console-next[data-status-value="done"], .expert-console-next[data-expert-console-bulk-status="done"] {{ background: #dcfce7; border-color: #86efac; color: #166534; }}
    .expert-console-next[data-status-value="done"]:hover, .expert-console-next[data-expert-console-bulk-status="done"]:hover {{ background: #bbf7d0; }}
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
    function reviewActionRows(section) {{
      return Array.from(section.querySelectorAll('[data-review-action-row="true"]'));
    }}
    function syncExpertConsole(section) {{
      const consoleBlock = expertConsoleForSection(section);
      if (!consoleBlock) {{
        return;
      }}
      const rows = reviewActionRows(section);
      const openRows = rows.filter((row) => (row.dataset.status || 'open') === 'open');
      const staleNode = section.querySelector('[data-review-action-stale-count="true"]');
      const staleCount = Number(staleNode ? staleNode.dataset.reviewActionStaleCountValue || '0' : '0');
      const missingGateCount = Number(consoleBlock.dataset.expertConsoleMissingGateCount || '0');
      const blocked = openRows.length > 0 || staleCount > 0 || missingGateCount > 0;
      consoleBlock.dataset.expertConsoleHandoffStatus = blocked ? 'blocked' : 'ready';
      consoleBlock.dataset.expertConsoleOpenCount = String(openRows.length);
      consoleBlock.dataset.expertConsoleStaleCount = String(staleCount);
      consoleBlock.dataset.expertConsoleMissingGateCount = String(missingGateCount);
      const readiness = consoleBlock.querySelector('[data-expert-console-readiness="true"]');
      if (readiness) {{
        readiness.classList.toggle('blocked', blocked);
        readiness.classList.toggle('ready', !blocked);
        readiness.textContent = blocked
          ? `交接狀態：尚未可交接，原因：Handoff Gate 有 ${{openRows.length + staleCount + missingGateCount}} 件阻塞`
          : '交接狀態：可進入人工交付審查';
      }}
      const nextStep = consoleBlock.querySelector('[data-expert-console-next-step="true"]');
      if (nextStep) {{
        if (missingGateCount > 0) {{
          nextStep.textContent = '下一步：先重新產生 research_summary.json，避免靜默遺漏 handoff gate。';
        }} else if (openRows.length > 0) {{
          nextStep.textContent = '下一步：先處理 Top 3 阻塞事項，再回到審查動作表確認剩餘事項。';
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
        if (row) {{
          row.dataset.status = result.status || payload.status;
          const statusCell = row.querySelector('[data-review-action-status-cell="true"]');
          if (statusCell) {{
            statusCell.textContent = reviewActionStatusLabel(result.status || payload.status);
          }}
        }}
        updateReviewActionSummary(button, result);
        const taskResult = expertConsoleTaskResultForButton(button);
        if (taskResult) {{
          taskResult.textContent = `處理結果：已標記為${{reviewActionStatusLabel(result.status || payload.status)}}。`;
        }}
        if (!options.bulk) {{
          showReviewActionApiResult(button, result);
        }}
        if (section && section.reviewActionApplyFilters) {{
          section.reviewActionApplyFilters();
        }}
        if (section) {{
          syncExpertConsole(section);
        }}
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
    initReviewActionFilters();
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
    gate = build_handoff_quality_gate(summary, state, blocker_limit=3)
    blockers = gate.get("top_blockers", [])
    top_blockers = blockers if isinstance(blockers, list) else []
    total_actions = int(gate.get("total_actions") or 0)
    ready = bool(gate.get("ready"))
    blocker_count = int(gate.get("blocker_count") or 0)
    open_count = int(gate.get("open_count") or 0)
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
    feedback_text = "等待處理 Top 3 阻塞事項。" if top_blockers else "目前沒有 Top 3 阻塞事項。"
    escaped_source_path = escape(source_path)
    return (
        f'<div class="expert-console-grid" data-expert-console-source-path="{escaped_source_path}"'
        f' data-expert-console-handoff-status="{escape(str(gate.get("status") or ""))}"'
        f' data-expert-console-open-count="{escape(str(open_count))}"'
        f' data-expert-console-stale-count="{escape(str(stale_count))}"'
        f' data-expert-console-missing-gate-count="{escape(str(missing_gate_count))}">'
        '<div class="expert-console-panel">'
        "<h3>\u7814\u7a76\u4ea4\u4ed8\u72c0\u614b</h3>"
        f'<p><span class="expert-console-readiness {readiness_class}" '
        f'data-expert-console-readiness="true">{escape(readiness_text)}</span></p>'
        f'<p class="status-line"><span class="badge">\u4f86\u6e90\uff1a{source_link}</span>'
        f'<span class="badge">\u5be9\u67e5\u52d5\u4f5c\uff1a{escape(str(total_actions))}</span>'
        f'<span class="badge">Gate \u963b\u585e\uff1a{escape(str(blocker_count))}</span></p>'
        f'<p data-expert-console-next-step="true">{escape(next_step)}</p>'
        f"{toolbar}"
        f'<p class="expert-console-feedback" data-expert-console-feedback="true">{escape(feedback_text)}</p>'
        f"{sync_note}"
        "</div>"
        '<div class="expert-console-panel">'
        "<h3>\u512a\u5148\u8655\u7406\u7684 3 \u4ef6\u5f85\u67e5\u4e8b\u9805</h3>"
        f"{_expert_console_action_list(top_blockers, source_path, state_path)}"
        "</div>"
        "</div>"
    )


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
    focus_available = action.get("focus_available", "true") == "true" and bool(action_id)
    focus_search = _expert_console_focus_search(action)
    title = stock_id if not company_name else f"{stock_id} {company_name}"
    next_copy = (
        "先確認這個阻塞，處理完可直接標記完成；需要保留但不阻塞時標記稍後處理。"
        if focus_available
        else action.get("next_step", "請執行 handoff doctor 後重新產生 dashboard。")
    )
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
    return (
        '<li class="expert-console-action" data-expert-console-task="true">'
        '<div class="expert-console-meta">'
        f'<span class="badge">{escape(action.get("expert_label") or _expert_agent_label(category))}</span>'
        f'<span class="badge">{escape(_review_label(severity, REVIEW_ACTION_SEVERITY_LABELS))}</span>'
        f'<span class="badge">{escape(_review_label(priority, REVIEW_ACTION_PRIORITY_LABELS))}</span>'
        "</div>"
        f'<strong class="expert-console-task-title">{escape(title)}</strong>'
        f'<p class="expert-console-task-copy"><strong>問題：</strong>{escape(action.get("message", ""))}</p>'
        f'<p class="expert-console-task-copy" data-expert-console-next-copy="true"><strong>建議處理：</strong>{escape(next_copy)}</p>'
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
    command = _review_action_state_command(state_path, stock_id, action_id, status)
    return (
        '<button type="button" class="expert-console-next" data-expert-console-action-command="true"'
        f' data-expert-console-source-path="{escape(source_path)}"'
        f' data-review-actions-source-path="{escape(source_path)}"'
        f' data-state-path="{escape(state_path)}"'
        f' data-stock-id="{escape(stock_id)}"'
        f' data-action-id="{escape(action_id)}"'
        f' data-status-value="{escape(status)}"'
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
                f' data-search-text="{escape(search_text)}">'
                '<td class="review-action-select-cell"><input type="checkbox" data-review-action-select-row="true" aria-label="選取審查動作"></td>'
                f"<td>{escape(stock_id)}</td>"
                f"<td>{escape(priority_label)}</td>"
                f'<td><span class="review-action-status" data-review-action-status-cell="true">{escape(status_label)}</span></td>'
                f"<td>{escape(severity_label)}</td>"
                f"<td>{escape(category_label)}</td>"
                f"<td>{escape(user_message)}{_review_action_state_metadata(action)}</td>"
                f"<td>{_review_action_command_cell(state_path, stock_id, action_id)}</td>"
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


def _review_action_state_metadata(action: dict[str, Any]) -> str:
    details = []
    note = str(action.get("note") or "").strip()
    updated_at = str(action.get("updated_at") or "").strip()
    if note:
        details.append(f"備註：{escape(note)}")
    if updated_at:
        details.append(f"更新：{escape(updated_at)}")
    if not details:
        return ""
    return f'<div class="review-action-state-meta">{" | ".join(details)}</div>'


def _review_action_command_cell(state_path: str, stock_id: str, action_id: str) -> str:
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
            f' data-command="{escape(command)}">'
            f"{escape(display_label)}"
            "</button>"
        )
    return (
        f'<div class="review-action-commands">{"".join(buttons)}</div>'
        '<details class="review-action-detail">'
        '<summary>指令 / API 詳細資訊</summary>'
        f'<code class="review-action-command-fallback">{escape(os.linesep.join(fallback_lines))}</code>'
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


def _relativize_fields(target: dict[str, Any], fields: list[str], base_dir: Path) -> None:
    for field in fields:
        value = target.get(field)
        if not isinstance(value, str) or not value:
            continue
        target[field] = os.path.relpath(Path(value).resolve(), base_dir.resolve()).replace(os.sep, "/")
