from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FRESHNESS_STATUSES = ("fresh", "stale", "unknown", "manual_review")
STATUS_PRIORITY = {"stale": 0, "unknown": 1, "manual_review": 2, "fresh": 3}
FINANCIAL_STATEMENT_STALE_DAYS = 120
PRICE_STALE_DAYS = 7
WORKFLOW_STALE_DAYS = 30


def classify_freshness(
    *,
    generated_at: str,
    now: str | None = None,
    source_mode: str = "unknown",
    stale_after_days: int = WORKFLOW_STALE_DAYS,
    review_reason: str = "",
) -> dict[str, Any]:
    timestamp = _parse_timestamp(generated_at)
    current = _parse_timestamp(now) if now else datetime.now(timezone.utc)
    age_days = None
    status = "unknown"
    reason = review_reason

    if timestamp is not None and current is not None:
        age_days = max((current - timestamp).days, 0)
        status = "stale" if age_days > stale_after_days else "fresh"
    else:
        reason = reason or "generated timestamp is missing or invalid"

    mode = (source_mode or "unknown").strip().lower()
    if mode in {"fixture", "offline"} and status != "stale":
        status = "manual_review"
        reason = reason or f"{mode} source requires manual review"

    return {
        "generated_at": generated_at or "",
        "source_mode": mode or "unknown",
        "age_days": age_days,
        "stale_after_days": stale_after_days,
        "status": status,
        "review_reason": reason,
    }


def summarize_source_audit(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in FRESHNESS_STATUSES}
    for item in items:
        status = str(item.get("status") or "unknown")
        if status not in counts:
            status = "unknown"
        counts[status] += 1

    overall = "fresh"
    for status in ("stale", "unknown", "manual_review", "fresh"):
        if counts[status]:
            overall = status
            break
    return {"status": overall, "counts": counts}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
