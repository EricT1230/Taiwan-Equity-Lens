from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

from taiwan_stock_analysis.market_intelligence import (
    _http_json,
    fetch_fund_flow_history,
)
from taiwan_stock_analysis.research import RESEARCH_COLUMNS, load_research_rows
from taiwan_stock_analysis.traceability import build_artifact_registry, build_run_metadata, merge_traceability


TWSE_PROFILE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_INDUSTRY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
TWSE_PRICE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_PROFILE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_INDUSTRY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
TPEX_PRICE_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
MIN_TREND_POINTS = 21


def fetch_official_profiles() -> tuple[list[dict[str, Any]], list[str]]:
    payloads: dict[str, list[dict[str, Any]]] = {}
    errors: list[str] = []
    for name, url in (
        ("twse_profiles", TWSE_PROFILE_URL),
        ("twse_industries", TWSE_INDUSTRY_URL),
        ("tpex_profiles", TPEX_PROFILE_URL),
        ("tpex_industries", TPEX_INDUSTRY_URL),
    ):
        try:
            payload = _http_json(url)
            if not isinstance(payload, list):
                raise ValueError("unexpected payload")
            payloads[name] = [row for row in payload if isinstance(row, dict)]
        except (OSError, ValueError) as exc:
            payloads[name] = []
            errors.append(f"{name}: {exc}")
    profiles = build_official_profiles(
        payloads["twse_profiles"],
        payloads["twse_industries"],
        payloads["tpex_profiles"],
        payloads["tpex_industries"],
    )
    return profiles, errors


