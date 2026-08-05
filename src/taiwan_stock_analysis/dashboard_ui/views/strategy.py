from __future__ import annotations

from typing import Any

from taiwan_stock_analysis.dashboard_ui.components import esc, pill
from taiwan_stock_analysis.dashboard_ui.product_data import finite, market_snapshot


_PLAYBOOKS = (
    {
        "key": "focus",
        "label": "市場焦點",
        "tone": "bull",
        "fit": ("偏多擴散", "輪動震盪"),
        "goal": "找出資金、量能與題材同步的主流研究候選。",
        "requires": ("產業溫度前段", "5D 報酬為正", "法人流向未背離"),
        "invalid": "上榜過久、爆量不漲，或大盤／櫃買狀態轉弱。",
    },
    {
        "key": "continuation",
        "label": "動能續攻",
        "tone": "bull",
        "fit": ("偏多擴散",),
        "goal": "檢查強勢產業內，是否仍有可驗證的營收與籌碼延續。",
        "requires": ("短中期趨勢同向", "量能有序放大", "基本面沒有新缺口"),
        "invalid": "量價背離、跌破研究門檻，或新財報推翻原假設。",
    },
    {
        "key": "pullback",
        "label": "回測觀察",
        "tone": "mixed",
        "fit": ("輪動震盪", "分歧觀察"),
        "goal": "追蹤近期強勢但進入整理的標的，不把回檔直接解讀成機會。",
        "requires": ("中期結構未破壞", "回檔量縮", "產業廣度尚未崩解"),
        "invalid": "關鍵趨勢跌破且量能放大，或同產業全面轉弱。",
    },
    {
        "key": "risk",
        "label": "風險雷達",
        "tone": "bear",
        "fit": ("偏空收縮", "分歧觀察", "資料不足", "資料已過期"),
        "goal": "優先找出弱勢、處置、資料缺口與 thesis breaker。",
        "requires": ("弱勢排名", "風險條件", "資料品質與來源時間"),
        "invalid": "風險證據消失且市場廣度、法人與趨勢重新同步。",
    },
)


def _playbook(snapshot: dict[str, Any], row: dict[str, Any]) -> str:
    is_fit = snapshot["regime"] in row["fit"]
    tone = "ok" if is_fit else "info"
    status = "符合目前盤勢" if is_fit else "備用情境"
    requirements = "".join(f"<li>{esc(value)}</li>" for value in row["requires"])
    return (
        f'<article class="strategy-card strategy-{esc(row["tone"])}" data-strategy="{esc(row["key"])}"'
        f' data-live-strategy-family="{esc(row["tone"])}">'
        f'<header><span class="strategy-icon">{esc(row["label"][:1])}</span>'
        f'<div><h3>{esc(row["label"])}</h3><span data-live-strategy-fit="true">'
        f'{pill(status, tone=tone)}</span></div></header>'
        f'<p>{esc(row["goal"])}</p><strong>啟用前提</strong><ul>{requirements}</ul>'
        f'<div class="strategy-invalid"><span>失效條件</span><p>{esc(row["invalid"])}</p></div>'
        "</article>"
    )


def _matrix(snapshot: dict[str, Any]) -> str:
    breadth = finite(snapshot["breadth"])
    sentiment = finite(snapshot["sentiment"])
    active_x = 1 if sentiment is not None and sentiment >= 20 else 0
    active_y = 1 if breadth is not None and breadth >= 0.5 else 0
    cells = []
    for y in (1, 0):
        for x in (0, 1):
            active = " active" if x == active_x and y == active_y else ""
            label = {
                (0, 1): "廣度尚可／動能偏弱",
                (1, 1): "動能與廣度同步",
                (0, 0): "風險優先",
                (1, 0): "少數權值撐盤",
            }[(x, y)]
            cells.append(f'<div class="strategy-matrix-cell{active}"><strong>{esc(label)}</strong></div>')
    return (
        '<section class="desk-card strategy-matrix">'
        '<div class="desk-section-head"><div><span class="desk-kicker">REGIME MATRIX</span>'
        '<h2>盤勢位置</h2></div><span class="desk-section-note">市場溫度 × 產業廣度</span></div>'
        '<div class="strategy-matrix-grid">'
        f'{"".join(cells)}'
        '<span class="strategy-axis strategy-axis-y">廣度高 ↑</span>'
        '<span class="strategy-axis strategy-axis-x">市場溫度高 →</span></div>'
        f'<p>目前判讀：<strong data-live-strategy-regime="true">{esc(snapshot["regime"])}</strong>。'
        f'<span data-live-strategy-posture="true">{esc(snapshot["posture"])}</span></p>'
        "</section>"
    )


