# Dashboard Workflow Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard discover and render `workflow_summary.json` so one-shot workflow runs are inspectable from `dashboard.html`.

**Architecture:** Extend the existing static dashboard pipeline. `discover_dashboard_items()` will collect workflow summary files, and `render_dashboard_html()` will render a concise workflow section with links and status.

**Tech Stack:** Python standard library, existing static HTML renderer, `unittest`.

---

## File Structure

- Modify: `src/taiwan_stock_analysis/dashboard.py`
  - Add `workflow_summaries` discovery.
  - Render workflow status, successful stock IDs, valuation CSV, dashboard, comparison links, and skipped reason.
- Modify: `tests/test_dashboard.py`
  - Cover workflow summary discovery and rendering.
- Modify: `docs/usage-workflow.md`
  - Document that dashboard now shows workflow run status.
- Modify: `README.md`
  - Add workflow summary visibility to the one-shot workflow section.

---

### Task 1: Discover Workflow Summaries

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing discovery test**

Add `workflow_summary.json` fixture and verify `discover_dashboard_items()` returns it under `workflow_summaries`.

- [ ] **Step 2: Implement discovery**

In `discover_dashboard_items()`, read `workflow_summary.json` when present. If invalid JSON, record a summary with an error field.

- [ ] **Step 3: Run focused test**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard -v`

Expected: PASS.

---

### Task 2: Render Workflow Section

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write rendering test**

Verify dashboard HTML includes:

- `workflow_summary.json`
- valuation CSV path or link
- successful stock IDs
- comparison skipped reason
- dashboard path

- [ ] **Step 2: Implement renderer helper**

Add `_workflow_summary_rows()` to keep `render_dashboard_html()` readable.

- [ ] **Step 3: Run focused dashboard tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard -v`

Expected: PASS.

---

### Task 3: Document Dashboard Visibility

**Files:**
- Modify: `README.md`
- Modify: `docs/usage-workflow.md`

- [ ] **Step 1: Update docs**

Document that `dashboard.html` now shows workflow run status and links to `workflow_summary.json`, valuation CSV, comparison outputs, and generated reports.

---

### Task 4: Verify and Finish

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
feat: show workflow summaries on dashboard
```
