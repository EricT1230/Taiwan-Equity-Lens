from __future__ import annotations

import csv
from pathlib import Path


def load_watchlist(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "stock_id" not in reader.fieldnames:
            raise ValueError("watchlist CSV must include a stock_id column")

        rows: list[dict[str, str]] = []
        for row in reader:
            stock_id = (row.get("stock_id") or "").strip()
            if not stock_id:
                continue
            rows.append(
                {
                    "stock_id": stock_id,
                    "company_name": (row.get("company_name") or "").strip(),
                }
            )
        return rows
