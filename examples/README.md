# Examples

This folder contains small CSV files and synthetic fixtures that make the CLI easy to try.

## Offline Research Workflow Demo

```powershell
python -m taiwan_stock_analysis.cli demo quickstart
```

Open:

```text
demo-dist/dashboard.html
```

Verify the generated demo handoff files:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist
```

Open the dashboard after the check passes:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist --open
```

For machine-readable output:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist --json
```

`examples/fixtures/` contains synthetic financial-statement HTML for offline demos. It is not source data and should not be used as real company data.

After opening the dashboard, inspect the review-action queue:

```powershell
python -m taiwan_stock_analysis.cli research action list demo-dist/research_summary.json --state demo-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action report demo-dist/research_summary.json --state demo-dist/review_action_state.json
```

Try persisting one review decision:

```powershell
python -m taiwan_stock_analysis.cli research action set demo-dist/review_action_state.json 2330 source-audit-manual-review --status done --note "checked source freshness"
python -m taiwan_stock_analysis.cli research action backups demo-dist/review_action_state.json
```

The first state write creates `review_action_state.json`. Later writes create timestamped backups next to that file.

Equivalent lower-level command:

```powershell
python -m taiwan_stock_analysis.cli research run examples/research.csv --fixture-root examples/fixtures --output-dir demo-dist --offline-prices
```

## Research Workbench

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
python -m taiwan_stock_analysis.cli research run research.csv --fixture-root examples/fixtures --output-dir research-dist --offline-prices
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
```

Open:

```text
research-dist/dashboard.html
```

`research run` writes memo files under `research-dist/memos/` and handoff packs under `research-dist/packs/` unless `--skip-memos` or `--skip-packs` is passed. The generated summary JSON files also carry traceability metadata and a universe review queue so the run inputs, derived outputs, and next research items can be inspected later. Use `research memo` or `research pack` to regenerate those outputs from existing workflow data.

`examples/research.csv` includes thesis, key risks, watch triggers, and follow-up questions so the offline demo shows how research-quality fields flow into summaries, memos, and packs.

## Single Research Memo

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir memo-dist
python -m taiwan_stock_analysis.cli memo memo-dist/2330_raw_data.json --output memos/2330_memo.md
```

The memo summarizes existing analysis JSON into a deterministic review draft with executive summary, observations, catalysts, risks, open questions, valuation scenarios, diagnostics, and next research actions.

## Batch Analysis

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

## Valuation-Aware Report

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

`valuation.csv` contains scenario assumptions. Edit price, book value per share, dividend, normalized EPS, PE range, and EPS growth rate before using the output for research.
