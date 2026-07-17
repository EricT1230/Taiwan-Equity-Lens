from __future__ import annotations

import csv
import json
import re
import ssl
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from taiwan_stock_analysis.industry_sentiment import (
    METHODOLOGY_VERSION,
    build_industry_sentiment_base,
    finalize_industry_sentiment,
)
from taiwan_stock_analysis.research import load_research_rows
from taiwan_stock_analysis.sentiment_history import (
    history_for_category,
    load_sentiment_history,
    sentiment_snapshot_from_industry,
    upsert_sentiment_snapshots,
)
from taiwan_stock_analysis.traceability import build_artifact_registry, build_run_metadata, merge_traceability


NON_ADVICE_NOTICE = (
    "This market-intelligence output is descriptive research context only and is not investment advice."
)
TWSE_NEWS_URL = "https://openapi.twse.com.tw/v1/news/newsList"
TWSE_FUND_FLOW_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_FUND_FLOW_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
TPEX_FUND_FLOW_HISTORY_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
DEFAULT_NEWS_MAX_AGE_HOURS = 96
DEFAULT_FUND_FLOW_MAX_AGE_DAYS = 5
DEFAULT_TREND_MAX_AGE_DAYS = 7
FINANCE_TERMS = {
    "AI",
    "CoWoS",
    "HBM",
    "半導體",
    "伺服器",
    "晶圓代工",
    "先進製程",
    "成熟製程",
    "供應鏈",
    "資料中心",
    "車用",
    "機器人",
    "電動車",
    "無人機",
    "軍工",
    "光通訊",
    "矽光子",
    "低軌衛星",
    "散熱",
    "重電",
    "生技",
    "新藥",
    "綠能",
    "儲能",
    "風電",
    "金融",
    "航運",
    "關稅",
    "匯率",
    "新台幣",
    "美元",
    "利率",
    "出口",
    "庫存",
    "營收",
    "法說",
    "資本支出",
    "併購",
}
KEYWORD_STOPWORDS = {
    "上市",
    "上櫃",
    "股票",
    "股份",
    "有限",
    "證券",
    "證交所",
    "交易所",
    "外資",
    "集中",
    "賣超",
    "買超",
    "上週",
    "最多",
    "申請",
    "方式",
    "辦理",
    "承銷",
    "拍賣",
    "公開",
    "公告",
    "公司",
    "表示",
    "今日",
    "今年",
    "市場",
    "台灣",
    "最新",
    "產業",
    "新聞",
    "投資",
    "相關",
    "持續",
}


def load_news_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted({"published_at", "title"} - fieldnames)
        if missing:
            raise ValueError(
                "news CSV must include published_at and title; missing: " + ", ".join(missing)
            )
        rows = []
        for index, row in enumerate(reader, start=2):
            title = str(row.get("title") or "").strip()
            published_at = _parse_datetime(row.get("published_at"))
            if not title:
                raise ValueError(f"news CSV row {index} must include a title")
            if published_at is None:
                raise ValueError(f"news CSV row {index} has invalid published_at")
            rows.append(
                {
                    "published_at": published_at.isoformat(),
                    "title": title,
                    "summary": str(row.get("summary") or "").strip(),
                    "url": str(row.get("url") or "").strip(),
                    "source": str(row.get("source") or path.name).strip(),
                }
            )
    return rows


def load_fund_flow_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = {"date", "stock_id", "foreign_net", "investment_trust_net", "dealer_net"}
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError("fund-flow CSV is missing: " + ", ".join(missing))
        rows = []
        for index, row in enumerate(reader, start=2):
            raw_date = str(row.get("date") or "").strip()
            stock_id = str(row.get("stock_id") or "").strip()
            parsed_date = _parse_date(raw_date)
            if parsed_date is None:
                raise ValueError(f"fund-flow CSV row {index} has invalid date")
            if not stock_id:
                raise ValueError(f"fund-flow CSV row {index} must include a stock_id")
            foreign_net = _number(row.get("foreign_net"), index, "foreign_net")
            trust_net = _number(row.get("investment_trust_net"), index, "investment_trust_net")
            dealer_net = _number(row.get("dealer_net"), index, "dealer_net")
            total_value = str(row.get("total_net") or "").strip()
            total_net = (
                _number(total_value, index, "total_net")
                if total_value
                else foreign_net + trust_net + dealer_net
            )
            traded_shares_value = str(row.get("traded_shares") or "").strip()
            traded_shares = (
                _number(traded_shares_value, index, "traded_shares")
                if traded_shares_value
                else None
            )
            rows.append(
                {
                    "date": parsed_date.isoformat(),
                    "stock_id": stock_id,
                    "company_name": str(row.get("company_name") or "").strip(),
                    "foreign_net": foreign_net,
                    "investment_trust_net": trust_net,
                    "dealer_net": dealer_net,
                    "total_net": total_net,
                    "traded_shares": traded_shares,
                    "source": str(row.get("source") or path.name).strip(),
                }
            )
    return rows


def fetch_twse_news() -> list[dict[str, Any]]:
    payload = _http_json(TWSE_NEWS_URL)
    if not isinstance(payload, list):
        raise ValueError("TWSE news API returned an unexpected payload")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("Title") or "").strip()
        published_at = _parse_datetime(item.get("Date"))
        if not title or published_at is None:
            continue
        rows.append(
            {
                "published_at": published_at.isoformat(),
                "title": title,
                "summary": "",
                "url": str(item.get("Url") or "").strip(),
                "source": "TWSE News OpenAPI",
            }
        )
    return rows


def fetch_feed_news(url: str) -> list[dict[str, Any]]:
    request = Request(url, headers={"User-Agent": "Taiwan-Equity-Lens/0.51"})
    with _open_url(request) as response:
        payload = response.read()
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError(f"news feed returned invalid XML: {url}") from exc
    rows: list[dict[str, Any]] = []
    channel_title = _xml_text(root, ["channel/title", "{*}title"]) or url
    entries = root.findall(".//item") or root.findall(".//{*}entry")
    for entry in entries:
        title = _xml_text(entry, ["title", "{*}title"])
        published = _xml_text(
            entry,
            ["pubDate", "published", "updated", "{*}published", "{*}updated"],
        )
        published_at = _parse_datetime(published)
        if not title or published_at is None:
            continue
        link = _xml_text(entry, ["link", "{*}link"])
        if not link:
            link_node = entry.find("{*}link")
            link = str(link_node.attrib.get("href") or "") if link_node is not None else ""
        rows.append(
            {
                "published_at": published_at.isoformat(),
                "title": title,
                "summary": _xml_text(entry, ["description", "summary", "{*}summary", "{*}content"]),
                "url": link,
                "source": channel_title,
            }
        )
    return rows


