from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.product_data import (
    finite,
    industry_rows,
    market_snapshot,
    news_rows,
    research_summary,
    stock_rows,
)
from taiwan_stock_analysis.news_urls import safe_http_url


def _number(value: Any, *, suffix: str = "", digits: int = 0) -> str:
    number = finite(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}{suffix}"


def _signed(value: Any, *, suffix: str = "") -> tuple[str, str]:
    number = finite(value)
    if number is None:
        return "-", ""
    sign = "+" if number > 0 else ""
    tone = "up" if number > 0 else "down" if number < 0 else ""
    return f"{sign}{number:,.0f}{suffix}", tone


def _metric(label: str, value: str, detail: str, *, tone: str = "", key: str = "") -> str:
    value_class = f"desk-metric-value mono {tone}".strip()
    live_attr = f' data-live-metric="{esc(key)}"' if key else ""
    return (
        f'<article class="desk-metric"{live_attr}>'
        f'<span class="desk-metric-label" data-live-metric-label="true">{esc(label)}</span>'
        f'<strong class="{value_class}" data-live-metric-value="true">{esc(value)}</strong>'
        f'<span class="desk-metric-detail" data-live-metric-detail="true">{esc(detail)}</span>'
        "</article>"
    )


def _hero(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    temperature = finite(snapshot["temperature"])
    raw_sentiment = finite(snapshot["sentiment"])
    gauge_value = temperature if temperature is not None else 0.0
    score_text = _number(temperature, digits=0)
    raw_text, _ = _signed(raw_sentiment)
    mode_tone = "ok" if snapshot["mode"] == "official" else "warn"
    return (
        '<section class="desk-hero" data-overview-hero="true">'
        '<div class="desk-hero-copy">'
        '<span class="desk-kicker">TODAY / 先看市場，再看策略</span>'
        f'<div class="desk-title-row"><h1 data-live-regime="true">{esc(snapshot["regime"])}</h1>'
        f'<span data-live-mode-badge="true">{pill(snapshot["mode_label"], tone=mode_tone)}</span></div>'
        f'<p data-live-posture="true">{esc(snapshot["posture"])}</p>'
        '<div class="desk-hero-meta">'
        f'<span>資料時間 <strong class="mono" data-live-as-of="true">{esc(snapshot["as_of"])}</strong></span>'
        f'<span>市場資料 Gate <strong data-live-gate="true">{esc(snapshot["gate_status"])}</strong></span>'
        f'<span>阻塞 <strong class="mono">{esc(snapshot["blocker_count"])}</strong></span>'
        "</div>"
        "</div>"
        f'<div class="desk-gauge" style="--gauge:{gauge_value:.2f}" role="img" data-live-gauge="true"'
        f' aria-label="市場溫度 {esc(score_text)} 分，原始情緒分數 {esc(raw_text)}">'
        '<div class="desk-gauge-ring">'
        f'<strong class="mono" data-live-temperature="true">{esc(score_text)}</strong><span>市場溫度</span>'
        "</div>"
        f'<small data-live-methodology="true">0 冷靜 · 100 過熱 · 原始情緒 {esc(raw_text)}</small>'
        "</div>"
        "</section>"
    )


def _metrics(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    breadth = finite(snapshot["breadth"])
    breadth_text = _number(breadth * 100 if breadth is not None else None, suffix="%")
    flow_text, flow_tone = _signed(snapshot["flow_total"], suffix=" 股")
    industry_detail = f'{snapshot["industry_count"]} 個產業納入計算'
    freshness_text = f'{snapshot["fresh_count"]}/{snapshot["fresh_total"]}'
    return (
        '<section class="desk-metrics" aria-label="市場關鍵指標">'
        f'{_metric("產業廣度", breadth_text, industry_detail, key="taiex")}'
        f'{_metric("法人動能", flow_text, "研究池映射之外資＋投信＋自營商淨股數", tone=flow_tone, key="otc")}'
        f'{_metric("快照狀態", snapshot["delivery_status"], f"{freshness_text} 資料域可用；非即時行情", key="status")}'
        f'{_metric("事件雷達", str(snapshot["news_count"]), "已映射新聞與公告", key="news")}'
        "</section>"
    )


def _top_open_actions(items: dict[str, Any]) -> list[dict[str, str]]:
    summary = research_summary(items)
    queue = summary.get("review_action_queue")
    if not isinstance(queue, list):
        return []
    category_labels = {
        "fundamental_review": "基本面專家",
        "source_audit": "來源稽核",
        "reliability": "資料可靠性",
        "valuation": "估值審查",
        "research_quality": "研究品質",
    }
    actions: list[dict[str, str]] = []
    for stock in queue:
        if not isinstance(stock, dict):
            continue
        for action in stock.get("actions") if isinstance(stock.get("actions"), list) else []:
            if not isinstance(action, dict) or str(action.get("status") or "open") != "open":
                continue
            category = str(action.get("category") or "research_quality")
            actions.append(
                {
                    "stock": str(stock.get("stock_id") or "-"),
                    "company": str(stock.get("company_name") or ""),
                    "expert": category_labels.get(category, category),
                    "message": str(action.get("message") or "完成研究複核"),
                }
            )
            if len(actions) == 3:
                return actions
    return actions


def _flow(items: dict[str, Any]) -> str:
    actions = _top_open_actions(items)
    if actions:
        cards = []
        for index, action in enumerate(actions, start=1):
            identity = " · ".join(
                value for value in (action["expert"], action["stock"], action["company"]) if value
            )
            cards.append(
                '<button type="button" class="desk-flow-step" data-jump-tab="workbench">'
                f'<span class="desk-flow-index">{index:02d}</span>'
                f'<strong>{esc(action["message"])}</strong>'
                f'<small>{esc(identity)}</small><span>前往研究工作台 →</span></button>'
            )
        return (
            '<section class="desk-card desk-flow">'
            '<div class="desk-section-head"><div><span class="desk-kicker">HANDOFF BLOCKERS</span>'
            '<h2>先處理三個交接阻塞</h2></div>'
            '<span class="desk-section-note">依目前研究佇列排序</span></div>'
            f'<div class="desk-flow-steps">{"".join(cards)}</div></section>'
        )
    return (
        '<section class="desk-card desk-flow">'
        '<div class="desk-section-head"><div><span class="desk-kicker">GUIDED FLOW</span>'
        '<h2>今天只做三件事</h2></div>'
        '<span class="desk-section-note">30 秒完成盤前定位</span></div>'
        '<div class="desk-flow-steps">'
        '<button type="button" class="desk-flow-step" data-jump-tab="market">'
        '<span class="desk-flow-index">01</span><strong>看氣氛</strong>'
        '<small>確認多空、廣度與最強產業</small><span>打開產業地圖 →</span></button>'
        '<button type="button" class="desk-flow-step" data-jump-tab="screener">'
        '<span class="desk-flow-index">02</span><strong>找動能</strong>'
        '<small>用多方／空方／處置條件縮小名單</small><span>打開智慧選股 →</span></button>'
        '<button type="button" class="desk-flow-step" data-jump-tab="intelligence">'
        '<span class="desk-flow-index">03</span><strong>驗證題材</strong>'
        '<small>用新聞、財報與筆記完成複核</small><span>打開市場情報 →</span></button>'
        "</div>"
        "</section>"
    )


def _industry_pulse(items: dict[str, Any]) -> str:
    rows = []
    for industry in industry_rows(items):
        sentiment = industry.get("sentiment") if isinstance(industry.get("sentiment"), dict) else {}
        score = finite(sentiment.get("score_5d"))
        change = finite(sentiment.get("change"))
        flow = industry.get("fund_flow") if isinstance(industry.get("fund_flow"), dict) else {}
        total = finite(flow.get("total_net"))
        rows.append((score, str(industry.get("category") or "未分類"), change, total))
    rows.sort(
        key=lambda row: (
            row[0] is not None,
            row[0] if row[0] is not None else float("-inf"),
            row[1],
        ),
        reverse=True,
    )
    cards = []
    for score, category, change, total in rows[:4]:
        change_text, change_tone = _signed(change)
        total_text, total_tone = _signed(total, suffix=" 股")
        cards.append(
            '<article class="desk-pulse-item">'
            f'<div><strong>{esc(category)}</strong><span class="mono">{esc(_number(score, digits=1))}</span></div>'
            f'<p>5D 溫度 <span class="{esc(change_tone)}">{esc(change_text)}</span></p>'
            f'<p>法人淨額 <span class="{esc(total_tone)}">{esc(total_text)}</span></p>'
            "</article>"
        )
    body = "".join(cards) or '<p class="desk-empty">尚無產業情緒資料，請先執行市場資料同步。</p>'
    return (
        '<section class="desk-card desk-pulse">'
        '<div class="desk-section-head"><div><span class="desk-kicker">SECTOR PULSE</span>'
        '<h2>產業溫度排行</h2></div><button type="button" class="desk-link" data-jump-tab="market">查看地圖 →</button></div>'
        f'<div class="desk-pulse-grid" data-live-overview-pulse="true">{body}</div>'
        "</section>"
    )


def _news(items: dict[str, Any]) -> str:
    cards = []
    for row in news_rows(items)[:4]:
        title = str(row.get("title") or "未命名事件")
        summary = str(row.get("summary") or "尚無摘要")
        source = str(row.get("source") or "來源未標示")
        published = str(row.get("published_at") or "時間未標示")[:16].replace("T", " ")
        url = safe_http_url(row.get("url"))
        title_html = (
            f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a>'
            if url
            else esc(title)
        )
        cards.append(
            '<article class="desk-news-item">'
            f'<div class="desk-news-meta"><span>{esc(source)}</span><time>{esc(published)}</time></div>'
            f"<h3>{title_html}</h3><p>{esc(summary)}</p>"
            "</article>"
        )
    body = "".join(cards) or '<p class="desk-empty">尚無可驗證的新聞或公告。</p>'
    return (
        '<section class="desk-card desk-briefing">'
        '<div class="desk-section-head"><div><span class="desk-kicker">MARKET BRIEF</span>'
        '<h2>事件與新聞</h2></div><button type="button" class="desk-link" data-jump-tab="intelligence">全部情報 →</button></div>'
        f'<div class="desk-news-list" data-live-overview-news="true">{body}</div>'
        "</section>"
    )


def _watchlist(items: dict[str, Any]) -> str:
    cards = []
    for row in stock_rows(items)[:5]:
        return_text, tone = _signed(row["return_5d"], suffix="%")
        cards.append(
            f'<article class="desk-watch-item" data-live-watch-symbol="{esc(row["stock_id"])}">'
            f'<span class="desk-watch-symbol mono">{esc(row["stock_id"])}</span>'
            f'<div><strong>{esc(row["company_name"])}</strong><small>{esc(row["category"])}</small></div>'
            f'<span class="desk-watch-return mono {esc(tone)}" data-live-watch-change="true">{esc(return_text)}</span>'
            '<small class="desk-watch-price mono" data-live-watch-price="true">--</small>'
            "</article>"
        )
    body = "".join(cards) or '<p class="desk-empty">研究池尚無標的。</p>'
    return (
        '<section class="desk-card desk-watch">'
        '<div class="desk-section-head"><div><span class="desk-kicker">RESEARCH POOL</span>'
        '<h2>觀察名單</h2></div><button type="button" class="desk-link" data-jump-tab="screener">前往選股 →</button></div>'
        f'<div class="desk-watch-list">{body}</div>'
        "</section>"
    )


def render_overview_view(items: dict[str, Any]) -> str:
    return (
        '<div class="desk-overview">'
        f"{_hero(items)}"
        f"{_metrics(items)}"
        f"{_flow(items)}"
        '<div class="desk-overview-grid">'
        f"{_industry_pulse(items)}"
        f"{_news(items)}"
        f"{_watchlist(items)}"
        "</div>"
        "</div>"
    )
