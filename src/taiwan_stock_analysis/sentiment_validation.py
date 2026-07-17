"""Validation-only labels and walk-forward checks for sentiment turning risk."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
import json
import math
from pathlib import Path
from typing import Any

from taiwan_stock_analysis.sentiment_forecast import calculate_turning_risk
from taiwan_stock_analysis.sentiment_history import load_sentiment_history


_LABEL_WINDOW_SESSIONS = 5
_TURNING_CHANGE_POINTS = 15.0
_MINIMUM_RISK_OBSERVATIONS = 60
_PROMOTION_MINIMUM_SESSIONS = 252
_PROMOTION_MINIMUM_EVENTS = 30
_EVALUATION_THRESHOLDS = (0.50, 0.70)


def _group_copies(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        row = dict(source)
        key = (
            str(row.get("category") or ""),
            str(row.get("methodology_version") or ""),
        )
        grouped[key].append(row)
    for group_rows in grouped.values():
        group_rows.sort(key=lambda row: str(row.get("as_of_date") or ""))
    return grouped


def _finite_score(row: Mapping[str, Any]) -> float | None:
    value = row.get("score_5d")
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) else None


def label_turning_events(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return copied rows with validation-only future peak/trough labels."""
    grouped = _group_copies(rows)

    labeled: list[dict[str, Any]] = []
    radius = _LABEL_WINDOW_SESSIONS
    for key in sorted(grouped):
        group_rows = grouped[key]
        scores = [_finite_score(row) for row in group_rows]
        for index, row in enumerate(group_rows):
            result = dict(row)
            result["peak_label"] = False
            result["trough_label"] = False
            if index < radius or index + radius >= len(group_rows):
                labeled.append(result)
                continue

            window = scores[index - radius : index + radius + 1]
            future = scores[index + 1 : index + radius + 1]
            current = scores[index]
            if current is None or any(score is None for score in window):
                labeled.append(result)
                continue

            numeric_window = [float(score) for score in window]
            numeric_future = [float(score) for score in future]
            earlier = numeric_window[:radius]
            result["peak_label"] = (
                current == max(numeric_window)
                and current not in earlier
                and current - min(numeric_future) >= _TURNING_CHANGE_POINTS
            )
            result["trough_label"] = (
                current == min(numeric_window)
                and current not in earlier
                and max(numeric_future) - current >= _TURNING_CHANGE_POINTS
            )
            labeled.append(result)

    return labeled


