# Changelog

## v0.48.0 - 2026-05-30

Evidence Preview Quality Gate release.

### Added
- Deterministic Reviewer Confidence checks for dashboard-created evidence files.
- `evidence_quality` and `evidence_preview` fields in `/api/evidence/compose-and-set` responses.
- Dashboard evidence result panel with Reviewer Confidence status, check list, next step, generated path, and markdown excerpt.
- Regression tests for specific evidence, low-confidence default stubs, served API responses, and dashboard hooks.
- v0.48.0 release notes and design spec.

### Changed
- Evidence Composer no longer treats a structurally valid handoff update as fully final by itself; weak reviewer, note, or summary inputs are surfaced as `needs_review`.
- README and usage workflow release doctor examples now target `0.48.0`.
- Package version is now `0.48.0`.

### Tests
- Added focused evidence-quality coverage and expanded dashboard/server evidence-composer coverage.

## v0.47.0 - 2026-05-29

Evidence Composer release.

### Added
- Dashboard Evidence Composer inside the Next Action Workbench for evidence-required blockers in served API mode.
- `/api/evidence/compose-and-set` endpoint that writes a local evidence markdown stub, updates `review_action_state.json`, and returns refreshed handoff gate counts.
- Served HTTP coverage that posts to the evidence composer endpoint, verifies the evidence file is written, and confirms the dashboard re-renders to the ready Evidence Pack action.
- v0.47.0 release notes and design spec.

### Changed
- The first-screen dashboard workflow can now clear the primary evidence-required blocker without relying on prompt dialogs or manually creating a file outside the dashboard.
- README and usage workflow release doctor examples now target `0.47.0`.
- Package version is now `0.47.0`.

### Tests
- Added dashboard and served-dashboard regression coverage for the evidence composer workflow.

## v0.46.0 - 2026-05-28

Guided Next Action Loop release.

### Added
- Next Action Workbench inside the Expert Agent Console with one recommended primary button, remaining gate counts, and post-action result text.
- Served HTTP coverage that reads the workbench button payload, posts it to `/api/review-actions/set`, and verifies the dashboard re-renders to the ready Evidence Pack action.
- v0.46.0 release notes and design spec.

### Changed
- Review-action API responses now include handoff gate status, readiness, blocker count, open count, and next-step text after a state write.
- README and usage workflow release doctor examples now target `0.46.0`.
- Package version is now `0.46.0`.

### Tests
- Added dashboard and served-dashboard regression coverage for the guided next-action loop.

## v0.45.0 - 2026-05-27

Served HTTP Evidence Smoke release.

### Added
- `create_dashboard_server()` for tests and tooling that need to start the real local dashboard HTTP server without blocking forever.
- HTTP smoke coverage that starts the dashboard server on an ephemeral port, GETs the rendered dashboard, POSTs a sector evidence-board action to `/api/review-actions/set`, and verifies the re-rendered stock evidence row becomes `證據可交付`.
- v0.45.0 release notes and design spec.

### Changed
- `serve_dashboard()` now reuses the server factory while preserving the CLI behavior.
- README and usage workflow release doctor examples now target `0.45.0`.
- Package version is now `0.45.0`.

### Tests
- Added served HTTP regression coverage for the sector evidence-board update path.

## v0.44.0 - 2026-05-25

Served Dashboard Quality Gate release.

### Added
- Regression coverage that uses the rendered sector evidence-board `補證並標記完成` button payload to update `review_action_state.json` through the served dashboard API helper.
- Post-update dashboard coverage confirming a stock evidence row can move to `證據可交付` after valid note, reviewer, and evidence reference fields are written.
- v0.44.0 release notes.

### Changed
- README and usage workflow release doctor examples now target `0.44.0`.
- Package version is now `0.44.0`.

### Tests
- Added served-dashboard quality coverage for the v0.43 sector evidence-board interaction path.

## v0.43.0 - 2026-05-24

Sector Evidence Board release.

