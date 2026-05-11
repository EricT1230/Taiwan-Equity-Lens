# Watchlist Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-command watchlist workflow that runs analysis, valuation template generation, optional valuation-aware rerun, comparison, dashboard generation, and writes a workflow summary.

**Architecture:** Keep existing commands as building blocks. Add a small orchestration module that calls `run_batch`, `write_valuation_template`, `run_compare`, and `write_dashboard_index` with stable output folders under one workflow directory.

**Tech Stack:** Python standard library, existing `unittest` suite, current CLI entrypoint `taiwan_stock_analysis.cli`.

---

## File Structure

- Create: `src/taiwan_stock_analysis/workflow.py`
  - Owns the one-command workflow orchestration and JSON summary.
- Modify: `src/taiwan_stock_analysis/cli.py`
  - Adds `workflow` subcommand and allows `run_batch` to receive an optional valuation CSV.
- Create: `tests/test_workflow.py`
  - Tests workflow orchestration with fixture data and offline price mode.
- Modify: `tests/test_cli.py`
  - Tests CLI route for `workflow`.
- Modify: `README.md`
  - Documents the new command briefly.
- Modify: `docs/usage-workflow.md`
  - Adds the one-command workflow as the recommended path.

---

### Task 1: Add Batch Valuation Input

**Files:**
- Modify: `src/taiwan_stock_analysis/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write a failing test for batch valuation CSV**

Add a test that runs `run_batch(..., valuation_csv=...)` and verifies the generated raw JSON includes valuation metrics from the CSV for a successful stock.

- [ ] **Step 2: Run the focused test**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_cli.CliTests.test_run_batch_accepts_valuation_csv -v`

Expected: FAIL because `run_batch` does not accept `valuation_csv`.

- [ ] **Step 3: Extend `run_batch`**

Add an optional `valuation_csv: Path | None = None` parameter and pass it through to `run(...)`.

- [ ] **Step 4: Re-run the focused test**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_cli.CliTests.test_run_batch_accepts_valuation_csv -v`

Expected: PASS.

---

### Task 2: Add Workflow Orchestration

**Files:**
- Create: `src/taiwan_stock_analysis/workflow.py`
- Test: `tests/test_workflow.py`

- [ ] **Step 1: Write failing workflow tests**

Test an offline fixture workflow that creates:

- `reports/batch_summary.json`
- `valuation.csv`
- `valuation-reports/batch_summary.json`
- `comparison/comparison.json`
- `comparison/comparison.html`
- `dashboard.html`
- `workflow_summary.json`

- [ ] **Step 2: Run the focused tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow -v`

Expected: FAIL because `workflow.py` does not exist.

- [ ] **Step 3: Implement `run_watchlist_workflow`**

Create `run_watchlist_workflow(watchlist_path, output_dir, *, fixture_root=None, offline_prices=False, include_valuation=True)` and return the path to `workflow_summary.json`.

The summary must include:

- input watchlist path
- stock IDs
- successful stock IDs used for comparison
- generated file paths
- skipped comparison reason when fewer than two successful stocks exist

- [ ] **Step 4: Re-run focused workflow tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow -v`

Expected: PASS.

---

### Task 3: Add CLI Subcommand

**Files:**
- Modify: `src/taiwan_stock_analysis/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write a failing CLI test**

Add `test_main_workflow_writes_summary` that calls:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --fixture-root fixtures --output-dir workflow-dist --offline-prices
```

Expected files: `workflow_summary.json` and `dashboard.html`.

- [ ] **Step 2: Implement CLI parser and route**

Add `workflow` to the subcommand set and wire parser args:

- positional `watchlist`
- `--output-dir`
- `--fixture-root`
- `--offline-prices`
- `--skip-valuation`

- [ ] **Step 3: Run CLI tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_cli -v`

Expected: PASS.

---

### Task 4: Document the Workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/usage-workflow.md`

- [ ] **Step 1: Add command documentation**

Document:

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli workflow watchlist.csv --output-dir workflow-dist
```

Include offline fixture command:

```powershell
python -m taiwan_stock_analysis.cli workflow watchlist.csv --fixture-root fixtures --output-dir workflow-dist --offline-prices
```

- [ ] **Step 2: Link generated outputs**

List:

- `workflow-dist/workflow_summary.json`
- `workflow-dist/dashboard.html`
- `workflow-dist/reports/`
- `workflow-dist/valuation.csv`
- `workflow-dist/valuation-reports/`
- `workflow-dist/comparison/`

---

### Task 5: Verify and Finish

**Files:**
- All changed files.

- [ ] **Step 1: Run full tests**

Run: `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run markdown link check**

Expected: `missing_links []`.

- [ ] **Step 3: Commit and push**

Commit message:

```text
feat: add watchlist workflow command
```
