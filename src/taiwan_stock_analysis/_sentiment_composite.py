import math
from typing import Any, Callable, Mapping, Sequence


LabelClassifier = Callable[[float], str]


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _freshness_entry(
    freshness: Mapping[str, Any], component_name: str
) -> Any:
    if component_name in freshness:
        return freshness[component_name]
    if component_name == "price":
        return freshness.get("industry_trend")
    return None


def _is_fresh(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        if "fresh" in value:
            return value.get("fresh") is True
        value = value.get("status")
    return str(value or "").strip().lower() == "fresh"


def _freshness_description(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("status", value.get("fresh"))
    if value is True:
        return "fresh"
    if value is False:
        return "not fresh"
    return str(value or "missing")


def _freshness_has_source_error(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _freshness_has_source_error(value.get(key))
            for key in ("status", "source_status", "source")
            if key in value
        )
    return str(value or "").strip().lower() == "source_error"


def component_freshness_state(
    source_value: Any,
    *,
    local_fresh: bool,
    local_failure: str,
) -> dict[str, Any]:
    source_status = _freshness_description(source_value)
    source_fresh = _is_fresh(source_value)
    status = (
        source_status
        if not source_fresh
        else "fresh"
        if local_fresh
        else local_failure
    )
    return {
        "status": status,
        "source_status": source_status,
        "local_status": "fresh" if local_fresh else local_failure,
        "fresh": source_fresh and local_fresh,
        "source": dict(source_value)
        if isinstance(source_value, Mapping)
        else source_value,
    }


def _component_warning(name: str, warning: Any) -> str:
    text = str(warning).strip()
    if text.startswith(f"{name} ") or text.startswith(f"{name}:"):
        return text
    return f"{name}: {text}"


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _component_reason(
    name: str,
    component: Mapping[str, Any],
    contribution: float,
) -> str:
    if name == "news":
        return f"news contribution {contribution:+.1f}"
    if name == "price":
        breadth = _finite_float(component.get("breadth_5d"))
        if breadth is not None:
            return f"5-day breadth {breadth * 100.0:.1f}%"
        return f"price contribution {contribution:+.1f}"
    persistence = _finite_float(component.get("persistence_5d"))
    if persistence is not None:
        return f"institutional flow persistence {persistence:+.2f}"
    return f"fund flow contribution {contribution:+.1f}"


def _coverage_downgrades(
    components: Mapping[str, Mapping[str, Any]], usable: Sequence[str]
) -> list[str]:
    downgrades: list[str] = []
    if "news" in usable:
        coverage = components["news"].get("coverage")
        articles = (
            _finite_float(coverage.get("articles_5d"))
            if isinstance(coverage, Mapping)
            else None
        )
        if articles is None or articles < 3.0:
            value = "missing" if articles is None else str(int(articles))
            downgrades.append(
                f"news 5d coverage {value} articles is below the 3-article minimum"
            )
    if "price" in usable:
        coverage = _finite_float(components["price"].get("coverage_ratio_5d"))
        if coverage is None:
            downgrades.append("price 5d coverage is missing or invalid")
        elif coverage < 0.80:
            downgrades.append(
                f"price 5d coverage {coverage * 100.0:.1f}% is below 80.0%"
            )
    if "fund_flow" in usable:
        valid_days = _finite_float(components["fund_flow"].get("valid_days_5d"))
        if valid_days is None:
            downgrades.append("fund_flow 5d valid-session coverage is missing")
        elif valid_days < 4.0:
            downgrades.append(
                f"fund_flow 5d has {int(valid_days)} valid sessions; high confidence requires 4"
            )
    for name in usable:
        component = components[name]
        if str(component.get("status") or "") == "partial":
            downgrades.append(f"{name} component has partial-source status")
        if component.get("warnings"):
            downgrades.append(f"{name} component has partial-source warnings")
    return downgrades


def _missing_score_windows(component: Mapping[str, Any]) -> list[str]:
    return [
        window
        for window in ("5d", "20d")
        if _finite_float(component.get(f"score_{window}")) is None
    ]


def _freshness_payload(value: Any, *, fresh: bool) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {"status": _freshness_description(value), "fresh": fresh}


def _prepare_component(
    name: str,
    raw_component: Mapping[str, Any],
    *,
    configured_weight: float,
) -> tuple[dict[str, Any], list[str], list[str]]:
    component = dict(raw_component)
    component["configured_weight"] = configured_weight
    component["effective_weight"] = None
    component["contribution_5d"] = None
    component["contribution_20d"] = None
    warnings = [
        _component_warning(name, warning)
        for warning in component.get("warnings") or []
    ]
    missing_windows = _missing_score_windows(component)
    if len(missing_windows) == 1:
        missing_text = f"missing {missing_windows[0]} score"
    elif missing_windows:
        missing_text = "missing 5d and 20d scores"
    else:
        missing_text = ""
    if missing_text:
        warnings.append(f"{name} removed from composite: {missing_text}")
    return component, warnings, missing_windows


def _select_usable_components(
    components: Mapping[str, Mapping[str, Any]],
    *,
    freshness: Mapping[str, Any],
    configured_weights: Mapping[str, float],
) -> tuple[dict[str, dict[str, Any]], list[str], list[str], list[str]]:
    normalized: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    usable: list[str] = []
    fresh_names: list[str] = []
    for name, weight in configured_weights.items():
        component, component_warnings, missing = _prepare_component(
            name,
            components.get(name, {}),
            configured_weight=weight,
        )
        normalized[name] = component
        for warning in component_warnings:
            _append_unique(warnings, warning)
        freshness_value = _freshness_entry(freshness, name)
        fresh = _is_fresh(freshness_value)
        component["freshness"] = _freshness_payload(freshness_value, fresh=fresh)
        if fresh:
            fresh_names.append(name)
        else:
            _append_unique(
                warnings,
                f"{name} removed from composite: freshness status "
                f"{_freshness_description(freshness_value)}",
            )
        if not missing and fresh:
            usable.append(name)
    return normalized, warnings, usable, fresh_names


def _effective_weights(
    names: Sequence[str], configured_weights: Mapping[str, float]
) -> dict[str, float]:
    total = sum(configured_weights[name] for name in names)
    return {name: configured_weights[name] / total for name in names}


def _score_usable_components(
    components: dict[str, dict[str, Any]],
    usable: Sequence[str],
    configured_weights: Mapping[str, float],
) -> tuple[dict[str, float], float, float, list[str]]:
    weights = _effective_weights(usable, configured_weights)
    score_5d = 0.0
    baseline_20d = 0.0
    reason_rows: list[tuple[float, str, str]] = []
    for name in usable:
        component = components[name]
        weight = weights[name]
        contribution_5d = float(component["score_5d"]) * weight
        contribution_20d = float(component["score_20d"]) * weight
        component["effective_weight"] = weight
        component["contribution_5d"] = contribution_5d
        component["contribution_20d"] = contribution_20d
        score_5d += contribution_5d
        baseline_20d += contribution_20d
        reason_rows.append(
            (
                -abs(contribution_5d),
                name,
                _component_reason(name, component, contribution_5d),
            )
        )
    reasons = [row[2] for row in sorted(reason_rows)[:3]]
    return weights, score_5d, baseline_20d, reasons


def _empty_composite() -> dict[str, Any]:
    return {
        "status": "insufficient_data",
        "score_5d": None,
        "baseline_20d": None,
        "change": None,
        "temperature": None,
        "label": None,
        "effective_weights": {},
        "reasons": [],
    }


def _composite_from_usable(
    components: dict[str, dict[str, Any]],
    usable: list[str],
    *,
    configured_weights: Mapping[str, float],
    label_classifier: LabelClassifier,
) -> dict[str, Any]:
    if len(usable) < 2:
        return _empty_composite()
    weights, score_5d, baseline_20d, reasons = _score_usable_components(
        components,
        usable,
        configured_weights,
    )
    change = score_5d - baseline_20d
    temperature = (
        "warming" if change >= 10.0 else "cooling" if change <= -10.0 else "stable"
    )
    status = "ready" if len(usable) == len(configured_weights) else "partial"
    return {
        "status": status,
        "score_5d": score_5d,
        "baseline_20d": baseline_20d,
        "change": change,
        "temperature": temperature,
        "label": label_classifier(score_5d),
        "effective_weights": weights,
        "reasons": reasons,
    }


def _news_articles_5d(components: Mapping[str, Mapping[str, Any]]) -> float | None:
    coverage = components["news"].get("coverage")
    return (
        _finite_float(coverage.get("articles_5d"))
        if isinstance(coverage, Mapping)
        else None
    )


def _meets_high_confidence_gates(
    components: Mapping[str, Mapping[str, Any]],
    usable: Sequence[str],
    fresh_names: Sequence[str],
    news_articles_5d: float | None,
) -> bool:
    price_coverage = _finite_float(components["price"].get("coverage_ratio_5d"))
    flow_valid_days = _finite_float(components["fund_flow"].get("valid_days_5d"))
    return (
        len(usable) == 3
        and len(fresh_names) == 3
        and news_articles_5d is not None
        and news_articles_5d >= 5.0
        and price_coverage is not None
        and price_coverage >= 0.80
        and flow_valid_days is not None
        and flow_valid_days >= 4.0
    )


def _component_confidence(
    components: Mapping[str, Mapping[str, Any]],
    *,
    usable: Sequence[str],
    fresh_names: Sequence[str],
    has_source_errors: bool,
) -> tuple[str | None, list[str]]:
    if len(usable) < 2:
        return None, [
            "confidence unavailable: fewer than two usable fresh components"
        ]
    coverage_downgrades = _coverage_downgrades(components, usable)
    if has_source_errors or coverage_downgrades:
        warnings = [
            f"confidence downgraded to low: {reason}"
            for reason in coverage_downgrades
        ]
        if has_source_errors:
            warnings.append(
                "confidence downgraded to low: required-source errors present"
            )
        return "low", warnings
    news_articles_5d = _news_articles_5d(components)
    if _meets_high_confidence_gates(
        components, usable, fresh_names, news_articles_5d
    ):
        return "high", []
    reason = (
        "fewer than three complete fresh components"
        if len(usable) < 3
        else "news has "
        f"{'missing' if news_articles_5d is None else int(news_articles_5d)} "
        "articles in 5d; high confidence requires 5"
    )
    return "medium", [f"confidence downgraded to medium: {reason}"]


def _normalized_source_errors(source_errors: Sequence[str]) -> list[str]:
    return sorted(
        {str(error).strip() for error in source_errors if str(error).strip()}
    )


def _freshness_source_error_names(
    freshness: Mapping[str, Any], configured_weights: Mapping[str, float]
) -> list[str]:
    return [
        name
        for name in configured_weights
        if _freshness_has_source_error(_freshness_entry(freshness, name))
    ]


def combine_sentiment_components_impl(
    components: Mapping[str, Mapping[str, Any]],
    *,
    freshness: Mapping[str, Any],
    source_errors: Sequence[str],
    configured_weights: Mapping[str, float],
    methodology_version: str,
    label_classifier: LabelClassifier,
) -> dict[str, Any]:
    normalized, warnings, usable, fresh_names = _select_usable_components(
        components,
        freshness=freshness,
        configured_weights=configured_weights,
    )
    normalized_errors = _normalized_source_errors(source_errors)
    for error in normalized_errors:
        _append_unique(warnings, f"source error: {error}")
    composite = _composite_from_usable(
        normalized,
        usable,
        configured_weights=configured_weights,
        label_classifier=label_classifier,
    )
    freshness_errors = _freshness_source_error_names(
        freshness, configured_weights
    )
    confidence, confidence_warnings = _component_confidence(
        normalized,
        usable=usable,
        fresh_names=fresh_names,
        has_source_errors=bool(normalized_errors or freshness_errors),
    )
    for warning in confidence_warnings:
        _append_unique(warnings, warning)
    return {
        "methodology_version": methodology_version,
        "status": composite["status"],
        "score_5d": composite["score_5d"],
        "baseline_20d": composite["baseline_20d"],
        "change": composite["change"],
        "temperature": composite["temperature"],
        "label": composite["label"],
        "confidence": confidence,
        "components": normalized,
        "effective_weights": composite["effective_weights"],
        "reasons": composite["reasons"],
        "warnings": warnings,
    }
