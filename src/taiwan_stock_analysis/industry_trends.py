from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from typing import Any, Iterable

from taiwan_stock_analysis.research import load_research_rows
from taiwan_stock_analysis.traceability import build_artifact_registry, build_run_metadata, merge_traceability


PRICE_HISTORY_COLUMNS = ["stock_id", "date", "close", "volume", "source"]
REQUIRED_PRICE_HISTORY_COLUMNS = {"stock_id", "date", "close"}
NON_ADVICE_NOTICE = (
    "This output is for research workflow triage only and is not investment advice."
)


def load_price_history_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_PRICE_HISTORY_COLUMNS - fieldnames)
        if missing:
            required = ", ".join(sorted(REQUIRED_PRICE_HISTORY_COLUMNS))
            raise ValueError(
                f"price history CSV must include {required}; missing: {', '.join(missing)}"
            )

        rows: list[dict[str, Any]] = []
        for index, row in enumerate(reader, start=2):
            stock_id = str(row.get("stock_id") or "").strip()
            raw_date = str(row.get("date") or "").strip()
            raw_close = str(row.get("close") or "").strip()
            if not stock_id:
                raise ValueError(f"price history CSV row {index} must include a stock_id")
            if not raw_date:
                raise ValueError(f"price history CSV row {index} must include a date")
            try:
                date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(
                    f"price history CSV row {index} has invalid ISO date '{raw_date}'"
                ) from exc
            try:
                close = float(raw_close.replace(",", ""))
            except ValueError as exc:
                raise ValueError(
                    f"price history CSV row {index} has invalid close '{raw_close}'"
                ) from exc
            if close <= 0:
                raise ValueError(f"price history CSV row {index} close must be positive")

            rows.append(
                {
                    "stock_id": stock_id,
                    "date": raw_date,
                    "close": close,
                    "volume": _optional_float(row.get("volume")),
                    "source": str(row.get("source") or "").strip(),
                }
            )
    return rows


def build_industry_trend_report(research_path: Path, price_history_path: Path) -> dict[str, Any]:
    research_rows = load_research_rows(research_path)
    price_rows = load_price_history_rows(price_history_path)
    prices_by_stock = _prices_by_stock(price_rows)
    stock_trends: list[dict[str, Any]] = []
    for research_row in research_rows:
        stock_id = research_row["stock_id"]
        trend = _stock_trend(research_row, prices_by_stock.get(stock_id, []))
        stock_trends.append(trend)

    categories = _category_trends(stock_trends)
    as_of_date = _latest_date(stock_trends)
    quality_gate = _quality_gate(stock_trends)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "industry_trend_report",
        "research_path": str(research_path),
        "price_history_path": str(price_history_path),
        "as_of_date": as_of_date,
        "coverage": _coverage(stock_trends, categories),
        "quality_gate": quality_gate,
        "stock_trends": stock_trends,
        "categories": categories,
        "non_advice_notice": NON_ADVICE_NOTICE,
    }
    return report


def write_industry_trend_report(
    research_path: Path,
    price_history_path: Path,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "industry_trend_report.json"
    markdown_path = output_dir / "industry_trend_report.md"
    html_path = output_dir / "industry_trend_report.html"
    report = build_industry_trend_report(research_path, price_history_path)
    report = merge_traceability(
        report,
        run_metadata=build_run_metadata(
            "industry-trends",
            "research industry-trends",
            {"research_csv": str(research_path), "price_history": str(price_history_path)},
            str(output_dir),
        ),
        artifact_registry=build_artifact_registry(
            str(summary_path),
            dependencies={
                "research_csv": str(research_path),
                "price_history": str(price_history_path),
            },
            outputs={
                "markdown": str(markdown_path),
                "html": str(html_path),
            },
        ),
    )
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_industry_trend_markdown(report), encoding="utf-8")
    html_path.write_text(render_industry_trend_html(report), encoding="utf-8")
    return summary_path


def render_industry_trend_markdown(report: dict[str, Any]) -> str:
    coverage = _dict_value(report.get("coverage"))
    gate = _dict_value(report.get("quality_gate"))
    lines = [
        "# Industry Trend Report",
        "",
        f"- as_of_date: {report.get('as_of_date') or '-'}",
        f"- quality_gate: {gate.get('status') or '-'}",
        f"- coverage: {coverage.get('stocks_with_price_history', 0)} / {coverage.get('stocks_total', 0)} stocks",
        f"- next_action: {gate.get('next_action') or '-'}",
        "",
        "## Sector Rotation Snapshot",
        "",
        "| Industry | Direction | Phase | 20D | 5D | 1D | Coverage | Volume | Leaders | Laggards |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for category in _category_rows(report):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(category.get("category") or "-"),
                    str(category.get("direction") or "-"),
                    str(category.get("rotation_phase") or "-"),
                    _return_text(category.get("average_return_20d")),
                    _return_text(category.get("average_return_5d")),
                    _return_text(category.get("average_return_1d")),
                    f"{category.get('coverage_count', 0)} / {category.get('stock_count', 0)}",
                    _ratio_text(category.get("average_volume_ratio_5d")),
                    _stock_list_text(category.get("leading_stocks")),
                    _stock_list_text(category.get("lagging_stocks")),
                ]
            )
            + " |"
        )
    blockers = gate.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Data Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
    lines.extend(["", "## Non-Advice Boundary", "", str(report.get("non_advice_notice") or NON_ADVICE_NOTICE)])
    return "\n".join(lines) + "\n"


