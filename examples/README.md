# Examples

This folder contains small CSV files that make the CLI easy to try.

## Watchlist Workflow Demo

```powershell
python -m taiwan_stock_analysis.cli workflow examples/watchlist.csv --output-dir workflow-dist --offline-prices
```

Open:

```text
workflow-dist/dashboard.html
```

## Batch Analysis

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

## Valuation-Aware Report

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

`valuation.csv` contains scenario assumptions. Edit price, book value per share, dividend, normalized EPS, PE range, and EPS growth rate before using the output for research.
