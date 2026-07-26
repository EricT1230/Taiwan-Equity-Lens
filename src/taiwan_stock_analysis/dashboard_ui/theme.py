from __future__ import annotations

TOKENS: dict[str, str] = {
    "bg": "#050810",
    "panel": "#131f38",
    "panel_deep": "#0d1526",
    "row": "#101a30",
    "topbar": "#0a1120",
    "border": "#223050",
    "border_bright": "#2c3d60",
    "text": "#f2f6fc",
    "text_2": "#c6d4e8",
    "text_3": "#a8bad6",
    "text_muted": "#6b7fa3",
    "text_faint": "#4c5f84",
    "accent": "#2ee0f7",
    "up": "#ff7570",
    "up_fill": "#f54e4e",
    "down": "#45e69a",
    "down_fill": "#34d07e",
    "blocked": "#ff8298",
    "warn": "#ffc94d",
    "ok": "#34d399",
}


def base_css() -> str:
    t = TOKENS
    return f"""
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: {t['bg']}; color: {t['text']};
      font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif; }}
    .mono {{ font-family: "Cascadia Mono", Consolas, "Courier New", monospace; font-variant-numeric: tabular-nums; }}
    a {{ color: {t['accent']}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h4 {{ margin: 0 0 5px; font-size: 14px; color: {t['text_3']}; font-weight: 700; letter-spacing: 1px; }}

    .topbar {{ display: flex; justify-content: space-between; align-items: center; gap: 12px;
      padding: 15px 22px; background: {t['topbar']}; border-bottom: 1px solid {t['border']}; flex-wrap: wrap; }}
    .topbar .brand strong {{ font-size: 19px; }}
    .topbar .brand span {{ color: {t['text_muted']}; font-size: 12px; margin-left: 10px; }}

    .ui-tabs {{ display: flex; gap: 2px; padding: 0 22px; background: {t['topbar']}; border-bottom: 1px solid {t['border']}; }}
    .ui-tab {{ padding: 12px 20px; font-size: 15px; font-weight: 700; color: #94a8c8;
      border-bottom: 2px solid transparent; cursor: pointer; background: none; border-top: none; border-left: none; border-right: none; }}
    .ui-tab.active {{ color: {t['accent']}; border-bottom-color: {t['accent']}; }}
    .ui-panel {{ display: none; padding: 20px 22px 22px; }}
    .ui-panel.active {{ display: block; }}

    .ui-card {{ background: {t['panel']}; border: 1px solid {t['border_bright']}; border-radius: 10px;
      padding: 18px; margin-bottom: 16px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.045); }}
    .ui-card-wide {{ grid-column: 1 / -1; }}

    .ui-pill, .ui-badge {{ display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }}
    .ui-pill {{ border-radius: 6px; padding: 5px 12px; font-size: 13px; border: 1px solid transparent; }}
    .ui-badge {{ border-radius: 6px; padding: 3px 9px; font-size: 12px; }}
    .ui-pill-info, .ui-badge-info {{ background: rgba(148,163,184,0.12); color: {t['text_3']}; border-color: {t['border_bright']}; }}
    .ui-pill-blocked, .ui-badge-blocked {{ background: rgba(244,63,94,0.16); color: {t['blocked']}; border-color: rgba(244,63,94,0.45); }}
    .ui-pill-warn, .ui-badge-warn {{ background: rgba(245,158,11,0.18); color: {t['warn']}; }}
    .ui-pill-ok, .ui-badge-ok {{ background: rgba(52,211,153,0.16); color: {t['ok']}; }}

    .ui-btn {{ display: inline-block; padding: 6px 12px; border-radius: 7px; font-size: 12.5px; font-weight: 700;
      border: 1px solid {t['border_bright']}; background: {t['topbar']}; color: {t['text_2']}; cursor: pointer; }}
    .ui-btn.primary {{ background: rgba(46,224,247,0.12); color: {t['accent']}; border-color: rgba(46,224,247,0.45); }}
    .ui-btn:focus-visible, .ui-tab:focus-visible {{ outline: 3px solid {t['accent']}; outline-offset: 2px; }}

    .up {{ color: {t['up']}; }}
    .down {{ color: {t['down']}; }}

    .chart-spark {{ display: block; margin-top: 12px; }}
    .chart-hbar {{ position: relative; height: 16px; background: #060a14; border-radius: 3px; overflow: hidden; }}
    .chart-hbar-fill {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; width: 0; }}
    .chart-hbar-fill.up {{ background: linear-gradient(90deg, rgba(245,78,78,0.5), {t['up_fill']}); }}
    .chart-hbar-fill.down {{ background: linear-gradient(90deg, rgba(52,208,126,0.5), {t['down_fill']}); }}
    .chart-track {{ height: 9px; border-radius: 4px; background: #060a14; overflow: hidden; }}
    .chart-fill {{ display: block; height: 100%; border-radius: 4px; background: {t['accent']}; width: 0; }}
    .chart-contrib-row {{ display: grid; grid-template-columns: 58px 1fr 70px; align-items: center; gap: 11px;
      font-size: 13.5px; color: {t['text_3']}; margin-top: 9px; }}
    .chart-num {{ text-align: right; font-weight: 700; }}
    .chart-progress {{ height: 10px; background: #060a14; border-radius: 5px; overflow: hidden; }}
    .chart-progress > span {{ display: block; height: 100%; border-radius: 5px;
      background: linear-gradient(90deg, {t['accent']}, {t['ok']}); }}

    .queue {{ border: 1px solid {t['border_bright']}; border-radius: 10px; overflow: hidden; }}
    .queue-row {{ display: grid; grid-template-columns: 34px 72px 56px 120px 130px 1fr 200px;
      align-items: center; gap: 10px; padding: 11px 14px; border-bottom: 1px solid #1c2942;
      font-size: 13.5px; color: {t['text_2']}; background: {t['row']}; }}
    .queue-row.head {{ background: {t['topbar']}; color: {t['text_muted']}; font-size: 12px; letter-spacing: 1px; }}
    .queue-row.next {{ background: rgba(46,224,247,0.07); border-left: 3px solid {t['accent']}; }}
    .queue-row.hidden {{ display: none; }}
    .queue-expand {{ background: {t['panel_deep']}; border-top: 1px solid {t['border']}; padding: 14px; }}
    .queue-evidence {{ display: grid; grid-template-columns: 1fr 1fr 1.6fr; gap: 8px; margin: 8px 0; }}
    .queue-evidence input {{ background: {t['topbar']}; border: 1px solid {t['border_bright']}; border-radius: 7px;
      padding: 8px 10px; color: {t['text_2']}; font-size: 13px; }}

    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 10px 0 12px; }}
    .filters select, .filters input {{ background: {t['topbar']}; color: {t['text_2']};
      border: 1px solid {t['border_bright']}; border-radius: 7px; padding: 7px 11px; font-size: 13.5px; }}
    .chip-btn {{ font-size: 13px; padding: 5px 12px; border-radius: 999px; background: rgba(148,163,184,0.14);
      color: {t['text_2']}; border: 1px solid transparent; font-weight: 700; cursor: pointer; }}
    .chip-btn.blocked {{ background: rgba(244,63,94,0.14); color: {t['blocked']}; border-color: rgba(244,63,94,0.4); }}

    .mini-table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
    .mini-table th {{ text-align: left; color: {t['text_muted']}; font-size: 12px; letter-spacing: 1px;
      padding: 6px 10px; border-bottom: 1px solid {t['border']}; }}
    .mini-table td {{ padding: 8px 10px; color: {t['text_2']}; border-bottom: 1px solid #1c2942; }}
    .table-scroll {{ overflow-x: auto; }}

    .disclaimer {{ color: {t['text_faint']}; font-size: 12px; text-align: center; padding: 18px 22px 24px; }}

    @media (max-width: 900px) {{
      .queue-row {{ grid-template-columns: 1fr; gap: 4px; }}
      .topbar {{ align-items: flex-start; }}
    }}
    """


