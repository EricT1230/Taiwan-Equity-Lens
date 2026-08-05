from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from taiwan_stock_analysis.dashboard_ui.page_script import SCRIPT
from taiwan_stock_analysis.dashboard_ui.views.market import render_market_view
from taiwan_stock_analysis.dashboard_ui.views.screener import render_screener_view


def test_screener_renders_full_market_controls_counts_and_pagination_hooks() -> None:
    html = render_screener_view({}, live_api_enabled=True)

    for hook in (
        'data-screener-market="true"',
        'data-screener-industry="true"',
        'data-screener-sort="true"',
        'data-screener-page-size="true"',
        'data-screener-body="true"',
        'data-screener-pagination="true"',
        'data-screener-scope-status="true"',
        'data-screener-universe-count="true"',
    ):
        assert hook in html
    for key in ("all", "bull", "bear", "disposition", "industry", "us"):
        assert f'data-screener-filter-count="{key}"' in html
    assert ">上漲 <" in html
    assert ">下跌 <" in html
    assert '>選產業</span> <span class="screen-filter-count' in html
    assert 'data-screener-industry-label="true">產業</span>' in html
    assert (
        'data-screener-filter="industry" aria-pressed="false" '
        'aria-haspopup="listbox" disabled aria-disabled="true"'
    ) in html
    assert (
        'data-screener-filter="us" aria-pressed="false" '
        'disabled aria-disabled="true"'
    ) in html
    assert '<option value="short_ratio_desc" disabled>' in html
    assert "上漲／下跌分類只表示本次漲跌" in html


def test_market_view_renders_dynamic_industry_summary_hooks() -> None:
    html = render_market_view({}, live_api_enabled=True)

    assert 'data-industry-map-grid="true"' in html
    assert 'data-industry-map-status="true"' in html
    assert 'data-industry-map-count="true"' in html
    assert 'role="status"' in html


