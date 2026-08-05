"""Node-executed tests for the dashboard's inline JavaScript.

The redesign shipped two real JS bugs that Python unit tests could not see and
that only a browser / `node` caught: a NaN sort comparator, and a raw newline in
the Python triple-quoted SCRIPT string that made the whole inline script an
unterminated-string syntax error. The migration that dropped the old renderer
also deleted the repo's only JS-executing test. These tests restore that safety
net: `node --check` on the shipped script (catches the syntax-error class), and a
Node-driven run of the sentiment-sort comparator (catches the NaN/ordering class).

Skipped when `node` is unavailable so environments without it do not fail.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard import render_dashboard_html

_NODE = shutil.which("node")


def _shipped_script(html: str) -> str:
    match = re.search(r"<script>(.*)</script>", html, re.S)
    assert match, "no inline <script> found in rendered dashboard"
    return match.group(1)


def _sort_block(script: str) -> str:
    """Extract SENTIMENT_SORT_ATTR + sentimentCardValue + sortSentimentCards."""
    start = script.index("var SENTIMENT_SORT_ATTR")
    end = script.index("function initIndustrySentimentSort")
    block = script[start:end]
    assert "function sortSentimentCards" in block, "sortSentimentCards not in extracted block"
    assert "function sentimentCardValue" in block, "sentimentCardValue not in extracted block"
    return block


def _bulk_filter_block(script: str) -> str:
    """Extract readFilterState/rowMatchesFilters/applyQueueFilters (filter
    logic) plus queueVisibleRows/queueRowCheckbox/queueSelectedRows/
    updateBulkSelectionUI/initBulkSelection (bulk-selection logic).

    The bulk <-> filter interaction under test (item B) lives entirely in how
    applyQueueFilters()'s `.hidden` class toggle feeds queueVisibleRows() --
    both "select currently visible" (initBulkSelection's selectVisible
    handler) and the live bulk count (updateBulkSelectionUI) read from it, so
    a row hidden by a filter is excluded from both without either function
    needing to know about filters at all.
    """
    start = script.index("function readFilterState")
    end = script.index("function initBulkStaticCopy")
    block = script[start:end]
    for name in (
        "function applyQueueFilters",
        "function queueVisibleRows",
        "function queueSelectedRows",
        "function updateBulkSelectionUI",
        "function initBulkSelection",
    ):
        assert name in block, f"{name} not in extracted block"
    return block


def _evidence_guard_block(script: str) -> str:
    """Extract evidenceGuardMessage: the single-row served-path pre-submit
    evidence guard (item A). Already implemented (commit 9ee93eb) and covered
    by a substring check on the rendered HTML
    (PageTests.test_inline_script_has_bulk_and_single_row_evidence_guards);
    this adds real execution coverage of its branch logic, which nothing
    previously exercised.
    """
    start = script.index("function evidenceGuardMessage")
    end = script.index("function handleReviewAction")
    block = script[start:end]
    assert "function evidenceGuardMessage" in block, "evidenceGuardMessage not in extracted block"
    return block


def _run_node(source: str) -> str:
    assert _NODE
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "harness.js"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [_NODE, str(path)], capture_output=True, encoding="utf-8", timeout=30, check=False
        )
        assert result.returncode == 0, f"node failed: {result.stderr}"
        return result.stdout.strip()


class ScriptSourceTests(unittest.TestCase):
    """Guards on how the inline script reaches the page.

    The body lives in dashboard_ui/script.js and is read at import time. These
    run without node because they protect the two ways that plumbing can break
    silently: the file going missing from an install, and the file arriving with
    CRLF line endings under core.autocrlf.
    """

    def test_script_body_comes_from_a_real_js_file(self):
        from taiwan_stock_analysis.dashboard_ui import page_script

        source = Path(page_script.__file__).with_name("script.js")
        self.assertTrue(source.is_file(), f"missing packaged script body: {source}")
        self.assertEqual(
            page_script.SCRIPT,
            "<script>" + source.read_text(encoding="utf-8") + "</script>",
        )

    def test_inline_script_has_no_carriage_returns(self):
        # A CRLF checkout would still parse, but it would silently change every
        # byte the rendered dashboard.html ships.
        self.assertNotIn("\r", _shipped_script(render_dashboard_html({})))


@unittest.skipUnless(_NODE, "node not available")
class DashboardScriptTests(unittest.TestCase):
    def test_shipped_script_passes_node_check(self):
        # Catches the raw-newline / unterminated-string class of bug that once
        # broke the entire inline script.
        script = _shipped_script(render_dashboard_html({}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shipped.js"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [_NODE, "--check", str(path)], capture_output=True, text=True, timeout=30, check=False
            )
        self.assertEqual(result.returncode, 0, f"node --check failed: {result.stderr}")

    def test_sort_comparator_orders_and_handles_missing(self):
        block = _sort_block(_shipped_script(render_dashboard_html({})))
        # Cards: two real ties (55.4), one higher (60.1), two missing ("-").
        # Descending by score; ties + all-missing broken by category ascending;
        # missing values (-Infinity) sort last. The all-missing pair exercises the
        # NaN path (-Infinity - -Infinity) the comparator's "diff || tiebreak"
        # idiom guards -- a naive "if (diff !== 0)" would return NaN here.
        harness = block + """
