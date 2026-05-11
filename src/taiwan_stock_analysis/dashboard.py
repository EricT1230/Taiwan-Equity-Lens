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


def _link(path: str, label: str) -> str:
    if not path:
        return "-"
    return f'<a href="{escape(path)}">{escape(label)}</a>'


def render_dashboard_html(items: DashboardItems) -> str:
    report_count = len(items.get("reports", []))
    comparison_count = len(items.get("comparisons", []))
    batch_results = [
        result
        for summary in items.get("batch_summaries", [])
        for result in summary.get("results", [])
    ]
    batch_count = len(batch_results)
    batch_error_count = sum(1 for result in batch_results if result.get("status") == "error")
    report_rows = "".join(
        "<tr>"
        f"<td>{escape(report['stock_id'])}</td>"
        f"<td>{_link(report.get('html_path', ''), Path(report.get('html_path', '')).name)}</td>"
        f"<td>{_link(report.get('json_path', ''), Path(report.get('json_path', '')).name)}</td>"
        "</tr>"
        for report in items.get("reports", [])
    )
    comparison_rows = "".join(
        "<tr>"
        f"<td>{_link(comparison.get('html_path', ''), Path(comparison.get('html_path', '')).name)}</td>"
        f"<td>{_link(comparison.get('json_path', ''), Path(comparison.get('json_path', '')).name)}</td>"
        "</tr>"
        for comparison in items.get("comparisons", [])
    )
    batch_rows = "".join(
        "<tr>"
        f"<td>{escape(summary.get('path', ''))}</td>"
        f"<td>{escape(result.get('stock_id', '-'))}</td>"
        f"<td>{escape(result.get('status', '-'))}</td>"
        f"<td>{escape(result.get('error', ''))}</td>"
        "</tr>"
        for summary in items.get("batch_summaries", [])
        for result in summary.get("results", [])
    )
    workflow_rows = _workflow_summary_rows(items.get("workflow_summaries", []))
    watchlist_template = "data:text/csv;charset=utf-8,stock_id%2Ccompany_name%0A2330%2C%E5%8F%B0%E7%A9%8D%E9%9B%BB%0A2303%2C%E8%81%AF%E9%9B%BB%0A"
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>台股基本面工具</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif; background: #f6f8fb; color: #1f2937; }}
    header {{ background: #12355b; color: white; padding: 24px 32px; }}
    main {{ padding: 24px 32px; max-width: 1200px; margin: 0 auto; }}
    section {{ background: white; border-radius: 8px; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08); }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; }}
    .summary div {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; background: #fbfdff; }}
    .summary strong {{ display: block; font-size: 28px; color: #12355b; }}
    .workflow {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }}
    .tool {{ border: 1px solid #d8dee8; border-radius: 8px; padding: 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 10px; text-align: left; }}
    th {{ background: #e8eef7; }}
    input {{ padding: 8px; margin-right: 8px; border: 1px solid #cbd5e1; border-radius: 6px; }}
    code {{ display: block; margin-top: 12px; padding: 12px; background: #0f172a; color: #e5e7eb; border-radius: 6px; overflow-x: auto; }}
  </style>
</head>
<body>
  <header><h1>台股基本面工具</h1></header>
  <main>
    <section class="summary" aria-label="輸出摘要">
      <div id="summaryReports"><strong>{report_count}</strong><span>單股報表</span></div>
      <div id="summaryComparisons"><strong>{comparison_count}</strong><span>同業比較</span></div>
      <div id="summaryBatchItems"><strong>{batch_count}</strong><span>批次項目</span></div>
      <div id="summaryBatchErrors"><strong>{batch_error_count}</strong><span>批次錯誤</span></div>
    </section>
    <section>
      <h2>新增單股分析</h2>
      <input id="stockInput" placeholder="股票代碼，例如 2330">
      <input id="nameInput" placeholder="公司名稱，例如 台積電">
      <code id="commandOutput">python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --output-dir dist</code>
    </section>
    <section>
      <h2>Workflow 工具</h2>
      <div class="workflow">
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
    <section>
      <h2>單股報表</h2>
      <table><thead><tr><th>股票代碼</th><th>HTML</th><th>JSON</th></tr></thead><tbody>{report_rows}</tbody></table>
    </section>
    <section>
      <h2>同業比較</h2>
      <table><thead><tr><th>HTML</th><th>JSON</th></tr></thead><tbody>{comparison_rows}</tbody></table>
    </section>
    <section>
      <h2>批次狀態</h2>
      <table><thead><tr><th>Summary</th><th>股票代碼</th><th>狀態</th><th>錯誤</th></tr></thead><tbody>{batch_rows}</tbody></table>
    </section>
    <section>
      <h2>Workflow Summary</h2>
      <table><thead><tr><th>Summary</th><th>Watchlist</th><th>Successful stocks</th><th>Valuation CSV</th><th>Dashboard</th><th>Comparison</th><th>Note</th></tr></thead><tbody>{workflow_rows}</tbody></table>
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


def _workflow_summary_rows(workflow_summaries: list[dict[str, Any]]) -> str:
    if not workflow_summaries:
        return '<tr><td colspan="7">No workflow summary found</td></tr>'

    rows = []
    for summary in workflow_summaries:
        paths = summary.get("paths", {})
        paths = paths if isinstance(paths, dict) else {}
        comparison = paths.get("comparison", {})
        comparison = comparison if isinstance(comparison, dict) else {}
        successful_stock_ids = summary.get("successful_stock_ids", [])
        successful_stock_ids = successful_stock_ids if isinstance(successful_stock_ids, list) else []
        note = summary.get("error") or summary.get("comparison_skipped_reason") or ""
        rows.append(
            "<tr>"
            f"<td>{_link(str(summary.get('path', '')), Path(str(summary.get('path', ''))).name)}</td>"
            f"<td>{escape(str(summary.get('watchlist_path', '')))}</td>"
            f"<td>{escape(', '.join(str(stock_id) for stock_id in successful_stock_ids) or '-')}</td>"
            f"<td>{_link(str(paths.get('valuation_csv', '')), Path(str(paths.get('valuation_csv', ''))).name)}</td>"
            f"<td>{_link(str(paths.get('dashboard', '')), Path(str(paths.get('dashboard', ''))).name)}</td>"
            f"<td>{_link(str(comparison.get('html', '')), Path(str(comparison.get('html', ''))).name)}</td>"
            f"<td>{escape(str(note))}</td>"
            "</tr>"
        )
    return "".join(rows)


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
        target[field] = os.path.relpath(Path(value).resolve(), base_dir.resolve())