def test_inline_script_enforces_the_exact_breadth_contract_and_live_overlay_boundary() -> None:
    for token in (
        "snapshot.market_catalog",
        "snapshot.full_market",
        "snapshot.industry_summaries",
        'window.fetch("/api/market/breadth"',
        "function loadMarketBreadth",
        "function marketBreadthContractError",
        "payload.ok !== true",
        "payload.schema_version !== 1",
        'payload.kind !== "market_breadth_snapshot"',
        'payload.mode === "LIVE_FULL+OFFICIAL_EOD"',
        '"EOD_PARTIAL+LIVE_PAGE": "PARTIAL"',
        '"STALE_FALLBACK+LIVE_PAGE": "STALE"',
        '"LIVE", "EOD", "PARTIAL", "STALE"',
        "payload.coverage.live_full_coverage !== true",
        "liveQuoteSource.authoritative !== true",
        "Number(liveMarketRatios.TPEX) < 0.95",
        "payload.cross_market_comparable !== true",
        "screenerBreadthStatus === \"STALE\"",
        "function sourceStatusAuthoritative",
        "var quotesAuthoritative = sourceStatusAuthoritative",
        '["LIVE", "EOD"].indexOf(screenerBreadthStatus)',
        "snapshot.live_session_dates",
        "screenerBreadthCoverage.live_quoted_total",
        '"data-base-price-text"',
        'window.fetch("/api/us/market"',
        "function usMarketContractError",
        "美股資料端點只在 loopback 服務模式開放",
        "function activateTaiwanScreener",
        "function activateUsScreener",
        "loadUsMarket(false)",
        'screenerUniverseMode === "US"',
        "FINRA 場外短售成交比並非 short interest",
        "function screenerNormalizeRow",
        "function renderBreadthScreener",
        "function liveRenderIndustrySummaries",
        "function scheduleVisibleLiveRefresh",
        "function marketBreadthNeedsRefresh",
        "function marketBreadthRefreshIntervalMs",
        "marketBreadthClientMinimumMs",
        "function scheduleMarketBreadthRefresh",
        "loadMarketBreadth(true)",
        'data-screener-filter="industry"',
        "industrySelect.showPicker()",
        "function screenerApplyLiveQuote",
        "var breadthRendered = liveSyncBreadthRows(quotes, alerts)",
        "function liveNewsNextVisibleCount",
        'data-intel-news-more="true"',
        "liveIntelligenceNewsRows = news.slice()",
        "liveLastRequestAt = Date.now()",
        '"全市場收盤底稿 · 可見前最多 " + liveSymbolLimit + " 檔行情更新"',
        '"LIVE_FULL"',
        '"EOD_FULL"',
        '"EPS " + liveNumber(row.eps, 2)',
        '" · 月營收 YoY " + livePercent(row.revenueYoy)',
        '" · 估值時點 "',
    ):
        assert token in SCRIPT
    assert "function liveOverlayBreadthRows" not in SCRIPT
    assert "screenerLoadBreadth(snapshot);" not in SCRIPT
    assert "全市場收盤 · 當頁即時" not in SCRIPT


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_breadth_contract_validator_fails_closed() -> None:
    start = SCRIPT.index("function marketBreadthContractError")
    end = SCRIPT.index("function loadMarketBreadth")
    block = SCRIPT[start:end]
    valid = {
        "ok": True,
        "schema_version": 1,
        "kind": "market_breadth_snapshot",
        "mode": "EOD_FULL+LIVE_PAGE",
        "status": "EOD",
        "cross_market_comparable": True,
        "session_fresh": True,
        "session_dates": {"TWSE": "2026-07-29", "TPEX": "2026-07-29"},
        "market_catalog": [{"symbol": "2330"}, {"symbol": "6488"}],
        "full_market": [{"symbol": "2330"}, {"symbol": "6488"}],
        "industry_summaries": [{"industry_name": "半導體業"}],
        "coverage": {
            "catalog_total": 2,
            "quoted_total": 2,
            "market_catalog_counts": {"TWSE": 1, "TPEX": 1},
        },
        "source_status": {
            "alerts": {"status": "FRESH", "authoritative": True},
            "disposition_alerts": {"status": "FRESH", "authoritative": True},
            "notice_alerts": {"status": "FRESH", "authoritative": True},
            "fund_flow": {"status": "EOD", "authoritative": True},
        },
    }
    harness = f"""
{block}
var valid = {json.dumps(valid, ensure_ascii=False)};
var aliasOnly = {{
  ok:true, schema_version:1, kind:"market_breadth_snapshot",
  mode:"EOD_FULL+LIVE_PAGE", catalog:valid.market_catalog,
  market_rows:valid.full_market, industry_summaries:valid.industry_summaries,
  coverage:valid.coverage
}};
var wrongMode = Object.assign({{}}, valid, {{mode:"LIVE_FULL"}});
var liveValid = JSON.parse(JSON.stringify(valid));
liveValid.mode = "LIVE_FULL+OFFICIAL_EOD";
liveValid.status = "LIVE";
liveValid.live_cross_market_comparable = true;
liveValid.live_session_fresh = true;
liveValid.coverage.live_full_coverage = true;
liveValid.coverage.live_ratio = 1;
liveValid.coverage.live_market_ratios = {{TWSE:1, TPEX:1}};
liveValid.source_status.live_quotes = {{
  status:"LIVE", authoritative:true,
  market_statuses:{{TWSE:"LIVE", TPEX:"LIVE"}}
}};
var liveIncomplete = JSON.parse(JSON.stringify(liveValid));
liveIncomplete.coverage.live_market_ratios.TPEX = 0.8;
var stale = Object.assign({{}}, valid, {{
  mode:"STALE_FALLBACK+LIVE_PAGE", status:"STALE", session_fresh:false
}});
var partial = Object.assign({{}}, valid, {{
  mode:"EOD_PARTIAL+LIVE_PAGE", status:"PARTIAL",
  cross_market_comparable:false, session_fresh:false
}});
var falseEod = Object.assign({{}}, valid, {{
  cross_market_comparable:false
}});
var mismatched = Object.assign({{}}, valid, {{
  full_market:[{{symbol:"2330"}}]
}});
process.stdout.write(JSON.stringify({{
  valid:marketBreadthContractError(valid),
  liveValid:marketBreadthContractError(liveValid),
  liveIncomplete:marketBreadthContractError(liveIncomplete),
  stale:marketBreadthContractError(stale),
  partial:marketBreadthContractError(partial),
  falseEod:marketBreadthContractError(falseEod),
  aliasOnly:marketBreadthContractError(aliasOnly),
  wrongMode:marketBreadthContractError(wrongMode),
  mismatched:marketBreadthContractError(mismatched)
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    assert result["valid"] == ""
    assert result["liveValid"] == ""
    assert result["liveIncomplete"]
    assert result["stale"] == ""
    assert result["partial"] == ""
    assert result["falseEod"]
    assert result["aliasOnly"]
    assert result["wrongMode"]
    assert result["mismatched"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_breadth_refresh_interval_uses_server_live_overlay_cadence() -> None:
    start = SCRIPT.index("function marketBreadthRefreshIntervalMs")
    end = SCRIPT.index("function marketBreadthTaipeiSessionKey")
    block = SCRIPT[start:end]
    harness = f"""
