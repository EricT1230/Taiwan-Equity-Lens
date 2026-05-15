from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from taiwan_stock_analysis.comparison import compare_results
from taiwan_stock_analysis.dashboard import write_dashboard_index
from taiwan_stock_analysis.diagnostics import build_diagnostics
from taiwan_stock_analysis.doctor import check_release_readiness, format_doctor_result
from taiwan_stock_analysis.fetcher import GoodinfoClient, build_metadata
from taiwan_stock_analysis.insights import build_insights
from taiwan_stock_analysis.market_price import offline_price, write_valuation_template
from taiwan_stock_analysis.memo import write_memo, write_research_memos
from taiwan_stock_analysis.metrics import calculate_metrics
from taiwan_stock_analysis.models import AnalysisResult
from taiwan_stock_analysis.parser import parse_financial_table
from taiwan_stock_analysis.price_data import load_price_data, load_price_reliability
from taiwan_stock_analysis.report_compare import render_comparison_html
from taiwan_stock_analysis.report import render_html_report
from taiwan_stock_analysis.research import (
    write_research_summary,
    write_research_template,
    write_watchlist_from_research,
)
from taiwan_stock_analysis.review_action_state import (
    ACTION_STATUSES,
    apply_review_action_state,
    build_review_action_state_report,
    load_review_action_state,
    prune_stale_review_action_state,
    review_action_rows,
    set_review_action_state,
    write_review_action_state,
)
from taiwan_stock_analysis.scoring import build_scorecard
from taiwan_stock_analysis.valuation import build_valuation
from taiwan_stock_analysis.verification import build_verification
from taiwan_stock_analysis.watchlist import load_watchlist


REPORT_FILES = {
    "income_statement": ("IS_YEAR", "IS_YEAR.html"),
    "balance_sheet": ("BS_YEAR", "BS_YEAR.html"),
    "cash_flow": ("CF_YEAR", "CF_YEAR.html"),
}


def _read_reports(stock_id: str, fixture_dir: Path | None) -> dict[str, str]:
    if fixture_dir is not None:
        return {
            name: (fixture_dir / file_name).read_text(encoding="utf-8")
            for name, (_, file_name) in REPORT_FILES.items()
        }

    client = GoodinfoClient()
    return {
        name: client.fetch_report(stock_id, report_category)
        for name, (report_category, _) in REPORT_FILES.items()
    }


def analyze(
    stock_id: str,
    fixture_dir: Path | None = None,
    price_inputs: dict[str, float | None] | None = None,
    reliability: list[dict[str, str]] | None = None,
) -> AnalysisResult:
    html_reports = _read_reports(stock_id, fixture_dir)
    income_statement, years = parse_financial_table(html_reports["income_statement"])
    balance_sheet, _ = parse_financial_table(html_reports["balance_sheet"])
    cash_flow, _ = parse_financial_table(html_reports["cash_flow"])
    years = years[:3]
    metrics_by_year = calculate_metrics(income_statement, balance_sheet, cash_flow, years)
    insights = build_insights(metrics_by_year, years)
    scorecard = build_scorecard(metrics_by_year, years)
    valuation = build_valuation(
        stock_id=stock_id,
        metrics_by_year=metrics_by_year,
        years=years,
        price_inputs=price_inputs,
    )
    diagnostics = build_diagnostics(
        years=years,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        metrics_by_year=metrics_by_year,
    )

    metadata = build_metadata(stock_id, years, source_mode="fixture" if fixture_dir is not None else "live")
    if reliability:
        metadata["reliability"] = reliability

    return AnalysisResult(
        stock_id=stock_id,
        years=years,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        metrics_by_year=metrics_by_year,
        insights=insights,
        scorecard=scorecard,
        valuation=valuation,
        diagnostics=diagnostics,
        metadata=metadata,
        verification=build_verification(metrics_by_year, years),
    )


