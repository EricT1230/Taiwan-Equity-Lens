from __future__ import annotations

from typing import Any


NON_ADVICE_NOTICE = (
    "research_workflow_support_only: expert review outputs are not investment advice, "
    "buy/sell/hold advice, target-price promises, or position-sizing guidance."
)


def build_fundamental_review(
    *,
    stock_id: str,
    research_row: dict[str, str],
    analysis_payload: dict[str, Any] | None,
    source_status: str,
    reliability_status: str,
) -> dict[str, Any]:
    if analysis_payload is None:
        return _missing_review(stock_id, source_status=source_status)

    years = _clean_years(analysis_payload.get("years"))
    latest_year = years[0] if years else ""
    metrics = _metrics_for_year(analysis_payload, latest_year)
    valuation = analysis_payload.get("valuation") if isinstance(analysis_payload.get("valuation"), dict) else {}

    agents = {
        "buffett_moat": _buffett_moat_review(metrics=metrics, years=years, research_row=research_row),
        "fundamental_quality": _fundamental_quality_review(
            metrics=metrics,
            years=years,
            source_status=source_status,
            reliability_status=reliability_status,
        ),
        "bear_case_risk": _bear_case_review(metrics=metrics, valuation=valuation, research_row=research_row),
        "valuation_margin_of_safety": _valuation_review(valuation=valuation, source_status=source_status),
    }
    agent_scores = {
        name: agent.get("score")
        for name, agent in agents.items()
        if isinstance(agent.get("score"), int)
    }
    score = round(sum(agent_scores.values()) / len(agent_scores)) if agent_scores else None
    thesis_breakers = _collect_unique(
        breaker
        for agent in agents.values()
        for breaker in _string_list(agent.get("thesis_breakers"))
    )
    questions = _collect_unique(
        question
        for agent in agents.values()
        for question in _string_list(agent.get("questions"))
    )
    verdict = _verdict(score=score, thesis_breakers=thesis_breakers, source_status=source_status)

    return {
        "stock_id": stock_id,
        "style": "buffett_value_review",
        "latest_year": latest_year,
        "source_status": source_status,
        "score": score,
        "verdict": verdict,
        "agents": agents,
        "agent_scores": agent_scores,
        "questions": questions,
        "thesis_breakers": thesis_breakers,
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def _missing_review(stock_id: str, *, source_status: str) -> dict[str, Any]:
    return {
        "stock_id": stock_id,
        "style": "buffett_value_review",
        "latest_year": "",
        "source_status": source_status,
        "score": None,
        "verdict": "incomplete",
        "agents": {},
        "agent_scores": {},
        "questions": ["Attach a generated raw analysis JSON before expert review."],
        "thesis_breakers": ["Core financial analysis data is unavailable."],
        "non_advice_notice": NON_ADVICE_NOTICE,
    }


def _buffett_moat_review(*, metrics: dict[str, Any], years: list[str], research_row: dict[str, str]) -> dict[str, Any]:
    checks = [
        _threshold_check("roe", _number(metrics.get("roe")), excellent=20.0, good=12.0, direction="higher"),
        _threshold_check("gross_margin", _number(metrics.get("gross_margin")), excellent=40.0, good=25.0, direction="higher"),
        _threshold_check("free_cash_flow_margin", _number(metrics.get("free_cash_flow_margin")), excellent=15.0, good=5.0, direction="higher"),
        _threshold_check("debt_to_equity", _number(metrics.get("debt_to_equity")), excellent=60.0, good=100.0, direction="lower"),
    ]
    thesis = (research_row.get("thesis") or "").strip()
    moat_evidence_score = 75 if len(thesis) >= 20 else 40 if thesis else None
    checks.append({"name": "moat_evidence", "score": moat_evidence_score, "value": thesis or None})
    score = _average_score(checks)
    questions = []
    thesis_breakers = []
    if len(years) < 3:
        questions.append("Review moat durability manually because fewer than three years of metrics are available.")
    if not thesis:
        thesis_breakers.append("Moat thesis is missing from the research row.")
    if _number(metrics.get("operating_cash_flow_to_net_income")) is not None and _number(metrics.get("operating_cash_flow_to_net_income")) < 80:
        thesis_breakers.append("Operating cash flow conversion is below 80% of net income.")
    return {
        "score": score,
        "grade": _grade(score),
        "moat_durability": _durability(score),
        "checks": checks,
        "questions": questions,
        "thesis_breakers": thesis_breakers,
        "non_advice_notice": True,
    }


def _fundamental_quality_review(
    *,
    metrics: dict[str, Any],
    years: list[str],
    source_status: str,
    reliability_status: str,
) -> dict[str, Any]:
    checks = [
        _threshold_check("profitability_roe", _number(metrics.get("roe")), excellent=20.0, good=12.0, direction="higher"),
        _threshold_check("net_margin", _number(metrics.get("net_margin")), excellent=20.0, good=10.0, direction="higher"),
        _threshold_check("financial_safety_debt_ratio", _number(metrics.get("debt_ratio")), excellent=40.0, good=60.0, direction="lower"),
        _threshold_check(
            "cash_conversion",
            _number(metrics.get("operating_cash_flow_to_net_income")),
            excellent=120.0,
            good=80.0,
            direction="higher",
        ),
    ]
    if reliability_status == "ok" and source_status == "available":
        checks.append({"name": "data_reliability", "score": 100, "value": "ok"})
    elif reliability_status in {"warning", "error"}:
        checks.append({"name": "data_reliability", "score": 40, "value": reliability_status})
    else:
        checks.append({"name": "data_reliability", "score": 55, "value": source_status or "unknown"})

    score = _average_score(checks)
    questions = []
    thesis_breakers = []
    if len(years) < 3:
        questions.append("Add more history before treating quality trends as durable.")
    if _number(metrics.get("net_income")) is not None and _number(metrics.get("operating_cash_flow")) is not None:
        if _number(metrics.get("net_income")) > 0 and _number(metrics.get("operating_cash_flow")) < 0:
            thesis_breakers.append("Net income is positive while operating cash flow is negative.")
    if reliability_status in {"warning", "error"}:
        questions.append("Resolve data reliability warnings before handoff.")
    return {
        "score": score,
        "quality_bucket": _quality_bucket(score),
        "checks": checks,
        "questions": questions,
        "thesis_breakers": thesis_breakers,
        "non_advice_notice": True,
    }


def _bear_case_review(
    *,
    metrics: dict[str, Any],
    valuation: dict[str, Any],
    research_row: dict[str, str],
) -> dict[str, Any]:
    checks = [
        _threshold_check("balance_sheet_resilience", _number(metrics.get("debt_ratio")), excellent=40.0, good=60.0, direction="lower"),
        _threshold_check("cash_flow_resilience", _number(metrics.get("free_cash_flow_margin")), excellent=15.0, good=5.0, direction="higher"),
    ]
    risk_text = (research_row.get("key_risks") or "").strip()
    trigger_text = (research_row.get("watch_triggers") or "").strip()
    checks.append({"name": "risk_disclosure", "score": 100 if risk_text else 40, "value": risk_text or None})
    checks.append({"name": "monitoring_trigger", "score": 100 if trigger_text else 40, "value": trigger_text or None})
    score = _average_score(checks)
    thesis_breakers = []
    questions = []
    if not risk_text:
        thesis_breakers.append("Bear case is missing from the research row.")
    if not trigger_text:
        questions.append("Add watch triggers so the bear case can be monitored.")
    if _valuation_downside_exceeds_upside(valuation):
        thesis_breakers.append("Downside scenario is larger than upside scenario.")
    return {
        "score": score,
        "risk_severity": _risk_severity(score),
        "checks": checks,
        "questions": questions,
        "thesis_breakers": thesis_breakers,
        "non_advice_notice": True,
    }


def _valuation_review(*, valuation: dict[str, Any], source_status: str) -> dict[str, Any]:
    summary = valuation.get("scenario_summary") if isinstance(valuation.get("scenario_summary"), dict) else {}
    confidence = summary.get("valuation_confidence") if isinstance(summary.get("valuation_confidence"), dict) else {}
    margin = _number(summary.get("margin_of_safety_percent"))
    confidence_score = _number(confidence.get("score"))
    checks = [
        {"name": "valuation_confidence", "score": int(confidence_score) if confidence_score is not None else None, "value": confidence.get("label")},
        _threshold_check("margin_of_safety", margin, excellent=25.0, good=15.0, direction="higher"),
    ]
    if source_status != "available":
        checks.append({"name": "source_available", "score": 40, "value": source_status})
    score = _average_score(checks)
    questions = []
    thesis_breakers = []
    if not valuation:
        thesis_breakers.append("Valuation scenario is unavailable.")
    if margin is None:
        questions.append("Review valuation assumptions because margin of safety is unavailable.")
    elif margin < 15:
        thesis_breakers.append("Base-case margin of safety is below the 15% review threshold.")
    return {
        "score": score,
        "valuation_confidence": confidence.get("label") or "insufficient",
        "margin_of_safety_percent": margin,
        "checks": checks,
        "questions": questions,
        "thesis_breakers": thesis_breakers,
        "non_advice_notice": True,
    }


def _threshold_check(name: str, value: float | None, *, excellent: float, good: float, direction: str) -> dict[str, Any]:
    if value is None:
        return {"name": name, "score": None, "value": None}
    if direction == "higher":
        score = 100 if value >= excellent else 75 if value >= good else 40
    else:
        score = 100 if value <= excellent else 75 if value <= good else 40
    return {"name": name, "score": score, "value": round(value, 2)}


def _clean_years(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(year) for year in value if str(year).strip()]


def _metrics_for_year(payload: dict[str, Any], year: str) -> dict[str, Any]:
    metrics_by_year = payload.get("metrics_by_year")
    if not isinstance(metrics_by_year, dict):
        return {}
    metrics = metrics_by_year.get(year)
    return metrics if isinstance(metrics, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _average_score(checks: list[dict[str, Any]]) -> int | None:
    scores = [int(check["score"]) for check in checks if isinstance(check.get("score"), int)]
    return round(sum(scores) / len(scores)) if scores else None


def _grade(score: int | None) -> str:
    if score is None:
        return "incomplete"
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _durability(score: int | None) -> str:
    if score is None:
        return "unproven"
    if score >= 80:
        return "strong"
    if score >= 60:
        return "moderate"
    return "weak"


def _quality_bucket(score: int | None) -> str:
    if score is None:
        return "insufficient_data"
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "mixed"
    return "weak"


def _risk_severity(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "low"
    if score >= 65:
        return "medium"
    if score >= 45:
        return "high"
    return "critical"


def _verdict(*, score: int | None, thesis_breakers: list[str], source_status: str) -> str:
    if source_status != "available":
        return "incomplete"
    if thesis_breakers:
        return "needs_work"
    if score is None:
        return "incomplete"
    if score < 60:
        return "needs_work"
    return "ready_for_manual_review"


def _valuation_downside_exceeds_upside(valuation: dict[str, Any]) -> bool:
    summary = valuation.get("scenario_summary") if isinstance(valuation.get("scenario_summary"), dict) else {}
    prices = summary.get("fair_value_range") if isinstance(summary.get("fair_value_range"), dict) else {}
    low = _number(prices.get("low"))
    base = _number(prices.get("base"))
    high = _number(prices.get("high"))
    if low is None or base is None or high is None:
        return False
    return abs(base - low) > abs(high - base)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _collect_unique(values: Any) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
