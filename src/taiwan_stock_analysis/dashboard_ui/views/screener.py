from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.product_data import finite, market_snapshot, stock_rows


_FILTERS = (
    ("all", "全部", "研究池所有標的"),
    ("bull", "上漲", "當日漲跌幅大於 0"),
    ("bear", "下跌", "當日漲跌幅小於 0"),
    ("disposition", "處置", "官方處置／注意名單"),
    ("industry", "選產業", "開啟產業下拉選單"),
    ("us", "美股", "官方名錄與 FINRA 場外短售量；價格未連接"),
)


def _percent(value: Any) -> tuple[str, str]:
    number = finite(value)
    if number is None:
        return "-", ""
    sign = "+" if number > 0 else ""
    tone = "up" if number > 0 else "down" if number < 0 else ""
    return f"{sign}{number:.1f}%", tone


def _score(value: Any) -> str:
    number = finite(value)
    return f"{number:.0f}" if number is not None else "-"


def _tag_label(tag: str) -> str:
    return {
        "bull": "當日上漲",
        "bear": "當日下跌",
        "disposition": "處置",
        "industry": "產業",
        "us": "美股",
    }.get(tag, tag)


def _tag_tone(tag: str) -> str:
    return {
        "bull": "ok",
        "bear": "blocked",
        "disposition": "warn",
        "industry": "info",
        "us": "info",
    }.get(tag, "info")


def _row(row: dict[str, Any], *, live_api_enabled: bool = False) -> str:
    if live_api_enabled:
        one_day, one_tone = "--", ""
        five_day, five_tone = "--", ""
        twenty_day, twenty_tone = "--", ""
    else:
        one_day, one_tone = _percent(row["return_1d"])
        five_day, five_tone = _percent(row["return_5d"])
        twenty_day, twenty_tone = _percent(row["return_20d"])
    reasons = dict(row.get("reasons")) if isinstance(row.get("reasons"), dict) else {}
    tags = list(row["tags"])
    if live_api_enabled:
        for tag in ("bull", "bear"):
            reason = str(reasons.get(tag) or "")
            if reason.startswith(("5D 報酬", "20D 報酬")):
                tags = [value for value in tags if value != tag]
                reasons.pop(tag, None)
    badges = "".join(
        pill(_tag_label(tag), tone=_tag_tone(tag))
        for tag in tags
        if tag != "industry" or len(tags) == 1
    )
    reliability = row["reliability"]
    reliability_label = {
        "ok": "資料可用",
        "warning": "需複核",
        "error": "資料錯誤",
        "unknown": "未確認",
    }.get(reliability, reliability)
    reliability_tone = "ok" if reliability == "ok" else "warn"
    tags_text = " ".join(tags)
    searchable = " ".join(
        (
            row["stock_id"],
            row["company_name"],
            row["category"],
            row["thesis"],
            row["risk"],
        )
    ).casefold()
    all_reasons = "｜".join(
        str(reasons[tag])
        for tag in tags
        if tag in reasons and str(reasons[tag]).strip()
    )
    reason_attrs = "".join(
        f' data-reason-{esc(key)}="{esc(value)}"'
        f' data-base-reason-{esc(key)}="{esc(value)}"'
        for key, value in reasons.items()
    )
    return (
        '<article class="screen-row" role="row" data-screener-row="true"'
        f' data-screener-tags="{esc(tags_text)}" data-base-screener-tags="{esc(tags_text)}"'
        f' data-search-text="{esc(searchable)}"'
        f' data-stock-key="{esc(row["stock_id"])}" data-live-market="{esc(row["market"])}"'
        f' data-live-category="{esc(row["category"])}"'
        f' data-reason-all="{esc(all_reasons)}"'
        f' data-base-reason-all="{esc(all_reasons)}"'
        f"{reason_attrs}>"
        '<div class="screen-star-cell" role="cell">'
        f'<button type="button" class="screen-star" data-watch-toggle="{esc(row["stock_id"])}"'
        ' aria-pressed="false" aria-label="加入自選">☆</button></div>'
        '<div class="screen-company" role="cell">'
        f'<strong><span class="mono">{esc(row["stock_id"])}</span> {esc(row["company_name"])}</strong>'
        f'<span>{esc(row["market"])} · {esc(row["category"])}</span>'
        '<span class="screen-live-price mono" data-live-stock-price="true">等待行情</span>'
        f'<div class="screen-tags" data-live-stock-tags="true">{badges}</div></div>'
        '<div class="screen-thesis" role="cell">'
        f'<strong data-screener-reason="true">{esc(all_reasons)}</strong>'
        f'<span>研究假設：{esc(row["thesis"])} · {esc(row["volume_signal"])}</span>'
        f'<small>風險證據：{esc(row["risk"])}</small></div>'
        f'<span class="screen-num mono {esc(one_tone)}" role="cell"'
        f' data-live-stock-change="true">{esc(one_day)}</span>'
        f'<span class="screen-num mono {esc(five_tone)}" role="cell">{esc(five_day)}</span>'
        f'<span class="screen-num mono {esc(twenty_tone)}" role="cell">{esc(twenty_day)}</span>'
        f'<span class="screen-score mono" role="cell">{esc(_score(row["score"]))}</span>'
        f'<span class="screen-quality" role="cell">{pill(reliability_label, tone=reliability_tone)}</span>'
        "</article>"
    )