### Added
- Sector evidence board inside the dashboard industry workflow detail panel.
- Stock-level evidence rows showing evidence status, required/filled evidence counts, missing fields, suggested evidence file, and next action.
- Direct handling buttons from the sector evidence board using the existing review-action state flow.
- Dashboard tests for sector evidence rows, suggested evidence paths, and detail-panel action re-binding.
- v0.43.0 release notes and design spec.

### Changed
- The industry workflow now shows both sector blockers and per-stock evidence readiness in one place.
- README and usage workflow release doctor examples now target `0.43.0`.
- Package version is now `0.43.0`.

### Tests
- Added dashboard coverage for the stock-level evidence board rendered inside industry details.

## v0.42.0 - 2026-05-22

Industry Map Drilldown / Sector Workflow release.

### Added
- Dashboard industry map workflow with status, evidence, expert-lens, and search filters.
- Sector detail panel that shows the selected industry's single next action, Top blockers, and evidence/review workload counts.
- Per-blocker `前往審查動作` buttons that jump from the sector workflow back into the matching Review Actions row.
- Dashboard tests for the industry-map filters, detail panel, task rendering, and escaping.
- v0.42.0 release notes and design spec.

### Changed
- The industry map is now an operational workflow for clearing handoff blockers rather than a static card grid.
- README and usage workflow release doctor examples now target `0.42.0`.
- Package version is now `0.42.0`.

### Tests
- Added dashboard coverage for sector filters, evidence status attributes, expert lens attributes, Top blockers, and workflow detail templates.

## v0.41.0 - 2026-05-22

Dashboard Evidence Pack Flow release.

### Added
- Served dashboard API endpoint for writing the Handoff Evidence Pack from the dashboard.
- Expert Agent Console Evidence Pack workflow with API-mode generation, static-mode CLI command copying, output path display, and missing-evidence guidance.
- Dashboard server and dashboard coverage for one-click pack generation and evidence-file guidance.
- Dashboard industry rotation map that groups research items by category, ranks research-delivery pressure from blockers and evidence gaps, and links back to review-action tasks.
- v0.41.0 release notes and design spec.

### Changed
- Dashboard handoff gate rendering now keeps the research summary base directory for local evidence validation when summaries are discovered from disk.
- README and usage workflow release doctor examples now target `0.41.0`.
- Package version is now `0.41.0`.

### Tests
- Added dashboard-server and dashboard tests for Handoff Evidence Pack workflow generation, path safety, static fallback, and API wiring.

## v0.40.0 - 2026-05-21

Handoff Evidence Pack release.

### Added
- `research handoff-pack` command that writes `handoff-pack.md`, `handoff-pack.html`, and `handoff_pack_summary.json` from a research summary and review-action state.
- `doctor handoff --write-pack` option for producing the same handoff evidence pack during gate checks.
- Handoff pack discovery and dashboard rendering for generated evidence-pack artifacts.
- v0.40.0 release notes and design spec.

### Changed
- `doctor handoff` now validates local evidence references when evidence URLs are file paths relative to the research summary directory.
- Handoff gate output now reports `invalid evidence refs` alongside open actions, missing evidence fields, stale state, and missing gate actions.
- README and usage workflow release doctor examples now target `0.40.0`.
- Package version is now `0.40.0`.

### Tests
- Added handoff evidence pack, invalid evidence reference, CLI, dashboard, dashboard-server, and doctor coverage.

## v0.39.0 - 2026-05-21

Evidence-Required Handoff release.

### Added

- Handoff Quality Gate blockers for handled high-risk actions that are missing `note`, `reviewer`, `evidence_url`, or `updated_at`.
- `--reviewer` and `--evidence-url` options for `research action set`.
- Dashboard evidence prompts for served review-action updates before a high-risk blocker can be marked `done`, `deferred`, or `ignored`.
- Visible evidence metadata, evidence-required badges, and static CLI flag hints in dashboard blocker tasks and review-action rows.
- v0.39.0 release notes.

### Changed

- `doctor handoff` now reports `evidence-required gaps` in the gate summary.
- Review-action list output includes note, reviewer, evidence URL, and update timestamp columns.
- README and usage workflow release doctor examples now target `0.39.0`.
- Package version is now `0.39.0`.

### Quality