var marketBreadthBaseTtlMs = 300000;
var marketBreadthClientMinimumMs = 5000;
{block}
var local = {{
  live:marketBreadthRefreshIntervalMs({{
    live_overlay_enabled:true, refresh_after_seconds:5
  }}),
  authFailure:marketBreadthRefreshIntervalMs({{
    live_overlay_enabled:true, refresh_after_seconds:5, status:"EOD"
  }}),
  boundedMinimum:marketBreadthRefreshIntervalMs({{
    live_overlay_enabled:true, refresh_after_seconds:1
  }}),
  officialOnly:marketBreadthRefreshIntervalMs({{
    live_overlay_enabled:false, refresh_after_seconds:5
  }})
}};
marketBreadthClientMinimumMs = 10000;
local.localMinimum = marketBreadthRefreshIntervalMs({{
  live_overlay_enabled:true, refresh_after_seconds:5
}});
marketBreadthClientMinimumMs = 30000;
local.publicMinimum = marketBreadthRefreshIntervalMs({{
  live_overlay_enabled:true, refresh_after_seconds:5
}});
process.stdout.write(JSON.stringify(local));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result == {
        "live": 5000,
        "authFailure": 5000,
        "boundedMinimum": 5000,
        "officialOnly": 300000,
        "localMinimum": 10000,
        "publicMinimum": 30000,
    }
    assert (
        "marketBreadthTtlMs = marketBreadthRefreshIntervalMs(payload);"
        in SCRIPT
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_live_quote_map_keeps_good_rows_when_batch_is_partial() -> None:
    start = SCRIPT.index("function liveQuoteMap")
    end = SCRIPT.index("function liveIndex")
    block = SCRIPT[start:end]
    harness = f"""
{block}
var mapped = liveQuoteMap({{
  quotes: [
    {{symbol:"2330", status:"LIVE", price:2200}},
    {{symbol:"2317", status:"EOD", price:210}},
    {{symbol:"6488", status:"STALE", price:440}}
  ],
  missing_symbols:["2454"]
}});
process.stdout.write(JSON.stringify(Object.keys(mapped).sort()));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(completed.stdout) == ["2317", "2330"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_breadth_normalizer_derives_only_observed_one_day_tags_and_sorts_missing_last() -> None:
    start = SCRIPT.index("function screenerPayloadRows")
    end = SCRIPT.index("function applyScreenerFilters")
    block = SCRIPT[start:end]
    payload = {
        "company_name": "台積電",
        "stock_id": "2330",
        "exchange": "TSE",
        "category": "半導體",
        "close": 2200,
        "previous_close": 2280,
        "volume": 123456,
        "status": "EOD",
        "attention": True,
        "alert_count": 1,
        "alert_titles": ["注意股票"],
        "eps": 12.34,
        "financial_period": "115Q1",
        "pe_ratio": 18.2,
        "pb_ratio": 7.1,
        "dividend_yield": 1.5,
        "revenue_yoy_percent": 22.8,
        "revenue_mom_percent": 3.2,
        "institutional_status": "EOD",
        "valuation_date": "2026-07-29",
        "session_date": "2026-07-29",
    }
    harness = f"""
function livePercent(value) {{
  if (value === null || value === undefined || value === "") return "--";
  var number = Number(value);
  return (number > 0 ? "+" : "") + number.toFixed(2) + "%";
}}
function liveNumber(value) {{ return value == null ? "--" : String(value); }}
function liveSignedNumber(value) {{ return value == null ? "--" : String(value); }}
function liveTone() {{}}
function screenerMetaSnapshot() {{
  return {{
    coverage:screenerBreadthCoverage,
    mode:screenerBreadthMode,
    status:screenerBreadthStatus,
    sessionDates:screenerBreadthSessionDates,
    sourceStatus:screenerBreadthSourceStatus
  }};
}}
function screenerApplyMeta(meta) {{
  screenerBreadthCoverage = (meta || {{}}).coverage || {{}};
  screenerBreadthMode = (meta || {{}}).mode || "UNAVAILABLE";
  screenerBreadthStatus = (meta || {{}}).status || "UNAVAILABLE";
  screenerBreadthSessionDates = (meta || {{}}).sessionDates || {{}};
  screenerBreadthSourceStatus = (meta || {{}}).sourceStatus || {{}};
}}
function usMarketApiEnabled() {{ return false; }}
{block}
var document = {{
  body:{{getAttribute:function () {{ return "false"; }}}},
  querySelector:function () {{ return null; }},
  querySelectorAll:function () {{ return []; }}
}};
var screenerBreadthRows = [];
var screenerTaiwanBreadthRows = [];
var screenerTaiwanBreadthMeta = null;
var screenerUsBreadthRows = [];
var screenerUsBreadthMeta = null;
var screenerUniverseMode = "TW";
var usMarketState = "idle";
var screenerBreadthPage = 1;
var screenerBreadthPageSize = 50;
var screenerBreadthCoverage = {{}};
var screenerBreadthMode = "UNAVAILABLE";
var screenerBreadthStatus = "UNAVAILABLE";
var screenerBreadthSessionDates = {{}};
var screenerBreadthSourceStatus = {{}};
function screenerState() {{
  return {{filter:"all", query:"", market:"all", industry:"all", sort:"change_desc"}};
}}
var row = screenerNormalizeRow({json.dumps(payload, ensure_ascii=False)}, {{}}, null);
var disposed = screenerNormalizeRow({{
  symbol:"6488", name:"環球晶", market:"TPEx", industry_name:"半導體業",
  disposition:true, alert_count:1, alert_titles:["處置期間"], quote_status:"EOD"
}}, {{}}, null);
var usRow = screenerNormalizeRow({{
  symbol:"AAPL", name:"Apple Inc.", market:"US", exchange:"NASDAQ",
  industry_name:"Technology", is_etf:false, price:null, change:null,
  change_percent:null, quote_status:"NOT_CONNECTED", session_date:"2026-07-28",
  short_volume:400, short_exempt_volume:5, reported_total_volume:1000,
  short_volume_ratio:40, short_volume_status:"EOD"
}}, {{}}, null);
screenerLoadBreadth({{
  mode:"EOD_FULL+LIVE_PAGE",
  coverage:{{catalog_total:2, quoted_total:1}},
  market_catalog:[
    {{symbol:"2330", name:"台積電", market:"TWSE", industry_name:"半導體業"}},
    {{symbol:"6488", name:"環球晶", market:"TPEx", industry_name:"半導體業"}}
  ],
  full_market:[
    {{symbol:"2330", price:2200, change_percent:-3.5, quote_status:"EOD"}},
    {{symbol:"6488", price:null, quote_status:"MISSING", disposition:true}}
  ]
}});
var sorted = screenerSortRows([
  {{symbol:"ZZZ", changePercent:null, volume:null}},
  {{symbol:"AAA", changePercent:2, volume:1}},
  {{symbol:"BBB", changePercent:-1, volume:2}}
], "change_desc");
var shortSorted = screenerSortRows([
  {{symbol:"MSFT", shortVolumeRatio:null}},
  {{symbol:"AAPL", shortVolumeRatio:40}},
  {{symbol:"NVDA", shortVolumeRatio:55}}
], "short_ratio_desc");
var holidayFlowAuthoritative = sourceStatusAuthoritative({{
  status:"EOD", transport_status:"STALE", authoritative:true,
  coverage_status:"COMPLETE", upstreams:[
    {{status:"EOD", transport_status:"STALE", latest_event_at:"2026-02-11"}}
  ]
}}, ["EOD", "FRESH", "LIVE"]);
process.stdout.write(JSON.stringify({{
  symbol: row.symbol,
  market: row.market,
  industry: row.industry,
  tags: row.tags,
  return5d: row.return5d,
  return20d: row.return20d,
  disposition: row.disposition,
  eps: row.eps,
  peRatio: row.peRatio,
  pbRatio: row.pbRatio,
  dividendYield: row.dividendYield,
  revenueYoy: row.revenueYoy,
  revenueMom: row.revenueMom,
  institutionalStatus: row.institutionalStatus,
  valuationDate: row.valuationDate,
  sourceEventTime: row.sourceEventTime,
  disposedTags: disposed.tags,
  disposedType: disposed.disposition.type,
  usTags: usRow.tags,
  usReason: usRow.reasonAll,
  usPrice: usRow.price,
  usShortRatio: usRow.shortVolumeRatio,
  usQuoteStatus: usRow.status,
  breadthCount: screenerBreadthRows.length,
  breadthMode: screenerBreadthMode,
  breadthCoverage: screenerBreadthCoverage,
  breadthSecondStatus: screenerBreadthRows[1].status,
  breadthSecondDisposition: screenerBreadthRows[1].tags.indexOf("disposition") !== -1,
  holidayFlowAuthoritative: holidayFlowAuthoritative,
  order: sorted.map(function (item) {{ return item.symbol; }}),
  shortOrder: shortSorted.map(function (item) {{ return item.symbol; }})
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    assert result["symbol"] == "2330"
    assert result["market"] == "TWSE"
    assert result["industry"] == "半導體"
    assert "bear" in result["tags"]
    assert "industry" in result["tags"]
    assert "disposition" in result["tags"]
    assert result["disposition"]["type"] == "notice"
    assert result["disposition"]["reason"] == "注意股票"
    assert result["return5d"] is None
    assert result["return20d"] is None
    assert result["eps"] == 12.34
    assert result["peRatio"] == 18.2
    assert result["pbRatio"] == 7.1
    assert result["dividendYield"] == 1.5
    assert result["revenueYoy"] == 22.8
    assert result["revenueMom"] == 3.2
    assert result["institutionalStatus"] == "EOD"
    assert result["valuationDate"] == "2026-07-29"
    assert result["sourceEventTime"] == "2026-07-29"
    assert "disposition" in result["disposedTags"]
    assert result["disposedType"] == "disposition"
    assert "us" in result["usTags"]
    assert "bull" not in result["usTags"]
    assert "bear" not in result["usTags"]
    assert result["usReason"] == "FINRA 場外短售成交比 40%"
    assert result["usPrice"] is None
    assert result["usShortRatio"] == 40
    assert result["usQuoteStatus"] == "NOT_CONNECTED"
    assert result["breadthCount"] == 2
    assert result["breadthMode"] == "EOD_FULL+LIVE_PAGE"
    assert result["breadthCoverage"] == {"catalog_total": 2, "quoted_total": 1}
    assert result["breadthSecondStatus"] == "MISSING"
    assert result["breadthSecondDisposition"] is True
    assert result["holidayFlowAuthoritative"] is True
    assert result["order"] == ["AAA", "BBB", "ZZZ"]
    assert result["shortOrder"] == ["NVDA", "AAPL", "MSFT"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_breadth_refreshes_on_ttl_and_taipei_session_rollover_without_loading_overlap() -> None:
    start = SCRIPT.index("function marketBreadthTaipeiSessionKey")
    end = SCRIPT.index("function scheduleMarketBreadthRetry")
    block = SCRIPT[start:end]
    load_start = SCRIPT.index("function loadMarketBreadth")
    load_prefix = SCRIPT[load_start : SCRIPT.index('    marketBreadthState = "loading";', load_start)]
    harness = f"""
var marketBreadthState = "ready";
var marketBreadthLastLoadedAt = Date.parse("2026-07-29T00:59:00Z");
var marketBreadthLoadedSessionKey = "";
var marketBreadthTtlMs = 300000;
var marketBreadthRefreshTimer = null;
var document = {{hidden:false}};
var window = {{
  clearTimeout:function () {{}},
  setTimeout:function () {{ return 1; }}
}};
{block}
marketBreadthLoadedSessionKey = marketBreadthTaipeiSessionKey(
  marketBreadthLastLoadedAt
);
var fresh = marketBreadthNeedsRefresh(
  false, Date.parse("2026-07-29T00:59:30Z")
);
var forced = marketBreadthNeedsRefresh(
  true, Date.parse("2026-07-29T00:59:30Z")
);
var phaseChanged = marketBreadthNeedsRefresh(
  false, Date.parse("2026-07-29T01:00:00Z")
);
marketBreadthTtlMs = 1000;
var expired = marketBreadthNeedsRefresh(
  false, Date.parse("2026-07-29T00:59:02Z")
);
process.stdout.write(JSON.stringify({{
  fresh:fresh,
  forced:forced,
  phaseChanged:phaseChanged,
  expired:expired
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result == {
        "fresh": False,
        "forced": True,
        "phaseChanged": True,
        "expired": True,
    }
    assert 'marketBreadthState === "loading"' in load_prefix
    assert "marketBreadthNeedsRefresh(Boolean(force), Date.now())" in load_prefix


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_live_quote_flip_updates_the_breadth_backing_row_and_can_restore_eod_baseline() -> None:
    baseline_start = SCRIPT.index("function screenerRememberBreadthBaseline")
    baseline_end = SCRIPT.index("function screenerLoadBreadth")
    apply_start = SCRIPT.index("function screenerApplyLiveQuote")
    apply_end = SCRIPT.index("function liveSyncBreadthRows")
    block = SCRIPT[baseline_start:baseline_end] + SCRIPT[apply_start:apply_end]
    harness = f"""
function screenerFinite(value) {{
  if (value === null || value === undefined || value === "") return null;
  var number = Number(value);
  return isFinite(number) ? number : null;
}}
function screenerFirstValue(row, keys, fallback) {{
  for (var i = 0; i < keys.length; i++) {{
    var value = row ? row[keys[i]] : null;
    if (value !== null && value !== undefined && value !== "") return value;
  }}
  return fallback;
}}
function livePercent(value) {{
  var number = Number(value);
  return (number > 0 ? "+" : "") + number.toFixed(2) + "%";
}}
{block}
var row = screenerRememberBreadthBaseline({{
  symbol:"2330", industry:"半導體業", price:100, referencePrice:99,
  change:1, changePercent:1.01, volume:10, tradeValue:1000,
  status:"EOD", sourceEventTime:"2026-07-29",
  disposition:{{type:"notice", reason:"注意股票"}},
  tags:["industry", "bull", "disposition"],
  reasonAll:"當日上漲 +1.01%｜注意：注意股票"
}});
screenerApplyLiveQuote(row, {{
  symbol:"2330", status:"LIVE", price:98, reference_price:99,
  change:-1, change_percent:-1.01, volume:20, event_time:"2026-07-30T10:00:00+08:00"
}}, []);
var live = {{
  price:row.price,
  changePercent:row.changePercent,
  tags:row.tags.slice(),
  reasonAll:row.reasonAll,
  status:row.status
}};
screenerApplyLiveQuote(row, null, []);
var restored = {{
  price:row.price,
  changePercent:row.changePercent,
  tags:row.tags.slice(),
  reasonAll:row.reasonAll,
  status:row.status
}};
process.stdout.write(JSON.stringify({{live:live, restored:restored}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["live"]["price"] == 98
    assert result["live"]["changePercent"] == -1.01
    assert result["live"]["tags"] == ["industry", "disposition", "bear"]
    assert result["live"]["reasonAll"] == "當日下跌 -1.01%｜注意：注意股票"
    assert result["live"]["status"] == "LIVE"
    assert result["restored"]["price"] == 100
    assert result["restored"]["changePercent"] == 1.01
    assert result["restored"]["tags"] == ["industry", "bull", "disposition"]
    assert result["restored"]["reasonAll"] == "當日上漲 +1.01%｜注意：注意股票"
    assert result["restored"]["status"] == "EOD"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_live_news_pagination_reaches_all_96_rows_in_bounded_batches() -> None:
    start = SCRIPT.index("function liveNewsNextVisibleCount")
    end = SCRIPT.index("function liveNewsRowsSignature")
    block = SCRIPT[start:end]
    harness = f"""
{block}
var visible = 12;
var steps = [visible];
while (visible < 96) {{
  visible = liveNewsNextVisibleCount(96, visible, 12);
  steps.push(visible);
}}
process.stdout.write(JSON.stringify({{
  steps:steps,
  capped:liveNewsNextVisibleCount(96, 96, 12)
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["steps"] == [12, 24, 36, 48, 60, 72, 84, 96]
    assert result["capped"] == 96


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_us_market_contract_rejects_prices_duplicates_and_count_drift() -> None:
    start = SCRIPT.index("function usMarketContractError")
    end = SCRIPT.index("function setScreenerActiveFilter")
    block = SCRIPT[start:end]
    valid = {
        "ok": True,
        "status": "EOD_REFERENCE",
        "session_date": "2026-07-28",
        "row_count": 2,
        "short_volume_source_row_count": 1,
        "short_volume_joined_row_count": 1,
        "short_volume_unmatched_row_count": 0,
        "short_volume_joined_security_count": 1,
        "price_provider_configured": False,
        "rows": [
            {
                "symbol": "AAPL",
                "market": "US",
                "price": None,
                "change": None,
                "change_percent": None,
                "quote_status": "NOT_CONNECTED",
            },
            {
                "symbol": "MSFT",
                "market": "US",
                "price": None,
                "change": None,
                "change_percent": None,
                "quote_status": "NOT_CONNECTED",
            },
        ],
        "source_status": {
            "directory": {"status": "FRESH"},
            "short_volume": {"status": "EOD"},
            "prices": {"status": "NOT_CONNECTED"},
        },
    }
    harness = f"""
{block}
var valid = {json.dumps(valid)};
var priced = JSON.parse(JSON.stringify(valid));
priced.rows[0].price = 200;
var duplicate = JSON.parse(JSON.stringify(valid));
duplicate.rows[1].symbol = "AAPL";
var drift = JSON.parse(JSON.stringify(valid));
drift.row_count = 3;
var shortDrift = JSON.parse(JSON.stringify(valid));
shortDrift.short_volume_unmatched_row_count = 1;
process.stdout.write(JSON.stringify({{
  valid:usMarketContractError(valid),
  priced:usMarketContractError(priced),
  duplicate:usMarketContractError(duplicate),
  drift:usMarketContractError(drift),
  shortDrift:usMarketContractError(shortDrift)
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["valid"] == ""
    assert result["priced"]
    assert result["duplicate"]
    assert result["drift"]
    assert result["shortDrift"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_live_symbols_never_send_us_directory_symbols_to_taiwan_snapshot() -> None:
    start = SCRIPT.index("function liveSymbols")
    end = SCRIPT.index("function liveQuoteMap")
    block = SCRIPT[start:end]
    harness = f"""
function fakeRow(symbol, market, hidden) {{
  return {{
    hidden:Boolean(hidden),
    getAttribute:function (name) {{
      if (name === "data-stock-key") return symbol;
      if (name === "data-live-market") return market;
      return "";
    }}
  }};
}}
var usRows = [
  fakeRow("AAPL", "US"), fakeRow("MSFT", "US"), fakeRow("NVDA", "US")
];
var fixedRows = [
  fakeRow("2330", "TWSE"), fakeRow("2317", "TWSE"),
  fakeRow("6488", "TPEx", true)
];
var document = {{
  querySelectorAll:function (selector) {{
    return selector === '[data-live-breadth-row="true"]' ? usRows : fixedRows;
  }}
}};
var liveSymbolLimit = 20;
{block}
process.stdout.write(JSON.stringify(liveSymbols()));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(completed.stdout) == ["2330", "2317"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_us_pill_market_select_and_taiwan_switch_are_wired_without_live_refresh() -> None:
    start = SCRIPT.index("function initScreener")
    end = SCRIPT.index("function storageGet")
    block = SCRIPT[start:end]
    harness = f"""
function fakeElement(attributes) {{
  return {{
    attributes:attributes || {{}},
    value:(attributes || {{}}).value || "",
    disabled:false,
    listeners:{{}},
    classList:{{
      toggle:function () {{}},
      contains:function () {{ return false; }}
    }},
    getAttribute:function (name) {{ return this.attributes[name] || null; }},
    setAttribute:function (name, value) {{ this.attributes[name] = value; }},
    addEventListener:function (name, callback) {{ this.listeners[name] = callback; }},
    trigger:function (name) {{
      this.listeners[name]({{currentTarget:this}});
    }}
  }};
}}
var filters = ["all", "bull", "bear", "disposition", "industry", "us"].map(
  function (key) {{ return fakeElement({{"data-screener-filter":key}}); }}
);
var market = fakeElement({{"data-screener-market":"true", value:"all"}});
var input = fakeElement({{"data-screener-search":"true"}});
var calls = {{us:0, taiwan:[], apply:0, live:0, init:0}};
var document = {{
  querySelectorAll:function (selector) {{
    if (selector === "[data-screener-filter]") return filters;
    if (selector.indexOf('[data-screener-market="true"]') !== -1) return [market];
    if (selector === "[data-screener-page]") return [];
    return [];
  }},
  querySelector:function (selector) {{
    if (selector === '[data-screener-search="true"]') return input;
    if (selector === '[data-screener-market="true"]') return market;
    return null;
  }}
}};
var screenerUniverseMode = "TW";
var screenerDesiredUniverseMode = "TW";
var screenerBreadthPage = 1;
var screenerBreadthPageSize = 50;
function initUsMarketControls() {{ calls.init += 1; }}
function usMarketApiEnabled() {{ return true; }}
function setScreenerActiveFilter() {{}}
function loadUsMarket() {{ calls.us += 1; }}
function activateTaiwanScreener(value) {{
  calls.taiwan.push(value);
  screenerUniverseMode = "TW";
}}
function applyScreenerFilters() {{ calls.apply += 1; }}
function scheduleVisibleLiveRefresh() {{ calls.live += 1; }}
function renderBreadthScreener() {{}}
{block}
initScreener();
filters[5].trigger("click");
var afterPill = {{us:calls.us, market:market.value}};
screenerUniverseMode = "US";
market.value = "TWSE";
market.trigger("change");
var afterTwse = {{taiwan:calls.taiwan.slice(), live:calls.live}};
market.value = "US";
market.trigger("change");
process.stdout.write(JSON.stringify({{
  init:calls.init,
  afterPill:afterPill,
  afterTwse:afterTwse,
  usCalls:calls.us
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["init"] == 1
    assert result["afterPill"] == {"us": 1, "market": "US"}
    assert result["afterTwse"]["taiwan"] == ["TWSE"]
    assert result["afterTwse"]["live"] == 0
    assert result["usCalls"] == 2


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_loopback_enables_us_pill_and_market_option_but_keeps_short_sort_scoped() -> None:
    start = SCRIPT.index("function initUsMarketControls")
    end = SCRIPT.index("function sourceStatusAuthoritative")
    block = SCRIPT[start:end]
    harness = f"""
var usOption = {{disabled:true}};
var market = {{
  querySelector:function () {{ return usOption; }}
}};
var button = {{
  disabled:true,
  title:"",
  attrs:{{}},
  setAttribute:function (name, value) {{ this.attrs[name] = value; }}
}};
var body = {{getAttribute:function () {{ return "true"; }}}};
var document = {{
  body:body,
  querySelector:function (selector) {{
    if (selector === '[data-screener-market="true"]') return market;
    if (selector === '[data-screener-filter="us"]') return button;
    return null;
  }}
}};
var sortUpdates = 0;
function usMarketApiEnabled() {{
  return document.body.getAttribute("data-us-market-api-enabled") === "true";
}}
function updateScreenerUniverseSortControl() {{ sortUpdates += 1; }}
function updateScreenerIndustrySemantics() {{}}
{block}
initUsMarketControls();
process.stdout.write(JSON.stringify({{
  optionDisabled:usOption.disabled,
  buttonDisabled:button.disabled,
  ariaDisabled:button.attrs["aria-disabled"],
  title:button.title,
  sortUpdates:sortUpdates
}}));
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["optionDisabled"] is False
    assert result["buttonDisabled"] is False
    assert result["ariaDisabled"] == "false"
    assert "首次點擊載入" in result["title"]
    assert result["sortUpdates"] == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_background_taiwan_breadth_does_not_overwrite_active_us_scope() -> None:
    start = SCRIPT.index("function loadMarketBreadth")
    end = SCRIPT.index("function liveSymbols")
    block = SCRIPT[start:end]
    harness = f"""
var AbortController = undefined;
var scope = {{
  textContent:"US_SCOPE",
  title:"",
  setAttribute:function (name, value) {{ this[name] = value; }}
}};
var industryScope = {{
  textContent:"INDUSTRY",
  title:"",
  setAttribute:function (name, value) {{ this[name] = value; }}
}};
var document = {{
  hidden:false,
  querySelector:function (selector) {{
    return selector === '[data-screener-scope-status="true"]'
      ? scope : industryScope;
  }}
}};
var screenerUniverseMode = "US";
var marketBreadthState = "idle";
var marketBreadthRefreshTimer = null;
var marketBreadthRetryTimer = null;
var marketBreadthFailures = 0;
var marketBreadthIndustryRows = [];
var liveBreadthRefreshPending = false;
var liveRequestInFlight = true;
function marketBreadthNeedsRefresh() {{ return true; }}
function marketBreadthContractError() {{ return ""; }}
function screenerLoadBreadth() {{ return true; }}
function scheduleMarketBreadthRefresh() {{}}
function scheduleMarketBreadthRetry() {{}}
function liveRenderIndustrySummaries() {{}}
function populateScreenerIndustriesFromSummaries() {{}}
function liveFetchSnapshot() {{}}
var window = {{
  fetch:function () {{
    return Promise.resolve({{
      ok:true,
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
{block}
(async function () {{
  loadMarketBreadth(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  var successScope = scope.textContent;
  marketBreadthState = "idle";
  window.fetch = function () {{ return Promise.reject(new Error("TW outage")); }};
  loadMarketBreadth(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify({{
    successScope:successScope,
    failureScope:scope.textContent
  }}));
}})();
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result == {"successScope": "US_SCOPE", "failureScope": "US_SCOPE"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_us_fetch_success_and_failure_keep_taiwan_backing_rows_isolated() -> None:
    contract_start = SCRIPT.index("function usMarketContractError")
    contract_end = SCRIPT.index("function setScreenerActiveFilter")
    load_start = SCRIPT.index("function loadUsMarket")
    load_end = SCRIPT.index("function initUsMarketControls")
    block = SCRIPT[contract_start:contract_end] + SCRIPT[load_start:load_end]
    payload = {
        "ok": True,
        "status": "EOD_REFERENCE",
        "session_date": "2026-07-28",
        "row_count": 2,
        "short_volume_source_row_count": 1,
        "short_volume_joined_row_count": 1,
        "short_volume_unmatched_row_count": 0,
        "short_volume_joined_security_count": 1,
        "price_provider_configured": False,
        "rows": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "market": "US",
                "price": None,
                "change": None,
                "change_percent": None,
                "quote_status": "NOT_CONNECTED",
                "short_volume_ratio": 40,
            },
            {
                "symbol": "MSFT",
                "name": "Microsoft Corp.",
                "market": "US",
                "price": None,
                "change": None,
                "change_percent": None,
                "quote_status": "NOT_CONNECTED",
                "short_volume_ratio": None,
            },
        ],
        "source_status": {
            "directory": {"status": "FRESH"},
            "short_volume": {"status": "EOD"},
            "prices": {"status": "NOT_CONNECTED"},
        },
    }
    harness = f"""
var AbortController = undefined;
var scope = {{textContent:"", title:"", setAttribute:function (name, value) {{
  this[name] = value;
}}}};
var document = {{
  body:{{getAttribute:function () {{ return "true"; }}}},
  querySelector:function () {{ return scope; }}
}};
var calls = {{us:0, taiwan:0, filter:""}};
var screenerTaiwanBreadthRows = [{{symbol:"2330"}}, {{symbol:"2317"}}];
var screenerUsBreadthRows = [];
var screenerUsBreadthMeta = null;
var screenerDesiredUniverseMode = "TW";
var usMarketState = "idle";
function usMarketApiEnabled() {{ return true; }}
function screenerNormalizeRow(row) {{
  return {{
    symbol:row.symbol,
    market:row.market,
    shortVolumeRatio:row.short_volume_ratio,
    tags:["us"]
  }};
}}
function screenerRememberBreadthBaseline(row) {{ return row; }}
function activateUsScreener() {{ calls.us += 1; }}
function activateTaiwanScreener() {{ calls.taiwan += 1; }}
function setScreenerActiveFilter(key) {{ calls.filter = key; }}
var window = {{
  fetch:function () {{
    return Promise.resolve({{
      ok:true,
      json:function () {{
        return Promise.resolve({json.dumps(payload)});
      }}
    }});
  }},
  setTimeout:function () {{ return 1; }},
  clearTimeout:function () {{}}
}};
{block}
(async function () {{
  loadUsMarket(false);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  var success = {{
    state:usMarketState,
    usRows:screenerUsBreadthRows.map(function (row) {{ return row.symbol; }}),
    taiwanRows:screenerTaiwanBreadthRows.map(function (row) {{ return row.symbol; }}),
    coverage:screenerUsBreadthMeta.coverage,
    activated:calls.us
  }};
  usMarketState = "idle";
  var deferredResolve = null;
  window.fetch = function () {{
    return new Promise(function (resolve) {{ deferredResolve = resolve; }});
  }};
  loadUsMarket(false);
  screenerDesiredUniverseMode = "TW";
  deferredResolve({{
    ok:true,
    json:function () {{ return Promise.resolve({json.dumps(payload)}); }}
  }});
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  var intentRace = {{
    state:usMarketState,
    desired:screenerDesiredUniverseMode,
    activated:calls.us
  }};
  usMarketState = "idle";
  window.fetch = function () {{ return Promise.reject(new Error("fixture outage")); }};
  loadUsMarket(true);
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  process.stdout.write(JSON.stringify({{
    success:success,
    intentRace:intentRace,
    failure:{{
      state:usMarketState,
      taiwanRows:screenerTaiwanBreadthRows.map(function (row) {{ return row.symbol; }}),
      restored:calls.taiwan,
      filter:calls.filter,
      message:scope.textContent
    }}
  }}));
}})();
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=harness,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["success"]["state"] == "ready"
    assert result["success"]["usRows"] == ["AAPL", "MSFT"]
    assert result["success"]["taiwanRows"] == ["2330", "2317"]
    assert result["success"]["coverage"] == {
        "catalog_total": 2,
        "quoted_total": 0,
        "short_volume_source_row_count": 1,
        "short_volume_joined_row_count": 1,
        "short_volume_unmatched_row_count": 0,
        "short_volume_joined_security_count": 1,
    }
    assert result["success"]["activated"] == 1
    assert result["intentRace"] == {
        "state": "ready",
        "desired": "TW",
        "activated": 1,
    }
    assert result["failure"]["state"] == "error"
    assert result["failure"]["taiwanRows"] == ["2330", "2317"]
    assert result["failure"]["restored"] == 1
    assert result["failure"]["filter"] == "all"
    assert result["failure"]["message"] == "美股資料不可用 · 台股資料未受影響"
