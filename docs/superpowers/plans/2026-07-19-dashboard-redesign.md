# 台股基本面儀表板重設計 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `dashboard.html` 的呈現層從 5,153 行的 f-string 巨石模組，重寫成深色金融終端風、單檔三分頁籤、統一審查佇列、內嵌 SVG 圖表的離線 HTML，且 CLI／JSON／伺服器行為零改動。

**Architecture:** 新增 `src/taiwan_stock_analysis/dashboard_ui/` 套件，內含設計 tokens（`theme.py`）、純函式 SVG 圖表（`charts.py`）、共用 HTML 元件（`components.py`）、三個分頁 view（`views/`）、頁殼組裝（`page.py`）。`dashboard.py` 保留資料發現/彙整與 `render_dashboard_html()` 入口簽名，內部改為委派 `dashboard_ui.page.render()`。產出仍是單一離線 HTML（CSS/JS/SVG 全內嵌）。

**Tech Stack:** Python ≥3.10、標準函式庫（`html.escape`、`math.isfinite`）、零第三方依賴、`unittest`。

**設計來源：** [docs/superpowers/specs/2026-07-19-dashboard-redesign-design.md](../specs/2026-07-19-dashboard-redesign-design.md)

## Global Constraints

- 測試指令一律用 `python -m unittest`（本專案**未安裝 pytest**；CI 用 `python -m unittest discover -s tests -v`）。
- 零第三方執行期依賴（`pyproject.toml` 的 `dependencies = []` 不得新增）。
- Python 版本下限 `>=3.10`。
- 產出必須是**單一離線 HTML**：CSS/JS/SVG 全部內嵌，禁止 CDN、外部字型、外部圖片、fetch 外部資源。
- 所有外部字串（股票名稱、新聞、路徑、指令）輸出前一律 `html.escape`。
- `render_dashboard_html(items, *, action_api_enabled: bool = False) -> str` 入口簽名不得更動（呼叫端：`dashboard.py:5113`、`dashboard_server.py:231`）。
- HTML `<title>` 維持字串 `台股基本面儀表板`（保留既有測試與書籤相容）。
- 顏色只能引用 `theme.TOKENS` 的值，不得散落 hex 字面值於 view/component/chart。
- 市場漲跌色（紅漲綠跌）與 workflow 狀態色（阻塞/警示/就緒）視覺文法分離：市場數字用裸色等寬字＋±號，狀態用帶文字的 pill/badge。
- 免責聲明全頁只出現一次（頁尾）。
- 覆蓋率維持既有水準（新模組皆附單元測試）。

## File Structure

| 檔案 | 責任 |
|---|---|
| `src/taiwan_stock_analysis/dashboard_ui/__init__.py` | 套件入口（空或匯出 `render`） |
| `src/taiwan_stock_analysis/dashboard_ui/theme.py` | `TOKENS` 常數 dict、`base_css() -> str` |
| `src/taiwan_stock_analysis/dashboard_ui/charts.py` | `sparkline`、`signed_hbar`、`contribution_bars`、`progress_bar` 純函式 |
| `src/taiwan_stock_analysis/dashboard_ui/components.py` | `esc`、`pill`、`badge`、`card`、`copy_button` |
| `src/taiwan_stock_analysis/dashboard_ui/labels.py` | review-action 標籤/嚴重度常數（leaf 模組，打破 `dashboard`↔`page` import 循環） |
| `src/taiwan_stock_analysis/dashboard_ui/views/__init__.py` | 匯出三個 view 函式 |
| `src/taiwan_stock_analysis/dashboard_ui/views/market.py` | `render_market_view(items) -> str` |
| `src/taiwan_stock_analysis/dashboard_ui/views/workbench.py` | `render_workbench_view(items, *, action_api_enabled) -> str` |
| `src/taiwan_stock_analysis/dashboard_ui/views/outputs.py` | `render_outputs_view(items, *, action_api_enabled) -> str` |
| `src/taiwan_stock_analysis/dashboard_ui/page.py` | `render(items, *, action_api_enabled) -> str`：狀態列＋頁籤＋三 view＋頁尾＋inline JS |
| `src/taiwan_stock_analysis/dashboard.py` | 保留資料發現/彙整；`render_dashboard_html` 改為委派；移除舊 `_*` 渲染 helper |
| `tests/test_dashboard_ui_charts.py` | charts 單元測試 |
| `tests/test_dashboard_ui_components.py` | components 單元測試 |
| `tests/test_dashboard_ui_theme.py` | theme 單元測試 |
| `tests/test_dashboard_ui_views.py` | 三 view＋page 單元測試 |
| `tests/test_dashboard.py` | 既有測試遷移到新結構 |

## 執行說明（altitude）

- **Phase 1（theme/charts/components）** 是全新、精確、小型的基石，計畫內附**完整程式碼與完整測試**。
- **Phase 2（views）** 本質是把 `dashboard.py` 既有的欄位擷取邏輯**移植**進新版標記。每個 view 任務會給：函式簽名、消費的 `items` 鍵與巢狀欄位、要呼叫的 chart/component、測試要斷言的輸出錨點（class/文字），以及可對照移植的既有 `dashboard.py` 函式名。View 內部的完整 HTML 由實作者依「結構」與「測試」產出——測試即驗收標準。
- **Phase 3** 串接入口、遷移大型既有測試、整頁煙霧測試與實機視覺檢查。

---

## Phase 1 — 基石

### Task 1: `dashboard_ui` 套件與 `theme.py`

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/__init__.py`
- Create: `src/taiwan_stock_analysis/dashboard_ui/theme.py`
- Test: `tests/test_dashboard_ui_theme.py`

**Interfaces:**
- Produces: `TOKENS: dict[str, str]`；`base_css() -> str`

- [ ] **Step 1: 建立套件目錄與空 `__init__.py`**

Create `src/taiwan_stock_analysis/dashboard_ui/__init__.py`（內容留空一行）。

- [ ] **Step 2: 寫失敗測試**

Create `tests/test_dashboard_ui_theme.py`:

```python
import unittest

from taiwan_stock_analysis.dashboard_ui.theme import TOKENS, base_css