- Added handoff, state, CLI, dashboard, dashboard-server, and doctor coverage for evidence-required blocker behavior.
- Added a v0.39.0 design note for the Evidence-Required Handoff contract.

## v0.38.0 - 2026-05-20

Gate Blocker Workflow release.

### Added

- Expert Agent Console Top 3 blocker cards now show a task-style problem, suggested handling path, and direct action buttons.
- Console-level `Top 3 標記完成` and `Top 3 稍後處理` controls.
- Served dashboard console actions reuse the existing review-action API and then resync the Handoff Quality Gate.
- Static dashboard console actions copy the matching `research action set` CLI commands.
- Persistent console and per-task feedback copy that tells the user what happened after a direct blocker action.
- v0.38.0 release notes.

### Changed

- Expert Console blocker list is now rendered as task cards instead of a sparse engineering list.
- README and usage workflow release doctor examples now target `0.38.0`.
- Package version is now `0.38.0`.

### Quality

- Added dashboard coverage for Top 3 task cards, console action commands, batch controls, and served-dashboard wiring.
- Added a v0.38.0 design note for the Gate Blocker Workflow contract.

## v0.37.0 - 2026-05-20

Handoff Quality Gate / Win Condition Contract release.

### Added

- Reusable Handoff Quality Gate for deciding whether a research summary can move into human handoff review.
- `doctor handoff` CLI command with text and JSON output for top blockers, gate status, next step, and the non-investment-advice notice.
- Expert Agent Console now uses the Handoff Quality Gate instead of only counting open review-action rows.
- Project win-condition document that records what this project is optimizing for and how the premortem risks are mitigated.
- v0.37.0 release notes.

### Changed

- Dashboard handoff status now blocks on open review actions, stale review-action state entries, and missing required gate actions.
- README and usage workflow release doctor examples now target `0.37.0`.
- Package version is now `0.37.0`.

### Quality

- Added focused unit coverage for Handoff Quality Gate ready, open-blocker, stale-state, and missing-action paths.
- Added doctor and dashboard coverage for handoff blockers and stale state surfaced in the Expert Agent Console.
- Review-action state loading now tolerates UTF-8 BOM files produced by some Windows tooling.
- Added a v0.37.0 design note for the Handoff Quality Gate contract.

## v0.36.0 - 2026-05-20

Expert Console State Sync release.

### Added

- Served dashboard Expert Agent Console now recalculates readiness, next-step copy, and the Top 3 blockers after review-action API updates.
- API-mode console notice that explains button clicks update the console immediately.
- Stable row metadata for console resync, including company name, priority label, severity label, and user-facing action message.
- v0.36.0 release notes.

### Changed

- Static dashboards keep the refresh/regenerate notice because their buttons copy CLI commands instead of writing state directly.
- README and usage workflow release doctor examples now target `0.36.0`.
- Package version is now `0.36.0`.

### Quality

- Added dashboard coverage for API-mode console sync hooks and escaped row metadata used by the resync path.
- Added a v0.36.0 design note for the Expert Console state-sync contract.

## v0.35.0 - 2026-05-20

Expert Agent Console / Guided Flow release.

### Added

- Dashboard Expert Agent Console before the research and review-action tables.
- Handoff readiness verdict that uses the full state-overlaid review-action queue.
- Top 3 guided blocker list with expert lens labels, severity, stock context, and `前往這個阻塞` buttons.
- Console focus controls that filter and scroll the existing review-action queue instead of creating a second state system.
- Persistent non-investment-advice notice for the guided console.
- Mode notice that distinguishes served API updates from static-dashboard CLI command copying.
- v0.35.0 release notes.

### Changed

- README and usage workflow release doctor examples now target `0.35.0`.
- Package version is now `0.35.0`.

### Quality

- Added dashboard coverage for guided console blocked/ready states, top-3 state-overlay behavior, mode notices, non-advice copy, and focus wiring.

## v0.34.0 - 2026-05-19

Fundamental Expert Review release.

### Added