function card(category, score) {
  return {
    dataset: { sentimentScore: score },
    getAttribute: function (name) { return name === "data-sentiment-category" ? category : null; }
  };
}
var order = [];
var cards = [
  card("Gamma", "-"),
  card("Alpha", "55.4"),
  card("Beta", "60.1"),
  card("Epsilon", "-"),
  card("Delta", "55.4")
];
var grid = {
  querySelectorAll: function () { return cards; },
  appendChild: function (c) { order.push(c.getAttribute("data-sentiment-category")); }
};
sortSentimentCards(grid, "score");
console.log(JSON.stringify(order));
"""
        order = json.loads(_run_node(harness))
        self.assertEqual(order, ["Beta", "Alpha", "Delta", "Epsilon", "Gamma"])

    def test_unknown_sort_key_falls_back_to_score(self):
        block = _sort_block(_shipped_script(render_dashboard_html({})))
        harness = block + """
function card(category, score) {
  return {
    dataset: { sentimentScore: score },
    getAttribute: function (name) { return name === "data-sentiment-category" ? category : null; }
  };
}
var order = [];
var cards = [card("Alpha", "10"), card("Beta", "20")];
var grid = {
  querySelectorAll: function () { return cards; },
  appendChild: function (c) { order.push(c.getAttribute("data-sentiment-category")); }
};
sortSentimentCards(grid, "totally-unknown-key");
console.log(JSON.stringify(order));
"""
        order = json.loads(_run_node(harness))
        # Falls back to score -> descending: Beta(20) before Alpha(10).
        self.assertEqual(order, ["Beta", "Alpha"])

    def test_select_visible_only_selects_unhidden_rows_and_excludes_filtered_rows_from_bulk_set(self):
        # Item B: past bug class lived exactly here -- bulk selection reading
        # straight from a raw row list instead of the filtered/visible set,
        # so a hidden row's stale selection could still be bulk-updated.
        block = _bulk_filter_block(_shipped_script(render_dashboard_html({})))
        harness = block + """
function makeCheckbox(checkedInitially) {
  return { checked: !!checkedInitially };
}
function makeRow(category, checkbox) {
  var hidden = false;
  return {
    checkbox: checkbox,
    getAttribute: function (name) { return name === "data-category" ? category : null; },
    textContent: category,
    classList: {
      toggle: function (name, force) { if (name === "hidden") { hidden = !!force; } },
      contains: function (name) { return name === "hidden" ? hidden : false; }
    },
    querySelector: function (selector) {
      return selector === '[data-queue-select="true"]' ? checkbox : null;
    }
  };
}
function makeFilterControl(name, value) {
  return { value: value, getAttribute: function (attr) { return attr === "data-queue-filter" ? name : null; } };
}
function makeToggleControl() {
  var listeners = {};
  return {
    checked: false,
    indeterminate: false,
    addEventListener: function (type, handler) { listeners[type] = handler; },
    dispatch: function (type) { listeners[type](); }
  };
}

// A/C match the "category=high" filter below; B/D don't. B starts
// pre-checked to simulate a stale selection made before the filter change.
var rowA = makeRow("high", makeCheckbox(true));
var rowB = makeRow("low", makeCheckbox(true));
var rowC = makeRow("high", makeCheckbox(false));
var rowD = makeRow("low", makeCheckbox(false));
var allRows = [rowA, rowB, rowC, rowD];

var filterControls = [
  makeFilterControl("severity", ""),
  makeFilterControl("category", "high"),
  makeFilterControl("priority", ""),
  makeFilterControl("status", ""),
  makeFilterControl("search", "")
];
var countEl = { textContent: "" };
var selectVisible = makeToggleControl();
var emptyState = { hidden: false };

var document = {
  querySelectorAll: function (selector) {
    if (selector === "[data-queue-filter]") { return filterControls; }
    if (selector === ".queue-row[data-stock]") { return allRows; }
    return [];
  },
  querySelector: function (selector) {
    if (selector === '[data-review-action-empty="true"]') { return emptyState; }
    if (selector === '[data-queue-bulk-count="true"]') { return countEl; }
    if (selector === '[data-queue-select-visible="true"]') { return selectVisible; }
    return null;
  }
};