def run(
    stock_id: str,
    output_dir: Path,
    company_name: str | None = None,
    fixture_dir: Path | None = None,
    valuation_csv: Path | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    price_inputs = None
    reliability = None
    if valuation_csv is not None:
        price_inputs = load_price_data(valuation_csv).get(stock_id)
        price_reliability = load_price_reliability(valuation_csv).get(stock_id)
        if price_reliability and price_reliability.get("status"):
            reliability = [price_reliability]
    result = analyze(stock_id, fixture_dir=fixture_dir, price_inputs=price_inputs, reliability=reliability)

    json_path = output_dir / f"{stock_id}_raw_data.json"
    html_path = output_dir / f"{stock_id}_analysis.html"
    json_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html_report(result, company_name=company_name), encoding="utf-8")
    return json_path, html_path


def _fixture_for_stock(fixture_root: Path | None, stock_id: str) -> Path | None:
    if fixture_root is None:
        return None
    stock_fixture = fixture_root / stock_id
    if stock_fixture.exists():
        return stock_fixture
    return fixture_root


def run_compare(
    stock_ids: list[str],
    output_dir: Path,
    fixture_root: Path | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        analyze(stock_id, fixture_dir=_fixture_for_stock(fixture_root, stock_id))
        for stock_id in stock_ids
    ]
    comparison = compare_results(results)
    json_path = output_dir / "comparison.json"
    html_path = output_dir / "comparison.html"
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_comparison_html(comparison), encoding="utf-8")
    return json_path, html_path


