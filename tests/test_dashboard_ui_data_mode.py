from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard_ui.page import render as render_page
from taiwan_stock_analysis.dashboard_ui import page_script


_NODE = shutil.which("node")
_SCRIPT_SOURCE = Path(page_script.__file__).with_name("script.js").read_text(encoding="utf-8")


def _status_policy_block() -> str:
    start = _SCRIPT_SOURCE.index("var MARKET_STATUS_POLICY")
    end = _SCRIPT_SOURCE.index("function activateTab", start)
    return _SCRIPT_SOURCE[start:end]


def _production_failure_block() -> str:
    start = _SCRIPT_SOURCE.index("function dashboardDataMode")
    end = _SCRIPT_SOURCE.index("function liveUpdateCountdown", start)
    return _SCRIPT_SOURCE[start:end]


def _breadth_load_block() -> str:
    start = _SCRIPT_SOURCE.index("function loadMarketBreadth")
    end = _SCRIPT_SOURCE.index("function liveSymbols", start)
    return _SCRIPT_SOURCE[start:end]


def _live_fetch_block() -> str:
    start = _SCRIPT_SOURCE.index("function liveRetryAfterSeconds")
    end = _SCRIPT_SOURCE.index("function initLiveMarket", start)
    return _SCRIPT_SOURCE[start:end]


def _post_json_block() -> str:
    start = _SCRIPT_SOURCE.index("function postJson")
    end = _SCRIPT_SOURCE.index("function setTopbarPill", start)
    return _SCRIPT_SOURCE[start:end]


def _live_quote_map_block() -> str:
    start = _SCRIPT_SOURCE.index("function liveQuoteMap")
    end = _SCRIPT_SOURCE.index("function liveIndex", start)
    return _SCRIPT_SOURCE[start:end]


def _screener_quote_block() -> str:
    start = _SCRIPT_SOURCE.index("function screenerOverlayQuoteTrendReady")
    end = _SCRIPT_SOURCE.index("function liveSyncBreadthRows", start)
    return _SCRIPT_SOURCE[start:end]


def _strategy_block() -> str:
    start = _SCRIPT_SOURCE.index("function liveUpdateStrategy")
    end = _SCRIPT_SOURCE.index("function liveApplySnapshot", start)
    return _SCRIPT_SOURCE[start:end]


class DashboardDataModePageTests(unittest.TestCase):
    def test_production_mode_is_machine_readable_and_visible_without_enabling_live_api(self) -> None:
        html = render_page(
            {},
            data_mode="production",
            live_api_enabled=False,
            admission_summary={"rejected_count": 2},
        )

        self.assertIn('data-dashboard-mode="production"', html)
        self.assertIn('data-data-mode="production"', html)
        self.assertIn('data-data-mode-badge="production"', html)
        self.assertIn('data-admission-rejected-count="2"', html)
        self.assertIn("已封鎖 2 份", html)
        self.assertIn("正式資料模式", html)
        self.assertIn('data-live-api-enabled="false"', html)

    def test_demo_mode_has_a_prominent_warning_without_disabling_live_api(self) -> None:
        html = render_page({}, data_mode="demo", live_api_enabled=True)

        self.assertIn('data-dashboard-mode="demo"', html)
        self.assertIn('data-data-mode="demo"', html)
        self.assertIn('data-data-mode-badge="demo"', html)
        self.assertIn('data-admission-rejected-count="0"', html)
        self.assertIn("Demo 模式", html)
        self.assertIn("DEMO／示範資料，不可作投資依據", html)
        self.assertIn('data-live-api-enabled="true"', html)

    def test_read_only_live_page_does_not_offer_a_force_refresh_button(self) -> None:
        read_only = render_page(
            {},
            action_api_enabled=False,
            live_api_enabled=True,
            data_mode="production",
        )
        mutable = render_page(
            {},
            action_api_enabled=True,
            live_api_enabled=True,
            data_mode="production",
        )

        read_only_markup = read_only.split("<script>", 1)[0]
        mutable_markup = mutable.split("<script>", 1)[0]
        self.assertNotIn('data-live-refresh="true"', read_only_markup)
        self.assertIn("唯讀自動更新", read_only_markup)
        self.assertIn('data-live-refresh="true"', mutable_markup)

    def test_admission_banner_exposes_only_a_safe_rejection_count(self) -> None:
        html = render_page(
            {},
            data_mode="production",
            admission_summary={
                "rejected_count": 1,
                "rejections": [{"artifact_ref": "SECRET_REJECTION_DETAIL"}],
            },
        )

        self.assertIn('data-admission-rejected-count="1"', html)
        self.assertNotIn("SECRET_REJECTION_DETAIL", html)