def view_css() -> str:
    """CSS for the mkt-*/wb-*/out-* classes emitted by dashboard_ui.views (Tasks
    7-9) plus the small set of page-shell-only classes page.py's topbar/tabs
    introduce (Task 10). Kept as a sibling of base_css() -- not merged into it --
    so base_css()'s own selectors (asserted byte-for-byte by ThemeTests) stay
    untouched; page.py embeds `base_css() + view_css()` together in one
    <style> block. Every color below is either a direct TOKENS reference or one
    of the exact translucent rgba(...) tuples base_css() itself already uses for
    the same semantic tone (blocked/warn/ok glow overlays) -- no new stray hex.
    """
    t = TOKENS
    return f"""
    /* -- page shell: topbar meta row + tab backlog badge --------------------- */
    .topbar-status {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
    .topbar-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-left: 3px; }}
    .topbar-dot-ok {{ background: {t['ok']}; box-shadow: 0 0 7px rgba(52,211,153,0.8); }}
    .topbar-dot-warn {{ background: {t['warn']}; box-shadow: 0 0 7px rgba(245,158,11,0.7); }}
    .ui-tab-count {{ font-size: 12px; margin-left: 5px; opacity: 0.85; }}

    /* -- shared section-heading + empty-state conventions --------------------- */
    h2 {{ margin: 26px 0 14px; font-size: 20px; font-weight: 800; color: {t['text']};
      letter-spacing: 0.3px; grid-column: 1 / -1; }}
    .ui-panel > section:first-child h2 {{ margin-top: 0; }}
    .mkt-empty, .wb-empty, .out-empty {{ color: {t['text_muted']}; font-size: 13.5px; margin: 4px 0; }}
    .out-empty-cell {{ text-align: center; color: {t['text_muted']}; padding: 16px; font-size: 13px; }}

    /* -- market view (mkt-*): bento grid of industry/rotation cards ----------- */
    .mkt-section {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 16px; margin: 0 0 6px; }}
    .mkt-section > .ui-card {{ margin-bottom: 0; }}
    .mkt-sentiment-head {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
    .mkt-score {{ font-size: 40px; font-weight: 700; line-height: 1.05; color: {t['text']}; }}
    .mkt-delta {{ font-size: 15px; font-weight: 700; }}
    .mkt-baseline {{ color: {t['text_muted']}; font-size: 13px; }}
    .mkt-pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }}
    .mkt-flow {{ margin-top: 14px; }}
    .mkt-flow-row, .mkt-rotation-row {{ display: grid; grid-template-columns: 64px 1fr 88px;
      align-items: center; gap: 11px; font-size: 14px; color: {t['text_2']}; margin-top: 10px; }}
    .mkt-flow-label, .mkt-rotation-label {{ grid-column: 1; color: {t['text_3']}; font-size: 13.5px; }}
    .mkt-flow-row > :last-child, .mkt-rotation-row > :last-child {{
      grid-column: 3; text-align: right; font-weight: 700; }}
    .mkt-flow .mkt-flow-row:last-child {{ border-top: 1px solid {t['border']}; padding-top: 10px; margin-top: 6px; }}
    .mkt-rotation-bars {{ margin-top: 4px; }}
    .mkt-rotation-head {{ display: flex; align-items: center; justify-content: space-between;
      gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }}
    .mkt-rotation-phase {{ color: {t['text_muted']}; font-size: 13px; }}
    .mkt-rotation-note {{ margin: 6px 0 0; font-size: 13.5px; color: {t['text_3']}; }}
    .mkt-keywords {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 13px 0 0; }}
    .mkt-news {{ list-style: none; margin: 9px 0 0; padding: 0; }}
    .mkt-news li {{ font-size: 14px; color: {t['text_2']}; margin: 7px 0; }}
    /* Sort control (data-industry-sentiment-sort) is a direct child of the
       .mkt-section grid alongside its <h2> and card siblings -- span the full row
       so it doesn't collapse into a single auto-fit column. */
    .mkt-sentiment-sort {{ grid-column: 1 / -1; display: flex; align-items: center;
      gap: 10px; flex-wrap: wrap; margin: -6px 0 2px; }}
    .mkt-sentiment-sort label {{ display: flex; align-items: center; gap: 10px;
      color: {t['text_3']}; font-size: 13px; font-weight: 700; letter-spacing: 0.3px; }}
    .mkt-sentiment-sort select {{ background: {t['topbar']}; color: {t['text_2']};
      border: 1px solid {t['border_bright']}; border-radius: 7px; padding: 7px 11px; font-size: 13.5px; }}
    .mkt-sentiment-sort select:focus-visible {{ outline: 3px solid {t['accent']}; outline-offset: 2px; }}
    /* Shared wrapper for both the forecast and turning-risk chips -- same class
       reused for both, mirroring dashboard.py:1230/1250's identical old CSS class. */
    .mkt-forecast {{ margin-top: 14px; padding-top: 12px; border-top: 1px solid {t['border']}; }}
    .mkt-forecast p {{ margin: 8px 0 0; font-size: 13.5px; color: {t['text_2']}; }}
    .mkt-forecast .ui-pill {{ margin: 0 6px 6px 0; }}

    /* -- workbench view (wb-*): unified review queue -------------------------- */
    .wb-gate-row {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
    .wb-gate-row .chart-progress {{ flex: 1; min-width: 180px; }}
    .wb-gate-stat {{ font-size: 15px; color: {t['text_2']}; }}
    .wb-gate-stat strong {{ font-size: 26px; color: {t['blocked']}; margin-right: 4px; }}
    .wb-gate-actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }}
    .queue-expand p {{ margin: 0 0 10px; font-size: 14px; color: {t['text_2']}; }}
    .wb-evidence-hint {{ color: {t['text_3']}; font-size: 13px; margin: 4px 0; }}
    .wb-actions-row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 4px; }}
    .wb-cli {{ color: {t['text_muted']}; font-size: 12px; }}
    .wb-actions {{ display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }}
    .wb-next-tag {{ font-size: 11px; font-weight: 800; letter-spacing: 1px; color: {t['accent']}; }}
    .wb-next-indicator {{ color: {t['accent']}; font-size: 13px; text-align: center; }}
    .wb-queue-note {{ color: {t['text_faint']}; font-size: 12px; text-align: center; margin-top: 10px; }}
    /* Bug fix: workbench.py emits .queue-expand as the immediate next sibling of
       its .queue-row (row_html + expand_html, no separator -- confirmed by
       reading _queue_row_block/_queue_card). Filtering a row (adding .hidden)
       must also hide its paired expand panel, or an expanded row's detail
       block is left floating after the row itself disappears. */
    .queue-row.hidden + .queue-expand {{ display: none; }}

    /* -- Feature D: 狀態資訊 status line (待處理/已完成/稍後處理/不處理 + stale + 最後更新) - */
    .wb-status-line {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 2px 0 14px; }}

    /* -- Feature C: 批次操作 bulk queue toolbar + per-row select checkbox ------ */
    .wb-bulk-tools {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 0 0 12px; }}
    .wb-bulk-select-all {{ display: flex; align-items: center; gap: 7px; color: {t['text_3']};
      font-size: 13px; font-weight: 700; cursor: pointer; }}
    .wb-bulk-count {{ color: {t['text_muted']}; font-size: 12.5px; margin-left: auto; }}
    /* Widens .queue-row's grid (base_css() still owns the byte-checked 7-column
       layout) by one leading column for the new select checkbox. Restated
       inside the @media block below so the existing small-viewport 1-column
       collapse still wins there (same selector/specificity, later source
       order inside that block beats this desktop rule). */
    .queue-row {{ grid-template-columns: 28px 34px 72px 56px 120px 130px 1fr 200px; }}
    .wb-select-cell {{ display: flex; align-items: center; justify-content: center; }}
    .wb-row-select {{ width: 15px; height: 15px; cursor: pointer; accent-color: {t['accent']}; }}

    /* -- spec section 10 (evidence composer): served-mode compose-and-set
       control appended below the plain note/reviewer/evidence_url hint
       (views/workbench.py's _evidence_compose_block). */
    .wb-compose {{ margin-top: 10px; padding-top: 10px; border-top: 1px dashed {t['border']}; }}
    .wb-compose-hint {{ color: {t['text_3']}; font-size: 13px; margin: 0 0 8px; }}
    .wb-compose-field {{ display: flex; flex-direction: column; gap: 4px; color: {t['text_3']};
      font-size: 13px; margin-bottom: 8px; }}
    .wb-compose-field textarea {{ background: {t['topbar']}; border: 1px solid {t['border_bright']};
      border-radius: 7px; padding: 8px 10px; color: {t['text_2']}; font-size: 13px;
      min-height: 64px; resize: vertical; font-family: inherit; }}
    .wb-compose-overwrite {{ display: flex; align-items: center; gap: 7px; color: {t['text_3']};
      font-size: 13px; margin-bottom: 8px; cursor: pointer; }}
    .wb-compose-result:empty {{ display: none; }}
    .wb-compose-result {{ margin-top: 10px; padding: 10px; border: 1px solid {t['border_bright']};
      border-radius: 8px; background: {t['panel_deep']}; }}
    .wb-compose-summary {{ margin: 0 0 6px; font-weight: 700; color: {t['text']}; font-size: 13.5px; }}
    .wb-compose-next {{ margin: 0 0 8px; color: {t['text_3']}; font-size: 13px; }}
    .wb-compose-checks {{ margin: 0 0 10px 18px; padding: 0; color: {t['text_3']};
      font-size: 12.5px; display: grid; gap: 4px; }}
    .wb-compose-preview {{ margin-top: 8px; padding: 8px 10px; border: 1px solid {t['border']};
      border-radius: 7px; background: {t['topbar']}; }}
    .wb-compose-preview strong {{ display: block; margin-bottom: 4px; color: {t['text_2']}; font-size: 12.5px; }}
    .wb-compose-preview pre {{ max-height: 220px; overflow: auto; margin: 6px 0 0; white-space: pre-wrap;
      overflow-wrap: anywhere; font-size: 12px; color: {t['text_3']};
      font-family: "Cascadia Mono", Consolas, "Courier New", monospace; }}

    /* -- outputs view (out-*): stacked report/status tables ------------------- */
    .out-section {{ margin: 0; }}
    .out-badges {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0 14px; }}
    .out-command-code {{ display: block; background: {t['topbar']}; border: 1px solid {t['border_bright']};
      border-radius: 8px; padding: 10px 14px; margin: 4px 0 10px; overflow-x: auto;
      white-space: nowrap; font-size: 13px; color: {t['text_2']}; }}
    .out-command-code + a.ui-btn {{ margin-right: 8px; }}
    .out-section[data-outputs-commands-section] {{ display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .out-section[data-outputs-commands-section] .ui-card {{ margin-bottom: 0; }}

    /* -- Task 1 gap: contribution_bars()'s wrapper div had no rule ------------ */
    .chart-contrib {{ margin-top: 15px; display: grid; gap: 9px; }}

    @media (max-width: 900px) {{
      .mkt-section {{ grid-template-columns: 1fr; }}
      .mkt-flow-row, .mkt-rotation-row {{ grid-template-columns: 52px 1fr 72px; }}
      .mkt-sentiment-sort {{ align-items: stretch; }}
      .mkt-sentiment-sort label {{ flex-direction: column; align-items: stretch; }}
      .mkt-sentiment-sort select {{ width: 100%; }}
      /* Reclaims the mobile 1-column collapse base_css() already defines for
         .queue-row -- this file's own desktop 8-column override above would
         otherwise win at small viewports too (same selector/specificity,
         later source order beats base_css()'s @media block). */
      .queue-row {{ grid-template-columns: 1fr; }}
    }}
    """