def _filters() -> str:
    buttons = []
    for index, (key, label, description) in enumerate(_FILTERS):
        active = " active" if index == 0 else ""
        pressed = "true" if index == 0 else "false"
        popup = ' aria-haspopup="listbox"' if key == "industry" else ""
        unavailable = (
            ' disabled aria-disabled="true"'
            if key in {"industry", "us"}
            else ""
        )
        label_html = (
            f'<span data-screener-industry-trigger-label="true">{esc(label)}</span>'
            if key == "industry"
            else esc(label)
        )
        buttons.append(
            f'<button type="button" class="screen-filter{active}" data-screener-filter="{esc(key)}"'
            f' aria-pressed="{pressed}"{popup}{unavailable} title="{esc(description)}">'
            f'<strong>{label_html} <span class="screen-filter-count mono"'
            f' data-screener-filter-count="{esc(key)}">-</span></strong>'
            f"<small>{esc(description)}</small></button>"
        )
    return f'<div class="screen-filter-strip">{"".join(buttons)}</div>'


def _breadth_controls(initial_count: int) -> str:
    return (
        '<div class="screen-breadth-controls" data-screener-breadth-controls="true"'
        ' aria-label="全市場篩選條件">'
        '<label>市場<select data-screener-market="true">'
        '<option value="all">全部市場</option>'
        '<option value="TWSE">上市</option>'
        '<option value="TPEx">上櫃</option>'
        '<option value="ESB" disabled>興櫃（尚未連接）</option>'
        '<option value="US" disabled>美股官方名錄／FINRA 短售量（價格未連接）</option>'
        "</select></label>"
        '<label><span data-screener-industry-label="true">產業</span>'
        '<select data-screener-industry="true" disabled>'
        '<option value="all">全部產業</option>'
        "</select></label>"
        '<label>排序<select data-screener-sort="true">'
        '<option value="change_desc">漲跌幅：高到低</option>'
        '<option value="change_asc">漲跌幅：低到高</option>'
        '<option value="volume_desc">成交量：高到低</option>'
        '<option value="short_ratio_desc" disabled>FINRA 場外短售成交比：高到低</option>'
        '<option value="symbol_asc">股票代號</option>'
        "</select></label>"
        '<label>每頁<select data-screener-page-size="true">'
        '<option value="25">25</option><option value="50" selected>50</option>'
        '<option value="100">100</option>'
        "</select></label>"
        '<div class="screen-breadth-status" role="status" aria-live="polite">'
        '<strong data-screener-scope-status="true">研究池範圍</strong>'
        f'<span><span data-screener-universe-count="true">{initial_count}</span> 檔可篩選</span>'
        "</div></div>"
    )


