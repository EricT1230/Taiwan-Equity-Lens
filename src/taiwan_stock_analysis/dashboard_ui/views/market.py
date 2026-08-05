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


# Final polish C6: full float precision (not the 1dp _score_text/
# _signed_score_text used for the visible cell) so the client sort comparator
# (page_script.py's sentimentCardValue -> Number(raw)) doesn't tie on two
# industries that only differ past the first decimal (e.g. 55.44 vs 55.38 ->
# both render "55.4"), while the server already orders by full precision
# (_industry_sort_key). str() of a float is Python's shortest round-trip
# repr, so this stays exact without any manual formatting.
def _score_attr_text(value: Any) -> str:
    number = _finite(value)
    return str(number) if number is not None else "-"


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


def _text_items(value: Any) -> list[str]:
    # Ported from dashboard.py:_market_intelligence_text_items (deleted at
    # da4a47a^).
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


# Final polish C7 (spec §3.2 "依據與警告" collapsible): sentiment.reasons and
# the forecast/turning-risk warnings are computed by the pipeline
# (_sentiment_composite.py's reasons, sentiment_forecast.py's warnings, e.g.
# "projection requires at least 20 valid snapshot days") but were dropped by
# this view entirely. Ported wording + structure from dashboard.py:
# _market_intelligence_sentiment_details (deleted at da4a47a^) -- same
# "依據與警告"/"主要依據"/"警告" labels, same top-3-reasons cap, same
# dedupe-across-sources behavior for warnings.
def _sentiment_details_block(
    sentiment: dict[str, Any],
    forecast: dict[str, Any],
    turning_risk: dict[str, Any],
) -> str:
    reasons = _text_items(sentiment.get("reasons"))[:3]
    warnings: list[str] = []
    for source in (sentiment, forecast, turning_risk):
        for warning in _text_items(source.get("warnings")):
            if warning not in warnings:
                warnings.append(warning)
    reasons_html = "".join(f"<li>{esc(reason)}</li>" for reason in reasons) or "<li>-</li>"
    warnings_html = "".join(f"<li>{esc(warning)}</li>" for warning in warnings) or "<li>-</li>"
    return (
        '<details class="mkt-sentiment-details">'
        "<summary>依據與警告</summary>"
        f"<h4>主要依據</h4><ul>{reasons_html}</ul>"
        f"<h4>警告</h4><ul>{warnings_html}</ul>"
        "</details>"
    )


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
        f' data-sentiment-score="{esc(_score_attr_text(score))}"'
        f' data-sentiment-change="{esc(_score_attr_text(change))}"'
        f' data-peak-risk="{esc(_score_attr_text(turning_risk.get("peak_risk")))}"'
        f' data-trough-risk="{esc(_score_attr_text(turning_risk.get("trough_risk")))}"'
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
        f"{_sentiment_details_block(sentiment, forecast, turning_risk)}"
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


def _is_synthetic_market_report(report: dict[str, Any]) -> bool:
    for key in ("news", "fund_flows"):
        for row in _rows(report, key):
            source = str(row.get("source") or "").casefold()
            url = str(row.get("url") or "").casefold()
            if "synthetic" in source or "example.com" in url:
                return True
    metadata = _dict(report.get("run_metadata"))
    inputs = _dict(metadata.get("inputs"))
    return any(
        str(value or "").replace("\\", "/").casefold().startswith("examples/")
        for value in inputs.values()
    )


def _is_synthetic_trend_report(report: dict[str, Any]) -> bool:
    paths = (
        report.get("research_path"),
        report.get("price_history_path"),
    )
    if not any(str(value or "").strip() for value in paths):
        return True
    return any(
        str(value or "").replace("\\", "/").casefold().startswith("examples/")
        for value in paths
    )


def _sentiment_section(
    items: dict[str, Any],
    *,
    suppress_synthetic: bool = False,
) -> str:
    report = _first_report(items.get("market_intelligence_reports"))
    if suppress_synthetic and _is_synthetic_market_report(report):
        return (
            '<section class="mkt-section" data-market-sentiment-section="true">'
            "<h2>產業情緒模型</h2>"
            '<p class="mkt-empty">已封鎖合成示範資料。完成正式歷史行情與授權新聞同步後，'
            "才會顯示 5D／20D 情緒、貢獻拆解與轉折風險。</p>"
            "</section>"
        )
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