def build_official_profiles(
    twse_profile_rows: Iterable[dict[str, Any]],
    twse_industry_rows: Iterable[dict[str, Any]],
    tpex_profile_rows: Iterable[dict[str, Any]],
    tpex_industry_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    twse_profiles = list(twse_profile_rows)
    tpex_profiles = list(tpex_profile_rows)
    direct_names = {
        "TWSE": {
            str(row.get("公司代號") or "").strip(): str(row.get("產業別") or "").strip()
            for row in twse_industry_rows
            if str(row.get("公司代號") or "").strip()
        },
        "TPEX": {
            str(row.get("SecuritiesCompanyCode") or "").strip(): str(row.get("產業別") or "").strip()
            for row in tpex_industry_rows
            if str(row.get("SecuritiesCompanyCode") or "").strip()
        },
    }
    normalized: list[dict[str, Any]] = []
    for market, rows in (("TWSE", twse_profiles), ("TPEX", tpex_profiles)):
        for row in rows:
            if market == "TWSE":
                stock_id = str(row.get("公司代號") or "").strip()
                company_name = str(row.get("公司名稱") or "").strip()
                abbreviation = str(row.get("公司簡稱") or "").strip()
                industry_code = str(row.get("產業別") or "").strip()
                snapshot = _roc_date(row.get("出表日期"))
            else:
                stock_id = str(row.get("SecuritiesCompanyCode") or "").strip()
                company_name = str(row.get("CompanyName") or "").strip()
                abbreviation = str(row.get("CompanyAbbreviation") or "").strip()
                industry_code = str(row.get("SecuritiesIndustryCode") or "").strip()
                snapshot = _roc_date(row.get("Date"))
            if not stock_id:
                continue
            normalized.append(
                {
                    "stock_id": stock_id,
                    "company_name": company_name,
                    "company_abbreviation": abbreviation,
                    "market": market,
                    "industry_code": industry_code,
                    "industry_name": direct_names[market].get(stock_id, ""),
                    "snapshot_date": snapshot.isoformat() if snapshot else "",
                    "source": "TWSE OpenAPI" if market == "TWSE" else "TPEx OpenAPI",
                }
            )
    _fill_industry_names_by_code(normalized)
    return sorted(normalized, key=lambda row: (str(row["stock_id"]), str(row["market"])))


def fetch_price_history(
    stock_id: str,
    market: str,
    *,
    as_of: date | str | None = None,
    history_months: int = 3,
) -> list[dict[str, Any]]:
    target = _as_of_date(as_of)
    rows: list[dict[str, Any]] = []
    for month_start in _month_starts(target, max(1, history_months)):
        if market == "TWSE":
            query = urlencode(
                {
                    "date": month_start.strftime("%Y%m%d"),
                    "stockNo": stock_id,
                    "response": "json",
                }
            )
            payload = _http_json(f"{TWSE_PRICE_URL}?{query}")
            rows.extend(parse_twse_price_payload(payload, stock_id))
        elif market == "TPEX":
            query = urlencode(
                {
                    "code": stock_id,
                    "date": month_start.strftime("%Y/%m/%d"),
                    "id": "",
                    "response": "json",
                }
            )
            payload = _http_json(f"{TPEX_PRICE_URL}?{query}")
            rows.extend(parse_tpex_price_payload(payload, stock_id))
        else:
            raise ValueError(f"unsupported official market for {stock_id}: {market}")
    deduped = {str(row["date"]): row for row in rows if _as_of_date(str(row["date"])) <= target}
    return [deduped[key] for key in sorted(deduped)]


def parse_twse_price_payload(payload: Any, stock_id: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return []
    fields = [_compact_field(value) for value in payload.get("fields", [])]
    date_index = _field_index(fields, "日期")
    volume_index = _field_index(fields, "成交股數")
    close_index = _field_index(fields, "收盤價")
    rows = []
    for row_index, values in enumerate(payload.get("data", []), start=1):
        if not isinstance(values, list):
            continue
        trade_date = _roc_date(values[date_index])
        close = _payload_optional_number(values[close_index], row_index, "close")
        volume = _payload_optional_number(values[volume_index], row_index, "volume")
        if trade_date is None or close is None or close <= 0:
            continue
        rows.append(
            {
                "stock_id": stock_id,
                "date": trade_date.isoformat(),
                "close": close,
                "volume": volume,
                "source": "TWSE STOCK_DAY",
            }
        )
    return rows


def parse_tpex_price_payload(payload: Any, stock_id: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    tables = payload.get("tables", [])
    table = next((item for item in tables if isinstance(item, dict) and item.get("data")), None)
    if table is None:
        return []
    fields = [_compact_field(value) for value in table.get("fields", [])]
    date_index = _field_index(fields, "日期")
    volume_index = _field_index(fields, "成交張數")
    close_index = _field_index(fields, "收盤")
    rows = []
    for row_index, values in enumerate(table.get("data", []), start=1):
        if not isinstance(values, list):
            continue
        trade_date = _roc_date(values[date_index])
        close = _payload_optional_number(values[close_index], row_index, "close")
        lots = _payload_optional_number(values[volume_index], row_index, "volume")
        if trade_date is None or close is None or close <= 0:
            continue
        volume = lots * 1000 if lots is not None else None
        if volume is not None and not math.isfinite(volume):
            raise ValueError(
                f"official price payload row {row_index} has invalid volume: non-finite number"
            )
        rows.append(
            {
                "stock_id": stock_id,
                "date": trade_date.isoformat(),
                "close": close,
                "volume": volume,
                "source": "TPEx tradingStock",
            }
        )
    return rows


def _attach_traded_shares(
    flow_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    volumes = {
        (str(row.get("date") or ""), str(row.get("stock_id") or "")): _optional_number(
            row.get("volume")
        )
        for row in price_rows
    }
    joined = []
    for row in flow_rows:
        item = dict(row)
        item["traded_shares"] = volumes.get(
            (str(row.get("date") or ""), str(row.get("stock_id") or ""))
        )
        joined.append(item)
    return joined


def write_market_data_bundle(
    research_path: Path,
    output_dir: Path,
    *,
    as_of: date | str | None = None,
    history_months: int = 3,
    replace_category: bool = False,
) -> dict[str, Path]:
    target = _as_of_date(as_of)
    profiles, source_errors = fetch_official_profiles()
    research_rows = load_research_rows(research_path)
    research_stock_ids = {row["stock_id"] for row in research_rows}
    profiles_by_stock = {str(row["stock_id"]): row for row in profiles}

    price_rows: list[dict[str, Any]] = []
    for stock_id in sorted(research_stock_ids):
        profile = profiles_by_stock.get(stock_id)
        if profile is None:
            continue
        try:
            price_rows.extend(
                fetch_price_history(
                    stock_id,
                    str(profile.get("market") or ""),
                    as_of=target,
                    history_months=history_months,
                )
            )
        except (OSError, ValueError) as exc:
            source_errors.append(f"price history {stock_id}: {exc}")

    fund_flow_rows, fund_flow_errors = fetch_fund_flow_history(as_of=target)
    source_errors.extend(fund_flow_errors)
    fund_flow_rows = [
        row
        for row in fund_flow_rows
        if str(row.get("stock_id") or "") in research_stock_ids
        and _row_date_not_after(row, target)
    ]
    fund_flow_rows = _attach_traded_shares(fund_flow_rows, price_rows)

    universe_path = output_dir / "official_universe.csv"
    research_output_path = output_dir / "research_official.csv"
    price_path = output_dir / "industry_price_history.csv"
    fund_flow_path = output_dir / "fund_flow.csv"
    report_path = output_dir / "market_data_report.json"
    markdown_path = output_dir / "market_data_report.md"
    report = build_market_data_report(
        research_rows,
        profiles,
        price_rows,
        fund_flow_rows,
        as_of=target,
        history_months=history_months,
        source_errors=source_errors,
    )
    report = merge_traceability(
        report,
        run_metadata=build_run_metadata(
            "market-data",
            "research market-data",
            {"research_csv": str(research_path), "as_of": target.isoformat()},
            str(output_dir),
        ),
        artifact_registry=build_artifact_registry(
            str(report_path),
            dependencies={"research_csv": str(research_path)},
            outputs={
                "official_universe": str(universe_path),
                "research_official": str(research_output_path),
                "price_history": str(price_path),
                "fund_flow": str(fund_flow_path),
                "markdown": str(markdown_path),
            },
        ),
    )
    report_text = _json_report_text(report, "market data report")
    markdown_text = render_market_data_markdown(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_universe_csv(universe_path, profiles, research_stock_ids)
    write_research_with_official_profiles(
        research_path,
        research_output_path,
        profiles,
        replace_category=replace_category,
    )
    _write_price_csv(price_path, price_rows)
    _write_fund_flow_csv(fund_flow_path, fund_flow_rows)
    report_path.write_text(report_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    return {
        "report": report_path,
        "markdown": markdown_path,
        "official_universe": universe_path,
        "research_csv": research_output_path,
        "price_history": price_path,
        "fund_flow": fund_flow_path,
    }


def write_research_with_official_profiles(
    research_path: Path,
    output_path: Path,
    profiles: Iterable[dict[str, Any]],
    *,
    replace_category: bool = False,
) -> Path:
    profiles_by_stock = {str(row.get("stock_id") or ""): row for row in profiles}
    with research_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        original_fields = reader.fieldnames or []
        rows = list(reader)
    fieldnames = list(dict.fromkeys([*original_fields, *RESEARCH_COLUMNS]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            stock_id = str(row.get("stock_id") or "").strip()
            profile = profiles_by_stock.get(stock_id, {})
            official_name = str(profile.get("industry_name") or "")
            enriched = dict(row)
            enriched["official_market"] = str(profile.get("market") or "")
            enriched["official_industry_code"] = str(profile.get("industry_code") or "")
            enriched["official_industry_name"] = official_name
            current_category = str(row.get("category") or "").strip()
            if official_name and (replace_category or current_category in {"", "Uncategorized"}):
                enriched["category"] = official_name
            writer.writerow(enriched)
    return output_path


def build_market_data_report(
    research_rows: list[dict[str, str]],
    profiles: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    fund_flow_rows: list[dict[str, Any]],
    *,
    as_of: date,
    history_months: int,
    source_errors: list[str],
) -> dict[str, Any]:
    profiles_by_stock = {str(row["stock_id"]): row for row in profiles}
    prices_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in price_rows:
        prices_by_stock[str(row.get("stock_id") or "")].append(row)
    flow_stocks = {str(row.get("stock_id") or "") for row in fund_flow_rows}
    items = []
    blockers = [f"source error: {error}" for error in source_errors]
    for research in research_rows:
        stock_id = research["stock_id"]
        profile = profiles_by_stock.get(stock_id, {})
        prices = sorted(prices_by_stock.get(stock_id, []), key=lambda row: str(row.get("date") or ""))
        if not profile:
            blockers.append(f"{stock_id}: missing official market profile")
        elif not profile.get("industry_name"):
            blockers.append(f"{stock_id}: missing official industry name")
        if len(prices) < MIN_TREND_POINTS:
            blockers.append(f"{stock_id}: only {len(prices)} price points; need {MIN_TREND_POINTS}")
        items.append(
            {
                "stock_id": stock_id,
                "company_name": research.get("company_name", ""),
                "market": str(profile.get("market") or ""),
                "industry_code": str(profile.get("industry_code") or ""),
                "industry_name": str(profile.get("industry_name") or ""),
                "profile_snapshot_date": str(profile.get("snapshot_date") or ""),
                "price_points": len(prices),
                "price_start_date": str(prices[0].get("date") or "") if prices else "",
                "price_latest_date": str(prices[-1].get("date") or "") if prices else "",
                "fund_flow_available": stock_id in flow_stocks,
            }
        )
    status = "ready" if not blockers else "needs_data"
    report = {
        "schema_version": 1,
        "kind": "market_data_report",
        "as_of_date": as_of.isoformat(),
        "history_months": history_months,
        "coverage": {
            "stocks_total": len(research_rows),
            "official_profile_count": sum(1 for item in items if item["market"]),
            "official_industry_count": sum(1 for item in items if item["industry_name"]),
            "price_ready_count": sum(1 for item in items if int(item["price_points"]) >= MIN_TREND_POINTS),
            "fund_flow_count": sum(1 for item in items if item["fund_flow_available"]),
            "fund_flow_session_count": len(
                {str(row.get("date") or "") for row in fund_flow_rows}
            ),
            "fund_flow_volume_join_count": sum(
                _optional_number(row.get("traded_shares")) is not None
                for row in fund_flow_rows
            ),
            "fund_flow_row_count": len(fund_flow_rows),
            "twse_count": sum(1 for item in items if item["market"] == "TWSE"),
            "tpex_count": sum(1 for item in items if item["market"] == "TPEX"),
        },
        "quality_gate": {
            "status": status,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "next_action": (
                "Generate industry trends and market intelligence from the refreshed official bundle."
                if status == "ready"
                else "Review source errors and missing profile or price-history coverage, then rerun market-data."
            ),
        },
        "source_errors": source_errors,
        "items": items,
        "sources": {
            "twse_profiles": TWSE_PROFILE_URL,
            "twse_industries": TWSE_INDUSTRY_URL,
            "twse_prices": TWSE_PRICE_URL,
            "tpex_profiles": TPEX_PROFILE_URL,
            "tpex_industries": TPEX_INDUSTRY_URL,
            "tpex_prices": TPEX_PRICE_URL,
        },
    }
    _require_finite_values(report, "market data report")
    return report


def render_market_data_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("coverage", {}) if isinstance(report.get("coverage"), dict) else {}
    gate = report.get("quality_gate", {}) if isinstance(report.get("quality_gate"), dict) else {}
    lines = [
        "# Official Market Data Import Report",
        "",
        f"- as_of_date: {report.get('as_of_date') or '-'}",
        f"- quality_gate: {gate.get('status') or '-'}",
        f"- official profiles: {coverage.get('official_profile_count', 0)} / {coverage.get('stocks_total', 0)}",
        f"- price ready: {coverage.get('price_ready_count', 0)} / {coverage.get('stocks_total', 0)}",
        f"- fund flow: {coverage.get('fund_flow_count', 0)} / {coverage.get('stocks_total', 0)}",
        "",
        "| Stock | Market | Official industry | Price points | Latest price date | Fund flow |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("stock_id") or "-"),
                    str(item.get("market") or "-"),
                    str(item.get("industry_name") or "-"),
                    str(item.get("price_points") or 0),
                    str(item.get("price_latest_date") or "-"),
                    "yes" if item.get("fund_flow_available") else "no",
                ]
            )
            + " |"
        )
    blockers = gate.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        lines.extend(["", "## Data Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
    return "\n".join(lines) + "\n"


def _fill_industry_names_by_code(profiles: list[dict[str, Any]]) -> None:
    names_by_market_code: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for profile in profiles:
        name = str(profile.get("industry_name") or "")
        code = str(profile.get("industry_code") or "")
        market = str(profile.get("market") or "")
        if name and code:
            names_by_market_code[(market, code)][name] += 1
    for profile in profiles:
        if profile.get("industry_name"):
            continue
        counter = names_by_market_code.get(
            (str(profile.get("market") or ""), str(profile.get("industry_code") or ""))
        )
        if counter:
            profile["industry_name"] = counter.most_common(1)[0][0]


def _write_universe_csv(path: Path, profiles: list[dict[str, Any]], stock_ids: set[str]) -> None:
    fields = [
        "stock_id",
        "company_name",
        "company_abbreviation",
        "market",
        "industry_code",
        "industry_name",
        "snapshot_date",
        "source",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(row for row in profiles if str(row.get("stock_id") or "") in stock_ids)


def _write_price_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["stock_id", "date", "close", "volume", "source"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (str(row["stock_id"]), str(row["date"]))))


def _write_fund_flow_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "date",
        "stock_id",
        "company_name",
        "foreign_net",
        "investment_trust_net",
        "dealer_net",
        "total_net",
        "traded_shares",
        "source",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            sorted(
                rows,
                key=lambda row: (
                    str(row.get("date") or ""),
                    str(row.get("stock_id") or ""),
                    str(row.get("source") or ""),
                ),
            )
        )


def _field_index(fields: list[str], name: str) -> int:
    try:
        return fields.index(name)
    except ValueError as exc:
        raise ValueError(f"official price payload is missing field: {name}") from exc


def _compact_field(value: Any) -> str:
    return "".join(str(value or "").split())


def _optional_number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if text in {"", "--", "---", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _payload_optional_number(value: Any, row_index: int, field: str) -> float | None:
    number = _optional_number(value)
    if number is not None:
        return number
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"--", "---", "-"}:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        raise ValueError(
            f"official price payload row {row_index} has invalid {field}: non-finite number"
        )
    return None


def _json_report_text(report: dict[str, Any], label: str) -> str:
    try:
        return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cannot publish {label}: non-finite or non-JSON value") from exc


def _require_finite_values(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for field, item in value.items():
            _require_finite_values(item, f"{label}.{field}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_finite_values(item, f"{label}[{index}]")


def _roc_date(value: Any) -> date | None:
    text = str(value or "").strip()
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) != 7:
        return None
    try:
        return date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return None


def _as_of_date(value: date | str | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as exc:
            raise ValueError(f"invalid as_of date: {value}") from exc
    return datetime.now().date()


def _month_starts(target: date, count: int) -> list[date]:
    months = []
    year = target.year
    month = target.month
    for _ in range(count):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


def _row_date_not_after(row: dict[str, Any], target: date) -> bool:
    try:
        return date.fromisoformat(str(row.get("date") or "")) <= target
    except ValueError:
        return False
