from __future__ import annotations

from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any, Iterable


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def parse_percent(value: Any) -> float | None:
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", "")
    return finite(value)


def non_negative_int(value: Any) -> int:
    number = finite(value)
    if number is None or number < 0:
        return 0
    return int(number)


def first_valid(rows: Any) -> dict[str, Any]:
    for row in as_list(rows):
        if isinstance(row, dict) and not row.get("error"):
            return row
    return {}


def market_report(items: dict[str, Any]) -> dict[str, Any]:
    return first_valid(items.get("market_intelligence_reports"))


def trend_report(items: dict[str, Any]) -> dict[str, Any]:
    return first_valid(items.get("industry_trend_reports"))


def research_summary(items: dict[str, Any]) -> dict[str, Any]:
    return first_valid(items.get("research_summaries"))


def research_rows(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(research_summary(items).get("items")) if isinstance(row, dict)]


def industry_rows(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(market_report(items).get("industries")) if isinstance(row, dict)]


def trend_rows(items: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(trend_report(items).get("categories")) if isinstance(row, dict)]


def news_rows(items: dict[str, Any]) -> list[dict[str, Any]]:
    report = market_report(items)
    rows = [row for row in as_list(report.get("news")) if isinstance(row, dict)]
    if not rows:
        seen: set[tuple[str, str]] = set()
        for industry in industry_rows(items):
            for row in as_list(industry.get("latest_news")):
                if not isinstance(row, dict):
                    continue
                key = (str(row.get("title") or ""), str(row.get("url") or ""))
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("published_at") or ""), reverse=True)


def _mapped_news_count(items: dict[str, Any]) -> int:
    return sum(
        1
        for row in news_rows(items)
        if any(
            as_list(row.get(key))
            for key in ("matched_stock_ids", "matched_categories", "matched_industries")
        )
    )


