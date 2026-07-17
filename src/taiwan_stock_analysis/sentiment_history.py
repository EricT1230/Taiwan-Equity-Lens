"""Deterministic persistence for stable industry sentiment snapshots."""

import csv
from collections.abc import Iterable, Mapping
from datetime import date
import math
from pathlib import Path
from typing import Any


SENTIMENT_HISTORY_COLUMNS = [
    "as_of_date",
    "category",
    "methodology_version",
    "status",
    "score_5d",
    "baseline_20d",
    "change",
    "news_score_5d",
    "price_score_5d",
    "fund_flow_score_5d",
    "fund_flow_score_20d",
    "price_return_5d",
    "breadth_5d",
    "breadth_20d",
    "volume_ratio_5d",
    "flow_persistence_5d",
    "news_novelty_5d",
    "news_topic_concentration_5d",
    "news_positive_topic_concentration_5d",
    "news_negative_topic_concentration_5d",
    "rank",
    "ranked_count",
    "cycle_phase",
    "confidence",
]

_FLOAT_COLUMNS = {
    "score_5d",
    "baseline_20d",
    "change",
    "news_score_5d",
    "price_score_5d",
    "fund_flow_score_5d",
    "fund_flow_score_20d",
    "price_return_5d",
    "breadth_5d",
    "breadth_20d",
    "volume_ratio_5d",
    "flow_persistence_5d",
    "news_novelty_5d",
    "news_topic_concentration_5d",
    "news_positive_topic_concentration_5d",
    "news_negative_topic_concentration_5d",
}
_INTEGER_COLUMNS = {"rank", "ranked_count"}
_OPTIONAL_TEXT_COLUMNS = {"status", "cycle_phase", "confidence"}


def _row_error(path: Path, row_number: int, field: str, detail: str) -> ValueError:
    return ValueError(f"{path}: row {row_number}: invalid {field}: {detail}")


