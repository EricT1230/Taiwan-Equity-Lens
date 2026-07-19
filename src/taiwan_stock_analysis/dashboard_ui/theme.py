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
