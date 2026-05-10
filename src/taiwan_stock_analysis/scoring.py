from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.models import MetricsByYear
from taiwan_stock_analysis.score_rules import DIMENSION_LABELS, SCORE_RULES, Rule


def _score_rule(value: float, rule: Rule) -> int:
    direction = rule["direction"]
    excellent = float(rule["excellent"])
    good = float(rule["good"])

    if direction == "higher":
        if value >= excellent:
            return 100
        if value >= good:
            return 75
        if value >= 0:
            return 40
        return 20

    if value <= excellent:
        return 100
    if value <= good:
        return 75
    return 40


def _reason(value: float, rule: Rule, score: int) -> str:
    label = rule["label"]
    if score >= 100:
        return f"{label} {value:.1f}% 達優秀區間"
    if score >= 75:
        return f"{label} {value:.1f}% 達穩健區間"
    return f"{label} {value:.1f}% 低於主要門檻"


def score_dimension(name: str, metrics: dict[str, float | None], rules: list[Rule]) -> dict[str, Any]:
    scores: list[int] = []
    reasons: list[str] = []
    missing = 0

    for rule in rules:
        value = metrics.get(rule["metric"])
        if value is None:
            missing += 1
            reasons.append(f"{rule['label']}缺資料，降低信心")
            continue
        score = _score_rule(value, rule)
        scores.append(score)
        reasons.append(_reason(value, rule, score))

    score = round(sum(scores) / len(scores)) if scores else None
    confidence = round(len(scores) / len(rules) * 100) if rules else 0
    return {
        "label": DIMENSION_LABELS.get(name, name),
        "score": score,
        "confidence": confidence,
        "missing_count": missing,
        "reasons": reasons,
    }


def build_scorecard(metrics_by_year: MetricsByYear, years: list[str]) -> dict[str, Any]:
    latest_year = years[0] if years else None
    latest_metrics = metrics_by_year.get(latest_year or "", {})
    dimensions = {
        name: score_dimension(name, latest_metrics, rules)
        for name, rules in SCORE_RULES.items()
    }
    valid_scores = [
        dimension["score"]
        for dimension in dimensions.values()
        if dimension["score"] is not None
    ]
    total_score = round(sum(valid_scores) / len(valid_scores)) if valid_scores else None
    confidence_values = [dimension["confidence"] for dimension in dimensions.values()]
    confidence = round(sum(confidence_values) / len(confidence_values)) if confidence_values else 0

    return {
        "latest_year": latest_year,
        "total_score": total_score,
        "confidence": confidence,
        "dimensions": dimensions,
        "disclaimer": "valuation_excluded: fundamental quality score excludes valuation and is not investment advice.",
    }
