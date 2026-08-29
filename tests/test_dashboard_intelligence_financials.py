from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard_ui import page_script
from taiwan_stock_analysis.dashboard_ui.views.intelligence import (
    render_intelligence_view,
)


_NODE = shutil.which("node")
_SCRIPT_SOURCE = Path(page_script.__file__).with_name("script.js").read_text(
    encoding="utf-8"
)


def _financial_script_block() -> str:
    policy_start = _SCRIPT_SOURCE.find("var MARKET_STATUS_POLICY")
    policy_end = _SCRIPT_SOURCE.find("function activateTab", policy_start)
    start = _SCRIPT_SOURCE.find("function liveFinancialStatusLabel")
    if policy_start < 0 or policy_end < 0 or start < 0:
        return ""
    end = _SCRIPT_SOURCE.find("function liveNewsArticle", start)
    return _SCRIPT_SOURCE[policy_start:policy_end] + _SCRIPT_SOURCE[start:end]


def _financial_node_harness(body: str) -> str:
    template = r"""
__BLOCK__

function makeNode(tag, initialText) {
  var node = {
    tagName:String(tag || "div").toUpperCase(),
    children:[],
    attributes:{},
    hidden:false,
    className:"",
    _text:String(initialText || ""),
    appendChild:function (child) { this.children.push(child); return child; },
    setAttribute:function (name, value) { this.attributes[name] = String(value); },
    getAttribute:function (name) { return this.attributes[name] || null; },
    removeAttribute:function (name) { delete this.attributes[name]; },
    addEventListener:function (name, handler) { this["on" + name] = handler; },
    querySelector:function () { return null; },
    querySelectorAll:function () { return []; },
    classList:{add:function () {}, remove:function () {}, toggle:function () {}}
  };
  Object.defineProperty(node, "textContent", {
    get:function () {
      return this._text + this.children.map(function (child) {
        return child.textContent || "";
      }).join("");
    },
    set:function (value) {
      this._text = String(value == null ? "" : value);
      this.children = [];
    }
  });
  return node;
}

var mode = "production";
var grid = makeNode("div", "fixture-agent-score-99");
var statusNode = makeNode("span", "fixture-status");
var countNode = makeNode("span", "fixture-count");
var moreButton = makeNode("button", "顯示更多");
var selectors = {
  '[data-live-fundamentals-grid="true"]':grid,
  '[data-live-fundamentals-status="true"]':statusNode,
  '[data-live-fundamentals-count="true"]':countNode,
  '[data-live-fundamentals-more="true"]':moreButton
};
var document = {
  body:{getAttribute:function (name) {
    if (name === "data-data-mode") { return mode; }
    if (name === "data-live-api-enabled") { return "true"; }
    return "";
  }},
  createElement:function (tag) { return makeNode(tag, ""); },
  querySelector:function (selector) { return selectors[selector] || null; },
  querySelectorAll:function (selector) {
    return selectors[selector] ? [selectors[selector]] : [];
  }
};
var liveFundamentalRows = [];
var liveFundamentalVisible = 24;
var liveFundamentalStatus = "UNAVAILABLE";
var liveFundamentalGeneratedAt = "";
var liveFundamentalSourceLabel = "";
var liveFundamentalOverlayLabel = "";
function dashboardDataMode() { return mode; }
function screenerFinite(value) {
  if (value == null || value === "") { return null; }
  var number = Number(value);
  return isFinite(number) ? number : null;
}
function liveNumber(value, digits) {
  if (value == null || !isFinite(Number(value))) { return "--"; }
  return Number(value).toFixed(digits);
}
function livePercent(value) {
  if (value == null || !isFinite(Number(value))) { return "--"; }
  return Number(value).toFixed(2) + "%";
}

__BODY__
"""
    return template.replace("__BLOCK__", _financial_script_block()).replace(
        "__BODY__", body
    )