def _execution(snapshot: dict[str, Any]) -> str:
    blockers = int(snapshot["blocker_count"])
    gate_status = str(snapshot["gate_status"] or "missing")
    freshness_ready = (
        snapshot["fresh_total"] > 0
        and snapshot["fresh_count"] == snapshot["fresh_total"]
    )
    research_ready = gate_status == "ready" and freshness_ready and not blockers
    if research_ready:
        gate_step = "研究快照的資料品質與鮮度 Gate 已通過，可進入候選複核"
    elif blockers:
        gate_step = f"研究快照仍有 {blockers} 個資料／研究阻塞，候選交接暫停"
    elif gate_status == "missing":
        gate_step = "研究快照尚無資料品質 Gate，先完成資料同步與覆蓋率檢查"
    else:
        gate_step = f"研究快照 Gate 尚未通過（{gate_status}），候選交接暫停"
    return (
        '<section class="desk-card strategy-execution">'
        '<div class="desk-section-head"><div><span class="desk-kicker">EXECUTION ORDER</span>'
        '<h2>今日執行順序</h2></div></div>'
        '<ol>'
        f'<li><span>01</span><div><strong>確認可用資料</strong>'
        f'<p data-live-strategy-gate="true" '
        f'data-research-gate-ready="{"true" if research_ready else "false"}" '
        f'data-research-gate-message="{esc(gate_step)}">{esc(gate_step)}</p></div></li>'
        f'<li><span>02</span><div><strong>鎖定合適策略</strong><p>目前以「'
        f'<span data-live-strategy-regime="true">{esc(snapshot["regime"])}</span>」對應的 playbook 為主。</p></div></li>'
        '<li><span>03</span><div><strong>建立候選清單</strong><p>每筆必須保留命中原因、來源時間與失效條件。</p></div></li>'
        '<li><span>04</span><div><strong>寫下反證</strong><p>完成新聞、財報、籌碼與產業位置複核後才交接。</p></div></li>'
        "</ol></section>"
    )


def _rules() -> str:
    return (
        '<section class="desk-card strategy-rules">'
        '<div class="desk-section-head"><div><span class="desk-kicker">RULE CONTRACT</span>'
        '<h2>策略必須公開什麼</h2></div></div>'
        '<div class="strategy-rule-grid">'
        '<div><strong>母體與條件</strong><p>股票池、排除條件、門檻與更新頻率。</p></div>'
        '<div><strong>成本與偏誤</strong><p>交易成本、滑價、存活者偏誤與前視偏誤。</p></div>'
        '<div><strong>樣本外驗證</strong><p>回測期間、驗證區間與失效監控。</p></div>'
        '<div><strong>資料版本</strong><p>來源、時間、延遲、缺失狀態與計算版本。</p></div>'
        "</div></section>"
    )


def render_strategy_view(items: dict[str, Any]) -> str:
    snapshot = market_snapshot(items)
    playbooks = "".join(_playbook(snapshot, row) for row in _PLAYBOOKS)
    market_mode_label = f"行情：{snapshot['delivery_status']}"
    research_mode_label = f"研究：{snapshot['mode_label']}"
    return (
        '<section class="strategy-view" data-strategy-view="true">'
        '<header class="product-page-head"><div><span class="desk-kicker">PLAYBOOK / 決定節奏</span>'
        '<h1>市場策略</h1><p>策略是可驗證的研究流程，不是黑箱明牌或自動下單。</p></div>'
        f'<div class="strategy-regime"><span>目前盤勢</span>'
        f'<strong data-live-strategy-regime="true">{esc(snapshot["regime"])}</strong>'
        f'<span data-live-strategy-mode="true">'
        f'{pill(market_mode_label, tone="info")}'
        f"</span>"
        f'<span data-strategy-research-mode="true">'
        f'{pill(research_mode_label, tone="ok" if snapshot["mode"] == "official" else "warn")}'
        f"</span></div></header>"
        f'<div class="strategy-grid">{playbooks}</div>'
        '<div class="strategy-bottom-grid">'
        f"{_matrix(snapshot)}"
        f"{_execution(snapshot)}"
        f"{_rules()}"
        "</div>"
        '<p class="screen-footnote">本頁只提供研究情境、必要條件與失效條件，不提供報酬承諾、部位配置或下單建議。</p>'
        "</section>"
    )
