# Taiwan Equity Lens Usage Workflow

This document shows the normal local workflow from installation to dashboard review.

## 1. Install

```powershell
cd C:\Users\user\Projects\Personal\taiwan-equity-lens
python -m pip install -e .
```

For direct module execution during development:

```powershell
$env:PYTHONPATH='src'
```

## 2. Run Single-Stock Analysis

Live Goodinfo run:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --output-dir live-dist
```

Fixture run:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --fixture fixtures --output-dir dist
```

Outputs:

- `live-dist/2330_raw_data.json`
- `live-dist/2330_analysis.html`

The JSON contains:

- parsed financial statements
- derived metrics
- trend insights
- scorecard
- valuation context when CSV input is provided
- diagnostics

## 3. Generate Valuation CSV Template

Price template with TWSE close price lookup:

```powershell
python -m taiwan_stock_analysis.cli price-template 2330 2303 --analysis-dir live-dist --output valuation.csv
```

Offline template for testing:

```powershell
python -m taiwan_stock_analysis.cli price-template 2330 --analysis-dir live-dist --output valuation.csv --offline
```

The template can fill:

- `price` from TWSE when available
- `normalized_eps` from existing analysis JSON
- default PE assumptions: `10`, `15`, `20`

Fields intentionally left blank until reliable source data exists:

- `book_value_per_share`
- `cash_dividend_per_share`
- `eps_growth_rate`

## 4. Run Valuation-Aware Report

After editing `valuation.csv`:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --valuation-csv valuation.csv --output-dir valuation-dist
```

The HTML report will show:

- PE / PB / dividend yield when inputs exist
- EPS scenarios
- target price scenarios
- price gap percentages

These are scenario outputs, not investment advice.

## 5. Compare Multiple Stocks

```powershell
python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist
```

Outputs:

- `compare-dist/comparison.json`
- `compare-dist/comparison.html`

## 6. Batch Analyze a Watchlist

Create `watchlist.csv`:

```csv
stock_id,company_name
2330,台積電
2303,聯電
```

Run:

```powershell
python -m taiwan_stock_analysis.cli batch watchlist.csv --output-dir batch-dist
```

Output:

- `batch-dist/batch_summary.json`

Each row records `ok` or `error`. Successful rows include `warning_count`.

## 7. Run the One-Shot Watchlist Workflow

The workflow command runs the normal watchlist path end to end:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --output-dir workflow-dist
```

For fixture or CI-style runs, keep price lookup offline:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --fixture-root fixtures --output-dir workflow-dist --offline-prices
```

Outputs:

- `workflow-dist/reports/batch_summary.json`
- `workflow-dist/valuation.csv`
- `workflow-dist/valuation-reports/batch_summary.json`
- `workflow-dist/comparison/comparison.json`
- `workflow-dist/comparison/comparison.html`
- `workflow-dist/dashboard.html`
- `workflow-dist/workflow_summary.json`

If you edit `valuation.csv` by hand, rerun the workflow with the edited file:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --output-dir workflow-dist --valuation-csv workflow-dist/valuation.csv
```

The workflow refreshes its generated subdirectories on each run to avoid stale report links. Comparison uses only stocks that succeeded in the first batch analysis.

## 8. Generate Dashboard

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir live-dist --scan-dir compare-dist --scan-dir batch-dist --scan-dir valuation-dist --output dashboard-index.html
```

Open `dashboard-index.html` in a browser. It lists generated reports, comparison outputs, batch status, and command builders.

## 9. Verify

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

## Guardrails

- The tool is for financial research workflow support.
- It does not provide buy/sell recommendations.
- Missing source data is preserved as missing; the tool should not silently turn missing values into zero.
- Generated reports and temporary files are ignored by git.
