from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from taiwan_stock_analysis.comparison import compare_results
from taiwan_stock_analysis.dashboard import write_dashboard_index
from taiwan_stock_analysis.diagnostics import build_diagnostics
from taiwan_stock_analysis.doctor import (
    check_demo_readiness,
    check_handoff_readiness,
    check_release_readiness,
    format_demo_doctor_result,
    format_doctor_result,
    format_handoff_doctor_result,
)
from taiwan_stock_analysis.fetcher import GoodinfoClient, build_metadata
from taiwan_stock_analysis.insights import build_insights
from taiwan_stock_analysis.industry_trends import write_industry_trend_report
from taiwan_stock_analysis.market_data_importer import write_market_data_bundle
from taiwan_stock_analysis.market_intelligence import (
    fetch_feed_news,
    fetch_fund_flow_history,
    fetch_twse_news,
    load_fund_flow_rows,
    load_news_rows,
    write_market_intelligence_report,
)
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
    backup_review_action_state,
    build_review_action_state_report,
    list_review_action_state_backups,
    load_review_action_state,
    prune_stale_review_action_state,
    review_action_rows,
    restore_review_action_state,
    set_review_action_state,
    write_review_action_state,
)
from taiwan_stock_analysis.scoring import build_scorecard
from taiwan_stock_analysis.sentiment_validation import write_sentiment_validation_report
from taiwan_stock_analysis.valuation import build_valuation
from taiwan_stock_analysis.verification import build_verification
from taiwan_stock_analysis.watchlist import load_watchlist


REPORT_FILES = {
    "income_statement": ("IS_YEAR", "IS_YEAR.html"),
    "balance_sheet": ("BS_YEAR", "BS_YEAR.html"),
    "cash_flow": ("CF_YEAR", "CF_YEAR.html"),
}