class ThemeTests(unittest.TestCase):
    def test_tokens_have_required_keys(self):
        for key in ("bg", "panel", "accent", "up", "down", "blocked", "warn", "ok", "border"):
            self.assertIn(key, TOKENS)
        self.assertEqual(TOKENS["bg"], "#050810")
        self.assertEqual(TOKENS["accent"], "#2ee0f7")

    def test_base_css_embeds_token_values_and_core_selectors(self):
        css = base_css()
        self.assertIn("#050810", css)          # bg
        self.assertIn(".chart-hbar-fill.up", css)
        self.assertIn(".chart-hbar-fill.down", css)
        self.assertIn(".ui-pill", css)
        self.assertIn(".ui-tab", css)
        self.assertIn("tabular-nums", css)

    def test_base_css_is_deterministic(self):
        self.assertEqual(base_css(), base_css())
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_theme -v`
Expected: FAIL（`ModuleNotFoundError: dashboard_ui.theme`）

- [ ] **Step 4: 實作 `theme.py`**

```python
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
```

- [ ] **Step 5: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_theme -v`
Expected: PASS（3 tests）

- [ ] **Step 6: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/__init__.py src/taiwan_stock_analysis/dashboard_ui/theme.py tests/test_dashboard_ui_theme.py
git commit -m "feat: add dashboard_ui theme tokens and base css"
```

---

### Task 2: `charts.py` — `sparkline`

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/charts.py`
- Test: `tests/test_dashboard_ui_charts.py`

**Interfaces:**
- Consumes: `TOKENS`（from Task 1）
- Produces: `sparkline(values: list, *, width: int = 320, height: int = 64) -> str`

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_dashboard_ui_charts.py`:

```python
import unittest

from taiwan_stock_analysis.dashboard_ui.charts import sparkline


class SparklineTests(unittest.TestCase):
    def test_renders_svg_line_and_endpoint_for_multiple_points(self):
        out = sparkline([30.6, 30.1, 29.4, 29.1])
        self.assertIn("<svg", out)
        self.assertIn("#2ee0f7", out)          # accent stroke
        self.assertIn("<circle", out)          # end point
        self.assertIn('role="img"', out)

    def test_placeholder_when_fewer_than_two_points(self):
        self.assertNotIn("<svg", sparkline([29.1]))
        self.assertIn("歷史資料不足", sparkline([29.1]))
        self.assertIn("歷史資料不足", sparkline([]))

    def test_ignores_non_finite_values(self):
        out = sparkline([1.0, float("nan"), 2.0, float("inf")])
        self.assertIn("<svg", out)             # 2 finite points remain

    def test_deterministic(self):
        self.assertEqual(sparkline([1.0, 2.0, 3.0]), sparkline([1.0, 2.0, 3.0]))
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_charts -v`
Expected: FAIL（`ModuleNotFoundError` / `ImportError: sparkline`）

- [ ] **Step 3: 實作 `sparkline`（建立 `charts.py`）**

```python
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
    step = width / (len(points) - 1)
    pad = 4
    coords = []
    for i, v in enumerate(points):
        x = round(i * step, 2)
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_charts -v`
Expected: PASS（4 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/charts.py tests/test_dashboard_ui_charts.py
git commit -m "feat: add sparkline chart"
```

---

### Task 3: `charts.py` — `signed_hbar`

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard_ui/charts.py`
- Test: `tests/test_dashboard_ui_charts.py`

**Interfaces:**
- Produces: `signed_hbar(value, max_abs, *, height: int = 16) -> str`（正值→`up` class，負值→`down` class，寬度百分比 = |value|/max_abs 上限 100%）

- [ ] **Step 1: 追加失敗測試**

Append to `tests/test_dashboard_ui_charts.py`:

```python
from taiwan_stock_analysis.dashboard_ui.charts import signed_hbar


class SignedHbarTests(unittest.TestCase):
    def test_positive_uses_up_class(self):
        out = signed_hbar(5900, 5900)
        self.assertIn("chart-hbar-fill up", out)
        self.assertIn("width:100%", out)

    def test_negative_uses_down_class(self):
        out = signed_hbar(-800, 5900)
        self.assertIn("chart-hbar-fill down", out)

    def test_zero_and_none_and_zero_maxabs_render_empty_track(self):
        for out in (signed_hbar(0, 5900), signed_hbar(None, 5900), signed_hbar(100, 0)):
            self.assertIn("width:0%", out)

    def test_caps_at_100_percent(self):
        self.assertIn("width:100%", signed_hbar(99999, 100))
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_charts.SignedHbarTests -v`
Expected: FAIL（`ImportError: signed_hbar`）

- [ ] **Step 3: 追加 `signed_hbar` 到 `charts.py`**

```python
def signed_hbar(value, max_abs, *, height: int = 16) -> str:
    valid = (
        isinstance(value, (int, float))
        and isfinite(value)
        and isinstance(max_abs, (int, float))
        and max_abs
    )
    if not valid:
        return '<div class="chart-hbar"><span class="chart-hbar-fill" style="width:0%"></span></div>'
    pct = min(abs(value) / abs(max_abs) * 100, 100)
    cls = "up" if value >= 0 else "down"
    return f'<div class="chart-hbar"><span class="chart-hbar-fill {cls}" style="width:{pct:.0f}%"></span></div>'
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_charts -v`
Expected: PASS（8 tests 累計）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/charts.py tests/test_dashboard_ui_charts.py
git commit -m "feat: add signed horizontal bar chart"
```

---

### Task 4: `charts.py` — `contribution_bars`

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard_ui/charts.py`
- Test: `tests/test_dashboard_ui_charts.py`

**Interfaces:**
- Produces: `contribution_bars(rows: list) -> str`（每列 `(label, value, max_abs)`；輸出 label、accent 軌道、`+/-` 一位小數數值）

- [ ] **Step 1: 追加失敗測試**

Append:

```python
from taiwan_stock_analysis.dashboard_ui.charts import contribution_bars


class ContributionBarsTests(unittest.TestCase):
    def test_renders_one_row_per_input_with_signed_values(self):
        out = contribution_bars([("新聞", 0.0, 26.6), ("價格", 2.5, 26.6), ("資金流", 26.6, 26.6)])
        self.assertEqual(out.count("chart-contrib-row"), 3)
        self.assertIn("+0.0", out)
        self.assertIn("+26.6", out)
        self.assertIn("新聞", out)

    def test_escapes_label(self):
        self.assertIn("&lt;x&gt;", contribution_bars([("<x>", 1.0, 1.0)]))

    def test_zero_maxabs_yields_zero_width(self):
        self.assertIn("width:0%", contribution_bars([("a", 5.0, 0)]))
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_charts.ContributionBarsTests -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 追加 `contribution_bars`**

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_charts -v`
Expected: PASS（11 tests 累計）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/charts.py tests/test_dashboard_ui_charts.py
git commit -m "feat: add contribution bars chart"
```

