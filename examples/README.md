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

`examples/fixtures/` contains synthetic financial-statement HTML for offline demos. `examples/industry_price_history.csv` contains synthetic daily close/volume rows used to generate the demo Industry Trend Report. `examples/market_news.csv` and `examples/fund_flow.csv` provide synthetic event and institutional-flow context for the Market Intelligence map. These files are not source data and should not be used as real company or market data.

The demo also writes `demo-dist/market-intelligence/industry_sentiment_history.csv`. Validate its experimental shadow report with:

```powershell
python -m taiwan_stock_analysis.cli research sentiment-backtest demo-dist/market-intelligence/industry_sentiment_history.csv --output demo-dist/market-intelligence/sentiment_backtest_report.json
```

The small synthetic history should fail minimum-history promotion gates while the command exits successfully with a valid `experimental` report. It must not report a calibrated forecast.

After opening the dashboard, inspect the review-action queue:

```powershell
python -m taiwan_stock_analysis.cli research action list demo-dist/research_summary.json --state demo-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action report demo-dist/research_summary.json --state demo-dist/review_action_state.json
```

Try persisting one review decision:

```powershell
python -m taiwan_stock_analysis.cli research action set demo-dist/review_action_state.json 2330 source-audit-manual-review --status done --note "checked source freshness" --reviewer "source-audit-lead" --evidence-url "demo-dist/evidence/2330-source.md"
python -m taiwan_stock_analysis.cli research handoff-pack demo-dist/research_summary.json --state demo-dist/review_action_state.json --output-dir demo-dist/handoff-pack
python -m taiwan_stock_analysis.cli research action backups demo-dist/review_action_state.json
```

The first state write creates `review_action_state.json`. Later writes create timestamped backups next to that file.

Equivalent lower-level command:

```powershell
python -m taiwan_stock_analysis.cli research run examples/research.csv --fixture-root examples/fixtures --output-dir demo-dist --offline-prices --industry-price-history examples/industry_price_history.csv --market-news-csv examples/market_news.csv --market-fund-flow-csv examples/fund_flow.csv --market-as-of 2026-07-12T12:00:00+08:00
```

Rerun only Market Intelligence for a controlled review cutoff:

```powershell
python -m taiwan_stock_analysis.cli research market-intelligence examples/research.csv --industry-trend-report demo-dist/industry-trends/industry_trend_report.json --news-csv examples/market_news.csv --fund-flow-csv examples/fund_flow.csv --as-of 2026-07-17T18:00:00+08:00 --output-dir demo-dist/market-intelligence
python -m taiwan_stock_analysis.cli research sentiment-backtest demo-dist/market-intelligence/industry_sentiment_history.csv --output demo-dist/market-intelligence/sentiment_backtest_report.json
```

The rerun upserts the same `(as_of_date, category, methodology_version)` key and preserves other dates. Current sentiment is descriptive; projections and turning-risk windows are experimental research diagnostics, not probabilities, price targets, exact dates, or investment advice.

Generate only the industry trend report:

```powershell
python -m taiwan_stock_analysis.cli research industry-trends examples/research.csv --price-history examples/industry_price_history.csv --output-dir demo-dist/industry-trends
```

Validate official listed and OTC coverage with the cross-market universe:

```powershell
python -m taiwan_stock_analysis.cli research market-data examples/research_cross_market.csv --output-dir market-data-dist --history-months 3
```

## Research Workbench

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
python -m taiwan_stock_analysis.cli research run research.csv --fixture-root examples/fixtures --output-dir research-dist --offline-prices
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
python -m taiwan_stock_analysis.cli research handoff-pack research-dist/research_summary.json --state research-dist/review_action_state.json --output-dir research-dist/handoff-pack
```

Open:

```text
research-dist/dashboard.html
```

`research run` writes memo files under `research-dist/memos/` and handoff packs under `research-dist/packs/` unless `--skip-memos` or `--skip-packs` is passed. The generated summary JSON files also carry traceability metadata and a universe review queue so the run inputs, derived outputs, and next research items can be inspected later. Use `research memo` or `research pack` to regenerate those outputs from existing workflow data.

`examples/research.csv` includes thesis, key risks, watch triggers, follow-up questions, optional market-rotation fields, and `news_keywords` aliases. The offline demo combines `examples/industry_price_history.csv`, `examples/market_news.csv`, and `examples/fund_flow.csv` so price trend, event keywords, and institutional flow can be reviewed together.

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
