from __future__ import annotations

from html import escape
from math import isfinite

from taiwan_stock_analysis.dashboard_ui.theme import TOKENS

_PLACEHOLDER = '<span class="ui-pill ui-pill-warn">歷史資料不足</span>'


def _finite(values: list) -> list[float]:
    return [float(v) for v in values if isinstance(v, (int, float)) and isfinite(v)]


def sparkline(values: list, *, width: int = 320, height: int = 64) -> str:
    points = _finite(values)
    if len(points) < 2:
        return _PLACEHOLDER
    color = TOKENS["accent"]
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    pad = 4
    step = (width - 2 * pad) / (len(points) - 1)
    coords = []
    for i, v in enumerate(points):
        x = round(pad + i * step, 2)
        y = round(height - pad - (v - lo) / span * (height - 2 * pad), 2)
        coords.append((x, y))
    line = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(coords))
    area = line + f" L{coords[-1][0]},{height} L{coords[0][0]},{height} Z"
    ex, ey = coords[-1]
    return (
        f'<svg class="chart-spark" viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="趨勢走勢圖">'
        f'<path d="{escape(area)}" fill="{color}" fill-opacity="0.16"/>'
        f'<path d="{escape(line)}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<circle cx="{ex}" cy="{ey}" r="3" fill="{color}"/>'
        f'</svg>'
    )


def signed_hbar(value, max_abs, *, height: int = 16) -> str:
    valid = (
        isinstance(value, (int, float))
        and isfinite(value)
        and value != 0
        and isinstance(max_abs, (int, float))
        and max_abs
    )
    if not valid:
        return '<div class="chart-hbar"><span class="chart-hbar-fill" style="width:0%"></span></div>'
    pct = min(abs(value) / abs(max_abs) * 100, 100)
    cls = "up" if value >= 0 else "down"
    return f'<div class="chart-hbar"><span class="chart-hbar-fill {cls}" style="width:{pct:.0f}%"></span></div>'


def contribution_bars(rows: list) -> str:
    out = ['<div class="chart-contrib">']
    for label, value, max_abs in rows:
        v = float(value) if isinstance(value, (int, float)) and isfinite(value) else 0.0
        pct = 0.0 if not max_abs else min(abs(v) / abs(max_abs) * 100, 100)
        out.append(
            f'<div class="chart-contrib-row"><span>{escape(str(label))}</span>'
            f'<div class="chart-track"><span class="chart-fill" style="width:{pct:.0f}%"></span></div>'
            f'<span class="chart-num mono">{v:+.1f}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def progress_bar(done: int, total: int) -> str:
    if not total:
        return ""
    pct = min(max(done / total * 100, 0), 100)
    return f'<div class="chart-progress"><span style="width:{pct:.0f}%"></span></div>'