def _methodology_note(
    items: dict[str, Any],
    *,
    live_api_enabled: bool = False,
) -> str:
    snapshot = market_snapshot(items)
    methodology = (
        "1D 由本次行情連線更新；未接妥正式歷史行情前，5D／20D 顯示 --，"
        "上漲／下跌分類只表示本次漲跌，不代表投資建議或研究 thesis。"
        if live_api_enabled
        else "目前分類來自研究池的 1D／5D／20D 報酬、優先度、基本面審查與風險條件；"
    )
    return (
        '<aside class="screen-method">'
        '<div><span class="desk-kicker">WHY THIS STOCK</span>'
        '<strong>每個命中都要能追溯</strong></div>'
        f"<p>{methodology}"
        '「處置」只有在匯入官方處置欄位時才會命中，「美股」只有在美股來源已連接時才會顯示。</p>'
        f'<span data-live-screener-mode="true">'
        f'{pill(snapshot["mode_label"], tone="ok" if snapshot["mode"] == "official" else "warn")}</span>'
        "</aside>"
    )


def render_screener_view(
    items: dict[str, Any],
    *,
    live_api_enabled: bool = False,
) -> str:
    rows = stock_rows(items)
    row_html = "".join(_row(row, live_api_enabled=live_api_enabled) for row in rows)
    if not row_html:
        row_html = '<p class="screen-source-empty">尚無研究池標的，請先匯入 research CSV 或執行官方市場資料同步。</p>'
    return (
        '<section class="screen-view" data-screener-view="true">'
        '<header class="product-page-head"><div><span class="desk-kicker">SCREENER / 找動能</span>'
        '<h1>智慧選股</h1><p>先選盤勢情境，再看命中理由與資料品質。</p></div>'
        '<div class="screen-search-wrap"><label for="screen-search">搜尋股票、產業或題材</label>'
        '<input id="screen-search" type="search" data-screener-search="true" placeholder="例如：2330、半導體、AI">'
        '<span class="mono" role="status" aria-live="polite"><strong data-screener-count="true">0</strong>'
        ' 筆命中</span></div></header>'
        f"{_filters()}"
        f"{_breadth_controls(len(rows))}"
        f"{_methodology_note(items, live_api_enabled=live_api_enabled)}"
        '<div class="screen-table" role="table" aria-label="智慧選股結果">'
        '<div class="screen-row screen-head" role="row"><span role="columnheader">自選</span>'
        '<span role="columnheader">股票／分類</span><span role="columnheader">命中理由</span>'
        '<span role="columnheader">1D</span><span role="columnheader">5D</span>'
        '<span role="columnheader">20D</span><span role="columnheader">研究分</span>'
        '<span role="columnheader">資料</span></div>'
        f'<div data-screener-body="true" role="rowgroup">{row_html}</div>'
        '<div class="screen-empty" data-screener-empty="true" hidden>'
        '<strong>此分類目前沒有已驗證標的</strong>'
        '<p>這是正確的空結果，不會以範例行情補位。請切換條件或完成對應資料源。</p></div>'
        "</div>"
        '<nav class="screen-pagination" data-screener-pagination="true"'
        ' aria-label="選股結果分頁" hidden>'
        '<button type="button" data-screener-page="prev" aria-label="上一頁">上一頁</button>'
        '<span class="mono" data-screener-page-status="true" aria-live="polite">第 1 / 1 頁</span>'
        '<button type="button" data-screener-page="next" aria-label="下一頁">下一頁</button>'
        "</nav>"
        '<p class="screen-footnote">上漲／下跌只表示有價格資料時的當日漲跌。'
        '美股資料為 Nasdaq Trader 官方名錄與 FINRA 場外短售成交量；'
        'FINRA 場外短售成交比不是 short interest，且美股價格來源尚未連接。'
        '此頁是研究工具，不構成買賣建議。</p>'
        "</section>"
    )