def render_industry_trend_html(report: dict[str, Any]) -> str:
    coverage = _dict_value(report.get("coverage"))
    gate = _dict_value(report.get("quality_gate"))
    cards = "".join(_category_card(category) for category in _category_rows(report))
    blockers = gate.get("blockers", [])
    blocker_items = ""
    if isinstance(blockers, list) and blockers:
        blocker_items = "<ul>" + "".join(f"<li>{escape(str(blocker))}</li>" for blocker in blockers) + "</ul>"
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Industry Trend Report</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; background: #f6f8fb; color: #172033; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    section {{ background: #ffffff; border: 1px solid #dbe4ef; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .summary div, .card {{ border: 1px solid #dbe4ef; border-radius: 8px; padding: 12px; background: #fbfdff; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .metric {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 10px 0; }}
    .metric span {{ border: 1px solid #e5edf6; border-radius: 8px; padding: 8px; background: white; }}
    .notice {{ border-color: #fde68a; background: #fffbeb; color: #92400e; }}
  </style>
</head>
<body>
  <main data-industry-trend-report="true">
    <section>
      <h1>Industry Trend Report</h1>
      <div class="summary" data-sector-rotation-pipeline="true">
        <div><strong>{escape(str(gate.get("status") or "-"))}</strong><span>quality gate</span></div>
        <div><strong>{escape(str(report.get("as_of_date") or "-"))}</strong><span>as of date</span></div>
        <div><strong>{escape(str(coverage.get("stocks_with_price_history", 0)))} / {escape(str(coverage.get("stocks_total", 0)))}</strong><span>price coverage</span></div>
        <div><strong>{escape(str(coverage.get("categories_total", 0)))}</strong><span>industries</span></div>
      </div>
      <p><strong>Next action:</strong> {escape(str(gate.get("next_action") or "-"))}</p>
    </section>
    <section>
      <h2>Sector Rotation Snapshot</h2>
      <div class="cards">{cards}</div>
    </section>
    <section>
      <h2>Data Blockers</h2>
      {blocker_items or '<p>No data blockers.</p>'}
    </section>
    <section class="notice">
      <h2>Non-Advice Boundary</h2>
      <p>{escape(str(report.get("non_advice_notice") or NON_ADVICE_NOTICE))}</p>
    </section>
  </main>
</body>
</html>
"""


def _prices_by_stock(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["stock_id"])].append(row)
    return {
        stock_id: sorted(stock_rows, key=lambda row: str(row["date"]))
        for stock_id, stock_rows in grouped.items()
    }


def _stock_trend(research_row: dict[str, str], price_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stock_id = research_row["stock_id"]
    base = {
        "stock_id": stock_id,
        "company_name": research_row.get("company_name", ""),
        "category": research_row.get("category", "") or "Uncategorized",
        "latest_date": "",
        "latest_close": None,
        "return_1d": None,
        "return_5d": None,
        "return_20d": None,
        "volume_ratio_5d": None,
        "volume_signal": "missing",
        "direction": "missing",
        "status": "missing_price_history",
        "price_points": 0,
        "source": "",
    }
    if not price_rows:
        return base

    latest = price_rows[-1]
    trend = dict(base)
    trend.update(
        {
            "latest_date": str(latest["date"]),
            "latest_close": _round(latest["close"]),
            "return_1d": _return_over_horizon(price_rows, 1),
            "return_5d": _return_over_horizon(price_rows, 5),
            "return_20d": _return_over_horizon(price_rows, 20),
            "volume_ratio_5d": _volume_ratio_5d(price_rows),
            "price_points": len(price_rows),
            "source": str(latest.get("source") or ""),
        }
    )
    trend["volume_signal"] = _volume_signal(trend["volume_ratio_5d"])
    trend["direction"] = _direction_for_returns(
        trend["return_20d"],
        trend["return_5d"],
        trend["return_1d"],
    )
    trend["status"] = "available" if trend["return_1d"] is not None else "insufficient_history"
    return trend


def _category_trends(stock_trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trend in stock_trends:
        groups[str(trend.get("category") or "Uncategorized")].append(trend)

    categories: list[dict[str, Any]] = []
    for category, trends in sorted(groups.items()):
        available = [trend for trend in trends if trend.get("status") == "available"]
        average_return_1d = _average(trend.get("return_1d") for trend in available)
        average_return_5d = _average(trend.get("return_5d") for trend in available)
        average_return_20d = _average(trend.get("return_20d") for trend in available)
        direction_counts = _direction_counts(available)
        direction = _category_direction(direction_counts, average_return_20d, average_return_5d, average_return_1d)
        leading = _stock_extremes(available, reverse=True)
        lagging = _stock_extremes(available, reverse=False)
        categories.append(
            {
                "category": category,
                "stock_count": len(trends),
                "coverage_count": len(available),
                "missing_count": len(trends) - len(available),
                "average_return_1d": average_return_1d,
                "average_return_5d": average_return_5d,
                "average_return_20d": average_return_20d,
                "average_volume_ratio_5d": _average(
                    trend.get("volume_ratio_5d") for trend in available
                ),
                "direction": direction,
                "rotation_phase": _rotation_phase(average_return_20d, average_return_5d, direction),
                "leading_stocks": leading,
                "lagging_stocks": lagging,
                "volume_signals": sorted(
                    {
                        str(trend.get("volume_signal") or "")
                        for trend in available
                        if str(trend.get("volume_signal") or "") not in {"", "missing"}
                    }
                ),
                "notes": _category_notes(trends, available),
            }
        )
    return sorted(
        categories,
        key=lambda item: (
            0 if item["direction"] == "mixed" else 1,
            -float(item.get("average_return_20d") or -9999),
            str(item["category"]),
        ),
    )


def _coverage(stock_trends: list[dict[str, Any]], categories: list[dict[str, Any]]) -> dict[str, int]:
    with_history = sum(1 for trend in stock_trends if trend.get("status") == "available")
    return {
        "stocks_total": len(stock_trends),
        "stocks_with_price_history": with_history,
        "missing_price_history": len(stock_trends) - with_history,
        "categories_total": len(categories),
        "categories_with_price_history": sum(
            1 for category in categories if int(category.get("coverage_count") or 0) > 0
        ),
    }


def _quality_gate(stock_trends: list[dict[str, Any]]) -> dict[str, Any]:
    blockers: list[str] = []
    for trend in stock_trends:
        stock_id = str(trend.get("stock_id") or "")
        status = str(trend.get("status") or "")
        if status == "missing_price_history":
            blockers.append(f"{stock_id}: missing price history")
        elif status == "insufficient_history":
            blockers.append(f"{stock_id}: need at least two price points")
        elif trend.get("return_20d") is None:
            blockers.append(f"{stock_id}: need at least 21 price points for 20D rotation")
    status = "ready" if not blockers else "needs_data"
    next_action = (
        "Review sector trend evidence and compare it with handoff blockers."
        if status == "ready"
        else "Add or extend price-history rows for the blocked stocks, then rerun industry-trends."
    )
    return {
        "status": status,
        "blocker_count": len(blockers),
        "blockers": blockers[:10],
        "next_action": next_action,
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def _return_over_horizon(rows: list[dict[str, Any]], horizon: int) -> float | None:
    if len(rows) <= horizon:
        return None
    latest = float(rows[-1]["close"])
    previous = float(rows[-1 - horizon]["close"])
    if previous <= 0:
        return None
    return _round((latest / previous - 1) * 100)


def _volume_ratio_5d(rows: list[dict[str, Any]]) -> float | None:
    if len(rows) < 6:
        return None
    latest_volume = _optional_float(rows[-1].get("volume"))
    if latest_volume is None:
        return None
    previous = [_optional_float(row.get("volume")) for row in rows[-6:-1]]
    volumes = [volume for volume in previous if volume is not None and volume > 0]
    if not volumes:
        return None
    return _round(latest_volume / (sum(volumes) / len(volumes)))


def _volume_signal(ratio: Any) -> str:
    value = _optional_float(ratio)
    if value is None:
        return "missing"
    if value >= 1.25:
        return "expanding"
    if value <= 0.75:
        return "contracting"
    return "normal"


def _direction_for_returns(return_20d: Any, return_5d: Any, return_1d: Any) -> str:
    value = _first_number(return_20d, return_5d, return_1d)
    if value is None:
        return "missing"
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


def _category_direction(
    direction_counts: dict[str, int],
    average_return_20d: float | None,
    average_return_5d: float | None,
    average_return_1d: float | None,
) -> str:
    if direction_counts.get("up", 0) > 0 and direction_counts.get("down", 0) > 0:
        return "mixed"
    return _direction_for_returns(average_return_20d, average_return_5d, average_return_1d)


def _rotation_phase(average_return_20d: float | None, average_return_5d: float | None, direction: str) -> str:
    if direction == "missing":
        return "missing"
    if direction == "mixed":
        return "divergent"
    long_term = average_return_20d or 0.0
    short_term = average_return_5d or 0.0
    if long_term > 0 and short_term > 0:
        return "leading"
    if long_term > 0 and short_term <= 0:
        return "cooling"
    if long_term < 0 and short_term > 0:
        return "rebounding"
    if long_term < 0 and short_term <= 0:
        return "lagging"
    return "flat"


def _stock_extremes(trends: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    candidates = [trend for trend in trends if _optional_float(trend.get("return_20d")) is not None]
    ordered = sorted(
        candidates,
        key=lambda trend: (
            float(trend.get("return_20d") or 0.0),
            str(trend.get("stock_id") or ""),
        ),
        reverse=reverse,
    )
    return [
        {
            "stock_id": str(trend.get("stock_id") or ""),
            "company_name": str(trend.get("company_name") or ""),
            "return_20d": trend.get("return_20d"),
        }
        for trend in ordered[:3]
    ]


def _category_notes(trends: list[dict[str, Any]], available: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    missing = [str(trend.get("stock_id") or "") for trend in trends if trend.get("status") != "available"]
    if missing:
        notes.append(f"Missing or insufficient price history: {', '.join(missing)}")
    signals = sorted(
        {
            str(trend.get("volume_signal") or "")
            for trend in available
            if str(trend.get("volume_signal") or "") not in {"", "missing", "normal"}
        }
    )
    if signals:
        notes.append(f"Volume signals: {', '.join(signals)}")
    return notes


def _direction_counts(trends: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trend in trends:
        direction = str(trend.get("direction") or "missing")
        counts[direction] = counts.get(direction, 0) + 1
    return counts


def _latest_date(stock_trends: list[dict[str, Any]]) -> str:
    dates = [str(trend.get("latest_date") or "") for trend in stock_trends if trend.get("latest_date")]
    return max(dates) if dates else ""


def _average(values: Iterable[Any]) -> float | None:
    numbers = [number for number in (_optional_float(value) for value in values) if number is not None]
    if not numbers:
        return None
    return _round(sum(numbers) / len(numbers))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _optional_float(value)
        if number is not None:
            return number
    return None


def _round(value: Any) -> float:
    return round(float(value), 2)


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _category_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    categories = report.get("categories", [])
    return [category for category in categories if isinstance(category, dict)] if isinstance(categories, list) else []


def _stock_list_text(value: Any) -> str:
    stocks = value if isinstance(value, list) else []
    labels = []
    for item in stocks[:3]:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "")
        labels.append(f"{stock_id} {_return_text(item.get('return_20d'))}".strip())
    return ", ".join(labels) if labels else "-"


def _return_text(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.2f}%"


def _ratio_text(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}x"


def _category_card(category: dict[str, Any]) -> str:
    leading = _stock_list_text(category.get("leading_stocks"))
    lagging = _stock_list_text(category.get("lagging_stocks"))
    notes = category.get("notes", [])
    note_text = " | ".join(str(note) for note in notes) if isinstance(notes, list) and notes else "-"
    direction = str(category.get("direction") or "missing")
    return (
        '<article class="card" data-industry-trend-category="'
        f'{escape(str(category.get("category") or ""))}" '
        f'data-industry-trend-direction="{escape(direction)}">'
        f'<h3>{escape(str(category.get("category") or "-"))}</h3>'
        f'<p><strong>Direction:</strong> {escape(direction)} / {escape(str(category.get("rotation_phase") or "-"))}</p>'
        '<div class="metric">'
        f'<span><strong>{escape(_return_text(category.get("average_return_20d")))}</strong>20D</span>'
        f'<span><strong>{escape(_return_text(category.get("average_return_5d")))}</strong>5D</span>'
        f'<span><strong>{escape(_return_text(category.get("average_return_1d")))}</strong>1D</span>'
        f'<span><strong>{escape(str(category.get("coverage_count", 0)))}/{escape(str(category.get("stock_count", 0)))}</strong>coverage</span>'
        "</div>"
        f'<p><strong>Volume:</strong> {escape(_ratio_text(category.get("average_volume_ratio_5d")))}</p>'
        f'<p><strong>Leading:</strong> {escape(leading)}</p>'
        f'<p><strong>Lagging:</strong> {escape(lagging)}</p>'
        f'<p><strong>Notes:</strong> {escape(note_text)}</p>'
        "</article>"
    )
