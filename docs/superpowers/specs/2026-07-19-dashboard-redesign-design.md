# 台股基本面儀表板全面重設計 Design Spec

- 日期：2026-07-19
- 狀態：已與使用者逐段確認（資訊架構、視覺系統 v2、工作台佈局、行為細節、技術架構）
- 範圍：`dashboard.html` 的呈現層（Approach A：呈現層重寫）

## 1. 背景與問題

目前的 dashboard.html 由 `dashboard.py`（5,153 行單一模組）以 f-string 產生，存在四個核心問題：

1. **資訊架構**：18 個區塊直向堆疊成一長頁，重點被淹沒；同一批審查待辦在專家 Console、Top 3 卡片、產業證據看板、審查動作表重複出現 4~5 次，且各處操作方式不一致。
2. **視覺**：白底細框卡片＋徽章的通用後台風格，缺乏金融研究產品質感。
3. **零視覺化**：情緒分數、法人資金流、產業輪動全為純文字數字。
4. **維護性**：呈現邏輯與資料彙整混在同一巨石模組。

## 2. 目標與非目標

**目標**（使用者四項全選）：資訊架構重整、視覺質感升級、功能流程簡化、加入資料視覺化。

**非目標（本階段不做）**：

- 其他 HTML 產出（個股報告、同業比較、備忘錄、研究包、MI 報告）——之後的階段再套用同一設計系統。
- CLI 介面、JSON/CSV 資料格式、資料管線、review-action 資料流——零改動。
- 前端框架、build step、客戶端資料抓取、深淺雙主題（僅深色）。

## 3. 資訊架構（已確認）

單一離線 HTML 檔，內含**固定頂部狀態列＋三個分頁籤**（vanilla JS 切換，`#market` / `#workbench` / `#outputs` hash 記憶狀態，重新整理不跳頁）。

### 3.1 頂部狀態列（跨分頁固定）

- 左：主標「台股研究鏡」＋副標小字「台股基本面儀表板」（HTML `<title>` 維持「台股基本面儀表板」以保留既有測試與書籤相容）＋ run id ＋ 資料來源模式（fixture/live）。
- 右：三顆狀態膠囊——交接 Gate（可交接／阻塞 N 件）、待辦數、資料鮮度（news/flow/price 三顆點燈）。

### 3.2 Tab 1 市場總覽（預設首屏；「先看盤勢」）

- 產業情緒卡（每產業一張）：5D 分數大字＋Δ變化、階段/信心/狀態 chips、情緒走勢 sparkline（取自 sentiment history CSV）、三組件（新聞/價格/資金流）貢獻橫條、情緒預測與轉折風險（含 insufficient history 佔位態）、依據與警告（收合）。
- 產業排序控制（目前 5D 分數／升溫降溫變化／高低點風險等，沿用現有排序選項）。
- 三大法人資金流橫條圖：外資/投信/自營商/合計。
- 產業輪動：1D/5D/20D 帶方向色橫條＋領先/落後個股＋量能。
- 新聞脈絡：關鍵字 chips＋新聞連結列表。
- MI 與產業趨勢報告的 quality gate/freshness/coverage chips 與 HTML/MD/JSON 連結（收成一排小按鈕）。

### 3.3 Tab 2 研究工作台（「再做事」）

- **交接 GATE 卡**：阻塞件數＋已處理進度條＋主按鈕「處理建議下一步」（捲動並展開佇列第一列）＋「產出 Evidence Pack」按鈕（含輸出路徑與缺證據提示，原 Evidence Pack 區功能全數收入）。
- **統一審查佇列**（唯一的待辦呈現處）：
  - 篩選：產業 chips（帶狀態色與件數）、嚴重度/類別/優先度/狀態下拉、搜尋、重設。
  - 預設排序：優先度 → 嚴重度；前三列即原 Top 3。
  - 第一列＝「建議下一步」：青色左邊條＋標記高亮（原下一步工作台功能）。
  - 每列：選取框、股票、優先度、嚴重度、類別、事項摘要、展開/收合。
  - 展開列：問題全文、交付證據三欄（note/reviewer/evidence URL）、標記完成/稍後處理/不處理、served 模式的證據 stub 建立流程、CLI 指令 details（靜態模式）。
  - 批次操作：選取目前顯示、批次標記完成、批次稍後處理（沿用現有行為）。
  - 狀態資訊：待處理/已完成/稍後/不處理計數、stale state 數、最後更新時間。
- **研究池卡**：原本兩張近乎相同的表合併成一張（股票、優先、研究狀態、可信度、注意原因、報告連結）。

### 3.4 Tab 3 產出與紀錄