- `fundamental_review` expert layer for research summaries.
- Buffett-style moat, fundamental quality, bear-case risk, and valuation margin-of-safety checks.
- Non-advice notice on expert review outputs.
- `fundamental_review` review-action category.
- Review actions for incomplete, low-quality, thesis-breaker, and manual-check expert review states.
- Dashboard category label and filter support for fundamental expert review actions.
- v0.34.0 release notes.

### Changed

- Research summaries now prefer valuation-aware raw analysis JSON, then fall back to base report JSON when building expert review outputs.
- README and usage workflow release doctor examples now target `0.34.0`.
- Package version is now `0.34.0`.

### Quality

- Added coverage for deterministic expert review scoring, research-summary integration, review-action generation, and dashboard category rendering.

## v0.33.0 - 2026-05-19

Review Actions Bulk Controls release.

### Added

- Review-action queues now include row checkboxes and a `選取目前顯示` control.
- Bulk controls can mark selected visible actions as `標記完成` or `稍後處理`.
- Served dashboards apply bulk updates through the local review-action API.
- Static dashboards copy the selected bulk CLI commands to the clipboard.
- Bulk selection count updates as rows are selected, filtered, or cleared.
- v0.33.0 release notes.

### Changed

- Review-action empty rows now span the new selection column.
- README and usage workflow release doctor examples now target `0.33.0`.
- Package version is now `0.33.0`.

### Quality

- Added dashboard coverage for bulk-control hooks, visible-row selection, and bulk status wiring.

## v0.32.0 - 2026-05-19

Review Actions Task Queue UX release.

### Changed

- Review-action dashboard statuses, severities, categories, priorities, and filter options now use Traditional Chinese user-facing labels.
- Review-action summaries now emphasize task-queue counts such as `待處理`, `已完成`, `稍後處理`, and `不處理`.
- The default review-action filter now focuses on open items.
- Served dashboard status updates now re-apply the active filter, so completed items leave the default queue immediately.
- Row actions now present task-oriented labels such as `標記完成`, `稍後處理`, `不處理`, and `重新開啟`.
- API update results now show a user-facing summary first, with raw JSON under `技術詳細資訊`.
- README and usage workflow release doctor examples now target `0.32.0`.
- Package version is now `0.32.0`.

### Quality

- Updated dashboard coverage for localized labels, default queue filtering, human-readable task messages, and technical-detail API output.

## v0.31.0 - 2026-05-19

Review Actions UX Cleanup release.

### Changed

- Review-action table columns now present the work as `待處理事項` and `操作`.
- Dashboard review-action buttons now use `完成`, `延後`, `忽略`, and `重開` while preserving stable machine-facing command values.
- CLI/API fallback details are collapsed under `指令 / API 詳細資訊`.
- API result JSON is collapsed under `更新結果` and opens automatically after a served dashboard update.
- README and usage workflow release doctor examples now target `0.31.0`.
- Package version is now `0.31.0`.

### Quality

- Updated dashboard coverage for the simplified review-action operation labels and collapsed detail/result panels.

## v0.30.0 - 2026-05-19

Dashboard API Results release.

### Added

- Served dashboard review-action updates now render a full API result JSON block after each button click.
- API responses now include `by_status`, `stale_count`, and `last_updated`.
- v0.30.0 release notes.

### Changed

- Served dashboard status updates now refresh the visible row status, state-health badge, stale-state badge, and last-updated badge.
- README and usage workflow release doctor examples now target `0.30.0`.
- Package version is now `0.30.0`.

### Quality

- Added dashboard coverage for API result rendering hooks and refreshed state summary markers.
- Added dashboard server coverage for returned state summary fields.

## v0.29.0 - 2026-05-19

Dashboard API Actions release.

### Added

- `dashboard --serve` for running an interactive localhost dashboard.
- Review-action API endpoint for updating `review_action_state.json` from dashboard buttons.
- API-enabled dashboard buttons that write status updates and show the result in the page.
- v0.29.0 release notes.

### Changed

- Static dashboards keep the original command-copy fallback.
- Served dashboards call the local API instead of requiring users to paste CLI commands.
- README and usage workflow release doctor examples now target `0.29.0`.
- Package version is now `0.29.0`.

### Quality

