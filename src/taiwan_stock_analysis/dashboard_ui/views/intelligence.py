from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.product_data import (
    as_dict,
    as_list,
    finite,
    market_snapshot,
    news_rows,
    research_rows,
)
from taiwan_stock_analysis.news_urls import safe_http_url


def _score(value: Any) -> str:
    number = finite(value)
    return f"{number:.0f}" if number is not None else "-"


def _news_card(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "未命名事件")
    summary = str(row.get("summary") or "尚無摘要")
    url = safe_http_url(row.get("url"))
    source = str(row.get("source") or "來源未標示")
    published = str(row.get("published_at") or "時間未標示")[:16].replace("T", " ")
    stocks = [
        str(value)
        for value in as_list(row.get("matched_stock_ids"))
        if str(value).strip()
    ]
    categories = [
        str(value)
        for value in as_list(row.get("matched_categories"))
        if str(value).strip()
    ]
    tags = "".join(pill(tag) for tag in [*categories[:2], *stocks[:3]])
    mapped = "true" if stocks or categories else "false"
    title_html = (
        f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a>'
        if url
        else esc(title)
    )
    return (
        f'<article class="intel-news-card" data-intel-news="true" data-intel-mapped="{mapped}">'
        f'<div class="intel-news-meta"><span>{esc(source)}</span><time>{esc(published)}</time></div>'
        f"<h3>{title_html}</h3><p>{esc(summary)}</p>"
        f'<div class="intel-tags">{tags or pill("尚未映射")}</div>'
        '<button type="button" class="desk-link" data-add-note="true">＋ 加到市場筆記</button>'
        "</article>"
    )


def _news_section(items: dict[str, Any]) -> str:
    cards = "".join(_news_card(row) for row in news_rows(items)[:12])
    if not cards:
        cards = '<p class="desk-empty">尚無通過 URL 與時間檢查的新聞／公告資料。</p>'
    return (
        '<section class="intel-news desk-card">'
        '<div class="desk-section-head"><div><span class="desk-kicker">NEWS GRAPH</span>'
        '<h2>新聞與事件</h2></div><div class="intel-news-filter">'
        '<button type="button" class="active" data-intel-news-filter="all" aria-pressed="true">全部</button>'
        '<button type="button" data-intel-news-filter="mapped" aria-pressed="false">已映射</button></div></div>'
        f'<div class="intel-news-grid" data-live-intelligence-news="true">{cards}</div>'
        "</section>"
    )


def _fundamental_card(row: dict[str, Any]) -> str:
    fundamental = as_dict(row.get("fundamental_review"))
    scores = as_dict(fundamental.get("agent_scores"))
    if not scores:
        for name, agent in as_dict(fundamental.get("agents")).items():
            score = finite(as_dict(agent).get("score"))
            if score is not None:
                scores[name] = score
    mapped_scores = (
        ("護城河", scores.get("buffett_moat")),
        ("基本面", scores.get("fundamental_quality")),
        ("風險韌性", scores.get("bear_case_risk")),
        ("估值安全", scores.get("valuation_margin_of_safety")),
    )
    score_html = "".join(
        '<div class="intel-factor">'
        f'<span>{esc(label)}</span><strong class="mono">{esc(_score(value))}</strong>'
        f'<i style="--factor:{max(0.0, min(100.0, finite(value) or 0.0)):.2f}"></i></div>'
        for label, value in mapped_scores
    )
    risks = str(row.get("key_risks") or "尚未建立風險條件")
    thesis = str(row.get("thesis") or "尚未建立研究假設")
    state = str(row.get("research_state") or "watching")
    return (
        '<article class="intel-fund-card" data-demo-fundamental-card="true">'
        '<header><div>'
        f'<span class="mono">{esc(row.get("stock_id") or "-")}</span>'
        f'<h3>{esc(row.get("company_name") or "-")}</h3></div>{pill(state)}</header>'
        f'<p class="intel-thesis">{esc(thesis)}</p>'
        f'<div class="intel-factors">{score_html}</div>'
        f'<details><summary>風險與待確認</summary><p>{esc(risks)}</p></details>'
        "</article>"
    )


def _fundamentals(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    rows = research_rows(items)[:6]
    cards = "".join(_fundamental_card(row) for row in rows)
    if not cards:
        cards = '<p class="desk-empty">尚無財報研究摘要。</p>'
    return (
        '<section class="intel-fundamentals desk-card"'
        ' data-live-fundamentals-section="true">'
        '<div class="desk-section-head"><div><span class="desk-kicker">FUNDAMENTALS</span>'
        '<h2>財報與研究摘要</h2></div><span class="desk-section-note">'
        '<span data-live-fundamentals-status="true" data-production-state="DEMO">'
        f'研究資料：{esc(snapshot["mode_label"])} · 分數只代表檢查完成度與規則結果'
        "</span>"
        "</span></div>"
        f'<div class="intel-fund-grid" data-live-fundamentals-grid="true"'
        f' data-demo-fundamentals="true">{cards}</div>'
        '<div class="screen-pagination">'
        '<button type="button" data-live-fundamentals-more="true" hidden>顯示更多</button>'
        f'<span data-live-fundamentals-count="true">{len(rows)} / {len(rows)}</span>'
        "</div>"
        "</section>"
    )


def _notes(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    return (
        '<aside class="intel-notes desk-card">'
        '<div class="desk-section-head"><div><span class="desk-kicker">YOUR NOTEBOOK</span>'
        '<h2>市場筆記</h2></div><span class="intel-save-state" data-note-state="true"'
        ' role="status" aria-live="polite">本機儲存</span></div>'
        '<label for="market-note">今天看到什麼？什麼會讓你的假設失效？</label>'
        '<textarea id="market-note" data-market-note="true" '
        'placeholder="例：AI 伺服器題材升溫，但法人流向與產業廣度尚未同步。先觀察，不急著下結論。"></textarea>'
        '<div class="intel-note-template">'
        '<strong>建議結構</strong><ol><li>觀察到的事實</li><li>資料來源與時間</li>'
        '<li>目前推論</li><li>反證與下一步</li></ol></div>'
        '<p>目前市場狀態：'
        f'<strong data-live-note-regime="true">{esc(snapshot["regime"])}</strong> · '
        f'<span data-live-note-as-of="true">{esc(snapshot["as_of"])}</span></p>'
        "</aside>"
    )


def render_intelligence_view(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    return (
        '<section class="intel-view" data-intelligence-view="true">'
        '<header class="product-page-head"><div><span class="desk-kicker">INTELLIGENCE / 驗證題材</span>'
        '<h1>市場情報</h1><p>把新聞、財報、產業與自己的假設放在同一個證據鏈。</p></div>'
        f'<div class="product-head-status"><span data-live-intelligence-mode="true">'
        f'{pill(snapshot["mode_label"], tone="ok" if snapshot["mode"] == "official" else "warn")}</span>'
        f'<span>最新事件 <strong class="mono" data-live-intelligence-as-of="true">'
        f'{esc(snapshot["as_of"])}</strong></span></div></header>'
        '<div class="intel-layout">'
        f"{_news_section(items)}"
        f"{_notes(items)}"
        f"{_fundamentals(items)}"
        "</div>"
        "</section>"
    )