- 產出檔案卡：個股報告、同業比較、備忘錄、研究包、Handoff Evidence Pack（各列 HTML/MD/JSON 連結；無產出時顯示空態列）。
- 狀態紀錄表：Workflow 狀態、批次狀態、資料可信度、來源稽核（精簡表格，沿用現有欄位）。
- Market data bundle 報告表（存在時顯示）。
- 常用指令：單一個股/同業比較/批次分析指令＋複製鈕＋watchlist CSV 範本下載（data URI）。

### 3.5 被合併／移除的區塊

| 原區塊 | 去向 |
|---|---|
| 專家 Agent Console：下一步工作台 | 工作台 Gate 卡＋佇列置頂「建議下一步」列 |
| 優先處理的 3 件待查事項（Top 3 卡片） | 佇列排序天然前三列 |
| 產業證據看板（每股證據卡） | 佇列展開列的證據欄位 |
| 產業輪動地圖卡片牆＋篩選 | 市場總覽的輪動視覺＋工作台產業 chips 篩選 |
| 6 處黃色免責聲明 | 頁尾單一固定聲明（每分頁底部可見） |
| 研究池兩張重複表 | 工作台單一研究池表 |

## 4. 視覺設計系統（v2 已確認）

**風格**：深色金融終端風（參考 Bloomberg/TradingView），單一深色主題。

**Design tokens**：

| Token | 值 | 用途 |
|---|---|---|
| bg | `#050810` | 頁面底（近黑） |
| panel | `#131f38` | 卡片底 |
| panel-deep | `#0d1526` / `#101a30` | 展開列、表列底 |
| topbar | `#0a1120` | 狀態列/頁籤列/輸入框底 |
| border | `#223050`；亮框 `#2c3d60` | 分隔與卡框 |
| text | `#f2f6fc`；次要 `#c6d4e8` / `#a8bad6`；弱 `#6b7fa3`；極弱 `#4c5f84` | 文字層級 |
| accent | `#2ee0f7`（終端青） | 作用中頁籤、連結、主按鈕、走勢線 |
| market-up | 文字 `#ff7570`、填色 `#f54e4e` | 台股慣例：紅＝漲/買超 |
| market-down | 文字 `#45e69a`、填色 `#34d07e` | 綠＝跌/賣超 |
| status-blocked | `#ff8298`（底 `rgba(244,63,94,.16)`） | 阻塞/需人工確認 |
| status-warn | `#ffc94d`（底 `rgba(245,158,11,.18)`） | 需注意/警示 |
| status-ok | `#34d399`（發光點） | 就緒/新鮮 |

**關鍵原則——市場色與狀態色的視覺文法分離**：市場漲跌永遠是「裸色等寬數字＋▲▼/±號」；workflow 狀態永遠是「帶文字標籤的膠囊/徽章」。兩者絕不混用，避免紅漲綠跌與紅錯綠對互相污染。

**字體**：內文 `"Noto Sans TC", "Microsoft JhengHei", sans-serif`；數字 `"Cascadia Mono", Consolas, monospace`＋`tabular-nums`。全部系統字型，不下載 webfont。

**字級**（v2 放大版）：主數字 42px、次數字 26px、頁籤 15px、內文 14px、標籤 14px（letter-spacing 1px）、輔助 12.5px、註腳 12px。

**卡片**：圓角 10px、亮邊框、陰影 `0 6px 18px rgba(0,0,0,.55)`＋頂部 1px 內光暈 `rgba(255,255,255,.045)`。

## 5. 圖表（`charts.py`，純 Python 產 SVG）

全部由純函式輸出決定性 SVG 字串，內嵌 HTML，零 JS 依賴、零外部函式庫：

| 函式 | 用途 | 空/異常輸入行為 |
|---|---|---|
| `sparkline(values, *, width, height)` | 情緒走勢線＋漸層填底＋端點 | 點數 <2 → 回傳「歷史資料不足」佔位 chip HTML |
| `signed_hbar(value, max_abs, *, direction)` | 法人資金流、輪動 1D/5D/20D | 0/None → 空軌道；非有限值上游已拒絕 |
| `contribution_bars(rows)` | 新聞/價格/資金流貢獻 | 全 0 → 顯示 0 寬條與數值 |
| `progress_bar(done, total)` | Gate 已處理進度 | total 0 → 隱藏 |

規格：`viewBox` 響應式寬度、`role="img"`＋`aria-label`、顏色只用 tokens、輸出字串可直接單元測試。

## 6. 行為與互動