def parse_twse_fund_flow_payload(
    payload: Any,
    requested_date: date,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return []
    data_date = _required_payload_date(payload, requested_date, "TWSE T86")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("TWSE T86 data must be an explicitly present list")
    if not data:
        return []
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        raise ValueError("TWSE T86 fields must be an explicitly present list")
    fields = [str(field) for field in raw_fields]
    indexes = {
        "stock_id": _field_index(fields, "證券代號"),
        "company_name": _field_index(fields, "證券名稱"),
        "foreign_net": _field_index(fields, "外陸資買賣超股數(不含外資自營商)"),
        "investment_trust_net": _field_index(fields, "投信買賣超股數"),
        "dealer_net": _field_index(fields, "自營商買賣超股數"),
        "total_net": _field_index(fields, "三大法人買賣超股數"),
    }
    rows = []
    required_index = max(indexes.values())
    for row_index, raw_row in enumerate(data, start=1):
        if not isinstance(raw_row, list):
            raise ValueError(f"TWSE T86 row {row_index} is missing required flow columns")
        if len(raw_row) <= required_index:
            raise ValueError(f"TWSE T86 row {row_index} is missing required flow columns")
        rows.append(
            {
                "date": data_date.isoformat(),
                "stock_id": str(raw_row[indexes["stock_id"]]).strip(),
                "company_name": str(raw_row[indexes["company_name"]]).strip(),
                "foreign_net": _required_flow_number(
                    raw_row[indexes["foreign_net"]], "TWSE T86", row_index, "foreign_net"
                ),
                "investment_trust_net": _required_flow_number(
                    raw_row[indexes["investment_trust_net"]],
                    "TWSE T86",
                    row_index,
                    "investment_trust_net",
                ),
                "dealer_net": _required_flow_number(
                    raw_row[indexes["dealer_net"]], "TWSE T86", row_index, "dealer_net"
                ),
                "total_net": _required_flow_number(
                    raw_row[indexes["total_net"]], "TWSE T86", row_index, "total_net"
                ),
                "source": "TWSE T86",
            }
        )
    return rows


def parse_tpex_fund_flow_payload(
    payload: Any,
    requested_date: date,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("stat") != "ok":
        return []
    data_date = _required_payload_date(payload, requested_date, "TPEx dailyTrade")
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise ValueError("TPEx dailyTrade tables must be an explicitly present list")
    if not tables or not isinstance(tables[0], dict):
        raise ValueError("TPEx dailyTrade tables must contain table 0")
    data = tables[0].get("data")
    if not isinstance(data, list):
        raise ValueError("TPEx dailyTrade table 0 data must be an explicitly present list")
    rows = []
    for row_index, raw_row in enumerate(data, start=1):
        if not isinstance(raw_row, list):
            raise ValueError(f"TPEx dailyTrade row {row_index} is missing required flow columns")
        if len(raw_row) <= 23:
            raise ValueError(f"TPEx dailyTrade row {row_index} is missing required flow columns")
        rows.append(
            {
                "date": data_date.isoformat(),
                "stock_id": str(raw_row[0]).strip(),
                "company_name": str(raw_row[1]).strip(),
                "foreign_net": _required_flow_number(
                    raw_row[4], "TPEx dailyTrade", row_index, "foreign_net"
                ),
                "investment_trust_net": _required_flow_number(
                    raw_row[13], "TPEx dailyTrade", row_index, "investment_trust_net"
                ),
                "dealer_net": _required_flow_number(
                    raw_row[22], "TPEx dailyTrade", row_index, "dealer_net"
                ),
                "total_net": _required_flow_number(
                    raw_row[23], "TPEx dailyTrade", row_index, "total_net"
                ),
                "source": "TPEx dailyTrade",
            }
        )
    return rows


def fetch_twse_fund_flow_for_date(trade_date: date) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "date": trade_date.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json",
        }
    )
    payload = _http_json(f"{TWSE_FUND_FLOW_URL}?{query}")
    return parse_twse_fund_flow_payload(payload, trade_date)


def fetch_tpex_fund_flow_for_date(trade_date: date) -> list[dict[str, Any]]:
    payload = _http_post_form_json(
        TPEX_FUND_FLOW_HISTORY_URL,
        {
            "type": "Daily",
            "sect": "EW",
            "date": trade_date.strftime("%Y/%m/%d"),
            "response": "json",
        },
    )
    return parse_tpex_fund_flow_payload(payload, trade_date)


def fetch_twse_fund_flow(
    *,
    as_of: date | datetime | str | None = None,
    lookback_days: int = 10,
) -> list[dict[str, Any]]:
    target = _as_of_datetime(as_of).date()
    for offset in range(max(1, lookback_days)):
        requested = target - timedelta(days=offset)
        rows = fetch_twse_fund_flow_for_date(requested)
        if rows:
            return rows
    return []


def fetch_tpex_fund_flow() -> list[dict[str, Any]]:
    payload = _http_json(TPEX_FUND_FLOW_URL)
    if not isinstance(payload, list):
        raise ValueError("TPEx institutional-flow API returned an unexpected payload")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("SecuritiesCompanyCode") or "").strip()
        flow_date = _parse_date(item.get("Date"))
        if not stock_id or flow_date is None:
            continue
        rows.append(
            {
                "date": flow_date.isoformat(),
                "stock_id": stock_id,
                "company_name": str(item.get("CompanyName") or "").strip(),
                "foreign_net": _plain_number(
                    item.get("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference")
                    or item.get("ForeignInvestorsInclude MainlandAreaInvestors-Difference")
                ),
                "investment_trust_net": _plain_number(
                    item.get("SecuritiesInvestmentTrustCompanies-Difference")
                ),
                "dealer_net": _plain_number(item.get("Dealers-Difference")),
                "total_net": _plain_number(item.get("TotalDifference")),
                "source": "TPEx 3insti daily trading",
            }
        )
    return rows


