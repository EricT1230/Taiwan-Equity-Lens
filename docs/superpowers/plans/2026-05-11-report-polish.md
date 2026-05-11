# Report Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the single-stock HTML report presentation with clean Traditional Chinese labels, readable sections, and stable empty states.

**Architecture:** Keep `render_html_report(result, company_name=None)` as the public entrypoint. Refactor `report.py` into small private helpers that render static HTML without changing analysis, valuation, or scoring data.

**Tech Stack:** Python standard library, static HTML/CSS, `unittest`.

---

## File Structure

- Modify: `src/taiwan_stock_analysis/report.py`
  - Replace corrupted labels with Traditional Chinese.
  - Add readable empty states for missing insights, valuation, scorecard, and diagnostics.
  - Preserve embedded JSON and source links.
- Modify: `tests/test_report.py`
  - Update assertions to clean labels and add missing-data coverage.
- Modify: `README.md`
  - Note that single-stock reports use cleaned Traditional Chinese sections.
- Modify: `docs/usage-workflow.md`
  - Add a report readability note.

---

### Task 1: Clean Report Labels

**Files:**
- Modify: `src/taiwan_stock_analysis/report.py`
- Modify: `tests/test_report.py`

- [ ] **Step 1: Add failing tests for clean labels**

Assert the report contains:

- `基本面分析報告`
- `營運概況`
- `獲利能力`
- `財務體質`
- `品質分數`
- `估值情境`
- `資料品質`

- [ ] **Step 2: Replace report labels**

Rewrite presentation strings in `report.py` while preserving input data and JSON embedding.

- [ ] **Step 3: Run report tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_report -v`

Expected: PASS.

---

### Task 2: Empty States and Tables

**Files:**
- Modify: `src/taiwan_stock_analysis/report.py`
- Modify: `tests/test_report.py`

- [ ] **Step 1: Add missing-data test**

Render a minimal `AnalysisResult` with no scorecard, valuation, diagnostics, or insights and assert readable empty states.

- [ ] **Step 2: Implement empty-state helpers**

Add `_empty_state()`, `_metric_table()`, and safe table helpers.

- [ ] **Step 3: Run focused tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_report -v`

Expected: PASS.

---

### Task 3: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/usage-workflow.md`

- [ ] **Step 1: Add presentation note**

Document that single-stock HTML reports now use cleaned Traditional Chinese sections and explicit empty states.

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
feat: polish single-stock report presentation
```