DashboardOpener = Callable[[Path], None]


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
    dashboard_parser.add_argument("--serve", action="store_true", help="Serve an interactive local dashboard API.")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Dashboard server host.")
    dashboard_parser.add_argument("--port", default=8765, type=int, help="Dashboard server port.")
    dashboard_parser.add_argument("--open", action="store_true", help="Open the local dashboard server in a browser.")

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

    demo_parser = subparsers.add_parser("demo", help="Run bundled local demos.")
    demo_subparsers = demo_parser.add_subparsers(dest="demo_command")
    demo_quickstart = demo_subparsers.add_parser("quickstart", help="Run the synthetic offline quickstart demo.")
    demo_quickstart.add_argument("--output-dir", default=Path("demo-dist"), type=Path)
    demo_quickstart.add_argument("--research-csv", default=Path("examples/research.csv"), type=Path)
    demo_quickstart.add_argument("--fixture-root", default=Path("examples/fixtures"), type=Path)
    demo_quickstart.add_argument("--industry-price-history", default=Path("examples/industry_price_history.csv"), type=Path)
    demo_quickstart.add_argument("--market-news-csv", default=Path("examples/market_news.csv"), type=Path)
    demo_quickstart.add_argument("--market-fund-flow-csv", default=Path("examples/fund_flow.csv"), type=Path)
    demo_quickstart.add_argument("--market-as-of", default="2026-07-12T12:00:00+08:00")

    doctor_parser = subparsers.add_parser("doctor", help="Run local project health checks.")
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command")
    doctor_release = doctor_subparsers.add_parser("release", help="Check release readiness.")
    doctor_release.add_argument("--version", help="Expected release version, for example 0.10.0.")
    doctor_demo = doctor_subparsers.add_parser("demo", help="Check bundled demo output readiness.")
    doctor_demo.add_argument("--output-dir", default=Path("demo-dist"), type=Path)
    doctor_demo.add_argument("--json", action="store_true", help="Print demo readiness as JSON.")
    doctor_demo.add_argument("--open", action="store_true", help="Open dashboard.html when demo readiness passes.")
    doctor_handoff = doctor_subparsers.add_parser("handoff", help="Check research handoff quality gate.")
    doctor_handoff.add_argument("research_summary", type=Path)
    doctor_handoff.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    doctor_handoff.add_argument("--blocker-limit", type=int, default=3)
    doctor_handoff.add_argument("--write-pack", action="store_true", help="Write a handoff evidence pack after the gate check.")
    doctor_handoff.add_argument("--pack-output-dir", type=Path, help="Directory for handoff evidence pack outputs.")
    doctor_handoff.add_argument("--format", choices=["both", "markdown", "html"], default="both")
    doctor_handoff.add_argument("--json", action="store_true", help="Print handoff readiness as JSON.")

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
    research_summary.add_argument("--industry-trend-report", type=Path)

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

    research_handoff_pack = research_subparsers.add_parser(
        "handoff-pack",
        help="Generate a handoff evidence pack from a research summary and review-action state.",
    )
    research_handoff_pack.add_argument("research_summary", type=Path)
    research_handoff_pack.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    research_handoff_pack.add_argument("--output-dir", type=Path)
    research_handoff_pack.add_argument("--format", choices=["both", "markdown", "html"], default="both")
    research_handoff_pack.add_argument("--blocker-limit", type=int, default=10)

    research_industry_trends = research_subparsers.add_parser(
        "industry-trends",
        help="Generate an industry trend report from research and price-history CSV files.",
    )
    research_industry_trends.add_argument("research_csv", type=Path)
    research_industry_trends.add_argument("--price-history", required=True, type=Path)
    research_industry_trends.add_argument("--output-dir", default=Path("research-dist/industry-trends"), type=Path)

    research_sentiment_backtest = research_subparsers.add_parser(
        "sentiment-backtest",
        help="Evaluate retained industry sentiment history with walk-forward validation.",
    )
    research_sentiment_backtest.add_argument("history_csv", type=Path)
    research_sentiment_backtest.add_argument(
        "--output",
        default=Path("sentiment_backtest_report.json"),
        type=Path,
    )

    research_market_intelligence = research_subparsers.add_parser(
        "market-intelligence",
        help="Combine industry trends, latest news keywords, and institutional fund flow.",
    )
    research_market_intelligence.add_argument("research_csv", type=Path)
    research_market_intelligence.add_argument("--industry-trend-report", type=Path)
    research_market_intelligence.add_argument("--news-csv", action="append", default=[], type=Path)
    research_market_intelligence.add_argument("--news-feed", action="append", default=[])
    research_market_intelligence.add_argument("--fetch-twse-news", action="store_true")
    research_market_intelligence.add_argument("--fund-flow-csv", action="append", default=[], type=Path)
    research_market_intelligence.add_argument("--fetch-twse-fund-flow", action="store_true")
    research_market_intelligence.add_argument("--fetch-tpex-fund-flow", action="store_true")
    research_market_intelligence.add_argument("--as-of", help="ISO date or datetime used for freshness checks.")
    research_market_intelligence.add_argument(
        "--output-dir",
        default=Path("research-dist/market-intelligence"),
        type=Path,
    )

    research_market_data = research_subparsers.add_parser(
        "market-data",
        help="Fetch official TWSE/TPEx profiles, industries, prices, and institutional flow.",
    )
    research_market_data.add_argument("research_csv", type=Path)
    research_market_data.add_argument("--output-dir", default=Path("research-dist/market-data"), type=Path)
    research_market_data.add_argument("--as-of", help="ISO date used for price history and freshness.")
    research_market_data.add_argument("--history-months", type=int, default=3)
    research_market_data.add_argument("--replace-category", action="store_true")

    research_action = research_subparsers.add_parser("action", help="Manage persisted review-action state.")
    research_action_subparsers = research_action.add_subparsers(dest="research_action_command")

    research_action_list = research_action_subparsers.add_parser("list", help="List review actions with persisted state.")
    research_action_list.add_argument("research_summary", type=Path)
    research_action_list.add_argument("--state", type=Path, help="Path to review_action_state.json.")

    research_action_report = research_action_subparsers.add_parser("report", help="Report review action state health.")
    research_action_report.add_argument("research_summary", type=Path)
    research_action_report.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    research_action_report.add_argument("--next-open-limit", type=int, default=5)

    research_action_backups = research_action_subparsers.add_parser("backups", help="List review-action state backup files.")
    research_action_backups.add_argument("state_path", type=Path)
    research_action_backups.add_argument("--json", action="store_true", help="Print backup list as JSON.")

    research_action_prune = research_action_subparsers.add_parser("prune-stale", help="Prune stale review-action state entries.")
    research_action_prune.add_argument("research_summary", type=Path)
    research_action_prune.add_argument("--state", type=Path, help="Path to review_action_state.json.")
    research_action_prune.add_argument("--write", action="store_true", help="Rewrite the state file after pruning stale entries.")

    research_action_restore = research_action_subparsers.add_parser("restore", help="Restore review-action state from a backup file.")
    research_action_restore.add_argument("state_path", type=Path)
    research_action_restore.add_argument("backup_path", type=Path)

    research_action_set = research_action_subparsers.add_parser("set", help="Set persisted review-action state.")
    research_action_set.add_argument("state_path", type=Path)
    research_action_set.add_argument("stock_id")
    research_action_set.add_argument("action_id")
    research_action_set.add_argument("--status", required=True, choices=ACTION_STATUSES)
    # default=None (not "") so an omitted flag means "preserve the currently
    # stored value" -- set_review_action_state() treats None that way. A
    # status-only `research action set ... --status done` re-set (no --note/
    # --reviewer/--evidence-url) therefore keeps any evidence a prior explicit
    # call already recorded, instead of silently clearing it.
    research_action_set.add_argument("--note", default=None)
    research_action_set.add_argument("--reviewer", default=None)
    research_action_set.add_argument("--evidence-url", default=None)

    research_run = research_subparsers.add_parser("run", help="Run workflow from a research CSV.")
    research_run.add_argument("research_csv", type=Path)
    research_run.add_argument("--output-dir", default=Path("research-dist"), type=Path)
    research_run.add_argument("--fixture-root", type=Path)
    research_run.add_argument("--offline-prices", action="store_true")
    research_run.add_argument("--valuation-csv", type=Path)
    research_run.add_argument("--skip-valuation", action="store_true")
    research_run.add_argument("--skip-memos", action="store_true")
    research_run.add_argument("--skip-packs", action="store_true")
    research_run.add_argument("--industry-price-history", type=Path)
    research_run.add_argument("--skip-industry-trends", action="store_true")
    research_run.add_argument("--market-news-csv", action="append", default=[], type=Path)
    research_run.add_argument("--market-news-feed", action="append", default=[])
    research_run.add_argument("--fetch-twse-news", action="store_true")
    research_run.add_argument("--market-fund-flow-csv", action="append", default=[], type=Path)
    research_run.add_argument("--fetch-twse-fund-flow", action="store_true")
    research_run.add_argument("--fetch-tpex-fund-flow", action="store_true")
    research_run.add_argument("--market-as-of", help="ISO date or datetime used for freshness checks.")
    research_run.add_argument("--skip-market-intelligence", action="store_true")
    research_run.add_argument("--fetch-market-data", action="store_true")
    research_run.add_argument("--market-data-as-of", help="ISO date used for official market-data import.")
    research_run.add_argument("--market-data-history-months", type=int, default=3)
    research_run.add_argument("--replace-category-with-official", action="store_true")
    return parser


