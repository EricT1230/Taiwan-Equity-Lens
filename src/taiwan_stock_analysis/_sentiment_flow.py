from collections import defaultdict
import math
from typing import Any, Mapping, Sequence


_WINDOW_FIELDS = (
    "valid_days",
    "valid_dates",
    "missing_dates",
    "joined_stocks",
    "joined_stock_ids",
    "expected_stocks",
    "coverage_by_date",
    "net_shares",
    "traded_shares",
    "persistence",
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flow_metrics(
    valid_rows: Sequence[Mapping[str, Any]], valid_dates: Sequence[str]
) -> dict[str, float | None]:
    net_shares = sum(float(row["total_net"]) for row in valid_rows)
    traded_shares = sum(float(row["traded_shares"]) for row in valid_rows)
    day_totals = {
        value: sum(
            float(row["total_net"])
            for row in valid_rows
            if row["date"] == value
        )
        for value in valid_dates
    }
    buy_days = sum(value > 0 for value in day_totals.values())
    sell_days = sum(value < 0 for value in day_totals.values())
    persistence = (
        (buy_days - sell_days) / len(valid_dates) if valid_dates else None
    )
    return {
        "net_shares": net_shares,
        "traded_shares": traded_shares,
        "persistence": persistence,
    }


def _flow_score(
    *, net_shares: float, traded_shares: float, persistence: float
) -> float:
    flow_ratio = net_shares / traded_shares
    return 100.0 * _clamp(
        0.75 * (flow_ratio / 0.05) + 0.25 * persistence,
        -1.0,
        1.0,
    )


def _flow_pair_sources(rows: Sequence[Mapping[str, Any]]) -> str:
    sources = {
        str(row.get("source") or "unknown").strip() or "unknown" for row in rows
    }
    return ", ".join(sorted(sources))


def _group_flow_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    covered_stock_ids: set[str],
    expected_dates: set[str],
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        date_value = str(row.get("date") or "").strip()
        stock_id = str(row.get("stock_id") or "").strip()
        if date_value in expected_dates and stock_id in covered_stock_ids:
            grouped[(date_value, stock_id)].append(row)
    return grouped


def _flow_pair_values(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[float, float] | None]:
    values: list[tuple[float, float] | None] = []
    for row in rows:
        total_net = _finite_float(row.get("total_net"))
        traded_shares = _finite_float(row.get("traded_shares"))
        valid = (
            total_net is not None
            and traded_shares is not None
            and traded_shares > 0.0
        )
        values.append((total_net, traded_shares) if valid else None)
    return values


def _resolve_flow_pair(
    rows: Sequence[Mapping[str, Any]],
    *,
    date_value: str,
    stock_id: str,
    window: str,
) -> tuple[tuple[float, float] | None, int, str | None]:
    values = _flow_pair_values(rows)
    valid_values = {value for value in values if value is not None}
    if len(rows) == 1:
        return (valid_values.pop(), 0, None) if valid_values else (None, 1, None)
    sources = _flow_pair_sources(rows)
    if len(valid_values) == 1 and all(value is not None for value in values):
        warning = (
            f"fund_flow {window} collapsed identical duplicate pair "
            f"({date_value}, {stock_id}) from sources {sources}"
        )
        return valid_values.pop(), 0, warning
    warning = (
        f"fund_flow {window} rejected conflicting duplicate pair "
        f"({date_value}, {stock_id}) from sources {sources}"
    )
    return None, sum(value is None for value in values), warning


def _normalize_flow_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    covered_stock_ids: set[str],
    expected_dates: set[str],
    window: str,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    grouped = _group_flow_pairs(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=expected_dates,
    )
    normalized: list[dict[str, Any]] = []
    excluded_invalid = 0
    warnings: list[str] = []
    for (date_value, stock_id), pair_rows in sorted(grouped.items()):
        value, invalid_count, warning = _resolve_flow_pair(
            pair_rows,
            date_value=date_value,
            stock_id=stock_id,
            window=window,
        )
        excluded_invalid += invalid_count
        if warning is not None:
            warnings.append(warning)
        if value is not None:
            total_net, traded_shares = value
            normalized.append(
                {
                    "date": date_value,
                    "stock_id": stock_id,
                    "total_net": total_net,
                    "traded_shares": traded_shares,
                }
            )
    return normalized, excluded_invalid, warnings


def _flow_date_coverage(
    joined_rows: Sequence[Mapping[str, Any]],
    *,
    expected_dates: Sequence[str],
    expected_stocks: int,
) -> tuple[dict[str, float], list[str]]:
    stock_ids_by_date = {
        value: {
            str(row["stock_id"])
            for row in joined_rows
            if row["date"] == value
        }
        for value in expected_dates
    }
    coverage_by_date = {
        value: (
            len(stock_ids_by_date[value]) / expected_stocks
            if expected_stocks
            else 0.0
        )
        for value in expected_dates
    }
    valid_dates = [
        value for value in expected_dates if coverage_by_date[value] >= 0.60
    ]
    return coverage_by_date, valid_dates


def _flow_window_warnings(
    *,
    score: float | None,
    valid_days: int,
    minimum_valid_days: int,
    excluded_invalid: int,
    pair_warnings: Sequence[str],
    window: str,
) -> list[str]:
    warnings: list[str] = []
    if score is None:
        warnings.append(
            f"fund_flow {window} unavailable: {valid_days} valid sessions; "
            f"requires {minimum_valid_days}"
        )
    if excluded_invalid:
        noun = "row" if excluded_invalid == 1 else "rows"
        warnings.append(
            f"fund_flow {window} excluded {excluded_invalid} {noun} without valid "
            "total_net and positive traded_shares"
        )
    warnings.extend(pair_warnings)
    return warnings


def _flow_window_payload(
    *,
    score: float | None,
    joined_rows: Sequence[Mapping[str, Any]],
    expected_dates: Sequence[str],
    expected_stocks: int,
    coverage_by_date: Mapping[str, float],
    valid_dates: Sequence[str],
    metrics: Mapping[str, float | None],
) -> dict[str, Any]:
    valid_date_set = set(valid_dates)
    joined_stock_ids = sorted({str(row["stock_id"]) for row in joined_rows})
    return {
        "score": score,
        "valid_days": len(valid_dates),
        "valid_dates": list(valid_dates),
        "missing_dates": [
            value for value in expected_dates if value not in valid_date_set
        ],
        "joined_stocks": len(joined_stock_ids),
        "joined_stock_ids": joined_stock_ids,
        "expected_stocks": expected_stocks,
        "coverage_by_date": dict(coverage_by_date),
        "net_shares": metrics["net_shares"],
        "traded_shares": metrics["traded_shares"],
        "persistence": metrics["persistence"],
    }


def _flow_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    covered_stock_ids: set[str],
    expected_dates: list[str],
    minimum_valid_days: int,
    window: str,
) -> tuple[dict[str, Any], list[str]]:
    expected_stocks = len(covered_stock_ids)
    joined_rows, excluded_invalid, pair_warnings = _normalize_flow_pairs(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=set(expected_dates),
        window=window,
    )
    coverage_by_date, valid_dates = _flow_date_coverage(
        joined_rows,
        expected_dates=expected_dates,
        expected_stocks=expected_stocks,
    )
    valid_date_set = set(valid_dates)
    valid_rows = [row for row in joined_rows if row["date"] in valid_date_set]
    metrics = _flow_metrics(valid_rows, valid_dates)
    score = (
        _flow_score(
            net_shares=float(metrics["net_shares"]),
            traded_shares=float(metrics["traded_shares"]),
            persistence=float(metrics["persistence"]),
        )
        if len(valid_dates) >= minimum_valid_days
        else None
    )
    payload = _flow_window_payload(
        score=score,
        joined_rows=joined_rows,
        expected_dates=expected_dates,
        expected_stocks=expected_stocks,
        coverage_by_date=coverage_by_date,
        valid_dates=valid_dates,
        metrics=metrics,
    )
    warnings = _flow_window_warnings(
        score=score,
        valid_days=len(valid_dates),
        minimum_valid_days=minimum_valid_days,
        excluded_invalid=excluded_invalid,
        pair_warnings=pair_warnings,
        window=window,
    )
    return payload, warnings


