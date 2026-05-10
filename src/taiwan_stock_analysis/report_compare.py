from __future__ import annotations

import json
from html import escape
from typing import Any


def _fmt(value: float | None, suffix: str = "%") -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}{suffix}"


def render_comparison_html(comparison: dict[str, Any]) -> str:
    dimensions = comparison["dimensions"]
    header_cells = "".join(f"<th>{escape(dimension['label'])}</th>" for dimension in dimensions)
    rows_html = []
    for row in comparison["rows"]:
        metric_cells = "".join(
            f"<td>{escape(_fmt(row.get(dimension['metric'])))}</td>"
            for dimension in dimensions
        )
        rank_cells = "".join(
            f"<td>{escape(str(row.get(dimension['metric'] + '_rank') or '-'))}</td>"
            for dimension in dimensions
        )
        rows_html.append(
            "<tr>"
            f"<td>{escape(row['stock_id'])}</td>"
            f"<td>{escape(str(row.get('latest_year') or '-'))}</td>"
            f"{metric_cells}"
            f"{rank_cells}"
            "</tr>"
        )

    rank_headers = "".join(f"<th>{escape(dimension['label'])}排名</th>" for dimension in dimensions)
    embedded_json = json.dumps(comparison, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>同業比較</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", sans-serif; background: #f6f8fb; color: #1f2937; }}
    header {{ background: #12355b; color: white; padding: 24px 32px; }}
    main {{ padding: 24px 32px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #d8dee8; padding: 10px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #e8eef7; }}
  </style>
</head>
<body>
  <header><h1>同業比較</h1></header>
  <main>
    <table>
      <thead>
        <tr><th>股票代碼</th><th>年度</th>{header_cells}{rank_headers}</tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
    <script type="application/json" id="comparison-data">{embedded_json}</script>
  </main>
</body>
</html>
"""
