from __future__ import annotations

from taiwan_stock_analysis.models import MetricsByYear


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator


def _safe_percent(numerator: float | None, denominator: float | None) -> float | None:
    result = _safe_divide(numerator, denominator)
    if result is None:
        return None
    return result * 100


def _fair_value(normalized_eps: float | None, target_pe: float | None) -> float | None:
    if normalized_eps is None or target_pe is None:
        return None
    return normalized_eps * target_pe


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _eps_history(metrics_by_year: MetricsByYear, years: list[str]) -> list[float]:
    values = []
    for year in years:
        eps = metrics_by_year.get(year, {}).get("eps")
        if eps is not None and eps > 0:
            values.append(eps)
    return values


def _assumption_labels(
    *,
    eps_history: list[float],
    normalized_eps: float | None,
    eps_growth_rate: float | None,
) -> dict[str, str]:
    eps_base = "unavailable"
    if normalized_eps is not None:
        eps_base = "manual_normalized_eps"
    elif eps_history:
        eps_base = "latest_positive_eps"

    eps_optimistic = "unavailable"
    if eps_history and eps_growth_rate is not None:
        eps_optimistic = "latest_eps_growth_rate"
    elif eps_history:
        eps_optimistic = "max_latest_or_average_eps"

    return {
        "eps_base": eps_base,
        "eps_optimistic": eps_optimistic,
        "target_price_low": "conservative_eps_x_target_pe_low",
        "target_price_base": "base_eps_x_target_pe_base",
        "target_price_high": "optimistic_eps_x_target_pe_high",
    }


def build_eps_scenarios(
    *,
    metrics_by_year: MetricsByYear,
    years: list[str],
    normalized_eps: float | None,
    eps_growth_rate: float | None,
) -> dict[str, float | None]:
    history = _eps_history(metrics_by_year, years)
    latest_eps = history[0] if history else None
    average_eps = sum(history) / len(history) if history else None
    base_eps = normalized_eps if normalized_eps is not None else latest_eps
    optimistic_eps = None
    if latest_eps is not None and eps_growth_rate is not None:
        optimistic_eps = latest_eps * (1 + eps_growth_rate / 100)
    elif latest_eps is not None and average_eps is not None:
        optimistic_eps = max(latest_eps, average_eps)

    conservative_eps = None
    if latest_eps is not None and average_eps is not None:
        conservative_eps = min(latest_eps, average_eps)

    return {
        "conservative": _round(conservative_eps),
        "base": _round(base_eps),
        "optimistic": _round(optimistic_eps),
    }


def _target_price_row(
    *,
    eps: float | None,
    target_pe: float | None,
    price: float | None,
) -> dict[str, float | None]:
    target_price = _fair_value(eps, target_pe)
    price_gap_percent = None
    if target_price is not None and price not in {None, 0}:
        price_gap_percent = (target_price - price) / price * 100
    return {
        "eps": _round(eps),
        "target_pe": _round(target_pe),
        "target_price": _round(target_price),
        "price_gap_percent": _round(price_gap_percent),
    }


def build_target_prices(
    *,
    price: float | None,
    eps_scenarios: dict[str, float | None],
    target_pe_low: float | None,
    target_pe_base: float | None,
    target_pe_high: float | None,
) -> dict[str, dict[str, float | None]]:
    return {
        "low": _target_price_row(
            eps=eps_scenarios.get("conservative"),
            target_pe=target_pe_low,
            price=price,
        ),
        "base": _target_price_row(
            eps=eps_scenarios.get("base"),
            target_pe=target_pe_base,
            price=price,
        ),
        "high": _target_price_row(
            eps=eps_scenarios.get("optimistic"),
            target_pe=target_pe_high,
            price=price,
        ),
    }


def build_scenario_summary(
    *,
    price: float | None,
    eps_scenarios: dict[str, float | None],
    target_prices: dict[str, dict[str, float | None]],
    target_pe_low: float | None,
    target_pe_base: float | None,
    target_pe_high: float | None,
) -> dict[str, object]:
    base_eps = eps_scenarios.get("base")
    fair_value_range = {
        "low": _round(_target_price_value(target_prices, "low")),
        "base": _round(_target_price_value(target_prices, "base")),
        "high": _round(_target_price_value(target_prices, "high")),
    }
    base_target = fair_value_range["base"]
    margin_of_safety = None
    if price is not None and base_target not in {None, 0}:
        margin_of_safety = (base_target - price) / base_target * 100

    confidence = _valuation_confidence(
        price=price,
        base_eps=base_eps,
        target_pe_low=target_pe_low,
        target_pe_base=target_pe_base,
        target_pe_high=target_pe_high,
        fair_value_range=fair_value_range,
    )
    return {
        "fair_value_range": fair_value_range,
        "margin_of_safety_percent": _round(margin_of_safety),
        "valuation_confidence": confidence,
    }


def _target_price_value(target_prices: dict[str, dict[str, float | None]], key: str) -> float | None:
    row = target_prices.get(key, {})
    if not isinstance(row, dict):
        return None
    return row.get("target_price")


