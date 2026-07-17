"""Deterministic sentiment projection and turning-risk shadow diagnostics."""

from collections.abc import Mapping, Sequence
from datetime import date
import math
from statistics import median
from typing import Any


PROJECTION_HISTORY_DAYS = 20
TURNING_RISK_HISTORY_DAYS = 60
RISK_FAMILY_MAXIMUMS = {
    "level": 25.0,
    "momentum": 25.0,
    "breadth": 20.0,
    "flow": 15.0,
    "crowding": 15.0,
}
RISK_AGREEMENT_THRESHOLDS = {
    "level": 10.0,
    "momentum": 10.0,
    "breadth": 8.0,
    "flow": 6.0,
    "crowding": 6.0,
}
_COMPARISON_ABS_EPSILON = 1e-12
_PROJECTION_RELEVANT_FIELDS = ("score_5d", "baseline_20d")
_RISK_RELEVANT_FIELDS = (
    "score_5d",
    "breadth_5d",
    "breadth_20d",
    "fund_flow_score_5d",
    "fund_flow_score_20d",
    "rank",
    "ranked_count",
    "news_positive_topic_concentration_5d",
    "news_negative_topic_concentration_5d",
    "volume_ratio_5d",
    "price_return_5d",
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _near_boundary(value: float, boundary: float) -> bool:
    return math.isclose(
        value, boundary, rel_tol=0.0, abs_tol=_COMPARISON_ABS_EPSILON
    )


def _at_least(value: float, boundary: float) -> bool:
    return value >= boundary or _near_boundary(value, boundary)


def _at_most(value: float, boundary: float) -> bool:
    return value <= boundary or _near_boundary(value, boundary)


def _strictly_above(value: float, boundary: float) -> bool:
    return value > boundary and not _at_most(value, boundary)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _strict_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _identity_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    return value


def _relevant_value(value: Any) -> tuple[Any, ...]:
    number = _finite_float(value)
    if number is not None:
        return ("number", number)
    if value is None or value == "":
        return ("missing",)
    return ("invalid", type(value).__name__, repr(value))


def _row_fingerprint(
    row: Mapping[str, Any], relevant_fields: Sequence[str]
) -> tuple[tuple[Any, ...], ...]:
    return tuple(_relevant_value(row.get(field)) for field in relevant_fields)


def _count_warning(count: int, noun: str) -> str:
    if count != 1:
        noun = noun.replace("snapshot", "snapshots", 1)
    return f"excluded {count} {noun}"


_EXCLUSION_WARNING_NOUNS = {
    "malformed": "prior snapshot with malformed as_of_date",
    "current": "prior snapshot on current date",
    "future": "future prior snapshot",
    "category": "prior snapshot with category mismatch",
    "category_malformed": "prior snapshot with malformed category",
    "methodology": "prior snapshot with methodology mismatch",
    "methodology_malformed": "prior snapshot with malformed methodology_version",
}


def _validate_current_identity_date(
    current: Mapping[str, Any],
) -> tuple[date | None, str | None, str | None, list[str]]:
    current_date = _strict_date(current.get("as_of_date"))
    category = _identity_text(current.get("category"))
    methodology = _identity_text(current.get("methodology_version"))
    warnings: list[str] = []
    if current_date is None:
        warnings.append(
            "current snapshot invalid: as_of_date must be strict ISO YYYY-MM-DD"
        )
    if category is None:
        warnings.append(
            "current snapshot invalid: category must be a nonempty string "
            "without surrounding whitespace"
        )
    if methodology is None:
        warnings.append(
            "current snapshot invalid: methodology_version must be a nonempty string "
            "without surrounding whitespace"
        )
    return current_date, category, methodology, warnings


def _classify_prior_row(
    row: Mapping[str, Any],
    *,
    current_date: date,
    current_category: str,
    current_methodology: str,
) -> tuple[date | None, str | None]:
    row_date = _strict_date(row.get("as_of_date"))
    if row_date is None:
        return None, "malformed"
    row_category = _identity_text(row.get("category"))
    if row_category is None:
        return None, "category_malformed"
    if row_category != current_category:
        return None, "category"
    row_methodology = _identity_text(row.get("methodology_version"))
    if row_methodology is None:
        return None, "methodology_malformed"
    if row_methodology != current_methodology:
        return None, "methodology"
    if row_date == current_date:
        return None, "current"
    if row_date > current_date:
        return None, "future"
    return row_date, None


def _exclusion_warnings(excluded: Mapping[str, int]) -> list[str]:
    return [
        _count_warning(excluded[key], noun)
        for key, noun in _EXCLUSION_WARNING_NOUNS.items()
        if excluded[key]
    ]


def _resolve_duplicate_date(
    row_date: date,
    rows: Sequence[Mapping[str, Any]],
    *,
    relevant_fields: Sequence[str],
    current_category: str,
    current_methodology: str,
) -> tuple[Mapping[str, Any], str | None]:
    fingerprints = {_row_fingerprint(row, relevant_fields) for row in rows}
    if len(fingerprints) > 1:
        return (
            {
                "as_of_date": row_date.isoformat(),
                "category": current_category,
                "methodology_version": current_methodology,
            },
            "conflicting duplicate prior snapshots rejected for "
            f"{row_date.isoformat()}",
        )
    warning = (
        f"collapsed duplicate prior snapshots for {row_date.isoformat()}"
        if len(rows) > 1
        else None
    )
    return rows[0], warning


def _canonicalize_history(
    history_with_current: Sequence[Mapping[str, Any]],
    *,
    relevant_fields: Sequence[str],
) -> tuple[list[Mapping[str, Any]], list[str], bool]:
    if not history_with_current:
        return [], ["current snapshot unavailable: history is empty"], False

    current = history_with_current[-1]
    current_date, current_category, current_methodology, current_warnings = (
        _validate_current_identity_date(current)
    )
    if current_warnings:
        return [], current_warnings, False

    by_date: dict[date, list[Mapping[str, Any]]] = {}
    excluded = dict.fromkeys(_EXCLUSION_WARNING_NOUNS, 0)
    for row in history_with_current[:-1]:
        row_date, reason = _classify_prior_row(
            row,
            current_date=current_date,
            current_category=current_category,
            current_methodology=current_methodology,
        )
        if reason is not None:
            excluded[reason] += 1
            continue
        by_date.setdefault(row_date, []).append(row)

    warnings = _exclusion_warnings(excluded)
    canonical_prior: list[Mapping[str, Any]] = []
    for row_date in sorted(by_date):
        resolved, warning = _resolve_duplicate_date(
            row_date,
            by_date[row_date],
            relevant_fields=relevant_fields,
            current_category=current_category,
            current_methodology=current_methodology,
        )
        canonical_prior.append(resolved)
        if warning is not None:
            warnings.append(warning)
    return [*canonical_prior, current], warnings, True


def _with_warnings(result: dict[str, Any], warnings: Sequence[str]) -> dict[str, Any]:
    if warnings:
        result["warnings"] = [*result["warnings"], *warnings]
    return result


def _weighted_slope(values: list[float], half_life: float = 3.0) -> float:
    x_values = [float(index) for index in range(len(values))]
    weights = [
        0.5 ** ((len(values) - 1 - index) / half_life)
        for index in range(len(values))
    ]
    weight_sum = sum(weights)
    x_mean = sum(
        weight * value for weight, value in zip(weights, x_values)
    ) / weight_sum
    y_mean = sum(
        weight * value for weight, value in zip(weights, values)
    ) / weight_sum
    denominator = sum(
        weight * (x_value - x_mean) ** 2
        for weight, x_value in zip(weights, x_values)
    )
    if denominator == 0:
        return 0.0
    numerator = sum(
        weight * (x_value - x_mean) * (y_value - y_mean)
        for weight, x_value, y_value in zip(weights, x_values, values)
    )
    return numerator / denominator


def _projection_rows(
    history_with_current: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], float, float]]:
    rows: list[tuple[Mapping[str, Any], float, float]] = []
    for row in history_with_current:
        score = _finite_float(row.get("score_5d"))
        baseline = _finite_float(row.get("baseline_20d"))
        if score is not None and baseline is not None:
            rows.append((row, score, baseline))
    return rows


