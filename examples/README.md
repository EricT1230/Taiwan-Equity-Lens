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

## Research Workbench

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
python -m taiwan_stock_analysis.cli research run examples/research.csv --output-dir research-dist --offline-prices
python -m taiwan_stock_analysis.cli research summary examples/research.csv --workflow-dir research-dist --output research-dist/research_summary.json
```

Open:

```text
research-dist/dashboard.html
```

## Batch Analysis

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

## Valuation-Aware Report

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

`valuation.csv` contains scenario assumptions. Edit price, book value per share, dividend, normalized EPS, PE range, and EPS growth rate before using the output for research.