applyQueueFilters();
initBulkSelection();

var beforeVisible = !rowA.classList.contains("hidden") && !rowC.classList.contains("hidden");
var beforeHidden = rowB.classList.contains("hidden") && rowD.classList.contains("hidden");
var beforeSelectedCategories = queueSelectedRows().map(function (r) { return r.getAttribute("data-category"); });
var beforeCountText = countEl.textContent;
var emptyStateHiddenWhenSomeRowsVisible = emptyState.hidden;

selectVisible.checked = true;
selectVisible.dispatch("change");

var afterSelectedCategories = queueSelectedRows().map(function (r) { return r.getAttribute("data-category"); });

console.log(JSON.stringify({
  beforeVisible: beforeVisible,
  beforeHidden: beforeHidden,
  beforeSelectedCategories: beforeSelectedCategories,
  beforeCountText: beforeCountText,
  emptyStateHiddenWhenSomeRowsVisible: emptyStateHiddenWhenSomeRowsVisible,
  rowBCheckedAfterSelectVisible: rowB.checkbox.checked,
  rowDCheckedAfterSelectVisible: rowD.checkbox.checked,
  afterSelectedCategories: afterSelectedCategories,
  afterCountText: countEl.textContent
}));
"""
        result = json.loads(_run_node(harness))
        self.assertTrue(result["beforeVisible"], "category=high rows must stay visible")
        self.assertTrue(result["beforeHidden"], "category=low rows must be hidden by the filter")
        # Row B's stale pre-filter selection is excluded from the bulk set the
        # moment it's hidden -- queueSelectedRows() is visible-rows ∩ checked,
        # not "every row whose checkbox happens to be checked".
        self.assertEqual(result["beforeSelectedCategories"], ["high"])
        self.assertEqual(result["beforeCountText"], "已選取 1 筆")
        self.assertTrue(result["emptyStateHiddenWhenSomeRowsVisible"])
        # "選取目前顯示" (initBulkSelection's selectVisible handler) must only
        # ever touch rows queueVisibleRows() returns -- hidden rows' checkboxes
        # are left completely alone, whatever state they already had.
        self.assertTrue(result["rowBCheckedAfterSelectVisible"])  # untouched, was already true
        self.assertFalse(result["rowDCheckedAfterSelectVisible"])  # untouched, was already false
        self.assertEqual(sorted(result["afterSelectedCategories"]), ["high", "high"])
        self.assertEqual(result["afterCountText"], "已選取 2 筆")

    def test_evidence_guard_blocks_only_blank_evidence_required_non_open_updates(self):
        # Item A: already implemented (commit 9ee93eb) and covered by a
        # substring check on the rendered HTML; this adds real execution
        # coverage of evidenceGuardMessage's branch logic.
        block = _evidence_guard_block(_shipped_script(render_dashboard_html({})))
        harness = block + """
function row(requiresEvidence, hasEvidence) {
  return {
    getAttribute: function (name) {
      if (name === "data-requires-evidence") { return requiresEvidence; }
      if (name === "data-has-evidence") { return hasEvidence; }
      return null;
    }
  };
}
var blankPayload = { status: "done", note: "", reviewer: "", evidence_url: "" };
var filledPayload = { status: "done", note: "n", reviewer: "r", evidence_url: "e" };
var openPayload = { status: "open", note: "", reviewer: "", evidence_url: "" };
console.log(JSON.stringify({
  blocksBlankEvidenceRequired: evidenceGuardMessage(row("true", "false"), blankPayload) !== "",
  allowsFilledEvidenceRequired: evidenceGuardMessage(row("true", "false"), filledPayload) === "",
  allowsAlreadyHasEvidenceEvenIfBlanked: evidenceGuardMessage(row("true", "true"), blankPayload) === "",
  allowsReopenToOpenEvenIfBlank: evidenceGuardMessage(row("true", "false"), openPayload) === "",
  allowsNonEvidenceRowRegardlessOfBlank: evidenceGuardMessage(row("false", "false"), blankPayload) === "",
  allowsWhenNoRowMatched: evidenceGuardMessage(null, blankPayload) === ""
}));
"""
        result = json.loads(_run_node(harness))
        self.assertTrue(result["blocksBlankEvidenceRequired"])
        self.assertTrue(result["allowsFilledEvidenceRequired"])
        self.assertTrue(result["allowsAlreadyHasEvidenceEvenIfBlanked"])
        self.assertTrue(result["allowsReopenToOpenEvenIfBlank"])
        self.assertTrue(result["allowsNonEvidenceRowRegardlessOfBlank"])
        self.assertTrue(result["allowsWhenNoRowMatched"])


if __name__ == "__main__":
    unittest.main()
