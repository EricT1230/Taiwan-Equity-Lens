from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard import write_dashboard_index
from taiwan_stock_analysis.market_price import offline_price, write_valuation_template
from taiwan_stock_analysis.watchlist import load_watchlist


def run_watchlist_workflow(
    watchlist_path: Path,
    output_dir: Path,
    *,
    fixture_root: Path | None = None,
    offline_prices: bool = False,
    valuation_csv: Path | None = None,
    include_valuation: bool = True,
) -> Path:
    from taiwan_stock_analysis.cli import run_batch, run_compare

    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / "reports"
    valuation_reports_dir = output_dir / "valuation-reports"
    comparison_dir = output_dir / "comparison"
    dashboard_path = output_dir / "dashboard.html"
    summary_path = output_dir / "workflow_summary.json"
    generated_valuation_path = output_dir / "valuation.csv"

    _reset_generated_path(reports_dir)
    _reset_generated_path(valuation_reports_dir)
    _reset_generated_path(comparison_dir)
    _unlink_if_exists(generated_valuation_path)
    _unlink_if_exists(dashboard_path)
    _unlink_if_exists(summary_path)

    watchlist_rows = load_watchlist(watchlist_path)
    stock_ids = [row["stock_id"] for row in watchlist_rows]

    batch_summary_path = run_batch(
        watchlist_path,
        output_dir=reports_dir,
        fixture_root=fixture_root,
    )
    batch_summary = _read_json(batch_summary_path)
    successful_stock_ids = _successful_stock_ids(batch_summary)

    valuation_path = valuation_csv
    generated_valuation_template = False
    valuation_summary_path: Path | None = None
    if include_valuation:
        if valuation_path is None:
            valuation_path = generated_valuation_path
            write_valuation_template(
                stock_ids,
                valuation_path,
                analysis_dir=reports_dir,
                fetch_price=offline_price if offline_prices else None,
            )
            generated_valuation_template = True

        valuation_summary_path = run_batch(
            watchlist_path,
            output_dir=valuation_reports_dir,
            fixture_root=fixture_root,
            valuation_csv=valuation_path,
        )

    comparison_paths: dict[str, str] = {}
    comparison_skipped_reason = ""
    if len(successful_stock_ids) >= 2:
        comparison_json, comparison_html = run_compare(
            successful_stock_ids,
            output_dir=comparison_dir,
            fixture_root=fixture_root,
        )
        comparison_paths = {
            "json": str(comparison_json),
            "html": str(comparison_html),
        }
    else:
        comparison_skipped_reason = "fewer than two successful stocks"

    scan_dirs = [reports_dir, comparison_dir]
    if include_valuation:
        scan_dirs.insert(1, valuation_reports_dir)
    write_dashboard_index(scan_dirs, dashboard_path)

    summary: dict[str, Any] = {
        "watchlist_path": str(watchlist_path),
        "output_dir": str(output_dir),
        "stock_ids": stock_ids,
        "successful_stock_ids": successful_stock_ids,
        "paths": {
            "batch_summary": str(batch_summary_path),
            "valuation_csv": str(valuation_path) if valuation_path is not None else "",
            "valuation_batch_summary": str(valuation_summary_path) if valuation_summary_path is not None else "",
            "comparison": comparison_paths,
            "dashboard": str(dashboard_path),
        },
        "generated_valuation_template": generated_valuation_template,
        "comparison_skipped_reason": comparison_skipped_reason,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def _successful_stock_ids(batch_summary: dict[str, Any]) -> list[str]:
    results = batch_summary.get("results", [])
    if not isinstance(results, list):
        return []
    stock_ids: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("status") == "ok":
            stock_id = str(result.get("stock_id") or "").strip()
            if stock_id:
                stock_ids.append(stock_id)
    return stock_ids


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _reset_generated_path(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()