def _normalized_date(value: Any, *, path: Path, row_number: int) -> str:
    if not isinstance(value, str):
        raise _row_error(path, row_number, "as_of_date", "expected YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise _row_error(path, row_number, "as_of_date", "expected YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise _row_error(path, row_number, "as_of_date", "expected YYYY-MM-DD")
    return value


def _normalized_required_text(
    value: Any, *, path: Path, row_number: int, field: str
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _row_error(path, row_number, field, "must be a non-empty string")
    return value


def _normalized_optional_text(
    value: Any, *, path: Path, row_number: int, field: str
) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise _row_error(path, row_number, field, "expected a string or empty value")
    return value


def _normalized_float(value: Any, *, path: Path, row_number: int, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise _row_error(path, row_number, field, "expected a finite number or empty value")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise _row_error(path, row_number, field, "expected a finite number or empty value") from error
    if not math.isfinite(number):
        raise _row_error(path, row_number, field, "expected a finite number or empty value")
    return number


def _normalized_integer(value: Any, *, path: Path, row_number: int, field: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise _row_error(path, row_number, field, "expected an integer or empty value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as error:
            raise _row_error(path, row_number, field, "expected an integer or empty value") from error
    raise _row_error(path, row_number, field, "expected an integer or empty value")


def _normalize_history_row(
    row: Mapping[str, Any], *, path: Path, row_number: int
) -> dict[str, Any]:
    missing = [field for field in SENTIMENT_HISTORY_COLUMNS if field not in row]
    if missing:
        raise _row_error(path, row_number, missing[0], "missing required field")

    normalized: dict[str, Any] = {}
    for field in SENTIMENT_HISTORY_COLUMNS:
        value = row[field]
        if field == "as_of_date":
            normalized[field] = _normalized_date(value, path=path, row_number=row_number)
        elif field in {"category", "methodology_version"}:
            normalized[field] = _normalized_required_text(
                value, path=path, row_number=row_number, field=field
            )
        elif field in _OPTIONAL_TEXT_COLUMNS:
            normalized[field] = _normalized_optional_text(
                value, path=path, row_number=row_number, field=field
            )
        elif field in _FLOAT_COLUMNS:
            normalized[field] = _normalized_float(
                value, path=path, row_number=row_number, field=field
            )
        elif field in _INTEGER_COLUMNS:
            normalized[field] = _normalized_integer(
                value, path=path, row_number=row_number, field=field
            )
    return normalized


def _history_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["as_of_date"]),
        str(row["category"]),
        str(row["methodology_version"]),
    )


def _serialize_history_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in SENTIMENT_HISTORY_COLUMNS}


def load_sentiment_history(path: Path) -> list[dict[str, Any]]:
    """Load and validate the fixed-schema sentiment history CSV."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != SENTIMENT_HISTORY_COLUMNS:
            raise _row_error(path, 1, "header", "does not match sentiment history schema")
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise _row_error(path, row_number, "surplus cells", "not allowed")
            rows.append(_normalize_history_row(row, path=path, row_number=row_number))
        return rows


def history_for_category(
    rows: Iterable[dict[str, Any]],
    *,
    category: str,
    methodology_version: str,
    as_of_date: str,
) -> list[dict[str, Any]]:
    """Return only compatible observations that precede the current date."""
    cutoff = date.fromisoformat(as_of_date)
    selected = [
        dict(row)
        for row in rows
        if str(row.get("category") or "") == category
        and str(row.get("methodology_version") or "") == methodology_version
        and date.fromisoformat(str(row.get("as_of_date") or "")) < cutoff
    ]
    return sorted(
        selected,
        key=lambda row: (
            str(row["as_of_date"]),
            str(row["category"]),
            str(row["methodology_version"]),
        ),
    )


def _mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"industry {field} must be a mapping")
    return value


def sentiment_snapshot_from_industry(
    as_of_date: str, industry: Mapping[str, Any]
) -> dict[str, Any]:
    """Extract the approved analytical fields from an industry sentiment payload."""
    sentiment = _mapping(industry.get("sentiment"), field="sentiment")
    components = _mapping(sentiment.get("components"), field="sentiment.components")
    news = _mapping(components.get("news"), field="sentiment.components.news")
    price = _mapping(components.get("price"), field="sentiment.components.price")
    fund_flow = _mapping(
        components.get("fund_flow"), field="sentiment.components.fund_flow"
    )
    market_trend = _mapping(industry.get("market_trend"), field="market_trend")
    row = {
        "as_of_date": as_of_date,
        "category": industry.get("category"),
        "methodology_version": sentiment.get("methodology_version"),
        "status": sentiment.get("status"),
        "score_5d": sentiment.get("score_5d"),
        "baseline_20d": sentiment.get("baseline_20d"),
        "change": sentiment.get("change"),
        "news_score_5d": news.get("score_5d"),
        "price_score_5d": price.get("score_5d"),
        "fund_flow_score_5d": fund_flow.get("score_5d"),
        "fund_flow_score_20d": fund_flow.get("score_20d"),
        "price_return_5d": market_trend.get("average_return_5d"),
        "breadth_5d": market_trend.get("positive_breadth_5d"),
        "breadth_20d": market_trend.get("positive_breadth_20d"),
        "volume_ratio_5d": market_trend.get("average_volume_ratio_5d"),
        "flow_persistence_5d": fund_flow.get("persistence_5d"),
        "news_novelty_5d": news.get("novelty"),
        "news_topic_concentration_5d": news.get("topic_concentration"),
        "news_positive_topic_concentration_5d": news.get(
            "positive_topic_concentration"
        ),
        "news_negative_topic_concentration_5d": news.get(
            "negative_topic_concentration"
        ),
        "rank": sentiment.get("rank"),
        "ranked_count": sentiment.get("ranked_count"),
        "cycle_phase": sentiment.get("cycle_phase"),
        "confidence": sentiment.get("confidence"),
    }
    return _normalize_history_row(row, path=Path("<industry>"), row_number=0)


def upsert_sentiment_snapshots(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    """Atomically replace rows sharing a date/category/methodology storage key."""
    merged = {_history_key(row): row for row in load_sentiment_history(path)}
    for row in rows:
        normalized = _normalize_history_row(row, path=path, row_number=0)
        merged[_history_key(normalized)] = normalized
    ordered = [merged[key] for key in sorted(merged)]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SENTIMENT_HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(_serialize_history_row(row) for row in ordered)
    temporary.replace(path)
    return path
