from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from taiwan_stock_analysis.reliability import build_retry_hint


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
    "price_status",
    "price_status_message",
    "price_retry_hint",
    "warning",
]

TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_DAILY_CLOSE_URL = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"

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


def parse_tpex_daily_close(
    stock_id: str,
    payload: dict[str, object],
    *,
    price_date: str = "",
) -> PriceRow:
    rows = payload.get("aaData", [])
    if not isinstance(rows, list):
        return _empty_price_with_source(stock_id, "TPEX_DAILY_CLOSE", "invalid TPEx payload")

    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            continue
        if str(row[0]).strip() != stock_id:
            continue
        close = _parse_float(row[2])
        if close is None:
            return _empty_price_with_source(stock_id, "TPEX_DAILY_CLOSE", "no TPEx close price")
        return {
            "stock_id": stock_id,
            "price": close,
            "price_date": str(payload.get("date") or price_date),
            "price_source": "TPEX_DAILY_CLOSE",
            "warning": "",
        }
    return _empty_price_with_source(stock_id, "TPEX_DAILY_CLOSE", "no TPEx close price")


def fetch_tpex_latest_close(
    stock_id: str,
    *,
    date: str | None = None,
    fetch: FetchBytes | None = None,
) -> PriceRow:
    query = urlencode(
        {
            "l": "zh-tw",
            "o": "json",
            "d": _tpex_date(date),
        }
    )
    fetch_bytes = fetch or _fetch_url
    try:
        payload = json.loads(fetch_bytes(f"{TPEX_DAILY_CLOSE_URL}?{query}").decode("utf-8-sig"))
    except Exception as exc:
        return _empty_price_with_source(stock_id, "TPEX_DAILY_CLOSE", f"TPEx fetch failed: {exc}")
    if not isinstance(payload, dict):
        return _empty_price_with_source(stock_id, "TPEX_DAILY_CLOSE", "invalid TPEx payload")
    return parse_tpex_daily_close(stock_id, payload, price_date=_tpex_date(date))


def fetch_latest_close(
    stock_id: str,
    *,
    date: str | None = None,
    fetch: FetchBytes | None = None,
) -> PriceRow:
    twse_price = fetch_twse_latest_close(stock_id, date=date, fetch=fetch)
    if twse_price.get("price") is not None:
        return twse_price

    tpex_price = fetch_tpex_latest_close(stock_id, date=date, fetch=fetch)
    if tpex_price.get("price") is not None:
        return tpex_price

    return _empty_price_with_source(
        stock_id,
        "TWSE_STOCK_DAY,TPEX_DAILY_CLOSE",
        _merge_warnings(twse_price.get("warning"), tpex_price.get("warning")),
    )


def write_valuation_template(
    stock_ids: list[str],
    output_path: Path,
    *,
    analysis_dir: Path | None = None,
    fetch_price: FetchPrice | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    price_fetcher = fetch_price or fetch_latest_close
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRICE_TEMPLATE_FIELDS)
        writer.writeheader()
        for stock_id in stock_ids:
            price_row = price_fetcher(stock_id)
            enrichment = load_analysis_enrichment(stock_id, analysis_dir) if analysis_dir is not None else {}
            price_reliability = _price_reliability(price_row)
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
                    "price_status": price_reliability["status"],
                    "price_status_message": price_reliability["message"],
                    "price_retry_hint": price_reliability["retry_hint"],
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
    return _empty_price_with_source(stock_id, "TWSE_STOCK_DAY", warning)


def _empty_price_with_source(stock_id: str, source: str, warning: str) -> PriceRow:
    return {
        "stock_id": stock_id,
        "price": None,
        "price_date": "",
        "price_source": source,
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


def _tpex_date(raw_date: str | None) -> str:
    value = raw_date or _today_yyyymmdd()
    if len(value) == 8 and value.isdigit():
        return f"{int(value[:4]) - 1911}/{value[4:6]}/{value[6:8]}"
    return value


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


def _price_reliability(price_row: PriceRow) -> dict[str, str]:
    warning = str(price_row.get("warning") or "").strip()
    if price_row.get("price") is None:
        return {
            "status": "warning",
            "message": "No market price was available from configured sources.",
            "retry_hint": build_retry_hint("price"),
        }

    if warning:
        return {
            "status": "warning",
            "message": f"Market price was loaded with warning: {warning}",
            "retry_hint": build_retry_hint("price"),
        }

    if price_row.get("price_source") == "TPEX_DAILY_CLOSE":
        return {
            "status": "warning",
            "message": "TWSE price was unavailable; loaded latest close price from TPEx fallback.",
            "retry_hint": build_retry_hint("price"),
        }

    return {
        "status": "ok",
        "message": "Latest close price loaded from TWSE.",
        "retry_hint": "",
    }


def _csv_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