def _risk_probability(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        risk = float(value)
    except (TypeError, ValueError):
        return None
    return risk / 100.0 if math.isfinite(risk) else None


def walk_forward_predictions(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Calculate current-inclusive risk without exposing future labels as features."""
    labels = label_turning_events(rows)
    grouped = _group_copies(labels)
    predictions: list[dict[str, Any]] = []
    for key in sorted(grouped):
        group_rows = grouped[key]
        for index in range(_MINIMUM_RISK_OBSERVATIONS - 1, len(group_rows)):
            feature_rows = [
                {
                    field: value
                    for field, value in row.items()
                    if field not in {"peak_label", "trough_label"}
                }
                for row in group_rows[: index + 1]
            ]
            current = group_rows[index]
            as_of_date = str(current.get("as_of_date") or "")
            feature_max_date = max(str(row.get("as_of_date") or "") for row in feature_rows)
            no_lookahead = feature_max_date <= as_of_date
            assert no_lookahead, "walk-forward features extend beyond the prediction date"
            risk = calculate_turning_risk(feature_rows)
            predictions.append(
                {
                    "as_of_date": as_of_date,
                    "category": key[0],
                    "methodology_version": key[1],
                    "feature_max_date": feature_max_date,
                    "no_lookahead": no_lookahead,
                    "peak_probability": _risk_probability(risk.get("peak_risk")),
                    "trough_probability": _risk_probability(risk.get("trough_risk")),
                    "peak_label": bool(current.get("peak_label")),
                    "trough_label": bool(current.get("trough_label")),
                }
            )

    predictions.sort(
        key=lambda row: (
            row["as_of_date"],
            row["category"],
            row["methodology_version"],
        )
    )
    assert all(
        row["feature_max_date"] <= row["as_of_date"] for row in predictions
    ), "walk-forward leakage audit failed"
    return predictions


def _target_metrics(
    predictions: Iterable[Mapping[str, Any]], target: str
) -> dict[str, Any]:
    probability_field = f"{target}_probability"
    label_field = f"{target}_label"
    observations: list[tuple[float, bool]] = []
    for row in predictions:
        probability = row.get(probability_field)
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            continue
        numeric_probability = float(probability)
        if not math.isfinite(numeric_probability):
            continue
        observations.append((numeric_probability, bool(row.get(label_field))))

    observation_count = len(observations)
    event_count = sum(label for _, label in observations)
    event_rate = event_count / observation_count if observation_count else 0.0
    brier_score = (
        sum((probability - float(label)) ** 2 for probability, label in observations)
        / observation_count
        if observation_count
        else None
    )
    unconditional_brier_score = (
        sum((event_rate - float(label)) ** 2 for _, label in observations)
        / observation_count
        if observation_count
        else None
    )
    thresholds: dict[str, dict[str, Any]] = {}
    for threshold in _EVALUATION_THRESHOLDS:
        predicted_positive_count = sum(
            probability >= threshold for probability, _ in observations
        )
        true_positive_count = sum(
            probability >= threshold and label for probability, label in observations
        )
        thresholds[f"{threshold:.2f}"] = {
            "predicted_positive_count": predicted_positive_count,
            "true_positive_count": true_positive_count,
            "precision": (
                true_positive_count / predicted_positive_count
                if predicted_positive_count
                else 0.0
            ),
            "recall": true_positive_count / event_count if event_count else 0.0,
        }

    return {
        "observation_count": observation_count,
        "event_count": event_count,
        "event_rate": event_rate,
        "brier_score": brier_score,
        "unconditional_brier_score": unconditional_brier_score,
        "baseline_brier_score": unconditional_brier_score,
        "thresholds": thresholds,
    }


def _brier_beats_baseline(metrics: Mapping[str, Any]) -> bool:
    brier_score = metrics.get("brier_score")
    baseline = metrics.get("unconditional_brier_score")
    return (
        isinstance(brier_score, (int, float))
        and not isinstance(brier_score, bool)
        and isinstance(baseline, (int, float))
        and not isinstance(baseline, bool)
        and brier_score < baseline
    )


def _target_is_stable(metrics: Mapping[str, Any]) -> bool:
    observation_count = int(metrics.get("observation_count") or 0)
    event_count = int(metrics.get("event_count") or 0)
    return (
        0 < event_count < observation_count
        and _brier_beats_baseline(metrics)
    )


def _chronological_holdouts(
    predictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    session_dates = sorted({str(row["as_of_date"]) for row in predictions})
    midpoint = len(session_dates) // 2
    date_halves = (session_dates[:midpoint], session_dates[midpoint:])
    holdouts: list[dict[str, Any]] = []
    for name, dates in zip(("first_half", "second_half"), date_halves, strict=True):
        date_set = set(dates)
        rows = [row for row in predictions if row["as_of_date"] in date_set]
        peak_metrics = _target_metrics(rows, "peak")
        trough_metrics = _target_metrics(rows, "trough")
        holdouts.append(
            {
                "name": name,
                "start_date": dates[0] if dates else None,
                "end_date": dates[-1] if dates else None,
                "observation_count": len(rows),
                "peak": peak_metrics,
                "trough": trough_metrics,
                "stable": (
                    _target_is_stable(peak_metrics)
                    and _target_is_stable(trough_metrics)
                ),
            }
        )
    return holdouts


def build_sentiment_validation_report(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build experimental metrics and mechanical promotion-readiness checks."""
    source_rows = [dict(row) for row in rows]
    predictions = walk_forward_predictions(source_rows)
    session_count = len({str(row.get("as_of_date") or "") for row in source_rows})
    metrics = {
        "peak": _target_metrics(predictions, "peak"),
        "trough": _target_metrics(predictions, "trough"),
    }
    peak_event_count = int(metrics["peak"]["event_count"])
    trough_event_count = int(metrics["trough"]["event_count"])
    violations = [
        {
            "as_of_date": row["as_of_date"],
            "category": row["category"],
            "methodology_version": row["methodology_version"],
            "feature_max_date": row["feature_max_date"],
        }
        for row in predictions
        if row["feature_max_date"] > row["as_of_date"]
    ]
    no_lookahead = not violations and all(
        bool(row.get("no_lookahead")) for row in predictions
    )
    holdouts = _chronological_holdouts(predictions)
    promotion_checks = {
        "minimum_sessions": session_count >= _PROMOTION_MINIMUM_SESSIONS,
        "minimum_peak_events": peak_event_count >= _PROMOTION_MINIMUM_EVENTS,
        "minimum_trough_events": trough_event_count >= _PROMOTION_MINIMUM_EVENTS,
        "no_lookahead": no_lookahead,
        "peak_brier_beats_baseline": _brier_beats_baseline(metrics["peak"]),
        "trough_brier_beats_baseline": _brier_beats_baseline(metrics["trough"]),
        "two_stable_holdouts": all(row["stable"] for row in holdouts),
    }
    failed_checks = [name for name, passed in promotion_checks.items() if not passed]
    counts = {
        "unique_sessions": session_count,
        "predictions": len(predictions),
        "peak_events": peak_event_count,
        "trough_events": trough_event_count,
    }
    return {
        "status": "experimental",
        "session_count": session_count,
        "unique_session_count": session_count,
        "prediction_count": len(predictions),
        "peak_event_count": peak_event_count,
        "trough_event_count": trough_event_count,
        "counts": counts,
        "metrics": metrics,
        "holdouts": holdouts,
        "leakage_audit": {
            "no_lookahead": no_lookahead,
            "prediction_count": len(predictions),
            "violations": violations,
        },
        "promotion_checks": promotion_checks,
        "failed_checks": failed_checks,
        "promotion_ready": all(promotion_checks.values()),
    }


def write_sentiment_validation_report(
    history_path: Path, output_path: Path
) -> dict[str, Any]:
    """Load stable history and write a traceable experimental validation report."""
    history_path = Path(history_path)
    output_path = Path(output_path)
    report = build_sentiment_validation_report(load_sentiment_history(history_path))
    report["history_path"] = str(history_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
