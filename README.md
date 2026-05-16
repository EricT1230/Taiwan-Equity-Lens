# Taiwan Equity Lens

[![Tests](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml/badge.svg)](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.22.0-blue.svg)](CHANGELOG.md)

Taiwan Equity Lens is a local Taiwan stock fundamental-analysis workflow. It parses public annual financial statement pages, calculates quality and valuation context, and generates static HTML/JSON reports for research.

> This project is for research workflow support only. It does not provide investment advice. See [docs/disclaimer.md](docs/disclaimer.md).

## What It Does

- Generates single-stock HTML and JSON fundamental reports.
- Calculates profitability, growth, leverage, cash-flow, dividend, EPS, PE/PB, and valuation scenario metrics.
- Builds a quality scorecard with confidence handling.
- Produces data-quality diagnostics instead of silently hiding missing fields.
- Compares multiple stocks in a peer comparison report.
- Runs a watchlist workflow from CSV to reports, valuation template, comparison, dashboard, and workflow summary.
- Tracks a research CSV with priority, research state, notes, workflow status, and reliability context.
- Builds a universe-level review queue for deciding which research items need attention first.
- Generates deterministic Markdown or HTML research memos with executive summary, observations, risks, open questions, and next research actions.
- Generates consolidated Markdown and HTML research packs for local handoff and review.
- Carries working thesis, key risks, watch triggers, and follow-up questions through research summaries, memos, and packs.
- Adds lightweight traceability metadata so workflow, summary, memo, and pack outputs can be followed across a run.
- Tracks source mode, freshness, and source-audit status across workflow, pack, and dashboard outputs.
- Converts source-audit, reliability, valuation, and research-quality signals into deterministic review actions.
- Filters dashboard review actions by severity, category, priority, and search text.
- Persists review-action done, deferred, and ignored states in a local sidecar state file.
- Reports review-action state health, stale sidecar entries, and the next open actions from the CLI and dashboard.
- Prunes stale review-action state entries explicitly with a dry-run-by-default CLI command.
- Backs up existing review-action state files before CLI writes.
- Lists available review-action state backup files before restore.
- Restores review-action state from explicit backup files after backing up the current state.
- Copies review-action state update commands directly from the static dashboard.
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

Use the synthetic example fixtures for a fully offline local demo:

```powershell
python -m taiwan_stock_analysis.cli research run examples/research.csv --fixture-root examples/fixtures --output-dir demo-dist --offline-prices
```

Open:

```text
demo-dist/dashboard.html
```

Demo outputs:

- `demo-dist/reports/`
- `demo-dist/valuation.csv`
- `demo-dist/valuation-reports/`
- `demo-dist/comparison/`
- `demo-dist/memos/`
- `demo-dist/packs/`
- `demo-dist/dashboard.html`
- `demo-dist/workflow_summary.json`
- `demo-dist/research_summary.json`

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

Create a research workbench CSV:

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
```

Run the research workflow:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices
```

Regenerate a research summary from existing workflow outputs:

```powershell
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
```

Generate a single research memo from existing analysis JSON:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir memo-dist
python -m taiwan_stock_analysis.cli memo memo-dist/2330_raw_data.json --output memos/2330_memo.md
```

Generate research memos from a research workflow directory:

```powershell
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
```

Generate a consolidated research pack:

```powershell
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
```

Generate a dashboard from existing outputs:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir dist --scan-dir batch-dist --scan-dir compare-dist --scan-dir workflow-dist --output dashboard-index.html
```

Check release readiness before tagging:

```powershell
python -m taiwan_stock_analysis.cli doctor release --version 0.22.0
```

## Example Files

- [examples/watchlist.csv](examples/watchlist.csv): sample watchlist for batch/workflow runs.
- [examples/valuation.csv](examples/valuation.csv): sample valuation assumptions.
- [examples/research.csv](examples/research.csv): sample research workbench universe.
- [examples/fixtures/](examples/fixtures): synthetic financial-statement HTML for offline demos.
- [examples/README.md](examples/README.md): example command guide.

## Output Surfaces

Single-stock reports use Traditional Chinese sections for:

- KPIs
- quality score
- valuation scenarios
- data quality
- data reliability
- source audit and manual-review status
- operating observations
- profitability observations
- financial health observations

Research memos add a review-oriented layer for:

- executive summary
- key observations
- catalysts and risks
- open questions
- grouped next research actions

The workflow dashboard shows:

- workflow summary status
- data reliability status
- source audit status and per-stock review reasons
- successful and failed batch rows
- valuation CSV link
- comparison output or skipped reason
- report and JSON links

When a `research_summary.json` is present, the dashboard also shows:

- research item counts by state and priority
- stocks that need review because of research state, workflow status, or reliability warnings
- a universe review queue for high-attention and blocked research items
- links back to generated workflow and research outputs
- links to generated Markdown and HTML research memos when memo outputs are present
- links to generated Markdown and HTML research packs when pack outputs are present

