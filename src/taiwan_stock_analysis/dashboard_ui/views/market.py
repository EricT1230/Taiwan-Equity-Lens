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

# Ported from dashboard.py:_market_intelligence_sentiment_status_label.
_STATUS_LABELS = {
    "ready": "資料完整",
    "partial": "資料不完整",
    "insufficient_data": "資料不足",
    "missing": "尚無情緒資料",
}
_STATUS_TONES = {"partial": "warn"}

_DIRECTION_LABELS = {
    "up": "輪動偏強",
    "down": "輪動偏弱",
    "mixed": "輪動分歧",
    "flat": "輪動持平",
    "missing": "市場資料缺口",
}

# Ported from dashboard.py:1268 (_market_intelligence_experimental_status) -- the
# short bilingual marker shown on both the forecast and turning-risk chips, so an
# insufficient-history placeholder reads identically to how the pre-redesign
# dashboard described it.
_EXPERIMENTAL_STATUS_LABELS = {
    "experimental": "experimental / 實驗訊號",
    "insufficient_history": "insufficient history / 歷史資料不足",
    "insufficient_data": "insufficient history / 歷史資料不足",
}
_INSUFFICIENT_STATUSES = {"insufficient_history", "insufficient_data", "missing"}

# New vocabulary -- the old renderer never surfaced turning_risk.direction/window
# (see dashboard.py:1250), spec 3.2 asks for them here. Values are the fixed enum
# produced by sentiment_forecast.py's calculate_turning_risk/_resolve_turning_signal
# (direction: peak/trough/unclear; window: 1_to_3_days/4_to_7_days/unclear).
_TURNING_DIRECTION_LABELS = {"peak": "高點", "trough": "低點", "unclear": "不明朗", "missing": "-"}
_TURNING_WINDOW_LABELS = {
    "1_to_3_days": "1-3 天",
    "4_to_7_days": "4-7 天",
    "unclear": "不明朗",
    "missing": "-",
}

# Ported from dashboard.py:1104 (_market_intelligence_industry_sort_key)'s local
# confidence_order literal -- reused here for the card's data-confidence-order attr.
_CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

# Ported from dashboard.py:1002-1009 (the <select data-industry-sentiment-sort>
# markup inside _market_intelligence_block) -- identical value/label pairs and
# default-selected "score" option.
_SORT_OPTIONS = (
    ("score", "目前 5D 分數"),
    ("change", "升溫／降溫變化"),
    ("peak_risk", "高點風險"),
    ("trough_risk", "低點風險"),
    ("confidence", "信心"),
)

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


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status.replace("_", " ") if status else "-")


def _direction_label(direction: str) -> str:
    return _DIRECTION_LABELS.get(direction, direction or "-")


# Ported from dashboard.py:1268 (_market_intelligence_experimental_status).
def _experimental_status_text(status: str) -> str:
    if status in _EXPERIMENTAL_STATUS_LABELS:
        return _EXPERIMENTAL_STATUS_LABELS[status]
    return status.replace("_", " ") if status != "missing" else "-"


def _turning_direction_label(direction: str) -> str:
    return _TURNING_DIRECTION_LABELS.get(direction, direction.replace("_", " ") if direction else "-")


def _turning_window_label(window: str) -> str:
    return _TURNING_WINDOW_LABELS.get(window, window.replace("_", " ") if window else "-")


# Ported from dashboard.py:1220 (_market_intelligence_interval).
def _interval_text(value: Any) -> str:
    if not isinstance(value, list) or len(value) != 2:
        return ""
    lower = _finite(value[0])
    upper = _finite(value[1])
    if lower is None or upper is None:
        return ""
    return f" [{lower:.1f}, {upper:.1f}]"


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


