from __future__ import annotations

from math import isfinite
from typing import Any

from taiwan_stock_analysis.dashboard_ui.charts import contribution_bars, signed_hbar, sparkline
from taiwan_stock_analysis.dashboard_ui.components import card, esc, pill
from taiwan_stock_analysis.news_urls import safe_http_url

_PHASE_LABELS = {
    "overheating": "過熱",
    "capitulation": "恐慌",
    "recovery": "復甦",
    "ignition": "啟動",
    "expansion": "擴張",
    "distribution": "派發",
    "cooling": "降溫",
    "contraction": "收縮",
    "consolidation": "盤整",
    "insufficient_history": "歷史資料不足",
    "missing": "-",
}

_CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低", "missing": "-"}
_CONFIDENCE_TONES = {"high": "ok", "medium": "info", "low": "warn"}

_DIRECTION_LABELS = {
    "up": "輪動偏強",
    "down": "輪動偏弱",
    "mixed": "輪動分歧",
    "flat": "輪動持平",
    "missing": "市場資料缺口",
}

_MAX_KEYWORDS = 8
_MAX_NEWS = 3
_MAX_ROTATION_CARDS = 8


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _score_text(value: Any) -> str:
    number = _finite(value)
    return f"{number:.1f}" if number is not None else "-"


def _signed_score_text(value: Any) -> str:
    number = _finite(value)
    return f"{number:+.1f}" if number is not None else "-"


def _percent_text(value: Any) -> str:
    number = _finite(value)
    if number is None:
        return "-"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _signed_money_text(value: Any) -> str:
    number = _finite(value)
    return f"{int(number):+,}" if number is not None else "-"


def _signed_class(value: Any) -> str:
    number = _finite(value)
    if not number:
        return ""
    return "up" if number > 0 else "down"


def _phase_label(phase: str) -> str:
    return _PHASE_LABELS.get(phase, phase.replace("_", " ") if phase else "-")


def _confidence_label(confidence: str) -> str:
    return _CONFIDENCE_LABELS.get(confidence, confidence.replace("_", " ") if confidence else "-")


def _direction_label(direction: str) -> str:
    return _DIRECTION_LABELS.get(direction, direction or "-")


def _stock_text(value: Any) -> str:
    if not isinstance(value, list):
        return "-"
    labels: list[str] = []
    for item in value[:3]:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "")
        labels.append(f"{stock_id} {_percent_text(item.get('return_20d'))}".strip())
    return ", ".join(labels) if labels else "-"


def _news_item(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "-")
    url = safe_http_url(row.get("url"))
    if url:
        return f'<li><a href="{esc(url)}">{esc(title)}</a></li>'
    return f"<li>{esc(title)}</li>"


def _flow_row(label: str, value: Any, max_abs: float, *, with_bar: bool) -> str:
    bar_html = signed_hbar(value, max_abs) if with_bar else ""
    number_cls = f"mono {_signed_class(value)}".strip()
    return (
        '<div class="mkt-flow-row">'
        f'<span class="mkt-flow-label">{esc(label)}</span>'
        f"{bar_html}"
        f'<span class="{number_cls}">{esc(_signed_money_text(value))}</span>'
        "</div>"
    )


def _rotation_row(label: str, value: Any, max_abs: float) -> str:
    number_cls = f"mono {_signed_class(value)}".strip()
    return (
        '<div class="mkt-rotation-row">'
        f'<span class="mkt-rotation-label">{esc(label)}</span>'
        f"{signed_hbar(value, max_abs)}"
        f'<span class="{number_cls}">{esc(_percent_text(value))}</span>'
        "</div>"
    )


def _sentiment_history(sentiment: dict[str, Any]) -> list:
    history = sentiment.get("history")
    if isinstance(history, list) and len([v for v in history if _finite(v) is not None]) >= 2:
        return history
    # Today's report snapshot does not carry a scored time series in `items` -- that
    # lives in a separate industry_sentiment_history.csv that the discover step does
    # not load. Fall back to the two points the snapshot does give us so the trend
    # sparkline still renders: 20D baseline -> current 5D score.
    return [v for v in (sentiment.get("baseline_20d"), sentiment.get("score_5d")) if _finite(v) is not None]


def _industry_sort_key(industry: dict[str, Any]) -> tuple[bool, float, str]:
    sentiment = _dict(industry.get("sentiment"))
    score = _finite(sentiment.get("score_5d"))
    return (score is None, -(score if score is not None else 0.0), str(industry.get("category") or "").casefold())