def _collect_market_intelligence_inputs(
    *,
    news_csv_paths: list[Path],
    news_feed_urls: list[str],
    include_twse_news: bool,
    fund_flow_csv_paths: list[Path],
    include_twse_fund_flow: bool,
    include_tpex_fund_flow: bool,
    as_of: str | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, str], list[str]]:
    news_rows: list[dict[str, object]] = []
    fund_flow_rows: list[dict[str, object]] = []
    dependencies: dict[str, str] = {}
    source_errors: list[str] = []
    for index, path in enumerate(news_csv_paths, start=1):
        news_rows.extend(load_news_rows(path))
        dependencies[f"news_csv_{index}"] = str(path)
    for index, url in enumerate(news_feed_urls, start=1):
        dependencies[f"news_feed_{index}"] = url
        try:
            news_rows.extend(fetch_feed_news(url))
        except (OSError, ValueError) as exc:
            source_errors.append(f"news feed {url}: {exc}")
    if include_twse_news:
        dependencies["twse_news"] = "https://openapi.twse.com.tw/v1/news/newsList"
        try:
            news_rows.extend(fetch_twse_news())
        except (OSError, ValueError) as exc:
            source_errors.append(f"TWSE news: {exc}")
    for index, path in enumerate(fund_flow_csv_paths, start=1):
        fund_flow_rows.extend(load_fund_flow_rows(path))
        dependencies[f"fund_flow_csv_{index}"] = str(path)
    if include_twse_fund_flow:
        dependencies["twse_fund_flow"] = "https://www.twse.com.tw/rwd/zh/fund/T86"
    if include_tpex_fund_flow:
        dependencies["tpex_fund_flow"] = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
    markets = tuple(
        market
        for market, enabled in (
            ("TWSE", include_twse_fund_flow),
            ("TPEX", include_tpex_fund_flow),
        )
        if enabled
    )
    if markets:
        official_rows, official_errors = fetch_fund_flow_history(
            as_of=as_of,
            session_count=20,
            markets=markets,
        )
        fund_flow_rows.extend(official_rows)
        source_errors.extend(official_errors)
    return news_rows, fund_flow_rows, dependencies, source_errors