def run_batch(
    watchlist_path: Path,
    output_dir: Path,
    fixture_root: Path | None = None,
    valuation_csv: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_watchlist(watchlist_path)
    summary: dict[str, list[dict[str, object]]] = {"results": []}

    for row in rows:
        stock_id = row["stock_id"]
        try:
            json_path, html_path = run(
                stock_id=stock_id,
                company_name=row.get("company_name") or None,
                output_dir=output_dir,
                fixture_dir=_fixture_for_stock(fixture_root, stock_id),
                valuation_csv=valuation_csv,
            )
        except Exception as exc:
            summary["results"].append(
                {
                    "stock_id": stock_id,
                    "company_name": row.get("company_name", ""),
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        summary["results"].append(
            {
                "stock_id": stock_id,
                "company_name": row.get("company_name", ""),
                "status": "ok",
                "warning_count": _diagnostic_warning_count(json_path),
                "json_path": str(json_path),
                "html_path": str(html_path),
            }
        )

    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def _diagnostic_warning_count(json_path: Path) -> int:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    diagnostics = payload.get("diagnostics", {})
    issue_count = diagnostics.get("issue_count", 0) if isinstance(diagnostics, dict) else 0
    return int(issue_count)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one Taiwan stock financial analysis report.")
    parser.add_argument("stock_id", help="Four-digit Taiwan stock id, for example 2330.")
    parser.add_argument("--company-name", help="Optional display name for the HTML report.")
    parser.add_argument("--output-dir", default="dist", type=Path, help="Directory for JSON and HTML output.")
    parser.add_argument("--fixture", type=Path, help="Directory containing IS_YEAR.html, BS_YEAR.html, and CF_YEAR.html.")
    parser.add_argument("--valuation-csv", type=Path, help="CSV file with valuation inputs.")
    return parser


def build_command_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Taiwan stock financial analysis reports.")
    subparsers = parser.add_subparsers(dest="command")

    compare_parser = subparsers.add_parser("compare", help="Compare multiple Taiwan stocks.")
    compare_parser.add_argument("stock_ids", nargs="+", help="Stock IDs to compare.")
    compare_parser.add_argument("--output-dir", default="compare-dist", type=Path)
    compare_parser.add_argument("--fixture-root", type=Path, help="Root directory containing per-stock fixture folders.")

    batch_parser = subparsers.add_parser("batch", help="Analyze a CSV watchlist.")
    batch_parser.add_argument("watchlist", type=Path, help="CSV file with stock_id and optional company_name columns.")
    batch_parser.add_argument("--output-dir", default="batch-dist", type=Path)
    batch_parser.add_argument("--fixture-root", type=Path, help="Root directory containing per-stock fixture folders.")
    batch_parser.add_argument("--valuation-csv", type=Path, help="CSV file with valuation inputs for all batch stocks.")

    dashboard_parser = subparsers.add_parser("dashboard", help="Generate a static dashboard index.")
    dashboard_parser.add_argument("--scan-dir", action="append", default=[], type=Path, help="Directory to scan for generated reports.")
    dashboard_parser.add_argument("--output", default=Path("dashboard-index.html"), type=Path, help="Output HTML path.")

    price_template_parser = subparsers.add_parser("price-template", help="Generate a valuation CSV template.")
    price_template_parser.add_argument("stock_ids", nargs="+", help="Stock IDs to include in the template.")
    price_template_parser.add_argument("--output", default=Path("valuation.csv"), type=Path, help="Output CSV path.")
    price_template_parser.add_argument("--offline", action="store_true", help="Do not fetch prices; write blank rows with warnings.")
    price_template_parser.add_argument("--analysis-dir", type=Path, help="Directory containing *_raw_data.json files for EPS enrichment.")

    memo_parser = subparsers.add_parser("memo", help="Generate a research memo from one analysis JSON.")
    memo_parser.add_argument("analysis_json", type=Path)
    memo_parser.add_argument("--output", required=True, type=Path)
    memo_parser.add_argument("--format", choices=["markdown", "html"], default="markdown")

    workflow_parser = subparsers.add_parser("workflow", help="Run the full watchlist workflow.")
    workflow_parser.add_argument("watchlist", type=Path, help="CSV file with stock_id and optional company_name columns.")
    workflow_parser.add_argument("--output-dir", default="workflow-dist", type=Path)
    workflow_parser.add_argument("--fixture-root", type=Path, help="Root directory containing per-stock fixture folders.")
    workflow_parser.add_argument("--offline-prices", action="store_true", help="Do not fetch market prices for the valuation template.")
    workflow_parser.add_argument("--valuation-csv", type=Path, help="Existing valuation CSV to use for valuation-aware reports.")
    workflow_parser.add_argument("--skip-valuation", action="store_true", help="Skip valuation template and valuation-aware rerun.")

    doctor_parser = subparsers.add_parser("doctor", help="Run local project health checks.")
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command")
    doctor_release = doctor_subparsers.add_parser("release", help="Check release readiness.")
    doctor_release.add_argument("--version", help="Expected release version, for example 0.10.0.")

    research_parser = subparsers.add_parser("research", help="Manage a local research workflow.")
    research_subparsers = research_parser.add_subparsers(dest="research_command")

    research_init = research_subparsers.add_parser("init", help="Create a research CSV template.")
    research_init.add_argument("--output", default=Path("research.csv"), type=Path)

    research_summary = research_subparsers.add_parser(
        "summary",
        help="Build a research summary from existing workflow outputs.",
    )
    research_summary.add_argument("research_csv", type=Path)
    research_summary.add_argument("--workflow-dir", default=Path("research-dist"), type=Path)
    research_summary.add_argument("--output", default=Path("research_summary.json"), type=Path)

    research_memo = research_subparsers.add_parser(
        "memo",
        help="Generate research memos from a research workflow.",
    )
    research_memo.add_argument("research_csv", type=Path)
    research_memo.add_argument("--workflow-dir", default=Path("research-dist"), type=Path)
    research_memo.add_argument("--output-dir", type=Path)
    research_memo.add_argument("--format", choices=["both", "markdown", "html"], default="both")

    research_pack = research_subparsers.add_parser(
        "pack",
        help="Generate Markdown and HTML research pack handoff files.",
    )
    research_pack.add_argument("research_csv", type=Path)
    research_pack.add_argument("--workflow-dir", default=Path("research-dist"), type=Path)
    research_pack.add_argument("--output-dir", default=Path("research-dist/packs"), type=Path)

    research_action = research_subparsers.add_parser("action", help="Manage persisted review-action state.")
    research_action_subparsers = research_action.add_subparsers(dest="research_action_command")

    research_action_list = research_action_subparsers.add_parser("list", help="List review actions with persisted state.")
    research_action_list.add_argument("research_summary", type=Path)
    research_action_list.add_argument("--state", type=Path, help="Path to review_action_state.json.")

    research_action_report = research_action_subparsers.add_parser("report", help="Report review action state health.")
    research_action_report.add_argument("research_summary", type=Path)
    research_action_report.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    research_action_report.add_argument("--next-open-limit", type=int, default=5)

    research_action_prune = research_action_subparsers.add_parser("prune-stale", help="Prune stale review-action state entries.")
    research_action_prune.add_argument("research_summary", type=Path)
    research_action_prune.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    research_action_prune.add_argument("--write", action="store_true", help="Rewrite the state file after pruning stale entries.")

    research_action_set = research_action_subparsers.add_parser("set", help="Set persisted review-action state.")
    research_action_set.add_argument("state_path", type=Path)
    research_action_set.add_argument("stock_id")
    research_action_set.add_argument("action_id")
    research_action_set.add_argument("--status", required=True, choices=ACTION_STATUSES)
    research_action_set.add_argument("--note", default="")

    research_run = research_subparsers.add_parser("run", help="Run workflow from a research CSV.")
    research_run.add_argument("research_csv", type=Path)
    research_run.add_argument("--output-dir", default=Path("research-dist"), type=Path)
    research_run.add_argument("--fixture-root", type=Path)
    research_run.add_argument("--offline-prices", action="store_true")
    research_run.add_argument("--valuation-csv", type=Path)
    research_run.add_argument("--skip-valuation", action="store_true")
    research_run.add_argument("--skip-memos", action="store_true")
    research_run.add_argument("--skip-packs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    if raw_args and raw_args[0] in {"compare", "batch", "dashboard", "price-template", "memo", "workflow", "doctor", "research"}:
        args = build_command_arg_parser().parse_args(raw_args)
    else:
        args = build_arg_parser().parse_args(raw_args)
        json_path, html_path = run(
            stock_id=args.stock_id,
            company_name=args.company_name,
            output_dir=args.output_dir,
            fixture_dir=args.fixture,
            valuation_csv=args.valuation_csv,
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {html_path}")
        return 0

    if args.command == "compare":
        json_path, html_path = run_compare(
            args.stock_ids,
            output_dir=args.output_dir,
            fixture_root=args.fixture_root,
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {html_path}")
        return 0

    if args.command == "batch":
        summary_path = run_batch(
            args.watchlist,
            output_dir=args.output_dir,
            fixture_root=args.fixture_root,
            valuation_csv=args.valuation_csv,
        )
        print(f"Wrote {summary_path}")
        return 0

    if args.command == "dashboard":
        scan_dirs = args.scan_dir or [
            Path("dist"),
            Path("live-dist"),
            Path("compare-dist"),
            Path("batch-dist"),
            Path("workflow-dist"),
        ]
        output_path = write_dashboard_index(scan_dirs, args.output)
        print(f"Wrote {output_path}")
        return 0

    if args.command == "price-template":
        fetch_price = offline_price if args.offline else None
        output_path = write_valuation_template(
            args.stock_ids,
            args.output,
            analysis_dir=args.analysis_dir,
            fetch_price=fetch_price,
        )
        print(f"Wrote {output_path}")
        return 0

    if args.command == "memo":
        output_path = write_memo(args.analysis_json, args.output, output_format=args.format)
        print(f"Wrote {output_path}")
        return 0

    if args.command == "workflow":
        from taiwan_stock_analysis.workflow import run_watchlist_workflow

        summary_path = run_watchlist_workflow(
            args.watchlist,
            args.output_dir,
            fixture_root=args.fixture_root,
            offline_prices=args.offline_prices,
            valuation_csv=args.valuation_csv,
            include_valuation=not args.skip_valuation,
        )
        print(f"Wrote {summary_path}")
        print(f"Open {args.output_dir / 'dashboard.html'}")
        return 0

    if args.command == "doctor":
        if args.doctor_command == "release":
            result = check_release_readiness(Path.cwd(), expected_version=args.version)
            print(format_doctor_result(result))
            return 0 if result.ok else 1
        build_command_arg_parser().error("doctor command is required")

    if args.command == "research":
        if args.research_command == "init":
            output_path = write_research_template(args.output)
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "summary":
            output_path = write_research_summary(args.research_csv, args.workflow_dir, args.output)
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "memo":
            research_summary_path = args.workflow_dir / "research_summary.json"
            if not research_summary_path.exists():
                write_research_summary(args.research_csv, args.workflow_dir, research_summary_path)
            output_dir = args.output_dir or (args.workflow_dir / "memos")
            output_path = write_research_memos(
                research_summary_path,
                args.workflow_dir,
                output_dir,
                output_format=args.format,
            )
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "pack":
            from taiwan_stock_analysis.pack import write_research_pack

            research_summary_path = args.workflow_dir / "research_summary.json"
            if not research_summary_path.exists():
                write_research_summary(args.research_csv, args.workflow_dir, research_summary_path)
            workflow_summary_path = args.workflow_dir / "workflow_summary.json"
            memo_summary_path = args.workflow_dir / "memos" / "memo_summary.json"
            dashboard_path = args.workflow_dir / "dashboard.html"
            output_path = write_research_pack(
                research_summary_path,
                args.output_dir,
                research_csv_path=args.research_csv,
                workflow_summary_path=workflow_summary_path if workflow_summary_path.exists() else None,
                memo_summary_path=memo_summary_path if memo_summary_path.exists() else None,
                dashboard_path=dashboard_path if dashboard_path.exists() else None,
            )
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "action":
            if args.research_action_command == "set":
                output_path = set_review_action_state(
                    args.state_path,
                    args.stock_id,
                    args.action_id,
                    args.status,
                    note=args.note,
                )
                print(f"Wrote {output_path}")
                return 0
            if args.research_action_command == "list":
                payload = json.loads(args.research_summary.read_text(encoding="utf-8"))
                queue = payload.get("review_action_queue", {}) if isinstance(payload, dict) else {}
                state_path = args.state or (args.research_summary.parent / "review_action_state.json")
                state, warning = load_review_action_state(state_path)
                if warning:
                    print(f"Warning: {warning}")
                overlaid = apply_review_action_state(queue if isinstance(queue, list) else [], state)
                print("stock_id\tpriority\tstatus\tseverity\tcategory\taction_id\tmessage")
                for row in review_action_rows(overlaid):
                    print(
                        "\t".join(
                            [
                                row["stock_id"],
                                row["priority"],
                                row["status"],
                                row["severity"],
                                row["category"],
                                row["action_id"],
                                row["message"],
                            ]
                        )
                    )
                return 0
            if args.research_action_command == "report":
                payload = json.loads(args.research_summary.read_text(encoding="utf-8"))
                queue = payload.get("review_action_queue", {}) if isinstance(payload, dict) else {}
                state_path = args.state or (args.research_summary.parent / "review_action_state.json")
                state, warning = load_review_action_state(state_path)
                if warning:
                    print(f"Warning: {warning}")
                report = build_review_action_state_report(
                    queue if isinstance(queue, list) else [],
                    state,
                    next_open_limit=args.next_open_limit,
                )
                _print_review_action_state_report(report)
                return 0
            if args.research_action_command == "prune-stale":
                payload = json.loads(args.research_summary.read_text(encoding="utf-8"))
                queue = payload.get("review_action_queue", {}) if isinstance(payload, dict) else {}
                state_path = args.state or (args.research_summary.parent / "review_action_state.json")
                state, warning = load_review_action_state(state_path)
                if warning:
                    print(f"Warning: {warning}")
                    return 1
                pruned_state, stale_rows = prune_stale_review_action_state(
                    queue if isinstance(queue, list) else [],
                    state,
                )
                if args.write and state_path.exists():
                    write_review_action_state(state_path, pruned_state)
                    print(f"Pruned {len(stale_rows)} stale review action state entries")
                    return 0
                _print_review_action_stale_rows(stale_rows, write_enabled=args.write, state_exists=state_path.exists())
                return 0
            build_command_arg_parser().error("research action command is required")
        if args.research_command == "run":
            from taiwan_stock_analysis.workflow import run_watchlist_workflow

            watchlist_path = args.output_dir / "research_watchlist.csv"
            write_watchlist_from_research(args.research_csv, watchlist_path)
            workflow_summary = run_watchlist_workflow(
                watchlist_path,
                args.output_dir,
                fixture_root=args.fixture_root,
                offline_prices=args.offline_prices,
                valuation_csv=args.valuation_csv,
                include_valuation=not args.skip_valuation,
            )
            research_summary = write_research_summary(
                args.research_csv,
                args.output_dir,
                args.output_dir / "research_summary.json",
            )
            if not args.skip_memos:
                memo_summary = write_research_memos(
                    research_summary,
                    args.output_dir,
                    args.output_dir / "memos",
                )
            if not args.skip_packs:
                from taiwan_stock_analysis.pack import write_research_pack

                pack_summary = write_research_pack(
                    research_summary,
                    args.output_dir / "packs",
                    research_csv_path=args.research_csv,
                    workflow_summary_path=args.output_dir / "workflow_summary.json",
                    memo_summary_path=(args.output_dir / "memos" / "memo_summary.json")
                    if not args.skip_memos
                    else None,
                    dashboard_path=args.output_dir / "dashboard.html",
                )
            write_dashboard_index(
                [
                    args.output_dir,
                    args.output_dir / "reports",
                    args.output_dir / "valuation-reports",
                    args.output_dir / "comparison",
                    args.output_dir / "memos",
                    args.output_dir / "packs",
                ],
                args.output_dir / "dashboard.html",
            )
            print(f"Wrote {workflow_summary}")
            print(f"Wrote {research_summary}")
            if not args.skip_memos:
                print(f"Wrote {memo_summary}")
            if not args.skip_packs:
                print(f"Wrote {pack_summary}")
            print(f"Open {args.output_dir / 'dashboard.html'}")
            return 0
        build_command_arg_parser().error("research command is required")
    build_command_arg_parser().error("command is required")


def _print_review_action_state_report(report: dict[str, object]) -> None:
    by_status = report.get("by_status", {})
    status_counts = by_status if isinstance(by_status, dict) else {}
    print(f"total_actions: {report.get('total_actions', 0)}")
    print(
        "by_status: "
        + " ".join(f"{status}={status_counts.get(status, 0)}" for status in ACTION_STATUSES)
    )
    print(f"stale_state: {report.get('stale_count', 0)}")
    print(f"last_updated: {report.get('last_updated', '-')}")
    print("next_open:")
    print("stock_id\tpriority\tseverity\tcategory\taction_id\tmessage")
    next_open = report.get("next_open", [])
    for row in next_open if isinstance(next_open, list) else []:
        if not isinstance(row, dict):
            continue
        print(
            "\t".join(
                [
                    str(row.get("stock_id", "")),
                    str(row.get("priority", "")),
                    str(row.get("severity", "")),
                    str(row.get("category", "")),
                    str(row.get("action_id", "")),
                    str(row.get("message", "")),
                ]
            )
        )
    print("stale_state_entries:")
    print("stock_id\tstatus\taction_id\tupdated_at\tnote")
    stale_state = report.get("stale_state", [])
    for row in stale_state if isinstance(stale_state, list) else []:
        if not isinstance(row, dict):
            continue
        print(
            "\t".join(
                [
                    str(row.get("stock_id", "")),
                    str(row.get("status", "")),
                    str(row.get("action_id", "")),
                    str(row.get("updated_at", "")),
                    str(row.get("note", "")),
                ]
            )
        )


def _print_review_action_stale_rows(
    stale_rows: list[dict[str, str]],
    *,
    write_enabled: bool = False,
    state_exists: bool = True,
) -> None:
    if write_enabled and not state_exists:
        print("Pruned 0 stale review action state entries")
        return
    print(f"stale_state: {len(stale_rows)}")
    print("mode: dry-run")
    print("stock_id\tstatus\taction_id\tupdated_at\tnote")
    for row in stale_rows:
        print(
            "\t".join(
                [
                    row["stock_id"],
                    row["status"],
                    row["action_id"],
                    row["updated_at"],
                    row["note"],
                ]
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