## Data Reliability

Generated workflow outputs include a reliability summary that explains which steps succeeded, which inputs used fallback sources, and which stocks failed or were skipped. They also include `source_audit` details that identify source mode, freshness status, and manual-review requirements for financial statements and prices.

Summary files also expose a lightweight traceability layer:

- `run_id`
- `generated_at`
- artifact dependencies
- downstream outputs derived from the same run

The source-audit layer uses source modes such as `live`, `fixture`, `offline`, `manual`, and `unknown`, and freshness statuses such as `fresh`, `stale`, `unknown`, and `manual_review`. Fixture, offline, and manually supplied data remain usable, but are flagged for review before research handoff.

Research summaries include a `universe_review` object for work prioritization. It groups the research universe by category, state, and priority, then builds a deterministic attention queue. This is a research workflow queue, not a portfolio ranking or investment recommendation.

Research summaries also include `review_actions`, `review_action_summary`, and `review_action_queue` so handoff artifacts show concrete source, workflow, reliability, valuation, and research-quality checks.

The project uses four status values:

- `ok`: the stage completed without detected data issues
- `warning`: output is usable, but a fallback, stale date, or missing field was detected
- `error`: the stage could not produce output
- `skipped`: the stage did not run because it was disabled or a prerequisite failed

Single-stock reports and dashboards surface the same reliability context, including price source status, workflow failure reasons, retry hints, source-audit status, and valuation assumption labels.

## Research Workflow

The research workbench starts from a CSV with `stock_id`, `company_name`, `category`, `priority`, `research_state`, and `notes`. It converts the research universe to the existing watchlist workflow, keeps research metadata in `research_summary.json`, and refreshes the static dashboard for local review.

Use `research init` to create an editable template, `research run` to produce reports and summaries from the CSV, and `research summary` to rebuild the research JSON after reviewing existing workflow outputs. The workflow is for organizing research status and data reliability review; it does not produce buy, sell, hold, or allocation recommendations.

By default, `research run` also writes memo files under `research-dist/memos/` and handoff packs under `research-dist/packs/`. Packs and dashboards surface the workflow source audit so fixture, offline, stale, unknown, or manually supplied data is visible during handoff. Pass `--skip-memos` to skip memo files or `--skip-packs` to skip pack files.

## Data Sources

See [docs/data-sources.md](docs/data-sources.md).

Current sources and inputs:

- Goodinfo annual financial statement pages
- TWSE listed-stock daily close data
- TPEx OTC daily close data as fallback
- MOPS links for manual official filing verification
- user-provided valuation CSV assumptions

## Documentation

- [Research methodology](docs/research-methodology.md)
- [Usage workflow](docs/usage-workflow.md)
- [Data sources](docs/data-sources.md)
- [Disclaimer](docs/disclaimer.md)
- [Changelog](CHANGELOG.md)
- [v0.22.0 release notes](docs/releases/v0.22.0.md)
- [v0.21.0 release notes](docs/releases/v0.21.0.md)
- [v0.20.0 release notes](docs/releases/v0.20.0.md)
- [v0.19.0 release notes](docs/releases/v0.19.0.md)
- [v0.18.0 release notes](docs/releases/v0.18.0.md)
- [v0.17.0 release notes](docs/releases/v0.17.0.md)
- [v0.16.0 release notes](docs/releases/v0.16.0.md)
- [v0.15.0 release notes](docs/releases/v0.15.0.md)
- [v0.14.0 release notes](docs/releases/v0.14.0.md)
- [v0.13.0 release notes](docs/releases/v0.13.0.md)
- [v0.12.0 release notes](docs/releases/v0.12.0.md)
- [v0.11.0 release notes](docs/releases/v0.11.0.md)
- [v0.10.0 release notes](docs/releases/v0.10.0.md)
- [v0.9.1 release notes](docs/releases/v0.9.1.md)
- [v0.9.0 release notes](docs/releases/v0.9.0.md)
- [v0.8.0 release notes](docs/releases/v0.8.0.md)
- [v0.7.0 release notes](docs/releases/v0.7.0.md)
- [v0.6.0 release notes](docs/releases/v0.6.0.md)
- [v0.5.0 release notes](docs/releases/v0.5.0.md)
- [v0.4.0 release notes](docs/releases/v0.4.0.md)
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
|-- memo.py           # Markdown and HTML research memo renderer
|-- pack.py           # consolidated research pack renderer
|-- traceability.py   # run metadata and artifact registry helpers
|-- metrics.py        # fundamental metric calculations
|-- models.py         # dataclasses
|-- parser.py         # HTML table parser
|-- price_data.py     # valuation CSV loader
|-- research.py       # research CSV and summary helpers
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
