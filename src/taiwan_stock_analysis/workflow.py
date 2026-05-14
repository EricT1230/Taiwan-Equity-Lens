from __future__ import annotations

import json
import shutil
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.dashboard import write_dashboard_index
from taiwan_stock_analysis.freshness import (
    FINANCIAL_STATEMENT_STALE_DAYS,
    PRICE_STALE_DAYS,
    classify_freshness,
    summarize_source_audit,
)
from taiwan_stock_analysis.market_price import offline_price, write_valuation_template
from taiwan_stock_analysis.reliability import ReliabilityStatus, build_retry_hint, summarize_reliability
from taiwan_stock_analysis.traceability import (
    build_artifact_registry,
    build_run_metadata,
    merge_traceability,
)
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
    statuses: list[ReliabilityStatus] = []

    batch_summary_path = run_batch(
        watchlist_path,
        output_dir=reports_dir,
        fixture_root=fixture_root,
    )
    batch_summary = _read_json(batch_summary_path)
    successful_stock_ids = _successful_stock_ids(batch_summary)
    stock_failures = _stock_failures(batch_summary, default_stage="batch")
    batch_status = _summary_status(batch_summary)
    statuses.append(
        ReliabilityStatus(
            stage="batch",
            status=batch_status,
            message=f"Analyzed {len(successful_stock_ids)} of {len(stock_ids)} watchlist stocks.",
            source=str(batch_summary_path),
            retry_hint=build_retry_hint("fetch") if batch_status in {"warning", "error"} else "",
        )
    )

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
        price_statuses = _price_statuses_from_csv(valuation_path)
        statuses.extend(price_statuses)

        valuation_summary_path = run_batch(
            watchlist_path,
            output_dir=valuation_reports_dir,
            fixture_root=fixture_root,
            valuation_csv=valuation_path,
        )
        valuation_summary = _read_json(valuation_summary_path)
        valuation_failures = _stock_failures(valuation_summary, default_stage="valuation")
        stock_failures.extend(valuation_failures)
        valuation_status = _summary_status(valuation_summary)
        statuses.append(
            ReliabilityStatus(
                stage="valuation",
                status=valuation_status,
                message="Valuation-aware batch reports generated.",
                source=str(valuation_summary_path),
                retry_hint=build_retry_hint("valuation") if valuation_status in {"warning", "error"} else "",
            )
        )
    else:
        statuses.append(
            ReliabilityStatus(
                stage="valuation",
                status="skipped",
                message="Valuation step disabled.",
                retry_hint=build_retry_hint("valuation"),
            )
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
        statuses.append(
            ReliabilityStatus(
                stage="comparison",
                status="ok",
                message=f"Compared {len(successful_stock_ids)} successful stocks.",
                source=str(comparison_json),
            )
        )
    else:
        comparison_skipped_reason = "fewer than two successful stocks"
        statuses.append(
            ReliabilityStatus(
                stage="comparison",
                status="skipped",
                message=comparison_skipped_reason,
                retry_hint=build_retry_hint("comparison"),
            )
        )

    statuses.append(
        ReliabilityStatus(
            stage="dashboard",
            status="ok",
            message="Dashboard index scheduled for generation.",
            source=str(dashboard_path),
        )
    )

    source_audit = _build_source_audit(
        stock_ids,
        reports_dir=reports_dir,
        valuation_path=valuation_path,
    )
    summary: dict[str, Any] = {
        "watchlist_path": str(watchlist_path),
        "output_dir": str(output_dir),
        "stock_ids": stock_ids,
        "successful_stock_ids": successful_stock_ids,
        "source_audit": source_audit,
        "paths": {
            "batch_summary": str(batch_summary_path),
            "valuation_csv": str(valuation_path) if valuation_path is not None else "",
            "valuation_batch_summary": str(valuation_summary_path) if valuation_summary_path is not None else "",
            "comparison": comparison_paths,
            "dashboard": str(dashboard_path),
        },
        "generated_valuation_template": generated_valuation_template,
        "comparison_skipped_reason": comparison_skipped_reason,
        "step_statuses": {status.stage: status.to_dict() for status in statuses},
        "data_reliability": summarize_reliability(statuses),
        "stock_failures": stock_failures,
    }
    summary = merge_traceability(
        summary,
        run_metadata=build_run_metadata(
            "workflow",
            "workflow run",
            {"watchlist": str(watchlist_path)},
            str(output_dir),
        ),
        artifact_registry=build_artifact_registry(
            str(summary_path),
            dependencies={"watchlist": str(watchlist_path)},
            outputs={"dashboard": str(dashboard_path)},
        ),
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    scan_dirs = [output_dir, reports_dir, comparison_dir]
    if include_valuation:
        scan_dirs.insert(2, valuation_reports_dir)
    write_dashboard_index(scan_dirs, dashboard_path)
    return summary_path


def _build_source_audit(
    stock_ids: list[str],
    *,
    reports_dir: Path,
    valuation_path: Path | None,
) -> dict[str, Any]:
    price_rows = _price_rows_by_stock(valuation_path)
    items: list[dict[str, Any]] = []
    status_items: list[dict[str, str]] = []

    for stock_id in stock_ids:
        financial = _financial_statement_audit(stock_id, reports_dir)
        price = _price_audit(stock_id, price_rows.get(stock_id))
        combined_status = _combine_audit_status([financial, price])
        items.append(
            {
                "stock_id": stock_id,
                "status": combined_status,
                "financial_statement": financial,
                "price": price,
            }
        )
        status_items.append({"status": combined_status})

    summary = summarize_source_audit(status_items)
    return {**summary, "items": items}


def _financial_statement_audit(stock_id: str, reports_dir: Path) -> dict[str, Any]:
    path = reports_dir / f"{stock_id}_raw_data.json"
    if not path.exists():
        return classify_freshness(
            generated_at="",
            source_mode="unknown",
            stale_after_days=FINANCIAL_STATEMENT_STALE_DAYS,
            review_reason=f"analysis report missing: {path}",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return classify_freshness(
            generated_at="",
            source_mode="unknown",
            stale_after_days=FINANCIAL_STATEMENT_STALE_DAYS,
            review_reason=f"analysis report invalid: {exc}",
        )
    if not isinstance(payload, dict):
        return classify_freshness(
            generated_at="",
            source_mode="unknown",
            stale_after_days=FINANCIAL_STATEMENT_STALE_DAYS,
            review_reason="analysis report invalid: expected object",
        )

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    fetched_at = str(metadata.get("fetched_at") or "")
    source_mode = str(metadata.get("source_mode") or "unknown")
    return classify_freshness(
        generated_at=fetched_at,
        source_mode=source_mode,
        stale_after_days=FINANCIAL_STATEMENT_STALE_DAYS,
    )


def _price_rows_by_stock(valuation_path: Path | None) -> dict[str, dict[str, str]]:
    if valuation_path is None or not valuation_path.exists():
        return {}
    try:
        with valuation_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return {
                stock_id: dict(row)
                for row in reader
                if (stock_id := str(row.get("stock_id") or "").strip())
            }
    except OSError:
        return {}


def _price_audit(stock_id: str, row: dict[str, str] | None) -> dict[str, Any]:
    if not row:
        return classify_freshness(
            generated_at="",
            source_mode="unknown",
            stale_after_days=PRICE_STALE_DAYS,
            review_reason=f"valuation price row missing for {stock_id}",
        )

    price_date = str(row.get("price_date") or "").strip()
    price_source = str(row.get("price_source") or "").strip()
    price_status = str(row.get("price_status") or "").strip().lower()
    warning = str(row.get("warning") or "").strip()
    message = str(row.get("price_status_message") or "").strip()
    warning_text = f"{warning} {message}".lower()

    source_mode = "unknown"
    review_reason = ""
    generated_at = price_date
    if "offline mode" in warning_text or (price_status == "warning" and not price_date):
        source_mode = "offline"
        review_reason = warning or message or "offline price source requires manual review"
        generated_at = price_date or datetime.now(timezone.utc).isoformat()
    elif price_source or price_date:
        source_mode = "live"
    else:
        review_reason = "price source and date are missing"

    return classify_freshness(
        generated_at=generated_at,
        source_mode=source_mode,
        stale_after_days=PRICE_STALE_DAYS,
        review_reason=review_reason,
    )


def _combine_audit_status(components: list[dict[str, Any]]) -> str:
    return summarize_source_audit(components)["status"]


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


def _summary_status(batch_summary: dict[str, Any]) -> str:
    results = batch_summary.get("results", [])
    if not isinstance(results, list) or not results:
        return "skipped"
    failed = sum(1 for result in results if isinstance(result, dict) and result.get("status") != "ok")
    warnings = sum(
        1
        for result in results
        if isinstance(result, dict) and int(result.get("warning_count") or 0) > 0
    )
    if failed == 0:
        return "warning" if warnings else "ok"
    if failed == len(results):
        return "error"
    return "warning"


def _price_statuses_from_csv(path: Path) -> list[ReliabilityStatus]:
    if not path.exists():
        return []
    statuses: list[ReliabilityStatus] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            warning = (row.get("warning") or "").strip()
            status = (row.get("price_status") or "").strip()
            if not status and warning:
                status = "warning"
            if status not in {"warning", "error"}:
                continue
            statuses.append(
                ReliabilityStatus(
                    stage="price",
                    status=status,
                    stock_id=(row.get("stock_id") or "").strip(),
                    source=(row.get("price_source") or "").strip(),
                    date=(row.get("price_date") or "").strip(),
                    message=(row.get("price_status_message") or warning).strip(),
                    retry_hint=(row.get("price_retry_hint") or build_retry_hint("price")).strip(),
                )
            )
    return statuses


def _stock_failures(batch_summary: dict[str, Any], *, default_stage: str) -> list[dict[str, str]]:
    results = batch_summary.get("results", [])
    if not isinstance(results, list):
        return []
    failures: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict) or result.get("status") == "ok":
            continue
        stage = str(result.get("stage") or default_stage).strip() or default_stage
        failures.append(
            {
                "stock_id": str(result.get("stock_id") or "").strip(),
                "stage": stage,
                "reason": str(result.get("error") or result.get("reason") or "").strip(),
                "retry_hint": build_retry_hint(stage),
            }
        )
    return failures


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