def fetch_fund_flow_history(
    *,
    as_of: date | datetime | str | None = None,
    session_count: int = 20,
    max_calendar_days: int = 45,
    markets: tuple[str, ...] = ("TWSE", "TPEX"),
) -> tuple[list[dict[str, Any]], list[str]]:
    target = _as_of_datetime(as_of).date()
    selected = tuple(dict.fromkeys(markets))
    sessions = {market: set() for market in selected}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    fetchers = {
        "TWSE": fetch_twse_fund_flow_for_date,
        "TPEX": fetch_tpex_fund_flow_for_date,
    }
    for offset in range(max_calendar_days):
        requested = target - timedelta(days=offset)
        if requested.weekday() >= 5:
            continue
        for market in selected:
            if len(sessions[market]) >= session_count:
                continue
            try:
                daily_rows = fetchers[market](requested)
            except (OSError, ValueError) as exc:
                errors.append(f"{market} fund flow {requested.isoformat()}: {exc}")
                continue
            if daily_rows:
                sessions[market].add(requested.isoformat())
                rows.extend(daily_rows)
        if all(len(values) >= session_count for values in sessions.values()):
            break
    deduped = {
        (str(row["date"]), str(row["stock_id"]), str(row["source"])): row
        for row in rows
    }
    ordered = [deduped[key] for key in sorted(deduped)]
    for market, values in sessions.items():
        if len(values) < session_count:
            errors.append(f"{market} fund flow: collected {len(values)} of {session_count} sessions")
    return ordered, errors


