# Changelog

## v0.7.0 - 2026-05-13

Memo Intelligence Upgrade release.

### Added

- Executive summary, key observations, catalysts, risks, open questions, and grouped next research actions in generated memos.
- Matching Markdown and HTML memo section coverage with deterministic wording.
- v0.7.0 release notes and documentation for the richer memo structure.

### Changed

- README, usage workflow docs, and examples now describe memos as review-ready research drafts.
- Package version is now `0.7.0`.

### Quality

- Memo section order, risk/question generation, empty-state behavior, and HTML coverage are exercised by the test suite.

## v0.6.0 - 2026-05-13

Research Pack release.

### Added

- `research pack` command for consolidated Markdown and HTML research handoff files.
- `research run` pack generation by default, with `--skip-packs` for report/memo-only refreshes.
- `pack_summary.json`, `research-pack.md`, and `research-pack.html` outputs.
- Dashboard discovery and links for generated research pack outputs.
- v0.6.0 release notes and workflow documentation for pack generation.

### Changed

- README, usage workflow docs, and examples now document research pack commands and handoff outputs.
- Package version is now `0.6.0`.

### Quality

- Research pack rendering, CLI routes, run integration, and dashboard links are covered by the test suite.

## v0.5.0 - 2026-05-12

Research Memo Generator release.

### Added

- Single-stock `memo` command for deterministic Markdown or HTML research memos from existing analysis JSON.
- `research memo` command for generating memo files from a research workflow directory.
- `research run` memo generation by default, with `--skip-memos` for report-only refreshes.
- Dashboard discovery and links for generated memo files and `memo_summary.json`.
- v0.5.0 release notes and documentation for memo workflows.

### Changed

- README, usage workflow docs, and examples now document research memo commands and memo output surfaces.
- Package version is now `0.5.0`.

### Quality

- Memo renderer, CLI, research integration, and dashboard memo links are covered by the existing test suite.

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