def _rotation_section(
    items: dict[str, Any],
    *,
    suppress_synthetic: bool = False,
) -> str:
    report = _first_report(items.get("industry_trend_reports"))
    if suppress_synthetic and _is_synthetic_trend_report(report):
        return (
            '<section class="mkt-section" data-market-rotation-section="true">'
            "<h2>產業輪動</h2>"
            '<p class="mkt-empty">已封鎖範例價格序列。上方地圖仍使用本次連線取得的研究池行情；'
            "完整 1D／5D／20D 輪動需由正式歷史行情重新計算。</p>"
            "</section>"
        )
    categories = _rows(report, "categories")[:_MAX_ROTATION_CARDS]
    body = "".join(_rotation_card(row) for row in categories) or '<p class="mkt-empty">尚未產生產業輪動報告。</p>'
    return f'<section class="mkt-section" data-market-rotation-section="true"><h2>產業輪動</h2>{body}</section>'


def _industry_map(items: dict[str, Any]) -> str:
    sentiment_report = _first_report(items.get("market_intelligence_reports"))
    trend_report = _first_report(items.get("industry_trend_reports"))
    sentiment_by_category = {
        str(row.get("category") or "-"): row
        for row in _rows(sentiment_report, "industries")
    }
    trend_by_category = {
        str(row.get("category") or "-"): row
        for row in _rows(trend_report, "categories")
    }
    categories = sorted(set(sentiment_by_category) | set(trend_by_category))
    tiles: list[tuple[float, str]] = []
    for category in categories:
        industry = sentiment_by_category.get(category, {})
        trend = trend_by_category.get(category, {})
        sentiment = _dict(industry.get("sentiment"))
        score = _finite(sentiment.get("score_5d"))
        return_5d = _finite(trend.get("average_return_5d"))
        stock_count = len(industry.get("stock_ids")) if isinstance(industry.get("stock_ids"), list) else 0
        heat = max(-10.0, min(10.0, return_5d if return_5d is not None else 0.0))
        heat_tone = "positive" if heat > 0 else "negative" if heat < 0 else "neutral"
        sort_score = score if score is not None else float("-inf")
        tile = (
            f'<button type="button" class="industry-tile industry-tile-{heat_tone}"'
            f' style="--heat:{abs(heat) / 10:.3f}" data-industry-tile="{esc(category)}">'
            f'<span class="industry-tile-name">{esc(category)}</span>'
            f'<strong class="mono" data-live-industry-score="true">{esc(_score_text(score))}</strong>'
            f'<span class="mono {_signed_class(return_5d)}" data-live-industry-change="true">'
            f'{esc(_percent_text(return_5d))} / 5D</span>'
            f'<small data-live-industry-count="true">{esc(stock_count)} 檔 · 點擊查看細節</small>'
            "</button>"
        )
        tiles.append((sort_score, tile))
    tiles.sort(key=lambda item: item[0], reverse=True)
    body = "".join(tile for _, tile in tiles) or (
        '<p class="mkt-empty">尚未取得可驗證的產業分類與報酬資料。</p>'
    )
    return (
        '<section class="industry-map" data-industry-map="true">'
        '<header class="product-page-head"><div><span class="desk-kicker">SECTOR MAP / 挖題材</span>'
        '<h1>產業地圖</h1><p>用產業溫度、5D 報酬與法人流向辨識輪動，不把單一紅綠色當成結論。</p></div>'
        '<div><div class="industry-map-legend"><span><i class="negative"></i>走弱</span>'
        '<span><i class="neutral"></i>中性</span><span><i class="positive"></i>走強</span></div>'
        '<p class="industry-map-summary" role="status" aria-live="polite">'
        '<strong data-industry-map-status="true">研究池產業</strong>'
        f' · <span data-industry-map-count="true">{len(categories)}</span> 個分類</p></div></header>'
        f'<div class="industry-map-grid" data-industry-map-grid="true">{body}</div>'
        '<p class="industry-map-note" data-live-industry-note="true">'
        '方塊顏色＝5D 產業報酬；大字＝產業情緒分數。'
        "自動分類仍需搭配官方產業代碼與版本化價值鏈人工校對。</p>"
        "</section>"
    )


def render_market_view(
    items: dict[str, Any],
    *,
    live_api_enabled: bool = False,
) -> str:
    return (
        _industry_map(items)
        + _sentiment_section(items, suppress_synthetic=live_api_enabled)
        + _rotation_section(items, suppress_synthetic=live_api_enabled)
    )
