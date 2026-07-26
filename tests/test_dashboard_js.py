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


def _run_node(source: str) -> str:
    assert _NODE
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "harness.js"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [_NODE, str(path)], capture_output=True, text=True, timeout=30, check=False
        )
        assert result.returncode == 0, f"node failed: {result.stderr}"
        return result.stdout.strip()


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


if __name__ == "__main__":
    unittest.main()