def build_market_intelligence_report(
    research_path: Path,
    *,
    news_rows: Iterable[dict[str, Any]],
    fund_flow_rows: Iterable[dict[str, Any]],
    industry_trend_report_path: Path | None = None,
    as_of: date | datetime | str | None = None,
    news_max_age_hours: int = DEFAULT_NEWS_MAX_AGE_HOURS,
    fund_flow_max_age_days: int = DEFAULT_FUND_FLOW_MAX_AGE_DAYS,
    trend_max_age_days: int = DEFAULT_TREND_MAX_AGE_DAYS,
    source_errors: Iterable[str] = (),
    sentiment_history_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    research_rows = load_research_rows(research_path)
    generated_at = _as_of_datetime(as_of)
    normalized_news = _dedupe_news(news_rows)
    normalized_flows = list(fund_flow_rows)
    trend_report = _load_trend_report(industry_trend_report_path)
    mapped_news = _map_news(normalized_news, research_rows)
    mapped_flows = _map_fund_flows(normalized_flows, research_rows)
    freshness = _freshness(
        generated_at,
        normalized_news,
        normalized_flows,
        trend_report,
        news_max_age_hours=news_max_age_hours,
        fund_flow_max_age_days=fund_flow_max_age_days,
        trend_max_age_days=trend_max_age_days,
    )
    normalized_source_errors = [str(error) for error in source_errors if str(error).strip()]
    raw_session_dates = trend_report.get("session_dates")
    expected_session_dates = (
        [str(value) for value in raw_session_dates if str(value).strip()]
        if isinstance(raw_session_dates, list)
        else []
    )
    industries = _build_industries(
        research_rows,
        mapped_news,
        mapped_flows,
        trend_report,
        expected_session_dates=expected_session_dates,
        freshness=freshness,
        source_errors=normalized_source_errors,
        generated_at=generated_at,
    )
    rankable = sorted(
        [
            row
            for row in industries
            if _dict(row.get("sentiment_base")).get("score_5d") is not None
        ],
        key=lambda row: (
            -float(_dict(row["sentiment_base"])["score_5d"]),
            str(row["category"]),
        ),
    )
    ranks = {
        str(row["category"]): index
        for index, row in enumerate(rankable, start=1)
    }
    history_rows = list(sentiment_history_rows)
    for industry in industries:
        category = str(industry["category"])
        prior = history_for_category(
            history_rows,
            category=category,
            methodology_version=METHODOLOGY_VERSION,
            as_of_date=generated_at.date().isoformat(),
        )
        industry["sentiment"] = finalize_industry_sentiment(
            industry.pop("sentiment_base"),
            prior_history=prior,
            rank=ranks.get(category),
            ranked_count=len(rankable),
        )
    industries.sort(
        key=lambda row: (
            _dict(row.get("sentiment")).get("score_5d") is None,
            -float(_dict(row["sentiment"])["score_5d"])
            if _dict(row.get("sentiment")).get("score_5d") is not None
            else 0.0,
            str(row["category"]),
        )
    )
    coverage = _coverage(research_rows, mapped_news, mapped_flows, industries)
    quality_gate = _quality_gate(freshness, coverage, normalized_source_errors)
    return {
        "schema_version": 2,
        "kind": "market_intelligence_report",
        "sentiment_methodology_version": METHODOLOGY_VERSION,
        "generated_at": generated_at.isoformat(),
        "research_path": str(research_path),
        "industry_trend_report_path": str(industry_trend_report_path or ""),
        "freshness": freshness,
        "coverage": coverage,
        "quality_gate": quality_gate,
        "source_errors": normalized_source_errors,
        "top_keywords": _top_keywords(mapped_news),
        "industries": industries,
        "news": mapped_news,
        "fund_flows": mapped_flows,
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def write_market_intelligence_report(
    research_path: Path,
    output_dir: Path,
    *,
    news_rows: Iterable[dict[str, Any]],
    fund_flow_rows: Iterable[dict[str, Any]],
    industry_trend_report_path: Path | None = None,
    as_of: date | datetime | str | None = None,
    dependencies: dict[str, str] | None = None,
    source_errors: Iterable[str] = (),
    sentiment_history_path: Path | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "market_intelligence_report.json"
    markdown_path = output_dir / "market_intelligence_report.md"
    html_path = output_dir / "market_intelligence_report.html"
    history_path = sentiment_history_path or output_dir / "industry_sentiment_history.csv"
    history_existed_before = history_path.exists()
    history_rows = load_sentiment_history(history_path)
    report = build_market_intelligence_report(
        research_path,
        news_rows=news_rows,
        fund_flow_rows=fund_flow_rows,
        industry_trend_report_path=industry_trend_report_path,
        as_of=as_of,
        source_errors=source_errors,
        sentiment_history_rows=history_rows,
    )
    report_date = str(report["generated_at"])[:10]
    snapshots = [
        sentiment_snapshot_from_industry(report_date, industry)
        for industry in _list_of_dicts(report.get("industries"))
    ]
    upsert_sentiment_snapshots(history_path, snapshots)
    dependency_map = {"research_csv": str(research_path), **(dependencies or {})}
    if industry_trend_report_path is not None:
        dependency_map["industry_trend_report"] = str(industry_trend_report_path)
    if history_existed_before:
        dependency_map["sentiment_history"] = str(history_path)
    report = merge_traceability(
        report,
        run_metadata=build_run_metadata(
            "market-intelligence",
            "research market-intelligence",
            dependency_map,
            str(output_dir),
        ),
        artifact_registry=build_artifact_registry(
            str(json_path),
            dependencies=dependency_map,
            outputs={
                "markdown": str(markdown_path),
                "html": str(html_path),
                "sentiment_history": str(history_path),
            },
        ),
    )
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_market_intelligence_markdown(report), encoding="utf-8")
    html_path.write_text(render_market_intelligence_html(report), encoding="utf-8")
    return json_path


def _markdown_text(value: Any) -> str:
    text = str(value)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = escape(text, quote=False)
    return text.replace("\\", "\\\\").replace("|", "\\|")


def render_market_intelligence_markdown(report: dict[str, Any]) -> str:
    gate = _dict(report.get("quality_gate"))
    coverage = _dict(report.get("coverage"))
    lines = [
        "# Market Intelligence Industry Map",
        "",
        f"- generated_at: {_markdown_text(report.get('generated_at') or '-')}",
        f"- quality_gate: {_markdown_text(gate.get('status') or '-')}",
        "- news mapped: "
        f"{_markdown_text(coverage.get('news_mapped', 0))} / "
        f"{_markdown_text(coverage.get('news_total', 0))}",
        "- fund-flow coverage: "
        f"{_markdown_text(coverage.get('stocks_with_fund_flow', 0))} / "
        f"{_markdown_text(coverage.get('stocks_total', 0))} stocks",
        "",
        "## Industry Map",
        "",
        "| Industry | Price trend | News | Keywords | Foreign net | Trust net | Dealer net | Total net | Score (5D) | Baseline (20D) | Change | Confidence | Phase | Forecast (experimental) | Peak risk (experimental) | Trough risk (experimental) |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: |",
    ]
    for industry in _list_of_dicts(report.get("industries")):
        flow = _dict(industry.get("fund_flow"))
        trend = _dict(industry.get("market_trend"))
        sentiment = _dict(industry.get("sentiment"))
        forecast = _dict(sentiment.get("forecast"))
        turning_risk = _dict(sentiment.get("turning_risk"))
        lines.append(
            "| "
            + " | ".join(
                _markdown_text(value)
                for value in [
                    str(industry.get("category") or "-"),
                    str(trend.get("direction") or "missing"),
                    str(industry.get("news_count", 0)),
                    ", ".join(str(value) for value in industry.get("top_keywords", [])[:6]) or "-",
                    _integer_text(flow.get("foreign_net")),
                    _integer_text(flow.get("investment_trust_net")),
                    _integer_text(flow.get("dealer_net")),
                    _integer_text(flow.get("total_net")),
                    _decimal_text(sentiment.get("score_5d")),
                    _decimal_text(sentiment.get("baseline_20d")),
                    _signed_decimal_text(sentiment.get("change")),
                    str(sentiment.get("confidence") or "-"),
                    str(sentiment.get("cycle_phase") or "-"),
                    _status_text(forecast.get("status"))
                    if sentiment
                    else "-",
                    _risk_value_text(turning_risk, "peak_risk")
                    if sentiment
                    else "-",
                    _risk_value_text(turning_risk, "trough_risk")
                    if sentiment
                    else "-",
                ]
            )
            + " |"
        )
    sentiment_industries = [
        industry
        for industry in _list_of_dicts(report.get("industries"))
        if _dict(industry.get("sentiment"))
    ]
    if sentiment_industries:
        lines.extend(["", "## Sentiment Evidence", ""])
        for industry in sentiment_industries:
            sentiment = _dict(industry.get("sentiment"))
            forecast = _dict(sentiment.get("forecast"))
            turning_risk = _dict(sentiment.get("turning_risk"))
            lines.extend(
                [
                    f"### {_markdown_text(industry.get('category') or '-')}",
                    "",
                    "- Reasons:",
                ]
            )
            reasons = sentiment.get("reasons")
            if isinstance(reasons, list) and reasons:
                lines.extend(f"  - {_markdown_text(reason)}" for reason in reasons)
            else:
                lines.append("  - none")
            lines.append("- Warnings:")
            warnings = _sentiment_warnings(sentiment)
            if warnings:
                lines.extend(f"  - {_markdown_text(warning)}" for warning in warnings)
            else:
                lines.append("  - none")
            lines.extend(
                [
                    "- Forecast (experimental research aid): "
                    + _markdown_text(_forecast_text(forecast)),
                    "- Turning risk (experimental research aid; not a calibrated probability): "
                    + _markdown_text(_turning_risk_text(turning_risk)),
                    "",
                ]
            )
    blockers = gate.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Data Blockers", ""])
        lines.extend(f"- {_markdown_text(blocker)}" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Non-Advice Boundary",
            "",
            _markdown_text(report.get("non_advice_notice") or NON_ADVICE_NOTICE),
        ]
    )
    return "\n".join(lines) + "\n"


def render_market_intelligence_html(report: dict[str, Any]) -> str:
    gate = _dict(report.get("quality_gate"))
    coverage = _dict(report.get("coverage"))
    cards = "".join(_industry_card(row) for row in _list_of_dicts(report.get("industries")))
    blockers = gate.get("blockers", [])
    blocker_html = "".join(f"<li>{escape(str(item))}</li>" for item in blockers) if isinstance(blockers, list) else ""
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Market Intelligence Industry Map</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft JhengHei", system-ui, sans-serif; background: #f3f6fa; color: #172033; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    section, article {{ background: white; border: 1px solid #dbe4ef; border-radius: 10px; padding: 16px; }}
    section {{ margin-bottom: 16px; }} .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
    .summary div {{ border: 1px solid #e3eaf3; border-radius: 8px; padding: 10px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
    .metrics span {{ background: #f8fafc; border-radius: 6px; padding: 8px; }}
    .sentiment {{ margin-top: 14px; border-top: 1px solid #e3eaf3; padding-top: 12px; }}
    .sentiment-label {{ display: flex; align-items: center; gap: 7px; }}
    .sentiment-swatch {{ width: 12px; height: 12px; border-radius: 50%; background: #64748b; display: inline-block; }}
    .sentiment-extremely_optimistic {{ background: #b91c1c; }} .sentiment-optimistic {{ background: #f97316; }}
    .sentiment-neutral {{ background: #64748b; }} .sentiment-pessimistic {{ background: #2563eb; }}
    .sentiment-extremely_pessimistic {{ background: #1e3a8a; }}
    .sentiment-evidence {{ font-size: 0.92rem; }}
    .notice {{ background: #fffbeb; border-color: #fde68a; color: #92400e; }}
  </style>
</head>
<body>
<main data-market-intelligence-report="true">
  <section><h1>Market Intelligence Industry Map</h1>
    <div class="summary" data-market-intelligence-freshness-gate="true">
      <div><strong>{escape(str(gate.get('status') or '-'))}</strong><br>quality gate</div>
      <div><strong>{escape(str(coverage.get('news_mapped', 0)))} / {escape(str(coverage.get('news_total', 0)))}</strong><br>mapped news</div>
      <div><strong>{escape(str(coverage.get('stocks_with_fund_flow', 0)))} / {escape(str(coverage.get('stocks_total', 0)))}</strong><br>fund-flow coverage</div>
      <div><strong>{escape(str(coverage.get('industries_total', 0)))}</strong><br>industries</div>
    </div>
  </section>
  <section><h2>Industry Map</h2><div class="grid">{cards}</div></section>
  <section><h2>Data Blockers</h2>{f'<ul>{blocker_html}</ul>' if blocker_html else '<p>No data blockers.</p>'}</section>
  <section class="notice"><h2>Non-Advice Boundary</h2><p>{escape(str(report.get('non_advice_notice') or NON_ADVICE_NOTICE))}</p></section>
</main>
</body>
</html>
"""


def _build_industries(
    research_rows: list[dict[str, str]],
    news_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
    trend_report: dict[str, Any],
    *,
    expected_session_dates: list[str],
    freshness: dict[str, Any],
    source_errors: list[str],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    categories = sorted({row.get("category") or "Uncategorized" for row in research_rows})
    stocks_by_category = {
        category: [row["stock_id"] for row in research_rows if (row.get("category") or "Uncategorized") == category]
        for category in categories
    }
    trends = {
        str(item.get("category") or "Uncategorized"): item
        for item in _list_of_dicts(trend_report.get("categories"))
    }
    industries = []
    for category in categories:
        industry_news = [row for row in news_rows if category in row.get("matched_categories", [])]
        industry_flows = [row for row in flow_rows if row.get("category") == category]
        flow = _aggregate_flow(industry_flows)
        trend = trends.get(category, {})
        market_trend = {
            key: trend.get(key)
            for key in (
                "direction",
                "rotation_phase",
                "average_return_1d",
                "average_return_5d",
                "average_return_20d",
                "positive_breadth_5d",
                "positive_breadth_20d",
                "coverage_ratio_5d",
                "coverage_ratio_20d",
                "high_count_20d",
                "low_count_20d",
                "average_volume_ratio_5d",
                "covered_stock_ids",
                "coverage_count",
                "stock_count",
            )
        }
        category_freshness, price_coverage_warning = _category_sentiment_freshness(
            freshness,
            market_trend,
        )
        sentiment_base = build_industry_sentiment_base(
            news_rows=industry_news,
            trend={"category": category, **market_trend},
            flow_rows=industry_flows,
            expected_session_dates=expected_session_dates,
            freshness=category_freshness,
            source_errors=source_errors,
            as_of=generated_at,
        )
        if price_coverage_warning:
            assessment_warnings = sentiment_base.get("warnings")
            if isinstance(assessment_warnings, list):
                if price_coverage_warning not in assessment_warnings:
                    assessment_warnings.append(price_coverage_warning)
            else:
                sentiment_base["warnings"] = [price_coverage_warning]
            price_component = _dict(
                _dict(sentiment_base.get("components")).get("price")
            )
            component_warnings = price_component.get("warnings")
            if isinstance(component_warnings, list):
                if price_coverage_warning not in component_warnings:
                    component_warnings.append(price_coverage_warning)
            else:
                price_component["warnings"] = [price_coverage_warning]
        industries.append(
            {
                "category": category,
                "stock_ids": stocks_by_category[category],
                "market_trend": market_trend,
                "news_count": len(industry_news),
                "top_keywords": _top_keywords(industry_news),
                "latest_news": industry_news[:5],
                "fund_flow": flow,
                "context": _context_lines(trend, len(industry_news), flow),
                "sentiment_base": sentiment_base,
            }
        )
    return industries


def _category_sentiment_freshness(
    freshness: dict[str, Any],
    trend: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    category_freshness = dict(freshness)
    coverage_values = (
        _finite_number(trend.get("coverage_ratio_5d")),
        _finite_number(trend.get("coverage_ratio_20d")),
    )
    coverage_is_sufficient = all(
        value is not None and 0.80 <= value <= 1.0
        for value in coverage_values
    )
    if coverage_is_sufficient:
        return category_freshness, None

    warning = (
        "price excluded: insufficient category price coverage; both 5d and 20d "
        "coverage ratios must be at least 80.0%"
    )
    source_freshness = freshness.get(
        "price",
        freshness.get("industry_trend"),
    )
    if _freshness_value_is_fresh(source_freshness):
        price_freshness = (
            dict(source_freshness)
            if isinstance(source_freshness, Mapping)
            else {"source": source_freshness}
        )
        price_freshness.update(
            {
                "status": "insufficient_category_price_coverage",
                "coverage_ratio_5d": trend.get("coverage_ratio_5d"),
                "coverage_ratio_20d": trend.get("coverage_ratio_20d"),
            }
        )
        category_freshness["price"] = price_freshness
    return category_freshness, warning


def _freshness_value_is_fresh(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        if "fresh" in value:
            return value.get("fresh") is True
        value = value.get("status")
    return str(value or "").strip().lower() == "fresh"


def _map_news(news_rows: list[dict[str, Any]], research_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    mapped = []
    for row in news_rows:
        text = f"{row.get('title', '')} {row.get('summary', '')}".casefold()
        stocks = []
        categories = set()
        matched_terms = set()
        for research in research_rows:
            category = research.get("category") or "Uncategorized"
            terms = [research.get("stock_id", ""), research.get("company_name", ""), category]
            terms.extend(_split_terms(research.get("news_keywords", "")))
            hits = [term for term in terms if len(term.strip()) >= 2 and _term_in_text(term, text)]
            if hits:
                stocks.append(research["stock_id"])
                categories.add(category)
                matched_terms.update(hits)
        finance_hits = [term for term in FINANCE_TERMS if _term_in_text(term, text)]
        item = dict(row)
        item["matched_stock_ids"] = sorted(set(stocks))
        item["matched_categories"] = sorted(categories)
        item["keywords"] = sorted(matched_terms.union(finance_hits), key=lambda value: (-len(value), value))
        mapped.append(item)
    mapped.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    emerging = _emerging_keywords([item for item in mapped if item.get("matched_categories")])
    for item in mapped:
        if not item.get("matched_categories"):
            continue
        title = str(item.get("title") or "")
        extra = [term for term in emerging if term in title]
        item["keywords"] = list(dict.fromkeys([*item.get("keywords", []), *extra]))[:12]
    return mapped


def _map_fund_flows(rows: list[dict[str, Any]], research_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    research_by_stock = {row["stock_id"]: row for row in research_rows}
    mapped = []
    for row in rows:
        stock_id = str(row.get("stock_id") or "")
        research = research_by_stock.get(stock_id)
        item = dict(row)
        item["category"] = (research.get("category") or "Uncategorized") if research else ""
        item["in_research_universe"] = research is not None
        mapped.append(item)
    return sorted(mapped, key=lambda item: (str(item.get("date") or ""), str(item.get("stock_id") or "")), reverse=True)


def _freshness(
    as_of: datetime,
    news_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
    trend_report: dict[str, Any],
    *,
    news_max_age_hours: int,
    fund_flow_max_age_days: int,
    trend_max_age_days: int,
) -> dict[str, Any]:
    latest_news = max((_parse_datetime(row.get("published_at")) for row in news_rows), default=None)
    latest_flow = max((_parse_date(row.get("date")) for row in flow_rows), default=None)
    trend_date = _parse_date(trend_report.get("as_of_date"))
    news_age = _hours_between(as_of, latest_news)
    flow_age = (as_of.date() - latest_flow).days if latest_flow else None
    trend_age = (as_of.date() - trend_date).days if trend_date else None
    return {
        "news": _freshness_entry(latest_news.isoformat() if latest_news else "", news_age, news_max_age_hours, "hours"),
        "fund_flow": _freshness_entry(latest_flow.isoformat() if latest_flow else "", flow_age, fund_flow_max_age_days, "days"),
        "industry_trend": _freshness_entry(trend_date.isoformat() if trend_date else "", trend_age, trend_max_age_days, "days"),
    }


def _coverage(
    research_rows: list[dict[str, str]],
    news_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
    industries: list[dict[str, Any]],
) -> dict[str, int]:
    research_stocks = {row["stock_id"] for row in research_rows}
    flow_stocks = {str(row.get("stock_id")) for row in flow_rows if row.get("in_research_universe")}
    return {
        "stocks_total": len(research_stocks),
        "stocks_with_fund_flow": len(research_stocks.intersection(flow_stocks)),
        "news_total": len(news_rows),
        "news_mapped": sum(1 for row in news_rows if row.get("matched_categories")),
        "news_unmapped": sum(1 for row in news_rows if not row.get("matched_categories")),
        "industries_total": len(industries),
        "industries_with_news": sum(1 for row in industries if int(row.get("news_count") or 0) > 0),
        "industries_with_fund_flow": sum(1 for row in industries if int(_dict(row.get("fund_flow")).get("stock_count") or 0) > 0),
    }


def _quality_gate(
    freshness: dict[str, Any],
    coverage: dict[str, int],
    source_errors: list[str],
) -> dict[str, Any]:
    blockers = [f"source error: {error}" for error in source_errors]
    for source, label in (("news", "news"), ("fund_flow", "fund flow"), ("industry_trend", "industry trend")):
        status = _dict(freshness.get(source)).get("status")
        if status == "missing":
            blockers.append(f"missing {label} data")
        elif status == "stale":
            blockers.append(f"stale {label} data")
    if coverage.get("news_total", 0) and coverage.get("news_mapped", 0) == 0:
        blockers.append("news exists but none maps to the research universe; add news_keywords aliases")
    if coverage.get("stocks_total", 0) and coverage.get("stocks_with_fund_flow", 0) == 0:
        blockers.append("fund-flow data does not cover the research universe")
    status = "ready" if not blockers else "needs_data"
    return {
        "status": status,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "next_action": (
            "Review event, price-trend, and fund-flow context by industry."
            if status == "ready"
            else "Refresh blocked sources or extend research news_keywords, then rerun market-intelligence."
        ),
    }


def _aggregate_flow(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "as_of_date": "",
            "stock_count": 0,
            "foreign_net": 0,
            "investment_trust_net": 0,
            "dealer_net": 0,
            "total_net": 0,
            "direction": "missing",
        }
    latest_date = max(str(row.get("date") or "") for row in rows)
    latest_rows = [row for row in rows if str(row.get("date") or "") == latest_date]
    values = {
        field: int(sum(float(row.get(field) or 0) for row in latest_rows))
        for field in ("foreign_net", "investment_trust_net", "dealer_net", "total_net")
    }
    total = values["total_net"]
    return {
        "as_of_date": latest_date,
        "stock_count": len({str(row.get("stock_id")) for row in latest_rows}),
        **values,
        "direction": "net_inflow" if total > 0 else "net_outflow" if total < 0 else "flat",
    }


def _top_keywords(rows: list[dict[str, Any]], limit: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(str(value) for value in row.get("keywords", []) if str(value).strip())
    return [value for value, _ in sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))[:limit]]


def _emerging_keywords(rows: list[dict[str, Any]]) -> list[str]:
    document_frequency: Counter[str] = Counter()
    for row in rows:
        title = str(row.get("title") or "")
        candidates = set(re.findall(r"[A-Za-z][A-Za-z0-9+.-]{1,20}", title))
        document_frequency.update(
            value
            for value in candidates
            if value not in KEYWORD_STOPWORDS
            and not any(stop in value for stop in KEYWORD_STOPWORDS)
        )
    ranked = [
        value
        for value, count in sorted(
            document_frequency.items(),
            key=lambda item: (-(item[1] * max(2, len(item[0]))), -len(item[0]), item[0]),
        )
        if count >= 3
    ]
    selected: list[str] = []
    for value in ranked:
        if any(value in existing or existing in value for existing in selected):
            continue
        selected.append(value)
        if len(selected) >= 12:
            break
    return selected


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _decimal_text(value: Any) -> str:
    number = _finite_number(value)
    return f"{number:.1f}" if number is not None else "-"


def _signed_decimal_text(value: Any) -> str:
    number = _finite_number(value)
    return f"{number:+.1f}" if number is not None else "-"


def _status_text(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace("_", " ") if text else "-"


def _interval_text(value: Any) -> str:
    if not isinstance(value, list) or len(value) != 2:
        return ""
    lower = _finite_number(value[0])
    upper = _finite_number(value[1])
    if lower is None or upper is None:
        return ""
    return f" [{lower:.1f}, {upper:.1f}]"


def _forecast_text(forecast: dict[str, Any]) -> str:
    status = _status_text(forecast.get("status"))
    if status in {"insufficient history", "insufficient data"}:
        return status
    points = []
    for label, value_key, interval_key in (
        ("1D", "forecast_1d", "interval_1d"),
        ("5D", "forecast_5d", "interval_5d"),
    ):
        value = _finite_number(forecast.get(value_key))
        if value is not None:
            points.append(
                f"{label} {value:.1f}{_interval_text(forecast.get(interval_key))}"
            )
    return "; ".join(points) if points else status


def _risk_value_text(turning_risk: dict[str, Any], key: str) -> str:
    status = _status_text(turning_risk.get("status"))
    if status in {"insufficient history", "insufficient data"}:
        return status
    return _decimal_text(turning_risk.get(key))


def _turning_risk_text(turning_risk: dict[str, Any]) -> str:
    status = _status_text(turning_risk.get("status"))
    if status in {"insufficient history", "insufficient data"}:
        return status
    peak = _finite_number(turning_risk.get("peak_risk"))
    trough = _finite_number(turning_risk.get("trough_risk"))
    if peak is None and trough is None:
        return status
    peak_text = f"{peak:.1f}" if peak is not None else "unavailable"
    trough_text = f"{trough:.1f}" if trough is not None else "unavailable"
    return f"peak {peak_text}; trough {trough_text}"


def _sentiment_warnings(sentiment: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for payload in (
        sentiment,
        _dict(sentiment.get("forecast")),
        _dict(sentiment.get("turning_risk")),
    ):
        values = payload.get("warnings")
        if not isinstance(values, list):
            continue
        for value in values:
            text = str(value).strip()
            if text and text not in warnings:
                warnings.append(text)
    return warnings


def _industry_card(industry: dict[str, Any]) -> str:
    trend = _dict(industry.get("market_trend"))
    flow = _dict(industry.get("fund_flow"))
    keywords = ", ".join(str(value) for value in industry.get("top_keywords", [])[:8]) or "-"
    events = "".join(
        f'<li>{escape(str(item.get("published_at") or ""))} — {_event_link(item)}</li>'
        for item in _list_of_dicts(industry.get("latest_news"))[:3]
    ) or "<li>No mapped news.</li>"
    sentiment_html = _industry_sentiment_html(_dict(industry.get("sentiment")))
    return (
        f'<article data-market-intelligence-industry="{escape(str(industry.get("category") or ""))}">'
        f'<h3>{escape(str(industry.get("category") or "-"))}</h3>'
        f'<p><strong>Price trend:</strong> {escape(str(trend.get("direction") or "missing"))} / {escape(str(trend.get("rotation_phase") or "-"))}</p>'
        f'<p><strong>Keywords:</strong> {escape(keywords)}</p>'
        '<div class="metrics">'
        f'<span><strong>{escape(_integer_text(flow.get("foreign_net")))}</strong><br>外資</span>'
        f'<span><strong>{escape(_integer_text(flow.get("investment_trust_net")))}</strong><br>投信</span>'
        f'<span><strong>{escape(_integer_text(flow.get("dealer_net")))}</strong><br>自營商</span>'
        f'<span><strong>{escape(_integer_text(flow.get("total_net")))}</strong><br>合計</span>'
        "</div>"
        f"<ul>{events}</ul>"
        f"{sentiment_html}"
        "</article>"
    )


def _industry_sentiment_html(sentiment: dict[str, Any]) -> str:
    if not sentiment:
        return ""
    components = _dict(sentiment.get("components"))
    forecast = _dict(sentiment.get("forecast"))
    turning_risk = _dict(sentiment.get("turning_risk"))
    label = str(sentiment.get("label") or "unavailable")
    status = str(sentiment.get("status") or "unavailable")
    score_text = _decimal_text(sentiment.get("score_5d"))
    phase = str(sentiment.get("cycle_phase") or "unavailable")
    confidence = str(sentiment.get("confidence") or "unavailable")
    forecast_status = str(forecast.get("status") or "unavailable")
    risk_status = str(turning_risk.get("status") or "unavailable")
    component_lines = "".join(
        _component_contribution_html(display_name, _dict(components.get(name)))
        for name, display_name in (
            ("news", "News"),
            ("price", "Price"),
            ("fund_flow", "Fund flow"),
        )
    )
    reasons = _evidence_list_html(sentiment.get("reasons"), empty_text="No stated reasons.")
    warnings = _evidence_list_html(
        _sentiment_warnings(sentiment),
        empty_text="No sentiment warnings.",
    )
    return (
        f'<div class="sentiment" data-industry-sentiment="{escape(status, quote=True)}" '
        f'data-industry-sentiment-score="{escape(score_text, quote=True)}" '
        f'data-industry-sentiment-phase="{escape(phase, quote=True)}" '
        f'data-industry-sentiment-confidence="{escape(confidence, quote=True)}" '
        f'data-industry-sentiment-forecast="{escape(forecast_status, quote=True)}" '
        f'data-industry-turning-risk="{escape(risk_status, quote=True)}">'
        '<p class="sentiment-label">'
        f'<span class="sentiment-swatch sentiment-{escape(label, quote=True)}" aria-hidden="true"></span>'
        f'<strong>Sentiment label:</strong> {escape(label)}</p>'
        f'<p><strong>Score (5D):</strong> {escape(score_text)}; '
        f'<strong>baseline (20D):</strong> {escape(_decimal_text(sentiment.get("baseline_20d")))}; '
        f'<strong>change:</strong> {escape(_signed_decimal_text(sentiment.get("change")))}</p>'
        f'<p data-industry-sentiment-phase="{escape(phase, quote=True)}"><strong>Phase:</strong> {escape(phase)}</p>'
        f'<p data-industry-sentiment-confidence="{escape(confidence, quote=True)}"><strong>Confidence:</strong> {escape(confidence)}</p>'
        f'<ul class="sentiment-evidence">{component_lines}</ul>'
        f'<p data-industry-sentiment-forecast="{escape(forecast_status, quote=True)}"><strong>Forecast (experimental research aid):</strong> {escape(_forecast_text(forecast))}</p>'
        f'<p data-industry-turning-risk="{escape(risk_status, quote=True)}"><strong>Turning risk (experimental research aid; not a calibrated probability):</strong> {escape(_turning_risk_text(turning_risk))}</p>'
        f'<h4>Reasons</h4>{reasons}'
        f'<h4>Warnings</h4>{warnings}'
        "</div>"
    )


def _component_contribution_html(
    display_name: str,
    component: dict[str, Any],
) -> str:
    contribution = _signed_decimal_text(component.get("contribution_5d"))
    effective_weight = _finite_number(component.get("effective_weight"))
    weight_text = (
        f"{effective_weight * 100.0:.1f}%"
        if effective_weight is not None
        else "unavailable"
    )
    return (
        f"<li><strong>{escape(display_name)} contribution:</strong> "
        f"{escape(contribution)} (effective weight {escape(weight_text)})</li>"
    )


def _evidence_list_html(value: Any, *, empty_text: str) -> str:
    items = [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []
    if not items:
        items = [empty_text]
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _event_link(item: dict[str, Any]) -> str:
    title = escape(str(item.get("title") or "-"))
    url = str(item.get("url") or "").strip()
    if not url or any(character.isspace() for character in url) or "\\" in url:
        return title
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return title
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        return title
    return f'<a href="{escape(url, quote=True)}">{title}</a>'


def _context_lines(trend: dict[str, Any], news_count: int, flow: dict[str, Any]) -> list[str]:
    lines = [f"price direction: {trend.get('direction') or 'missing'}", f"mapped news: {news_count}"]
    lines.append(f"institutional flow: {flow.get('direction') or 'missing'}")
    return lines


def _load_trend_report(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid industry trend report: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid industry trend report: {path}")
    return payload


def _dedupe_news(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for row in rows:
        title = str(row.get("title") or "").strip()
        published = _parse_datetime(row.get("published_at"))
        if not title or published is None:
            continue
        key = (str(row.get("url") or "").strip(), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "published_at": published.isoformat(),
                "title": title,
                "summary": str(row.get("summary") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "source": str(row.get("source") or "unknown").strip(),
            }
        )
    return sorted(result, key=lambda item: item["published_at"], reverse=True)


def _http_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Taiwan-Equity-Lens/0.51"})
    with _open_url(request) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return json.loads(raw.decode(charset, errors="strict"))


def _http_post_form_json(url: str, fields: Mapping[str, str]) -> Any:
    body = urlencode(fields).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "User-Agent": "Taiwan-Equity-Lens/0.53",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with _open_url(request) as response:
        payload = response.read().decode("utf-8")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"form endpoint returned invalid JSON: {url}") from exc


def _open_url(request: Request):
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        context.verify_flags &= ~strict_flag
    return urlopen(request, timeout=20, context=context)  # noqa: S310 - caller controls audited source URL


def _parse_datetime(value: Any) -> datetime | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    roc_date = _parse_roc_date(text_value)
    if roc_date is not None:
        return datetime.combine(roc_date, time.min, timezone(timedelta(hours=8)))
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text_value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_date(value: Any) -> date | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    roc_date = _parse_roc_date(text_value)
    if roc_date is not None:
        return roc_date
    try:
        if re.fullmatch(r"\d{8}", text_value):
            return datetime.strptime(text_value, "%Y%m%d").date()
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def _parse_roc_date(value: str) -> date | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 7:
        return None
    try:
        return date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return None


def _as_of_datetime(value: date | datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone(timedelta(hours=8)))
    if isinstance(value, date):
        return datetime.combine(value, time.max, timezone(timedelta(hours=8)))
    if isinstance(value, str):
        parsed = _parse_datetime(value)
        if parsed is None:
            raise ValueError(f"invalid as_of value: {value}")
        return parsed
    return datetime.now(timezone(timedelta(hours=8)))


def _freshness_entry(latest: str, age: float | int | None, maximum: int, unit: str) -> dict[str, Any]:
    return {
        "latest": latest,
        "age": round(age, 2) if isinstance(age, float) else age,
        "unit": unit,
        "max_age": maximum,
        "status": "missing" if age is None else "fresh" if age <= maximum else "stale",
    }


def _hours_between(later: datetime, earlier: datetime | None) -> float | None:
    if earlier is None:
        return None
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return max(0.0, (later.astimezone(timezone.utc) - earlier.astimezone(timezone.utc)).total_seconds() / 3600)


def _field_index(fields: list[str], name: str) -> int:
    try:
        return fields.index(name)
    except ValueError as exc:
        raise ValueError(f"TWSE T86 is missing field: {name}") from exc


def _number(value: Any, row_index: int, field: str) -> float:
    try:
        return _plain_number(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fund-flow CSV row {row_index} has invalid {field}") from exc


def _plain_number(value: Any) -> float:
    return float(str(value or "0").replace(",", "").strip())


def _required_payload_date(
    payload: dict[str, Any],
    requested_date: date,
    source: str,
) -> date:
    value = payload.get("date")
    if not isinstance(value, str):
        raise ValueError(f"{source} returned a missing or invalid payload date")
    try:
        if re.fullmatch(r"\d{8}", value):
            payload_date = datetime.strptime(value, "%Y%m%d").date()
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            payload_date = date.fromisoformat(value)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"{source} returned a missing or invalid payload date") from exc
    if payload_date != requested_date:
        raise ValueError(
            f"{source} payload date {payload_date.isoformat()} does not match requested date "
            f"{requested_date.isoformat()}"
        )
    return payload_date


def _required_flow_number(
    value: Any,
    source: str,
    row_index: int,
    field: str,
) -> float:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text:
        raise ValueError(f"{source} row {row_index} is missing {field}")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{source} row {row_index} has invalid {field}") from exc
    if not isfinite(number):
        raise ValueError(f"{source} row {row_index} has invalid {field}")
    return number


def _split_terms(value: str) -> list[str]:
    return [term.strip() for term in re.split(r"[|,;，；]", value) if term.strip()]


def _term_in_text(term: str, casefolded_text: str) -> bool:
    normalized = term.strip().casefold()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9+.-]+", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", casefolded_text) is not None
    return normalized in casefolded_text


def _xml_text(node: ElementTree.Element, paths: list[str]) -> str:
    for path in paths:
        child = node.find(path)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _integer_text(value: Any) -> str:
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "-"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