def _sentiment_card(industry: dict[str, Any]) -> str:
    category = str(industry.get("category") or "-")
    sentiment = _dict(industry.get("sentiment"))
    flow = _dict(industry.get("fund_flow"))
    components = _dict(sentiment.get("components"))

    news_c = _finite(_dict(components.get("news")).get("contribution_5d")) or 0.0
    price_c = _finite(_dict(components.get("price")).get("contribution_5d")) or 0.0
    flow_c = _finite(_dict(components.get("fund_flow")).get("contribution_5d")) or 0.0
    contrib_max = max([abs(news_c), abs(price_c), abs(flow_c)], default=1) or 1

    change_cls = _signed_class(sentiment.get("change"))
    phase_pill = pill(_phase_label(str(sentiment.get("cycle_phase") or "missing")))
    confidence = str(sentiment.get("confidence") or "missing")
    confidence_pill = pill(
        f"信心：{_confidence_label(confidence)}", tone=_CONFIDENCE_TONES.get(confidence, "info")
    )

    foreign = flow.get("foreign_net")
    trust = flow.get("investment_trust_net")
    dealer = flow.get("dealer_net")
    total = flow.get("total_net")
    flow_max = max([abs(_finite(v) or 0.0) for v in (foreign, trust, dealer)], default=1) or 1

    keywords = industry.get("top_keywords")
    keyword_html = "".join(
        f'<span class="chip-btn">{esc(kw)}</span>'
        for kw in (keywords[:_MAX_KEYWORDS] if isinstance(keywords, list) else [])
    ) or '<p class="mkt-empty">尚未取得關鍵字。</p>'

    news_rows = industry.get("latest_news")
    news_list = [
        row for row in (news_rows[:_MAX_NEWS] if isinstance(news_rows, list) else []) if isinstance(row, dict)
    ]
    news_html = "".join(_news_item(row) for row in news_list) or "<li>尚無相關新聞。</li>"

    body = (
        '<div class="mkt-sentiment-head">'
        f'<span class="mkt-score mono">{esc(_score_text(sentiment.get("score_5d")))}</span>'
        f'<span class="mkt-delta mono {change_cls}">{esc(_signed_score_text(sentiment.get("change")))}</span>'
        f'<span class="mkt-baseline">20D 基準 {esc(_score_text(sentiment.get("baseline_20d")))}</span>'
        "</div>"
        f'<div class="mkt-pills">{phase_pill}{confidence_pill}</div>'
        f"{sparkline(_sentiment_history(sentiment))}"
        f'{contribution_bars([("新聞", news_c, contrib_max), ("價格", price_c, contrib_max), ("資金流", flow_c, contrib_max)])}'
        '<div class="mkt-flow">'
        f'{_flow_row("外資", foreign, flow_max, with_bar=True)}'
        f'{_flow_row("投信", trust, flow_max, with_bar=True)}'
        f'{_flow_row("自營商", dealer, flow_max, with_bar=True)}'
        f'{_flow_row("合計", total, flow_max, with_bar=False)}'
        "</div>"
        f'<p class="mkt-keywords">{keyword_html}</p>'
        f'<ul class="mkt-news">{news_html}</ul>'
    )
    return card(category, body)


def _rotation_card(category: dict[str, Any]) -> str:
    name = str(category.get("category") or "-")
    direction = str(category.get("direction") or "missing")
    rotation_phase = str(category.get("rotation_phase") or "-")
    changes = [
        ("1D", category.get("average_return_1d")),
        ("5D", category.get("average_return_5d")),
        ("20D", category.get("average_return_20d")),
    ]
    max_abs = max([abs(_finite(value) or 0.0) for _, value in changes], default=1) or 1
    rows_html = "".join(_rotation_row(label, value, max_abs) for label, value in changes)
    leading = _stock_text(category.get("leading_stocks"))
    lagging = _stock_text(category.get("lagging_stocks"))

    body = (
        '<div class="mkt-rotation-head">'
        f"{pill(_direction_label(direction))}"
        f'<span class="mkt-rotation-phase">{esc(rotation_phase)}</span>'
        "</div>"
        f'<div class="mkt-rotation-bars">{rows_html}</div>'
        f'<p class="mkt-rotation-note"><strong>領先：</strong>{esc(leading)}</p>'
        f'<p class="mkt-rotation-note"><strong>落後：</strong>{esc(lagging)}</p>'
    )
    return card(name, body)


def _first_report(reports: Any) -> dict[str, Any]:
    if not isinstance(reports, list) or not reports:
        return {}
    report = reports[0]
    if not isinstance(report, dict) or report.get("error"):
        return {}
    return report


def _rows(container: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = container.get(key)
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, dict)]


def _sentiment_section(items: dict[str, Any]) -> str:
    report = _first_report(items.get("market_intelligence_reports"))
    industries = sorted(_rows(report, "industries"), key=_industry_sort_key)
    body = "".join(_sentiment_card(row) for row in industries) or '<p class="mkt-empty">尚未產生市場情緒報告。</p>'
    return f'<section class="mkt-section" data-market-sentiment-section="true"><h2>產業情緒</h2>{body}</section>'


def _rotation_section(items: dict[str, Any]) -> str:
    report = _first_report(items.get("industry_trend_reports"))
    categories = _rows(report, "categories")[:_MAX_ROTATION_CARDS]
    body = "".join(_rotation_card(row) for row in categories) or '<p class="mkt-empty">尚未產生產業輪動報告。</p>'
    return f'<section class="mkt-section" data-market-rotation-section="true"><h2>產業輪動</h2>{body}</section>'


def render_market_view(items: dict[str, Any]) -> str:
    return _sentiment_section(items) + _rotation_section(items)
