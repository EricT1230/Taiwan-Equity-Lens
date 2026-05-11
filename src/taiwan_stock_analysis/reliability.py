from __future__ import annotations

from dataclasses import dataclass


VALID_STATUSES = {"ok", "warning", "error", "skipped"}


@dataclass(slots=True)
class ReliabilityStatus:
    stage: str
    status: str
    message: str
    source: str = ""
    date: str = ""
    retry_hint: str = ""
    stock_id: str = ""

    def normalized_status(self) -> str:
        return self.status if self.status in VALID_STATUSES else "warning"

    def to_dict(self) -> dict[str, str]:
        payload = {
            "stage": self.stage,
            "status": self.normalized_status(),
            "source": self.source,
            "date": self.date,
            "message": self.message,
            "retry_hint": self.retry_hint,
            "stock_id": self.stock_id,
        }
        return {key: value for key, value in payload.items() if value != ""}


def build_retry_hint(stage: str) -> str:
    hints = {
        "fetch": "Run the workflow again later or use fixture data if the source is unavailable.",
        "parse": "Check whether the source layout changed or run with fixture data.",
        "price": "Run again after the next market data update or provide a valuation CSV manually.",
        "valuation": "Provide price and assumption fields in the valuation CSV.",
        "report": "Check the raw JSON output and rerun the stock report command.",
        "comparison": "Comparison needs at least two successful stock reports.",
        "dashboard": "Open the generated output directory and rerun the workflow if files are missing.",
    }
    return hints.get(stage, "Review the workflow summary and rerun the failed step.")


def summarize_reliability(statuses: list[ReliabilityStatus]) -> dict[str, int | str]:
    counts = {"ok": 0, "warning": 0, "error": 0, "skipped": 0}
    for status in statuses:
        counts[status.normalized_status()] += 1

    overall_status = "ok"
    if counts["error"]:
        overall_status = "error"
    elif counts["warning"]:
        overall_status = "warning"
    elif counts["skipped"]:
        overall_status = "skipped"

    return {**counts, "overall_status": overall_status}
