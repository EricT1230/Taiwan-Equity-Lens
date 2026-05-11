# Dashboard Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the static dashboard with readable Traditional Chinese labels, clear sections, and stable empty/status states.

**Architecture:** Keep `discover_dashboard_items()` and `render_dashboard_html(items)` as public boundaries. Refactor `dashboard.py` with small private render helpers so tests can lock user-facing HTML without changing data sources or valuation logic.

**Tech Stack:** Python standard library, static HTML/CSS, `unittest`.

---

## File Structure

- Modify: `src/taiwan_stock_analysis/dashboard.py`
  - Replace mojibake labels with Traditional Chinese.
  - Add empty-state rows for reports, comparisons, batch, and workflow sections.
  - Add workflow and batch summary helpers.
- Modify: `tests/test_dashboard.py`
  - Assert clean Traditional Chinese labels and empty states.
  - Assert workflow and batch status summary content.
- Modify: `tests/test_workflow.py`
  - Assert generated workflow dashboard includes polished labels and valid links.
- Modify: `README.md`
  - Mention the dashboard now surfaces workflow and batch status in Traditional Chinese.
- Modify: `docs/usage-workflow.md`
  - Add the same dashboard polish behavior note.

---

### Task 1: Dashboard Labels and Empty States

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing tests for clean labels and empty states**

Add assertions for:

- `台股基本面儀表板`
- `總覽`
- `個股報告`
- `批次狀態`
- `尚無個股報告`
- `尚無批次結果`
- `尚無 workflow summary`

- [ ] **Step 2: Implement label and empty-state helpers**

Add helpers such as `_empty_row()`, `_report_rows()`, `_comparison_rows()`, `_batch_rows()`, and update render output.

- [ ] **Step 3: Run dashboard tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard -v`

Expected: PASS.

---

### Task 2: Workflow and Batch Status Summary

**Files:**
- Modify: `src/taiwan_stock_analysis/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add failing tests for status text**

Verify dashboard output includes:

- `成功 1 / 2`
- `失敗 1`
- `同業比較略過`
- `估值 CSV`

- [ ] **Step 2: Implement status labels**

Add helpers that turn raw status and workflow summary fields into readable text.

- [ ] **Step 3: Run focused tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard -v`

Expected: PASS.

---

### Task 3: Workflow Smoke and Documentation

**Files:**
- Modify: `tests/test_workflow.py`
- Modify: `README.md`
- Modify: `docs/usage-workflow.md`

- [ ] **Step 1: Add workflow dashboard smoke assertions**

Assert generated `dashboard.html` contains polished labels and does not contain known mojibake title text.

- [ ] **Step 2: Update docs**

Mention that dashboard sections are in Traditional Chinese and include workflow/batch status summaries.

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
feat: polish dashboard presentation
```