- **靜態模式**（`file://` 開啟）：操作按鈕＝複製對應 CLI 指令，按鈕下方顯示「靜態模式：按下後複製 CLI 指令」提示（沿用現有指令內容）。
- **伺服模式**（`dashboard_server.py`）：同一顆按鈕改打現有 API，成功後**該列就地更新**（狀態徽章/計數/進度條），不再要求整頁重新整理；證據 stub 建立流程保留於展開列。
- 兩模式按鈕外觀一致，僅提示文字不同；模式判定沿用現有 `action_api_enabled` 旗標。
- 分頁切換、佇列篩選、展開/收合、複製、批次選取全部 vanilla inline JS（延續現有 data-attribute 驅動模式）。
- 免責聲明：頁面內容底部固定一處（非 sticky）。
- 響應式：<900px 卡片轉單欄；佇列表格橫向捲動；狀態列膠囊換行。
- 無障礙：現有 focus-visible 外框、aria-label、鍵盤可操作 details/按鈕全數保留；深色下對比至少 AA。

## 7. 技術架構

新增套件 `src/taiwan_stock_analysis/dashboard_ui/`：

```
dashboard_ui/
├── __init__.py
├── theme.py         # design tokens 常數＋base CSS 字串
├── charts.py        # sparkline / signed_hbar / contribution_bars / progress_bar
├── components.py    # pill、badge、card、tabs、copy 按鈕等共用 HTML helper
├── page.py          # 頁殼組裝：狀態列＋頁籤＋三 view＋footer＋inline JS
└── views/
    ├── __init__.py
    ├── market.py    # Tab 1 市場總覽
    ├── workbench.py # Tab 2 研究工作台（統一佇列）
    └── outputs.py   # Tab 3 產出與紀錄
```

- `dashboard.py`：保留 `discover_dashboard_items()` 等資料發現/彙整函式與 `render_dashboard_html(items, *, action_api_enabled)` 入口簽名，內部委派 `dashboard_ui.page.render()`；移除舊渲染私有函式。
- `dashboard_server.py`、CLI、JSON/CSV 格式、review-action state 流程：**零改動**。
- 產出仍為單一離線 HTML（CSS/JS/SVG 全內嵌、無 CDN、無外部資源），檔案大小與現況同量級。
- 所有外部字串照現有慣例 `html.escape` 後輸出。

## 8. 錯誤處理

- 各 view 對缺漏 JSON 欄位沿用現有寬容處理（空態列、「尚未產出」、佔位文字），不得拋例外中斷整頁產生。
- 圖表函式對空列表/None 回傳佔位輸出（見 §5 表）；非有限值由上游既有驗證拒絕。
- 佇列在 0 筆待辦時顯示「無待辦」空態＋Gate 卡轉為可交接綠態。

## 9. 測試策略

1. **charts.py 單元測試**：決定性 SVG 字串斷言；邊界（空、單點、負值、全 0、大值縮放）。
2. **各 view 單元測試**：以合成 items 輸入斷言關鍵內容、escape 行為、空態。
3. **既有 dashboard 測試遷移**：斷言舊區塊/ID 的測試改為斷言新結構（頁籤容器、統一佇列、狀態列）；行為測試（篩選 JS hooks、複製指令內容、served API 標記）對應更新。
4. **整合**：`render_dashboard_html` 以 demo fixtures 產出完整頁面的煙霧測試（含三分頁區塊存在、免責聲明單一出現）。
5. 覆蓋率維持 ≥80%。

## 10. 功能保留清單（重設計後不得遺失）

審查動作標記（完成/稍後/不處理）與 CLI 指令複製、批次標記、狀態計數與 stale 提示、最後更新時間、served 模式 API 更新與證據 stub 建立、Evidence Pack 產出指令與缺證據提示、備忘錄/研究包/Handoff pack/個股報告/同業比較連結、Workflow/批次/可信度/來源稽核表、MI 與產業趨勢報告連結及 gate chips、情緒排序控制、預測與轉折風險（含實驗性標記）、關鍵字與新聞連結、watchlist 範本下載、常用指令、免責聲明（單一處）。

## 11. 決策紀錄

| 決策 | 選項 | 結果 |
|---|---|---|
| 範圍 | 主儀表板 vs 含報告 vs 全部 | 先做主儀表板 |
| 結構 | 單檔分頁籤 vs 側邊導覽 vs 多檔 | 單檔分頁籤 |
| 視覺 | 深色終端 vs 明亮編輯 vs SaaS vs 雙主題 | 深色金融終端風 |
| 強調色 | 終端青 vs 琥珀金 | 終端青 `#2ee0f7` |
| 質感微調 | — | 背景更黑、卡片對比更強、字級放大（v2） |
| 簡化力度 | 大膽合併 vs 分層保留 vs 只換皮 | 大膽合併（單一佇列） |
| 實作路線 | A 呈現層重寫 vs B 換皮 vs C 前端化 | A |
