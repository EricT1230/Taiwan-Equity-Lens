# Taiwan Equity Lens（台股基本面透鏡）

輸入台灣股票代碼，從 Goodinfo.tw 讀取年度財報頁面，解析損益表、資產負債表、現金流量表，計算常用財務指標，並輸出 JSON 與 HTML 儀表板。

> 本工具僅供財務學習與研究參考，不構成投資建議。資料來源若有異動，請以公開資訊觀測站與公司正式申報為準。

## 功能

- 抓取 Goodinfo 年度財報頁面：`IS_YEAR`、`BS_YEAR`、`CF_YEAR`
- 解析 Goodinfo 常見「年度 / 百分比」成對欄位
- 計算毛利率、營業利益率、淨利率、費用率、EPS、ROE、ROA、流動比率、負債比率、營業現金流、自由現金流
- 補充基本面進階指標：營收 CAGR、EPS CAGR、股東權益成長率、OCF / 淨利、FCF margin、股利支付率、負債權益比、現金對流動負債
- 自動產生經營、獲利、財務健全度三段趨勢解讀
- 產生基本面品質分數：獲利能力、成長性、財務安全、現金流品質、股利品質
- 可用 CSV 補充估值脈絡：PE、PB、殖利率、PE 情境估值
- 產生資料品質診斷，標示缺欄位、缺指標、年份不足與現金流矛盾
- 產生可分享的 HTML 報表與完整 JSON 原始資料
- 支援 fixture 模式，不連網也能測試整個流程
- 支援多股票同業比較，輸出 comparison JSON / HTML
- 支援 watchlist CSV 批次分析，單一股票失敗不會中斷整批

## 安裝

```powershell
python -m pip install -e .
```

本版核心只使用 Python 標準函式庫，不需要額外安裝 `requests` 或 `beautifulsoup4`。

## 授權

MIT License. See [LICENSE](LICENSE).

## 版本

See [CHANGELOG.md](CHANGELOG.md).

Release notes are stored in [docs/releases](docs/releases).

## 使用

```powershell
taiwan-equity-lens 2330 --company-name 台積電 --output-dir dist
```

也可以直接用 module 執行：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --output-dir dist
```

輸出檔案：

- `dist/2330_raw_data.json`
- `dist/2330_analysis.html`

## Fixture 模式

建立一個資料夾，放入三個 HTML 檔：

```text
fixtures/
├── IS_YEAR.html
├── BS_YEAR.html
└── CF_YEAR.html
```

執行：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --fixture fixtures --output-dir dist
```

## 同業比較

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist
```

輸出檔案：

- `compare-dist/comparison.json`
- `compare-dist/comparison.html`

比較維度包含毛利率、ROE、營收 CAGR、負債比率、FCF margin、OCF / 淨利。

## 基本面品質分數

單股報表會輸出 `scorecard`，包含：

- 總分與信心度
- 獲利能力
- 成長性
- 財務安全
- 現金流品質
- 股利品質
- 每個構面的主要原因

分數只衡量財報品質，不含估值，僅供基本面研究參考。

## 資料品質診斷

單股 JSON 會輸出 `diagnostics`，HTML 報表會顯示「資料品質診斷」區塊。診斷會標示：

- 分析年度少於 3 年
- 損益表、資產負債表、現金流量表缺少核心欄位
- 最新年度核心指標缺值
- 淨利為正但營業現金流為負等盈餘品質警示

批次分析成功列會額外輸出 `warning_count`，方便先挑出需要人工檢查的公司。

## 估值脈絡

先使用使用者提供的 CSV，不自動綁定外部股價來源。CSV 欄位：

```csv
stock_id,price,book_value_per_share,cash_dividend_per_share,normalized_eps,target_pe_low,target_pe_base,target_pe_high,eps_growth_rate
2330,1000,160,12,60,15,20,25,10
```

執行：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --valuation-csv valuation.csv --output-dir valuation-dist
```

估值會和基本面品質分數分開呈現，避免把「公司品質」和「價格高低」混在同一個分數。

EPS 與目標價情境：

- 保守 EPS：最新 EPS 與歷史平均正 EPS 取較低者
- 基準 EPS：優先使用 `normalized_eps`，未提供時使用最新 EPS
- 樂觀 EPS：若提供 `eps_growth_rate`，用最新 EPS 乘上成長率；否則取最新 EPS 與歷史平均正 EPS 較高者
- 目標價：`EPS 情境 * target_pe`
- 目標價差距：`(目標價 - price) / price * 100`

這些是情境估算，不是價格預測或投資建議。

也可以先產生估值 CSV 範本，上市股票會嘗試用 TWSE 個股日成交資訊補入最近收盤價：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli price-template 2330 2303 --output valuation.csv
```

若已經有單股分析輸出的 `*_raw_data.json`，可以用 `--analysis-dir` 自動補 `normalized_eps` 和預設 PE 區間：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli price-template 2330 --analysis-dir dist --output valuation.csv
```

補值規則：

- `normalized_eps`：優先使用分析 JSON 的 `valuation.eps_scenarios.base`，否則使用最新年度 EPS
- `target_pe_low`：`10`
- `target_pe_base`：`15`
- `target_pe_high`：`20`
- `book_value_per_share` 與 `cash_dividend_per_share`：沒有可靠股數或股利資料時保留空白

若資料來源暫時無法取得，`price` 會留空並在 `warning` 欄位記錄原因。測試或離線時可使用：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli price-template 2330 --output valuation.csv --offline
```

## 批次分析

建立 `watchlist.csv`：

```csv
stock_id,company_name
2330,台積電
2303,聯電
```

執行：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli batch watchlist.csv --output-dir batch-dist
```

輸出 `batch-dist/batch_summary.json`，每檔股票會記錄 `ok` 或 `error`，避免單一股票資料失敗時中斷整批。

## 靜態 Dashboard

產生本機靜態入口頁，集中瀏覽已產出的單股報告、同業比較和批次分析狀態：

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli dashboard --scan-dir live-dist --scan-dir compare-dist --scan-dir batch-dist --scan-dir valuation-dist --output dashboard-index.html
```

`dashboard-index.html` 是靜態 HTML，不需要啟動伺服器。頁面會列出可開啟的 HTML / JSON 輸出，顯示單股報表、同業比較、批次項目和批次錯誤數量，並提供：

- 單股分析指令產生器
- 同業比較指令產生器
- 批次分析指令產生器
- watchlist CSV 範本下載

## 開發與測試

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

## 專案結構

```text
src/taiwan_stock_analysis/
├── cli.py            # CLI orchestration
├── comparison.py     # 多股票比較與排名
├── dashboard.py      # static dashboard index renderer
├── diagnostics.py    # data quality diagnostics
├── fetcher.py        # Goodinfo network boundary
├── insights.py       # 中文趨勢解讀
├── market_price.py   # TWSE price template helper
├── metrics.py        # 財務指標計算
├── models.py         # dataclasses
├── parser.py         # HTML table parser
├── price_data.py     # valuation CSV loader
├── report.py         # HTML renderer
├── report_compare.py # comparison HTML renderer
├── score_rules.py    # 基本面評分門檻
├── scoring.py        # 基本面 scorecard
├── trends.py         # YoY / CAGR / trend helpers
├── valuation.py      # PE/PB/yield/scenario valuation
├── verification.py   # 合理性檢查
└── watchlist.py      # watchlist CSV loader
```
