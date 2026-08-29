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
        "text_faint": "#7d8eae",
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
    /* Final polish C7: collapsible 依據與警告 (sentiment.reasons + forecast/
       turning-risk warnings), ported from the pre-redesign dashboard.py's
       .industry-sentiment-details. */
    .mkt-sentiment-details {{ margin-top: 14px; padding-top: 12px; border-top: 1px solid {t['border']}; }}
    .mkt-sentiment-details summary {{ cursor: pointer; font-weight: 700; color: {t['text_3']}; font-size: 13px; }}
    .mkt-sentiment-details summary:focus-visible {{ outline: 3px solid {t['accent']}; outline-offset: 2px; }}
    .mkt-sentiment-details h4 {{ margin: 10px 0 4px; font-size: 12px; color: {t['text_muted']};
      letter-spacing: 0.3px; }}
    .mkt-sentiment-details ul {{ margin: 0 0 4px 18px; padding: 0; font-size: 13px; color: {t['text_2']}; }}
    .mkt-sentiment-details li {{ margin: 3px 0; }}

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

    /* -- retail desktop shell ------------------------------------------------ */
    body {{ min-height: 100vh; background:
      radial-gradient(circle at 78% -10%, rgba(46,224,247,0.09), transparent 31rem),
      linear-gradient(rgba(34,48,80,0.12) 1px, transparent 1px),
      linear-gradient(90deg, rgba(34,48,80,0.10) 1px, transparent 1px),
      {t['bg']}; background-size: auto, 42px 42px, 42px 42px, auto; }}
    button, input, textarea, select {{ font: inherit; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }}
    .app-shell {{ min-height: 100vh; display: grid; grid-template-columns: 236px minmax(0, 1fr); }}
    .app-main {{ min-width: 0; }}
    .side-rail {{ position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column;
      padding: 22px 14px 16px; background: rgba(10,17,32,0.96); border-right: 1px solid {t['border']};
      box-shadow: 18px 0 50px rgba(0,0,0,0.22); z-index: 20; }}
    .brand {{ display: flex; align-items: center; gap: 11px; padding: 0 8px 20px; }}
    .brand-mark {{ width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px;
      background: linear-gradient(145deg, {t['accent']}, {t['ok']}); color: {t['bg']};
      font-family: "Cascadia Mono", Consolas, monospace; font-size: 20px; font-weight: 900;
      box-shadow: 0 0 24px rgba(46,224,247,0.23); }}
    .brand > div {{ min-width: 0; display: grid; }}
    .brand strong {{ font-size: 18px; letter-spacing: 1px; }}
    .brand small {{ color: {t['text_muted']}; font: 9px/1.4 "Cascadia Mono", Consolas, monospace;
      letter-spacing: 2px; }}
    .brand .mono {{ display: block; max-width: 150px; margin-top: 5px; color: {t['text_faint']};
      font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .ui-tabs {{ flex: 1; display: flex; flex-direction: column; gap: 5px; padding: 10px 0;
      background: transparent; border: 0; overflow-y: auto; scrollbar-width: none; }}
    .ui-tabs::-webkit-scrollbar {{ display: none; }}
    .ui-tab {{ width: 100%; display: flex; align-items: center; gap: 11px; padding: 11px 13px;
      color: #91a5c5; border: 1px solid transparent; border-radius: 9px; text-align: left;
      font-size: 14px; letter-spacing: 0.2px; transition: 160ms ease; }}
    .ui-tab:hover {{ color: {t['text']}; text-decoration: none; background: rgba(255,255,255,0.035); }}
    .ui-tab.active {{ color: {t['text']}; border-color: rgba(46,224,247,0.26);
      background: linear-gradient(90deg, rgba(46,224,247,0.13), rgba(46,224,247,0.025));
      box-shadow: inset 3px 0 0 {t['accent']}; }}
    .ui-tab-icon {{ width: 22px; color: {t['accent']}; font: 17px/1 "Cascadia Mono", Consolas, monospace;
      text-align: center; }}
    .side-rail-foot {{ display: flex; align-items: center; gap: 10px; margin: 18px 7px 0; padding: 12px;
      border: 1px solid {t['border']}; border-radius: 10px; background: rgba(5,8,16,0.54); }}
    .side-rail-foot > div {{ display: grid; gap: 2px; }}
    .side-rail-foot strong {{ color: {t['text_2']}; font-size: 11px; }}
    .side-rail-foot small {{ color: {t['text_faint']}; font-size: 9px; }}
    .side-live-dot {{ width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%;
      background: {t['ok']}; box-shadow: 0 0 10px rgba(52,211,153,0.8); }}
    .topbar {{ position: sticky; top: 0; z-index: 15; min-height: 70px; padding: 11px 30px;
      background: rgba(5,8,16,0.86); border-bottom-color: rgba(44,61,96,0.7);
      backdrop-filter: blur(18px); }}
    .topbar-heading {{ display: grid; gap: 2px; min-width: 130px; }}
    .topbar-heading > strong {{ font-size: 17px; letter-spacing: 0.4px; }}
    .desk-kicker {{ color: {t['accent']}; font: 700 10px/1.4 "Cascadia Mono", Consolas, monospace;
      letter-spacing: 1.7px; text-transform: uppercase; }}
    .topbar-search {{ flex: 1; max-width: 430px; min-width: 210px; display: flex; align-items: center; gap: 9px;
      padding: 8px 12px; border: 1px solid {t['border']}; border-radius: 10px; background: rgba(13,21,38,0.84); }}
    .topbar-search > span {{ color: {t['text_muted']}; font-size: 18px; }}
    .topbar-search input {{ min-width: 0; width: 100%; border: 0; outline: 0; background: transparent;
      color: {t['text_2']}; font-size: 13px; }}
    .topbar-search:focus-within {{ border-color: rgba(46,224,247,0.55); box-shadow: 0 0 0 3px rgba(46,224,247,0.08); }}
    .ui-panel {{ padding: 30px clamp(20px, 3vw, 44px) 42px; }}
    .ui-panel > * {{ max-width: 1560px; margin-left: auto; margin-right: auto; }}
    .disclaimer {{ max-width: 980px; margin: 0 auto; border-top: 1px solid rgba(34,48,80,0.5); }}

    /* -- shared retail product primitives ----------------------------------- */
    .product-page-head {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 22px;
      margin-bottom: 22px; }}
    .product-page-head h1 {{ margin: 4px 0 6px; font-size: clamp(28px, 3vw, 42px); line-height: 1.1;
      letter-spacing: -1.2px; }}
    .product-page-head p {{ max-width: 700px; margin: 0; color: {t['text_3']}; font-size: 14px; }}
    .product-head-status {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      color: {t['text_muted']}; font-size: 12px; }}
    .desk-card {{ background: linear-gradient(145deg, rgba(19,31,56,0.96), rgba(13,21,38,0.96));
      border: 1px solid {t['border_bright']}; border-radius: 14px; padding: 20px;
      box-shadow: 0 14px 40px rgba(0,0,0,0.24), inset 0 1px rgba(255,255,255,0.035); }}
    .desk-section-head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 15px;
      margin-bottom: 16px; }}
    .desk-section-head h2 {{ margin: 3px 0 0; font-size: 19px; letter-spacing: -0.2px; }}
    .desk-section-note {{ color: {t['text_muted']}; font-size: 11px; text-align: right; }}
    .desk-link {{ border: 0; padding: 4px; background: transparent; color: {t['accent']}; font-weight: 700;
      font-size: 12px; cursor: pointer; }}
    .desk-link:hover {{ text-decoration: underline; }}
    .desk-empty {{ color: {t['text_muted']}; font-size: 13px; }}

    /* -- overview ------------------------------------------------------------ */
    .desk-overview {{ display: grid; gap: 17px; }}
    .desk-hero {{ position: relative; overflow: hidden; min-height: 240px; display: grid;
      grid-template-columns: minmax(0,1fr) auto; align-items: center; gap: 28px; padding: clamp(25px, 4vw, 48px);
      border: 1px solid rgba(46,224,247,0.22); border-radius: 18px;
      background: radial-gradient(circle at 82% 18%, rgba(46,224,247,0.15), transparent 28%),
        radial-gradient(circle at 5% 110%, rgba(52,211,153,0.09), transparent 38%),
        linear-gradient(135deg, rgba(19,31,56,0.98), rgba(8,13,25,0.99)); }}
    .desk-hero::after {{ content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0.22;
      background: repeating-linear-gradient(118deg, transparent 0 46px, rgba(46,224,247,0.07) 47px 48px); }}
    .desk-hero-copy {{ position: relative; z-index: 1; }}
    .desk-title-row {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
    .desk-title-row h1 {{ margin: 7px 0 9px; font-size: clamp(40px, 6vw, 76px); line-height: 0.98;
      letter-spacing: -3px; }}
    .desk-hero-copy > p {{ max-width: 720px; color: {t['text_2']}; font-size: 16px; line-height: 1.8; }}
    .desk-hero-meta {{ display: flex; gap: 18px; flex-wrap: wrap; margin-top: 22px; color: {t['text_muted']};
      font-size: 11px; }}
    .desk-hero-meta strong {{ color: {t['text_2']}; }}
    .desk-gauge {{ position: relative; z-index: 1; display: grid; justify-items: center; gap: 10px; }}
    .desk-gauge-ring {{ width: 152px; aspect-ratio: 1; display: grid; place-content: center; text-align: center;
      border-radius: 50%; background: radial-gradient(circle at center, {t['panel_deep']} 57%, transparent 58%),
      conic-gradient({t['accent']} calc(var(--gauge) * 1%), rgba(44,61,96,0.65) 0); box-shadow: 0 0 34px rgba(46,224,247,0.12); }}
    .desk-gauge-ring strong {{ font-size: 42px; line-height: 1; }}
    .desk-gauge-ring span {{ margin-top: 4px; color: {t['text_muted']}; font-size: 10px; letter-spacing: 1px; }}
    .desk-gauge small {{ color: {t['text_faint']}; font-size: 9px; }}
    .desk-metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .desk-metric {{ display: grid; gap: 7px; padding: 16px 18px; background: rgba(13,21,38,0.8);
      border: 1px solid {t['border']}; border-radius: 12px; }}
    .desk-metric-label {{ color: {t['text_muted']}; font-size: 11px; letter-spacing: 0.7px; }}
    .desk-metric-value {{ font-size: 23px; }}
    .desk-metric-detail {{ color: {t['text_faint']}; font-size: 10px; }}
    .desk-flow-steps {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .desk-flow-step {{ position: relative; display: grid; gap: 7px; min-height: 138px; padding: 16px;
      text-align: left; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 11px;
      background: rgba(5,8,16,0.36); cursor: pointer; transition: transform 160ms ease, border-color 160ms ease; }}
    .desk-flow-step:hover {{ transform: translateY(-2px); border-color: rgba(46,224,247,0.42); }}
    .desk-flow-index {{ color: {t['accent']}; font: 700 10px "Cascadia Mono", Consolas, monospace; }}
    .desk-flow-step strong {{ font-size: 17px; }}
    .desk-flow-step small {{ color: {t['text_3']}; line-height: 1.55; }}
    .desk-flow-step > span:last-child {{ margin-top: auto; color: {t['accent']}; font-size: 11px; font-weight: 700; }}
    .desk-overview-grid {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 17px; align-items: start; }}
    .desk-watch {{ grid-column: 1 / -1; }}
    .desk-pulse-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 9px; }}
    .desk-pulse-item {{ padding: 13px; border: 1px solid {t['border']}; border-radius: 10px; background: rgba(5,8,16,0.28); }}
    .desk-pulse-item > div {{ display: flex; justify-content: space-between; gap: 10px; }}
    .desk-pulse-item > div > span {{ color: {t['accent']}; font-size: 20px; font-weight: 700; }}
    .desk-pulse-item p {{ display: flex; justify-content: space-between; gap: 8px; margin: 7px 0 0;
      color: {t['text_muted']}; font-size: 10px; }}
    .desk-news-list {{ display: grid; gap: 0; }}
    .desk-news-item {{ padding: 12px 0; border-top: 1px solid {t['border']}; }}
    .desk-news-item:first-child {{ padding-top: 0; border-top: 0; }}
    .desk-news-meta {{ display: flex; justify-content: space-between; gap: 12px; color: {t['text_faint']};
      font: 9px "Cascadia Mono", Consolas, monospace; }}
    .desk-news-item h3 {{ margin: 7px 0 4px; font-size: 14px; }}
    .desk-news-item p {{ margin: 0; color: {t['text_3']}; font-size: 11px; line-height: 1.6; }}
    .desk-watch-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 9px; }}
    .desk-watch-item {{ display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px;
      padding: 12px; border: 1px solid {t['border']}; border-radius: 10px; background: rgba(5,8,16,0.28); }}
    .desk-watch-symbol {{ color: {t['accent']}; font-size: 11px; }}
    .desk-watch-item > div {{ display: grid; gap: 3px; min-width: 0; }}
    .desk-watch-item > div strong {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }}
    .desk-watch-item small {{ color: {t['text_faint']}; font-size: 9px; }}
    .desk-watch-price {{ grid-column: 3; grid-row: 2; text-align: right; color: {t['text_3']} !important; }}
    .desk-watch-return {{ font-size: 12px; font-weight: 700; }}

    /* -- industry map -------------------------------------------------------- */
    .industry-map {{ margin-bottom: 28px; }}
    .industry-map-legend {{ display: flex; gap: 13px; flex-wrap: wrap; color: {t['text_muted']}; font-size: 10px; }}
    .industry-map-legend span {{ display: flex; align-items: center; gap: 5px; }}
    .industry-map-legend i {{ width: 8px; height: 8px; border-radius: 2px; }}
    .industry-map-legend .positive {{ background: {t['up']}; }}
    .industry-map-legend .negative {{ background: {t['down']}; }}
    .industry-map-legend .neutral {{ background: {t['text_muted']}; }}
    .industry-map-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      grid-auto-rows: minmax(150px, auto); gap: 10px; }}
    .industry-tile {{ display: grid; align-content: space-between; gap: 6px; padding: 17px; text-align: left;
      color: {t['text']}; border: 1px solid {t['border_bright']}; border-radius: 12px; cursor: pointer;
      transition: transform 150ms ease, border-color 150ms ease; }}
    .industry-tile:hover {{ transform: translateY(-2px); border-color: rgba(255,255,255,0.28); }}
    .industry-tile-positive {{ background: linear-gradient(145deg, rgba(245,78,78,0.19), rgba(19,31,56,0.94)); }}
    .industry-tile-negative {{ background: linear-gradient(145deg, rgba(52,208,126,0.17), rgba(19,31,56,0.94)); }}
    .industry-tile-neutral {{ background: linear-gradient(145deg, rgba(107,127,163,0.10), rgba(19,31,56,0.94)); }}
    .industry-tile-name {{ color: {t['text_3']}; font-size: 12px; font-weight: 700; }}
    .industry-tile strong {{ font-size: 38px; line-height: 1; }}
    .industry-tile > span:not(.industry-tile-name) {{ font-size: 11px; }}
    .industry-tile small {{ color: {t['text_faint']}; font-size: 9px; }}
    .industry-map-summary {{ margin: 8px 0 0; color: {t['text_muted']}; font-size: 10px; text-align: right; }}
    .industry-map-summary strong {{ color: {t['accent']}; }}
    .industry-map-note {{ margin: 10px 2px 0; color: {t['text_faint']}; font-size: 10px; }}
    .ui-card.industry-focus {{ animation: industry-focus 1.35s ease; }}
    @keyframes industry-focus {{ 0%,100% {{ box-shadow: 0 6px 18px rgba(0,0,0,0.55); }}
      35% {{ box-shadow: 0 0 0 3px rgba(46,224,247,0.35), 0 0 36px rgba(46,224,247,0.22); }} }}

    /* -- screener ------------------------------------------------------------ */
    .screen-view {{ display: grid; gap: 15px; }}
    .screen-search-wrap {{ min-width: 310px; display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; }}
    .screen-search-wrap label {{ grid-column: 1 / -1; color: {t['text_muted']}; font-size: 10px; }}
    .screen-search-wrap input {{ min-width: 0; padding: 10px 12px; color: {t['text_2']}; background: {t['panel_deep']};
      border: 1px solid {t['border_bright']}; border-radius: 9px; }}
    .screen-search-wrap > span {{ align-self: center; color: {t['text_muted']}; font-size: 11px; }}
    .screen-filter-strip {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }}
    .screen-filter {{ min-height: 70px; display: grid; gap: 5px; padding: 12px; text-align: left;
      color: {t['text_3']}; border: 1px solid {t['border']}; border-radius: 10px; background: rgba(13,21,38,0.72);
      cursor: pointer; }}
    .screen-filter strong {{ color: {t['text_2']}; font-size: 14px; }}
    .screen-filter-count {{ color: {t['accent']}; font-size: 10px; }}
    .screen-filter small {{ color: {t['text_faint']}; font-size: 9px; line-height: 1.45; }}
    .screen-filter.active {{ border-color: rgba(46,224,247,0.5); background: rgba(46,224,247,0.09);
      box-shadow: inset 0 -2px {t['accent']}; }}
    .screen-breadth-controls {{ display: grid; grid-template-columns: repeat(4, minmax(125px, 1fr)) minmax(160px, auto);
      align-items: end; gap: 9px; padding: 11px 13px; border: 1px solid {t['border']};
      border-radius: 10px; background: rgba(5,8,16,0.28); }}
    .screen-breadth-controls label {{ display: grid; gap: 5px; color: {t['text_muted']}; font-size: 9px; }}
    .screen-breadth-controls select {{ min-width: 0; padding: 8px 9px; color: {t['text_2']};
      background: {t['panel_deep']}; border: 1px solid {t['border_bright']}; border-radius: 7px; }}
    .screen-breadth-controls select:disabled {{ opacity: .55; cursor: not-allowed; }}
    .screen-breadth-status {{ display: grid; align-self: stretch; align-content: center; justify-items: end;
      gap: 3px; color: {t['text_muted']}; font-size: 9px; }}
    .screen-breadth-status strong {{ color: {t['accent']}; font-size: 11px; }}
    .screen-method {{ display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 16px;
      padding: 13px 16px; border: 1px dashed {t['border_bright']}; border-radius: 10px; background: rgba(5,8,16,0.3); }}
    .screen-method > div {{ display: grid; gap: 3px; }}
    .screen-method p {{ margin: 0; color: {t['text_3']}; font-size: 10px; line-height: 1.6; }}
    .screen-table {{ overflow: hidden; border: 1px solid {t['border_bright']}; border-radius: 12px; background: {t['panel_deep']}; }}
    .screen-row {{ display: grid; grid-template-columns: 38px minmax(210px,1.15fr) minmax(220px,1.4fr)
      66px 66px 66px 66px 96px; align-items: center; gap: 9px; min-height: 76px; padding: 10px 14px;
      border-top: 1px solid rgba(34,48,80,0.72); }}
    .screen-row[hidden] {{ display: none; }}
    .screen-head {{ min-height: 40px; color: {t['text_muted']}; background: {t['topbar']}; border-top: 0;
      font-size: 10px; letter-spacing: 0.6px; }}
    .screen-star {{ border: 0; background: transparent; color: {t['text_muted']}; font-size: 20px; cursor: pointer; }}
    .screen-star.active {{ color: {t['warn']}; }}
    .screen-company, .screen-thesis {{ min-width: 0; display: grid; gap: 4px; }}
    .screen-company strong {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }}
    .screen-company > span, .screen-thesis span {{ color: {t['text_muted']}; font-size: 9px; }}
    .screen-company .screen-live-price {{ color: {t['accent']}; font-weight: 700; }}
    .screen-thesis strong {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: {t['text_2']};
      font-size: 11px; }}
    .screen-thesis small {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      color: {t['blocked']}; font-size: 9px; }}
    .screen-tags {{ display: flex; gap: 4px; flex-wrap: wrap; }}
    .screen-tags .ui-pill {{ padding: 2px 6px; font-size: 8px; }}
    .screen-num, .screen-score {{ text-align: right; font-size: 11px; font-weight: 700; }}
    .screen-score {{ color: {t['accent']}; font-size: 14px; }}
    .screen-quality .ui-pill {{ padding: 4px 7px; font-size: 9px; }}
    .screen-empty, .screen-source-empty {{ padding: 38px; text-align: center; color: {t['text_3']}; }}
    .screen-empty p {{ margin: 7px auto 0; max-width: 530px; color: {t['text_muted']}; font-size: 11px; }}
    .screen-pagination {{ display: flex; justify-content: center; align-items: center; gap: 12px; }}
    .screen-pagination[hidden] {{ display: none; }}
    .screen-pagination button {{ padding: 7px 11px; color: {t['text_2']}; background: {t['panel_deep']};
      border: 1px solid {t['border_bright']}; border-radius: 7px; cursor: pointer; }}
    .screen-pagination button:disabled {{ opacity: .45; cursor: not-allowed; }}
    .screen-pagination span {{ min-width: 105px; color: {t['text_muted']}; text-align: center; font-size: 10px; }}
    .screen-footnote {{ color: {t['text_faint']}; font-size: 10px; text-align: center; }}

    /* -- intelligence -------------------------------------------------------- */
    .intel-layout {{ display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(280px, .8fr); gap: 16px; align-items: start; }}
    .intel-fundamentals {{ grid-column: 1 / -1; }}
    .intel-news-filter {{ display: flex; gap: 5px; }}
    .intel-news-filter button {{ padding: 5px 9px; border: 1px solid {t['border']}; border-radius: 7px;
      background: transparent; color: {t['text_muted']}; font-size: 9px; cursor: pointer; }}
    .intel-news-filter button.active {{ color: {t['accent']}; border-color: rgba(46,224,247,0.35); }}
    .intel-news-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 9px; }}
    .intel-news-card {{ display: grid; align-content: start; gap: 8px; padding: 14px; border: 1px solid {t['border']};
      border-radius: 10px; background: rgba(5,8,16,0.28); }}
    .intel-news-meta {{ display: flex; justify-content: space-between; gap: 8px; color: {t['text_faint']};
      font: 9px "Cascadia Mono", Consolas, monospace; }}
    .intel-news-card h3 {{ margin: 0; font-size: 13px; line-height: 1.5; }}
    .intel-news-card p {{ margin: 0; color: {t['text_3']}; font-size: 10px; line-height: 1.65;
      display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
    .intel-tags {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .intel-tags .ui-pill {{ padding: 2px 6px; font-size: 8px; }}
    .intel-news-card .desk-link {{ justify-self: start; margin-top: auto; }}
    .intel-notes {{ position: sticky; top: 92px; }}
    .intel-save-state {{ color: {t['ok']}; font-size: 9px; }}
    .intel-notes label {{ display: block; margin-bottom: 8px; color: {t['text_3']}; font-size: 10px; }}
    .intel-notes textarea {{ width: 100%; min-height: 240px; resize: vertical; padding: 13px;
      color: {t['text_2']}; background: rgba(5,8,16,0.52); border: 1px solid {t['border_bright']}; border-radius: 10px;
      line-height: 1.75; font-size: 12px; }}
    .intel-notes textarea:focus {{ outline: 3px solid rgba(46,224,247,0.12); border-color: rgba(46,224,247,0.5); }}
    .intel-note-template {{ margin-top: 12px; padding: 12px; border-radius: 9px; background: rgba(46,224,247,0.055); }}
    .intel-note-template strong {{ font-size: 10px; color: {t['accent']}; }}
    .intel-note-template ol {{ margin: 8px 0 0 18px; padding: 0; color: {t['text_muted']}; font-size: 9px; line-height: 1.7; }}
    .intel-notes > p {{ color: {t['text_muted']}; font-size: 9px; }}
    .intel-fund-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .intel-fund-card {{ padding: 15px; border: 1px solid {t['border']}; border-radius: 10px; background: rgba(5,8,16,0.28); }}
    .intel-fund-card header {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }}
    .intel-fund-card header > div {{ display: flex; align-items: baseline; gap: 8px; }}
    .intel-fund-card header span.mono {{ color: {t['accent']}; font-size: 10px; }}
    .intel-fund-card h3 {{ margin: 0; font-size: 15px; }}
    .intel-thesis {{ min-height: 34px; color: {t['text_3']}; font-size: 10px; line-height: 1.6; }}
    .intel-factors {{ display: grid; gap: 7px; }}
    .intel-factor {{ display: grid; grid-template-columns: 62px 1fr 28px; align-items: center; gap: 8px;
      color: {t['text_muted']}; font-size: 9px; }}
    .intel-factor strong {{ grid-column: 3; grid-row: 1; text-align: right; color: {t['text_2']}; }}
    .intel-factor i {{ grid-column: 2; grid-row: 1; height: 4px; border-radius: 3px;
      background: linear-gradient(90deg, {t['accent']} calc(var(--factor) * 1%), {t['border']} 0); }}
    .intel-fund-card details {{ margin-top: 12px; color: {t['text_muted']}; font-size: 9px; }}
    .intel-fund-card details p {{ color: {t['text_3']}; line-height: 1.6; }}

    /* -- strategy ------------------------------------------------------------ */
    .strategy-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 11px; }}
    .strategy-card {{ position: relative; overflow: hidden; display: grid; align-content: start; padding: 18px;
      border: 1px solid {t['border_bright']}; border-radius: 13px; background: linear-gradient(150deg, {t['panel']}, {t['panel_deep']}); }}
    .strategy-card::before {{ content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: {t['text_muted']}; }}
    .strategy-bull::before {{ background: {t['up']}; }}
    .strategy-bear::before {{ background: {t['down']}; }}
    .strategy-mixed::before {{ background: {t['warn']}; }}
    .strategy-card header {{ display: flex; align-items: center; gap: 10px; }}
    .strategy-card header > div {{ display: grid; gap: 5px; }}
    .strategy-card h3 {{ margin: 0; font-size: 16px; }}
    .strategy-icon {{ width: 36px; height: 36px; display: grid; place-items: center; border: 1px solid {t['border_bright']};
      border-radius: 10px; background: rgba(5,8,16,0.4); color: {t['accent']}; font-weight: 900; }}
    .strategy-card > p {{ min-height: 54px; color: {t['text_3']}; font-size: 10px; line-height: 1.7; }}
    .strategy-card > strong, .strategy-invalid > span {{ color: {t['text_muted']}; font-size: 9px; letter-spacing: .6px; }}
    .strategy-card ul {{ margin: 8px 0 14px 17px; padding: 0; color: {t['text_2']}; font-size: 10px; line-height: 1.7; }}
    .strategy-invalid {{ margin-top: auto; padding-top: 10px; border-top: 1px solid {t['border']}; }}
    .strategy-invalid p {{ margin: 6px 0 0; color: {t['text_3']}; font-size: 9px; line-height: 1.6; }}
    .strategy-regime {{ display: grid; justify-items: end; gap: 4px; }}
    .strategy-regime > span {{ color: {t['text_muted']}; font-size: 9px; }}
    .strategy-regime > strong {{ font-size: 22px; }}
    .strategy-bottom-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 15px; }}
    .strategy-rules {{ grid-column: 1 / -1; }}
    .strategy-matrix-grid {{ position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 6px;
      padding: 10px 10px 26px 36px; }}
    .strategy-matrix-cell {{ min-height: 70px; display: grid; place-items: center; padding: 10px; text-align: center;
      border: 1px solid {t['border']}; border-radius: 8px; background: rgba(5,8,16,0.3); color: {t['text_muted']};
      font-size: 10px; }}
    .strategy-matrix-cell.active {{ color: {t['text']}; border-color: {t['accent']}; background: rgba(46,224,247,0.11);
      box-shadow: 0 0 22px rgba(46,224,247,0.08); }}
    .strategy-axis {{ position: absolute; color: {t['text_faint']}; font-size: 8px; }}
    .strategy-axis-y {{ left: 2px; top: 50%; transform: rotate(-90deg) translateY(-50%); }}
    .strategy-axis-x {{ right: 12px; bottom: 5px; }}
    .strategy-matrix > p {{ color: {t['text_3']}; font-size: 10px; line-height: 1.6; }}
    .strategy-execution ol {{ display: grid; gap: 9px; margin: 0; padding: 0; list-style: none; }}
    .strategy-execution li {{ display: grid; grid-template-columns: 32px 1fr; gap: 10px; align-items: start; }}
    .strategy-execution li > span {{ color: {t['accent']}; font: 700 10px "Cascadia Mono", Consolas, monospace; }}
    .strategy-execution li > div {{ padding-bottom: 9px; border-bottom: 1px solid {t['border']}; }}
    .strategy-execution li strong {{ font-size: 11px; }}
    .strategy-execution li p {{ margin: 4px 0 0; color: {t['text_muted']}; font-size: 9px; line-height: 1.55; }}
    .strategy-rule-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 9px; }}
    .strategy-rule-grid > div {{ padding: 12px; border: 1px solid {t['border']}; border-radius: 9px; background: rgba(5,8,16,0.28); }}
    .strategy-rule-grid strong {{ color: {t['text_2']}; font-size: 10px; }}
    .strategy-rule-grid p {{ margin: 5px 0 0; color: {t['text_muted']}; font-size: 9px; line-height: 1.6; }}

    /* -- explicit production / demo data mode ------------------------------ */
    .data-mode-banner {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
      margin: 14px 26px 0; padding: 10px 14px; border: 1px solid {t['border_bright']};
      border-radius: 10px; background: rgba(13,21,38,0.9); }}
    .data-mode-banner strong {{ font-size: 12px; letter-spacing: .25px; }}
    .data-mode-banner small {{ color: {t['text_muted']}; font-size: 9px; }}
    .data-mode-production {{ border-color: rgba(46,224,247,0.28); }}
    .data-mode-production strong {{ color: {t['accent']}; }}
    .data-mode-demo {{ border-width: 2px; border-color: rgba(255,201,77,0.88);
      background: repeating-linear-gradient(-45deg, rgba(255,201,77,0.13),
        rgba(255,201,77,0.13) 10px, rgba(255,107,125,0.08) 10px,
        rgba(255,107,125,0.08) 20px); }}
    .data-mode-demo strong {{ color: {t['warn']}; font-size: 13px; }}
    .data-mode-demo small {{ color: {t['text_2']}; }}

    /* -- connected live market mode ---------------------------------------- */
    .live-connection {{ display: flex; align-items: center; justify-content: space-between; gap: 14px;
      margin: 14px 26px 0; padding: 10px 14px; border: 1px solid {t['border_bright']};
      border-radius: 10px; background: rgba(13,21,38,0.9); }}
    .live-connection > div:first-child {{ display: grid; grid-template-columns: auto auto; align-items: center;
      gap: 2px 9px; }}
    .live-connection > div:first-child small {{ grid-column: 2; color: {t['text_muted']}; font-size: 9px; }}
    .live-connection-dot {{ grid-row: 1 / 3; width: 9px; height: 9px; border-radius: 50%;
      background: {t['warn']}; box-shadow: 0 0 0 5px rgba(255,192,74,0.08); }}
    .live-connection strong {{ color: {t['text_2']}; font-size: 11px; }}
    .live-connection-actions {{ display: flex; align-items: center; gap: 11px; color: {t['text_muted']};
      font-size: 9px; }}
    .live-connection-live {{ border-color: rgba(52,208,126,0.34); background: rgba(52,208,126,0.06); }}
    .live-connection-live .live-connection-dot {{ background: {t['ok']};
      box-shadow: 0 0 0 5px rgba(52,208,126,0.09), 0 0 14px rgba(52,208,126,0.5);
      animation: live-pulse 1.8s ease-in-out infinite; }}
    .live-connection-eod {{ border-color: rgba(46,224,247,0.25); }}
    .live-connection-eod .live-connection-dot {{ background: {t['accent']};
      box-shadow: 0 0 0 5px rgba(46,224,247,0.08); }}
    .live-connection-error, .live-connection-offline {{ border-color: rgba(255,107,125,0.35);
      background: rgba(255,107,125,0.055); }}
    .live-connection-error .live-connection-dot, .live-connection-offline .live-connection-dot {{
      background: {t['blocked']}; box-shadow: 0 0 0 5px rgba(255,107,125,0.08); }}
    .live-connection-loading .live-connection-dot {{ animation: live-pulse 1.25s ease-in-out infinite; }}
    .strategy-card.market-fit {{ border-color: rgba(46,224,247,0.55);
      box-shadow: 0 0 0 1px rgba(46,224,247,0.08), 0 12px 34px rgba(0,0,0,0.28); }}
    [data-live-updated="true"] {{ animation: live-flash 650ms ease; }}
    @keyframes live-pulse {{ 50% {{ opacity: .45; transform: scale(.78); }} }}
    @keyframes live-flash {{ 0% {{ background-color: rgba(46,224,247,0.16); }} 100% {{ background-color: transparent; }} }}

    @media (max-width: 900px) {{
      .app-shell {{ display: block; }}
      .side-rail {{ position: sticky; height: auto; padding: 9px 12px 0; border-right: 0; border-bottom: 1px solid {t['border']}; }}
      .side-rail .brand, .side-rail-foot {{ display: none; }}
      .ui-tabs {{ flex-direction: row; overflow-x: auto; padding: 0 0 8px; }}
      .ui-tab {{ width: auto; min-width: max-content; padding: 9px 11px; }}
      .ui-tab.active {{ box-shadow: inset 0 -2px 0 {t['accent']}; }}
      .topbar {{ position: static; padding: 12px 16px; }}
      .topbar-heading {{ display: none; }}
      .topbar-search {{ order: 2; max-width: none; flex-basis: 100%; }}
      .data-mode-banner, .live-connection {{ margin: 10px 14px 0; }}
      .ui-panel {{ padding: 22px 14px 30px; }}
      .product-page-head {{ align-items: flex-start; flex-direction: column; }}
      .desk-hero {{ grid-template-columns: 1fr; }}
      .desk-gauge {{ justify-self: start; grid-template-columns: auto auto; align-items: center; }}
      .desk-gauge-ring {{ width: 116px; }}
      .desk-metrics {{ grid-template-columns: repeat(2,1fr); }}
      .desk-flow-steps {{ grid-template-columns: 1fr; }}
      .desk-overview-grid {{ grid-template-columns: 1fr; }}
      .desk-watch {{ grid-column: auto; }}
      .screen-filter-strip {{ grid-template-columns: repeat(3,1fr); }}
      .screen-breadth-controls {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .screen-breadth-status {{ justify-items: start; }}
      .screen-method {{ grid-template-columns: 1fr; }}
      .screen-table {{ overflow-x: auto; }}
      .screen-row {{ min-width: 930px; }}
      .intel-layout {{ grid-template-columns: 1fr; }}
      .intel-fundamentals {{ grid-column: auto; }}
      .intel-notes {{ position: static; }}
      .strategy-grid {{ grid-template-columns: repeat(2,1fr); }}
      .strategy-bottom-grid {{ grid-template-columns: 1fr; }}
      .strategy-rules {{ grid-column: auto; }}
      .strategy-rule-grid {{ grid-template-columns: repeat(2,1fr); }}
      .mkt-section {{ grid-template-columns: 1fr; }}
      .mkt-flow-row, .mkt-rotation-row {{ grid-template-columns: 52px 1fr 72px; }}
      .mkt-sentiment-sort {{ align-items: stretch; }}
      .mkt-sentiment-sort label {{ flex-direction: column; align-items: stretch; }}
      .mkt-sentiment-sort select {{ width: 100%; }}
      /* Reclaims the mobile 1-column collapse base_css() already defines for
         .queue-row -- this file's own desktop 8-column override above would
         otherwise win at small viewports too (same selector/specificity,
         later source order beats base_css()'s @media block). */
      .queue {{ overflow: visible; }}
      .queue-row {{ grid-template-columns: 1fr; }}
      .queue-evidence {{ grid-template-columns: 1fr; }}
      .queue-evidence input {{ width: 100%; min-width: 0; }}
      .queue-expand {{ overflow-wrap: anywhere; }}
    }}
    @media (max-width: 560px) {{
      .topbar-status .ui-pill {{ padding: 4px 7px; font-size: 9px; }}
      .desk-title-row h1 {{ font-size: 40px; letter-spacing: -1.8px; }}
      .desk-metrics {{ grid-template-columns: 1fr 1fr; }}
      .desk-pulse-grid, .intel-news-grid {{ grid-template-columns: 1fr; }}
      .screen-filter-strip {{ grid-template-columns: repeat(2,1fr); }}
      .screen-breadth-controls {{ grid-template-columns: 1fr; }}
      .screen-search-wrap {{ min-width: 0; width: 100%; }}
      .strategy-grid, .strategy-rule-grid {{ grid-template-columns: 1fr; }}
      .industry-map-grid {{ grid-template-columns: 1fr 1fr; }}
      .industry-tile {{ min-height: 130px; padding: 13px; }}
      .industry-tile strong {{ font-size: 30px; }}
      .live-connection {{ align-items: flex-start; flex-direction: column; }}
      .live-connection-actions {{ width: 100%; justify-content: space-between; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        scroll-behavior: auto !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }}
    }}
    """