# Ported from dashboard.py:1230 (_market_intelligence_forecast). insufficient_history
# / insufficient_data / missing all fall back to the same placeholder text the old
# dashboard used, so wording stays identical for the demo's real "insufficient_history"
# forecast payload (verified in .tmp-v053-preview/market-intelligence/
# market_intelligence_report.json).
def _forecast_block(forecast: dict[str, Any]) -> str:
    status = str(forecast.get("status") or "missing")
    status_pill = pill(_experimental_status_text(status), tone="warn")
    if status in _INSUFFICIENT_STATUSES:
        text = "歷史資料不足" if status != "missing" else "-"
    else:
        text = " / ".join(
            (
                f"1D {_score_text(forecast.get('forecast_1d'))}{_interval_text(forecast.get('interval_1d'))}",
                f"5D {_score_text(forecast.get('forecast_5d'))}{_interval_text(forecast.get('interval_5d'))}",
            )
        )
    return f'<div class="mkt-forecast">{status_pill}<p><strong>情緒預測：</strong>{esc(text)}</p></div>'


# Ported from dashboard.py:1250 (_market_intelligence_turning_risk) for the status
# pill / insufficient-history placeholder / "高點 X / 低點 Y" text. The direction and
# window pills are new: the old renderer never surfaced turning_risk.direction/window
# at all, but spec 3.2 asks for "高低點風險" alongside direction/window once real
# values exist.
def _turning_risk_block(turning_risk: dict[str, Any]) -> str:
    status = str(turning_risk.get("status") or "missing")
    status_pill = pill(_experimental_status_text(status), tone="warn")
    if status in _INSUFFICIENT_STATUSES:
        text = "歷史資料不足" if status != "missing" else "-"
        meta_pills = ""
    else:
        peak = _score_text(turning_risk.get("peak_risk"))
        trough = _score_text(turning_risk.get("trough_risk"))
        text = f"高點 {peak} / 低點 {trough}"
        direction = _turning_direction_label(str(turning_risk.get("direction") or "missing"))
        window = _turning_window_label(str(turning_risk.get("window") or "missing"))
        meta_pills = pill(f"方向：{direction}") + pill(f"時間窗：{window}")
    return f'<div class="mkt-forecast">{status_pill}{meta_pills}<p><strong>轉折風險：</strong>{esc(text)}</p></div>'


# Ported from dashboard.py:1002-1009 (see _SORT_OPTIONS above for the exact
# value/label pairs) -- same data-industry-sentiment-sort hook and aria-label so the
# control is discoverable the same way it was pre-redesign. Always rendered (even
# when there are zero industries) to match the old _market_intelligence_block, which
# rendered the select unconditionally ahead of the cards-or-empty-state message.
def _industry_sentiment_sort_control() -> str:
    options = "".join(
        f'<option value="{esc(value)}"{" selected" if value == "score" else ""}>{esc(label)}</option>'
        for value, label in _SORT_OPTIONS
    )
    return (
        '<div class="mkt-sentiment-sort"><label>產業情緒排序'
        f'<select data-industry-sentiment-sort="true" aria-label="產業情緒排序">{options}</select>'
        "</label></div>"
    )


# data-* hooks read by page_script.py's sortSentimentCards(). Values reuse
# _score_text() (unsigned 1dp, "-" when missing/non-finite) so the client's
# NaN-safe Number() parse naturally sorts missing/insufficient-history industries
# last, matching this module's own _industry_sort_key() default-order convention.
def _sentiment_card_attrs(
    category: str,
    status: str,
    score: Any,
    change: Any,
    turning_risk: dict[str, Any],
    confidence: str,
) -> str:
    confidence_order = _CONFIDENCE_ORDER.get(confidence, 0)
    return (
        f' data-sentiment-status="{esc(status)}"'
        f' data-sentiment-category="{esc(category)}"'
        f' data-sentiment-score="{esc(_score_text(score))}"'
        f' data-sentiment-change="{esc(_score_text(change))}"'
        f' data-peak-risk="{esc(_score_text(turning_risk.get("peak_risk")))}"'
        f' data-trough-risk="{esc(_score_text(turning_risk.get("trough_risk")))}"'
        f' data-confidence-order="{esc(confidence_order)}"'
    )


