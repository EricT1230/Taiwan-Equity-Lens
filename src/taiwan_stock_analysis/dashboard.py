from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any


DashboardItems = dict[str, list[dict[str, Any]]]


def discover_dashboard_items(search_dirs: list[Path]) -> DashboardItems:
    items: DashboardItems = {
        "reports": [],
        "comparisons": [],
        "batch_summaries": [],
        "workflow_summaries": [],
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
    return items


def render_dashboard_html(items: DashboardItems) -> str:
    report_count = len(items.get("reports", []))
    comparison_count = len(items.get("comparisons", []))
    batch_results = _batch_results(items)
    batch_count = len(batch_results)
    batch_error_count = sum(1 for result in batch_results if result.get("status") == "error")
    workflow_count = len(items.get("workflow_summaries", []))
    watchlist_template = "data:text/csv;charset=utf-8,stock_id%2Ccompany_name%0A2330%2C%E5%8F%B0%E7%A9%8D%E9%9B%BB%0A2303%2C%E8%81%AF%E9%9B%BB%0A"

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
      <div id="summaryWorkflows"><strong>{workflow_count}</strong><span>Workflow summary</span></div>
    </section>
    <section>
      <h2>Workflow 狀態</h2>
      {_workflow_status_line(items.get("workflow_summaries", []))}
      <table><thead><tr><th>Summary</th><th>Watchlist</th><th>成功股票</th><th>估值 CSV</th><th>Dashboard</th><th>同業比較</th><th>備註</th></tr></thead><tbody>{_workflow_summary_rows(items.get("workflow_summaries", []))}</tbody></table>
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
    stockInput.addEventListener('input', updateCommand);
    nameInput.addEventListener('input', updateCommand);
    compareInput.addEventListener('input', updateCompareCommand);
    batchPathInput.addEventListener('input', updateBatchCommand);
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
        return _empty_row(7, "尚無 workflow summary。執行 workflow 後會顯示 watchlist、估值 CSV 與比較結果。")

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


def write_dashboard_index(search_dirs: list[Path], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    items = discover_dashboard_items(search_dirs)
    _make_links_relative(items, output_path.parent)
    output_path.write_text(render_dashboard_html(items), encoding="utf-8")
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


def _relativize_fields(target: dict[str, Any], fields: list[str], base_dir: Path) -> None:
    for field in fields:
        value = target.get(field)
        if not isinstance(value, str) or not value:
            continue
        target[field] = os.path.relpath(Path(value).resolve(), base_dir.resolve()).replace(os.sep, "/")
