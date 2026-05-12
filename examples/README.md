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
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
```

Open:

```text
research-dist/dashboard.html
```

`research run` writes memo files under `research-dist/memos/` and handoff packs under `research-dist/packs/` unless `--skip-memos` or `--skip-packs` is passed. Use `research memo` or `research pack` to regenerate those outputs from existing workflow data.

## Single Research Memo

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir memo-dist
python -m taiwan_stock_analysis.cli memo memo-dist/2330_raw_data.json --output memos/2330_memo.md
```

The memo summarizes existing analysis JSON, data reliability context, valuation scenarios, diagnostics, and follow-up checks for research review.

## Batch Analysis

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

## Valuation-Aware Report

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

`valuation.csv` contains scenario assumptions. Edit price, book value per share, dividend, normalized EPS, PE range, and EPS growth rate before using the output for research.