def _official_payload(status: str = "EOD") -> dict[str, object]:
    return {
        "status": status,
        "mode": "STALE_FALLBACK+LIVE_PAGE"
        if status == "STALE"
        else "EOD_FULL+LIVE_PAGE",
        "generated_at": "2026-08-28T12:34:56+08:00",
        "source_status": {
            "fundamentals": {
                "status": "FRESH",
                "upstreams": [
                    {
                        "id": "twse-financial-summary",
                        "label": "TWSE 財務摘要",
                        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap14_L",
                        "status": "FRESH",
                    },
                    {
                        "id": "tpex-financial-summary",
                        "label": "TPEx 財務摘要",
                        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O",
                        "status": "FRESH",
                    },
                ],
            },
            "valuation": {
                "status": "FRESH",
                "upstreams": [
                    {
                        "id": "twse-valuation",
                        "label": "TWSE 估值",
                        "url": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
                        "status": "FRESH",
                    }
                ],
            },
            "revenue": {
                "status": "PARTIAL",
                "upstreams": [
                    {
                        "id": "twse-revenue",
                        "label": "TWSE 月營收",
                        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
                        "status": "FRESH",
                    },
                    {
                        "id": "tpex-revenue",
                        "label": "TPEx 月營收",
                        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
                        "status": "PARTIAL",
                    }
                ],
            },
        },
        "full_market": [
            {
                "symbol": "2330",
                "name": "台積電",
                "market": "TWSE",
                "eps": 12.5,
                "financial_period": "115Q2",
                "pe_ratio": 18.2,
                "pb_ratio": 7.1,
                "dividend_yield": 1.5,
                "valuation_date": "2026-08-27",
                "revenue_yoy_percent": 22.8,
                "revenue_month": "2026-07",
            }
        ],
    }


class IntelligenceFinancialViewTests(unittest.TestCase):
    def test_demo_research_cards_have_explicit_replaceable_hooks(self) -> None:
        items = {
            "research_summaries": [
                {
                    "items": [
                        {
                            "stock_id": "2330",
                            "company_name": "台積電",
                            "research_state": "review",
                            "fundamental_review": {
                                "agent_scores": {
                                    "buffett_moat": 99,
                                    "fundamental_quality": 88,
                                }
                            },
                        }
                    ]
                }
            ]
        }

        html = render_intelligence_view(items)

        self.assertIn('data-live-fundamentals-section="true"', html)
        self.assertIn('data-live-fundamentals-status="true"', html)
        self.assertIn('data-live-fundamentals-grid="true"', html)
        self.assertIn('data-live-fundamentals-count="true"', html)
        self.assertIn('data-live-fundamentals-more="true"', html)
        self.assertIn('data-demo-fundamental-card="true"', html)
        self.assertIn("99", html)


