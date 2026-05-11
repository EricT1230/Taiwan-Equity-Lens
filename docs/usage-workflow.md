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
Single-stock reports use Traditional Chinese sections for KPIs, quality score, valuation scenarios, data quality, and operating / profitability / financial health observations.

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

`dashboard.html` reads `workflow_summary.json` and shows the workflow run in one place:

- watchlist path
- successful stock IDs
- valuation CSV link when present
- comparison link when produced
- comparison skipped reason when fewer than two stocks succeeded
- workflow summary JSON link
- data reliability status and failure retry hints

The dashboard uses Traditional Chinese labels and clear empty states, so missing reports, missing comparison output, and missing workflow summary are shown as readable status messages instead of blank tables.

### Workflow Summary Reliability Fields

`workflow_summary.json` preserves the existing v0.2.0 fields and adds reliability fields:

- `step_statuses`: stage-level status records for batch, valuation, comparison, and dashboard generation
- `data_reliability`: aggregate counts for `ok`, `warning`, `error`, and `skipped`
- `stock_failures`: per-stock failure reason and retry hint

Status values mean:

- `ok`: the stage completed without detected data issues
- `warning`: output is usable, but a fallback, missing field, or partial failure was detected
- `error`: the stage could not produce output
- `skipped`: the stage did not run because it was disabled or a prerequisite failed

If you edit `valuation.csv` by hand, rerun the workflow with the edited file:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --output-dir workflow-dist --valuation-csv workflow-dist/valuation.csv
```

The workflow refreshes its generated subdirectories on each run to avoid stale report links. Comparison uses only stocks that succeeded in the first batch analysis.

## 8. Generate Dashboard

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir live-dist --scan-dir compare-dist --scan-dir batch-dist --scan-dir valuation-dist --output dashboard-index.html
```

To include a one-shot workflow run manually:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir workflow-dist --scan-dir workflow-dist/reports --scan-dir workflow-dist/valuation-reports --scan-dir workflow-dist/comparison --output dashboard-index.html
```

Open `dashboard-index.html` in a browser. It lists generated reports, comparison outputs, batch status, and command builders.
When no `--scan-dir` is provided, the dashboard command also scans `workflow-dist` by default.

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
