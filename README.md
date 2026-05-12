# Taiwan Equity Lens

[![Tests](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml/badge.svg)](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.3.1-blue.svg)](CHANGELOG.md)

Taiwan Equity Lens is a local Taiwan stock fundamental-analysis workflow. It parses public annual financial statement pages, calculates quality and valuation context, and generates static HTML/JSON reports for research.

> This project is for research workflow support only. It does not provide investment advice. See [docs/disclaimer.md](docs/disclaimer.md).

## What It Does

- Generates single-stock HTML and JSON fundamental reports.
- Calculates profitability, growth, leverage, cash-flow, dividend, EPS, PE/PB, and valuation scenario metrics.
- Builds a quality scorecard with confidence handling.
- Produces data-quality diagnostics instead of silently hiding missing fields.
- Compares multiple stocks in a peer comparison report.
- Runs a watchlist workflow from CSV to reports, valuation template, comparison, dashboard, and workflow summary.
- Creates valuation CSV templates with TWSE first and TPEx fallback close-price lookup.
- Keeps reports fully local as static HTML and JSON.

## Quick Start

```powershell
git clone https://github.com/EricT1230/Taiwan-Equity-Lens.git
cd Taiwan-Equity-Lens
python -m pip install -e .
```

Run one stock:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir dist
```

Outputs:

- `dist/2330_raw_data.json`
- `dist/2330_analysis.html`

## One-Command Demo

Use the example watchlist and keep price lookup offline for a deterministic demo:

```powershell
python -m taiwan_stock_analysis.cli workflow examples/watchlist.csv --output-dir workflow-dist --offline-prices
```

Open:

```text
workflow-dist/dashboard.html
```

Workflow outputs:

- `workflow-dist/reports/`
- `workflow-dist/valuation.csv`
- `workflow-dist/valuation-reports/`
- `workflow-dist/comparison/`
- `workflow-dist/dashboard.html`
- `workflow-dist/workflow_summary.json`

## Common Commands

Batch analyze a watchlist:

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

Compare multiple stocks:

```powershell
python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist
```

Generate a valuation CSV template:

```powershell
python -m taiwan_stock_analysis.cli price-template 2330 2303 --analysis-dir dist --output valuation.csv
```

Run a valuation-aware report:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

Generate a dashboard from existing outputs:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir dist --scan-dir batch-dist --scan-dir compare-dist --scan-dir workflow-dist --output dashboard-index.html
```

## Example Files

- [examples/watchlist.csv](examples/watchlist.csv): sample watchlist for batch/workflow runs.
- [examples/valuation.csv](examples/valuation.csv): sample valuation assumptions.
- [examples/README.md](examples/README.md): example command guide.

## Output Surfaces

Single-stock reports use Traditional Chinese sections for:

- KPIs
- quality score
- valuation scenarios
- data quality
- data reliability
- operating observations
- profitability observations
- financial health observations

The workflow dashboard shows:

- workflow summary status
- data reliability status
- successful and failed batch rows
- valuation CSV link
- comparison output or skipped reason
- report and JSON links

## Data Reliability

Generated workflow outputs include a reliability summary that explains which steps succeeded, which inputs used fallback sources, and which stocks failed or were skipped.

The project uses four status values:

- `ok`: the stage completed without detected data issues
- `warning`: output is usable, but a fallback, stale date, or missing field was detected
- `error`: the stage could not produce output
- `skipped`: the stage did not run because it was disabled or a prerequisite failed

Single-stock reports and dashboards surface the same reliability context, including price source status, workflow failure reasons, retry hints, and valuation assumption labels.

## Data Sources

See [docs/data-sources.md](docs/data-sources.md).

Current sources and inputs:

- Goodinfo annual financial statement pages
- TWSE listed-stock daily close data
- TPEx OTC daily close data as fallback
- MOPS links for manual official filing verification
- user-provided valuation CSV assumptions

## Documentation

- [Usage workflow](docs/usage-workflow.md)
- [Data sources](docs/data-sources.md)
- [Disclaimer](docs/disclaimer.md)
- [Changelog](CHANGELOG.md)
- [v0.3.0 release notes](docs/releases/v0.3.0.md)
- [v0.2.0 release notes](docs/releases/v0.2.0.md)

## Verify

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

## Project Structure

```text
src/taiwan_stock_analysis/
|-- cli.py            # CLI orchestration
|-- comparison.py     # peer comparison model
|-- dashboard.py      # static dashboard renderer
|-- diagnostics.py    # data quality diagnostics
|-- fetcher.py        # Goodinfo network boundary
|-- insights.py       # Traditional Chinese trend observations
|-- market_price.py   # TWSE/TPEx valuation price template helper
|-- metrics.py        # fundamental metric calculations
|-- models.py         # dataclasses
|-- parser.py         # HTML table parser
|-- price_data.py     # valuation CSV loader
|-- reliability.py    # data reliability status model
|-- report.py         # single-stock HTML renderer
|-- report_compare.py # comparison HTML renderer
|-- score_rules.py    # scorecard rules
|-- scoring.py        # scorecard builder
|-- trends.py         # YoY / CAGR / trend helpers
|-- valuation.py      # PE/PB/yield/scenario valuation
|-- verification.py   # sanity checks
|-- workflow.py       # watchlist workflow orchestration
`-- watchlist.py      # watchlist CSV loader
```

## License

MIT License. See [LICENSE](LICENSE).