- Added dashboard server tests for state writes, invalid statuses, and path safety.
- Added CLI coverage for `dashboard --serve`.

## v0.28.0 - 2026-05-18

Dashboard Traditional Chinese Labels release.

### Added

- v0.28.0 release notes.

### Changed

- Dashboard main visible labels now use Traditional Chinese for research memos, research packs, universe review, review actions, source audit, workflow summary, and review-action filters.
- `doctor demo` now verifies the stable review-action section marker instead of the English `Review Actions` heading.
- README and usage workflow release doctor examples now target `0.28.0`.
- Package version is now `0.28.0`.

### Quality

- Updated dashboard, demo doctor, and CLI tests for the Traditional Chinese dashboard labels.
- Verified the v0.28.0 quickstart dashboard and demo readiness JSON output.

## v0.27.0 - 2026-05-18

Demo Doctor Open release.

### Added

- `doctor demo --open` for opening the generated demo dashboard after readiness passes.
- `opened_dashboard` and `open_error` fields in `doctor demo --json` output.
- CLI coverage for successful opens, failed readiness without opening, JSON plus open, and opener failure.
- v0.27.0 release notes.

### Changed

- `doctor demo --open` returns non-zero when dashboard opening fails.
- README, usage workflow, and examples now document dashboard opening after demo readiness checks.
- Package version is now `0.27.0`.

### Quality

- Added opener tests with a patched dashboard opener so tests do not launch a browser.
- Release doctor updated for `0.27.0`.

## v0.26.0 - 2026-05-18

Demo Doctor JSON release.

### Added

- `doctor demo --json` for machine-readable demo readiness output.
- JSON fields for `ok`, `messages`, `failures`, `output_dir`, and `repair_command`.
- CLI coverage for successful and failing JSON demo doctor output.
- v0.26.0 release notes.

### Changed

- README, usage workflow, and examples now document JSON demo doctor output for scripts and CI.
- Package version is now `0.26.0`.

### Quality

- Added deterministic JSON output coverage for demo readiness pass and failure paths.
- Release doctor updated for `0.26.0`.

## v0.25.0 - 2026-05-18

Demo Doctor release.

### Added

- `doctor demo --output-dir demo-dist` CLI check for validating bundled quickstart demo outputs.
- Demo readiness checks for required handoff files, readable summary JSON, successful stock IDs, review-action queue data, and the dashboard Review Actions section.
- Repair guidance that points back to `demo quickstart` when demo output is incomplete.
- v0.25.0 release notes.

### Changed

- README, usage workflow, and examples now show the demo doctor after `demo quickstart`.
- Package version is now `0.25.0`.

### Quality

- Added demo doctor unit and CLI coverage for pass and failure paths.
- Release doctor updated for `0.25.0`.

## v0.24.0 - 2026-05-18

Demo Quickstart Command release.

### Added

- `demo quickstart` CLI command for running the bundled synthetic offline demo.
- Quickstart output that prints the dashboard path and first review-action commands.
- CLI coverage for the bundled quickstart command.
- v0.24.0 release notes.

### Changed

- README, usage workflow, and examples now recommend `demo quickstart` as the first demo entrypoint.
- `research run` and `demo quickstart` now share the same internal workflow execution path.
- Package version is now `0.24.0`.

### Quality

- Added full-demo CLI regression coverage for `demo quickstart`.
- Release doctor updated for `0.24.0`.

## v0.23.0 - 2026-05-17

Quickstart Onboarding release.

### Added

- Fastest Local Demo guidance in `docs/usage-workflow.md` with copyable offline workflow commands.
- README and example quickstart commands for opening the dashboard and inspecting review-action state.
- v0.23.0 release notes.

### Changed

- Package version is now `0.23.0`.
- Release readiness examples now target `0.23.0`.

### Quality

- Added a docs-only release path that keeps quickstart commands aligned with the existing offline fixtures.
- Release doctor updated for `0.23.0`.

## v0.22.0 - 2026-05-16

Review Action State Backup List release.

### Added