def _run_research_workflow_command(
    research_csv: Path,
    output_dir: Path,
    fixture_root: Path | None,
    offline_prices: bool,
    valuation_csv: Path | None,
    skip_valuation: bool,
    skip_memos: bool,
    skip_packs: bool,
    industry_price_history: Path | None = None,
    skip_industry_trends: bool = False,
    market_news_csv: list[Path] | None = None,
    market_news_feed: list[str] | None = None,
    fetch_twse_news_enabled: bool = False,
    market_fund_flow_csv: list[Path] | None = None,
    fetch_twse_fund_flow_enabled: bool = False,
    fetch_tpex_fund_flow_enabled: bool = False,
    market_as_of: str | None = None,
    skip_market_intelligence: bool = False,
    fetch_market_data_enabled: bool = False,
    market_data_as_of: str | None = None,
    market_data_history_months: int = 3,
    replace_category_with_official: bool = False,
) -> dict[str, Path | None]:
    from taiwan_stock_analysis.workflow import run_watchlist_workflow

    effective_research_csv = research_csv
    market_data_outputs: dict[str, Path] | None = None
    effective_market_fund_flow_csv = list(market_fund_flow_csv or [])
    if fetch_market_data_enabled:
        market_data_outputs = write_market_data_bundle(
            research_csv,
            output_dir / "market-data",
            as_of=market_data_as_of,
            history_months=market_data_history_months,
            replace_category=replace_category_with_official,
        )
        effective_research_csv = market_data_outputs["research_csv"]
        industry_price_history = market_data_outputs["price_history"]
        effective_market_fund_flow_csv.append(market_data_outputs["fund_flow"])
        fetch_twse_news_enabled = True
        market_as_of = market_as_of or market_data_as_of

    watchlist_path = output_dir / "research_watchlist.csv"
    write_watchlist_from_research(effective_research_csv, watchlist_path)
    workflow_summary = run_watchlist_workflow(
        watchlist_path,
        output_dir,
        fixture_root=fixture_root,
        offline_prices=offline_prices,
        valuation_csv=valuation_csv,
        include_valuation=not skip_valuation,
    )
    industry_trend_report: Path | None = None
    if not skip_industry_trends and industry_price_history is not None and industry_price_history.exists():
        industry_trend_report = write_industry_trend_report(
            effective_research_csv,
            industry_price_history,
            output_dir / "industry-trends",
        )
    market_intelligence_report: Path | None = None
    sentiment_history: Path | None = None
    market_inputs_requested = any(
        [
            market_news_csv,
            market_news_feed,
            fetch_twse_news_enabled,
            effective_market_fund_flow_csv,
            fetch_twse_fund_flow_enabled,
            fetch_tpex_fund_flow_enabled,
        ]
    )
    if not skip_market_intelligence and market_inputs_requested:
        news_rows, fund_flow_rows, dependencies, source_errors = _collect_market_intelligence_inputs(
            news_csv_paths=market_news_csv or [],
            news_feed_urls=market_news_feed or [],
            include_twse_news=fetch_twse_news_enabled,
            fund_flow_csv_paths=effective_market_fund_flow_csv,
            include_twse_fund_flow=fetch_twse_fund_flow_enabled,
            include_tpex_fund_flow=fetch_tpex_fund_flow_enabled,
            as_of=market_as_of,
        )
        market_intelligence_report = write_market_intelligence_report(
            effective_research_csv,
            output_dir / "market-intelligence",
            news_rows=news_rows,
            fund_flow_rows=fund_flow_rows,
            industry_trend_report_path=industry_trend_report,
            as_of=market_as_of,
            dependencies=dependencies,
            source_errors=source_errors,
        )
        sentiment_history_path = output_dir / "market-intelligence" / "industry_sentiment_history.csv"
        if sentiment_history_path.exists():
            sentiment_history = sentiment_history_path
    research_summary = write_research_summary(
        effective_research_csv,
        output_dir,
        output_dir / "research_summary.json",
        industry_trend_report_path=industry_trend_report,
    )
    memo_summary: Path | None = None
    if not skip_memos:
        memo_summary = write_research_memos(
            research_summary,
            output_dir,
            output_dir / "memos",
        )
    pack_summary: Path | None = None
    if not skip_packs:
        from taiwan_stock_analysis.pack import write_research_pack

        pack_summary = write_research_pack(
            research_summary,
            output_dir / "packs",
            research_csv_path=effective_research_csv,
            workflow_summary_path=output_dir / "workflow_summary.json",
            memo_summary_path=(output_dir / "memos" / "memo_summary.json") if not skip_memos else None,
            dashboard_path=output_dir / "dashboard.html",
        )
    write_dashboard_index(
        [
            output_dir,
            output_dir / "reports",
            output_dir / "valuation-reports",
            output_dir / "comparison",
            output_dir / "memos",
            output_dir / "packs",
            output_dir / "industry-trends",
            output_dir / "market-intelligence",
            output_dir / "market-data",
        ],
        output_dir / "dashboard.html",
    )
    return {
        "workflow_summary": workflow_summary,
        "research_summary": research_summary,
        "memo_summary": memo_summary,
        "pack_summary": pack_summary,
        "industry_trend_report": industry_trend_report,
        "market_intelligence_report": market_intelligence_report,
        "sentiment_history": sentiment_history,
        "market_data_report": market_data_outputs["report"] if market_data_outputs else None,
        "dashboard": output_dir / "dashboard.html",
    }


