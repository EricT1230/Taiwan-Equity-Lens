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
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir live-dist
```

Optional local fixture run. The repository ships `examples/fixtures/` for synthetic offline demos; for real research, point `--fixture` at your own maintained fixture directory:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --fixture examples/fixtures/2330 --output-dir dist
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
- metadata source mode and source-review status

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
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv valuation.csv --output-dir valuation-dist
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
2330,TSMC
2303,UMC
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

For fixture or CI-style runs, keep price lookup offline. The committed `examples/fixtures/` directory is synthetic and suitable for demos; use your own fixture root for real company source snapshots:

```powershell
python -m taiwan_stock_analysis.cli workflow examples/watchlist.csv --fixture-root examples/fixtures --output-dir workflow-dist --offline-prices
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
- source audit status and per-stock source review details

The dashboard uses Traditional Chinese labels and clear empty states, so missing reports, missing comparison output, and missing workflow summary are shown as readable status messages instead of blank tables.

### Workflow Summary Reliability Fields

`workflow_summary.json` preserves the existing v0.2.0 fields and adds reliability fields:

- `step_statuses`: stage-level status records for batch, valuation, comparison, and dashboard generation
- `data_reliability`: aggregate counts for `ok`, `warning`, `error`, and `skipped`
- `stock_failures`: per-stock failure reason and retry hint
- `source_audit`: aggregate source freshness and manual-review status for financial statements and prices

From v0.8.0 onward, summary outputs also include traceability fields:

- `run_metadata`: run id, generation timestamp, command context, inputs, and output root
- `artifact_registry`: self path, dependency paths, and downstream outputs

Status values mean:

- `ok`: the stage completed without detected data issues
- `warning`: output is usable, but a fallback, missing field, or partial failure was detected
- `error`: the stage could not produce output
- `skipped`: the stage did not run because it was disabled or a prerequisite failed

Source audit source modes mean:

- `live`: fetched from the configured live public source.
- `fixture`: loaded from local fixture HTML. This is useful for demos and tests, but requires manual review for real research.
- `offline`: generated by offline demo/template mode. This requires manual review.
- `manual`: supplied by a user-edited input such as valuation CSV assumptions. This requires manual review.
- `unknown`: the source could not be determined from the available artifact.

Freshness and source-audit statuses mean:

- `fresh`: timestamped source data is within the configured freshness window.
- `stale`: timestamped source data is older than the configured freshness window.
- `unknown`: timestamp or source context is missing or invalid.
- `manual_review`: the data may be usable, but fixture, offline, or manual source mode requires review against source filings or market data before handoff.

If you edit `valuation.csv` by hand, rerun the workflow with the edited file:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --output-dir workflow-dist --valuation-csv workflow-dist/valuation.csv
```

The workflow refreshes its generated subdirectories on each run to avoid stale report links. Comparison uses only stocks that succeeded in the first batch analysis.

## 8. Research Workbench

The research workbench lets you track a CSV research universe through the existing workflow outputs without adding a database or hosted service.

Create an editable research CSV:

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
```

Required columns:

- `stock_id`
- `company_name`
- `category`
- `priority`
- `research_state`
- `notes`

Optional research-quality columns:

- `thesis`
- `key_risks`
- `watch_triggers`
- `follow_up_questions`

These fields carry the working thesis, main risks, review triggers, and unanswered questions into research summaries, memo drafts, and consolidated packs. See [Research Methodology](research-methodology.md) for field definitions and workflow boundaries.