---

### Task 5: `charts.py` — `progress_bar`

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard_ui/charts.py`
- Test: `tests/test_dashboard_ui_charts.py`

**Interfaces:**
- Produces: `progress_bar(done: int, total: int) -> str`（`total==0` → 空字串；否則寬度 = done/total）

- [ ] **Step 1: 追加失敗測試**

Append:

```python
from taiwan_stock_analysis.dashboard_ui.charts import progress_bar


class ProgressBarTests(unittest.TestCase):
    def test_empty_when_total_zero(self):
        self.assertEqual(progress_bar(0, 0), "")

    def test_zero_done(self):
        self.assertIn("width:0%", progress_bar(0, 11))

    def test_full_done(self):
        self.assertIn("width:100%", progress_bar(11, 11))

    def test_clamps_over_100(self):
        self.assertIn("width:100%", progress_bar(20, 11))
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_charts.ProgressBarTests -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 追加 `progress_bar`**

```python
def progress_bar(done: int, total: int) -> str:
    if not total:
        return ""
    pct = min(max(done / total * 100, 0), 100)
    return f'<div class="chart-progress"><span style="width:{pct:.0f}%"></span></div>'
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_charts -v`
Expected: PASS（15 tests 累計）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/charts.py tests/test_dashboard_ui_charts.py
git commit -m "feat: add gate progress bar chart"
```

---

### Task 6: `components.py` — 共用 HTML 元件

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/components.py`
- Test: `tests/test_dashboard_ui_components.py`

**Interfaces:**
- Produces:
  - `esc(value) -> str`（`html.escape(str(value))`）
  - `pill(text, *, tone="info") -> str`；`badge(text, *, tone="info") -> str`（tone ∈ {info,blocked,warn,ok}，非法值退回 info）
  - `card(title, body_html, *, wide=False) -> str`
  - `copy_button(label, command) -> str`（帶 `data-copy` 屬性的 `<button>`）

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_dashboard_ui_components.py`:

```python
import unittest

from taiwan_stock_analysis.dashboard_ui.components import badge, card, copy_button, esc, pill


class ComponentsTests(unittest.TestCase):
    def test_esc_escapes_and_stringifies(self):
        self.assertEqual(esc("<a>"), "&lt;a&gt;")
        self.assertEqual(esc(11), "11")

    def test_pill_tone_class_and_escaped_text(self):
        self.assertIn("ui-pill-blocked", pill("阻塞", tone="blocked"))
        self.assertIn("需注意", pill("需注意", tone="warn"))
        self.assertIn("&lt;x&gt;", pill("<x>"))

    def test_pill_invalid_tone_falls_back_to_info(self):
        self.assertIn("ui-pill-info", pill("x", tone="nope"))

    def test_badge_tone_class(self):
        self.assertIn("ui-badge-warn", badge("警示", tone="warn"))

    def test_card_wraps_title_and_body(self):
        out = card("研究池", "<p>body</p>")
        self.assertIn("<h4>研究池</h4>", out)
        self.assertIn("<p>body</p>", out)
        self.assertIn("ui-card", out)

    def test_card_wide_flag(self):
        self.assertIn("ui-card-wide", card("t", "b", wide=True))

    def test_copy_button_puts_command_in_data_attr_escaped(self):
        out = copy_button("複製", 'python -m x "2330"')
        self.assertIn('data-copy=', out)
        self.assertIn("&quot;2330&quot;", out)
        self.assertIn("複製", out)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_components -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 `components.py`**