@unittest.skipUnless(_NODE, "node is unavailable")
class DashboardProductionFailureScriptTests(unittest.TestCase):
    def test_snapshot_failure_clears_production_residue_but_preserves_demo_content(self) -> None:
        harness = f"""
{_production_failure_block()}

function makeNode(text) {{
  return {{
    textContent:text,
    attributes:{{}},
    setAttribute:function (name, value) {{ this.attributes[name] = String(value); }},
    getAttribute:function (name) {{ return this.attributes[name] || null; }},
    querySelector:function () {{ return null; }},
    classList:{{remove:function () {{}}, add:function () {{}}, toggle:function () {{}}}}
  }};
}}

function run(primaryMode, legacyMode) {{
  var overviewNews = makeNode("fixture-news");
  var intelligenceNews = makeNode("fixture-intelligence");
  var industryMap = makeNode("fixture-industry-map");
  var pulse = makeNode("fixture-pulse");
  var screener = makeNode("fixture-screener");
  var strategy = makeNode("fixture-strategy");
  var strategyGate = makeNode("fixture-gate");
  var selectors = {{
    '[data-live-overview-news="true"]':[overviewNews],
    '[data-live-intelligence-news="true"]':[intelligenceNews],
    '[data-industry-map-grid="true"]':[industryMap],
    '[data-live-overview-pulse="true"]':[pulse],
    '[data-screener-body="true"]':[screener],
    '[data-live-strategy-regime="true"]':[strategy],
    '[data-live-strategy-gate="true"]':[strategyGate]
  }};
  document = {{
    body:{{getAttribute:function (name) {{
      if (name === "data-data-mode") {{ return primaryMode; }}
      return name === "data-dashboard-mode" ? legacyMode : "";
    }}}},
    querySelectorAll:function (selector) {{ return selectors[selector] || []; }},
    querySelector:function (selector) {{
      var matches = selectors[selector] || [];
      return matches.length ? matches[0] : null;
    }}
  }};
  screenerBreadthRows = [{{symbol:"2330"}}];
  screenerTaiwanBreadthRows = [{{symbol:"2330"}}];
  screenerTaiwanBreadthMeta = {{status:"EOD"}};
  marketBreadthIndustryRows = [{{industry_name:"fixture"}}];
  liveIntelligenceNewsRows = [{{title:"fixture"}}];
  liveIntelligenceNewsSignature = "fixture";
  liveIntelligenceNewsVisible = 12;
  liveInvalidateSnapshot("provider outage");
  return {{
    overviewNews:overviewNews.textContent,
    intelligenceNews:intelligenceNews.textContent,
    industryMap:industryMap.textContent,
    pulse:pulse.textContent,
    screener:screener.textContent,
    strategy:strategy.textContent,
    strategyGate:strategyGate.textContent
  }};
}}

var document;
var screenerBreadthRows = [];
var screenerTaiwanBreadthRows = [];
var screenerTaiwanBreadthMeta = null;
var marketBreadthIndustryRows = [];
var liveIntelligenceNewsRows = [];
var liveIntelligenceNewsSignature = "";
var liveIntelligenceNewsVisible = 12;
function liveSymbols() {{ return []; }}
function liveText(selector, value) {{
  var nodes = document.querySelectorAll(selector);
  for (var i = 0; i < nodes.length; i++) {{ nodes[i].textContent = value; }}
}}
function liveUpdateHero() {{}}
function liveUpdateOverviewMetrics() {{}}
function liveUpdateStocks() {{}}
function liveUpdateStrategy() {{}}

process.stdout.write(JSON.stringify({{
  production:run("production", "demo"),
  demo:run("demo", "production")
}}));
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        for value in result["production"].values():
            self.assertTrue(value.startswith("UNAVAILABLE"), value)
        self.assertEqual(
            {
                "overviewNews": "fixture-news",
                "intelligenceNews": "fixture-intelligence",
                "industryMap": "fixture-industry-map",
                "pulse": "fixture-pulse",
                "screener": "fixture-screener",
                "strategy": "fixture-strategy",
                "strategyGate": "fixture-gate",
            },
            result["demo"],
        )

    def test_breadth_failure_clears_existing_production_content(self) -> None:
        harness = f"""
{_production_failure_block()}
{_breadth_load_block()}