def _average(values: Iterable[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return sum(valid) / len(valid) if valid else None


def _date_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "尚未同步"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:16]
    return parsed.strftime("%Y-%m-%d %H:%M")


def delivery_status(value: Any, *, now: datetime | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNAVAILABLE"
    try:
        generated_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "UNAVAILABLE"
    current = now or datetime.now().astimezone()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=current.tzinfo)
    current = current.astimezone(generated_at.tzinfo)
    age = current - generated_at
    if age < -timedelta(minutes=5):
        return "UNAVAILABLE"

    # Static market reports are EOD snapshots. Weekend wall-clock hours must not
    # make a valid Friday close stale before the next completed trading session.
    # Production deployments should replace this weekday fallback with the
    # exchange calendar carried by the licensed data service.
    def latest_completed_weekday(moment: datetime) -> date:
        session_date = moment.date()
        if moment.weekday() >= 5 or (moment.hour, moment.minute) < (13, 40):
            session_date -= timedelta(days=1)
        while session_date.weekday() >= 5:
            session_date -= timedelta(days=1)
        return session_date

    expected_session = latest_completed_weekday(current)
    date_only = "T" not in text and " " not in text
    generated_session = (
        generated_at.date()
        if date_only
        else latest_completed_weekday(generated_at)
    )
    return "EOD" if generated_session >= expected_session else "STALE"


def _source_mode(items: dict[str, Any]) -> tuple[str, str]:
    report = market_report(items)
    sources = {
        str(row.get("source") or "").casefold()
        for row in news_rows(items)
        if isinstance(row, dict)
    }
    if any("synthetic" in source or "fixture" in source for source in sources):
        return "展示快照", "demo"
    source_audit = as_dict(research_summary(items).get("source_audit"))
    audit_text = " ".join(str(value) for value in source_audit.values()).casefold()
    if "fixture" in audit_text or "offline" in audit_text:
        return "離線研究", "offline"
    if report:
        return "官方／匯入資料", "official"
    return "等待資料", "missing"


def market_snapshot(
    items: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    report = market_report(items)
    industries = industry_rows(items)
    trends = trend_rows(items)
    scores = [finite(as_dict(row.get("sentiment")).get("score_5d")) for row in industries]
    sentiment = _average(scores)

    five_day_returns = [finite(row.get("average_return_5d")) for row in trends]
    covered_returns = [value for value in five_day_returns if value is not None]
    breadth = (
        sum(1 for value in covered_returns if value > 0) / len(covered_returns)
        if covered_returns
        else None
    )

    flow_values = [
        finite(as_dict(row.get("fund_flow")).get("total_net"))
        for row in industries
    ]
    available_flow_values = [value for value in flow_values if value is not None]
    flow_total = sum(available_flow_values) if available_flow_values else None
    freshness = as_dict(report.get("freshness"))
    freshness_keys = ("news", "fund_flow", "industry_trend")
    report_fresh_count = sum(
        1
        for key in freshness_keys
        if str(as_dict(freshness.get(key)).get("status") or "") == "fresh"
    )
    gate = as_dict(report.get("quality_gate"))
    source_gate_status = str(gate.get("status") or "missing")
    blocker_count = non_negative_int(gate.get("blocker_count"))
    mode_label, mode = _source_mode(items)
    generated_at = report.get("generated_at") or trend_report(items).get("as_of_date")
    status = delivery_status(generated_at, now=now)
    fresh_count = report_fresh_count if status == "EOD" else 0
    gate_status = (
        source_gate_status
        if source_gate_status != "ready" or status == "EOD"
        else status.casefold()
    )
    temperature = (
        max(0.0, min(100.0, (sentiment + 100.0) / 2.0))
        if sentiment is not None
        else None
    )
    can_interpret = (
        sentiment is not None
        and breadth is not None
        and gate_status == "ready"
        and fresh_count == len(freshness_keys)
    )

    if status == "STALE":
        regime = "資料已過期"
        regime_tone = "missing"
        posture = "這份快照僅供介面展示；請重新同步資料後再判讀市場。"
    elif not can_interpret:
        regime = "資料不足"
        regime_tone = "missing"
        posture = "先完成來源、鮮度與品質閘門，再判讀市場狀態。"
    elif sentiment >= 20 and breadth >= 0.6:
        regime = "偏多擴散"
        regime_tone = "bull"
        posture = "多數產業同步轉強，優先檢查動能延續與過熱風險。"
    elif sentiment > -20 and breadth >= 0.45:
        regime = "輪動震盪"
        regime_tone = "mixed"
        posture = "指數與產業分歧，先選產業、再選個股，降低追價衝動。"
    elif sentiment <= -20 or breadth < 0.35:
        regime = "偏空收縮"
        regime_tone = "bear"
        posture = "弱勢面擴大，先做風險清單與資料複核，不急著建立結論。"
    else:
        regime = "分歧觀察"
        regime_tone = "mixed"
        posture = "多空證據尚未收斂，維持觀察名單並等待確認訊號。"

    return {
        "sentiment": sentiment,
        "temperature": temperature,
        "breadth": breadth,
        "flow_total": flow_total,
        "fresh_count": fresh_count,
        "report_fresh_count": report_fresh_count,
        "fresh_total": len(freshness_keys),
        "gate_status": gate_status,
        "source_gate_status": source_gate_status,
        "blocker_count": blocker_count,
        "delivery_status": status,
        "mode_label": mode_label,
        "mode": mode,
        "as_of": _date_label(generated_at),
        "regime": regime,
        "regime_tone": regime_tone,
        "posture": posture,
        "industry_count": len(industries),
        "news_count": _mapped_news_count(items),
    }


def _agent_score(row: dict[str, Any]) -> float | None:
    fundamental = as_dict(row.get("fundamental_review"))
    direct = finite(fundamental.get("score"))
    if direct is not None:
        return direct
    values = [
        finite(value)
        for value in as_dict(fundamental.get("agent_scores")).values()
    ]
    return _average(values)


def stock_rows(items: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in research_rows(items):
        stock_id = str(row.get("stock_id") or "").strip()
        market = str(row.get("official_market") or "").strip().upper()
        category = str(
            row.get("official_industry_name")
            or row.get("category")
            or "未分類"
        ).strip()
        return_1d = parse_percent(row.get("market_return_1d"))
        return_5d = parse_percent(row.get("market_return_5d"))
        return_20d = parse_percent(row.get("market_return_20d"))
        fundamental = as_dict(row.get("fundamental_review"))
        breakers = [str(value) for value in as_list(fundamental.get("thesis_breakers")) if str(value).strip()]
        tags = {"industry"}
        reasons = {"industry": f"產業分類：{category or '未分類'}"}
        if market in {"US", "NYSE", "NASDAQ", "AMEX"}:
            tags.add("us")
            reasons["us"] = f"已連接市場欄位：{market}"
        if row.get("disposition") or row.get("is_disposition"):
            tags.add("disposition")
            reasons["disposition"] = "官方匯入欄位標示為處置／注意標的"
        if (return_5d is not None and return_5d > 0) and str(row.get("priority") or "") == "high":
            tags.add("bull")
            reasons["bull"] = f"5D 報酬 {return_5d:+.1f}% 且研究優先度 high"
        if (return_5d is not None and return_5d < 0) or breakers:
            tags.add("bear")
            reasons["bear"] = (
                f"Thesis breaker：{breakers[0]}"
                if breakers
                else f"5D 報酬 {return_5d:+.1f}%"
            )
        if tags == {"industry"} and return_20d is not None:
            if return_20d > 0:
                tags.add("bull")
                reasons["bull"] = f"20D 報酬 {return_20d:+.1f}%"
            elif return_20d < 0:
                tags.add("bear")
                reasons["bear"] = f"20D 報酬 {return_20d:+.1f}%"

        rows.append(
            {
                "stock_id": stock_id or "-",
                "company_name": str(row.get("company_name") or stock_id or "-"),
                "market": market or "未確認",
                "category": category or "未分類",
                "priority": str(row.get("priority") or "medium"),
                "research_state": str(row.get("research_state") or "watching"),
                "return_1d": return_1d,
                "return_5d": return_5d,
                "return_20d": return_20d,
                "score": _agent_score(row),
                "volume_signal": str(row.get("market_volume_signal") or "尚無量能資料"),
                "thesis": str(row.get("thesis") or "尚未建立研究假設"),
                "risk": str(row.get("key_risks") or (breakers[0] if breakers else "尚未建立風險條件")),
                "reliability": str(row.get("reliability_status") or "unknown"),
                "tags": sorted(tags),
                "reasons": reasons,
            }
        )
    return rows