```python
from __future__ import annotations

from html import escape

_TONES = {"info", "blocked", "warn", "ok"}


def esc(value) -> str:
    return escape(str(value))


def _tone(tone: str) -> str:
    return tone if tone in _TONES else "info"


def pill(text, *, tone: str = "info") -> str:
    return f'<span class="ui-pill ui-pill-{_tone(tone)}">{esc(text)}</span>'


def badge(text, *, tone: str = "info") -> str:
    return f'<span class="ui-badge ui-badge-{_tone(tone)}">{esc(text)}</span>'


def card(title, body_html: str, *, wide: bool = False) -> str:
    cls = "ui-card ui-card-wide" if wide else "ui-card"
    head = f"<h4>{esc(title)}</h4>" if title else ""
    return f'<section class="{cls}">{head}{body_html}</section>'


def copy_button(label, command) -> str:
    return f'<button type="button" class="ui-btn" data-copy="{esc(command)}">{esc(label)}</button>'
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_components -v`
Expected: PASS（7 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/components.py tests/test_dashboard_ui_components.py
git commit -m "feat: add shared dashboard_ui html components"
```

---

## Phase 2 — 分頁 Views（移植既有欄位擷取 → 新版標記）

> 每個 view 是純函式，輸入 `items`（`dict[str, list[dict]]`，鍵見下），輸出 HTML 片段字串。內部欄位擷取可對照移植既有 `dashboard.py` 的對應函式；輸出結構依「必要錨點」，由測試驗收。所有外部字串用 `components.esc`。
>
> **重要**：實作 view 前，先 `Read` 對照的既有 `dashboard.py` 函式，確認 demo JSON 的實際欄位名（`.tmp-v053-preview/*.json` 或 `demo-dist/*.json` 可作實際樣本）。若欄位名與本計畫假設不符，以**實際 JSON 欄位為準**並同步修正測試 fixture。

### Task 7: `views/market.py` — 市場總覽

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/views/__init__.py`
- Create: `src/taiwan_stock_analysis/dashboard_ui/views/market.py`
- Test: `tests/test_dashboard_ui_views.py`

**消費的 `items` 鍵與欄位（以 demo JSON 為準核對）：**
- `market_intelligence_reports[].report`：`industries[]`（`name`、`sentiment.score_5d`、`sentiment.baseline_20d`、`sentiment.delta`、`sentiment.phase`、`sentiment.confidence`、`sentiment.status`、`sentiment.components.{news,price,fund_flow}.contribution`、`sentiment.history[]`、`keywords[]`、`news[]{title,url}`、`fund_flow.{foreign,investment_trust,dealer,total}`）、`quality_gate`、`freshness`
- `industry_trend_reports[].report`：`categories[]`（`name`、`direction`、`change_1d/5d/20d`、`leaders[]`、`laggards[]`）、`as_of`
- **移植對照**（既有 `dashboard.py`）：`_market_intelligence_industry_card`、`_market_intelligence_sentiment`、`_market_intelligence_component`、`_industry_trend_category_card` 的欄位讀取與標籤對映（`_market_intelligence_phase_label` 等）。

**Interfaces:**
- Consumes: `sparkline`、`signed_hbar`、`contribution_bars`（charts）、`pill`、`card`、`esc`（components）、`safe_http_url`（from `taiwan_stock_analysis.news_urls`）
- Produces: `render_market_view(items: dict) -> str`

**必要輸出錨點（測試斷言）：**
- 情緒卡含 `chart-spark`、`chart-contrib-row`×3、階段/信心 pill。
- 法人資金流四列（外資/投信/自營商/合計），買超用 `up`、賣超用 `down`。
- 產業輪動 1D/5D/20D 三列（`signed_hbar`）。
- 關鍵字 chips 與新聞連結（`safe_http_url` 過濾）。
- 缺 MI 或趨勢資料時各自顯示含「尚未」字樣空態，不拋例外。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_dashboard_ui_views.py`:

```python
import unittest

from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view

_MI = {
    "market_intelligence_reports": [{
        "report": {
            "quality_gate": {"status": "ready"},
            "freshness": {"news": "fresh", "price": "fresh", "fund_flow": "fresh"},
            "industries": [{
                "name": "Semiconductor",
                "keywords": ["AI", "CoWoS"],
                "news": [{"title": "台積電 AI 伺服器需求", "url": "https://example.com/a"}],
                "fund_flow": {"foreign": 5900, "investment_trust": 3850, "dealer": -800, "total": 8950},
                "sentiment": {
                    "score_5d": 29.1, "baseline_20d": 30.6, "delta": -1.5,
                    "phase": "consolidation", "confidence": "low", "status": "ready",
                    "history": [30.6, 30.1, 29.4, 29.1],
                    "components": {
                        "news": {"contribution": 0.0}, "price": {"contribution": 2.5},
                        "fund_flow": {"contribution": 26.6},
                    },
                },
            }],
        }
    }],
    "industry_trend_reports": [{
        "report": {
            "as_of": "2026-07-10",
            "categories": [{
                "name": "Semiconductor", "direction": "divergent",
                "change_1d": 0.1, "change_5d": 0.8, "change_20d": 3.5,
                "leaders": ["2330 +11.1%"], "laggards": ["2303 -4.0%"],
            }],
        }
    }],
}


class MarketViewTests(unittest.TestCase):
    def test_renders_sentiment_chart_and_components(self):
        html = render_market_view(_MI)
        self.assertIn("Semiconductor", html)
        self.assertIn("chart-spark", html)                 # sparkline
        self.assertEqual(html.count("chart-contrib-row"), 3)
        self.assertIn("29.1", html)

    def test_fund_flow_uses_market_up_down_grammar(self):
        html = render_market_view(_MI)
        self.assertIn("+5,900", html)                      # foreign buy, formatted
        self.assertIn("-800", html)                        # dealer sell
        self.assertIn("chart-hbar-fill up", html)
        self.assertIn("chart-hbar-fill down", html)

    def test_keywords_and_news_link_escaped_and_safe(self):
        html = render_market_view(_MI)
        self.assertIn("CoWoS", html)
        self.assertIn("https://example.com/a", html)

    def test_empty_items_render_placeholder_not_error(self):
        html = render_market_view({})
        self.assertIn("尚未", html)                         # 空態文字
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_views.MarketViewTests -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 `views/__init__.py`（僅 market）與 `views/market.py`**

`views/__init__.py`（本 task 只匯入 market，Task 8/9 再補）：

```python
from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view

__all__ = ["render_market_view"]
```

實作 `views/market.py` 的 `render_market_view(items)`，依上方「必要輸出錨點」與欄位。實作要點：
- 取 `items.get("market_intelligence_reports", [])` 首筆 `report`；對每個 `industry` 產一張 `card`：
  - 大字 `sentiment["score_5d"]`（`.mono`）＋ `delta`（±號、裸色：`>=0` 用 `up`，否則 `down`）＋基準 `baseline_20d`。
  - `pill` 呈現階段（phase 標籤對映移植自 `dashboard.py:_market_intelligence_phase_label`，例：`consolidation`→`盤整`）與信心（`low`→`低`，tone=warn）。
  - `sparkline(sentiment.get("history", []))`。
  - `m = max((abs(c) for c in 三個 contribution), default=1) or 1`；`contribution_bars([("新聞", news_c, m), ("價格", price_c, m), ("資金流", flow_c, m)])`。
  - 資金流四列：外資/投信/自營商用 `signed_hbar(value, max_abs)`（`max_abs = max(abs(foreign), abs(investment_trust), abs(dealer)) or 1`）＋裸色等寬數字 `f"{v:+,}"`（正紅負綠 class）；合計列同樣著色。
  - 關鍵字：每個 `<span class="chip-btn">{esc(kw)}</span>`。
  - 新聞：`safe_http_url(url)` 通過才輸出 `<a href>`，`esc(title)`。
- 取 `items.get("industry_trend_reports", [])`；對每個 `category` 產輪動列：1D/5D/20D 用 `signed_hbar(change, max_abs)`，`max_abs = max(abs(三個 change)) or 1`；領先/落後字串 `esc`。
- MI 或趨勢任一為空 → 該區塊輸出含「尚未產生」字樣的空態段落。

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_views.MarketViewTests -v`
Expected: PASS（4 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/views/__init__.py src/taiwan_stock_analysis/dashboard_ui/views/market.py tests/test_dashboard_ui_views.py
git commit -m "feat: add market overview view"
```

---

### Task 8: `views/workbench.py` — 研究工作台（統一審查佇列）

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/labels.py`
- Create: `src/taiwan_stock_analysis/dashboard_ui/views/workbench.py`
- Modify: `src/taiwan_stock_analysis/dashboard_ui/views/__init__.py`
- Test: `tests/test_dashboard_ui_views.py`

**消費的 `items` 鍵與欄位（以 demo JSON 為準核對）：**
- `research_summaries[]`：`review_actions[]`（`stock_id`、`priority`、`severity`、`category`、`message`、`status`、`requires_evidence`、`action_id`）、`handoff_gate`（`blocked`、`blocker_count`、`ready`）、`research_pool[]`（`stock_id`、`company_name`、`priority`、`research_state`、`reliability_status`、`attention_reasons`）、`source_path`、`state_path`
- **移植對照**：`dashboard.py` 的 `_expert_console_action_item`、審查動作表列渲染、`_next_action_*`、CLI 指令字串產生。**標籤/嚴重度常數改放進新 leaf 模組 `dashboard_ui/labels.py`**（不從 `dashboard` import，避免 `dashboard → page → workbench → dashboard` 循環）。

**Interfaces:**
- Consumes: `pill`、`badge`、`card`、`copy_button`、`esc`（components）、`progress_bar`（charts）、`REVIEW_ACTION_SEVERITIES`、`REVIEW_ACTION_CATEGORY_LABELS`、`REVIEW_ACTION_PRIORITY_LABELS`、`REVIEW_ACTION_SEVERITY_LABELS`、`REVIEW_ACTION_STATUS_LABELS`（from **`dashboard_ui.labels`**）
- Produces: `render_workbench_view(items: dict, *, action_api_enabled: bool = False) -> str`；`dashboard_ui/labels.py` 匯出上述四個常數（值與現有 `dashboard.py` 模組級常數完全相同）

**必要輸出錨點（測試斷言）：**
- 交接 GATE 卡：阻塞件數、`chart-progress`、主按鈕「處理建議下一步」、「產出 Evidence Pack」。
- 唯一 `class="queue"`；每筆 action 一個 `queue-row`；第一列（排序後最高優先）帶 `queue-row next` 與「建議下一步」字樣。
- 每列 `data-stock`、`data-severity`、`data-category`、`data-priority`、`data-status`。
- 展開列 `queue-expand` 含證據三輸入（`note`/`reviewer`/`evidence`）與「標記完成/稍後處理/不處理」按鈕。
- 靜態模式：操作按鈕帶 `data-copy`；`action_api_enabled=True` 時帶 `data-action-api`。
- 研究池單一 `mini-table`。
- 0 筆待辦 → 佇列空態「無待辦」＋GATE pill 轉 `ok`（`ui-pill-ok`）。

- [ ] **Step 1: 追加失敗測試**

Append to `tests/test_dashboard_ui_views.py`:

```python
from taiwan_stock_analysis.dashboard_ui.views.workbench import render_workbench_view

_RS = {
    "research_summaries": [{
        "source_path": "research_summary.json",
        "state_path": "review_action_state.json",
        "handoff_gate": {"blocked": True, "blocker_count": 11, "ready": False},
        "research_pool": [
            {"stock_id": "2330", "company_name": "TSMC", "priority": "high",
             "research_state": "review", "reliability_status": "warning",
             "attention_reasons": ["needs review"]},
        ],
        "review_actions": [
            {"stock_id": "2330", "priority": "high", "severity": "manual_review",
             "category": "fundamental_review", "message": "確認 thesis breaker",
             "status": "open", "requires_evidence": True, "action_id": "a1"},
            {"stock_id": "2303", "priority": "medium", "severity": "info",
             "category": "valuation", "message": "估值輸出缺失",
             "status": "open", "requires_evidence": False, "action_id": "a2"},
        ],
    }]
}


class WorkbenchViewTests(unittest.TestCase):
    def test_gate_card_shows_blocker_count_and_progress(self):
        html = render_workbench_view(_RS)
        self.assertIn("11", html)
        self.assertIn("chart-progress", html)
        self.assertIn("處理建議下一步", html)
        self.assertIn("產出 Evidence Pack", html)

    def test_single_queue_first_row_is_next_action_high_priority_first(self):
        html = render_workbench_view(_RS)
        self.assertEqual(html.count('class="queue"'), 1)
        self.assertNotEqual(html.find("queue-row next"), -1)
        self.assertLess(html.find("2330"), html.find("2303"))   # high before medium
        self.assertIn("建議下一步", html)

    def test_rows_carry_filter_data_attributes(self):
        html = render_workbench_view(_RS)
        self.assertIn('data-priority="high"', html)
        self.assertIn('data-category="fundamental_review"', html)
        self.assertIn('data-severity="manual_review"', html)

    def test_expand_row_has_evidence_inputs_and_actions(self):
        html = render_workbench_view(_RS)
        self.assertIn("queue-expand", html)
        self.assertIn("reviewer", html)
        self.assertIn("標記完成", html)

    def test_static_mode_uses_data_copy_served_mode_uses_action_api(self):
        self.assertIn("data-copy", render_workbench_view(_RS, action_api_enabled=False))
        self.assertIn("data-action-api", render_workbench_view(_RS, action_api_enabled=True))

    def test_no_open_actions_shows_empty_state_and_ok_gate(self):
        empty = {"research_summaries": [{
            "handoff_gate": {"blocked": False, "blocker_count": 0, "ready": True},
            "review_actions": [], "research_pool": [],
            "source_path": "x", "state_path": "y",
        }]}
        html = render_workbench_view(empty)
        self.assertIn("無待辦", html)
        self.assertIn("ui-pill-ok", html)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_views.WorkbenchViewTests -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 建立 `labels.py`，實作 `views/workbench.py` 並更新 `views/__init__.py`**

先建立 `src/taiwan_stock_analysis/dashboard_ui/labels.py`，把下列常數的**確切值**從現有 `dashboard.py`（line 21–66）複製過來（是純資料、無依賴）：

```python
from __future__ import annotations

REVIEW_ACTION_SEVERITIES = ("error", "stale", "unknown", "manual_review", "warning", "info")
REVIEW_ACTION_PRIORITIES = ("high", "medium", "low")
REVIEW_ACTION_SEVERITY_LABELS = {
    "error": "錯誤", "stale": "資料過期", "unknown": "狀態不明",
    "manual_review": "需人工確認", "warning": "需注意", "info": "提醒",
}
REVIEW_ACTION_CATEGORY_LABELS = {
    "source_audit": "來源檢查", "workflow": "工作流程", "reliability": "資料可信度",
    "valuation": "估值", "research_quality": "研究品質", "fundamental_review": "基本面專家審查",
}
REVIEW_ACTION_PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
REVIEW_ACTION_STATUS_LABELS = {
    "open": "待處理", "done": "已完成", "deferred": "稍後處理", "ignored": "不處理",
}
```

（狀態鍵 `open/done/deferred/ignored` 對應 `review_action_state.ACTION_STATUSES`；此處用字面 dict 保持 leaf 無依賴。若要防漂移，可在 `labels.py` 加一條 `assert set(REVIEW_ACTION_STATUS_LABELS) == set(ACTION_STATUSES)` 的匯入檢查，但非必要。）

`views/__init__.py` 追加 `from taiwan_stock_analysis.dashboard_ui.views.workbench import render_workbench_view` 並加進 `__all__`。

實作 `render_workbench_view(items, *, action_api_enabled=False)`，依「必要輸出錨點」。標籤/嚴重度常數 `from taiwan_stock_analysis.dashboard_ui.labels import ...`。要點：
- 取 `research_summaries` 首筆（無則整體空態）。
- **GATE 卡**：`handoff_gate["blocker_count"]`；`progress_bar(done, total)`，`total = len(review_actions)`、`done = sum(1 for a in review_actions if a["status"] != "open")`；`pill` 依 `blocked` 用 `blocked`/`ok` tone；兩顆 `ui-btn primary`：「⚡ 處理建議下一步」「產出 Evidence Pack」。
- **排序**：`priority_rank = {"high":0,"medium":1,"low":2}`；`severity_rank = REVIEW_ACTION_SEVERITIES.index(sev)`；`sorted(actions, key=lambda a:(priority_rank.get(a["priority"],9), severity_rank(a["severity"])))`。
- **佇列**：`<div class="queue">`＋表頭；每筆 `<div class="queue-row" data-stock=… data-priority=… data-severity=… data-category=… data-status=…>`；index 0 額外 `next` class＋「建議下一步」標記。欄位：股票（`.mono`）、優先 `badge`（`REVIEW_ACTION_PRIORITY_LABELS`）、嚴重度 `badge`（tone 對映：`manual_review`/`error`→blocked、`warning`/`stale`→warn、`info`/`unknown`→info；文字用 `REVIEW_ACTION_SEVERITY_LABELS`）、類別（`REVIEW_ACTION_CATEGORY_LABELS`）、`esc(message)`、展開鈕。
- **展開列** `queue-expand`：問題全文；`requires_evidence` 為真時三個 `<input>`（placeholder `note：處理說明`/`reviewer：覆核人`/`evidence：檔案路徑或 URL`）；三顆操作按鈕。
  - `action_api_enabled=False`：按鈕 `data-copy="<CLI 指令>"`（移植既有指令產生，含 `source_path`、`state_path`、`action_id`、目標 `status`）。
  - `action_api_enabled=True`：按鈕帶 `data-action-api` 與 `data-action-id`、`data-status`。
- **研究池**：單一 `<table class="mini-table">`（股票、優先、研究狀態、可信度 `badge`、注意原因、報告連結）。
- 0 筆 open → 佇列「無待辦」空態、GATE pill 用 `ok` tone。
- 外部字串全 `esc`。

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_views.WorkbenchViewTests -v`
Expected: PASS（6 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/labels.py src/taiwan_stock_analysis/dashboard_ui/views/workbench.py src/taiwan_stock_analysis/dashboard_ui/views/__init__.py tests/test_dashboard_ui_views.py
git commit -m "feat: add research workbench view with unified review queue"
```

---

### Task 9: `views/outputs.py` — 產出與紀錄

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/views/outputs.py`
- Modify: `src/taiwan_stock_analysis/dashboard_ui/views/__init__.py`
- Test: `tests/test_dashboard_ui_views.py`

**消費的 `items` 鍵與欄位（以 demo JSON 為準核對）：**
- `reports[]`（`stock_id`、`html_path`、`json_path`）、`comparisons[]`（`html_path`、`json_path`）、`memo_outputs[]`、`pack_outputs[]`、`handoff_pack_outputs[]`、`workflow_summaries[]`、`batch_summaries[]`（`results[]{stock_id,status,error}`）、`market_data_reports[]`。
- **移植對照**：`dashboard.py` 報告連結表、`_market_data_section`、workflow/批次/來源稽核表渲染、常用指令區、watchlist data URI 常數。

**Interfaces:**
- Consumes: `card`、`copy_button`、`esc`
- Produces: `render_outputs_view(items: dict, *, action_api_enabled: bool = False) -> str`

**必要輸出錨點（測試斷言）：**
- 個股報告連結（HTML/JSON）、同業比較連結。
- Workflow/批次/可信度/來源稽核 `mini-table`（各以 `table-scroll` 包裹）。
- 常用指令三段＋`copy_button`＋watchlist CSV `data:text/csv` 範本。
- 各區塊無資料 → 含「尚未」空態，不拋例外。

- [ ] **Step 1: 追加失敗測試**

Append:

```python
from taiwan_stock_analysis.dashboard_ui.views.outputs import render_outputs_view

_OUT = {
    "reports": [{"stock_id": "2330", "html_path": "reports/2330_analysis.html", "json_path": "reports/2330_raw_data.json"}],
    "comparisons": [{"html_path": "comparison/comparison.html", "json_path": "comparison/comparison.json"}],
    "workflow_summaries": [{"path": "workflow_summary.json", "successful_stock_ids": ["2330", "2303"]}],
    "batch_summaries": [{"path": "reports/batch_summary.json", "results": [{"stock_id": "2330", "status": "ok"}]}],
}


class OutputsViewTests(unittest.TestCase):
    def test_lists_report_and_comparison_links(self):
        html = render_outputs_view(_OUT)
        self.assertIn("2330_analysis.html", html)
        self.assertIn("comparison.html", html)

    def test_includes_command_snippets_with_copy_and_watchlist_template(self):
        html = render_outputs_view(_OUT)
        self.assertIn("data-copy", html)
        self.assertIn("data:text/csv", html)
        self.assertIn("python -m taiwan_stock_analysis.cli", html)

    def test_status_tables_scroll_wrapped(self):
        html = render_outputs_view(_OUT)
        self.assertIn("table-scroll", html)
        self.assertIn("mini-table", html)

    def test_empty_items_render_placeholders(self):
        html = render_outputs_view({})
        self.assertIn("尚未", html)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_views.OutputsViewTests -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 實作 `views/outputs.py` 並更新 `views/__init__.py`**

`views/__init__.py` 補 `render_outputs_view` 匯入與 `__all__`。

實作 `render_outputs_view(items, *, action_api_enabled=False)`。要點：
- 產出檔案卡：`reports`（stock_id＋HTML/JSON 連結）、`comparisons`、`memo_outputs`、`pack_outputs`、`handoff_pack_outputs`；每類無資料顯示「尚未產生…」列。
- 狀態表（各 `<div class="table-scroll"><table class="mini-table">`）：Workflow 狀態、批次狀態（`results[]` stock_id/status/error）、資料可信度、來源稽核，欄位沿用既有。
- `market_data_reports` 存在才輸出對應表。
- 常用指令三段（單一個股／同業比較／批次）各配 `copy_button(label, command)`；watchlist 範本**直接在 `outputs.py` 內以字面值 inline**（`"data:text/csv;charset=utf-8,stock_id%2Ccompany_name%0A2330%2C..."`，值同 `dashboard.py:327`），不從 `dashboard` import 以免製造 import 循環邊。
- 連結/路徑全 `esc`。

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_views.OutputsViewTests -v`
Expected: PASS（4 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/views/outputs.py src/taiwan_stock_analysis/dashboard_ui/views/__init__.py tests/test_dashboard_ui_views.py
git commit -m "feat: add outputs and records view"
```

---

## Phase 3 — 頁殼組裝與整合

### Task 10: `page.py` — 頁殼（狀態列＋頁籤＋三 view＋頁尾＋inline JS）

**Files:**
- Create: `src/taiwan_stock_analysis/dashboard_ui/page.py`
- Test: `tests/test_dashboard_ui_views.py`（新增 `PageTests`）

**Interfaces:**
- Consumes: `base_css`（theme）、`render_market_view`、`render_workbench_view`、`render_outputs_view`、`pill`、`esc`
- Produces: `render(items: dict, *, action_api_enabled: bool = False) -> str`（完整 `<!DOCTYPE html>` 文件）

**必要輸出錨點（測試斷言）：**
- `<title>台股基本面儀表板</title>`。
- 頂部狀態列：交接 Gate pill、待辦數 pill、鮮度三點。
- 三個 `<button class="ui-tab">`＋三個 `<section class="ui-panel">`（market/workbench/outputs），market 預設 `active`。
- 頁尾唯一一處免責聲明（字串「不構成投資建議」恰好一次）。
- inline `<script>`：tab 切換（hash 記憶）、佇列篩選、展開/收合、`data-copy` 複製、`data-action-api` 分流。
- 全文無外部資源（無 `<link>`、無 `cdn`、無 `googleapis`）。

- [ ] **Step 1: 追加失敗測試**

Append to `tests/test_dashboard_ui_views.py`:

```python
from taiwan_stock_analysis.dashboard_ui.page import render as render_page


class PageTests(unittest.TestCase):
    def _items(self):
        d = {}
        d.update(_MI)
        d.update(_RS)
        d.update(_OUT)
        return d

    def test_full_document_structure(self):
        html = render_page(self._items())
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>台股基本面儀表板</title>", html)
        self.assertEqual(html.count('class="ui-tab"'), 3)
        self.assertIn('class="ui-panel active"', html)      # market default

    def test_single_disclaimer(self):
        self.assertEqual(render_page(self._items()).count("不構成投資建議"), 1)

    def test_topbar_status_pills_present(self):
        html = render_page(self._items())
        self.assertIn("交接", html)
        self.assertIn("待辦", html)

    def test_offline_no_external_asset_tags(self):
        html = render_page(self._items())
        self.assertNotIn("cdn", html.lower())
        self.assertNotIn("<link", html)
        self.assertNotIn("googleapis", html)

    def test_inline_script_has_tab_and_copy_handlers(self):
        html = render_page(self._items())
        self.assertIn("<script>", html)
        self.assertIn("data-copy", html)
        self.assertIn("ui-tab", html)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `python -m unittest tests.test_dashboard_ui_views.PageTests -v`
Expected: FAIL（`ModuleNotFoundError: page`）

- [ ] **Step 3: 實作 `page.py`**

實作 `render(items, *, action_api_enabled=False)`：
- `_topbar(items)`：從 `research_summaries[0].handoff_gate` 取 `blocker_count`→Gate pill（`blocked`/`ok` tone、文字「交接 Gate：阻塞 N 件」或「可交接」）；待辦數 pill（open action 數）；鮮度三點（MI `freshness` 三鍵，`fresh`→ok 綠點、否則 warn）。無 `research_summaries`/MI 時給安全預設。
- 三個 `<button class="ui-tab" data-tab="market|workbench|outputs">`，market 加 `active`。
- 三個 `<section class="ui-panel" id="market|workbench|outputs">`，market 加 `active`，內容為三 view 回傳（workbench/outputs 傳入 `action_api_enabled`）。
- 頁尾 `<footer class="disclaimer">…不構成投資建議…</footer>`（唯一）。
- `<head>`：`<meta charset>`、`<meta viewport>`、`<title>台股基本面儀表板</title>`、`<style>{base_css()}</style>`。
- 頁尾前 `<script>`（vanilla、無依賴）：
  - tab 切換：點 `.ui-tab` → 切 active、對應 panel 顯示、寫 `location.hash`；載入讀 hash 還原。
  - 篩選：讀 `.filters` select/input＋chip → 對 `.queue-row[data-*]` 加/移 `hidden` class。
  - 展開/收合：toggle 對應 `.queue-expand`。
  - 複製：`[data-copy]` → `navigator.clipboard.writeText`。
  - served：`[data-action-api]` → `fetch` 既有端點（沿用 `dashboard_server` 路徑），成功後就地更新該列狀態與計數。
- 不得出現 `<link>`、CDN、外部字型。

- [ ] **Step 4: 執行測試確認通過**

Run: `python -m unittest tests.test_dashboard_ui_views.PageTests -v`
Expected: PASS（5 tests）

- [ ] **Step 5: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard_ui/page.py tests/test_dashboard_ui_views.py
git commit -m "feat: assemble dashboard page shell with tabs and inline js"
```

---

### Task 11: 串接入口並遷移既有 dashboard 測試

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard.py`（`render_dashboard_html` 改委派；移除舊 `_*` 渲染 helper）
- Modify: `tests/test_dashboard.py`（render 測試遷移到新結構）
- Modify: `tests/test_dashboard_server.py`（若有舊字串斷言，改新錨點）

**Interfaces:**
- `render_dashboard_html(items, *, action_api_enabled=False) -> str` 簽名不變，內部呼叫 `dashboard_ui.page.render`。

- [ ] **Step 1: 先跑既有 dashboard 測試建立基準**

Run: `python -m unittest tests.test_dashboard -v`
Expected: 目前全數 PASS（記下數量，作為遷移後對照）。

- [ ] **Step 2: 改 `render_dashboard_html` 為委派**

在 `dashboard.py` 頂部 import 區新增：

```python
from taiwan_stock_analysis.dashboard_ui.page import render as _render_dashboard_page
```

把 `render_dashboard_html`（line 313 起）整個函式本體換成：

```python
def render_dashboard_html(items: DashboardItems, *, action_api_enabled: bool = False) -> str:
    return _render_dashboard_page(items, action_api_enabled=action_api_enabled)
```

- [ ] **Step 3: 移除已死的舊渲染 helper**

刪除 `dashboard.py` 中只被舊 `render_dashboard_html` 內文呼叫、現已無用的 `_*` **HTML 渲染** 函式（`_expert_agent_console_section`、`_market_intelligence_block`、`_industry_trend_report_block`、`_next_action_*`、`_expert_console_*` 等整批）。**保留**：`discover_dashboard_items` 及其 `_discover_*`、`write` 路徑（line ~5113）。

**避免重複定義（DRY）**：`dashboard.py` 原本的 review-action 標籤常數（line 21–66）已在 Task 8 移到 `dashboard_ui/labels.py`。把 `dashboard.py` 的這些定義改成 re-export，讓外部呼叫端仍可 `from ...dashboard import REVIEW_ACTION_SEVERITY_LABELS`：

```python
from taiwan_stock_analysis.dashboard_ui.labels import (
    REVIEW_ACTION_CATEGORY_LABELS,
    REVIEW_ACTION_PRIORITIES,
    REVIEW_ACTION_PRIORITY_LABELS,
    REVIEW_ACTION_SEVERITIES,
    REVIEW_ACTION_SEVERITY_LABELS,
)
```

（`labels.py` 是 leaf、不 import 任何內部模組，故 `dashboard → labels` 與 `dashboard → page → workbench → labels` 皆無循環。若 `dashboard.py` 尚有其他自身邏輯用到 `EXPERT_AGENT_LABELS` 等未搬移常數，保留原定義即可。）

- [ ] **Step 4: import 與 render 煙霧測試**

Run:
```bash
python -c "from taiwan_stock_analysis.dashboard import render_dashboard_html, discover_dashboard_items; print(render_dashboard_html({})[:15])"
```
Expected: 印出 `<!DOCTYPE html>`（前 15 字），無 ImportError/NameError。

- [ ] **Step 5: 遷移 `tests/test_dashboard.py` 的 render 斷言**

保留 `discover_dashboard_items` 相關測試不動。把各 `test_render_dashboard_html_*` 斷言從舊區塊字串改為新結構錨點：
- 報告/比較連結：仍斷言 `2330_analysis.html`、`comparison.html`。
- 空態：`test_render_dashboard_html_shows_clear_empty_states` 改斷言「尚未」空態文字仍存在。
- 來源稽核/workflow/批次：斷言對應 `mini-table` 內含既有欄位值。
- 移除只驗證舊版特定 class（`expert-console-grid`、`industry-map-card` 等）的斷言，改驗證等義新錨點（`queue`、`ui-tab`、`chart-*`、`ui-panel`）。

- [ ] **Step 6: 跑 dashboard 測試確認通過**

Run: `python -m unittest tests.test_dashboard -v`
Expected: PASS。

- [ ] **Step 7: 跑 dashboard_server 測試確認 served 行為未破壞**

Run: `python -m unittest tests.test_dashboard_server -v`
Expected: PASS（`action_api_enabled=True` 路徑仍產出頁面；若斷言舊字串，比照 Step 5 改新錨點）。

- [ ] **Step 8: 提交**

```bash
git add src/taiwan_stock_analysis/dashboard.py tests/test_dashboard.py tests/test_dashboard_server.py
git commit -m "refactor: delegate dashboard render to dashboard_ui and migrate tests"
```

---

### Task 12: 全套件測試、demo 產出與實機視覺檢查

**Files:**
- Test: 全 `tests/`
- 產物驗證：`demo-dist/dashboard.html`

- [ ] **Step 1: 跑整套測試**

Run: `python -m unittest discover -s tests -v`
Expected: 全數 PASS。

- [ ] **Step 2: 產出 demo dashboard**

Run: `python -m taiwan_stock_analysis.cli demo quickstart`
Expected: 印出 dashboard 路徑，無例外。

- [ ] **Step 3: demo doctor 驗證交付檔完整**

Run: `python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist`
Expected: 通過（readiness OK）。

- [ ] **Step 4: 實機視覺檢查（三分頁）**

用瀏覽器開 `demo-dist/dashboard.html`（`file://`，以 `mcp__Claude_Browser__preview_start` 開檔＋截圖）：
- 市場總覽：情緒 sparkline、資金流紅漲綠跌、輪動橫條正常。
- 研究工作台：單一佇列、第一列「建議下一步」、展開列證據欄、篩選可用、複製鈕複製 CLI。
- 產出與紀錄：連結可點、指令可複製。
- 頁尾免責聲明只有一處；切分頁不跳頁；縮到 <900px 不橫向溢出。

- [ ] **Step 5: 確認離線純淨（無外部資源）**

Run:
```bash
python -c "h=open('demo-dist/dashboard.html',encoding='utf-8').read(); assert '<link' not in h and 'cdn' not in h.lower() and 'googleapis' not in h; print('offline-ok len=',len(h))"
```
Expected: 印出 `offline-ok`。

- [ ] **Step 6: 更新 CHANGELOG 與 README**

在 `CHANGELOG.md` 新增一則 feat 條目描述儀表板重設計；README「What It Does」相關敘述若有對應則同步。

- [ ] **Step 7: 最終提交**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: note dashboard redesign in changelog"
```

---

## Self-Review 對照（spec §→task）

- §3.1 狀態列 → Task 10（topbar）
- §3.2 市場總覽（情緒/資金流/輪動/新聞/圖表）→ Task 7 + charts 2–4
- §3.3 工作台（GATE/統一佇列/建議下一步/證據/研究池）→ Task 8 + charts 5
- §3.4 產出與紀錄 → Task 9
- §3.5 合併/移除重複區塊 → Task 8（佇列取代 Console/Top3/證據看板）、Task 10（單一免責）、Task 11（刪舊 helper）
- §4 視覺 tokens/字級/卡片 → Task 1
- §5 四個 SVG 圖表 → Task 2–5
- §6 靜態/伺服雙模式行為 → Task 8（data-copy/data-action-api）、Task 10（JS 分流）
- §7 dashboard_ui 套件與委派 → Task 1、10、11
- §8 錯誤處理（空態、非有限值）→ 各 view 空態測試 + charts 邊界測試
- §9 測試策略 → 每 task TDD + Task 12 整合
- §10 功能保留清單 → Task 8/9 錨點測試 + Task 11 遷移測試 + Task 12 實機檢查
- §11 決策紀錄 → 已納入 Global Constraints 與各 task