- `research action backups STATE_PATH` CLI command for listing review-action state backup files.
- `--json` output for deterministic backup inventory automation.
- Newest-first backup sorting with parsed timestamps and deterministic handling for unknown suffixes.
- v0.22.0 release notes.

### Changed

- Package version is now `0.22.0`.

### Quality

- Added unit and CLI coverage for backup discovery, sorting, empty listings, text output, and JSON output.
- Release doctor updated for `0.22.0`.

## v0.21.0 - 2026-05-16

Review Action State Restore release.

### Added

- `research action restore STATE_PATH BACKUP_PATH` CLI command for restoring explicit review-action state backups.
- Current-state backup creation before restore when `STATE_PATH` already exists and is valid.
- Restore output lines showing both the current-state backup path and restored state path.
- v0.21.0 release notes.

### Changed

- Package version is now `0.21.0`.

### Quality

- Added unit and CLI coverage for byte-preserving restore, missing targets, current-state backups, invalid backups, and invalid current state files.
- Release doctor updated for `0.21.0`.

## v0.20.0 - 2026-05-16

Review Action State Backups release.

### Added

- Timestamped backups before `research action set` rewrites an existing valid state file.
- Timestamped backups before `research action prune-stale --write` rewrites an existing valid state file.
- Backup output lines showing the created backup path.
- v0.20.0 release notes.

### Changed

- Package version is now `0.20.0`.
- `research action set` now refuses to overwrite invalid state JSON.

### Quality

- Added unit coverage for backup naming, byte preservation, collision handling, CLI backup output, missing state files, and invalid state JSON.
- Release doctor updated for `0.20.0`.

## v0.19.0 - 2026-05-16

Review Action State Pruning release.

### Added

- `research action prune-stale` CLI command for explicit stale sidecar cleanup.
- Dry-run output that lists stale review-action state entries without modifying the state file.
- `--write` mode for pruning stale entries while preserving current generated action state.
- v0.19.0 release notes.

### Changed

- Package version is now `0.19.0`.

### Quality

- Added unit coverage for stale pruning helpers, CLI dry-run behavior, write behavior, default state path, missing state files, and invalid state JSON.
- Release doctor updated for `0.19.0`.

## v0.18.0 - 2026-05-16

Review Action State Report release.

### Added

- `research action report` CLI command for read-only review-action state audits.
- Review-action state report helpers for status counts, stale sidecar entries, latest update time, and next open actions.
- Dashboard state-health badges for persisted status counts, stale state count, and latest `updated_at`.
- v0.18.0 release notes.

### Changed

- Package version is now `0.18.0`.

### Quality

- Added unit coverage for report helpers, CLI report output, and dashboard health badges.
- Release doctor updated for `0.18.0`.

## v0.17.0 - 2026-05-15

Review Action Dashboard Commands release.

### Added

- Dashboard command buttons for marking review actions done, deferred, ignored, or open.
- Clipboard copy behavior with a textarea fallback for static dashboard command workflows.
- Visible fallback command text for each review action.
- Persisted review-action `note` and `updated_at` display in dashboard rows.
- v0.17.0 release notes.

### Changed

- Package version is now `0.17.0`.

### Quality

- Added dashboard tests for command rendering, PowerShell quoting, copy hooks, and state metadata.

## v0.16.0 - 2026-05-15

Review Action Completion Persistence release.

### Added

- Local `review_action_state.json` sidecar files for persisted review-action state.
- CLI commands to set and list review-action status.
- Dashboard status overlay, status filter, state counts, and invalid-state warnings.
- v0.16.0 release notes.

### Changed

- Package version is now `0.16.0`.

### Quality

- Added state-module, CLI, and dashboard tests for persisted review-action completion behavior.

## v0.15.0 - 2026-05-15

Review Action Dashboard Filtering release.

### Added

- Dashboard filters for review action severity, category, priority, and search text.
- Stable review-action row metadata for client-side filtering.
- No-match empty state for filtered review action tables.
- v0.15.0 release notes.

### Changed

- Package version is now `0.15.0`.

### Quality

- Added dashboard tests for filter controls, row metadata, escaping, JavaScript hooks, and legacy compatibility.

## v0.14.0 - 2026-05-15

