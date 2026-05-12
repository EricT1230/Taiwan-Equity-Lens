from __future__ import annotations

import csv
from pathlib import Path


RESEARCH_COLUMNS = ["stock_id", "company_name", "category", "priority", "research_state", "notes"]
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_STATES = {"new", "watching", "review", "done", "blocked"}


def load_research_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "stock_id" not in fieldnames:
            raise ValueError("research CSV must include a stock_id column")

        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=2):
            stock_id = (row.get("stock_id") or "").strip()
            if not stock_id:
                raise ValueError(f"research CSV row {index} must include a stock_id")

            priority = _normalized_choice(row, "priority", "medium")
            if priority not in ALLOWED_PRIORITIES:
                allowed = ", ".join(sorted(ALLOWED_PRIORITIES))
                raise ValueError(
                    f"research CSV row {index} has invalid priority '{priority}'. Allowed: {allowed}"
                )

            research_state = _normalized_choice(row, "research_state", "new")
            if research_state not in ALLOWED_STATES:
                allowed = ", ".join(sorted(ALLOWED_STATES))
                raise ValueError(
                    f"research CSV row {index} has invalid research_state '{research_state}'. Allowed: {allowed}"
                )

            rows.append(
                {
                    "stock_id": stock_id,
                    "company_name": (row.get("company_name") or "").strip(),
                    "category": (row.get("category") or "").strip(),
                    "priority": priority,
                    "research_state": research_state,
                    "notes": (row.get("notes") or "").strip(),
                }
            )
        return rows


def write_research_template(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "stock_id": "2330",
                "company_name": "TSMC",
                "category": "Semiconductor",
                "priority": "high",
                "research_state": "review",
                "notes": "Add valuation assumptions before final review",
            }
        )
        writer.writerow(
            {
                "stock_id": "2303",
                "company_name": "UMC",
                "category": "Semiconductor",
                "priority": "medium",
                "research_state": "watching",
                "notes": "Track workflow warnings",
            }
        )
    return path


def write_watchlist_from_research(research_path: Path, output_path: Path) -> Path:
    rows = load_research_rows(research_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["stock_id", "company_name"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"stock_id": row["stock_id"], "company_name": row["company_name"]})
    return output_path


def _normalized_choice(row: dict[str, str], field: str, default: str) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        return default
    return value.lower()