def _flow_component_status(*, score_5d: float | None, score_20d: float | None) -> str:
    available = sum(score is not None for score in (score_5d, score_20d))
    return "ready" if available == 2 else "partial" if available == 1 else "insufficient_data"


def _flow_component_payload(
    *,
    window_5d: Mapping[str, Any],
    window_20d: Mapping[str, Any],
    expected_stocks: int,
    warnings: Sequence[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "score_5d": window_5d["score"],
        "score_20d": window_20d["score"],
        "expected_stocks": expected_stocks,
        "status": _flow_component_status(
            score_5d=window_5d["score"],
            score_20d=window_20d["score"],
        ),
        "warnings": list(warnings),
    }
    for suffix, window in (("5d", window_5d), ("20d", window_20d)):
        for name in _WINDOW_FIELDS:
            result[f"{name}_{suffix}"] = window[name]
    return result


def score_fund_flow_component_impl(
    rows: Sequence[Mapping[str, Any]],
    *,
    price_covered_stock_ids: Sequence[str],
    expected_session_dates: Sequence[str],
) -> dict[str, Any]:
    covered_stock_ids = {
        normalized
        for value in price_covered_stock_ids
        if value is not None and (normalized := str(value).strip())
    }
    dates = sorted(
        {
            normalized
            for value in expected_session_dates
            if value is not None and (normalized := str(value).strip())
        }
    )
    window_5d, warnings_5d = _flow_window(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=dates[-5:],
        minimum_valid_days=3,
        window="5d",
    )
    window_20d, warnings_20d = _flow_window(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=dates[-20:],
        minimum_valid_days=10,
        window="20d",
    )
    warnings = [*warnings_5d, *warnings_20d]
    if not covered_stock_ids:
        warnings.insert(0, "fund_flow unavailable: no price-covered stocks")
    if not dates:
        warnings.insert(0, "fund_flow unavailable: no expected session dates")
    return _flow_component_payload(
        window_5d=window_5d,
        window_20d=window_20d,
        expected_stocks=len(covered_stock_ids),
        warnings=warnings,
    )
