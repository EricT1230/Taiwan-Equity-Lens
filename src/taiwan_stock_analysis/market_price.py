from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PRICE_TEMPLATE_FIELDS = [
    "stock_id",
    "price",
    "book_value_per_share",
    "cash_dividend_per_share",
    "normalized_eps",
    "target_pe_low",
    "target_pe_base",
    "target_pe_high",
    "eps_growth_rate",
    "price_date",
    "price_source",
    "warning",
]

TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"

PriceRow = dict[str, str | float | None]
FetchBytes = Callable[[str], bytes]
FetchPrice = Callable[[str], PriceRow]


def parse_twse_stock_day(stock_id: str, payload: dict[str, object]) -> PriceRow:
    fields = payload.get("fields", [])
    data = payload.get("data", [])
    if not isinstance(fields, list) or not isinstance(data, list):
        return _empty_price(stock_id, "invalid TWSE payload")

    close_index = _field_index(fields, "收盤價")
    date_index = _field_index(fields, "日期")
    if close_index is None or date_index is None:
        return _empty_price(stock_id, "TWSE payload missing close price field")

    for row in reversed(data):
        if not isinstance(row, list):
            continue
        if len(row) <= max(close_index, date_index):
            continue
        close = _parse_float(row[close_index])
        if close is None:
            continue
        return {
            "stock_id": stock_id,
            "price": close,
            "price_date": str(row[date_index]),
            "price_source": "TWSE_STOCK_DAY",
            "warning": "",
        }
    return _empty_price(stock_id, "no TWSE close price")


def fetch_twse_latest_close(
    stock_id: str,
    *,
    date: str | None = None,
    fetch: FetchBytes | None = None,
) -> PriceRow:
    query = urlencode(
        {
            "date": date or _today_yyyymmdd(),
            "stockNo": stock_id,
            "response": "json",
        }
    )
    fetch_bytes = fetch or _fetch_url
    try:
        payload = json.loads(fetch_bytes(f"{TWSE_STOCK_DAY_URL}?{query}").decode("utf-8-sig"))
    except Exception as exc:
        return _empty_price(stock_id, f"TWSE fetch failed: {exc}")
    if not isinstance(payload, dict):
        return _empty_price(stock_id, "invalid TWSE payload")
    return parse_twse_stock_day(stock_id, payload)


def write_valuation_template(
    stock_ids: list[str],
    output_path: Path,
    *,
    analysis_dir: Path | None = None,
    fetch_price: FetchPrice | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    price_fetcher = fetch_price or fetch_twse_latest_close
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_TEMPLATE_FIELDS)
        writer.writeheader()
        for stock_id in stock_ids:
            price_row = price_fetcher(stock_id)
            enrichment = load_analysis_enrichment(stock_id, analysis_dir) if analysis_dir is not None else {}
            row = {field: "" for field in PRICE_TEMPLATE_FIELDS}
            row.update(
                {
                    "stock_id": stock_id,
                    "price": _csv_value(price_row.get("price")),
                    "normalized_eps": _csv_value(enrichment.get("normalized_eps")),
                    "target_pe_low": _csv_value(enrichment.get("target_pe_low")),
                    "target_pe_base": _csv_value(enrichment.get("target_pe_base")),
                    "target_pe_high": _csv_value(enrichment.get("target_pe_high")),
                    "price_date": _csv_value(price_row.get("price_date")),
                    "price_source": _csv_value(price_row.get("price_source")),
                    "warning": _merge_warnings(price_row.get("warning"), enrichment.get("warning")),
                }
            )
            writer.writerow(row)
    return output_path


def load_analysis_enrichment(stock_id: str, analysis_dir: Path) -> dict[str, float | str | None]:
    path = analysis_dir / f"{stock_id}_raw_data.json"
    if not path.exists():
        return _default_enrichment(f"analysis JSON not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _default_enrichment(f"analysis JSON invalid: {exc}")
    if not isinstance(payload, dict):
        return _default_enrichment("analysis JSON invalid")

    normalized_eps = _normalized_eps_from_analysis(payload)
    result = _default_enrichment("")
    result["normalized_eps"] = normalized_eps
    if normalized_eps is None:
        result["warning"] = "analysis JSON missing EPS"
    return result


def offline_price(stock_id: str) -> PriceRow:
    return _empty_price(stock_id, "offline mode")


def _empty_price(stock_id: str, warning: str) -> PriceRow:
    return {
        "stock_id": stock_id,
        "price": None,
        "price_date": "",
        "price_source": "TWSE_STOCK_DAY",
        "warning": warning,
    }


def _field_index(fields: list[object], name: str) -> int | None:
    for index, field in enumerate(fields):
        if str(field) == name:
            return index
    return None


def _parse_float(raw: object) -> float | None:
    if raw is None:
        return None
    value = str(raw).replace(",", "").strip()
    if not value or value in {"--", "-"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fetch_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "taiwan-equity-lens/0.1"})
    with urlopen(request, timeout=15) as response:
        return response.read()


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def _default_enrichment(warning: str) -> dict[str, float | str | None]:
    return {
        "normalized_eps": None,
        "target_pe_low": 10.0,
        "target_pe_base": 15.0,
        "target_pe_high": 20.0,
        "warning": warning,
    }


def _normalized_eps_from_analysis(payload: dict[str, object]) -> float | None:
    valuation = payload.get("valuation", {})
    if isinstance(valuation, dict):
        eps_scenarios = valuation.get("eps_scenarios", {})
        if isinstance(eps_scenarios, dict):
            scenario_eps = _parse_float(eps_scenarios.get("base"))
            if scenario_eps is not None:
                return scenario_eps

    years = payload.get("years", [])
    metrics_by_year = payload.get("metrics_by_year", {})
    if not isinstance(years, list) or not years or not isinstance(metrics_by_year, dict):
        return None
    latest_year = str(years[0])
    latest_metrics = metrics_by_year.get(latest_year, {})
    if not isinstance(latest_metrics, dict):
        return None
    return _parse_float(latest_metrics.get("eps"))


def _merge_warnings(*warnings: object) -> str:
    parts = [str(warning).strip() for warning in warnings if str(warning or "").strip()]
    return "; ".join(parts)


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