Run the research workflow from that CSV:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices
```

The command writes:

- `research-dist/research_watchlist.csv`
- `research-dist/research_summary.json`
- `research-dist/memos/memo_summary.json`
- `research-dist/memos/*_memo.md`
- `research-dist/memos/*_memo.html`
- `research-dist/packs/pack_summary.json`
- `research-dist/packs/research-pack.md`
- `research-dist/packs/research-pack.html`
- `research-dist/workflow_summary.json`
- `research-dist/dashboard.html`
- report, valuation, and comparison outputs when enough workflow data is available

`research run` writes memo and pack outputs by default. To skip memo generation for a report-only refresh:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices --skip-memos
```

To keep memo outputs but skip the consolidated handoff pack:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices --skip-packs
```

Regenerate the research summary without rerunning source fetches:

```powershell
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
```

Generate a single memo from an existing analysis JSON file:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir memo-dist
python -m taiwan_stock_analysis.cli memo memo-dist/2330_raw_data.json --output memos/2330_memo.md
```

The memo is a deterministic review draft. It includes an executive summary, observations, catalysts, risks, open questions, valuation context, diagnostics, and grouped next research actions.

Generate memos for an existing research workflow directory:

```powershell
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
```

Generate a consolidated research pack from the current workflow outputs:

```powershell
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
```

`research_summary.json` preserves your research metadata and adds workflow status, reliability status, source-audit status, attention reasons, and traceability metadata. The dashboard shows research counts by state and priority, source audit status, plus items that need review because of research state, workflow status, source audit, or data reliability warnings. When memo or pack outputs exist, the dashboard links to those artifacts and can surface their run lineage.

Research packs include a Source Audit Overview with overall status and counts, and item-level source-audit reasons where the workflow summary provides them.

`research_summary.json` also includes `universe_review`, a research workflow queue that groups the universe by category, state, and priority. It highlights high-attention, blocked, new, and active-review items without producing investment rankings or allocation advice.

From v0.14.0 onward, `research_summary.json` also includes review-action fields:

- `review_actions`: per-stock open checklist items.
- `review_action_summary`: aggregate open counts by category and severity.
- `review_action_queue`: deterministic queue sorted by severity, research priority, and stock ID.

Review actions are workflow tasks, not investment recommendations. They identify source checks, workflow failures, reliability warnings, valuation gaps, and missing research-quality fields.

The dashboard `Review Actions` section can filter actions by severity, category, priority, persisted status, and search text. Filtering is local to the static dashboard page and does not modify `research_summary.json`.

From v0.16.0 onward, manual review-action decisions can be persisted in a sibling `review_action_state.json` sidecar file. This keeps generated summaries rebuildable while preserving queue decisions across reruns.

```powershell
python -m taiwan_stock_analysis.cli research action set research-dist/review_action_state.json 2330 source-audit-manual-review --status done --note "checked source freshness"
python -m taiwan_stock_analysis.cli research action list research-dist/research_summary.json --state research-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action report research-dist/research_summary.json --state research-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action prune-stale research-dist/research_summary.json --state research-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action prune-stale research-dist/research_summary.json --state research-dist/review_action_state.json --write
python -m taiwan_stock_analysis.cli research action restore research-dist/review_action_state.json research-dist/review_action_state.json.bak-20260516T173000Z
```

Allowed statuses are `open`, `done`, `deferred`, and `ignored`. When `dashboard.html` is regenerated, it automatically reads `review_action_state.json` from the same directory as `research_summary.json` and overlays those statuses into the Review Actions table.

From v0.17.0 onward, each dashboard review-action row also includes command buttons for `done`, `deferred`, `ignored`, and `reopen`. These buttons copy the matching `research action set` command to the clipboard. They do not mutate `review_action_state.json` until you run the copied command in PowerShell.

From v0.18.0 onward, `research action report` audits the sidecar state without mutating it. The report shows total generated actions, current status counts, stale state entries that no longer match the generated queue, the latest `updated_at`, and the next open actions in queue order. The dashboard Review Actions section shows the same state-health counts, stale count, and latest update timestamp as compact badges.

From v0.19.0 onward, `research action prune-stale` removes stale sidecar entries only when `--write` is provided. Without `--write`, it runs as a dry-run and lists the stale entries that would be removed.

From v0.20.0 onward, write commands that update an existing valid `review_action_state.json` first create a timestamped backup such as `review_action_state.json.bak-20260516T173000Z`. Backups are created for `research action set` and `research action prune-stale --write`; missing or invalid state files are not backed up.

From v0.21.0 onward, `research action restore STATE_PATH BACKUP_PATH` restores an explicit backup file. If the current state file exists and is valid, the command first creates a new timestamped backup of the current state, then copies the selected backup bytes to `STATE_PATH`. Invalid backup files or invalid current state files are not overwritten.

The research workbench is for organizing local research review. Memo drafts help structure review work, but they do not provide buy, sell, hold, or allocation recommendations.

## 9. Generate Dashboard

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir live-dist --scan-dir compare-dist --scan-dir batch-dist --scan-dir valuation-dist --output dashboard-index.html
```

To include a one-shot workflow run manually:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir workflow-dist --scan-dir workflow-dist/reports --scan-dir workflow-dist/valuation-reports --scan-dir workflow-dist/comparison --output dashboard-index.html
```

Open `dashboard-index.html` in a browser. It lists generated reports, comparison outputs, batch status, and command builders.
When no `--scan-dir` is provided, the dashboard command also scans `workflow-dist` by default.

## 10. Verify

```powershell
python -m taiwan_stock_analysis.cli doctor release --version 0.21.0
python -m unittest discover -s tests -v
```

The release doctor checks version metadata, release notes, README badge, CHANGELOG entry, and local documentation links before tagging.

Expected: the release doctor reports `Release readiness OK` and all tests pass.

## Guardrails

- The tool is for financial research workflow support.
- It does not provide buy/sell recommendations.
- Missing source data is preserved as missing; the tool should not silently turn missing values into zero.
- Generated reports and temporary files are ignored by git.