Review Action Layer release.

### Added

- Deterministic review actions for source audit, workflow, reliability, valuation, and research-quality checks.
- Per-stock `review_actions` in research summaries.
- Top-level `review_action_summary` and `review_action_queue`.
- Review Action Checklist in research packs.
- Review Actions section in dashboards.
- v0.14.0 release notes.

### Changed

- GitHub Actions now uses Node 24-compatible `actions/checkout@v6` and `actions/setup-python@v6`.
- Package version is now `0.14.0`.

### Quality

- Added tests for action building, research-summary aggregation, pack/dashboard rendering, CI workflow action versions, and release readiness.

## v0.13.0 - 2026-05-14

Data Freshness & Source Audit release.

### Added

- Source-audit and freshness classification helpers.
- Analysis metadata source mode for live and fixture data.
- Workflow source audit summary for financial statements and prices.
- Research summary, pack, and dashboard source-audit visibility.
- v0.13.0 release notes.

### Changed

- Research workflow handoff artifacts now show source freshness and manual-review status.
- Package version is now `0.13.0`.

### Quality

- Added tests for freshness classification, source-mode metadata, workflow source audit, pack/dashboard rendering, and release readiness.

## v0.12.0 - 2026-05-14

Research Quality Upgrade release.

### Added

- Optional research CSV fields for thesis, key risks, watch triggers, and follow-up questions.
- Valuation scenario summary with fair-value range, margin-of-safety context, and assumption-completeness confidence.
- Thesis Snapshot in research memos.
- Research Quality Overview in research packs.
- Research methodology documentation.

### Changed

- Example research CSV now demonstrates the richer research workflow.
- Package version is now `0.12.0`.

### Quality

- Added tests for research-quality fields, valuation confidence, memo rendering, pack rendering, and release readiness.

## v0.11.0 - 2026-05-14

Offline Demo Kit release.

### Added

- Synthetic example financial-statement fixtures for fully offline demos.
- Offline research workflow demo smoke test.
- v0.11.0 release notes.

### Changed

- README and examples now use the offline research workflow as the primary demo path.
- Package version is now `0.11.0`.

### Quality

- The public offline demo command is covered by the test suite.

## v0.10.0 - 2026-05-14

Release Quality Gate release.

### Added

- `doctor release` CLI command for local release readiness checks.
- Version metadata, release note, README badge, CHANGELOG, and local Markdown link validation.

### Changed

- GitHub Actions Python matrix now uses `fail-fast: false` so all Python version results stay visible.
- Package version is now `0.10.0`.

### Quality

- Release readiness checks are covered by unit tests and can be run before pushing tags.

## v0.9.1 - 2026-05-14

Python 3.10 compatibility patch.

### Fixed

- Replaced the Python 3.11+ `datetime.UTC` timestamp helper with `timezone.utc` so the traceability layer imports correctly on Python 3.10.

### Changed

- Package version is now `0.9.1`.

### Quality

- Verified the full test suite on Python 3.10 and the default local Python runtime.

## v0.9.0 - 2026-05-13

Universe Review Layer release.

### Added

- `universe_review` metadata in research summaries for category, state, priority, and attention queue review.
- Dashboard Universe Review section for high-attention, blocked, new, and active-review research items.
- v0.9.0 release notes and workflow documentation for the universe review layer.

### Changed

- README, usage workflow docs, and examples now explain the universe review queue.
- Package version is now `0.9.0`.

### Quality

- Universe review queue construction, bucket assignment, dashboard rendering, and legacy compatibility are covered by the test suite.

## v0.8.0 - 2026-05-13

Traceability Layer release.

### Added

- Run metadata with run id, generation timestamp, command context, and output root.
- Artifact registries linking workflow, research summary, memo summary, and pack summary outputs.
- Dashboard traceability surfaces for inspecting run lineage.
- v0.8.0 release notes and workflow documentation for traceability fields.

### Changed

- README, usage workflow docs, and examples now describe run lineage and artifact registries.
- Package version is now `0.8.0`.

### Quality

- Traceability generation, inheritance, and dashboard compatibility are covered by the test suite.

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
