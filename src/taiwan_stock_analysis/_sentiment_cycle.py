import math
from typing import Any, Mapping, Sequence


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ols_slope(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    selected = list(values[-3:])
    x_mean = (len(selected) - 1) / 2.0
    y_mean = sum(selected) / len(selected)
    denominator = sum((index - x_mean) ** 2 for index in range(len(selected)))
    return sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(selected)
    ) / denominator


def _slope_direction(slope: float | None) -> str:
    if slope is None:
        return "unavailable"
    if slope >= 2.0:
        return "positive"
    if slope <= -2.0:
        return "negative"
    return "flat"


def _nested_component(
    assessment: Mapping[str, Any], name: str
) -> Mapping[str, Any]:
    components = assessment.get("components")
    if not isinstance(components, Mapping):
        return {}
    component = components.get(name)
    return component if isinstance(component, Mapping) else {}


def _assessment_number(
    assessment: Mapping[str, Any],
    flat_key: str,
    *,
    component_name: str,
    component_key: str,
) -> float | None:
    value = _finite_float(assessment.get(flat_key))
    if value is not None:
        return value
    return _finite_float(
        _nested_component(assessment, component_name).get(component_key)
    )


def _ordered_prior_history(
    prior_history: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    indexed = [(index, dict(row)) for index, row in enumerate(prior_history)]
    indexed.sort(key=lambda item: (str(item[1].get("as_of_date") or ""), item[0]))
    return [row for _, row in indexed]


def _compatible_history_tail(
    prior_history: Sequence[Mapping[str, Any]], methodology_version: str
) -> list[dict[str, Any]]:
    compatible_reversed: list[dict[str, Any]] = []
    for row in reversed(_ordered_prior_history(prior_history)):
        row_version = str(row.get("methodology_version") or methodology_version)
        if row_version != methodology_version:
            break
        compatible_reversed.append(row)
    return list(reversed(compatible_reversed))


def _positive_int(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None or number <= 0.0 or not number.is_integer():
        return None
    return int(number)


def _ranking_streak(
    prior_history: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
    methodology_version: str,
) -> int:
    rows = [*_ordered_prior_history(prior_history), dict(current)]
    streak = 0
    for row in reversed(rows):
        row_version = str(row.get("methodology_version") or methodology_version)
        if row_version != methodology_version:
            break
        rank = _positive_int(row.get("rank"))
        ranked_count = _positive_int(row.get("ranked_count"))
        if rank is None or ranked_count is None:
            break
        if _finite_float(row.get("score_5d")) is None:
            break
        top_quartile_count = max(1, math.ceil(ranked_count * 0.25))
        if rank > top_quartile_count:
            break
        streak += 1
    return streak


def _trailing_percentile(
    scores: Sequence[float], current_score: float | None
) -> float | None:
    if current_score is None or len(scores) < 20:
        return None
    return 100.0 * sum(value <= current_score for value in scores) / len(scores)


def _cycle_history_diagnostics(
    assessment: Mapping[str, Any],
    prior_history: Sequence[Mapping[str, Any]],
    default_methodology_version: str,
) -> dict[str, Any]:
    methodology_version = str(
        assessment.get("methodology_version") or default_methodology_version
    )
    compatible_prior = _compatible_history_tail(
        prior_history, methodology_version
    )
    score = _finite_float(assessment.get("score_5d"))
    prior_scores = [
        value
        for row in compatible_prior
        if (value := _finite_float(row.get("score_5d"))) is not None
    ]
    scores_with_current = [*prior_scores]
    if score is not None:
        scores_with_current.append(score)
    recent_slope = _ols_slope(scores_with_current)
    prior_slope = _ols_slope(prior_scores)
    return {
        "recent_slope": recent_slope,
        "prior_slope": prior_slope,
        "slope_direction": _slope_direction(recent_slope),
        "trailing_percentile": _trailing_percentile(scores_with_current, score),
        "ranking_streak": _ranking_streak(
            prior_history, assessment, methodology_version
        ),
        "history_scores": len(scores_with_current),
    }


def _cycle_breadth_diagnostics(
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    breadth_5d = _assessment_number(
        assessment,
        "breadth_5d",
        component_name="price",
        component_key="breadth_5d",
    )
    breadth_20d = _assessment_number(
        assessment,
        "breadth_20d",
        component_name="price",
        component_key="breadth_20d",
    )
    breadth_change = (
        breadth_5d - breadth_20d
        if breadth_5d is not None and breadth_20d is not None
        else None
    )
    breadth_state = (
        "expanding"
        if breadth_change is not None and breadth_change >= 0.10
        else "contracting"
        if breadth_change is not None and breadth_change <= -0.10
        else "stable"
        if breadth_change is not None
        else "unavailable"
    )
    return {
        "breadth_5d": breadth_5d,
        "breadth_20d": breadth_20d,
        "breadth_change": breadth_change,
        "breadth_state": breadth_state,
    }


def _cycle_crowding_signals(
    *,
    score: float | None,
    ranking_streak: int,
    topic_concentration: float | None,
    volume_ratio_5d: float | None,
) -> list[str]:
    signals: list[str] = []
    if ranking_streak >= 5:
        signals.append("top_quartile_streak")
    if topic_concentration is not None and topic_concentration >= 0.60:
        signals.append("topic_concentration")
    if (
        volume_ratio_5d is not None
        and volume_ratio_5d >= 1.8
        and score is not None
        and abs(score) >= 60.0
    ):
        signals.append("high_volume_extreme_score")
    return signals


def _cycle_deceleration(
    *,
    score: float | None,
    recent_slope: float | None,
    prior_slope: float | None,
) -> tuple[bool, str | None]:
    positive = (
        score is not None
        and score >= 50.0
        and prior_slope is not None
        and prior_slope >= 2.0
        and recent_slope is not None
        and recent_slope <= 0.5 * prior_slope
    )
    negative = (
        score is not None
        and score <= -50.0
        and prior_slope is not None
        and prior_slope <= -2.0
        and recent_slope is not None
        and recent_slope >= 0.5 * prior_slope
    )
    direction = "positive" if positive else "negative" if negative else None
    return positive or negative, direction


def _cycle_diagnostic_payload(
    history: Mapping[str, Any],
    breadth: Mapping[str, Any],
    *,
    topic_concentration: float | None,
    volume_ratio_5d: float | None,
    crowding_signals: Sequence[str],
    decelerating: bool,
    deceleration_direction: str | None,
) -> dict[str, Any]:
    return {
        "recent_slope": history["recent_slope"],
        "prior_slope": history["prior_slope"],
        "slope_direction": history["slope_direction"],
        "breadth_5d": breadth["breadth_5d"],
        "breadth_20d": breadth["breadth_20d"],
        "breadth_change": breadth["breadth_change"],
        "breadth_state": breadth["breadth_state"],
        "trailing_percentile": history["trailing_percentile"],
        "ranking_streak": history["ranking_streak"],
        "topic_concentration": topic_concentration,
        "volume_ratio_5d": volume_ratio_5d,
        "crowding": bool(crowding_signals),
        "crowding_signals": list(crowding_signals),
        "decelerating": decelerating,
        "deceleration_direction": deceleration_direction,
        "history_scores": history["history_scores"],
    }


def _cycle_diagnostics(
    assessment: Mapping[str, Any],
    prior_history: Sequence[Mapping[str, Any]],
    default_methodology_version: str,
) -> dict[str, Any]:
    history = _cycle_history_diagnostics(
        assessment, prior_history, default_methodology_version
    )
    breadth = _cycle_breadth_diagnostics(assessment)
    score = _finite_float(assessment.get("score_5d"))
    topic_concentration = _assessment_number(
        assessment,
        "news_topic_concentration_5d",
        component_name="news",
        component_key="topic_concentration",
    )
    volume_ratio_5d = _assessment_number(
        assessment,
        "volume_ratio_5d",
        component_name="price",
        component_key="volume_ratio_5d",
    )
    crowding_signals = _cycle_crowding_signals(
        score=score,
        ranking_streak=int(history["ranking_streak"]),
        topic_concentration=topic_concentration,
        volume_ratio_5d=volume_ratio_5d,
    )
    decelerating, deceleration_direction = _cycle_deceleration(
        score=score,
        recent_slope=history["recent_slope"],
        prior_slope=history["prior_slope"],
    )
    return _cycle_diagnostic_payload(
        history,
        breadth,
        topic_concentration=topic_concentration,
        volume_ratio_5d=volume_ratio_5d,
        crowding_signals=crowding_signals,
        decelerating=decelerating,
        deceleration_direction=deceleration_direction,
    )


def _is_overheating(
    score: float | None,
    trailing_percentile: float | None,
    ranking_streak: int,
    crowding: bool,
    decelerating: bool,
) -> bool:
    extreme = score is not None and (
        score >= 70.0
        or (
            trailing_percentile is not None
            and trailing_percentile >= 90.0
            and ranking_streak >= 3
        )
    )
    return extreme and (crowding or decelerating)


def _is_recovery(
    score: float | None, change: float | None, slope_direction: str
) -> bool:
    return (
        score is not None
        and score <= 20.0
        and change is not None
        and change >= 10.0
        and slope_direction == "positive"
    )


def _is_ignition(
    score: float | None,
    change: float | None,
    slope_direction: str,
    breadth_state: str,
) -> bool:
    return (
        score is not None
        and -20.0 <= score < 40.0
        and change is not None
        and change >= 10.0
        and slope_direction == "positive"
        and breadth_state == "expanding"
    )


def _is_expansion(
    score: float | None,
    slope_direction: str,
    breadth_5d: float | None,
) -> bool:
    return (
        score is not None
        and 20.0 <= score < 70.0
        and slope_direction == "positive"
        and breadth_5d is not None
        and breadth_5d >= 0.55
    )


def _is_cooling(
    score: float | None,
    change: float | None,
    slope_direction: str,
    breadth_state: str,
) -> bool:
    return (
        score is not None
        and score > -20.0
        and (
            (change is not None and change <= -10.0)
            or (
                slope_direction == "negative"
                and breadth_state == "contracting"
            )
        )
    )


def _select_cycle_phase(
    assessment: Mapping[str, Any], diagnostics: Mapping[str, Any]
) -> str:
    score = _finite_float(assessment.get("score_5d"))
    change = _finite_float(assessment.get("change"))
    slope = str(diagnostics.get("slope_direction") or "unavailable")
    breadth_5d = _finite_float(diagnostics.get("breadth_5d"))
    breadth_state = str(diagnostics.get("breadth_state") or "unavailable")
    percentile = _finite_float(diagnostics.get("trailing_percentile"))
    ranking_streak = int(diagnostics.get("ranking_streak") or 0)
    if _is_overheating(
        score,
        percentile,
        ranking_streak,
        diagnostics.get("crowding") is True,
        diagnostics.get("decelerating") is True,
    ):
        return "overheating"
    if score is not None and score <= -60.0 and slope == "negative":
        return "capitulation"
    if _is_recovery(score, change, slope):
        return "recovery"
    if _is_ignition(score, change, slope, breadth_state):
        return "ignition"
    if _is_expansion(score, slope, breadth_5d):
        return "expansion"
    if _is_cooling(score, change, slope, breadth_state):
        return "cooling"
    return "consolidation"


def classify_sentiment_cycle_impl(
    assessment: Mapping[str, Any],
    prior_history: Sequence[Mapping[str, Any]],
    *,
    default_methodology_version: str,
) -> dict[str, Any]:
    diagnostics = _cycle_diagnostics(
        assessment, prior_history, default_methodology_version
    )
    return {"phase": _select_cycle_phase(assessment, diagnostics), **diagnostics}