def _print_research_workflow_outputs(paths: dict[str, Path | None]) -> None:
    print(f"Wrote {paths['workflow_summary']}")
    print(f"Wrote {paths['research_summary']}")
    if paths["memo_summary"] is not None:
        print(f"Wrote {paths['memo_summary']}")
    if paths["pack_summary"] is not None:
        print(f"Wrote {paths['pack_summary']}")
    if paths.get("industry_trend_report") is not None:
        print(f"Wrote {paths['industry_trend_report']}")
    if paths.get("market_intelligence_report") is not None:
        print(f"Wrote {paths['market_intelligence_report']}")
    sentiment_history = paths.get("sentiment_history")
    if sentiment_history is not None and sentiment_history.exists():
        print(f"Wrote {sentiment_history}")
    if paths.get("market_data_report") is not None:
        print(f"Wrote {paths['market_data_report']}")
    print(f"Open {paths['dashboard']}")


def _open_dashboard(path: Path) -> None:
    resolved = path.resolve()
    if hasattr(os, "startfile"):
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    if not webbrowser.open(resolved.as_uri()):
        raise OSError("browser open returned false")


def main(argv: list[str] | None = None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    if raw_args and raw_args[0] in {"compare", "batch", "dashboard", "price-template", "memo", "workflow", "demo", "doctor", "research"}:
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
        if args.serve:
            from taiwan_stock_analysis.dashboard_server import serve_dashboard

            print(f"Serving dashboard at http://{args.host}:{args.port}/")
            serve_dashboard(scan_dirs, host=args.host, port=args.port, open_browser=args.open)
            return 0
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

    if args.command == "demo":
        if args.demo_command == "quickstart":
            paths = _run_research_workflow_command(
                args.research_csv,
                args.output_dir,
                fixture_root=args.fixture_root,
                offline_prices=True,
                valuation_csv=None,
                skip_valuation=False,
                skip_memos=False,
                skip_packs=False,
                industry_price_history=args.industry_price_history,
                market_news_csv=[args.market_news_csv],
                market_fund_flow_csv=[args.market_fund_flow_csv],
                market_as_of=args.market_as_of,
            )
            _print_research_workflow_outputs(paths)
            research_summary = paths["research_summary"]
            state_path = args.output_dir / "review_action_state.json"
            print("Next review-action commands:")
            print(f"python -m taiwan_stock_analysis.cli research action list {research_summary} --state {state_path}")
            print(f"python -m taiwan_stock_analysis.cli research action report {research_summary} --state {state_path}")
            print(
                "python -m taiwan_stock_analysis.cli research action set "
                f"{state_path} 2330 source-audit-manual-review --status done --note "
                '"checked source freshness" --reviewer "source-audit-lead" '
                f'--evidence-url "{args.output_dir / "evidence" / "2330-source.md"}"'
            )
            print(
                "python -m taiwan_stock_analysis.cli research handoff-pack "
                f"{research_summary} --state {state_path} --output-dir {args.output_dir / 'handoff-pack'}"
            )
            print(f"python -m taiwan_stock_analysis.cli research action backups {state_path}")
            return 0
        build_command_arg_parser().error("demo command is required")

    if args.command == "doctor":
        if args.doctor_command == "release":
            result = check_release_readiness(Path.cwd(), expected_version=args.version)
            print(format_doctor_result(result))
            return 0 if result.ok else 1
        if args.doctor_command == "demo":
            result = check_demo_readiness(args.output_dir)
            opened_dashboard = False
            open_error = ""
            if args.open and result.ok:
                dashboard_path = args.output_dir / "dashboard.html"
                try:
                    _open_dashboard(dashboard_path)
                except OSError as exc:
                    open_error = f"could not open {dashboard_path}: {exc}"
                else:
                    opened_dashboard = True
            if args.json:
                print(
                    json.dumps(
                        {
                            "failures": result.failures,
                            "messages": result.messages,
                            "ok": result.ok,
                            "open_error": open_error,
                            "opened_dashboard": opened_dashboard,
                            "output_dir": str(args.output_dir),
                            "repair_command": result.repair_command,
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
                if open_error:
                    return 1
                return 0 if result.ok else 1
            else:
                print(format_demo_doctor_result(result))
                if opened_dashboard:
                    print(f"Opened {args.output_dir / 'dashboard.html'}")
                if open_error:
                    print(f"Warning: {open_error}")
                    return 1
            return 0 if result.ok else 1
        if args.doctor_command == "handoff":
            result = check_handoff_readiness(
                args.research_summary,
                state_path=args.state,
                blocker_limit=args.blocker_limit,
            )
            pack_summary_path = ""
            if args.write_pack:
                from taiwan_stock_analysis.handoff_pack import write_handoff_evidence_pack

                output_dir = args.pack_output_dir or (args.research_summary.parent / "handoff-pack")
                try:
                    pack_summary = write_handoff_evidence_pack(
                        args.research_summary,
                        output_dir,
                        state_path=args.state,
                        output_format=args.format,
                        blocker_limit=args.blocker_limit,
                    )
                except ValueError as exc:
                    print(f"Warning: {exc}")
                    return 1
                pack_summary_path = str(pack_summary)
            if args.json:
                payload = asdict(result)
                if pack_summary_path:
                    payload["handoff_pack_summary_path"] = pack_summary_path
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(format_handoff_doctor_result(result))
                if pack_summary_path:
                    print(f"Wrote {pack_summary_path}")
            return 0 if result.ok else 1
        build_command_arg_parser().error("doctor command is required")

    if args.command == "research":
        if args.research_command == "init":
            output_path = write_research_template(args.output)
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "summary":
            output_path = write_research_summary(
                args.research_csv,
                args.workflow_dir,
                args.output,
                industry_trend_report_path=args.industry_trend_report,
            )
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
        if args.research_command == "handoff-pack":
            from taiwan_stock_analysis.handoff_pack import write_handoff_evidence_pack

            output_dir = args.output_dir or (args.research_summary.parent / "handoff-pack")
            try:
                output_path = write_handoff_evidence_pack(
                    args.research_summary,
                    output_dir,
                    state_path=args.state,
                    output_format=args.format,
                    blocker_limit=args.blocker_limit,
                )
            except ValueError as exc:
                print(f"Warning: {exc}")
                return 1
            print(f"Wrote {output_path}")
            return 0
        if args.research_command == "industry-trends":
            try:
                output_path = write_industry_trend_report(
                    args.research_csv,
                    args.price_history,
                    args.output_dir,
                )
            except ValueError as exc:
                print(f"Warning: {exc}")
                return 1
            print(f"Wrote {output_path}")
            print(f"Wrote {args.output_dir / 'industry_trend_report.md'}")
            print(f"Wrote {args.output_dir / 'industry_trend_report.html'}")
            return 0
        if args.research_command == "sentiment-backtest":
            try:
                write_sentiment_validation_report(args.history_csv, args.output)
            except (csv.Error, OSError, ValueError) as exc:
                print(f"Warning: {exc}")
                return 1
            print(f"Wrote {args.output}")
            return 0
        if args.research_command == "market-data":
            try:
                outputs = write_market_data_bundle(
                    args.research_csv,
                    args.output_dir,
                    as_of=args.as_of,
                    history_months=args.history_months,
                    replace_category=args.replace_category,
                )
            except (OSError, ValueError) as exc:
                print(f"Warning: {exc}")
                return 1
            for output_path in outputs.values():
                print(f"Wrote {output_path}")
            return 0
        if args.research_command == "market-intelligence":
            try:
                news_rows, fund_flow_rows, dependencies, source_errors = _collect_market_intelligence_inputs(
                    news_csv_paths=args.news_csv,
                    news_feed_urls=args.news_feed,
                    include_twse_news=args.fetch_twse_news,
                    fund_flow_csv_paths=args.fund_flow_csv,
                    include_twse_fund_flow=args.fetch_twse_fund_flow,
                    include_tpex_fund_flow=args.fetch_tpex_fund_flow,
                    as_of=args.as_of,
                )
                output_path = write_market_intelligence_report(
                    args.research_csv,
                    args.output_dir,
                    news_rows=news_rows,
                    fund_flow_rows=fund_flow_rows,
                    industry_trend_report_path=args.industry_trend_report,
                    as_of=args.as_of,
                    dependencies=dependencies,
                    source_errors=source_errors,
                )
            except (OSError, ValueError) as exc:
                print(f"Warning: {exc}")
                return 1
            print(f"Wrote {output_path}")
            print(f"Wrote {args.output_dir / 'market_intelligence_report.md'}")
            print(f"Wrote {args.output_dir / 'market_intelligence_report.html'}")
            sentiment_history_path = args.output_dir / "industry_sentiment_history.csv"
            if sentiment_history_path.exists():
                print(f"Wrote {sentiment_history_path}")
            for source_error in source_errors:
                print(f"Warning: {source_error}")
            return 0
        if args.research_command == "action":
            if args.research_action_command == "set":
                try:
                    output_path, backup_path = set_review_action_state(
                        args.state_path,
                        args.stock_id,
                        args.action_id,
                        args.status,
                        note=args.note,
                        reviewer=args.reviewer,
                        evidence_url=args.evidence_url,
                    )
                except ValueError as exc:
                    print(f"Warning: {exc}")
                    return 1
                _print_review_action_state_backup(backup_path)
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
                print("stock_id\tpriority\tstatus\tseverity\tcategory\taction_id\tnote\treviewer\tevidence_url\tupdated_at\tmessage")
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
                                row["note"],
                                row["reviewer"],
                                row["evidence_url"],
                                row["updated_at"],
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
            if args.research_action_command == "backups":
                rows = list_review_action_state_backups(args.state_path)
                if args.json:
                    print(
                        json.dumps(
                            {"backups": rows, "state_path": str(args.state_path)},
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                    )
                    return 0
                _print_review_action_state_backups(rows)
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
                    backup_path = backup_review_action_state(state_path)
                    write_review_action_state(state_path, pruned_state)
                    _print_review_action_state_backup(backup_path)
                    print(f"Pruned {len(stale_rows)} stale review action state entries")
                    return 0
                _print_review_action_stale_rows(stale_rows, write_enabled=args.write, state_exists=state_path.exists())
                return 0
            if args.research_action_command == "restore":
                try:
                    output_path, backup_path = restore_review_action_state(args.state_path, args.backup_path)
                except ValueError as exc:
                    print(f"Warning: {exc}")
                    return 1
                _print_review_action_state_backup(backup_path)
                print(f"Restored review action state: {output_path}")
                return 0
            build_command_arg_parser().error("research action command is required")
        if args.research_command == "run":
            paths = _run_research_workflow_command(
                args.research_csv,
                args.output_dir,
                fixture_root=args.fixture_root,
                offline_prices=args.offline_prices,
                valuation_csv=args.valuation_csv,
                skip_valuation=args.skip_valuation,
                skip_memos=args.skip_memos,
                skip_packs=args.skip_packs,
                industry_price_history=args.industry_price_history,
                skip_industry_trends=args.skip_industry_trends,
                market_news_csv=args.market_news_csv,
                market_news_feed=args.market_news_feed,
                fetch_twse_news_enabled=args.fetch_twse_news,
                market_fund_flow_csv=args.market_fund_flow_csv,
                fetch_twse_fund_flow_enabled=args.fetch_twse_fund_flow,
                fetch_tpex_fund_flow_enabled=args.fetch_tpex_fund_flow,
                market_as_of=args.market_as_of,
                skip_market_intelligence=args.skip_market_intelligence,
                fetch_market_data_enabled=args.fetch_market_data,
                market_data_as_of=args.market_data_as_of,
                market_data_history_months=args.market_data_history_months,
                replace_category_with_official=args.replace_category_with_official,
            )
            _print_research_workflow_outputs(paths)
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


def _print_review_action_state_backup(backup_path: Path | None) -> None:
    if backup_path is not None:
        print(f"Backup review action state: {backup_path}")


def _print_review_action_state_backups(rows: list[dict[str, object]]) -> None:
    print("created_at\tsize\tpath")
    for row in rows:
        print(f"{row.get('created_at', '')}\t{row.get('size', '')}\t{row.get('path', '')}")


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