@unittest.skipUnless(_NODE, "node is unavailable")
class IntelligenceOfficialFinancialScriptTests(unittest.TestCase):
    def test_official_full_market_fields_render_without_agent_scores_or_predictions(self) -> None:
        body = """
var payload = __PAYLOAD__;
var rendered = liveRenderOfficialFundamentals(payload);
function collectLinks(node, output) {
  if (node && node.attributes && node.attributes.href) {
    output.push(node.attributes.href);
  }
  var children = node && node.children || [];
  for (var i = 0; i < children.length; i++) { collectLinks(children[i], output); }
}
var links = [];
collectLinks(grid, links);
process.stdout.write(JSON.stringify({
  rendered:rendered,
  text:grid.textContent,
  links:links,
  cardCount:grid.children.length,
  state:grid.getAttribute("data-production-state"),
  status:statusNode.textContent,
  count:countNode.textContent
}));
""".replace("__PAYLOAD__", json.dumps(_official_payload(), ensure_ascii=False))
        completed = subprocess.run(
            [_NODE or "node"],
            input=_financial_node_harness(body),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["rendered"])
        self.assertEqual(1, result["cardCount"])
        self.assertEqual("EOD", result["state"])
        for value in (
            "2330",
            "台積電",
            "EPS 12.50",
            "115Q2",
            "PE 18.20",
            "PB 7.10",
            "殖利率 1.50%",
            "月營收 YoY 22.80%",
            "2026-08-27",
            "2026-07",
        ):
            self.assertIn(value, result["text"])
        self.assertIn("基本面 FRESH", result["status"])
        self.assertIn("估值 FRESH", result["status"])
        self.assertIn("月營收 PARTIAL", result["status"])
        self.assertIn("TWSE 財務摘要", result["text"])
        self.assertIn("TWSE 估值", result["text"])
        self.assertIn("TWSE 月營收", result["text"])
        self.assertNotIn("TPEx 財務摘要", result["text"])
        self.assertNotIn("TPEx 月營收", result["text"])
        self.assertEqual(
            {
                "https://openapi.twse.com.tw/v1/opendata/t187ap14_L",
                "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
                "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            },
            set(result["links"]),
        )
        self.assertIn("1 / 1", result["count"])
        self.assertNotIn("fixture-agent-score-99", result["text"])
        self.assertNotIn("買進", result["text"])
        self.assertIn("不產生評分、推薦或預測", result["text"])

    def test_stale_and_delayed_keep_last_official_values_but_unavailable_clears(self) -> None:
        body = """
var payload = __PAYLOAD__;
liveRenderOfficialFundamentals(payload);
var eod = grid.textContent;
liveMarkOfficialFundamentalsReadOnly({
  status:"STALE", generated_at:"2026-08-28T13:00:00+08:00"
});
var stale = {text:grid.textContent, status:statusNode.textContent,
  state:grid.getAttribute("data-production-state")};
liveMarkOfficialFundamentalsReadOnly({
  status:"DELAYED", generated_at:"2026-08-28T13:05:00+08:00"
});
var delayed = {text:grid.textContent, status:statusNode.textContent,
  state:grid.getAttribute("data-production-state")};
liveClearOfficialFundamentals("official financial source unavailable");
var unavailable = {text:grid.textContent, status:statusNode.textContent,
  state:grid.getAttribute("data-production-state")};
process.stdout.write(JSON.stringify({eod:eod, stale:stale, delayed:delayed,
  unavailable:unavailable}));
""".replace("__PAYLOAD__", json.dumps(_official_payload(), ensure_ascii=False))
        completed = subprocess.run(
            [_NODE or "node"],
            input=_financial_node_harness(body),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertIn("EPS 12.50", result["eod"])
        for status_key, expected in (("stale", "STALE"), ("delayed", "DELAYED")):
            self.assertIn("EPS 12.50", result[status_key]["text"])
            self.assertIn("唯讀", result[status_key]["status"])
            self.assertEqual(expected, result[status_key]["state"])
        self.assertNotIn("EPS 12.50", result["unavailable"]["text"])
        self.assertIn("UNAVAILABLE", result["unavailable"]["text"])
        self.assertEqual("UNAVAILABLE", result["unavailable"]["state"])

    def test_production_initialization_clears_fixture_scores_while_demo_preserves_them(self) -> None:
        body = """
mode = "production";
grid.textContent = "fixture-agent-score-99";
initOfficialFundamentals();
var production = grid.textContent;
mode = "demo";
grid.textContent = "fixture-agent-score-99";
initOfficialFundamentals();
var demo = grid.textContent;
process.stdout.write(JSON.stringify({production:production, demo:demo}));
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=_financial_node_harness(body),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertNotIn("fixture-agent-score-99", result["production"])
        self.assertIn("正式 full_market 財報", result["production"])
        self.assertEqual("fixture-agent-score-99", result["demo"])

    def test_breadth_and_live_status_chains_call_financial_renderer(self) -> None:
        self.assertIn("liveRenderOfficialFundamentals(payload)", _SCRIPT_SOURCE)
        self.assertIn("liveMarkOfficialFundamentalsReadOnly(snapshot)", _SCRIPT_SOURCE)
        self.assertIn("liveClearOfficialFundamentals(detail)", _SCRIPT_SOURCE)


if __name__ == "__main__":
    unittest.main()
