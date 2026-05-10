from __future__ import annotations

import csv
from pathlib import Path


NUMERIC_FIELDS = {
    "price",
    "book_value_per_share",
    "cash_dividend_per_share",
    "normalized_eps",
    "target_pe_low",
    "target_pe_base",
    "target_pe_high",
    "eps_growth_rate",
}


def _parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return float(value)


def load_price_data(path: Path) -> dict[str, dict[str, float | None]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "stock_id" not in reader.fieldnames:
            raise ValueError("valuation CSV must include a stock_id column")

        data: dict[str, dict[str, float | None]] = {}
        for row in reader:
            stock_id = (row.get("stock_id") or "").strip()
            if not stock_id:
                continue
            data[stock_id] = {
                field: _parse_float(row.get(field))
                for field in NUMERIC_FIELDS
                if field in row
            }
        return data