def _empty_projection(history_days: int) -> dict[str, Any]:
    return {
        "status": "insufficient_history",
        "history_days": history_days,
        "forecast_1d": None,
        "forecast_5d": None,
        "interval_1d": None,
        "interval_5d": None,
        "forecast_slope_10d": None,
        "daily_step": None,
        "residual_count": 0,
        "robust_sigma": None,
        "warnings": [
            "projection requires at least 20 valid snapshot days"
        ],
    }


def _invalid_projection(history_days: int, warning: str) -> dict[str, Any]:
    result = _empty_projection(history_days)
    result["status"] = "insufficient_data"
    result["warnings"] = [warning]
    return result


def _one_step_residuals(
    rows: Sequence[tuple[Mapping[str, Any], float, float]],
) -> list[float]:
    residuals: list[float] = []
    for index in range(10, len(rows)):
        prior_scores = [score for _, score, _ in rows[index - 10 : index]]
        origin_score = rows[index - 1][1]
        origin_baseline = rows[index - 1][2]
        daily_step = (
            0.70 * _weighted_slope(prior_scores)
            + 0.30 * ((origin_baseline - origin_score) / 20.0)
        )
        predicted = _clamp(origin_score + daily_step, -100.0, 100.0)
        residuals.append(rows[index][1] - predicted)
    return residuals