def _valuation_confidence(
    *,
    price: float | None,
    base_eps: float | None,
    target_pe_low: float | None,
    target_pe_base: float | None,
    target_pe_high: float | None,
    fair_value_range: dict[str, float | None],
) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    if price is not None:
        score += 25
        reasons.append("price_available")
    if base_eps is not None:
        score += 25
        reasons.append("base_eps_available")
    if all(value is not None for value in [target_pe_low, target_pe_base, target_pe_high]):
        score += 25
        reasons.append("target_pe_range_complete")
    if all(fair_value_range.get(key) is not None for key in ["low", "base", "high"]):
        score += 25
        reasons.append("target_price_range_complete")

    label = "low"
    if score >= 75:
        label = "high"
    elif score >= 50:
        label = "medium"
    return {"score": score, "label": label, "reasons": reasons}


def calculate_valuation(
    *,
    price: float | None,
    eps: float | None,
    book_value_per_share: float | None,
    cash_dividend_per_share: float | None,
    normalized_eps: float | None,
    target_pe_low: float | None,
    target_pe_base: float | None,
    target_pe_high: float | None,
) -> dict[str, float | None]:
    fair_value_low = _fair_value(normalized_eps, target_pe_low)
    fair_value_base = _fair_value(normalized_eps, target_pe_base)
    fair_value_high = _fair_value(normalized_eps, target_pe_high)
    return {
        "price": price,
        "pe": _safe_divide(price, eps),
        "pb": _safe_divide(price, book_value_per_share),
        "dividend_yield": _safe_percent(cash_dividend_per_share, price),
        "fair_value_low": fair_value_low,
        "fair_value_base": fair_value_base,
        "fair_value_high": fair_value_high,
        "price_to_base_fair_value": _safe_percent(price, fair_value_base),
    }


def build_valuation(
    *,
    stock_id: str,
    metrics_by_year: MetricsByYear,
    years: list[str],
    price_inputs: dict[str, float | None] | None,
) -> dict[str, object]:
    if not price_inputs:
        return {}

    latest_year = years[0] if years else None
    latest_metrics = metrics_by_year.get(latest_year or "", {})
    normalized_eps = price_inputs.get("normalized_eps")
    eps_growth_rate = price_inputs.get("eps_growth_rate")
    eps_history = _eps_history(metrics_by_year, years)
    assumptions = _assumption_labels(
        eps_history=eps_history,
        normalized_eps=normalized_eps,
        eps_growth_rate=eps_growth_rate,
    )
    eps_scenarios = build_eps_scenarios(
        metrics_by_year=metrics_by_year,
        years=years,
        normalized_eps=normalized_eps,
        eps_growth_rate=eps_growth_rate,
    )
    if normalized_eps is None:
        normalized_eps = eps_scenarios.get("base")
    target_prices = build_target_prices(
        price=price_inputs.get("price"),
        eps_scenarios=eps_scenarios,
        target_pe_low=price_inputs.get("target_pe_low"),
        target_pe_base=price_inputs.get("target_pe_base"),
        target_pe_high=price_inputs.get("target_pe_high"),
    )
    scenario_summary = build_scenario_summary(
        price=price_inputs.get("price"),
        eps_scenarios=eps_scenarios,
        target_prices=target_prices,
        target_pe_low=price_inputs.get("target_pe_low"),
        target_pe_base=price_inputs.get("target_pe_base"),
        target_pe_high=price_inputs.get("target_pe_high"),
    )

    metrics = calculate_valuation(
        price=price_inputs.get("price"),
        eps=latest_metrics.get("eps"),
        book_value_per_share=price_inputs.get("book_value_per_share"),
        cash_dividend_per_share=price_inputs.get("cash_dividend_per_share"),
        normalized_eps=normalized_eps,
        target_pe_low=price_inputs.get("target_pe_low"),
        target_pe_base=price_inputs.get("target_pe_base"),
        target_pe_high=price_inputs.get("target_pe_high"),
    )
    context = _context(metrics)
    return {
        "stock_id": stock_id,
        "latest_year": latest_year,
        "inputs": dict(price_inputs),
        "eps_scenarios": eps_scenarios,
        "target_prices": target_prices,
        "scenario_summary": scenario_summary,
        "assumptions": assumptions,
        "metrics": metrics,
        "context": context,
        "disclaimer": "valuation_context_only: valuation is separated from quality score and is for research context.",
    }


def _context(metrics: dict[str, float | None]) -> str:
    price_to_base = metrics.get("price_to_base_fair_value")
    if price_to_base is None:
        return "估值資料不足，僅保留品質分析。"
    if price_to_base <= 90:
        return "高品質且價格低於基準情境，可進一步研究估值假設。"
    if price_to_base <= 110:
        return "價格接近基準情境，品質與估值大致匹配。"
    return "價格高於基準情境，需確認成長假設是否足以支撐。"
