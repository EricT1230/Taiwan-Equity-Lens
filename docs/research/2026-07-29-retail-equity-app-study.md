# 台美股桌面研究 App：競品、產品與資料架構研究

- 研究日期：2026-07-29
- 目標：以「韭菜畢業班」的引導式決策流程為參考，設計原創桌面版台美股研究工作台
- 證據原則：官方產品頁、官方 App listing、官方教學與資料供應商文件優先；推論另行標示

## 結論

韭菜畢業班真正值得借鏡的不是品牌或單一畫面，而是一條非常短的研究漏斗：

`市場狀態 → 產業主流 → 多空策略 → 候選名單 → 基本面／籌碼／量能複核 → 自選與內容`

桌面版應保留這個順序，但把每個訊號補上來源、時間、延遲、命中理由、風險條件與下一步。產品差異化應是：

> 有來源、有時間、有理由、有下一步的台股桌面研究工作台。

## 1. 韭菜畢業班已證實的內容

官方 App listing 與教學可證實：

- iOS／Android 行動 App；未找到原生 Windows 桌面版。iOS listing 表示 Apple Silicon Mac 可執行 iPhone 版，但尚未針對 macOS 驗證。
- 先看加權與櫃買偏多／偏空，再決定節奏。
- 「市場焦點」以氣氛值排序；教學公開的輸入包含成交金額、即時量比、成本平均、上榜天數與技術型態，但目前完整公式與權重未公開。
- 多方策略包含市場焦點、飆股續攻、回測等上漲；空方有小心震盪。
- 表格包含上榜天數、漲跌幅、氣氛值、即時量比、分點／投信／外資連續買賣、技術突破、預估營收與 EPS。
- 處置頁包含撮合分鐘、處置起訖日與出關提醒。
- 2026 年版加入 240+ 產業／題材、產業供應鏈、產業成分股即時 K 線、個股反查產業與美股資訊。
- 個股頁包含即時資訊、K 線、主力、資券、籌碼集中、預估營收／EPS 與預估本益比河流圖。
- 內容層包含文章、影音、Podcast、社團、VIP 聊天室與語音直播；不能因此推論它是完整的全市場新聞聚合器。
- 採免費下載＋試用＋自動續約。2026-07-29 CMoney 網頁顯示 93 天優惠價 NT$4,800；App Store SKU 仍標示 6,000 元／季，價格可能依通路與活動變動。

主要來源：