def _projection_interval(
    forecast: float, robust_sigma: float, horizon: float
) -> list[float]:
    radius = 1.96 * robust_sigma * math.sqrt(horizon)
    return [
        _clamp(forecast - radius, -100.0, 100.0),
        _clamp(forecast + radius, -100.0, 100.0),
    ]


def project_sentiment(
    history_with_current: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a bounded deterministic projection, never a calibrated probability."""
    canonical, canonical_warnings, current_contract_valid = _canonicalize_history(
        history_with_current,
        relevant_fields=_PROJECTION_RELEVANT_FIELDS,
    )
    if not current_contract_valid:
        return _with_warnings(
            _invalid_projection(0, "current snapshot contract is invalid"),
            canonical_warnings,
        )
    rows = _projection_rows(canonical)
    history_days = len(rows)
    current = canonical[-1]
    current_score = _finite_float(current.get("score_5d"))
    current_baseline = _finite_float(current.get("baseline_20d"))
    if current_score is None:
        return _with_warnings(
            _invalid_projection(
                history_days,
                "current snapshot invalid: score_5d must be finite",
            ),
            canonical_warnings,
        )
    if current_baseline is None:
        return _with_warnings(
            _invalid_projection(
                history_days,
                "current snapshot invalid: baseline_20d must be finite",
            ),
            canonical_warnings,
        )
    if history_days < PROJECTION_HISTORY_DAYS:
        return _with_warnings(
            _empty_projection(history_days), canonical_warnings
        )

    scores = [score for _, score, _ in rows]
    score = scores[-1]
    baseline = rows[-1][2]
    forecast_slope_10d = _weighted_slope(scores[-10:])
    daily_step = (
        0.70 * forecast_slope_10d
        + 0.30 * ((baseline - score) / 20.0)
    )
    forecast_1d = _clamp(score + daily_step, -100.0, 100.0)
    forecast_5d = _clamp(score + 5.0 * daily_step, -100.0, 100.0)
    residuals = _one_step_residuals(rows)
    robust_sigma = None
    interval_1d = None
    interval_5d = None
    warnings = [
        "experimental deterministic projection; not a calibrated probability"
    ]
    if len(residuals) >= 10:
        residual_median = median(residuals)
        robust_sigma = 1.4826 * median(
            [abs(value - residual_median) for value in residuals]
        )
        interval_1d = _projection_interval(forecast_1d, robust_sigma, 1.0)
        interval_5d = _projection_interval(forecast_5d, robust_sigma, 5.0)
    else:
        warnings.append(
            "projection interval unavailable: fewer than 10 one-step residuals"
        )
    return _with_warnings({
        "status": "experimental",
        "history_days": history_days,
        "forecast_1d": forecast_1d,
        "forecast_5d": forecast_5d,
        "interval_1d": interval_1d,
        "interval_5d": interval_5d,
        "forecast_slope_10d": forecast_slope_10d,
        "daily_step": daily_step,
        "residual_count": len(residuals),
        "robust_sigma": robust_sigma,
        "warnings": warnings,
    }, canonical_warnings)


def _empty_risk(history_days: int) -> dict[str, Any]:
    empty_families = {name: 0.0 for name in RISK_FAMILY_MAXIMUMS}
    return {
        "status": "insufficient_history",
        "history_days": history_days,
        "peak_risk": None,
        "trough_risk": None,
        "direction": "unclear",
        "window": "unclear",
        "diagnostics": {
            "peak": dict(empty_families),
            "trough": dict(empty_families),
        },
        "warnings": [
            "turning-risk diagnostics require at least 60 valid snapshot days"
        ],
        "calibrated_probability": None,
    }


def _invalid_risk(history_days: int, warning: str) -> dict[str, Any]:
    result = _empty_risk(history_days)
    result["status"] = "insufficient_data"
    result["warnings"] = [warning]
    return result


def _positive_int(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None or number <= 0.0 or not number.is_integer():
        return None
    return int(number)


def _quartile_streak(
    rows: Sequence[Mapping[str, Any]], *, top: bool
) -> int:
    streak = 0
    for row in reversed(rows):
        if _finite_float(row.get("score_5d")) is None:
            break
        rank = _positive_int(row.get("rank"))
        ranked_count = _positive_int(row.get("ranked_count"))
        if rank is None or ranked_count is None or rank > ranked_count:
            break
        quartile_count = max(1, math.ceil(ranked_count * 0.25))
        qualifies = (
            rank <= quartile_count
            if top
            else rank > ranked_count - quartile_count
        )
        if not qualifies:
            break
        streak += 1
    return streak


def _risk_window(risk: float, agreeing_families: int) -> str:
    if _at_least(risk, 70.0) and agreeing_families >= 3:
        return "1_to_3_days"
    if (
        _at_least(risk, 50.0)
        and not _at_least(risk, 70.0)
        and agreeing_families >= 2
    ):
        return "4_to_7_days"
    return "unclear"


def _meets_agreement_threshold(contribution: float, threshold: float) -> bool:
    return _at_least(contribution, threshold)


def _resolve_turning_signal(
    *,
    peak_risk: float,
    peak_agreeing_families: int,
    trough_risk: float,
    trough_agreeing_families: int,
) -> tuple[str, str, list[str]]:
    if _strictly_above(peak_risk, 50.0) and _strictly_above(
        trough_risk,
        50.0,
    ):
        return (
            "unclear",
            "unclear",
            ["regime uncertainty: peak and trough diagnostics conflict"],
        )

    peak_window = _risk_window(peak_risk, peak_agreeing_families)
    trough_window = _risk_window(trough_risk, trough_agreeing_families)
    if (
        peak_window != "unclear"
        and _strictly_above(peak_risk, trough_risk)
        and _at_most(trough_risk, 50.0)
    ):
        return "peak", peak_window, []
    if (
        trough_window != "unclear"
        and _strictly_above(trough_risk, peak_risk)
        and _at_most(peak_risk, 50.0)
    ):
        return "trough", trough_window, []
    return "unclear", "unclear", []


def _level_family(score: float, percentile: float) -> tuple[float, float]:
    peak = (
        15.0 * _clamp((score - 50.0) / 30.0, 0.0, 1.0)
        + 10.0 * _clamp((percentile - 80.0) / 15.0, 0.0, 1.0)
    )
    trough = (
        15.0 * _clamp((-score - 40.0) / 30.0, 0.0, 1.0)
        + 10.0 * _clamp((20.0 - percentile) / 15.0, 0.0, 1.0)
    )
    return peak, trough


def _momentum_family(
    slope_now: float, slope_prior: float
) -> tuple[float, float]:
    peak = (
        25.0
        * _clamp(
            (slope_prior - slope_now) / max(abs(slope_prior), 2.0),
            0.0,
            1.0,
        )
        if slope_prior > 0.0
        else 0.0
    )
    trough = (
        25.0
        * _clamp(
            (slope_now - slope_prior) / max(abs(slope_prior), 2.0),
            0.0,
            1.0,
        )
        if slope_prior < 0.0
        else 0.0
    )
    return peak, trough


def _breadth_family(
    current: Mapping[str, Any], score: float
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    breadth_5d = _finite_float(current.get("breadth_5d"))
    breadth_20d = _finite_float(current.get("breadth_20d"))
    if breadth_5d is None or breadth_20d is None:
        warnings.append(
            "breadth diagnostic unavailable: missing breadth_5d or breadth_20d; "
            "family contributes zero"
        )
        return 0.0, 0.0, warnings
    peak = (
        20.0 * _clamp((breadth_20d - breadth_5d) / 0.20, 0.0, 1.0)
        if score > 20.0
        else 0.0
    )
    trough = (
        20.0 * _clamp((breadth_5d - breadth_20d) / 0.20, 0.0, 1.0)
        if score < -20.0
        else 0.0
    )
    return peak, trough, warnings


def _flow_family(
    current: Mapping[str, Any], score: float
) -> tuple[float, float, list[str]]:
    warnings: list[str] = []
    flow_5d = _finite_float(current.get("fund_flow_score_5d"))
    flow_20d = _finite_float(current.get("fund_flow_score_20d"))
    if flow_5d is None or flow_20d is None:
        warnings.append(
            "flow diagnostic unavailable: missing fund_flow_score_5d or "
            "fund_flow_score_20d; family contributes zero"
        )
        return 0.0, 0.0, warnings
    peak = (
        15.0 * _clamp((flow_20d - flow_5d) / 40.0, 0.0, 1.0)
        if score > 20.0
        else 0.0
    )
    trough = (
        15.0 * _clamp((flow_5d - flow_20d) / 40.0, 0.0, 1.0)
        if score < -20.0
        else 0.0
    )
    return peak, trough, warnings


def _crowding_family(
    current: Mapping[str, Any],
    canonical_rows: Sequence[Mapping[str, Any]],
) -> tuple[float, float, int, int]:
    top_quartile_streak = _quartile_streak(canonical_rows, top=True)
    bottom_quartile_streak = _quartile_streak(canonical_rows, top=False)
    positive_concentration = _finite_float(
        current.get("news_positive_topic_concentration_5d")
    )
    negative_concentration = _finite_float(
        current.get("news_negative_topic_concentration_5d")
    )
    volume_ratio = _finite_float(current.get("volume_ratio_5d"))
    price_return = _finite_float(current.get("price_return_5d"))
    peak = sum(
        (
            5.0 if top_quartile_streak >= 5 else 0.0,
            5.0
            if positive_concentration is not None
            and positive_concentration >= 0.60
            else 0.0,
            5.0
            if volume_ratio is not None
            and price_return is not None
            and volume_ratio >= 1.8
            and price_return > 0.0
            else 0.0,
        )
    )
    trough = sum(
        (
            5.0 if bottom_quartile_streak >= 5 else 0.0,
            5.0
            if negative_concentration is not None
            and negative_concentration >= 0.60
            else 0.0,
            5.0
            if volume_ratio is not None
            and price_return is not None
            and volume_ratio >= 1.8
            and price_return < 0.0
            else 0.0,
        )
    )
    return peak, trough, top_quartile_streak, bottom_quartile_streak


def _risk_contributions(
    rows: Sequence[tuple[Mapping[str, Any], float]],
    *,
    canonical_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, float], dict[str, float], dict[str, Any], list[str]]:
    current, score = rows[-1]
    scores = [value for _, value in rows[-60:]]
    percentile = 100.0 * sum(value <= score for value in scores) / len(scores)
    slope_now = (scores[-1] - scores[-3]) / 2.0
    slope_prior = (scores[-4] - scores[-6]) / 2.0

    peak_level, trough_level = _level_family(score, percentile)
    peak_momentum, trough_momentum = _momentum_family(
        slope_now,
        slope_prior,
    )
    peak_breadth, trough_breadth, breadth_warnings = _breadth_family(
        current,
        score,
    )
    peak_flow, trough_flow, flow_warnings = _flow_family(current, score)
    (
        peak_crowding,
        trough_crowding,
        top_quartile_streak,
        bottom_quartile_streak,
    ) = _crowding_family(current, canonical_rows)
    peak = {
        "level": peak_level,
        "momentum": peak_momentum,
        "breadth": peak_breadth,
        "flow": peak_flow,
        "crowding": peak_crowding,
    }
    trough = {
        "level": trough_level,
        "momentum": trough_momentum,
        "breadth": trough_breadth,
        "flow": trough_flow,
        "crowding": trough_crowding,
    }

    for family, maximum in RISK_FAMILY_MAXIMUMS.items():
        peak[family] = _clamp(peak[family], 0.0, maximum)
        trough[family] = _clamp(trough[family], 0.0, maximum)
    context = {
        "percentile_60d": percentile,
        "slope_now": slope_now,
        "slope_prior": slope_prior,
        "top_quartile_streak": top_quartile_streak,
        "bottom_quartile_streak": bottom_quartile_streak,
    }
    return peak, trough, context, [*breadth_warnings, *flow_warnings]


def calculate_turning_risk(
    history_with_current: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return descriptive peak/trough risk values in experimental shadow mode."""
    canonical, canonical_warnings, current_contract_valid = _canonicalize_history(
        history_with_current,
        relevant_fields=_RISK_RELEVANT_FIELDS,
    )
    if not current_contract_valid:
        return _with_warnings(
            _invalid_risk(0, "current snapshot contract is invalid"),
            canonical_warnings,
        )
    rows = [
        (row, score)
        for row in canonical
        if (score := _finite_float(row.get("score_5d"))) is not None
    ]
    history_days = len(rows)
    if _finite_float(canonical[-1].get("score_5d")) is None:
        return _with_warnings(
            _invalid_risk(
                history_days,
                "current snapshot invalid: score_5d must be finite",
            ),
            canonical_warnings,
        )
    if history_days < TURNING_RISK_HISTORY_DAYS:
        return _with_warnings(_empty_risk(history_days), canonical_warnings)

    peak, trough, context, diagnostic_warnings = _risk_contributions(
        rows,
        canonical_rows=canonical,
    )
    peak_risk = _clamp(sum(peak.values()), 0.0, 100.0)
    trough_risk = _clamp(sum(trough.values()), 0.0, 100.0)
    peak_agreeing_families = sum(
        _meets_agreement_threshold(peak[family], threshold)
        for family, threshold in RISK_AGREEMENT_THRESHOLDS.items()
    )
    trough_agreeing_families = sum(
        _meets_agreement_threshold(trough[family], threshold)
        for family, threshold in RISK_AGREEMENT_THRESHOLDS.items()
    )
    direction, window, conflict_warnings = _resolve_turning_signal(
        peak_risk=peak_risk,
        peak_agreeing_families=peak_agreeing_families,
        trough_risk=trough_risk,
        trough_agreeing_families=trough_agreeing_families,
    )
    return _with_warnings({
        "status": "experimental",
        "history_days": history_days,
        "peak_risk": peak_risk,
        "trough_risk": trough_risk,
        "direction": direction,
        "window": window,
        "diagnostics": {
            "peak": peak,
            "trough": trough,
            **context,
            "peak_agreeing_families": peak_agreeing_families,
            "trough_agreeing_families": trough_agreeing_families,
        },
        "warnings": [
            "experimental turning risk; risk is not a calibrated probability",
            *diagnostic_warnings,
            *conflict_warnings,
        ],
        "calibrated_probability": None,
    }, canonical_warnings)