def _sentiment_card(industry: dict[str, Any]) -> str:
    category = str(industry.get("category") or "-")
    sentiment = _dict(industry.get("sentiment"))
    flow = _dict(industry.get("fund_flow"))
    components = _dict(sentiment.get("components"))
    forecast = _dict(sentiment.get("forecast"))
    turning_risk = _dict(sentiment.get("turning_risk"))

    news_c = _finite(_dict(components.get("news")).get("contribution_5d")) or 0.0
    price_c = _finite(_dict(components.get("price")).get("contribution_5d")) or 0.0
    flow_c = _finite(_dict(components.get("fund_flow")).get("contribution_5d")) or 0.0
    contrib_max = max([abs(news_c), abs(price_c), abs(flow_c)], default=1) or 1

    score = sentiment.get("score_5d")
    change = sentiment.get("change")
    change_cls = _signed_class(change)
    status = str(sentiment.get("status") or "missing")
    status_pill = pill(_status_label(status), tone=_STATUS_TONES.get(status, "info"))
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
        f'<span class="mkt-score mono">{esc(_score_text(score))}</span>'
        f'<span class="mkt-delta mono {change_cls}">{esc(_signed_score_text(change))}</span>'
        f'<span class="mkt-baseline">20D 基準 {esc(_score_text(sentiment.get("baseline_20d")))}</span>'
        "</div>"
        f'<div class="mkt-pills">{status_pill}{phase_pill}{confidence_pill}</div>'
        f"{sparkline(_sentiment_history(sentiment))}"
        f'{contribution_bars([("新聞", news_c, contrib_max), ("價格", price_c, contrib_max), ("資金流", flow_c, contrib_max)])}'
        f"{_forecast_block(forecast)}"
        f"{_turning_risk_block(turning_risk)}"
        '<div class="mkt-flow">'
        f'{_flow_row("外資", foreign, flow_max, with_bar=True)}'
        f'{_flow_row("投信", trust, flow_max, with_bar=True)}'
        f'{_flow_row("自營商", dealer, flow_max, with_bar=True)}'
        f'{_flow_row("合計", total, flow_max, with_bar=False)}'
        "</div>"
        f'<p class="mkt-keywords">{keyword_html}</p>'
        f'<ul class="mkt-news">{news_html}</ul>'
    )
    attrs = _sentiment_card_attrs(category, status, score, change, turning_risk, confidence)
    return f'<section class="ui-card"{attrs}><h4>{esc(category)}</h4>{body}</section>'


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
    # data-rotation-card="true": a card-level content marker doctor.py's
    # check_demo_readiness anchors on (see DEMO_INDUSTRY_TREND_HOOK). Unlike the
    # "mkt-rotation-head" substring it replaces, this attribute is only emitted
    # here -- theme.py's CSS never mentions it -- so it is genuinely absent when
    # _rotation_section() falls back to its empty-state placeholder instead of
    # calling this function. Built inline (not via components.card()) to match
    # _sentiment_card()'s own precedent of hand-assembling its <section> tag
    # whenever it needs to attach extra data-* attributes.
    return f'<section class="ui-card" data-rotation-card="true"><h4>{esc(name)}</h4>{body}</section>'


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
    # Cards stay direct children of .mkt-section (server-default order = score desc,
    # matching _industry_sort_key) so the bento grid layout is correct with no JS.
    # page_script.py's sortSentimentCards() re-appends matched [data-sentiment-status]
    # children in the user's chosen order on <select> change -- it never touches the
    # sort control or <h2>, which aren't matched by that selector.
    return (
        '<section class="mkt-section" data-market-sentiment-section="true">'
        "<h2>產業情緒</h2>"
        f"{_industry_sentiment_sort_control()}"
        f"{body}"
        "</section>"
    )


def _rotation_section(items: dict[str, Any]) -> str:
    report = _first_report(items.get("industry_trend_reports"))
    categories = _rows(report, "categories")[:_MAX_ROTATION_CARDS]
    body = "".join(_rotation_card(row) for row in categories) or '<p class="mkt-empty">尚未產生產業輪動報告。</p>'
    return f'<section class="mkt-section" data-market-rotation-section="true"><h2>產業輪動</h2>{body}</section>'


def render_market_view(items: dict[str, Any]) -> str:
    return _sentiment_section(items) + _rotation_section(items)
