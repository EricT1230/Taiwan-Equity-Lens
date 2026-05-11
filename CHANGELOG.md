# Changelog

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
