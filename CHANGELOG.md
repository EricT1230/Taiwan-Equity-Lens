# Changelog

## v0.4.1 - 2026-05-12

Documentation hotfix for research workbench onboarding.

### Fixed

- README research workflow commands now consistently use the `research.csv` created by `research init`.
- README demo wording no longer implies a fully deterministic run without fixture data.

## v0.4.0 - 2026-05-12

Research Workbench release.

### Added

- Research CSV template and validation for tracking stock ID, company name, category, priority, research state, and notes.
- `research init`, `research run`, and `research summary` commands.
- `research_summary.json` output that combines research rows with workflow status and data reliability context.
- Dashboard rendering for research state counts, priority counts, and attention items.
- Example research CSV and v0.4.0 release notes.

### Changed

- README, usage workflow docs, and examples now include the research workbench command path.
- Package version is now `0.4.0`.

### Quality

- Existing watchlist workflow, reliability, comparison, valuation, and dashboard tests remain the release verification path.

## v0.3.1 - 2026-05-12

Documentation hotfix for public onboarding.

### Fixed

- Cleaned corrupted display text from public README and usage examples.
- Replaced sample company names with ASCII-safe labels in command examples.

## v0.3.0 - 2026-05-12

Data reliability and research workflow automation.

### Added

- Workflow data reliability summary with `ok`, `warning`, `error`, and `skipped` counts.
- Step-level workflow status records for batch, valuation, comparison, and dashboard generation.
- Per-stock failure reasons and retry hints in `workflow_summary.json`.
- Price source reliability fields in valuation CSV templates.
- Valuation assumption labels for EPS and target-price scenarios.
- Report and dashboard sections for reliability review.
- v0.3.0 release notes and reliability documentation.

### Changed

- Workflow status now reflects partial batch and valuation failures as warnings.
- Price rows with source warnings are no longer marked as fully healthy.
- Single-stock reports surface valuation assumptions alongside reliability context.

### Quality

- Expanded tests for reliability serialization, workflow summaries, price source status, valuation assumptions, reports, and dashboard rendering.
- Existing v0.2.0 commands and workflow summary fields remain compatible.

## v0.2.0 - 2026-05-11

Release polish and workflow upgrade.

### Added

- One-command watchlist workflow: batch reports, valuation CSV, valuation-aware rerun, peer comparison, dashboard, and workflow summary.
- TPEx fallback for valuation price templates when TWSE does not return a valid close price.
- Workflow summary discovery and rendering in the static dashboard.
- Example watchlist and valuation CSV files for quick demos.
- v0.2.0 release notes and refreshed README onboarding.

### Changed

- Polished dashboard presentation with readable Traditional Chinese labels, empty states, and status badges.
- Polished single-stock HTML reports with readable sections for KPIs, quality score, valuation scenarios, data quality, and insights.
- Dashboard default scanning now includes `workflow-dist`.
- Batch analysis can accept a valuation CSV for valuation-aware batch reports.

### Quality

- Expanded tests for workflow, dashboard, TPEx price fallback, and report presentation.
- Preserved valuation, scorecard, metric, and data-source calculation contracts.

## v0.1.0 - 2026-05-11

Initial public release of Taiwan Equity Lens.

### Added

- Single-stock financial statement parsing from Goodinfo annual reports.
- Derived metrics for profitability, growth, leverage, cash flow, and dividends.
- Trend insights and data quality diagnostics.
- Fundamental scorecard with confidence handling.
- Peer comparison and watchlist batch analysis.
- Valuation CSV workflow with EPS scenarios, PE target prices, and price gaps.
- TWSE price template helper for valuation CSV setup.
- Static dashboard index for generated reports.
- GitHub Actions test workflow and examples.