function makeNode(text) {{
  return {{
    textContent:text,
    title:"",
    attributes:{{}},
    setAttribute:function (name, value) {{ this.attributes[name] = String(value); }},
    getAttribute:function (name) {{ return this.attributes[name] || null; }},
    querySelector:function () {{ return null; }},
    classList:{{remove:function () {{}}, add:function () {{}}, toggle:function () {{}}}}
  }};
}}

var overviewNews = makeNode("fixture-news");
var screener = makeNode("fixture-screener");
var scope = makeNode("fixture-scope");
var industryStatus = makeNode("fixture-industry");
var selectors = {{
  '[data-live-overview-news="true"]':[overviewNews],
  '[data-screener-body="true"]':[screener],
  '[data-screener-scope-status="true"]':[scope],
  '[data-industry-map-status="true"]':[industryStatus]
}};
var document = {{
  hidden:false,
  body:{{getAttribute:function (name) {{
    return name === "data-dashboard-mode" ? "production" : "";
  }}}},
  querySelectorAll:function (selector) {{ return selectors[selector] || []; }},
  querySelector:function (selector) {{
    var matches = selectors[selector] || [];
    return matches.length ? matches[0] : null;
  }}
}};
var window = {{
  fetch:function () {{ return Promise.reject(new Error("breadth outage")); }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
var AbortController = undefined;
var marketBreadthState = "idle";
var marketBreadthRefreshTimer = null;
var marketBreadthRetryTimer = null;
var marketBreadthFailures = 0;
var marketBreadthIndustryRows = [{{industry_name:"fixture"}}];
var marketBreadthLastLoadedAt = 0;
var marketBreadthTtlMs = 300000;
var marketBreadthLoadedSessionKey = "";
var liveBreadthRefreshPending = false;
var liveRequestInFlight = false;
var screenerUniverseMode = "TW";
var screenerBreadthRows = [{{symbol:"2330"}}];
var screenerTaiwanBreadthRows = [{{symbol:"2330"}}];
var screenerTaiwanBreadthMeta = {{status:"EOD"}};
var liveIntelligenceNewsRows = [{{title:"fixture"}}];
var liveIntelligenceNewsSignature = "fixture";
var liveIntelligenceNewsVisible = 12;
function marketBreadthNeedsRefresh() {{ return true; }}
function marketBreadthContractError() {{ return ""; }}
function screenerLoadBreadth() {{ return true; }}
function scheduleMarketBreadthRefresh() {{}}
function scheduleMarketBreadthRetry() {{}}
function liveRenderIndustrySummaries() {{}}
function populateScreenerIndustriesFromSummaries() {{}}
function liveFetchSnapshot() {{}}
function liveSymbols() {{ return []; }}
function liveText(selector, value) {{
  var nodes = document.querySelectorAll(selector);
  for (var i = 0; i < nodes.length; i++) {{ nodes[i].textContent = value; }}
}}
function liveUpdateHero() {{}}
function liveUpdateOverviewMetrics() {{}}
function liveUpdateStocks() {{}}
function liveUpdateStrategy() {{}}

(async function () {{
  loadMarketBreadth(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify({{
    overviewNews:overviewNews.textContent,
    screener:screener.textContent,
    scope:scope.textContent,
    industryStatus:industryStatus.textContent
  }}));
}})();
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        for value in result.values():
            self.assertTrue(value.startswith("UNAVAILABLE"), value)

    def test_invalid_live_snapshot_fails_closed_before_rendering(self) -> None:
        harness = f"""
{_production_failure_block()}
{_live_fetch_block()}

var news = {{
  textContent:"fixture-news",
  setAttribute:function () {{}},
  getAttribute:function () {{ return null; }}
}};
var selectors = {{'[data-live-overview-news="true"]':[news]}};
var document = {{
  hidden:false,
  body:{{getAttribute:function (name) {{
    return name === "data-dashboard-mode" ? "production" : "";
  }}}},
  querySelectorAll:function (selector) {{ return selectors[selector] || []; }},
  querySelector:function (selector) {{
    var matches = selectors[selector] || [];
    return matches.length ? matches[0] : null;
  }}
}};
var window = {{
  fetch:function () {{
    return Promise.resolve({{
      ok:true,
      headers:{{get:function () {{ return null; }}}},
      json:function () {{
        return Promise.resolve({{
          ok:true,
          schema_version:999,
          kind:"not-a-live-market-snapshot",
          status:"LIVE"
        }});
      }}
    }});
  }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
var AbortController = undefined;
var liveRequestInFlight = false;
var liveVisibleRefreshTimer = null;
var liveMarketTimer = null;
var liveLastRequestAt = 0;
var liveBreadthRefreshPending = false;
var liveIntelligenceNewsRows = [{{title:"fixture"}}];
var liveIntelligenceNewsSignature = "fixture";
var liveIntelligenceNewsVisible = 12;
var screenerBreadthRows = [{{symbol:"2330"}}];
var screenerTaiwanBreadthRows = [{{symbol:"2330"}}];
var screenerTaiwanBreadthMeta = {{status:"EOD"}};
var marketBreadthIndustryRows = [{{industry_name:"fixture"}}];
var applyCount = 0;
function liveSymbols() {{ return []; }}
function liveUpdateCountdown() {{}}
function liveSchedule() {{ return 15; }}
function liveApplySnapshot() {{ applyCount += 1; }}
function liveText(selector, value) {{
  var nodes = document.querySelectorAll(selector);
  for (var i = 0; i < nodes.length; i++) {{ nodes[i].textContent = value; }}
}}
function liveUpdateHero() {{}}
function liveUpdateOverviewMetrics() {{}}
function liveUpdateStocks() {{}}
function liveUpdateStrategy() {{}}

(async function () {{
  liveFetchSnapshot();
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify({{news:news.textContent, applyCount:applyCount}}));
}})();
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertTrue(result["news"].startswith("UNAVAILABLE"), result)
        self.assertEqual(0, result["applyCount"])

    def test_stale_and_delayed_snapshots_render_read_only_but_unavailable_clears(self) -> None:
        harness = f"""
{_live_fetch_block()}

var currentStatus = "STALE";
var applyCount = 0;
var invalidateCount = 0;
var connectionCount = 0;
var document = {{
  hidden:false,
  querySelector:function () {{ return null; }}
}};
var window = {{
  fetch:function () {{
    var status = currentStatus;
    return Promise.resolve({{
      ok:true,
      headers:{{get:function () {{ return null; }}}},
      json:function () {{
        return Promise.resolve({{
          ok:true,
          schema_version:1,
          kind:"live_market_snapshot",
          status:status,
          market:{{status:status}},
          source_status:{{quotes:{{status:status}}}},
          quotes:[{{symbol:"2330", status:status, price:100}}],
          generated_at:"2026-08-28T12:00:00+08:00"
        }});
      }}
    }});
  }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
var AbortController = undefined;
var liveRequestInFlight = false;
var liveVisibleRefreshTimer = null;
var liveMarketTimer = null;
var liveLastRequestAt = 0;
var liveNextRefreshAt = 0;
var liveBreadthRefreshPending = false;
function liveSymbols() {{ return ["2330"]; }}
function liveUpdateCountdown() {{}}
function liveSchedule() {{ return 60; }}
function liveApplySnapshot() {{ applyCount += 1; }}
function liveInvalidateSnapshot() {{ invalidateCount += 1; }}
function liveUpdateConnection() {{ connectionCount += 1; }}
function liveText() {{}}

async function run(status) {{
  currentStatus = status;
  applyCount = 0;
  invalidateCount = 0;
  connectionCount = 0;
  liveFetchSnapshot(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  return {{apply:applyCount, invalidate:invalidateCount, connection:connectionCount}};
}}

(async function () {{
  var stale = await run("STALE");
  var delayed = await run("DELAYED");
  var unavailable = await run("UNAVAILABLE");
  process.stdout.write(JSON.stringify({{
    stale:stale,
    delayed:delayed,
    unavailable:unavailable
  }}));
}})();
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertEqual({"apply": 1, "invalidate": 0, "connection": 0}, result["stale"])
        self.assertEqual({"apply": 1, "invalidate": 0, "connection": 0}, result["delayed"])
        self.assertEqual(
            {"apply": 0, "invalidate": 1, "connection": 1},
            result["unavailable"],
        )

    def test_stale_and_delayed_quotes_do_not_overwrite_verified_eod_direction(self) -> None:
        harness = f"""
{_status_policy_block()}
{_live_quote_map_block()}
{_screener_quote_block()}

function sourceStatusAuthoritative(value, statuses) {{
  return Boolean(value && value.authoritative !== false && !value.partial &&
    statuses.indexOf(String(value.status || "").toUpperCase()) !== -1);
}}
function screenerRestoreBreadthBaseline() {{}}
function screenerFinite(value) {{
  var number = Number(value);
  return value == null || value === "" || !isFinite(number) ? null : number;
}}
function screenerFirstValue(value, keys, fallback) {{
  for (var i = 0; i < keys.length; i++) {{
    if (value[keys[i]] != null) {{ return value[keys[i]]; }}
  }}
  return fallback;
}}
function livePercent(value) {{ return Number(value).toFixed(2) + "%"; }}
var screenerBreadthExpectedSessionDate = "2026-08-28";

var mapped = liveQuoteMap({{status:"STALE", quotes:[
  {{symbol:"LIVE", status:"LIVE"}},
  {{symbol:"EOD", status:"EOD"}},
  {{symbol:"STALE", status:"STALE"}},
  {{symbol:"DELAYED", status:"DELAYED"}},
  {{symbol:"NO", status:"UNAVAILABLE"}}
]}});
var decisionReady = {{
  invalid:liveSnapshotDecisionReady(null),
  live:liveSnapshotDecisionReady({{
    status:"LIVE", source_status:{{quotes:{{status:"LIVE", authoritative:true}}}},
    missing_symbols:[]
  }}),
  eod:liveSnapshotDecisionReady({{
    status:"EOD", source_status:{{quotes:{{status:"EOD", authoritative:true}}}},
    missing_symbols:[]
  }}),
  stale:liveSnapshotDecisionReady({{
    status:"STALE", source_status:{{quotes:{{status:"EOD", authoritative:true}}}},
    missing_symbols:[]
  }}),
  delayed:liveSnapshotDecisionReady({{
    status:"DELAYED", source_status:{{quotes:{{status:"LIVE", authoritative:true}}}},
    missing_symbols:[]
  }})
}};
var row = {{
  tags:["bull", "semiconductor"],
  industry:"半導體",
  price:101,
  status:"EOD",
  sourceEventTime:"2026-08-28",
  reasonAll:"fixture-direction"
}};
var rowWithoutQuote = {{
  tags:["bear", "electronics"],
  industry:"電子",
  reasonAll:"fixture-direction"
}};
screenerApplyLiveQuote(
  row,
  {{symbol:"2330", status:"STALE", price:100, change_percent:3.5,
    session_date:"2026-08-28"}},
  []
);
screenerApplyLiveQuote(rowWithoutQuote, null, []);
process.stdout.write(JSON.stringify({{
  mapped:Object.keys(mapped).sort(),
  decisionReady:decisionReady,
  price:row.price,
  tags:row.tags,
  reasonAll:row.reasonAll,
  noQuoteTags:rowWithoutQuote.tags,
  noQuoteReason:rowWithoutQuote.reasonAll
}}));
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        self.assertEqual(["DELAYED", "EOD", "LIVE", "STALE"], result["mapped"])
        self.assertEqual(
            {
                "invalid": False,
                "live": True,
                "eod": True,
                "stale": False,
                "delayed": False,
            },
            result["decisionReady"],
        )
        self.assertEqual(101, result["price"])
        self.assertIn("bull", result["tags"])
        self.assertEqual("fixture-direction", result["reasonAll"])
        self.assertIn("bear", result["noQuoteTags"])
        self.assertEqual("fixture-direction", result["noQuoteReason"])

    def test_stale_and_delayed_snapshots_disable_strategy_with_visible_status_time(self) -> None:
        harness = f"""
{_status_policy_block()}
{_live_quote_map_block()}
{_strategy_block()}

function makeNode(text) {{
  return {{
    textContent:text || "",
    attributes:{{}},
    children:[],
    setAttribute:function (name, value) {{ this.attributes[name] = String(value); }},
    getAttribute:function (name) {{ return this.attributes[name] || null; }},
    appendChild:function (child) {{ this.children.push(child); this.textContent += child.textContent; }},
    querySelector:function () {{ return null; }},
    classList:{{toggle:function () {{}}}}
  }};
}}
function sourceStatusAuthoritative(value, statuses) {{
  return Boolean(value && value.authoritative !== false && !value.partial &&
    statuses.indexOf(String(value.status || "").toUpperCase()) !== -1);
}}
function liveText(selector, value) {{
  var nodes = document.querySelectorAll(selector);
  for (var i = 0; i < nodes.length; i++) {{ nodes[i].textContent = value; }}
}}

function run(status) {{
  var regime = makeNode("fixture-bullish");
  var posture = makeNode("fixture-posture");
  var mode = makeNode("");
  var gate = makeNode("fixture-gate");
  gate.attributes["data-research-gate-ready"] = "true";
  var fit = makeNode("");
  var card = makeNode("");
  card.attributes["data-live-strategy-family"] = "trend";
  card.querySelector = function () {{ return fit; }};
  var selectors = {{
    '[data-live-strategy-regime="true"]':[regime],
    '[data-live-strategy-posture="true"]':[posture],
    '[data-live-strategy-mode="true"]':[mode],
    '[data-live-strategy-gate="true"]':[gate],
    '[data-live-strategy-family]':[card]
  }};
  document = {{
    querySelectorAll:function (selector) {{ return selectors[selector] || []; }},
    querySelector:function (selector) {{
      var nodes = selectors[selector] || [];
      return nodes.length ? nodes[0] : null;
    }},
    createElement:function () {{ return makeNode(""); }}
  }};
  liveUpdateStrategy({{
    status:status,
    generated_at:"2026-08-28T12:34:56+08:00",
    market:{{regime:"偏多", posture:"可積極", strategy:"trend"}},
    source_status:{{quotes:{{status:status, authoritative:true}}}},
    missing_symbols:[]
  }});
  return {{
    regime:regime.textContent,
    posture:posture.textContent,
    mode:mode.textContent,
    gate:gate.textContent,
    fit:fit.textContent
  }};
}}

var document;
process.stdout.write(JSON.stringify({{stale:run("STALE"), delayed:run("DELAYED")}}));
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)

        for status, values in (("STALE", result["stale"]), ("DELAYED", result["delayed"])):
            self.assertIn(status, values["regime"])
            self.assertIn("2026-08-28 12:34:56", values["posture"])
            self.assertIn(status, values["mode"])
            self.assertIn("停用", values["gate"])
            self.assertIn("停用", values["fit"])

    def test_manual_live_snapshot_refresh_bypasses_backend_cache_only_when_forced(self) -> None:
        harness = f"""
{_post_json_block()}
{_live_fetch_block()}

var requestedRequests = [];
var document = {{
  hidden:false,
  body:{{getAttribute:function (name) {{
    return name === "data-action-api-token" ? "local-test-token" : "";
  }}}},
  querySelector:function () {{ return null; }}
}};
var window = {{
  fetch:function (url, options) {{
    requestedRequests.push({{
      url:url,
      method:(options && options.method) || "GET",
      token:options && options.headers
        ? options.headers["X-Taiwan-Equity-Lens-Token"] || ""
        : "",
      body:options && options.body ? JSON.parse(options.body) : null
    }});
    return Promise.resolve({{
      ok:true,
      status:200,
      headers:{{get:function () {{ return null; }}}},
      json:function () {{ return Promise.resolve({{
        ok:true,
        schema_version:1,
        kind:"live_market_snapshot",
        status:"LIVE",
        market:{{status:"LIVE"}},
        source_status:{{quotes:{{status:"LIVE"}}}}
      }}); }}
    }});
  }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
var AbortController = undefined;
var liveRequestInFlight = false;
var liveVisibleRefreshTimer = null;
var liveMarketTimer = null;
var liveLastRequestAt = 0;
var liveNextRefreshAt = 0;
var liveBreadthRefreshPending = false;
function liveSymbols() {{ return ["2330", "2317"]; }}
function liveUpdateCountdown() {{}}
function liveSchedule() {{ return 60; }}
function liveApplySnapshot() {{}}
function liveInvalidateSnapshot() {{}}
function liveUpdateConnection() {{}}
function liveText() {{}}

(async function () {{
  liveFetchSnapshot(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  liveFetchSnapshot(true);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify(requestedRequests));
}})();
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(
            [
                {
                    "url": "/api/live/snapshot?symbols=2330%2C2317",
                    "method": "GET",
                    "token": "",
                    "body": None,
                },
                {
                    "url": "/api/live/snapshot/refresh",
                    "method": "POST",
                    "token": "local-test-token",
                    "body": {"symbols": ["2330", "2317"]},
                },
            ],
            json.loads(completed.stdout),
        )

    def test_manual_breadth_refresh_bypasses_backend_cache_only_when_forced(self) -> None:
        harness = f"""
{_post_json_block()}
{_breadth_load_block()}

var requestedRequests = [];
var requestedSnapshotForces = [];
var document = {{
  hidden:false,
  body:{{getAttribute:function (name) {{
    return name === "data-action-api-token" ? "local-test-token" : "";
  }}}},
  querySelector:function () {{ return null; }}
}};
var window = {{
  fetch:function (url, options) {{
    requestedRequests.push({{
      url:url,
      method:(options && options.method) || "GET",
      token:options && options.headers
        ? options.headers["X-Taiwan-Equity-Lens-Token"] || ""
        : "",
      body:options && options.body ? JSON.parse(options.body) : null
    }});
    return Promise.resolve({{
      ok:true,
      status:200,
      json:function () {{
        return Promise.resolve({{
          industry_summaries:[],
          status:"EOD",
          mode:"EOD_FULL+LIVE_PAGE"
        }});
      }}
    }});
  }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
var AbortController = undefined;
var marketBreadthState = "idle";
var marketBreadthRefreshTimer = null;
var marketBreadthRetryTimer = null;
var marketBreadthFailures = 0;
var marketBreadthIndustryRows = [];
var marketBreadthLastLoadedAt = 0;
var marketBreadthTtlMs = 300000;
var marketBreadthLoadedSessionKey = "";
var liveBreadthRefreshPending = false;
var liveBreadthRefreshForce = false;
var liveRequestInFlight = false;
var screenerUniverseMode = "TW";
function marketBreadthNeedsRefresh() {{ return true; }}
function marketBreadthContractError() {{ return ""; }}
function screenerLoadBreadth() {{ return true; }}
function marketBreadthRefreshIntervalMs() {{ return 300000; }}
function marketBreadthTaipeiSessionKey() {{ return "2026-08-28"; }}
function scheduleMarketBreadthRefresh() {{}}
function scheduleMarketBreadthRetry() {{}}
function liveRenderIndustrySummaries() {{}}
function populateScreenerIndustriesFromSummaries() {{}}
function liveFetchSnapshot(force) {{ requestedSnapshotForces.push(Boolean(force)); }}
function liveFailClosedProduction() {{}}

(async function () {{
  loadMarketBreadth(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  loadMarketBreadth(true);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify({{
    breadthRequests:requestedRequests,
    snapshotForces:requestedSnapshotForces
  }}));
}})();
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(
            {
                "breadthRequests": [
                    {
                        "url": "/api/market/breadth",
                        "method": "GET",
                        "token": "",
                        "body": None,
                    },
                    {
                        "url": "/api/market/breadth/refresh",
                        "method": "POST",
                        "token": "local-test-token",
                        "body": {},
                    },
                ],
                "snapshotForces": [False, True],
            },
            json.loads(completed.stdout),
        )


if __name__ == "__main__":
    unittest.main()