- [App Store 產品與版本記錄](https://apps.apple.com/tw/app/%E9%9F%AD%E8%8F%9C%E5%8F%94%E5%8F%94-%E9%9F%AD%E8%8F%9C%E7%95%A2%E6%A5%AD%E7%8F%AD/id6740838438)
- [Google Play 產品說明](https://play.google.com/store/apps/details?hl=zh_TW&id=com.cmoney.productionline.jioutasi)
- [CMoney 產品／訂閱頁](https://www.cmoney.tw/app/itemcontent.aspx?id=6963)
- [官方市場氛圍與多空策略指南](https://www.cmoney.tw/notes/note-detail.aspx?nid=938386)
- [官方市場焦點公式說明](https://www.cmoney.tw/notes/note-detail.aspx?nid=944820)
- [官方投資流程指南](https://www.cmoney.tw/notes/note-detail.aspx?nid=945071)

### 尚未證實

- 氣氛值、加權／櫃買多空、產業燈號的完整公式與版本。
- 即時行情、分點與美股行情的授權商及延遲 SLA。
- 產業圖譜由人工或自動維護、更新頻率與歷史版本。
- 是否有可重現的量化回測、樣本外結果、勝率與最大回撤。
- 是否使用特定前端框架、機器學習、AI 選股或券商下單。

合理但未證實的技術推論是「CMoney 共用金融資料／帳號／訂閱平台＋創作者規則與內容層」，不可當作原始碼或技術棧事實。

## 2. 競品應借鏡什麼

| 產品 | 借鏡能力 | 不應照搬 |
| --- | --- | --- |
| 韭菜畢業班 | 先看盤勢、再選策略、再看個股的引導流程 | 不透明氣氛分數、品牌與策略文案 |
| CMoney 籌碼K線 | 分點、法人、大戶散戶與個股籌碼中心 | 功能與訂閱 SKU 過度分散 |
| 財報狗 | 圖表化財務、亮點風險、產品組合與供應鏈 | 盤中節奏與籌碼較弱，不宜硬塞成看盤終端 |
| Goodinfo | 台股公開資料廣度與查核深度 | 滿版表格、深層選單與高認知負荷 |
| TradingView | 工作區、熱圖、警示、可程式化與全球市場 | 台灣分點籌碼與在地產業語境不足 |
| Finviz | 高速橫斷面篩選、結果數與多視圖 | 只列數字、不解釋命中原因 |
| StockFeel | 新聞／文章、題材、產業與標的知識連結 | 內容流容易稀釋研究主線 |

官方參考：

- [籌碼K線 App 方案](https://www.cmoney.tw/app/ItemContent.aspx?id=3537)
- [財報狗選股器](https://statementdog.com/screeners)與[定價／功能](https://statementdog.com/pricing)
- [Goodinfo 首頁](https://goodinfo.tw/tw/index.asp)
- [TradingView 功能](https://www.tradingview.com/features/?folder=43000547460)
- [Finviz Screener](https://finviz.com/screener)與[資料延遲說明](https://finviz.com/help/faq)
- [StockFeel 關於頁](https://www.stockfeel.com.tw/about/)

## 3. 建議產品資訊架構

### 今日總覽

首屏在 30 秒內回答：

- 現在是偏多擴散、輪動震盪、偏空收縮、分歧觀察，還是資料不足？
- 市場溫度與產業廣度是否一致？
- 最強／最弱產業、法人方向與事件雷達。
- 今天先處理的三件事：看氣氛、找動能、驗證題材。

### 產業地圖

- 第一層：產業溫度、5D 報酬、法人流向、資料品質。
- 第二層：題材 → 上中下游 → 產品／零組件 → 台美股公司。
- 第三層：關鍵 KPI、營收／毛利／資本支出、新聞、財報事件與來源。
- 產業關係需版本化、自動建議＋人工審核；不可把粗產業代碼假裝成精確供應鏈。

### 智慧選股

固定入口：

- 多方：動能與研究優先度同時偏強。
- 空方：弱勢、thesis breaker 或風險條件命中。
- 處置：只接受官方處置／注意資料。
- 產業：依產業與題材探索。
- 美股：只顯示合法美股資料連接器的標的。

每筆至少顯示命中原因、資料時間、風險旗標、產業、資料品質與加入自選。沒有合法來源時顯示真實空結果，不用範例行情補位。

### 市場情報

- 公司公告、授權新聞與研究內容分級，不混成相同可信度。
- 每則保留原始來源、發布時間、抓取時間、關聯公司／產業、摘要與待確認事項。
- 財報摘要與市場筆記在同一證據鏈；筆記區分觀察事實、推論、反證與下一步。

### 市場策略

每個 playbook 必須公開：

- 股票母體、條件與門檻。
- 更新頻率、失效條件與再平衡規則。
- 交易成本、滑價、存活者偏誤與前視偏誤。
- 回測／樣本外期間與策略版本。

第一版不做券商下單、自動交易、報酬承諾或部位配置。

## 4. 正式資料來源

### 建議組合

- 台股盤後、基本資料、注意／處置、官方公告：TWSE／TPEx OpenAPI。
- 台股財報與重大訊息：MOPS XBRL；商業低延遲使用 MOPS Push。
- 台股即時行情：Fugle Enterprise 或另一家取得交易所公開展示權的資訊公司。
- 產業地圖：官方粗分類＋版本化自建價值鏈，或另簽 TEJ／CMoney 授權。
- 美股行情：Massive Business。
- 美股申報與財報：SEC EDGAR。
- 新聞：官方公告＋有公開展示權的商業新聞源；不爬取媒體全文。

| 資料域 | 主來源 | 產品規則 |
| --- | --- | --- |
| 台股盤後 OHLCV | [TWSE OpenAPI](https://openapi.twse.com.tw/)、[TPEx OpenAPI](https://www.tpex.org.tw/openapi/) | 原子快照；失敗保留上一版並標示 STALE |
| 台股即時行情 | [Fugle Enterprise](https://developer.fugle.tw/docs/data/intro/) | 個人方案不等於公開轉播權 |
| 注意／處置 | TWSE `/announcement/notice`、`/announcement/punish`；TPEx 對應 OpenAPI | 優先於多空訊號；顯示起訖與處置方式 |
| 法人／籌碼 | TPEx OpenAPI；TWSE 商業資料商品／合法供應商 | 18:00 preliminary、20:00 final，D+1／D+2 校正 |
| 台股財報 | MOPS XBRL／Push | 保留申報與修正版本，不覆蓋歷史 |
| 公司公告 | TWSE／TPEx 重大訊息 OpenAPI、MOPS Push | 顯示原文連結，不轉貼未授權全文 |
| 產業價值鏈 | 官方粗分類＋人工審核自建圖譜 | 每個 edge 有來源、有效日期與版本 |
| 美股行情 | [Massive Business](https://massive.com/business) | 個人方案不可做公開多人產品後端 |
| 美股申報 | [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 後端存取、識別 User-Agent、低於 10 req/s |

### 不適合直接作公開產品後端

- FinMind：適合原型與內部校驗；官方授權不包含未取得原始資料權利的對外再散布。
- Fugle 個人方案：API 額度與 WebSocket 訂閱不代表公開展示／轉接權。
- Alpha Vantage 預設方案：個人非商業用途；多人商業產品需另簽合約。
- Massive 個人方案：Individual use only。
- TWSE／TPEx／MOPS 網頁爬蟲：端點、條款與結構都不適合作正式契約。
- CMoney QData：截至研究日公開頁仍標示即將推出，沒有可確認的價格、速率或 SLA。

參考：

- [FinMind 授權說明](https://finmind.github.io/Disclaimer/)
- [Fugle 定價](https://developer.fugle.tw/docs/pricing/)
- [TEJ API 文件](https://api.tej.com.tw/documents.html)
- [Alpha Vantage 條款](https://www.alphavantage.co/terms_of_service/)
- [TWSE 交易資訊使用／授權](https://www.twse.com.tw/zh/products/information/use.html)

## 5. 正確性與鮮度契約

每筆資料至少包含：

`source`、`source_url`、`source_event_time`、`market_session_date`、`ingested_at`、`payload_hash`、`schema_version`、`revision`、`license_scope`

三層儲存：

1. Bronze：原始 JSON／CSV／XBRL 與 SHA-256，不覆寫。
2. Silver：正規化證券、行情、財報、公告與產業關係。
3. Gold：市場情緒、選股、產業熱度與策略結果，記錄輸入 snapshot ID 與公式版本。

以下狀況 fail closed，不發布新快照：

- 未來日期或非交易日日期。
- NaN、Infinity、負成交量、不可能的 OHLC。
- schema drift、無效 UTF-8、HTML 假裝 JSON。
- 覆蓋率低於門檻。
- 新聞來源或 canonical URL 無法驗證。

UI 必須顯示 `LIVE`、`15 MIN DELAYED`、`EOD`、`STALE` 或 `UNAVAILABLE`，不能在來源失敗時靜默混用不同時效資料。

### 本機連線版落地狀態（2026-07-29）

- `/api/live/snapshot` 已整合行情、TWSE 新聞、TWSE／TPEx 重大訊息、注意／處置與每日法人流向；每個資料域獨立快取與標示鮮度。
- 本機 loopback 行情採 TWSE MIS 瀏覽端點，只作個人開發驗證；介面明示不可公開再揭示。
- `FUGLE_API_KEY` 可切換至文件化 REST 行情；公開模式還必須明確設定 `FUGLE_REDISPLAY_LICENSED=1`，代表營運者已另行取得再揭示授權。
- 行情狀態同時驗證 session date 與來源事件時間；缺時間、凍結或未來行情均不會標成 `LIVE`。新聞剛更新時，也不會把中斷的行情誤標成 `EOD`。
- 本機 TWSE MIS 開發模式交易時段輪詢 5 秒；Fugle 與公開頁最短 30 秒，盤後 60 秒。背景分頁停止輪詢，`429` 依 `Retry-After` 恢復。各上游可部分失敗並保留其他成功資料，來源失敗會保留最後快取並標 `STALE`，沒有快取則 `UNAVAILABLE`。
- 公開綁定只保留唯讀資料面，單次最多 20 檔、每個客戶端每分鐘最多 2 次，且全站共用 60-unit/min 的 provider 入口預算；本機證據與狀態寫入僅允許 loopback。
- 即時快照由固定大小 worker pool 執行；HTTP handler 最長等待 14 秒，逾時回 `504` 與 `Retry-After`。部分股票超時時會列出缺少代號並把行情資料域降為 `STALE`，策略匹配與候選複核 fail closed。
- 內建 `ThreadingHTTPServer` 不是網際網路邊界；正式公開時必須放在具 TLS、驗證、路由白名單與額外 user/IP quota 的 reverse proxy 後方。

## 6. 建議架構

```text
Desktop / Web
      │
      ▼
BFF / Data API ── Redis latest snapshot
      │
      ├── TWSE / TPEx / TAIFEX adapters
      ├── MOPS / SEC filing adapters
      ├── Fugle / Massive licensed adapters
      └── licensed news adapters
      │
      ▼
Raw object store → PostgreSQL / Timescale → Signal / Screening engine
```

- API key 不寫入桌面安裝包。
- 正式產品由後端代抓並向客戶端發短效 token。
- 個人 BYO-key 模式只存 Windows Credential Manager／macOS Keychain，且不得經過自家伺服器。
- 備援只能降低時效並明確標示，不能把不同定義的資料偽裝成同一來源。

## 7. 法律與可信度邊界

- 不複製韭菜畢業班品牌、人物、圖樣、截圖、文案、配色組合或專有策略名稱。
- 收費後提供個別證券分析或推介可能涉及投顧業務；上市前應由台灣合資格法律顧問確認。
- 不以過去績效、感謝函或獲利見證暗示確保獲利。
- 新聞只顯示有權展示的標題、必要摘要與原文連結；全文、圖片、圖表需授權。
- 每個分數公開公式版本、資料時間、缺漏與調整紀錄。
- 多方／空方為研究情境，不是買賣、報酬、部位或下單建議。

官方法規參考：

- [金融監督管理委員會法規資料](https://law.fsc.gov.tw/LawContent.aspx?id=GL001365)
- [證券投資信託及顧問法第 70-1 條](https://law.fsc.gov.tw/LawContent.aspx?id=FL030633)
- [智慧財產局著作權說明](https://www.tipo.gov.tw/tw/copyright/774-5043.html)
