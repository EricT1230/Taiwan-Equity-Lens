
(function () {
  "use strict";

  var TAB_KEYS = ["overview", "market", "screener", "intelligence", "strategy", "workbench", "outputs"];
  var DEFAULT_TAB = "overview";
  var screenerBreadthRows = [];
  var screenerBreadthPage = 1;
  var screenerBreadthPageSize = 50;
  var screenerBreadthCoverage = {};
  var screenerBreadthMode = "UNAVAILABLE";
  var screenerBreadthStatus = "UNAVAILABLE";
  var screenerBreadthSessionDates = {};
  var screenerBreadthSourceStatus = {};
  var screenerTaiwanBreadthRows = [];
  var screenerTaiwanBreadthMeta = null;
  var screenerUsBreadthRows = [];
  var screenerUsBreadthMeta = null;
  var screenerUniverseMode = "TW";
  var screenerDesiredUniverseMode = "TW";
  var usMarketState = "idle";
  var marketBreadthState = "idle";
  var marketBreadthRetryTimer = null;
  var marketBreadthRefreshTimer = null;
  var marketBreadthFailures = 0;
  var marketBreadthLastLoadedAt = 0;
  var marketBreadthLoadedSessionKey = "";
  var marketBreadthIndustryRows = [];
  var liveBreadthRefreshPending = false;
  var liveVisibleRefreshTimer = null;
  var liveLastRequestAt = 0;
  var liveIntelligenceNewsRows = [];
  var liveIntelligenceNewsVisible = 12;
  var liveIntelligenceNewsSignature = "";

  function activateTab(name) {
    if (TAB_KEYS.indexOf(name) === -1) { name = DEFAULT_TAB; }
    var tabs = document.querySelectorAll(".ui-tab");
    var activeLabel = "今日總覽";
    for (var i = 0; i < tabs.length; i++) {
      var isActive = tabs[i].getAttribute("data-tab") === name;
      tabs[i].classList.toggle("active", isActive);
      tabs[i].setAttribute("aria-current", isActive ? "page" : "false");
      if (isActive) { activeLabel = tabs[i].getAttribute("data-tab-label") || activeLabel; }
    }
    var panels = document.querySelectorAll(".ui-panel");
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.toggle("active", panels[j].id === name);
    }
    var title = document.querySelector('[data-page-title="true"]');
    if (title) { title.textContent = activeLabel; }
  }

  function setTabHash(name) {
    if (window.history && typeof window.history.replaceState === "function") {
      window.history.replaceState(null, "", "#" + name);
    } else {
      location.hash = name;
    }
  }

  function focusActivePanel(name) {
    var panel = document.getElementById(name);
    if (!panel) { return; }
    var target = panel.querySelector("h1, h2") || panel;
    target.setAttribute("tabindex", "-1");
    try {
      target.focus({ preventScroll: true });
    } catch (err) {
      target.focus();
    }
  }

  function initTabs() {
    var tabs = document.querySelectorAll(".ui-tab");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener("click", function (event) {
        var name = event.currentTarget.getAttribute("data-tab");
        activateTab(name);
        setTabHash(name);
        window.scrollTo(0, 0);
      });
    }
    var initial = (location.hash || "").replace("#", "");
    // Final polish C5: the gate card's "處理建議下一步" link
    // (views/workbench.py's _gate_card) points at "#wb-row-0", a queue row
    // id inside the workbench panel -- not a top-level tab key. Without this,
    // activateTab()'s TAB_KEYS guard below falls through to "market" on
    // reload, leaving the target row stuck inside a display:none panel.
    if (initial.indexOf("wb-row-") === 0) { initial = "workbench"; }
    activateTab(initial || DEFAULT_TAB);
  }

  function initTabJumps() {
    var jumps = document.querySelectorAll("[data-jump-tab]");
    for (var i = 0; i < jumps.length; i++) {
      jumps[i].addEventListener("click", function (event) {
        var name = event.currentTarget.getAttribute("data-jump-tab") || DEFAULT_TAB;
        activateTab(name);
        setTabHash(name);
        window.scrollTo(0, 0);
        focusActivePanel(name);
      });
    }
  }

  function initGlobalSearch() {
    var input = document.querySelector('[data-global-search="true"]');
    var screenInput = document.querySelector('[data-screener-search="true"]');
    if (!input) { return; }
    input.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") { return; }
      if (screenInput) {
        screenInput.value = input.value;
        screenInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
      activateTab("screener");
      setTabHash("screener");
      window.scrollTo(0, 0);
      focusActivePanel("screener");
    });
    document.addEventListener("keydown", function (event) {
      var target = event.target;
      var editing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT");
      if (!editing && event.key === "/") {
        event.preventDefault();
        input.focus();
      }
    });
  }

  function screenerState() {
    var active = document.querySelector(".screen-filter.active");
    var input = document.querySelector('[data-screener-search="true"]');
    var market = document.querySelector('[data-screener-market="true"]');
    var industry = document.querySelector('[data-screener-industry="true"]');
    var sort = document.querySelector('[data-screener-sort="true"]');
    return {
      filter: active ? active.getAttribute("data-screener-filter") : "all",
      query: input ? (input.value || "").trim().toLowerCase() : "",
      market: market ? market.value : "all",
      industry: industry ? industry.value : "all",
      sort: sort ? sort.value : "change_desc"
    };
  }

  function screenerMetaSnapshot() {
    return {
      coverage: screenerBreadthCoverage,
      mode: screenerBreadthMode,
      status: screenerBreadthStatus,
      sessionDates: screenerBreadthSessionDates,
      sourceStatus: screenerBreadthSourceStatus
    };
  }

  function screenerApplyMeta(meta) {
    meta = meta || {};
    screenerBreadthCoverage = meta.coverage || {};
    screenerBreadthMode = String(meta.mode || "UNAVAILABLE").toUpperCase();
    screenerBreadthStatus = String(meta.status || "UNAVAILABLE").toUpperCase();
    screenerBreadthSessionDates = meta.sessionDates || {};
    screenerBreadthSourceStatus = meta.sourceStatus || {};
  }

  function usMarketApiEnabled() {
    return document.body.getAttribute("data-us-market-api-enabled") === "true";
  }

  function screenerPayloadRows(value) {
    if (Array.isArray(value)) { return value; }
    if (!value || typeof value !== "object") { return []; }
    if (Array.isArray(value.items)) { return value.items; }
    if (Array.isArray(value.rows)) { return value.rows; }
    return [];
  }

  function screenerFirstValue(row, keys, fallback) {
    for (var i = 0; i < keys.length; i++) {
      var value = row ? row[keys[i]] : null;
      if (value !== null && value !== undefined && value !== "") { return value; }
    }
    return fallback;
  }

  function screenerFinite(value) {
    if (value === null || value === undefined || value === "") { return null; }
    var number = Number(value);
    return isFinite(number) ? number : null;
  }

  function screenerMarketCode(value) {
    var normalized = String(value || "").trim().toUpperCase();
    if (normalized === "TPEX" || normalized === "OTC") { return "TPEx"; }
    if (normalized === "TWSE" || normalized === "TSE") { return "TWSE"; }
    if (normalized === "ESB" || normalized === "EMERGING") { return "ESB"; }
    if (normalized === "US" || normalized === "NYSE" || normalized === "NASDAQ" ||
        normalized === "AMEX") { return "US"; }
    return normalized || "未分類";
  }

  function screenerTagList(raw, market, industry, changePercent, disposition) {
    var values = [];
    var supplied = screenerFirstValue(raw, ["tags", "signals", "categories"], []);
    if (typeof supplied === "string") { supplied = supplied.split(/[\s,|]+/); }
    if (Array.isArray(supplied)) {
      for (var i = 0; i < supplied.length; i++) {
        var tag = String(supplied[i] || "").trim().toLowerCase();
        if (["bull", "bear", "disposition", "industry", "us"].indexOf(tag) !== -1 &&
            values.indexOf(tag) === -1) {
          values.push(tag);
        }
      }
    }
    if (changePercent !== null && changePercent > 0 && values.indexOf("bull") === -1) {
      values.push("bull");
    }
    if (changePercent !== null && changePercent < 0 && values.indexOf("bear") === -1) {
      values.push("bear");
    }
    if (industry && industry !== "未分類" && values.indexOf("industry") === -1) {
      values.push("industry");
    }
    if (market === "US" && values.indexOf("us") === -1) { values.push("us"); }
    if (disposition && values.indexOf("disposition") === -1) { values.push("disposition"); }
    return values;
  }

  function screenerNormalizeRow(raw, catalog, alert) {
    var merged = {};
    var key;
    catalog = catalog && typeof catalog === "object" ? catalog : {};
    raw = raw && typeof raw === "object" ? raw : {};
    for (key in catalog) {
      if (Object.prototype.hasOwnProperty.call(catalog, key)) { merged[key] = catalog[key]; }
    }
    for (key in raw) {
      if (Object.prototype.hasOwnProperty.call(raw, key)) { merged[key] = raw[key]; }
    }
    var symbol = String(screenerFirstValue(
      merged, ["symbol", "stock_id", "code", "ticker"], ""
    )).trim().toUpperCase();
    if (!symbol) { return null; }
    var name = String(screenerFirstValue(
      merged, ["name", "company_name", "security_name", "short_name"], symbol
    )).trim();
    var market = screenerMarketCode(screenerFirstValue(
      merged, ["market", "exchange", "board"], ""
    ));
    var industry = String(screenerFirstValue(
      merged, ["industry_name", "industry", "category", "sector"], "未分類"
    )).trim() || "未分類";
    var price = screenerFinite(screenerFirstValue(
      merged, ["price", "close", "last_price", "last"], null
    ));
    var referencePrice = screenerFinite(screenerFirstValue(
      merged, ["reference_price", "previous_close", "prev_close"], null
    ));
    var change = screenerFinite(screenerFirstValue(
      merged, ["change", "price_change"], null
    ));
    var changePercent = screenerFinite(screenerFirstValue(
      merged, ["change_percent", "change_pct", "return_1d", "percent_change"], null
    ));
    if (changePercent === null && price !== null && referencePrice && referencePrice !== 0) {
      changePercent = (price - referencePrice) / referencePrice * 100;
    }
    if (change === null && price !== null && referencePrice !== null) {
      change = price - referencePrice;
    }
    var shortVolume = screenerFinite(screenerFirstValue(
      merged, ["short_volume"], null
    ));
    var shortExemptVolume = screenerFinite(screenerFirstValue(
      merged, ["short_exempt_volume"], null
    ));
    var reportedTotalVolume = screenerFinite(screenerFirstValue(
      merged, ["reported_total_volume", "finra_total_volume"], null
    ));
    var shortVolumeRatio = screenerFinite(screenerFirstValue(
      merged, ["short_volume_ratio"], null
    ));
    var dispositionValue = merged.disposition;
    var attentionValue = merged.attention;
    var dispositionFlag = dispositionValue === true || dispositionValue === 1 ||
      String(dispositionValue || "").toLowerCase() === "true";
    var attentionFlag = attentionValue === true || attentionValue === 1 ||
      String(attentionValue || "").toLowerCase() === "true";
    var alertTitles = Array.isArray(merged.alert_titles)
      ? merged.alert_titles.filter(function (title) { return String(title || "").trim(); })
      : [];
    var disposition = dispositionValue && typeof dispositionValue === "object"
      ? dispositionValue : null;
    if (!disposition && (dispositionFlag || attentionFlag)) {
      disposition = {
        type: dispositionFlag ? "disposition" : "notice",
        reason: alertTitles.slice(0, 2).join("｜") ||
          ((Number(merged.alert_count) || 1) + " 筆官方警示")
      };
    }
    if (!disposition && alert) { disposition = alert; }
    var tags = screenerTagList(merged, market, industry, changePercent, disposition);
    var reasonParts = [];
    if (changePercent !== null && changePercent !== 0) {
      reasonParts.push((changePercent > 0 ? "當日漲幅 " : "當日跌幅 ") + livePercent(changePercent));
    }
    if (market === "US") {
      reasonParts.push(
        shortVolumeRatio === null
          ? "FINRA 場外短售成交量尚無資料"
          : "FINRA 場外短售成交比 " + liveNumber(shortVolumeRatio, 2) + "%"
      );
    }
    if (disposition) {
      reasonParts.push(
        (String(disposition.type || "") === "disposition" ? "處置" : "注意") +
        "：" + String(disposition.reason || disposition.period || "官方名單命中")
      );
    }
    if (!reasonParts.length && industry !== "未分類") { reasonParts.push("產業：" + industry); }
    var status = String(screenerFirstValue(
      merged, ["status", "quote_status", "data_status"], price === null ? "CATALOG" : "AVAILABLE"
    )).toUpperCase();
    if (["LIVE", "EOD", "AVAILABLE"].indexOf(status) === -1) {
      tags = tags.filter(function (tag) {
        return tag !== "bull" && tag !== "bear";
      });
    }
    return {
      symbol: symbol,
      name: name || symbol,
      market: market,
      exchange: String(screenerFirstValue(merged, ["exchange"], "")),
      industry: industry,
      industryCode: String(screenerFirstValue(merged, ["industry_code", "sector_code"], "")),
      isEtf: Boolean(screenerFirstValue(merged, ["is_etf"], false)),
      price: price,
      referencePrice: referencePrice,
      change: change,
      changePercent: changePercent,
      return5d: screenerFinite(screenerFirstValue(merged, ["return_5d", "change_percent_5d"], null)),
      return20d: screenerFinite(screenerFirstValue(merged, ["return_20d", "change_percent_20d"], null)),
      volume: screenerFinite(screenerFirstValue(merged, ["volume", "trade_volume"], null)),
      tradeValue: screenerFinite(screenerFirstValue(merged, ["trade_value", "turnover"], null)),
      institutionalNet: screenerFinite(screenerFirstValue(
        merged, ["institutional_net", "total_net", "institutional_net_shares"], null
      )),
      institutionalStatus: String(screenerFirstValue(
        merged, ["institutional_status", "fund_flow_status"], ""
      )),
      peRatio: screenerFinite(screenerFirstValue(merged, ["pe_ratio", "pe"], null)),
      pbRatio: screenerFinite(screenerFirstValue(merged, ["pb_ratio", "pb"], null)),
      dividendYield: screenerFinite(screenerFirstValue(
        merged, ["dividend_yield", "yield_percent"], null
      )),
      valuationDate: String(screenerFirstValue(
        merged, ["valuation_date", "valuation_as_of", "valuationDate"], ""
      )),
      eps: screenerFinite(screenerFirstValue(merged, ["eps", "earnings_per_share"], null)),
      financialPeriod: String(screenerFirstValue(
        merged, ["financial_period", "period"], ""
      )),
      revenueYoy: screenerFinite(screenerFirstValue(
        merged, ["revenue_yoy_percent", "revenue_yoy"], null
      )),
      revenueMom: screenerFinite(screenerFirstValue(
        merged, ["revenue_mom_percent", "revenue_mom"], null
      )),
      shortVolume: shortVolume,
      shortExemptVolume: shortExemptVolume,
      reportedTotalVolume: reportedTotalVolume,
      shortVolumeRatio: shortVolumeRatio,
      shortVolumeStatus: String(screenerFirstValue(
        merged, ["short_volume_status"], ""
      )),
      score: screenerFinite(screenerFirstValue(merged, ["score", "research_score"], null)),
      status: status,
      sourceEventTime: String(screenerFirstValue(
        merged, ["source_event_time", "event_time", "as_of", "session_date"], ""
      )),
      disposition: disposition,
      tags: tags,
      reasonAll: reasonParts.join("｜") || "尚無可驗證的命中原因",
      searchText: [
        symbol,
        name,
        market,
        industry,
        String(screenerFirstValue(merged, ["exchange"], ""))
      ].join(" ").toLowerCase()
    };
  }

  function screenerRememberBreadthBaseline(row) {
    row.breadthBaseline = {
      price: row.price,
      referencePrice: row.referencePrice,
      change: row.change,
      changePercent: row.changePercent,
      volume: row.volume,
      tradeValue: row.tradeValue,
      status: row.status,
      sourceEventTime: row.sourceEventTime,
      disposition: row.disposition,
      tags: row.tags.slice(),
      reasonAll: row.reasonAll
    };
    return row;
  }

  function screenerRestoreBreadthBaseline(row) {
    var baseline = row && row.breadthBaseline;
    if (!baseline) { return row; }
    row.price = baseline.price;
    row.referencePrice = baseline.referencePrice;
    row.change = baseline.change;
    row.changePercent = baseline.changePercent;
    row.volume = baseline.volume;
    row.tradeValue = baseline.tradeValue;
    row.status = baseline.status;
    row.sourceEventTime = baseline.sourceEventTime;
    row.disposition = baseline.disposition;
    row.tags = baseline.tags.slice();
    row.reasonAll = baseline.reasonAll;
    return row;
  }

  function screenerLoadBreadth(snapshot) {
    if (!snapshot ||
        !Array.isArray(snapshot.market_catalog) ||
        !Array.isArray(snapshot.full_market)) {
      return false;
    }
    var catalogRows = snapshot.market_catalog;
    var marketRows = snapshot.full_market;
    if (!catalogRows.length || marketRows.length !== catalogRows.length) { return false; }
    screenerBreadthCoverage = snapshot.coverage &&
      typeof snapshot.coverage === "object" && !Array.isArray(snapshot.coverage)
      ? snapshot.coverage : {};
    screenerBreadthMode = String(snapshot.mode || "UNAVAILABLE").toUpperCase();
    screenerBreadthStatus = String(snapshot.status || "UNAVAILABLE").toUpperCase();
    var activeSessionDates = screenerBreadthStatus === "LIVE"
      ? snapshot.live_session_dates : snapshot.session_dates;
    screenerBreadthSessionDates = activeSessionDates &&
      typeof activeSessionDates === "object" && !Array.isArray(activeSessionDates)
      ? activeSessionDates : {};
    screenerBreadthSourceStatus = snapshot.source_status &&
      typeof snapshot.source_status === "object" && !Array.isArray(snapshot.source_status)
      ? snapshot.source_status : {};
    var catalogBySymbol = {};
    var order = [];
    for (var i = 0; i < catalogRows.length; i++) {
      var catalogSymbol = String(screenerFirstValue(
        catalogRows[i], ["symbol", "stock_id", "code", "ticker"], ""
      )).trim().toUpperCase();
      if (!catalogSymbol) { continue; }
      catalogBySymbol[catalogSymbol] = catalogRows[i];
      order.push(catalogSymbol);
    }
    var rawBySymbol = {};
    for (var j = 0; j < marketRows.length; j++) {
      var marketSymbol = String(screenerFirstValue(
        marketRows[j], ["symbol", "stock_id", "code", "ticker"], ""
      )).trim().toUpperCase();
      if (!marketSymbol) { continue; }
      rawBySymbol[marketSymbol] = marketRows[j];
      if (order.indexOf(marketSymbol) === -1) { order.push(marketSymbol); }
    }
    var alertRows = Array.isArray(snapshot.alerts) ? snapshot.alerts : [];
    var alertBySymbol = {};
    for (var alertIndex = 0; alertIndex < alertRows.length; alertIndex++) {
      var alertSymbol = String(alertRows[alertIndex].symbol || "").trim().toUpperCase();
      if (alertSymbol && !alertBySymbol[alertSymbol]) {
        alertBySymbol[alertSymbol] = alertRows[alertIndex];
      }
    }
    var normalized = [];
    for (var orderIndex = 0; orderIndex < order.length; orderIndex++) {
      var symbol = order[orderIndex];
      var row = screenerNormalizeRow(
        rawBySymbol[symbol] || {}, catalogBySymbol[symbol] || {}, alertBySymbol[symbol]
      );
      if (row && ["LIVE", "EOD"].indexOf(screenerBreadthStatus) === -1) {
        row.tags = row.tags.filter(function (tag) {
          return tag !== "bull" && tag !== "bear";
        });
      }
      if (row) { normalized.push(screenerRememberBreadthBaseline(row)); }
    }
    screenerTaiwanBreadthRows = normalized;
    screenerTaiwanBreadthMeta = screenerMetaSnapshot();
    if (screenerUniverseMode === "US") {
      screenerApplyMeta(screenerUsBreadthMeta);
      return true;
    }
    screenerBreadthRows = screenerTaiwanBreadthRows;
    var pageSize = document.querySelector('[data-screener-page-size="true"]');
    screenerBreadthPageSize = Math.max(1, Number(pageSize ? pageSize.value : 50) || 50);
    screenerBreadthPage = 1;
    populateScreenerIndustries();
    updateScreenerSourceControls();
    renderBreadthScreener();
    return true;
  }

  function usMarketContractError(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return "US market payload is not an object";
    }
    if (payload.ok !== true) { return "US market payload is unavailable"; }
    if (["EOD_REFERENCE", "DIRECTORY_ONLY", "STALE"].indexOf(
      String(payload.status || "").toUpperCase()
    ) === -1) {
      return "US market status is invalid";
    }
    if (payload.price_provider_configured !== false) {
      return "US price-provider boundary is invalid";
    }
    if (!Array.isArray(payload.rows) ||
        Number(payload.row_count) !== payload.rows.length ||
        !payload.rows.length) {
      return "US market directory is incomplete";
    }
    if (!payload.source_status ||
        typeof payload.source_status !== "object" ||
        Array.isArray(payload.source_status)) {
      return "US market source status is missing";
    }
    var sourceShortRows = Number(payload.short_volume_source_row_count);
    var joinedShortRows = Number(payload.short_volume_joined_row_count);
    var unmatchedShortRows = Number(payload.short_volume_unmatched_row_count);
    var joinedShortSecurities = Number(
      payload.short_volume_joined_security_count
    );
    if (!isFinite(sourceShortRows) || sourceShortRows < 0 ||
        !isFinite(joinedShortRows) || joinedShortRows < 0 ||
        !isFinite(unmatchedShortRows) || unmatchedShortRows < 0 ||
        !isFinite(joinedShortSecurities) || joinedShortSecurities < 0 ||
        joinedShortRows + unmatchedShortRows !== sourceShortRows ||
        joinedShortSecurities > joinedShortRows) {
      return "US short-volume coverage is invalid";
    }
    var symbols = {};
    for (var i = 0; i < payload.rows.length; i++) {
      var row = payload.rows[i];
      var symbol = row && typeof row === "object"
        ? String(row.symbol || "").trim().toUpperCase() : "";
      if (!symbol || symbols[symbol] || String(row.market || "").toUpperCase() !== "US") {
        return "US market symbols are invalid";
      }
      if (row.price !== null || row.change !== null || row.change_percent !== null ||
          String(row.quote_status || "") !== "NOT_CONNECTED") {
        return "US market price boundary is invalid";
      }
      symbols[symbol] = true;
    }
    return "";
  }

  function setScreenerActiveFilter(key) {
    var filters = document.querySelectorAll("[data-screener-filter]");
    for (var i = 0; i < filters.length; i++) {
      var active = filters[i].getAttribute("data-screener-filter") === key;
      filters[i].classList.toggle("active", active);
      filters[i].setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function updateScreenerUniverseSortControl() {
    var sort = document.querySelector('[data-screener-sort="true"]');
    var usOption = sort
      ? sort.querySelector('option[value="short_ratio_desc"]') : null;
    var usActive = screenerUniverseMode === "US";
    if (usOption) { usOption.disabled = !usActive; }
    if (sort && !usActive && sort.value === "short_ratio_desc") {
      sort.value = "change_desc";
    }
  }

  function updateScreenerIndustrySemantics() {
    var usActive = screenerUniverseMode === "US";
    var label = document.querySelector('[data-screener-industry-label="true"]');
    var triggerLabel = document.querySelector(
      '[data-screener-industry-trigger-label="true"]'
    );
    if (label) {
      label.textContent = usActive ? "掛牌市場／分類" : "產業";
    }
    if (triggerLabel) {
      triggerLabel.textContent = usActive ? "選掛牌市場" : "選產業";
    }
  }

  function activateTaiwanScreener(marketValue) {
    screenerDesiredUniverseMode = "TW";
    screenerUniverseMode = "TW";
    screenerBreadthRows = screenerTaiwanBreadthRows;
    screenerApplyMeta(screenerTaiwanBreadthMeta);
    updateScreenerUniverseSortControl();
    updateScreenerIndustrySemantics();
    var market = document.querySelector('[data-screener-market="true"]');
    if (market) { market.value = marketValue || "all"; }
    screenerBreadthPage = 1;
    populateScreenerIndustries();
    updateScreenerSourceControls();
    if (screenerBreadthRows.length) {
      renderBreadthScreener();
    } else {
      var body = document.querySelector('[data-screener-body="true"]');
      if (body) { body.textContent = ""; }
    }
  }

  function activateUsScreener() {
    if (!screenerUsBreadthRows.length || !screenerUsBreadthMeta) { return; }
    screenerDesiredUniverseMode = "US";
    screenerUniverseMode = "US";
    if (liveVisibleRefreshTimer) {
      window.clearTimeout(liveVisibleRefreshTimer);
      liveVisibleRefreshTimer = null;
    }
    screenerBreadthRows = screenerUsBreadthRows;
    screenerApplyMeta(screenerUsBreadthMeta);
    updateScreenerUniverseSortControl();
    updateScreenerIndustrySemantics();
    var market = document.querySelector('[data-screener-market="true"]');
    if (market) { market.value = "US"; }
    setScreenerActiveFilter("us");
    screenerBreadthPage = 1;
    populateScreenerIndustries();
    updateScreenerSourceControls();
    renderBreadthScreener();
  }

  function loadUsMarket(force) {
    if (!usMarketApiEnabled() || !window.fetch) { return; }
    screenerDesiredUniverseMode = "US";
    if (usMarketState === "loading") { return; }
    if (!force && usMarketState === "ready" && screenerUsBreadthRows.length) {
      activateUsScreener();
      return;
    }
    usMarketState = "loading";
    var scope = document.querySelector('[data-screener-scope-status="true"]');
    if (scope) {
      scope.textContent = "載入美股官方名錄與 FINRA 場外短售成交量…";
    }
    var controller = typeof AbortController !== "undefined"
      ? new AbortController() : null;
    var timeout = controller
      ? window.setTimeout(function () { controller.abort(); }, 20000) : null;
    var options = { cache: "no-store", headers: { "Accept": "application/json" } };
    if (controller) { options.signal = controller.signal; }
    window.fetch("/api/us/market", options)
      .then(function (response) {
        if (!response.ok) { throw new Error("US market API HTTP " + response.status); }
        return response.json();
      })
      .then(function (payload) {
        var contractError = usMarketContractError(payload);
        if (contractError) { throw new Error(contractError); }
        var normalized = [];
        for (var i = 0; i < payload.rows.length; i++) {
          var row = screenerNormalizeRow(payload.rows[i], {}, null);
          if (row) { normalized.push(screenerRememberBreadthBaseline(row)); }
        }
        if (normalized.length !== payload.rows.length) {
          throw new Error("US market rows could not be normalized");
        }
        screenerUsBreadthRows = normalized;
        screenerUsBreadthMeta = {
          coverage: {
            catalog_total: normalized.length,
            quoted_total: 0,
            short_volume_source_row_count: (
              Number(payload.short_volume_source_row_count) || 0
            ),
            short_volume_joined_row_count: (
              Number(payload.short_volume_joined_row_count) || 0
            ),
            short_volume_unmatched_row_count: (
              Number(payload.short_volume_unmatched_row_count) || 0
            ),
            short_volume_joined_security_count: (
              Number(payload.short_volume_joined_security_count) || 0
            )
          },
          mode: "US_OFFICIAL_DIRECTORY",
          status: String(payload.status || "DIRECTORY_ONLY").toUpperCase(),
          sessionDates: {US: String(payload.session_date || "")},
          sourceStatus: payload.source_status
        };
        usMarketState = "ready";
        if (screenerDesiredUniverseMode === "US") {
          activateUsScreener();
        }
      })
      .catch(function (error) {
        usMarketState = "error";
        if (screenerDesiredUniverseMode === "US") {
          activateTaiwanScreener("all");
          setScreenerActiveFilter("all");
          var failedScope = document.querySelector(
            '[data-screener-scope-status="true"]'
          );
          if (failedScope) {
            failedScope.textContent = "美股資料不可用 · 台股資料未受影響";
            failedScope.setAttribute("title", String(error.message || error));
          }
        }
      })
      .then(function () {
        if (timeout) { window.clearTimeout(timeout); }
      });
  }

  function initUsMarketControls() {
    var enabled = usMarketApiEnabled();
    var market = document.querySelector('[data-screener-market="true"]');
    var option = market ? market.querySelector('option[value="US"]') : null;
    if (option) { option.disabled = !enabled; }
    var button = document.querySelector('[data-screener-filter="us"]');
    if (button) {
      button.disabled = !enabled;
      button.setAttribute("aria-disabled", enabled ? "false" : "true");
      button.title = enabled
        ? "首次點擊載入美股官方名錄與 FINRA 場外短售成交量"
        : "美股資料端點只在 loopback 服務模式開放";
    }
    updateScreenerUniverseSortControl();
    updateScreenerIndustrySemantics();
  }

  function sourceStatusAuthoritative(value, acceptedStatuses) {
    if (!value || typeof value !== "object" || Array.isArray(value)) { return false; }
    if (value.authoritative === false || value.partial === true) { return false; }
    var status = String(value.status || "UNAVAILABLE").toUpperCase();
    if (acceptedStatuses.indexOf(status) === -1) { return false; }
    var upstreams = Array.isArray(value.upstreams) ? value.upstreams : [];
    for (var upstreamIndex = 0; upstreamIndex < upstreams.length; upstreamIndex++) {
      var upstreamStatus = String(
        (upstreams[upstreamIndex] || {}).status || "UNAVAILABLE"
      ).toUpperCase();
      if (acceptedStatuses.indexOf(upstreamStatus) === -1) { return false; }
    }
    return value.authoritative === true || !Object.prototype.hasOwnProperty.call(
      value, "authoritative"
    );
  }

  function screenerBreadthSourceAuthoritative(key) {
    if (screenerBreadthStatus === "STALE") { return false; }
    return sourceStatusAuthoritative(
      screenerBreadthSourceStatus[key],
      ["EOD", "FRESH", "LIVE"]
    );
  }

  function updateScreenerSourceControls() {
    var dispositionButton = document.querySelector(
      '[data-screener-filter="disposition"]'
    );
    var dispositionCount = document.querySelector(
      '[data-screener-filter-count="disposition"]'
    );
    var alertsReady = screenerBreadthSourceAuthoritative("disposition_alerts");
    var noticesReady = screenerBreadthSourceAuthoritative("notice_alerts");
    if (dispositionButton) {
      dispositionButton.disabled = !alertsReady;
      dispositionButton.setAttribute("aria-disabled", alertsReady ? "false" : "true");
      if (!alertsReady) {
        dispositionButton.title = "官方處置來源不完整，篩選已停用";
        if (dispositionButton.classList.contains("active")) {
          dispositionButton.classList.remove("active");
          dispositionButton.setAttribute("aria-pressed", "false");
          var allButton = document.querySelector('[data-screener-filter="all"]');
          if (allButton) {
            allButton.classList.add("active");
            allButton.setAttribute("aria-pressed", "true");
          }
        }
      } else if (!noticesReady) {
        dispositionButton.title = "處置來源完整；注意股票來源不完整，目前僅篩選處置名單";
      } else {
        dispositionButton.title = "篩選官方處置／注意名單";
      }
    }
    if (dispositionCount && !alertsReady) { dispositionCount.textContent = "—"; }
    var trendReady = ["LIVE", "EOD"].indexOf(screenerBreadthStatus) !== -1;
    var trendKeys = ["bull", "bear"];
    for (var trendIndex = 0; trendIndex < trendKeys.length; trendIndex++) {
      var trendButton = document.querySelector(
        '[data-screener-filter="' + trendKeys[trendIndex] + '"]'
      );
      var trendCount = document.querySelector(
        '[data-screener-filter-count="' + trendKeys[trendIndex] + '"]'
      );
      if (trendButton) {
        trendButton.disabled = !trendReady;
        trendButton.setAttribute("aria-disabled", trendReady ? "false" : "true");
        if (!trendReady) {
          trendButton.title = screenerUniverseMode === "US"
            ? "美股價格來源未連接，不計算上漲／下跌"
            : "完整且同交易日的收盤資料不可用，漲跌篩選已停用";
          if (trendButton.classList.contains("active")) {
            trendButton.classList.remove("active");
            trendButton.setAttribute("aria-pressed", "false");
            var fallbackAll = document.querySelector('[data-screener-filter="all"]');
            if (fallbackAll) {
              fallbackAll.classList.add("active");
              fallbackAll.setAttribute("aria-pressed", "true");
            }
          }
        }
      }
      if (trendCount && !trendReady) { trendCount.textContent = "—"; }
    }
    var usEnabled = usMarketApiEnabled();
    var usReady = screenerUsBreadthRows.length > 0;
    var usButton = document.querySelector('[data-screener-filter="us"]');
    var usCount = document.querySelector('[data-screener-filter-count="us"]');
    if (usButton) {
      usButton.disabled = !usEnabled;
      usButton.setAttribute("aria-disabled", usEnabled ? "false" : "true");
      usButton.title = !usEnabled
        ? "美股資料端點只在 loopback 服務模式開放"
        : usReady
          ? "美股官方名錄與 FINRA 場外短售成交量；價格來源未連接"
          : "首次點擊載入美股官方名錄與 FINRA 場外短售成交量";
    }
    if (usCount) {
      usCount.textContent = !usEnabled
        ? "—"
        : usReady
          ? String(screenerUsBreadthRows.length)
          : usMarketState === "loading" ? "…" : "載入";
    }
  }

  function populateScreenerIndustries() {
    var select = document.querySelector('[data-screener-industry="true"]');
    if (!select) { return; }
    var previous = select.value || "all";
    var values = [];
    for (var i = 0; i < screenerBreadthRows.length; i++) {
      var industry = screenerBreadthRows[i].industry;
      if (industry && industry !== "未分類" && values.indexOf(industry) === -1) {
        values.push(industry);
      }
    }
    values.sort(function (left, right) { return left.localeCompare(right, "zh-TW"); });
    select.textContent = "";
    var allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = screenerUniverseMode === "US"
      ? "全部掛牌市場／分類" : "全部產業";
    select.appendChild(allOption);
    for (var j = 0; j < values.length; j++) {
      var option = document.createElement("option");
      option.value = values[j];
      option.textContent = values[j];
      select.appendChild(option);
    }
    select.disabled = values.length === 0;
    select.value = values.indexOf(previous) === -1 ? "all" : previous;
    var trigger = document.querySelector('[data-screener-filter="industry"]');
    if (trigger) {
      trigger.disabled = select.disabled;
      trigger.setAttribute("aria-disabled", select.disabled ? "true" : "false");
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.title = select.disabled
        ? (screenerUniverseMode === "US"
          ? "掛牌市場分類尚未載入" : "產業資料尚未載入")
        : (screenerUniverseMode === "US"
          ? "開啟掛牌市場／分類下拉選單（共 " + values.length + " 類）"
          : "開啟產業下拉選單（共 " + values.length + " 個產業）");
    }
    var count = document.querySelector('[data-screener-filter-count="industry"]');
    if (count) { count.textContent = values.length ? String(values.length) : "—"; }
  }

  function screenerCommonMatch(row, state) {
    var marketMatch = state.market === "all" ||
      String(row.market || "").toUpperCase() === String(state.market || "").toUpperCase();
    var industryMatch = state.industry === "all" || row.industry === state.industry;
    var queryMatch = !state.query || row.searchText.indexOf(state.query) !== -1;
    return marketMatch && industryMatch && queryMatch;
  }

  function screenerSortRows(rows, mode) {
    rows.sort(function (left, right) {
      if (mode === "symbol_asc") { return left.symbol.localeCompare(right.symbol); }
      var key = mode === "volume_desc"
        ? "volume"
        : mode === "short_ratio_desc" ? "shortVolumeRatio" : "changePercent";
      var leftValue = left[key];
      var rightValue = right[key];
      if (leftValue === null && rightValue === null) { return left.symbol.localeCompare(right.symbol); }
      if (leftValue === null) { return 1; }
      if (rightValue === null) { return -1; }
      if (mode === "change_asc") { return leftValue - rightValue || left.symbol.localeCompare(right.symbol); }
      return rightValue - leftValue || left.symbol.localeCompare(right.symbol);
    });
    return rows;
  }

  function screenerStatusLabel(status) {
    var normalized = String(status || "").toUpperCase();
    if (normalized === "LIVE") { return "即時"; }
    if (normalized === "EOD") { return "收盤"; }
    if (normalized === "CATALOG") { return "名錄"; }
    if (normalized === "AVAILABLE") { return "可用"; }
    if (normalized === "MISSING" || normalized === "NO_ROW") { return "無行情"; }
    if (normalized === "SUSPENDED") { return "停牌／無成交"; }
    if (normalized === "UNDATED") { return "日期無效"; }
    if (normalized === "FUTURE") { return "未來日期拒絕"; }
    if (normalized === "PARTIAL") { return "資料不完整"; }
    if (normalized === "STALE") { return "逾時"; }
    if (normalized === "UNAVAILABLE") { return "不可用"; }
    if (normalized === "NOT_CONNECTED") { return "價格未連接"; }
    return normalized || "待確認";
  }

  function screenerAppendText(parent, tag, className, textValue) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    node.textContent = textValue;
    parent.appendChild(node);
    return node;
  }

  function screenerTagLabel(tag) {
    return {
      bull: "當日上漲",
      bear: "當日下跌",
      disposition: "處置／注意",
      industry: "產業",
      us: "美股"
    }[tag] || tag;
  }

  function buildBreadthScreenerRow(row) {
    var article = document.createElement("article");
    article.className = "screen-row";
    article.setAttribute("role", "row");
    article.setAttribute("data-screener-row", "true");
    article.setAttribute("data-live-breadth-row", "true");
    article.setAttribute("data-stock-key", row.symbol);
    article.setAttribute("data-live-market", row.market);
    article.setAttribute("data-live-category", row.industry);
    article.setAttribute("data-search-text", row.searchText);
    article.setAttribute("data-screener-tags", row.tags.join(" "));
    article.setAttribute("data-base-screener-tags", row.tags.join(" "));
    article.setAttribute("data-reason-all", row.reasonAll);
    article.setAttribute("data-base-reason-all", row.reasonAll);
    for (var tagIndex = 0; tagIndex < row.tags.length; tagIndex++) {
      var tagName = row.tags[tagIndex];
      var reason = tagName === "disposition" && row.disposition
        ? (row.disposition.reason || row.reasonAll) : row.reasonAll;
      article.setAttribute("data-reason-" + tagName, String(reason));
      article.setAttribute("data-base-reason-" + tagName, String(reason));
    }

    var starCell = document.createElement("div");
    starCell.className = "screen-star-cell";
    starCell.setAttribute("role", "cell");
    var star = document.createElement("button");
    star.type = "button";
    star.className = "screen-star";
    star.setAttribute("data-watch-toggle", row.symbol);
    star.setAttribute("aria-pressed", "false");
    star.setAttribute("aria-label", "加入自選");
    star.textContent = "☆";
    var savedWatchlist = storageGet(storageKey("watchlist"), "");
    var savedSymbols = savedWatchlist ? savedWatchlist.split(",") : [];
    if (savedSymbols.indexOf(row.symbol) !== -1) {
      star.classList.add("active");
      star.setAttribute("aria-pressed", "true");
      star.setAttribute("aria-label", "移出自選");
      star.textContent = "★";
    }
    starCell.appendChild(star);
    article.appendChild(starCell);

    var company = document.createElement("div");
    company.className = "screen-company";
    company.setAttribute("role", "cell");
    var companyName = document.createElement("strong");
    var symbol = screenerAppendText(companyName, "span", "mono", row.symbol);
    symbol.appendChild(document.createTextNode(" "));
    companyName.appendChild(document.createTextNode(row.name));
    company.appendChild(companyName);
    var companyMeta = row.market + (row.exchange ? " / " + row.exchange : "");
    if (row.industry &&
        row.industry !== "未分類" &&
        String(row.industry).toUpperCase() !== String(row.exchange || "").toUpperCase()) {
      companyMeta += " · " + row.industry;
    }
    if (row.isEtf) { companyMeta += " · ETF"; }
    screenerAppendText(company, "span", "", companyMeta);
    var basePriceText = row.price === null
      ? (row.market === "US" ? "價格來源未連接" : "現價未提供")
      : "現價 " + liveNumber(row.price, 2) +
        (row.status ? " · " + row.status : "");
    var priceNode = screenerAppendText(
      company, "span", "screen-live-price mono",
      basePriceText
    );
    priceNode.setAttribute("data-live-stock-price", "true");
    priceNode.setAttribute("data-base-price-text", basePriceText);
    var tagBox = document.createElement("div");
    tagBox.className = "screen-tags";
    tagBox.setAttribute("data-live-stock-tags", "true");
    for (var tagIndex2 = 0; tagIndex2 < row.tags.length; tagIndex2++) {
      var badge = screenerAppendText(tagBox, "span", "ui-pill ui-pill-info", screenerTagLabel(row.tags[tagIndex2]));
      badge.setAttribute("data-screener-tag", row.tags[tagIndex2]);
      if (row.tags[tagIndex2] === "bull") { badge.className = "ui-pill ui-pill-ok"; }
      if (row.tags[tagIndex2] === "bear") { badge.className = "ui-pill ui-pill-blocked"; }
      if (row.tags[tagIndex2] === "disposition") { badge.className = "ui-pill ui-pill-warn"; }
    }
    company.appendChild(tagBox);
    article.appendChild(company);

    var thesis = document.createElement("div");
    thesis.className = "screen-thesis";
    thesis.setAttribute("role", "cell");
    var reason = screenerAppendText(thesis, "strong", "", row.reasonAll);
    reason.setAttribute("data-screener-reason", "true");
    if (row.market === "US") {
      screenerAppendText(
        thesis, "span", "",
        "FINRA 場外短售成交比 " + (
          row.shortVolumeRatio === null
            ? "--" : liveNumber(row.shortVolumeRatio, 2) + "%"
        ) +
        " · 短售量 " + liveNumber(row.shortVolume, 0) +
        " · 場外申報總量 " + liveNumber(row.reportedTotalVolume, 0)
      );
      screenerAppendText(
        thesis, "small", "",
        "FINRA 場外短售成交比並非 short interest，也不代表未回補空單"
      );
      screenerAppendText(
        thesis, "small", "",
        "價格來源未連接 · Nasdaq Trader 官方名錄" +
        (row.sourceEventTime
          ? " · FINRA 日期 " + row.sourceEventTime.replace("T", " ").slice(0, 16)
          : "")
      );
    } else {
      screenerAppendText(
        thesis, "span", "",
        "成交量 " + liveNumber(row.volume, 0) + " · 成交額 " + liveNumber(row.tradeValue, 0)
      );
      screenerAppendText(
        thesis, "small", "",
        "EPS " + liveNumber(row.eps, 2) +
        (row.financialPeriod ? " (" + row.financialPeriod + ")" : "") +
        " · PE " + liveNumber(row.peRatio, 2) +
        " · PB " + liveNumber(row.pbRatio, 2) +
        " · 殖利率 " + livePercent(row.dividendYield) +
        " · 估值時點 " + (
          row.valuationDate
            ? row.valuationDate.replace("T", " ").slice(0, 16)
            : "未提供"
        ) +
        " · 月營收 YoY " + livePercent(row.revenueYoy)
      );
      screenerAppendText(
        thesis, "small", "",
        "法人淨額 " + liveSignedNumber(row.institutionalNet, 0) +
        (row.institutionalStatus ? " · " + row.institutionalStatus : "") +
        (row.sourceEventTime
          ? " · " + row.sourceEventTime.replace("T", " ").slice(0, 16)
          : "")
      );
    }
    article.appendChild(thesis);

    var oneDay = screenerAppendText(article, "span", "screen-num mono", livePercent(row.changePercent));
    oneDay.setAttribute("role", "cell");
    oneDay.setAttribute("data-live-stock-change", "true");
    oneDay.setAttribute("data-base-change-text", livePercent(row.changePercent));
    oneDay.setAttribute(
      "data-base-change-value",
      row.changePercent === null ? "" : String(row.changePercent)
    );
    liveTone(oneDay, row.changePercent);
    var fiveDay = screenerAppendText(article, "span", "screen-num mono", livePercent(row.return5d));
    fiveDay.setAttribute("role", "cell");
    liveTone(fiveDay, row.return5d);
    var twentyDay = screenerAppendText(article, "span", "screen-num mono", livePercent(row.return20d));
    twentyDay.setAttribute("role", "cell");
    liveTone(twentyDay, row.return20d);
    var score = screenerAppendText(
      article, "span", "screen-score mono", row.score === null ? "未研究" : liveNumber(row.score, 0)
    );
    score.setAttribute("role", "cell");
    var quality = document.createElement("span");
    quality.className = "screen-quality";
    quality.setAttribute("role", "cell");
    var qualityPill = screenerAppendText(quality, "span", "ui-pill ui-pill-info", screenerStatusLabel(row.status));
    if (row.status === "LIVE") { qualityPill.className = "ui-pill ui-pill-ok"; }
    if ([
      "STALE", "UNAVAILABLE", "MISSING", "NO_ROW", "SUSPENDED",
      "UNDATED", "FUTURE", "PARTIAL", "NOT_CONNECTED"
    ].indexOf(row.status) !== -1) {
      qualityPill.className = "ui-pill ui-pill-warn";
    }
    article.appendChild(quality);
    return article;
  }

  function updateScreenerFilterCounts(rows, state) {
    var keys = ["all", "bull", "bear", "disposition", "industry", "us"];
    for (var keyIndex = 0; keyIndex < keys.length; keyIndex++) {
      if (keys[keyIndex] === "industry") {
        var industries = {};
        for (var industryIndex = 0; industryIndex < rows.length; industryIndex++) {
          if (!screenerCommonMatch(rows[industryIndex], {
            filter: state.filter,
            query: state.query,
            market: state.market,
            industry: "all",
            sort: state.sort
          })) { continue; }
          var industryName = String(rows[industryIndex].industry || "").trim();
          if (industryName && industryName !== "未分類") {
            industries[industryName] = true;
          }
        }
        var industryCount = document.querySelector(
          '[data-screener-filter-count="industry"]'
        );
        if (industryCount) {
          industryCount.textContent = String(Object.keys(industries).length);
        }
        continue;
      }
      if (keys[keyIndex] === "disposition" &&
          !screenerBreadthSourceAuthoritative("disposition_alerts")) {
        var unavailableNode = document.querySelector(
          '[data-screener-filter-count="disposition"]'
        );
        if (unavailableNode) { unavailableNode.textContent = "—"; }
        continue;
      }
      if ((keys[keyIndex] === "bull" || keys[keyIndex] === "bear") &&
          ["LIVE", "EOD"].indexOf(screenerBreadthStatus) === -1) {
        var trendUnavailableNode = document.querySelector(
          '[data-screener-filter-count="' + keys[keyIndex] + '"]'
        );
        if (trendUnavailableNode) { trendUnavailableNode.textContent = "—"; }
        continue;
      }
      if (keys[keyIndex] === "us" && screenerUniverseMode !== "US") {
        var unloadedUsNode = document.querySelector(
          '[data-screener-filter-count="us"]'
        );
        if (unloadedUsNode) {
          unloadedUsNode.textContent = !usMarketApiEnabled()
            ? "—"
            : screenerUsBreadthRows.length
              ? String(screenerUsBreadthRows.length)
              : usMarketState === "loading" ? "…" : "載入";
        }
        continue;
      }
      if (keys[keyIndex] === "us" &&
          !rows.some(function (row) {
            return String(row.market || "").toUpperCase() === "US";
          })) {
        var usUnavailableNode = document.querySelector(
          '[data-screener-filter-count="us"]'
        );
        if (usUnavailableNode) { usUnavailableNode.textContent = "—"; }
        continue;
      }
      var count = 0;
      for (var rowIndex = 0; rowIndex < rows.length; rowIndex++) {
        if (!screenerCommonMatch(rows[rowIndex], state)) { continue; }
        if (keys[keyIndex] === "all" || rows[rowIndex].tags.indexOf(keys[keyIndex]) !== -1) {
          count += 1;
        }
      }
      var node = document.querySelector(
        '[data-screener-filter-count="' + keys[keyIndex] + '"]'
      );
      if (node) { node.textContent = String(count); }
    }
  }

  function renderBreadthScreener() {
    if (!screenerBreadthRows.length) { return; }
    var state = screenerState();
    updateScreenerFilterCounts(screenerBreadthRows, state);
    var filtered = [];
    for (var i = 0; i < screenerBreadthRows.length; i++) {
      var row = screenerBreadthRows[i];
      if (!screenerCommonMatch(row, state)) { continue; }
      if (state.filter !== "all" && row.tags.indexOf(state.filter) === -1) { continue; }
      filtered.push(row);
    }
    screenerSortRows(filtered, state.sort);
    var filteredTotal = filtered.length;
    var totalPages = Math.max(1, Math.ceil(filteredTotal / screenerBreadthPageSize));
    screenerBreadthPage = Math.max(1, Math.min(screenerBreadthPage, totalPages));
    var start = (screenerBreadthPage - 1) * screenerBreadthPageSize;
    var pageRows = filtered.slice(start, start + screenerBreadthPageSize);
    var body = document.querySelector('[data-screener-body="true"]');
    if (body) {
      body.textContent = "";
      var fragment = document.createDocumentFragment();
      for (var pageIndex = 0; pageIndex < pageRows.length; pageIndex++) {
        fragment.appendChild(buildBreadthScreenerRow(pageRows[pageIndex]));
      }
      body.appendChild(fragment);
    }
    var count = document.querySelector('[data-screener-count="true"]');
    if (count) { count.textContent = String(filteredTotal); }
    var universeCount = document.querySelector('[data-screener-universe-count="true"]');
    var catalogTotal = Number(screenerBreadthCoverage.catalog_total);
    if (universeCount) {
      universeCount.textContent = String(
        isFinite(catalogTotal) && catalogTotal > screenerBreadthRows.length
          ? catalogTotal : screenerBreadthRows.length
      );
    }
    var quotedTotal = Number(
      screenerBreadthStatus === "LIVE"
        ? screenerBreadthCoverage.live_quoted_total
        : screenerBreadthCoverage.quoted_total
    );
    var scope = document.querySelector('[data-screener-scope-status="true"]');
    if (scope) {
      if (screenerUniverseMode === "US") {
        var usSession = String(screenerBreadthSessionDates.US || "");
        var shortSourceCount = Number(
          screenerBreadthCoverage.short_volume_source_row_count
        );
        var shortJoinedCount = Number(
          screenerBreadthCoverage.short_volume_joined_row_count
        );
        var shortUnmatchedCount = Number(
          screenerBreadthCoverage.short_volume_unmatched_row_count
        );
        var shortSecurityCount = Number(
          screenerBreadthCoverage.short_volume_joined_security_count
        );
        scope.textContent = (
          screenerBreadthStatus === "STALE"
            ? "美股官方名錄快取已過期"
            : "美股官方名錄 · FINRA 場外短售成交量"
        ) +
          (usSession ? " · FINRA 日期 " + usSession : "") +
          " · 價格來源未連接 · " + screenerBreadthRows.length + " 檔" +
          (
            isFinite(shortSecurityCount) && isFinite(shortJoinedCount) &&
            isFinite(shortSourceCount)
              ? " · FINRA 對照 " + shortSecurityCount + " 檔（" +
                shortJoinedCount + " / " + shortSourceCount + " 筆來源）"
              : ""
          ) +
          (
            isFinite(shortUnmatchedCount) && shortUnmatchedCount > 0
              ? " · 未對照 " + shortUnmatchedCount + " 筆"
              : ""
          ) +
          " · 非 short interest";
      } else {
        var scopeLabel = screenerBreadthStatus === "STALE"
        ? "全市場快取已過期"
        : screenerBreadthStatus === "PARTIAL"
          ? "全市場資料不完整"
          : screenerBreadthMode.indexOf("LIVE_FULL") !== -1
            ? "全市場即時"
            : screenerBreadthMode === "UNAVAILABLE"
              ? "全市場名錄 · 行情不可用"
              : screenerBreadthMode.indexOf("EOD_FULL") !== -1 &&
                screenerBreadthMode.indexOf("LIVE_PAGE") !== -1
                ? "全市場收盤底稿 · 可見前最多 " + liveSymbolLimit + " 檔行情更新"
                : screenerBreadthMode.indexOf("EOD") !== -1
                  ? "全市場收盤"
                  : screenerBreadthMode === "CATALOG_ONLY"
                    ? "全市場名錄 · 尚無行情" : "全市場資料";
      var sessionValues = [];
      var sessionMarkets = ["TWSE", "TPEX"];
      for (var sessionIndex = 0; sessionIndex < sessionMarkets.length; sessionIndex++) {
        var sessionValue = String(
          screenerBreadthSessionDates[sessionMarkets[sessionIndex]] || ""
        );
        if (sessionValue && sessionValues.indexOf(sessionValue) === -1) {
          sessionValues.push(sessionValue);
        }
      }
      if (sessionValues.length) { scopeLabel += " · 日期 " + sessionValues.join(" / "); }
      var supportWarnings = [];
      if (!screenerBreadthSourceAuthoritative("disposition_alerts")) {
        supportWarnings.push("處置來源不完整");
      }
      if (!screenerBreadthSourceAuthoritative("notice_alerts")) {
        supportWarnings.push("注意股票來源不完整");
      }
      if (!screenerBreadthSourceAuthoritative("fund_flow")) {
        supportWarnings.push("法人來源不完整");
      }
      if (!sourceStatusAuthoritative(
        screenerBreadthSourceStatus.valuation,
        ["FRESH"]
      )) {
        supportWarnings.push("估值覆蓋不完整");
      }
      if (!sourceStatusAuthoritative(
        screenerBreadthSourceStatus.fundamentals,
        ["FRESH"]
      )) {
        supportWarnings.push("財報覆蓋不完整");
      }
      if (!sourceStatusAuthoritative(
        screenerBreadthSourceStatus.revenue,
        ["FRESH"]
      )) {
        supportWarnings.push("月營收覆蓋不完整");
      }
      if (supportWarnings.length) { scopeLabel += " · " + supportWarnings.join("、"); }
      scope.textContent = isFinite(catalogTotal) && isFinite(quotedTotal)
        ? scopeLabel + " · 行情 " + quotedTotal + " / " + catalogTotal
        : scopeLabel + " · " + screenerBreadthRows.length + " 檔";
      }
    }
    var empty = document.querySelector('[data-screener-empty="true"]');
    if (empty) { empty.hidden = filteredTotal !== 0; }
    var pagination = document.querySelector('[data-screener-pagination="true"]');
    if (pagination) { pagination.hidden = filteredTotal <= screenerBreadthPageSize; }
    var pageStatus = document.querySelector('[data-screener-page-status="true"]');
    if (pageStatus) {
      pageStatus.textContent = "第 " + screenerBreadthPage + " / " + totalPages +
        " 頁 · " + filteredTotal + " 筆";
    }
    var previous = document.querySelector('[data-screener-page="prev"]');
    var next = document.querySelector('[data-screener-page="next"]');
    if (previous) { previous.disabled = screenerBreadthPage <= 1; }
    if (next) { next.disabled = screenerBreadthPage >= totalPages; }
  }

  function applyScreenerFilters() {
    if (screenerBreadthRows.length) {
      renderBreadthScreener();
      return;
    }
    var state = screenerState();
    var rows = document.querySelectorAll('[data-screener-row="true"]');
    var visible = 0;
    for (var i = 0; i < rows.length; i++) {
      var tags = " " + (rows[i].getAttribute("data-screener-tags") || "") + " ";
      var textValue = rows[i].getAttribute("data-search-text") || rows[i].textContent.toLowerCase();
      var tagMatch = state.filter === "all" || tags.indexOf(" " + state.filter + " ") !== -1;
      var queryMatch = !state.query || textValue.indexOf(state.query) !== -1;
      var rowMarket = String(rows[i].getAttribute("data-live-market") || "").toUpperCase();
      var marketMatch = state.market === "all" ||
        rowMarket === String(state.market || "").toUpperCase();
      var rowIndustry = rows[i].getAttribute("data-live-category") || "未分類";
      var industryMatch = state.industry === "all" || rowIndustry === state.industry;
      var show = tagMatch && queryMatch && marketMatch && industryMatch;
      rows[i].hidden = !show;
      var reason = rows[i].querySelector('[data-screener-reason="true"]');
      if (reason) {
        reason.textContent = rows[i].getAttribute("data-reason-" + state.filter)
          || rows[i].getAttribute("data-reason-all")
          || "尚無可驗證的命中原因";
      }
      if (show) { visible += 1; }
    }
    var count = document.querySelector('[data-screener-count="true"]');
    if (count) { count.textContent = String(visible); }
    var universeCount = document.querySelector('[data-screener-universe-count="true"]');
    if (universeCount) { universeCount.textContent = String(rows.length); }
    var scope = document.querySelector('[data-screener-scope-status="true"]');
    if (scope) { scope.textContent = "研究池範圍"; }
    var filterKeys = ["all", "bull", "bear", "disposition", "industry", "us"];
    for (var filterIndex = 0; filterIndex < filterKeys.length; filterIndex++) {
      var filterCount = 0;
      for (var countIndex = 0; countIndex < rows.length; countIndex++) {
        var countTags = " " + (rows[countIndex].getAttribute("data-screener-tags") || "") + " ";
        var countText = rows[countIndex].getAttribute("data-search-text") ||
          rows[countIndex].textContent.toLowerCase();
        var countMarket = String(
          rows[countIndex].getAttribute("data-live-market") || ""
        ).toUpperCase();
        var countIndustry = rows[countIndex].getAttribute("data-live-category") || "未分類";
        if (state.query && countText.indexOf(state.query) === -1) { continue; }
        if (state.market !== "all" &&
            countMarket !== String(state.market || "").toUpperCase()) { continue; }
        if (state.industry !== "all" && countIndustry !== state.industry) { continue; }
        if (filterKeys[filterIndex] === "all" ||
            countTags.indexOf(" " + filterKeys[filterIndex] + " ") !== -1) {
          filterCount += 1;
        }
      }
      var filterNode = document.querySelector(
        '[data-screener-filter-count="' + filterKeys[filterIndex] + '"]'
      );
      if (filterNode) { filterNode.textContent = String(filterCount); }
    }
    var empty = document.querySelector('[data-screener-empty="true"]');
    if (empty) { empty.hidden = visible !== 0; }
  }

  function initScreener() {
    initUsMarketControls();
    var filters = document.querySelectorAll("[data-screener-filter]");
    for (var i = 0; i < filters.length; i++) {
      filters[i].addEventListener("click", function (event) {
        var requestedFilter = event.currentTarget.getAttribute("data-screener-filter");
        if (requestedFilter === "us") {
          if (!usMarketApiEnabled()) { return; }
          setScreenerActiveFilter("us");
          var usMarketSelect = document.querySelector(
            '[data-screener-market="true"]'
          );
          if (usMarketSelect) { usMarketSelect.value = "US"; }
          loadUsMarket(false);
          return;
        }
        if (screenerUniverseMode !== "US") {
          screenerDesiredUniverseMode = "TW";
        }
        if (requestedFilter === "all") {
          screenerDesiredUniverseMode = "TW";
          if (screenerUniverseMode === "US") {
            activateTaiwanScreener("all");
          }
        }
        if (requestedFilter === "industry") {
          var industrySelect = document.querySelector(
            '[data-screener-industry="true"]'
          );
          if (!industrySelect || industrySelect.disabled) { return; }
          for (var resetIndex = 0; resetIndex < filters.length; resetIndex++) {
            var isAll = filters[resetIndex].getAttribute("data-screener-filter") === "all";
            filters[resetIndex].classList.toggle("active", isAll);
            filters[resetIndex].setAttribute("aria-pressed", isAll ? "true" : "false");
          }
          screenerBreadthPage = 1;
          applyScreenerFilters();
          industrySelect.focus();
          if (typeof industrySelect.showPicker === "function") {
            try { industrySelect.showPicker(); } catch (err) {}
          }
          return;
        }
        for (var j = 0; j < filters.length; j++) {
          var active = filters[j] === event.currentTarget;
          filters[j].classList.toggle("active", active);
          filters[j].setAttribute("aria-pressed", active ? "true" : "false");
        }
        screenerBreadthPage = 1;
        applyScreenerFilters();
        scheduleVisibleLiveRefresh();
      });
    }
    var input = document.querySelector('[data-screener-search="true"]');
    if (input) {
      input.addEventListener("input", function () {
        screenerBreadthPage = 1;
        applyScreenerFilters();
        scheduleVisibleLiveRefresh();
      });
    }
    var selects = document.querySelectorAll(
      '[data-screener-market="true"], [data-screener-industry="true"], ' +
      '[data-screener-sort="true"], [data-screener-page-size="true"]'
    );
    for (var selectIndex = 0; selectIndex < selects.length; selectIndex++) {
      selects[selectIndex].addEventListener("change", function (event) {
        screenerBreadthPage = 1;
        var isMarketSelect = event.currentTarget.getAttribute(
          "data-screener-market"
        ) === "true";
        if (isMarketSelect && event.currentTarget.value === "US") {
          setScreenerActiveFilter("us");
          loadUsMarket(false);
          return;
        }
        if (isMarketSelect) {
          var taiwanMarket = event.currentTarget.value || "all";
          screenerDesiredUniverseMode = "TW";
          if (screenerUniverseMode === "US") {
            activateTaiwanScreener(taiwanMarket);
            setScreenerActiveFilter("all");
            applyScreenerFilters();
            return;
          }
        }
        if (event.currentTarget.getAttribute("data-screener-page-size") === "true") {
          screenerBreadthPageSize = Math.max(1, Number(event.currentTarget.value) || 50);
        }
        applyScreenerFilters();
        scheduleVisibleLiveRefresh();
      });
    }
    var pageButtons = document.querySelectorAll("[data-screener-page]");
    for (var pageIndex = 0; pageIndex < pageButtons.length; pageIndex++) {
      pageButtons[pageIndex].addEventListener("click", function (event) {
        var direction = event.currentTarget.getAttribute("data-screener-page");
        screenerBreadthPage += direction === "prev" ? -1 : 1;
        renderBreadthScreener();
        scheduleVisibleLiveRefresh();
        var table = document.querySelector(".screen-table");
        if (table) { table.scrollIntoView({ behavior: "smooth", block: "start" }); }
      });
    }
    applyScreenerFilters();
  }

  function storageGet(key, fallback) {
    try {
      if (window.localStorage) {
        var value = window.localStorage.getItem(key);
        return value === null ? fallback : value;
      }
    } catch (err) {}
    return fallback;
  }

  function storageSet(key, value) {
    try {
      if (window.localStorage) {
        window.localStorage.setItem(key, value);
        return true;
      }
    } catch (err) {}
    return false;
  }

  function storageKey(name) {
    var namespace = document.body.getAttribute("data-storage-namespace") || "unscoped";
    return "taiwan-equity-lens:" + encodeURIComponent(namespace) + ":" + name;
  }

  function initWatchlist() {
    var key = storageKey("watchlist");
    var saved = storageGet(key, "");
    var selected = saved ? saved.split(",") : [];
    var buttons = document.querySelectorAll("[data-watch-toggle]");
    function sync(btn) {
      var stock = btn.getAttribute("data-watch-toggle") || "";
      var active = selected.indexOf(stock) !== -1;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      btn.setAttribute("aria-label", active ? "移出自選" : "加入自選");
      btn.textContent = active ? "★" : "☆";
    }
    for (var i = 0; i < buttons.length; i++) { sync(buttons[i]); }
    document.addEventListener("click", function (event) {
      var target = event.target;
      var btn = target && target.closest ? target.closest("[data-watch-toggle]") : null;
      if (!btn) { return; }
      var stock = btn.getAttribute("data-watch-toggle") || "";
      var index = selected.indexOf(stock);
      if (index === -1) { selected.push(stock); } else { selected.splice(index, 1); }
      var stored = storageSet(key, selected.join(","));
      sync(btn);
      if (!stored) {
        btn.setAttribute("title", "本機儲存不可用；自選只保留到此頁關閉");
      }
    });
  }

  function initMarketNotes() {
    var input = document.querySelector('[data-market-note="true"]');
    var state = document.querySelector('[data-note-state="true"]');
    var key = storageKey("market-note");
    if (!input) { return; }
    input.value = storageGet(key, "");
    var timer = null;
    input.addEventListener("input", function () {
      if (state) { state.textContent = "儲存中…"; }
      if (timer) { clearTimeout(timer); }
      timer = setTimeout(function () {
        var stored = storageSet(key, input.value);
        if (state) {
          state.textContent = stored
            ? "已儲存在本機"
            : "本機儲存失敗；內容仍保留在目前頁面";
        }
      }, 220);
    });
    var addButtons = document.querySelectorAll('[data-add-note="true"]');
    for (var i = 0; i < addButtons.length; i++) {
      addButtons[i].addEventListener("click", function (event) {
        var card = event.currentTarget.closest ? event.currentTarget.closest(".intel-news-card") : null;
        var title = card ? card.querySelector("h3") : null;
        var line = title ? "• " + title.textContent.trim() : "• 新聞事件";
        input.value = (input.value ? input.value.replace(/\s+$/, "") + "\n" : "") + line + "\n  - 重要性：\n  - 待確認：";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      });
    }
  }

  function activeIntelNewsFilter() {
    var active = document.querySelector("[data-intel-news-filter].active");
    return active ? active.getAttribute("data-intel-news-filter") || "all" : "all";
  }

  function applyIntelNewsFilter() {
    var mode = activeIntelNewsFilter();
    var cards = document.querySelectorAll('[data-intel-news="true"]');
    for (var i = 0; i < cards.length; i++) {
      cards[i].hidden = mode === "mapped" &&
        cards[i].getAttribute("data-intel-mapped") !== "true";
    }
  }

  function initIntelNewsFilters() {
    var buttons = document.querySelectorAll("[data-intel-news-filter]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        for (var j = 0; j < buttons.length; j++) {
          var active = buttons[j] === event.currentTarget;
          buttons[j].classList.toggle("active", active);
          buttons[j].setAttribute("aria-pressed", active ? "true" : "false");
        }
        applyIntelNewsFilter();
      });
    }
  }

  function initIndustryMap() {
    var map = document.querySelector('[data-industry-map="true"]');
    if (!map) { return; }
    map.addEventListener("click", function (event) {
      var target = event.target;
      var tile = target && target.closest ? target.closest("[data-industry-tile]") : null;
      if (!tile) { return; }
      var category = tile.getAttribute("data-industry-tile") || "";
      var cards = document.querySelectorAll("[data-sentiment-category]");
      for (var j = 0; j < cards.length; j++) {
        if (cards[j].getAttribute("data-sentiment-category") === category) {
          cards[j].scrollIntoView({ behavior: "smooth", block: "center" });
          cards[j].classList.add("industry-focus");
          (function (card) {
            setTimeout(function () { card.classList.remove("industry-focus"); }, 1400);
          })(cards[j]);
          return;
        }
      }
      var select = document.querySelector('[data-screener-industry="true"]');
      if (select) {
        for (var optionIndex = 0; optionIndex < select.options.length; optionIndex++) {
          var option = select.options[optionIndex];
          if (option.value === category ||
              option.getAttribute("data-industry-name") === category) {
            select.value = option.value;
            screenerBreadthPage = 1;
            applyScreenerFilters();
            scheduleVisibleLiveRefresh();
            activateTab("screener");
            setTabHash("screener");
            window.scrollTo(0, 0);
            focusActivePanel("screener");
            return;
          }
        }
      }
    });
  }

  function initExpandToggles() {
    var toggles = document.querySelectorAll("[data-queue-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        var targetId = btn.getAttribute("data-queue-toggle");
        var expand = document.querySelector('.queue-expand[data-expand-for="' + targetId + '"]');
        if (!expand) { return; }
        var label = btn.getAttribute("data-toggle-label") || "審查事項";
        if (expand.hasAttribute("hidden")) {
          expand.removeAttribute("hidden");
          btn.textContent = "收合 ▲";
          btn.setAttribute("aria-expanded", "true");
          btn.setAttribute("aria-label", label + "：收合");
        } else {
          expand.setAttribute("hidden", "");
          btn.textContent = "展開 ▼";
          btn.setAttribute("aria-expanded", "false");
          btn.setAttribute("aria-label", label + "：展開");
        }
      });
    }
  }

  function readFilterState() {
    var state = {};
    var controls = document.querySelectorAll("[data-queue-filter]");
    for (var i = 0; i < controls.length; i++) {
      state[controls[i].getAttribute("data-queue-filter")] = (controls[i].value || "").trim();
    }
    return state;
  }

  function rowMatchesFilters(row, state) {
    var attrKeys = ["priority", "category", "severity", "status"];
    for (var i = 0; i < attrKeys.length; i++) {
      var key = attrKeys[i];
      var want = state[key];
      if (want && want !== "all" && row.getAttribute("data-" + key) !== want) {
        return false;
      }
    }
    var search = (state.search || "").toLowerCase();
    if (search && row.textContent.toLowerCase().indexOf(search) === -1) {
      return false;
    }
    return true;
  }

  function applyQueueFilters() {
    var state = readFilterState();
    var rows = document.querySelectorAll(".queue-row[data-stock]");
    var visibleCount = 0;
    for (var i = 0; i < rows.length; i++) {
      var matches = rowMatchesFilters(rows[i], state);
      rows[i].classList.toggle("hidden", !matches);
      if (matches) { visibleCount += 1; }
    }
    // Final polish C1 (spec §3.3 "...搜尋、重設"): show the
    // data-review-action-empty marker only when the current filters excluded
    // every row (never when the queue itself is empty -- that's
    // _queue_card()'s own separate "目前無待辦" placeholder, and this element
    // isn't rendered in that case at all, so the query below is a safe no-op).
    var emptyState = document.querySelector('[data-review-action-empty="true"]');
    if (emptyState) { emptyState.hidden = !(rows.length > 0 && visibleCount === 0); }
    // Keep the bulk toolbar's live count / "select visible" tri-state in sync
    // whenever the visible-row set changes (filter edits, and the end of a
    // bulk update below) -- updateBulkSelectionUI() no-ops when the toolbar
    // isn't on the page (empty queue), so this is safe to call unconditionally.
    updateBulkSelectionUI();
  }

  function initQueueFilters() {
    var controls = document.querySelectorAll("[data-queue-filter]");
    for (var i = 0; i < controls.length; i++) {
      var eventName = controls[i].tagName === "SELECT" ? "change" : "input";
      controls[i].addEventListener(eventName, applyQueueFilters);
    }
    if (controls.length) { applyQueueFilters(); }
  }

  // Final polish C1: resets every [data-queue-filter] control to its default
  // (each <select>'s first option is the "all" value _filter_select() always
  // renders first; the search <input> just clears) and re-applies filters so
  // every row is shown again. Attribute name ported from the pre-redesign
  // dashboard.py's resetButton handler (deleted at da4a47a^).
  function initQueueFilterReset() {
    var resetButton = document.querySelector('[data-review-filter-reset="true"]');
    if (!resetButton) { return; }
    resetButton.addEventListener("click", function () {
      var controls = document.querySelectorAll("[data-queue-filter]");
      for (var i = 0; i < controls.length; i++) {
        controls[i].value = controls[i].tagName === "SELECT" ? "all" : "";
      }
      applyQueueFilters();
    });
  }

  // -- Feature C: bulk queue operations (spec 3.3 "批次操作") -----------------

  function queueVisibleRows() {
    var rows = document.querySelectorAll(".queue-row[data-stock]");
    var visible = [];
    for (var i = 0; i < rows.length; i++) {
      if (!rows[i].classList.contains("hidden")) { visible.push(rows[i]); }
    }
    return visible;
  }

  function queueRowCheckbox(row) {
    return row.querySelector('[data-queue-select="true"]');
  }

  function queueSelectedRows() {
    var visible = queueVisibleRows();
    var selected = [];
    for (var i = 0; i < visible.length; i++) {
      var checkbox = queueRowCheckbox(visible[i]);
      if (checkbox && checkbox.checked) { selected.push(visible[i]); }
    }
    return selected;
  }

  function updateBulkSelectionUI() {
    var countEl = document.querySelector('[data-queue-bulk-count="true"]');
    if (!countEl) { return; }
    var selected = queueSelectedRows();
    countEl.textContent = "已選取 " + selected.length + " 筆";
    var selectVisible = document.querySelector('[data-queue-select-visible="true"]');
    if (selectVisible) {
      var visible = queueVisibleRows();
      selectVisible.checked = visible.length > 0 && selected.length === visible.length;
      selectVisible.indeterminate = selected.length > 0 && selected.length < visible.length;
    }
  }

  function initBulkSelection() {
    var selectVisible = document.querySelector('[data-queue-select-visible="true"]');
    if (selectVisible) {
      selectVisible.addEventListener("change", function () {
        var checked = selectVisible.checked;
        var rows = queueVisibleRows();
        for (var i = 0; i < rows.length; i++) {
          var checkbox = queueRowCheckbox(rows[i]);
          if (checkbox) { checkbox.checked = checked; }
        }
        updateBulkSelectionUI();
      });
    }
    var checkboxes = document.querySelectorAll('[data-queue-select="true"]');
    for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].addEventListener("change", updateBulkSelectionUI);
    }
    updateBulkSelectionUI();
  }

  function initBulkStaticCopy() {
    // Static mode only: served-mode bulk buttons carry data-action-api and are
    // handled by handleBulkReviewAction() via the initActionApi() dispatcher
    // below instead.
    var buttons = document.querySelectorAll('[data-queue-bulk-status]:not([data-action-api])');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        var status = btn.getAttribute("data-queue-bulk-status") || "";
        var selected = queueSelectedRows();
        if (!selected.length) {
          flashLabel(btn, "請先勾選事項", 1500);
          return;
        }
        var commands = [];
        for (var j = 0; j < selected.length; j++) {
          var checkbox = queueRowCheckbox(selected[j]);
          var command = checkbox ? checkbox.getAttribute("data-command-" + status) : "";
          if (command) { commands.push(command); }
        }
        if (!commands.length || !navigator.clipboard || !navigator.clipboard.writeText) { return; }
        navigator.clipboard.writeText(commands.join("\n")).then(function () {
          flashLabel(btn, "已複製 " + commands.length + " 筆 ✓", 1500);
        }, function () {
          flashLabel(btn, "複製失敗", 1500);
        });
      });
    }
  }

  function flashLabel(el, text, delayMs) {
    var original = el.textContent;
    el.textContent = text;
    var live = document.querySelector('[data-ui-live-status="true"]');
    if (live) { live.textContent = text; }
    setTimeout(function () { el.textContent = original; }, delayMs || 1500);
  }

  function initCopyButtons() {
    var buttons = document.querySelectorAll("[data-copy]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        var text = btn.getAttribute("data-copy") || "";
        if (!navigator.clipboard || !navigator.clipboard.writeText) { return; }
        navigator.clipboard.writeText(text).then(function () {
          flashLabel(btn, "已複製 ✓", 1500);
        }, function () {
          flashLabel(btn, "複製失敗", 1500);
        });
      });
    }
  }

  function postJson(url, payload) {
    var mutationToken = document.body
      ? (document.body.getAttribute("data-action-api-token") || "")
      : "";
    if (!mutationToken) {
      return Promise.reject(new Error("mutation API token is unavailable"));
    }
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Taiwan-Equity-Lens-Token": mutationToken
      },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || data.ok === false) {
          throw new Error((data && data.error) || ("request failed: " + response.status));
        }
        return data;
      });
    });
  }

  function setTopbarPill(id, text, tone) {
    var host = document.getElementById(id);
    if (!host) { return; }
    host.innerHTML = "";
    var span = document.createElement("span");
    span.className = "ui-pill ui-pill-" + tone;
    span.textContent = text;
    host.appendChild(span);
  }

  function syncGateFromResponse(data) {
    if (typeof data.blocker_count === "number") {
      var ready = !!data.ready;
      setTopbarPill(
        "topbar-gate-pill",
        ready ? "可交接" : "交接 Gate：阻塞 " + data.blocker_count + " 件",
        ready ? "ok" : "blocked"
      );
      syncGateCard(data);
    }
    if (typeof data.open_count === "number") {
      setTopbarPill("topbar-backlog-pill", "待辦 " + data.open_count, "info");
    }
  }

  // Resyncs the workbench gate card (views/workbench.py:_gate_card) so it
  // doesn't contradict the just-updated topbar pill. Every number used here is
  // taken directly from (or is a plain sum of) fields dashboard_server.py's
  // /api/review-actions/set and /api/handoff-pack/write responses already
  // return -- blocker_count/ready always; by_status (open/done/deferred/
  // ignored counts, from review_action_state.py:build_review_action_state_report)
  // only on review-actions/set. Nothing here is invented client-side: total and
  // processed are exact sums of the server's own per-status counts, and the
  // readiness pill text mirrors workbench.py's own
  // `"交付門檻已通過" if ready else f"尚有 {blocker_count} 件待交接阻塞"` template verbatim.
  function syncGateCard(data) {
    var blockersEl = document.getElementById("wb-gate-blockers");
    if (blockersEl) { blockersEl.textContent = String(data.blocker_count); }

    var readinessEl = document.getElementById("wb-gate-readiness");
    if (readinessEl) {
      var ready = !!data.ready;
      readinessEl.innerHTML = "";
      var pillSpan = document.createElement("span");
      pillSpan.className = "ui-pill ui-pill-" + (ready ? "ok" : "blocked");
      pillSpan.textContent = ready ? "交付門檻已通過" : "尚有 " + data.blocker_count + " 件待交接阻塞";
      readinessEl.appendChild(pillSpan);
    }

    // by_status is absent from the handoff-pack response (it doesn't change any
    // action's status) -- skip the processed/total + progress-bar update rather
    // than showing a fabricated 0/0. Final polish C4: dashboard_server.py's
    // _state_report_for_path also degrades to {"by_status": {}, ...} (still
    // inside an "ok": true response) when the sibling research_summary.json
    // is missing/unparseable/has a state warning -- an EMPTY object is still
    // "present" under the old `!byStatus` check alone, so it fell through to
    // render a fabricated "0 / 0 已處理" that contradicts this comment's own
    // intent. Object.keys(...).length catches that case the same way.
    var byStatus = data.by_status;
    if (!byStatus || typeof byStatus !== "object" || !Object.keys(byStatus).length) { return; }
    var openCt = byStatus.open || 0;
    var doneCt = byStatus.done || 0;
    var deferredCt = byStatus.deferred || 0;
    var ignoredCt = byStatus.ignored || 0;
    var total = openCt + doneCt + deferredCt + ignoredCt;
    var processed = doneCt + deferredCt + ignoredCt;

    var processedEl = document.getElementById("wb-gate-processed");
    if (processedEl) { processedEl.textContent = processed + " / " + total + " 已處理"; }

    var progressEl = document.getElementById("wb-gate-progress");
    if (progressEl && total > 0) {
      var fill = progressEl.querySelector("span");
      if (fill) {
        var pct = Math.min(Math.max((processed / total) * 100, 0), 100);
        fill.style.width = Math.round(pct) + "%";
      }
    }
  }

  var STATUS_LABELS = { done: "已完成", deferred: "稍後處理", ignored: "不處理" };
  var STATUS_TONES = { done: "ok", deferred: "warn", ignored: "info" };

  function updateRowStatus(row, status) {
    if (!row) { return; }
    row.setAttribute("data-status", status);
    var actions = row.querySelector(".wb-actions");
    var label = STATUS_LABELS[status];
    if (!actions || !label) { return; }
    var badge = actions.querySelector(".ui-badge");
    if (!badge) {
      badge = document.createElement("span");
      actions.insertBefore(badge, actions.firstChild);
    }
    badge.className = "ui-badge ui-badge-" + (STATUS_TONES[status] || "info");
    badge.textContent = label;
  }

  // CRITICAL fix (data loss regression, restored from the pre-redesign
  // window.prompt-based guard): an evidence-required row moving to a non-
  // "open" status with no note/reviewer/evidence_url anywhere (neither typed
  // into the form now nor already on record) must be refused client-side,
  // not silently sent as three blank strings. data-requires-evidence/
  // data-has-evidence come from the row's own attributes (workbench.py's
  // _queue_row_block); a deliberate CLEAR (row already has stored evidence,
  // user blanks the inputs on purpose) is still allowed through -- only the
  // "never had evidence, still doesn't" case is blocked.
  function evidenceGuardMessage(row, payload) {
    if (!row || row.getAttribute("data-requires-evidence") !== "true") { return ""; }
    if (payload.status === "open") { return ""; }
    if (row.getAttribute("data-has-evidence") === "true") { return ""; }
    var blank = !(payload.note && payload.note.trim())
      && !(payload.reviewer && payload.reviewer.trim())
      && !(payload.evidence_url && payload.evidence_url.trim());
    return blank ? "需要 note、reviewer、evidence URL 才能更新這個交付前 blocker。" : "";
  }

  function handleReviewAction(btn) {
    var expand = btn.closest ? btn.closest(".queue-expand") : null;
    var rowId = expand ? expand.getAttribute("data-expand-for") : null;
    var row = rowId ? document.getElementById(rowId) : null;
    var payload = {
      state_path: btn.getAttribute("data-state-path") || "",
      stock_id: btn.getAttribute("data-stock") || "",
      action_id: btn.getAttribute("data-action-id") || "",
      status: btn.getAttribute("data-status") || ""
    };
    var evidenceInputs = expand ? expand.querySelectorAll(".queue-evidence input") : [];
    if (evidenceInputs.length === 3) {
      payload.note = evidenceInputs[0].value || "";
      payload.reviewer = evidenceInputs[1].value || "";
      payload.evidence_url = evidenceInputs[2].value || "";
    }
    var guardMessage = evidenceGuardMessage(row, payload);
    if (guardMessage) {
      flashLabel(btn, guardMessage, 1500);
      return;
    }
    btn.disabled = true;
    postJson("/api/review-actions/set", payload).then(function (data) {
      updateRowStatus(row, payload.status);
      syncGateFromResponse(data);
      applyQueueFilters();
      flashLabel(btn, "已更新 ✓", 1500);
    }, function (err) {
      if (window.console && window.console.error) { window.console.error(err); }
      flashLabel(btn, "更新失敗", 1500);
    }).then(function () {
      btn.disabled = false;
    });
  }

  function handleHandoffPack(btn) {
    var payload = {
      research_summary_path: btn.getAttribute("data-source-path") || "",
      state_path: btn.getAttribute("data-state-path") || ""
    };
    btn.disabled = true;
    postJson("/api/handoff-pack/write", payload).then(function (data) {
      syncGateFromResponse(data);
      flashLabel(btn, "已產出 ✓", 1500);
    }, function (err) {
      if (window.console && window.console.error) { window.console.error(err); }
      flashLabel(btn, "產出失敗", 1500);
    }).then(function () {
      btn.disabled = false;
    });
  }

  var SENTIMENT_SORT_ATTR = {
    score: "sentimentScore",
    change: "sentimentChange",
    peak_risk: "peakRisk",
    trough_risk: "troughRisk",
    confidence: "confidenceOrder"
  };

  function sentimentCardValue(card, attrKey) {
    var raw = card.dataset[attrKey];
    var number = raw && raw.trim() ? Number(raw) : NaN;
    return Number.isFinite(number) ? number : -Infinity;
  }

  function sortSentimentCards(grid, sortKey) {
    var attrKey = SENTIMENT_SORT_ATTR[sortKey] || SENTIMENT_SORT_ATTR.score;
    var cards = Array.prototype.slice.call(grid.querySelectorAll("[data-sentiment-status]"));
    cards.sort(function (left, right) {
      // "|| tiebreak", not "if (diff !== 0)": when both cards are missing/
      // insufficient-history, sentimentCardValue() returns -Infinity for both, and
      // -Infinity - (-Infinity) is NaN, not 0. "!==" treats NaN as "different" and
      // would return NaN as the comparator result (unspecified sort behavior); "||"
      // treats NaN the same as 0 (both falsy) and correctly falls through to the
      // category tiebreak, matching dashboard.py:685's proven `bv - av || tiebreak`.
      var diff = sentimentCardValue(right, attrKey) - sentimentCardValue(left, attrKey);
      var leftName = left.getAttribute("data-sentiment-category") || "";
      var rightName = right.getAttribute("data-sentiment-category") || "";
      return diff || leftName.localeCompare(rightName, "zh-Hant-TW");
    });
    for (var i = 0; i < cards.length; i++) {
      grid.appendChild(cards[i]);
    }
  }

  function initIndustrySentimentSort() {
    var select = document.querySelector('[data-industry-sentiment-sort="true"]');
    var grid = document.querySelector('[data-market-sentiment-section="true"]');
    if (!select || !grid) { return; }
    select.addEventListener("change", function () {
      sortSentimentCards(grid, select.value);
    });
  }

  // Served-mode bulk handler (spec 3.3 "批次操作"): POSTs each selected row's
  // action to /api/review-actions/set one at a time -- sequentially, not via
  // Promise.all, because set_review_action_state() is a read-modify-write on
  // one shared JSON file and concurrent requests could clobber each other.
  // Mirrors handleReviewAction()'s per-row update + gate resync, just applied
  // once per selected row and gate-synced once at the end from the final
  // response (which already reflects every update made so far in this batch).
  function handleBulkReviewAction(btn) {
    var status = btn.getAttribute("data-queue-bulk-status") || "";
    var statePath = btn.getAttribute("data-state-path") || "";
    var rows = queueSelectedRows();
    if (!rows.length) {
      flashLabel(btn, "請先勾選事項", 1500);
      return;
    }
    btn.disabled = true;
    var succeeded = 0;
    var skipped = 0;
    var attempted = 0;
    var lastData = null;
    var chain = Promise.resolve();
    rows.forEach(function (row) {
      // CRITICAL fix: bulk never sends note/reviewer/evidence_url (see below),
      // so an evidence-required row with nothing on record yet must be
      // skipped here -- otherwise the server would silently close it with no
      // evidence at all. Rows that already have evidence on record are safe
      // to bulk-update: the server preserves it (data-loss fix in
      // dashboard_server.py::set_review_action_status_from_payload).
      if (row.getAttribute("data-requires-evidence") === "true" && row.getAttribute("data-has-evidence") !== "true") {
        skipped += 1;
        return;
      }
      attempted += 1;
      chain = chain.then(function () {
        var checkbox = queueRowCheckbox(row);
        var payload = {
          state_path: statePath,
          stock_id: checkbox ? (checkbox.getAttribute("data-stock") || "") : "",
          action_id: checkbox ? (checkbox.getAttribute("data-action-id") || "") : "",
          status: status
        };
        return postJson("/api/review-actions/set", payload).then(function (data) {
          succeeded += 1;
          lastData = data;
          updateRowStatus(row, status);
          if (checkbox) { checkbox.checked = false; }
        }, function (err) {
          if (window.console && window.console.error) { window.console.error(err); }
        });
      });
    });
    chain.then(function () {
      btn.disabled = false;
      if (lastData) { syncGateFromResponse(lastData); }
      applyQueueFilters();
      var message = attempted > 0 ? "已更新 " + succeeded + " / " + attempted + " 筆" : "";
      if (skipped > 0) {
        var skipMessage = skipped + " 筆需要交付證據，已略過";
        message = message ? message + "，" + skipMessage : skipMessage;
      }
      flashLabel(btn, message, 1500);
    });
  }

  function initActionApi() {
    if (!window.fetch) { return; }
    var buttons = document.querySelectorAll("[data-action-api]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        var kind = btn.getAttribute("data-action-api");
        if (kind === "review-action") {
          handleReviewAction(btn);
        } else if (kind === "handoff-pack") {
          handleHandoffPack(btn);
        } else if (kind === "bulk-review-action") {
          handleBulkReviewAction(btn);
        }
      });
    }
  }

  // -- spec section 10 (evidence composer): served-mode compose-and-set
  // control, restoring a client for dashboard_server.py's still-live
  // /api/evidence/compose-and-set route (compose_evidence_from_payload) that
  // the redesign migration dropped. Reads the SAME 3 .queue-evidence inputs
  // (note/reviewer/evidence_url) handleReviewAction already reads above, plus
  // the new evidence_summary textarea and overwrite checkbox
  // views/workbench.py's _evidence_compose_block renders
  // (data-evidence-compose-summary / data-evidence-compose-overwrite). Ported
  // Chinese vocabulary (Reviewer Confidence labels, Evidence Preview heading)
  // matches the pre-redesign dashboard.py's
  // evidenceQualityLabel/renderEvidenceComposerResult. Uses its own
  // data-evidence-compose="true" hook (not the data-action-api dispatcher
  // above) and its own initEvidenceCompose(), per the button markup
  // views/workbench.py emits.
  var EVIDENCE_QUALITY_LABELS = { handoff_ready: "可交付", needs_review: "需要再審查", draft: "草稿" };

  function evidenceQualityLabel(status) {
    return EVIDENCE_QUALITY_LABELS[status] || "未知";
  }

  function evidenceComposeFields(expand) {
    var evidenceInputs = expand ? expand.querySelectorAll(".queue-evidence input") : [];
    var summaryField = expand ? expand.querySelector('[data-evidence-compose-summary="true"]') : null;
    var overwriteField = expand ? expand.querySelector('[data-evidence-compose-overwrite="true"]') : null;
    return {
      note: evidenceInputs.length === 3 ? (evidenceInputs[0].value || "") : "",
      reviewer: evidenceInputs.length === 3 ? (evidenceInputs[1].value || "") : "",
      evidence_url: evidenceInputs.length === 3 ? (evidenceInputs[2].value || "") : "",
      evidence_summary: summaryField ? (summaryField.value || "") : "",
      overwrite: !!(overwriteField && overwriteField.checked)
    };
  }

  // Mirrors evidenceGuardMessage()'s vocabulary above, but compose always
  // writes a brand-new evidence file server-side (compose_evidence_from_payload's
  // _required_text on all three fields) -- so this blocks on ANY of the three
  // being blank, not only the "nothing on record anywhere" all-blank case the
  // plain status-set guard above allows through.
  function evidenceComposeGuardMessage(fields) {
    var hasNote = !!(fields.note && fields.note.trim());
    var hasReviewer = !!(fields.reviewer && fields.reviewer.trim());
    var hasSummary = !!(fields.evidence_summary && fields.evidence_summary.trim());
    if (hasNote && hasReviewer && hasSummary) { return ""; }
    return "需要 note、reviewer、evidence summary 才能建立證據並標記完成。";
  }

  function renderEvidenceComposeResult(container, data) {
    if (!container) { return; }
    var quality = data.evidence_quality || {};
    var preview = data.evidence_preview || {};
    var checks = Array.isArray(quality.checks) ? quality.checks : [];
    var status = quality.status || "unknown";
    container.textContent = "";
    container.setAttribute("data-evidence-quality-status", status);

    var summary = document.createElement("p");
    summary.className = "wb-compose-summary";
    summary.textContent = "已建立證據：" + (data.evidence_url || "-") +
      "；Reviewer Confidence（審查信心）：" + evidenceQualityLabel(status) + "。";
    container.appendChild(summary);

    var nextStep = document.createElement("p");
    nextStep.className = "wb-compose-next";
    nextStep.textContent = quality.next_step || "請先檢查證據預覽再交付。";
    container.appendChild(nextStep);

    var checkList = document.createElement("ul");
    checkList.className = "wb-compose-checks";
    for (var i = 0; i < checks.length; i++) {
      var check = checks[i] || {};
      var item = document.createElement("li");
      item.textContent = (check.label || check.id || "check") + ": " +
        (check.status || "unknown") + " - " + (check.message || "");
      checkList.appendChild(item);
    }
    container.appendChild(checkList);

    var previewBox = document.createElement("div");
    previewBox.className = "wb-compose-preview";
    var previewTitle = document.createElement("strong");
    previewTitle.textContent = "Evidence Preview（證據預覽）";
    previewBox.appendChild(previewTitle);
    var previewPath = document.createElement("p");
    previewPath.textContent = preview.path || data.evidence_path || data.evidence_url || "-";
    previewBox.appendChild(previewPath);
    var previewContent = document.createElement("pre");
    previewContent.textContent = preview.excerpt || "沒有回傳證據預覽。";
    previewBox.appendChild(previewContent);
    container.appendChild(previewBox);
  }

  function handleEvidenceCompose(btn) {
    var expand = btn.closest ? btn.closest(".queue-expand") : null;
    var rowId = expand ? expand.getAttribute("data-expand-for") : null;
    var row = rowId ? document.getElementById(rowId) : null;
    var fields = evidenceComposeFields(expand);
    var guardMessage = evidenceComposeGuardMessage(fields);
    if (guardMessage) {
      flashLabel(btn, guardMessage, 1500);
      return;
    }
    var payload = {
      state_path: btn.getAttribute("data-state-path") || "",
      stock_id: btn.getAttribute("data-stock") || "",
      action_id: btn.getAttribute("data-action-id") || "",
      status: btn.getAttribute("data-status") || "done",
      note: fields.note,
      reviewer: fields.reviewer,
      evidence_url: fields.evidence_url,
      evidence_summary: fields.evidence_summary,
      overwrite: fields.overwrite
    };
    var resultBox = expand ? expand.querySelector('[data-evidence-compose-result="true"]') : null;
    var evidenceInputs = expand ? expand.querySelectorAll(".queue-evidence input") : [];
    btn.disabled = true;
    postJson("/api/evidence/compose-and-set", payload).then(function (data) {
      updateRowStatus(row, payload.status);
      if (row) { row.setAttribute("data-has-evidence", "true"); }
      if (evidenceInputs.length === 3) {
        evidenceInputs[0].value = data.note || "";
        evidenceInputs[1].value = data.reviewer || "";
        evidenceInputs[2].value = data.evidence_url || "";
      }
      if (resultBox) { renderEvidenceComposeResult(resultBox, data); }
      syncGateFromResponse(data);
      applyQueueFilters();
      flashLabel(btn, "已建立證據 ✓", 1500);
    }, function (err) {
      if (window.console && window.console.error) { window.console.error(err); }
      flashLabel(btn, "建立失敗", 1500);
    }).then(function () {
      btn.disabled = false;
    });
  }

  function initEvidenceCompose() {
    var buttons = document.querySelectorAll('[data-evidence-compose="true"]');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (event) {
        handleEvidenceCompose(event.currentTarget);
      });
    }
  }

  // -- connected live-market dashboard -------------------------------------
  // Served mode exposes one normalized endpoint. The browser never receives a
  // provider API key; it only consumes the same-origin snapshot assembled by
  // dashboard_server.py/live_market.py. Static file mode deliberately skips
  // this block and keeps the clear "start dashboard --serve" notice.
  var liveMarketTimer = null;
  var liveCountdownTimer = null;
  var liveNextRefreshAt = 0;
  var liveRequestInFlight = false;
  var liveSymbolLimit = Math.max(
    1,
    Number(document.body.getAttribute("data-live-symbol-limit")) || 20
  );
  var liveMinimumRefreshSeconds = Math.max(
    5,
    Number(document.body.getAttribute("data-live-min-refresh-seconds")) || 5
  );
  var marketBreadthBaseTtlMs = Math.max(
    60,
    Number(document.body.getAttribute("data-market-breadth-ttl-seconds")) || 300
  ) * 1000;
  var marketBreadthClientMinimumMs = Math.max(
    liveMinimumRefreshSeconds * 1000,
    document.body.getAttribute("data-us-market-api-enabled") === "true"
      ? 5000 : 30000
  );
  var marketBreadthTtlMs = marketBreadthBaseTtlMs;

  function liveText(selector, value) {
    var nodes = document.querySelectorAll(selector);
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = value;
    }
  }

  function liveNumber(value, digits) {
    if (value == null || value === "") { return "--"; }
    var number = Number(value);
    if (!isFinite(number)) { return "--"; }
    return number.toLocaleString("zh-TW", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function livePercent(value) {
    if (value == null || value === "") { return "--"; }
    var number = Number(value);
    if (!isFinite(number)) { return "--"; }
    return (number > 0 ? "+" : "") + liveNumber(number, 2) + "%";
  }

  function liveSignedNumber(value, digits) {
    if (value == null || value === "") { return "--"; }
    var number = Number(value);
    if (!isFinite(number)) { return "--"; }
    return (number > 0 ? "+" : "") + liveNumber(number, digits);
  }

  function liveTone(node, value) {
    if (!node) { return; }
    var number = Number(value);
    node.classList.remove("up", "down");
    if (!isFinite(number) || number === 0) { return; }
    node.classList.add(number > 0 ? "up" : "down");
  }

  function liveSafeUrl(value) {
    try {
      var parsed = new URL(value, window.location.href);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : "";
    } catch (err) {
      return "";
    }
  }

  function marketBreadthContractError(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return "market breadth payload is not an object";
    }
    if (payload.ok !== true) { return "market breadth payload is unavailable"; }
    if (payload.schema_version !== 1) {
      return "market breadth schema_version is not supported";
    }
    if (payload.kind !== "market_breadth_snapshot") {
      return "market breadth kind is invalid";
    }
    var liveFullMode = payload.mode === "LIVE_FULL+OFFICIAL_EOD";
    var expectedStatusByMode = {
      "LIVE_FULL+OFFICIAL_EOD": "LIVE",
      "EOD_FULL+LIVE_PAGE": "EOD",
      "EOD_PARTIAL+LIVE_PAGE": "PARTIAL",
      "STALE_FALLBACK+LIVE_PAGE": "STALE"
    };
    if (!expectedStatusByMode[payload.mode]) {
      return "market breadth mode is invalid";
    }
    if (["LIVE", "EOD", "PARTIAL", "STALE"].indexOf(payload.status) === -1) {
      return "market breadth status is invalid";
    }
    if (payload.status !== expectedStatusByMode[payload.mode]) {
      return "market breadth live mode and status disagree";
    }
    if (payload.status === "EOD" &&
        (payload.cross_market_comparable !== true || payload.session_fresh !== true)) {
      return "market breadth EOD status is not session-complete";
    }
    if (!Array.isArray(payload.market_catalog) ||
        !Array.isArray(payload.full_market) ||
        !Array.isArray(payload.industry_summaries)) {
      return "market breadth arrays are missing";
    }
    if (!payload.coverage ||
        typeof payload.coverage !== "object" ||
        Array.isArray(payload.coverage)) {
      return "market breadth coverage is missing";
    }
    if (!payload.market_catalog.length) {
      return "market breadth catalog is empty";
    }
    if (payload.full_market.length !== payload.market_catalog.length) {
      return "market breadth row count does not match the catalog";
    }
    if (Number(payload.coverage.catalog_total) !== payload.market_catalog.length) {
      return "market breadth coverage does not match the catalog";
    }
    var marketCounts = payload.coverage.market_catalog_counts;
    if (!marketCounts || typeof marketCounts !== "object" ||
        Number(marketCounts.TWSE) <= 0 || Number(marketCounts.TPEX) <= 0) {
      return "market breadth catalog is not complete across TWSE and TPEx";
    }
    if (!payload.source_status ||
        typeof payload.source_status !== "object" ||
        !payload.source_status.alerts ||
        !payload.source_status.disposition_alerts ||
        !payload.source_status.notice_alerts ||
        !payload.source_status.fund_flow) {
      return "market breadth support source status is missing";
    }
    if (liveFullMode) {
      var liveMarketRatios = payload.coverage.live_market_ratios || {};
      var liveQuoteSource = payload.source_status.live_quotes || {};
      var liveMarketStatuses = liveQuoteSource.market_statuses || {};
      if (payload.live_cross_market_comparable !== true ||
          payload.live_session_fresh !== true ||
          payload.coverage.live_full_coverage !== true ||
          Number(payload.coverage.live_ratio) < 0.95 ||
          Number(liveMarketRatios.TWSE) < 0.95 ||
          Number(liveMarketRatios.TPEX) < 0.95 ||
          liveQuoteSource.authoritative !== true ||
          String(liveMarketStatuses.TWSE || "") !== "LIVE" ||
          String(liveMarketStatuses.TPEX || "") !== "LIVE") {
        return "market breadth live coverage is not authoritative";
      }
    }
    var catalogSymbols = {};
    for (var catalogIndex = 0;
         catalogIndex < payload.market_catalog.length;
         catalogIndex++) {
      var catalogRow = payload.market_catalog[catalogIndex];
      var catalogSymbol = catalogRow && typeof catalogRow === "object"
        ? String(catalogRow.symbol || "").trim().toUpperCase() : "";
      if (!catalogSymbol || catalogSymbols[catalogSymbol]) {
        return "market breadth catalog symbols are invalid";
      }
      catalogSymbols[catalogSymbol] = true;
    }
    var marketSymbols = {};
    for (var marketIndex = 0; marketIndex < payload.full_market.length; marketIndex++) {
      var marketRow = payload.full_market[marketIndex];
      var marketSymbol = marketRow && typeof marketRow === "object"
        ? String(marketRow.symbol || "").trim().toUpperCase() : "";
      if (!marketSymbol || marketSymbols[marketSymbol] || !catalogSymbols[marketSymbol]) {
        return "market breadth market symbols are invalid";
      }
      marketSymbols[marketSymbol] = true;
    }
    return "";
  }

  function marketBreadthRetryDelay(failures) {
    return Math.min(60, 5 * Math.pow(2, Math.max(0, Number(failures) - 1)));
  }

  function marketBreadthRefreshIntervalMs(payload) {
    var liveEnabled = Boolean(payload && payload.live_overlay_enabled);
    if (!liveEnabled) { return marketBreadthBaseTtlMs; }
    var seconds = Number(payload && payload.refresh_after_seconds);
    if (!isFinite(seconds) || seconds < 5) { seconds = 5; }
    return Math.min(
      marketBreadthBaseTtlMs,
      Math.max(marketBreadthClientMinimumMs, seconds * 1000)
    );
  }

  function marketBreadthTaipeiSessionKey(nowMs) {
    var date = new Date(nowMs == null ? Date.now() : nowMs);
    var values = {};
    try {
      var formatter = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Taipei",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23"
      });
      var parts = formatter.formatToParts(date);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type !== "literal") { values[parts[i].type] = parts[i].value; }
      }
    } catch (err) {
      values.year = String(date.getFullYear());
      values.month = String(date.getMonth() + 1).padStart(2, "0");
      values.day = String(date.getDate()).padStart(2, "0");
      values.hour = String(date.getHours()).padStart(2, "0");
      values.minute = String(date.getMinutes()).padStart(2, "0");
    }
    var minutes = Number(values.hour || 0) * 60 + Number(values.minute || 0);
    var phase = minutes < 540 ? "preopen" : minutes < 840 ? "session" : "postclose";
    return [values.year, values.month, values.day].join("-") + ":" + phase;
  }

  function marketBreadthNeedsRefresh(force, nowMs) {
    if (force) { return true; }
    if (marketBreadthState !== "ready") { return true; }
    var now = nowMs == null ? Date.now() : Number(nowMs);
    if (!marketBreadthLastLoadedAt ||
        now - marketBreadthLastLoadedAt >= marketBreadthTtlMs) {
      return true;
    }
    return marketBreadthLoadedSessionKey !== marketBreadthTaipeiSessionKey(now);
  }

  function scheduleMarketBreadthRefresh() {
    if (marketBreadthRefreshTimer) {
      window.clearTimeout(marketBreadthRefreshTimer);
      marketBreadthRefreshTimer = null;
    }
    if (document.hidden || marketBreadthState !== "ready") { return; }
    var elapsed = Math.max(0, Date.now() - marketBreadthLastLoadedAt);
    var wait = Math.max(1000, marketBreadthTtlMs - elapsed);
    marketBreadthRefreshTimer = window.setTimeout(function () {
      marketBreadthRefreshTimer = null;
      loadMarketBreadth(false);
    }, wait);
  }

  function scheduleMarketBreadthRetry() {
    if (marketBreadthRetryTimer || document.hidden) { return; }
    var delay = marketBreadthRetryDelay(marketBreadthFailures);
    marketBreadthRetryTimer = window.setTimeout(function () {
      marketBreadthRetryTimer = null;
      loadMarketBreadth(false);
    }, delay * 1000);
  }

  function loadMarketBreadth(force) {
    if (!window.fetch || marketBreadthState === "loading") { return; }
    if (!marketBreadthNeedsRefresh(Boolean(force), Date.now())) {
      scheduleMarketBreadthRefresh();
      return;
    }
    if (marketBreadthRefreshTimer) {
      window.clearTimeout(marketBreadthRefreshTimer);
      marketBreadthRefreshTimer = null;
    }
    marketBreadthState = "loading";
    var scope = document.querySelector('[data-screener-scope-status="true"]');
    if (scope && screenerUniverseMode !== "US") {
      scope.textContent = "載入全市場資料…";
    }
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = controller ? window.setTimeout(function () { controller.abort(); }, 30000) : null;
    var options = { cache: "no-store", headers: { "Accept": "application/json" } };
    if (controller) { options.signal = controller.signal; }
    window.fetch("/api/market/breadth", options)
      .then(function (response) {
        if (!response.ok) { throw new Error("market breadth API HTTP " + response.status); }
        return response.json();
      })
      .then(function (payload) {
        var contractError = marketBreadthContractError(payload);
        if (contractError) { throw new Error(contractError); }
        var industryRows = payload.industry_summaries;
        marketBreadthIndustryRows = industryRows;
        if (!screenerLoadBreadth(payload)) {
          throw new Error("market breadth payload could not be normalized");
        }
        if (industryRows.length) {
          liveRenderIndustrySummaries(
            industryRows,
            payload.status || payload.mode || screenerBreadthStatus
          );
          if (screenerUniverseMode !== "US") {
            populateScreenerIndustriesFromSummaries(industryRows);
          }
        }
        marketBreadthState = "ready";
        marketBreadthFailures = 0;
        marketBreadthTtlMs = marketBreadthRefreshIntervalMs(payload);
        marketBreadthLastLoadedAt = Date.now();
        marketBreadthLoadedSessionKey = marketBreadthTaipeiSessionKey(
          marketBreadthLastLoadedAt
        );
        if (marketBreadthRetryTimer) {
          window.clearTimeout(marketBreadthRetryTimer);
          marketBreadthRetryTimer = null;
        }
        scheduleMarketBreadthRefresh();
        liveBreadthRefreshPending = true;
        if (!liveRequestInFlight && !document.hidden) {
          liveBreadthRefreshPending = false;
          liveFetchSnapshot();
        }
      })
      .catch(function (error) {
        marketBreadthState = "idle";
        marketBreadthFailures += 1;
        marketBreadthIndustryRows = [];
        var status = document.querySelector('[data-screener-scope-status="true"]');
        if (status && screenerUniverseMode !== "US") {
          status.textContent = "研究池範圍 · 全市場資料未載入";
          status.setAttribute("title", String(error.message || error));
        }
        var industryStatus = document.querySelector('[data-industry-map-status="true"]');
        if (industryStatus) {
          industryStatus.textContent = "研究池產業 · 全市場資料未載入";
          industryStatus.setAttribute("title", String(error.message || error));
        }
        scheduleMarketBreadthRetry();
      })
      .then(function () {
        if (timeout) { window.clearTimeout(timeout); }
      });
  }

  function liveSymbols() {
    var symbols = [];
    var seen = {};
    var groups = [
      document.querySelectorAll('[data-live-breadth-row="true"]'),
      document.querySelectorAll("[data-stock-key]")
    ];
    for (var groupIndex = 0; groupIndex < groups.length; groupIndex++) {
      var rows = groups[groupIndex];
      for (var rowIndex = 0; rowIndex < rows.length; rowIndex++) {
        if (rows[rowIndex].hidden) { continue; }
        if (String(
          rows[rowIndex].getAttribute("data-live-market") || ""
        ).toUpperCase() === "US") {
          continue;
        }
        var symbol = (rows[rowIndex].getAttribute("data-stock-key") || "")
          .trim().toUpperCase();
        if (symbol && !seen[symbol]) {
          seen[symbol] = true;
          symbols.push(symbol);
          if (symbols.length >= liveSymbolLimit) { return symbols; }
        }
      }
    }
    return symbols.slice(0, liveSymbolLimit);
  }

  function liveQuoteMap(snapshot) {
    var rows = Array.isArray(snapshot.quotes) ? snapshot.quotes : [];
    var mapped = {};
    for (var i = 0; i < rows.length; i++) {
      var status = String((rows[i] || {}).status || "").toUpperCase();
      if (rows[i] && rows[i].symbol && (status === "LIVE" || status === "EOD")) {
        mapped[String(rows[i].symbol).toUpperCase()] = rows[i];
      }
    }
    return mapped;
  }

  function liveIndex(snapshot, symbol) {
    var rows = Array.isArray(snapshot.indices) ? snapshot.indices : [];
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i].symbol || "") === symbol) { return rows[i]; }
    }
    return null;
  }

  function liveUpdateConnection(snapshot) {
    var bar = document.querySelector('[data-live-connection="true"]');
    if (!bar) { return; }
    var status = String(snapshot.status || "UNAVAILABLE").toUpperCase();
    var provider = snapshot.provider || {};
    var quoteState = (snapshot.source_status || {}).quotes || {};
    var missingSymbols = Array.isArray(snapshot.missing_symbols)
      ? snapshot.missing_symbols : [];
    var errorCount = Array.isArray(snapshot.errors) ? snapshot.errors.length : 0;
    var quotePartial = Boolean(quoteState.partial) || missingSymbols.length > 0;
    bar.classList.remove(
      "live-connection-loading", "live-connection-live", "live-connection-eod",
      "live-connection-error"
    );
    bar.classList.add(
      status === "LIVE" ? "live-connection-live" :
      status === "EOD" ? "live-connection-eod" : "live-connection-error"
    );
    var title = bar.querySelector('[data-live-connection-title="true"]');
    var detail = bar.querySelector('[data-live-connection-detail="true"]');
    if (title) {
      title.textContent = quotePartial ? "部分自選行情未取得" :
        status === "LIVE" ? "市場連線中" :
        status === "EOD" ? "今日收盤資料已連線" :
        status === "STALE" ? "來源已過期" : "市場來源暫時不可用";
    }
    if (detail) {
      var generated = String(snapshot.generated_at || "").replace("T", " ").slice(0, 19);
      detail.textContent = (provider.label || "來源未標示") + " · " + generated +
        " · " + (provider.notice || "") +
        (missingSymbols.length ? " · 缺少 " + missingSymbols.join(", ") : "") +
        (errorCount ? " · " + errorCount + " 個來源錯誤" : "");
    }
    liveText('[data-live-provider-label="true"]', provider.label || "市場資料");
    liveText('[data-live-provider-mode="true"]', provider.mode || status);
    var sideDot = document.querySelector('[data-live-dot="true"]');
    if (sideDot) { sideDot.classList.toggle("is-live", status === "LIVE"); }
    var badge = document.querySelector('[data-live-market-badge="true"]');
    if (badge) {
      badge.textContent = status;
      badge.className = "ui-pill " + (status === "LIVE" ? "ui-pill-ok" :
        status === "EOD" ? "ui-pill-info" : "ui-pill-warn");
      badge.title = (provider.label || "") + "；" + (provider.notice || "");
    }
  }

  function liveUpdateHero(snapshot) {
    var market = snapshot.market || {};
    liveText('[data-live-regime="true"]', market.regime || "行情資料不足");
    liveText('[data-live-posture="true"]', market.posture || "等待市場資料。");
    liveText('[data-live-as-of="true"]', String(market.as_of || snapshot.generated_at || "")
      .replace("T", " ").slice(0, 19));
    liveText('[data-live-gate="true"]', market.status || snapshot.status || "UNAVAILABLE");
    var temperature = market.temperature == null ? NaN : Number(market.temperature);
    var gauge = document.querySelector('[data-live-gauge="true"]');
    if (gauge && isFinite(temperature)) {
      gauge.style.setProperty("--gauge", String(Math.max(0, Math.min(100, temperature))));
      gauge.setAttribute("aria-label", "市場溫度 " + liveNumber(temperature, 0) + " 分");
    } else if (gauge) {
      gauge.style.setProperty("--gauge", "0");
      gauge.setAttribute("aria-label", "市場溫度資料不可用");
    }
    liveText('[data-live-temperature="true"]', isFinite(temperature) ? liveNumber(temperature, 0) : "--");
    liveText('[data-live-methodology="true"]', market.methodology || "市場溫度資料不足");
    var mode = document.querySelector('[data-live-mode-badge="true"]');
    if (mode) {
      mode.textContent = "";
      var pill = document.createElement("span");
      pill.className = "ui-pill " + (snapshot.status === "LIVE" ? "ui-pill-ok" :
        snapshot.status === "EOD" ? "ui-pill-info" : "ui-pill-warn");
      pill.textContent = (snapshot.provider && snapshot.provider.mode) || snapshot.status || "LIVE";
      mode.appendChild(pill);
    }
  }

  function liveUpdateMetric(key, label, value, detail, change) {
    var metric = document.querySelector('[data-live-metric="' + key + '"]');
    if (!metric) { return; }
    var labelNode = metric.querySelector('[data-live-metric-label="true"]');
    var valueNode = metric.querySelector('[data-live-metric-value="true"]');
    var detailNode = metric.querySelector('[data-live-metric-detail="true"]');
    if (labelNode) { labelNode.textContent = label; }
    if (valueNode) {
      valueNode.textContent = value;
      liveTone(valueNode, change);
    }
    if (detailNode) { detailNode.textContent = detail; }
  }

  function liveUpdateOverviewMetrics(snapshot) {
    var taiex = liveIndex(snapshot, "t00");
    var otc = liveIndex(snapshot, "o00");
    var missingSymbols = Array.isArray(snapshot.missing_symbols)
      ? snapshot.missing_symbols : [];
    if (taiex) {
      liveUpdateMetric(
        "taiex", "加權指數", liveNumber(taiex.price, 2),
        livePercent(taiex.change_percent) + " · " + (taiex.status || ""), taiex.change_percent
      );
    } else {
      liveUpdateMetric("taiex", "加權指數", "--", "目前行情來源未提供", null);
    }
    if (otc) {
      liveUpdateMetric(
        "otc", "櫃買指數", liveNumber(otc.price, 2),
        livePercent(otc.change_percent) + " · " + (otc.status || ""), otc.change_percent
      );
    } else {
      liveUpdateMetric("otc", "櫃買指數", "--", "目前行情來源未提供", null);
    }
    var sourceStatuses = snapshot.source_status || {};
    var available = 0;
    var partial = 0;
    var keys = ["quotes", "news", "alerts", "fund_flow"];
    for (var i = 0; i < keys.length; i++) {
      var sourceState = sourceStatuses[keys[i]] || {};
      var state = String(sourceState.status || "");
      if (state && state !== "UNAVAILABLE" && state !== "STALE") {
        if (sourceState.partial === true || state === "PARTIAL") {
          partial += 1;
        } else {
          available += 1;
        }
      }
    }
    liveUpdateMetric(
      "status", "連線狀態", snapshot.status || "UNAVAILABLE",
       available + "/4 資料域完整" +
        (partial ? " · " + partial + " 部分" : "") +
        (missingSymbols.length ? " · 缺 " + missingSymbols.length + " 檔行情" : ""),
      null
    );
    var alertCount = Array.isArray(snapshot.active_watchlist_alerts)
      ? snapshot.active_watchlist_alerts.length : 0;
    var newsCount = Array.isArray(snapshot.news) ? snapshot.news.length : 0;
    liveUpdateMetric(
      "news", "消息／風險", String(newsCount),
      alertCount + " 個自選股注意／處置", null
    );
  }

  function liveAlertMap(snapshot) {
    if (!sourceStatusAuthoritative(
      ((snapshot.source_status || {}).alerts || {}),
      ["EOD", "FRESH", "LIVE"]
    )) {
      return {};
    }
    var rows = Array.isArray(snapshot.active_watchlist_alerts)
      ? snapshot.active_watchlist_alerts : [];
    var mapped = {};
    for (var i = 0; i < rows.length; i++) {
      var symbol = String(rows[i].symbol || "").toUpperCase();
      if (!mapped[symbol]) { mapped[symbol] = []; }
      mapped[symbol].push(rows[i]);
    }
    return mapped;
  }

  function screenerApplyLiveQuote(row, quote, stockAlerts) {
    screenerRestoreBreadthBaseline(row);
    stockAlerts = Array.isArray(stockAlerts) ? stockAlerts : [];
    if (!quote && !stockAlerts.length) { return row; }
    if (quote && typeof quote === "object") {
      row.price = screenerFinite(quote.price);
      var quoteReference = screenerFinite(screenerFirstValue(
        quote, ["reference_price", "previous_close", "prev_close"], null
      ));
      if (quoteReference !== null) { row.referencePrice = quoteReference; }
      row.change = screenerFinite(screenerFirstValue(
        quote, ["change", "price_change"], null
      ));
      row.changePercent = screenerFinite(screenerFirstValue(
        quote, ["change_percent", "change_pct", "percent_change"], null
      ));
      var quoteVolume = screenerFinite(screenerFirstValue(
        quote, ["volume", "trade_volume"], null
      ));
      var quoteTradeValue = screenerFinite(screenerFirstValue(
        quote, ["trade_value", "turnover"], null
      ));
      if (quoteVolume !== null) { row.volume = quoteVolume; }
      if (quoteTradeValue !== null) { row.tradeValue = quoteTradeValue; }
      row.status = String(quote.status || row.status || "UNAVAILABLE").toUpperCase();
      row.sourceEventTime = String(screenerFirstValue(
        quote, ["source_event_time", "event_time", "as_of"], row.sourceEventTime
      ));
      row.tags = row.tags.filter(function (tag) {
        return tag !== "bull" && tag !== "bear";
      });
      if (row.changePercent !== null && row.changePercent !== 0) {
        row.tags.push(row.changePercent > 0 ? "bull" : "bear");
      }
    }
    if (stockAlerts.length) {
      var firstAlert = stockAlerts[0] || {};
      row.disposition = {
        type: String(firstAlert.type || "") === "disposition"
          ? "disposition" : "notice",
        reason: String(firstAlert.reason || firstAlert.period || "官方名單命中")
      };
      if (row.tags.indexOf("disposition") === -1) {
        row.tags.push("disposition");
      }
    }
    var reasons = [];
    if (quote && row.changePercent !== null) {
      reasons.push(
        row.changePercent > 0
          ? "當日上漲 " + livePercent(row.changePercent)
          : row.changePercent < 0
            ? "當日下跌 " + livePercent(row.changePercent)
            : "當日平盤 0.00%"
      );
    }
    if (row.disposition) {
      reasons.push(
        (String(row.disposition.type || "") === "disposition" ? "處置" : "注意") +
        "：" + String(row.disposition.reason || row.disposition.period || "官方名單命中")
      );
    }
    if (!reasons.length && row.industry && row.industry !== "未分類") {
      reasons.push("產業：" + row.industry);
    }
    if (reasons.length) { row.reasonAll = reasons.join("｜"); }
    return row;
  }

  function liveSyncBreadthRows(quotes, alerts) {
    if (screenerUniverseMode === "US") { return true; }
    if (!screenerBreadthRows.length) { return false; }
    for (var i = 0; i < screenerBreadthRows.length; i++) {
      var symbol = String(screenerBreadthRows[i].symbol || "").toUpperCase();
      screenerApplyLiveQuote(
        screenerBreadthRows[i],
        quotes[symbol] || null,
        alerts[symbol] || []
      );
    }
    renderBreadthScreener();
    return true;
  }

  function liveUpdateStocks(snapshot) {
    var quoteSourceStatus = ((snapshot.source_status || {}).quotes || {});
    var quotesAuthoritative = sourceStatusAuthoritative(
      quoteSourceStatus,
      ["EOD", "LIVE"]
    );
    var quotes = liveQuoteMap(snapshot);
    var alerts = liveAlertMap(snapshot);
    var breadthRendered = liveSyncBreadthRows(quotes, alerts);
    var rows = document.querySelectorAll('[data-screener-row="true"]');
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].getAttribute("data-live-breadth-row") === "true") {
        continue;
      }
      var symbol = String(rows[i].getAttribute("data-stock-key") || "").toUpperCase();
      var baseTags = rows[i].getAttribute("data-base-screener-tags") || "";
      rows[i].setAttribute("data-screener-tags", baseTags);
      var reasonKeys = ["bull", "bear", "disposition"];
      for (var reasonIndex = 0; reasonIndex < reasonKeys.length; reasonIndex++) {
        var reasonKey = reasonKeys[reasonIndex];
        var baseReason = rows[i].getAttribute("data-base-reason-" + reasonKey);
        if (baseReason == null) {
          rows[i].removeAttribute("data-reason-" + reasonKey);
        } else {
          rows[i].setAttribute("data-reason-" + reasonKey, baseReason);
        }
      }
      rows[i].setAttribute(
        "data-reason-all",
        rows[i].getAttribute("data-base-reason-all") || ""
      );
      var oldAlertTag = rows[i].querySelector('[data-live-alert-tag="true"]');
      if (oldAlertTag) { oldAlertTag.remove(); }
      var oldTrendTag = rows[i].querySelector('[data-live-trend-tag="true"]');
      if (oldTrendTag) { oldTrendTag.remove(); }
      var quote = quotes[symbol];
      var priceNode = rows[i].querySelector('[data-live-stock-price="true"]');
      var changeNode = rows[i].querySelector('[data-live-stock-change="true"]');
      if (!quote && !quotesAuthoritative) {
        var unavailableQuoteStatus = String(
          quoteSourceStatus.status || "UNAVAILABLE"
        ).toUpperCase();
        if (priceNode) {
          var basePriceText = priceNode.getAttribute("data-base-price-text");
          priceNode.textContent = (basePriceText || "即時行情不可用") +
            " · 即時來源 " + screenerStatusLabel(unavailableQuoteStatus);
        }
        if (changeNode) {
          var baseChangeText = changeNode.getAttribute("data-base-change-text");
          var baseChangeValue = changeNode.getAttribute("data-base-change-value");
          changeNode.textContent = baseChangeText == null ? "--" : baseChangeText;
          liveTone(changeNode, baseChangeValue === "" ? null : baseChangeValue);
        }
      } else if (quote) {
        if (priceNode) {
          priceNode.textContent = quote.price == null
            ? "現價未提供 · " + (quote.status || "UNAVAILABLE")
            : "現價 " + liveNumber(quote.price, 2) + " · " + (quote.status || "");
        }
        if (changeNode) {
          changeNode.textContent = livePercent(quote.change_percent);
          liveTone(changeNode, quote.change_percent);
        }
        var currentChange = quote.change_percent == null
          ? NaN : Number(quote.change_percent);
        if (isFinite(currentChange) && currentChange !== 0) {
          var trendKey = currentChange > 0 ? "bull" : "bear";
          var currentTags = " " + (rows[i].getAttribute("data-screener-tags") || "") + " ";
          if (rows[i].getAttribute("data-live-breadth-row") === "true") {
            var tagParts = currentTags.trim().split(/\s+/).filter(function (tagPart) {
              return tagPart && tagPart !== "bull" && tagPart !== "bear";
            });
            currentTags = " " + tagParts.join(" ") + " ";
            rows[i].setAttribute("data-screener-tags", tagParts.join(" "));
            rows[i].removeAttribute("data-reason-bull");
            rows[i].removeAttribute("data-reason-bear");
            rows[i].setAttribute(
              "data-reason-all",
              rows[i].getAttribute("data-reason-disposition") || ""
            );
            var baseTrendBadges = rows[i].querySelectorAll(
              '[data-screener-tag="bull"], [data-screener-tag="bear"]'
            );
            for (var badgeIndex = 0; badgeIndex < baseTrendBadges.length; badgeIndex++) {
              baseTrendBadges[badgeIndex].remove();
            }
          }
          var trendAlreadyPresent = currentTags.indexOf(" " + trendKey + " ") !== -1;
          if (!trendAlreadyPresent) {
            rows[i].setAttribute(
              "data-screener-tags",
              (currentTags + " " + trendKey).trim()
            );
          }
          var trendLabel = (quote.status === "LIVE" ? "即時行情 " : "本日收盤 ") +
            livePercent(currentChange);
          var storedReason = rows[i].getAttribute("data-reason-" + trendKey) || "";
          rows[i].setAttribute(
            "data-reason-" + trendKey,
            storedReason ? storedReason + "｜" + trendLabel : trendLabel
          );
          var allReason = rows[i].getAttribute("data-reason-all") || "";
          rows[i].setAttribute(
            "data-reason-all",
            allReason ? allReason + "｜" + trendLabel : trendLabel
          );
          var liveTagBox = rows[i].querySelector('[data-live-stock-tags="true"]');
          if (liveTagBox && !trendAlreadyPresent) {
            var trendTag = document.createElement("span");
            trendTag.className = "ui-pill " +
              (trendKey === "bull" ? "ui-pill-ok" : "ui-pill-blocked");
            trendTag.setAttribute("data-live-trend-tag", "true");
            trendTag.textContent = trendKey === "bull" ? "當日上漲" : "當日下跌";
            liveTagBox.appendChild(trendTag);
          }
        } else if (isFinite(currentChange) &&
                   rows[i].getAttribute("data-live-breadth-row") === "true") {
          var flatTags = (rows[i].getAttribute("data-screener-tags") || "")
            .split(/\s+/).filter(function (tagPart) {
              return tagPart && tagPart !== "bull" && tagPart !== "bear";
            });
          rows[i].setAttribute("data-screener-tags", flatTags.join(" "));
          rows[i].removeAttribute("data-reason-bull");
          rows[i].removeAttribute("data-reason-bear");
          var flatReason = rows[i].getAttribute("data-reason-disposition") || "";
          rows[i].setAttribute(
            "data-reason-all",
            flatReason ? flatReason + "｜即時行情 0.00%" : "即時行情 0.00%"
          );
          var flatBadges = rows[i].querySelectorAll(
            '[data-screener-tag="bull"], [data-screener-tag="bear"]'
          );
          for (var flatIndex = 0; flatIndex < flatBadges.length; flatIndex++) {
            flatBadges[flatIndex].remove();
          }
        }
      } else {
        if (rows[i].getAttribute("data-live-breadth-row") !== "true") {
          if (priceNode) { priceNode.textContent = "現價未提供"; }
          if (changeNode) {
            changeNode.textContent = "--";
            liveTone(changeNode, null);
          }
        }
      }
      var stockAlerts = alerts[symbol] || [];
      if (stockAlerts.length) {
        var tags = " " + (rows[i].getAttribute("data-screener-tags") || "") + " ";
        if (tags.indexOf(" disposition ") === -1) {
          rows[i].setAttribute("data-screener-tags", (tags + " disposition").trim());
        }
        var firstAlert = stockAlerts[0] || {};
        rows[i].setAttribute(
          "data-reason-disposition",
          (firstAlert.type === "disposition" ? "處置" : "注意") + "：" +
          (firstAlert.reason || firstAlert.period || "官方名單命中")
        );
        var tagBox = rows[i].querySelector('[data-live-stock-tags="true"]');
        if (tagBox &&
            !tagBox.querySelector(
              '[data-live-alert-tag="true"], [data-screener-tag="disposition"]'
            )) {
          var tag = document.createElement("span");
          tag.className = "ui-pill ui-pill-warn";
          tag.setAttribute("data-live-alert-tag", "true");
          tag.textContent = firstAlert.type === "disposition" ? "處置" : "注意";
          tagBox.appendChild(tag);
        }
      }
    }
    var watchRows = document.querySelectorAll("[data-live-watch-symbol]");
    for (var j = 0; j < watchRows.length; j++) {
      var watchSymbol = String(watchRows[j].getAttribute("data-live-watch-symbol") || "").toUpperCase();
      var watchQuote = quotes[watchSymbol];
      var watchPrice = watchRows[j].querySelector('[data-live-watch-price="true"]');
      var watchChange = watchRows[j].querySelector('[data-live-watch-change="true"]');
      if (watchQuote && watchPrice) { watchPrice.textContent = liveNumber(watchQuote.price, 2); }
      if (!watchQuote && watchPrice) { watchPrice.textContent = "--"; }
      if (watchQuote && watchChange) {
        watchChange.textContent = livePercent(watchQuote.change_percent);
        liveTone(watchChange, watchQuote.change_percent);
      }
      if (!watchQuote && watchChange) {
        watchChange.textContent = "--";
        liveTone(watchChange, null);
      }
    }
    var screenerMode = document.querySelector('[data-live-screener-mode="true"]');
    if (screenerMode) {
      screenerMode.textContent = "";
      var screenerPill = document.createElement("span");
      screenerPill.className = "ui-pill " + (
        screenerUniverseMode === "US"
          ? "ui-pill-info"
          : snapshot.status === "LIVE" ? "ui-pill-ok" :
            snapshot.status === "EOD" ? "ui-pill-info" : "ui-pill-warn"
      );
      screenerPill.textContent = screenerUniverseMode === "US"
        ? "美股官方名錄 / FINRA EOD"
        : (snapshot.provider && snapshot.provider.mode) ||
          snapshot.status || "UNAVAILABLE";
      screenerMode.appendChild(screenerPill);
    }
    if (!breadthRendered) { applyScreenerFilters(); }
  }

  function liveNewsArticle(row, compact) {
    var article = document.createElement("article");
    article.className = compact ? "desk-news-item" : "intel-news-card";
    if (!compact) {
      article.setAttribute("data-intel-news", "true");
      var mapped = Boolean(
        row.symbol ||
        (Array.isArray(row.matched_stock_ids) && row.matched_stock_ids.length) ||
        (Array.isArray(row.matched_categories) && row.matched_categories.length)
      );
      article.setAttribute("data-intel-mapped", mapped ? "true" : "false");
    }
    var meta = document.createElement("div");
    meta.className = compact ? "desk-news-meta" : "intel-news-meta";
    var source = document.createElement("span");
    source.textContent = row.source || "官方消息";
    var published = document.createElement("time");
    published.textContent = String(row.published_at || "").replace("T", " ").slice(0, 16);
    meta.appendChild(source);
    meta.appendChild(published);
    article.appendChild(meta);
    var heading = document.createElement("h3");
    var href = liveSafeUrl(row.url || "");
    if (href) {
      var link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = row.title || "未命名事件";
      heading.appendChild(link);
    } else {
      heading.textContent = row.title || "未命名事件";
    }
    article.appendChild(heading);
    var summary = document.createElement("p");
    summary.textContent = row.summary || (row.kind === "material_announcement" ? "公司重大訊息" : "交易所公告");
    article.appendChild(summary);
    if (!compact) {
      var tags = document.createElement("div");
      tags.className = "intel-tags";
      var tag = document.createElement("span");
      tag.className = "ui-pill ui-pill-info";
      tag.textContent = row.symbol || (row.kind === "material_announcement" ? "重大訊息" : "交易所");
      tags.appendChild(tag);
      article.appendChild(tags);
      var add = document.createElement("button");
      add.type = "button";
      add.className = "desk-link";
      add.textContent = "＋ 加到市場筆記";
      add.addEventListener("click", function () {
        var note = document.querySelector('[data-market-note="true"]');
        if (!note) { return; }
        var line = (row.published_at || "").slice(0, 10) + "｜" + (row.title || "");
        note.value = (note.value ? note.value.replace(/\s+$/, "") + "\n" : "") + line;
        note.dispatchEvent(new Event("input", { bubbles: true }));
        note.focus();
      });
      article.appendChild(add);
    }
    return article;
  }

  function liveNewsNextVisibleCount(total, current, increment) {
    var safeTotal = Math.max(0, Number(total) || 0);
    var safeCurrent = Math.max(0, Number(current) || 0);
    var batch = Math.max(1, Number(increment) || 12);
    return Math.min(safeTotal, Math.max(12, safeCurrent + batch));
  }

  function liveNewsRowsSignature(rows) {
    if (!rows.length) { return "0"; }
    var first = rows[0] || {};
    var last = rows[rows.length - 1] || {};
    return [
      rows.length,
      first.published_at || "",
      first.title || "",
      last.published_at || "",
      last.title || ""
    ].join("|");
  }

  function liveNewsMoreButton(grid) {
    var section = grid && grid.closest ? grid.closest(".intel-news") : null;
    if (!section) { return null; }
    var button = section.querySelector('[data-intel-news-more="true"]');
    if (button) { return button; }
    var controls = document.createElement("div");
    controls.className = "intel-news-more";
    button = document.createElement("button");
    button.type = "button";
    button.className = "desk-link";
    button.setAttribute("data-intel-news-more", "true");
    button.addEventListener("click", function () {
      liveIntelligenceNewsVisible = liveNewsNextVisibleCount(
        liveIntelligenceNewsRows.length,
        liveIntelligenceNewsVisible,
        12
      );
      liveRenderIntelligenceNews();
    });
    controls.appendChild(button);
    section.appendChild(controls);
    return button;
  }

  function liveRenderIntelligenceNews() {
    var grid = document.querySelector('[data-live-intelligence-news="true"]');
    if (!grid) { return; }
    grid.textContent = "";
    var limit = Math.min(
      liveIntelligenceNewsRows.length,
      Math.max(12, liveIntelligenceNewsVisible)
    );
    for (var i = 0; i < limit; i++) {
      grid.appendChild(liveNewsArticle(liveIntelligenceNewsRows[i], false));
    }
    if (!liveIntelligenceNewsRows.length) {
      var empty = document.createElement("p");
      empty.className = "desk-empty";
      empty.textContent = "目前沒有通過來源與時間檢查的最新消息。";
      grid.appendChild(empty);
    }
    applyIntelNewsFilter();
    var button = liveNewsMoreButton(grid);
    if (button) {
      button.hidden = limit >= liveIntelligenceNewsRows.length;
      button.textContent = "顯示更多（已載入 " + limit + " / " +
        liveIntelligenceNewsRows.length + "）";
    }
  }

  function liveUpdateNews(snapshot) {
    var news = Array.isArray(snapshot.news) ? snapshot.news : [];
    var overview = document.querySelector('[data-live-overview-news="true"]');
    if (overview) {
      overview.textContent = "";
      for (var i = 0; i < Math.min(4, news.length); i++) {
        overview.appendChild(liveNewsArticle(news[i], true));
      }
      if (!news.length) {
        var empty = document.createElement("p");
        empty.className = "desk-empty";
        empty.textContent = "目前沒有通過來源與時間檢查的最新消息。";
        overview.appendChild(empty);
      }
    }
    var intelligence = document.querySelector('[data-live-intelligence-news="true"]');
    if (intelligence) {
      var signature = liveNewsRowsSignature(news);
      if (signature !== liveIntelligenceNewsSignature) {
        liveIntelligenceNewsVisible = liveIntelligenceNewsSignature
          ? Math.min(news.length, Math.max(12, liveIntelligenceNewsVisible))
          : Math.min(news.length, 12);
        liveIntelligenceNewsSignature = signature;
      }
      liveIntelligenceNewsRows = news.slice();
      liveRenderIntelligenceNews();
    }
    liveText(
      '[data-live-intelligence-as-of="true"]',
      String((((snapshot.source_status || {}).news || {}).latest_event_at) ||
        snapshot.generated_at || "").replace("T", " ").slice(0, 19)
    );
    liveText('[data-live-note-regime="true"]', (snapshot.market || {}).regime || "行情資料不足");
    liveText(
      '[data-live-note-as-of="true"]',
      String((snapshot.market || {}).as_of || snapshot.generated_at || "")
        .replace("T", " ").slice(0, 19)
    );
    var mode = document.querySelector('[data-live-intelligence-mode="true"]');
    if (mode) {
      mode.textContent = "";
      var pill = document.createElement("span");
      pill.className = "ui-pill " + (snapshot.status === "LIVE" ? "ui-pill-ok" :
        snapshot.status === "EOD" ? "ui-pill-info" : "ui-pill-warn");
      pill.textContent = snapshot.status || "UNAVAILABLE";
      mode.appendChild(pill);
    }
  }

  function liveIndustrySummaryRows(snapshot) {
    return screenerPayloadRows(
      snapshot.industry_summaries || snapshot.industry_summary || snapshot.sector_summaries
    );
  }

  function liveAggregateBreadthIndustries() {
    var grouped = {};
    for (var i = 0; i < screenerBreadthRows.length; i++) {
      var row = screenerBreadthRows[i];
      var category = row.industry || "未分類";
      if (!grouped[category]) {
        grouped[category] = {
          industry_name: category,
          industry_code: row.industryCode || "",
          stock_count: 0,
          quoted_count: 0,
          advance_count: 0,
          decline_count: 0,
          flat_count: 0,
          change_total: 0,
          total_trade_value: 0,
          institutional_net: 0,
          institutional_count: 0
        };
      }
      var group = grouped[category];
      group.stock_count += 1;
      if (row.changePercent !== null) {
        group.quoted_count += 1;
        group.change_total += row.changePercent;
        if (row.changePercent > 0) { group.advance_count += 1; }
        else if (row.changePercent < 0) { group.decline_count += 1; }
        else { group.flat_count += 1; }
      }
      if (row.tradeValue !== null) { group.total_trade_value += row.tradeValue; }
      if (row.institutionalNet !== null) {
        group.institutional_net += row.institutionalNet;
        group.institutional_count += 1;
      }
    }
    return Object.keys(grouped).map(function (key) {
      var group = grouped[key];
      group.average_change_percent = group.quoted_count
        ? group.change_total / group.quoted_count : null;
      group.breadth_percent = group.quoted_count
        ? (group.advance_count - group.decline_count) / group.quoted_count * 100 : null;
      group.temperature = group.average_change_percent === null
        ? null : Math.max(0, Math.min(100, 50 + group.average_change_percent * 8));
      if (!group.institutional_count) { group.institutional_net = null; }
      return group;
    });
  }

  function liveNormalizeIndustrySummary(raw) {
    var name = String(screenerFirstValue(
      raw, ["industry_name", "category", "industry", "sector"], "未分類"
    )).trim() || "未分類";
    var average = screenerFinite(screenerFirstValue(
      raw, ["average_change_percent", "average_return_1d", "change_percent"], null
    ));
    var temperature = screenerFinite(screenerFirstValue(
      raw, ["temperature", "score", "sentiment_score"], null
    ));
    if (temperature === null && average !== null) {
      temperature = Math.max(0, Math.min(100, 50 + average * 8));
    }
    return {
      name: name,
      code: String(screenerFirstValue(raw, ["industry_code", "sector_code"], "")),
      stockCount: screenerFinite(screenerFirstValue(raw, ["stock_count", "catalog_count"], null)),
      quotedCount: screenerFinite(screenerFirstValue(raw, ["quoted_count", "quote_count"], null)),
      advanceCount: screenerFinite(screenerFirstValue(raw, ["advance_count", "up_count"], null)),
      declineCount: screenerFinite(screenerFirstValue(raw, ["decline_count", "down_count"], null)),
      flatCount: screenerFinite(screenerFirstValue(raw, ["flat_count", "unchanged_count"], null)),
      average: average,
      breadth: screenerFinite(screenerFirstValue(raw, ["breadth_percent", "breadth"], null)),
      tradeValue: screenerFinite(screenerFirstValue(raw, ["total_trade_value", "trade_value"], null)),
      institutionalNet: screenerFinite(screenerFirstValue(
        raw, ["institutional_net", "total_net"], null
      )),
      temperature: temperature
    };
  }

  function liveRenderIndustrySummaries(rawRows, mode) {
    var grid = document.querySelector('[data-industry-map-grid="true"]');
    if (!grid) { return; }
    var rows = [];
    for (var i = 0; i < rawRows.length; i++) {
      if (rawRows[i] && typeof rawRows[i] === "object") {
        rows.push(liveNormalizeIndustrySummary(rawRows[i]));
      }
    }
    rows.sort(function (left, right) {
      if (left.temperature === null && right.temperature === null) {
        return left.name.localeCompare(right.name, "zh-TW");
      }
      if (left.temperature === null) { return 1; }
      if (right.temperature === null) { return -1; }
      return right.temperature - left.temperature || left.name.localeCompare(right.name, "zh-TW");
    });
    grid.textContent = "";
    var fragment = document.createDocumentFragment();
    for (var rowIndex = 0; rowIndex < rows.length; rowIndex++) {
      var row = rows[rowIndex];
      var average = row.average;
      var tone = average === null ? "neutral" : average > 0 ? "positive" :
        average < 0 ? "negative" : "neutral";
      var tile = document.createElement("button");
      tile.type = "button";
      tile.className = "industry-tile industry-tile-" + tone;
      tile.setAttribute("data-industry-tile", row.name);
      tile.setAttribute(
        "aria-label",
        row.name + "，平均漲跌 " + livePercent(average) +
        "，報價 " + liveNumber(row.quotedCount, 0) + " 檔"
      );
      tile.style.setProperty(
        "--heat",
        average === null ? "0" : String(Math.min(1, Math.abs(average) / 10))
      );
      screenerAppendText(tile, "span", "industry-tile-name", row.name);
      var score = screenerAppendText(
        tile, "strong", "mono",
        row.temperature === null ? "--" : liveNumber(row.temperature, 0)
      );
      score.setAttribute("data-live-industry-score", "true");
      var change = screenerAppendText(
        tile, "span", "mono", livePercent(average) + " / " +
        (String(mode || "").toUpperCase() === "LIVE" ||
         String(mode || "").toUpperCase().indexOf("LIVE_FULL") !== -1
          ? "即時"
          : String(mode || "").toUpperCase() === "STALE"
            ? "逾時"
            : String(mode || "").toUpperCase() === "PARTIAL"
              ? "不完整" : "收盤")
      );
      change.setAttribute("data-live-industry-change", "true");
      liveTone(change, average);
      var quoted = row.quotedCount === null ? row.stockCount : row.quotedCount;
      var countText = liveNumber(quoted, 0) + " / " + liveNumber(row.stockCount, 0) + " 檔";
      if (row.advanceCount !== null || row.declineCount !== null) {
        countText += " · 漲 " + liveNumber(row.advanceCount, 0) +
          " / 跌 " + liveNumber(row.declineCount, 0);
      }
      var count = screenerAppendText(tile, "small", "", countText);
      count.setAttribute("data-live-industry-count", "true");
      fragment.appendChild(tile);
    }
    grid.appendChild(fragment);
    var countNode = document.querySelector('[data-industry-map-count="true"]');
    if (countNode) { countNode.textContent = String(rows.length); }
    var statusNode = document.querySelector('[data-industry-map-status="true"]');
    if (statusNode) {
      statusNode.textContent = (
        String(mode || "").toUpperCase() === "LIVE" ||
        String(mode || "").toUpperCase().indexOf("LIVE_FULL") !== -1
      )
        ? "全市場即時產業"
        : String(mode || "").indexOf("STALE") !== -1
          ? "全市場產業快取已過期"
          : String(mode || "").indexOf("PARTIAL") !== -1
            ? "全市場產業資料不完整"
        : String(mode || "").indexOf("EOD") !== -1
          ? "全市場收盤產業" : "全市場產業";
    }

    var pulse = document.querySelector('[data-live-overview-pulse="true"]');
    if (pulse) {
      pulse.textContent = "";
      for (var pulseIndex = 0; pulseIndex < Math.min(4, rows.length); pulseIndex++) {
        var pulseRow = rows[pulseIndex];
        var article = document.createElement("article");
        article.className = "desk-pulse-item";
        var head = document.createElement("div");
        screenerAppendText(head, "strong", "", pulseRow.name);
        screenerAppendText(
          head, "span", "mono",
          pulseRow.temperature === null ? "--" : liveNumber(pulseRow.temperature, 1)
        );
        article.appendChild(head);
        var changeLine = document.createElement("p");
        changeLine.appendChild(document.createTextNode("平均漲跌 "));
        var changeNode = screenerAppendText(changeLine, "span", "", livePercent(pulseRow.average));
        liveTone(changeNode, pulseRow.average);
        article.appendChild(changeLine);
        var flowLine = document.createElement("p");
        flowLine.appendChild(document.createTextNode("法人淨額 "));
        var flowNode = screenerAppendText(
          flowLine, "span", "",
          pulseRow.institutionalNet === null
            ? "未提供" : liveSignedNumber(pulseRow.institutionalNet, 0) + " 股"
        );
        liveTone(flowNode, pulseRow.institutionalNet);
        article.appendChild(flowLine);
        pulse.appendChild(article);
      }
    }
  }

  function populateScreenerIndustriesFromSummaries(rawRows) {
    var select = document.querySelector('[data-screener-industry="true"]');
    if (!select) { return; }
    var previous = select.value || "all";
    var values = [];
    for (var i = 0; i < rawRows.length; i++) {
      if (!rawRows[i] || typeof rawRows[i] !== "object") { continue; }
      var row = liveNormalizeIndustrySummary(rawRows[i]);
      if (row.name !== "未分類") { values.push(row); }
    }
    values.sort(function (left, right) { return left.name.localeCompare(right.name, "zh-TW"); });
    select.textContent = "";
    var allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = "全部產業";
    select.appendChild(allOption);
    for (var valueIndex = 0; valueIndex < values.length; valueIndex++) {
      var option = document.createElement("option");
      option.value = values[valueIndex].name;
      option.setAttribute("data-industry-name", values[valueIndex].name);
      option.textContent = values[valueIndex].name;
      select.appendChild(option);
    }
    select.disabled = values.length === 0;
    var foundPrevious = false;
    for (var optionIndex = 0; optionIndex < select.options.length; optionIndex++) {
      if (select.options[optionIndex].value === previous) { foundPrevious = true; break; }
    }
    select.value = foundPrevious ? previous : "all";
  }

  function liveUpdateIndustryMap(snapshot) {
    var summaryRows = liveIndustrySummaryRows(snapshot);
    var usingBreadthSummary = false;
    if (!summaryRows.length && marketBreadthIndustryRows.length) {
      summaryRows = marketBreadthIndustryRows;
      usingBreadthSummary = true;
    }
    if (!summaryRows.length && screenerBreadthRows.length) {
      summaryRows = liveAggregateBreadthIndustries();
      usingBreadthSummary = true;
    }
    if (summaryRows.length) {
      var summaryPayload = snapshot.industry_summaries || {};
      var industryMode = String(
        usingBreadthSummary
          ? screenerBreadthStatus
          : (summaryPayload && typeof summaryPayload === "object" &&
              (summaryPayload.status || summaryPayload.mode)) ||
            snapshot.industry_summary_mode || snapshot.status ||
            snapshot.mode || screenerBreadthStatus
      ).toUpperCase();
      liveRenderIndustrySummaries(summaryRows, industryMode);
      if (screenerUniverseMode !== "US") {
        populateScreenerIndustriesFromSummaries(summaryRows);
      }
      liveText(
        '[data-live-industry-note="true"]',
        "產業方塊使用全市場分類的可用報價聚合；顯示報價覆蓋、上漲／下跌家數與平均漲跌。" +
        (industryMode.indexOf("LIVE_FULL") !== -1
          ? "目前為全市場即時模式。"
          : industryMode.indexOf("STALE") !== -1
            ? "目前快取已過期，不應視為當期市場狀態。"
            : industryMode.indexOf("PARTIAL") !== -1
              ? "目前來源或交易日不完整，僅供缺口檢視。"
          : industryMode.indexOf("EOD") !== -1
            ? "目前為全市場收盤模式，不宣稱全市場即時。"
            : "請以狀態標籤確認資料時點。")
      );
      return;
    }
    var quotes = liveQuoteMap(snapshot);
    var quoteLabel = snapshot.status === "LIVE" ? "即時" :
      snapshot.status === "EOD" ? "收盤" : "來源狀態未確認";
    var flowRows = Array.isArray(snapshot.fund_flow) ? snapshot.fund_flow : [];
    var flowBySymbol = {};
    for (var flowIndex = 0; flowIndex < flowRows.length; flowIndex++) {
      var flowSymbol = String(flowRows[flowIndex].stock_id || "").toUpperCase();
      if (flowSymbol) { flowBySymbol[flowSymbol] = flowRows[flowIndex]; }
    }
    var stockRows = document.querySelectorAll('[data-screener-row="true"]');
    var groups = {};
    var groupFlows = {};
    for (var i = 0; i < stockRows.length; i++) {
      var symbol = String(stockRows[i].getAttribute("data-stock-key") || "").toUpperCase();
      var category = stockRows[i].getAttribute("data-live-category") || "未分類";
      var quote = quotes[symbol];
      if (!quote || !isFinite(Number(quote.change_percent))) { continue; }
      if (!groups[category]) { groups[category] = []; }
      groups[category].push(Number(quote.change_percent));
      var flow = flowBySymbol[symbol] || {};
      if (flow.total_net != null && isFinite(Number(flow.total_net))) {
        groupFlows[category] = (groupFlows[category] || 0) + Number(flow.total_net);
      }
    }
    var tiles = document.querySelectorAll("[data-industry-tile]");
    for (var j = 0; j < tiles.length; j++) {
      var tileCategory = tiles[j].getAttribute("data-industry-tile") || "";
      var values = groups[tileCategory] || [];
      var score = tiles[j].querySelector('[data-live-industry-score="true"]');
      var change = tiles[j].querySelector('[data-live-industry-change="true"]');
      var count = tiles[j].querySelector('[data-live-industry-count="true"]');
      if (!values.length) {
        tiles[j].classList.remove(
          "industry-tile-positive", "industry-tile-negative", "industry-tile-neutral"
        );
        tiles[j].classList.add("industry-tile-neutral");
        tiles[j].style.setProperty("--heat", "0");
        if (score) { score.textContent = "--"; }
        if (change) {
          change.textContent = "行情未提供";
          liveTone(change, null);
        }
        if (count) { count.textContent = "研究池成分股本次無可用報價"; }
        continue;
      }
      var total = 0;
      for (var k = 0; k < values.length; k++) { total += values[k]; }
      var average = total / values.length;
      var temperature = Math.max(0, Math.min(100, 50 + average * 8));
      tiles[j].classList.remove(
        "industry-tile-positive", "industry-tile-negative", "industry-tile-neutral"
      );
      tiles[j].classList.add(
        average > 0 ? "industry-tile-positive" :
        average < 0 ? "industry-tile-negative" : "industry-tile-neutral"
      );
      tiles[j].style.setProperty("--heat", String(Math.min(1, Math.abs(average) / 10)));
      if (score) { score.textContent = liveNumber(temperature, 0); }
      if (change) {
        change.textContent = livePercent(average) + " / " + quoteLabel;
        liveTone(change, average);
      }
      if (count) { count.textContent = values.length + " 檔" + quoteLabel + "報價 · 點擊查看細節"; }
    }
    var overviewPulse = document.querySelector('[data-live-overview-pulse="true"]');
    if (overviewPulse) {
      var pulseRows = Object.keys(groups).map(function (categoryName) {
        var categoryValues = groups[categoryName];
        var categoryTotal = 0;
        for (var index = 0; index < categoryValues.length; index++) {
          categoryTotal += categoryValues[index];
        }
        var categoryAverage = categoryTotal / categoryValues.length;
        return {
          category: categoryName,
          average: categoryAverage,
          temperature: Math.max(0, Math.min(100, 50 + categoryAverage * 8)),
          flow: Object.prototype.hasOwnProperty.call(groupFlows, categoryName)
            ? groupFlows[categoryName] : null
        };
      });
      pulseRows.sort(function (left, right) {
        return right.temperature - left.temperature || left.category.localeCompare(right.category);
      });
      overviewPulse.textContent = "";
      for (var pulseIndex = 0; pulseIndex < Math.min(4, pulseRows.length); pulseIndex++) {
        var pulseRow = pulseRows[pulseIndex];
        var article = document.createElement("article");
        article.className = "desk-pulse-item";
        var head = document.createElement("div");
        var categoryNode = document.createElement("strong");
        categoryNode.textContent = pulseRow.category;
        var temperatureNode = document.createElement("span");
        temperatureNode.className = "mono";
        temperatureNode.textContent = liveNumber(pulseRow.temperature, 1);
        head.appendChild(categoryNode);
        head.appendChild(temperatureNode);
        article.appendChild(head);
        var changeLine = document.createElement("p");
        changeLine.appendChild(document.createTextNode("當日均幅 "));
        var changeNode = document.createElement("span");
        changeNode.textContent = livePercent(pulseRow.average);
        liveTone(changeNode, pulseRow.average);
        changeLine.appendChild(changeNode);
        article.appendChild(changeLine);
        var flowLine = document.createElement("p");
        flowLine.appendChild(document.createTextNode("法人淨額 "));
        var flowNode = document.createElement("span");
        flowNode.textContent = pulseRow.flow == null
          ? "未提供" : liveSignedNumber(pulseRow.flow, 0) + " 股";
        liveTone(flowNode, pulseRow.flow);
        flowLine.appendChild(flowNode);
        article.appendChild(flowLine);
        overviewPulse.appendChild(article);
      }
      if (!pulseRows.length) {
        var pulseEmpty = document.createElement("p");
        pulseEmpty.className = "desk-empty";
        pulseEmpty.textContent = "目前行情來源尚未提供研究池的產業溫度。";
        overviewPulse.appendChild(pulseEmpty);
      }
    }
    liveText(
      '[data-live-industry-note="true"]',
      "連線時方塊顏色＝研究池成分股本次行情平均漲跌；大字＝透明規則溫度。" +
      "完整產業廣度仍需全市場授權快照。"
    );
  }

  function liveUpdateStrategy(snapshot) {
    var market = snapshot.market || {};
    liveText('[data-live-strategy-regime="true"]', market.regime || "行情資料不足");
    liveText('[data-live-strategy-posture="true"]', market.posture || "等待市場資料。");
    var family = market.strategy || "neutral";
    var quoteState = (snapshot.source_status || {}).quotes || {};
    var missingSymbols = Array.isArray(snapshot.missing_symbols)
      ? snapshot.missing_symbols : [];
    var quoteStatus = String(quoteState.status || "").toUpperCase();
    var quoteComplete = !quoteState.partial && missingSymbols.length === 0 &&
      (quoteStatus === "LIVE" || quoteStatus === "EOD");
    var usable = (snapshot.status === "LIVE" || snapshot.status === "EOD") &&
      quoteComplete;
    var modeBox = document.querySelector('[data-live-strategy-mode="true"]');
    if (modeBox) {
      modeBox.textContent = "";
      var modePill = document.createElement("span");
      modePill.className = "ui-pill " + (usable ? "ui-pill-ok" : "ui-pill-warn");
      modePill.textContent = !quoteComplete
        ? "行情：部分缺漏"
        : (snapshot.status === "LIVE"
          ? "行情：即時連線"
          : (snapshot.status === "EOD"
            ? "行情：今日收盤"
            : "行情：" + (snapshot.status || "無可用行情")));
      modeBox.appendChild(modePill);
    }
    var gateNode = document.querySelector('[data-live-strategy-gate="true"]');
    if (gateNode) {
      var researchReady = gateNode.getAttribute("data-research-gate-ready") === "true";
      var researchMessage = gateNode.getAttribute("data-research-gate-message")
        || "研究快照 Gate 尚未通過，候選交接暫停";
      if (!quoteComplete) {
        gateNode.textContent = "自選行情只完成部分同步，候選複核與策略匹配暫停";
      } else if (snapshot.status === "LIVE") {
        gateNode.textContent = "即時行情可用；" + (
          researchReady
            ? "研究快照 Gate 已通過，可進入候選複核"
            : researchMessage
        );
      } else if (snapshot.status === "EOD") {
        gateNode.textContent = "今日收盤行情可用；" + (
          researchReady
            ? "研究快照 Gate 已通過，可進入候選複核"
            : researchMessage
        );
      } else if (snapshot.status === "STALE") {
        gateNode.textContent = "行情已過期，暫停策略判讀並等待資料恢復";
      } else {
        gateNode.textContent = "行情資料不可用，暫停策略判讀並檢查來源狀態";
      }
    }
    var cards = document.querySelectorAll("[data-live-strategy-family]");
    for (var i = 0; i < cards.length; i++) {
      var cardFamily = cards[i].getAttribute("data-live-strategy-family") || "";
      var fit = usable && cardFamily === family;
      cards[i].classList.toggle("market-fit", fit);
      var fitBox = cards[i].querySelector('[data-live-strategy-fit="true"]');
      if (fitBox) {
        fitBox.textContent = "";
        var pill = document.createElement("span");
        pill.className = "ui-pill " + (fit ? "ui-pill-ok" : "ui-pill-info");
        pill.textContent = fit
          ? (snapshot.status === "LIVE" ? "符合即時盤勢" : "符合今日收盤情境")
          : (usable ? "備用情境" : "等待可用行情");
        fitBox.appendChild(pill);
      }
    }
  }

  function liveApplySnapshot(snapshot) {
    liveUpdateConnection(snapshot);
    liveUpdateHero(snapshot);
    liveUpdateOverviewMetrics(snapshot);
    liveUpdateStocks(snapshot);
    liveUpdateNews(snapshot);
    liveUpdateIndustryMap(snapshot);
    liveUpdateStrategy(snapshot);
    var panel = document.querySelector(".ui-panel.active");
    if (panel) {
      panel.setAttribute("data-live-updated", "true");
      window.setTimeout(function () { panel.removeAttribute("data-live-updated"); }, 700);
    }
  }

  function liveInvalidateSnapshot(message) {
    var unavailable = {
      status: "UNAVAILABLE",
      market: {
        status: "UNAVAILABLE",
        regime: "行情資料不可用",
        strategy: "neutral",
        posture: message || "等待市場資料恢復。"
      },
      indices: [],
      quotes: [],
      missing_symbols: liveSymbols(),
      active_watchlist_alerts: [],
      news: [],
      source_status: {
        quotes: {status: "UNAVAILABLE", partial: true},
        alerts: {status: "UNAVAILABLE"},
        news: {status: "UNAVAILABLE"},
        fund_flow: {status: "UNAVAILABLE"}
      }
    };
    liveUpdateHero(unavailable);
    liveUpdateOverviewMetrics(unavailable);
    liveUpdateStocks(unavailable);
    liveUpdateStrategy(unavailable);
  }

  function liveUpdateCountdown() {
    var node = document.querySelector('[data-live-countdown="true"]');
    if (!node) { return; }
    if (document.hidden) {
      node.textContent = "分頁隱藏，已暫停更新";
      return;
    }
    var remaining = Math.max(0, Math.ceil((liveNextRefreshAt - Date.now()) / 1000));
    node.textContent = liveRequestInFlight ? "更新中" : remaining + " 秒後更新";
  }

  function liveSchedule(seconds) {
    if (liveMarketTimer) {
      window.clearTimeout(liveMarketTimer);
      liveMarketTimer = null;
    }
    var wait = Math.max(liveMinimumRefreshSeconds, Number(seconds) || 60);
    liveNextRefreshAt = Date.now() + wait * 1000;
    if (!document.hidden) {
      liveMarketTimer = window.setTimeout(liveFetchSnapshot, wait * 1000);
    }
    liveUpdateCountdown();
    return wait;
  }

  function scheduleVisibleLiveRefresh() {
    if (screenerUniverseMode === "US" ||
        marketBreadthState !== "ready" || document.hidden || !window.fetch) {
      return;
    }
    if (liveVisibleRefreshTimer) {
      window.clearTimeout(liveVisibleRefreshTimer);
      liveVisibleRefreshTimer = null;
    }
    var minimumWait = liveMinimumRefreshSeconds * 1000;
    var elapsed = liveLastRequestAt ? Date.now() - liveLastRequestAt : minimumWait;
    var wait = Math.max(250, minimumWait - elapsed);
    liveVisibleRefreshTimer = window.setTimeout(function () {
      liveVisibleRefreshTimer = null;
      if (document.hidden) { return; }
      liveBreadthRefreshPending = true;
      if (!liveRequestInFlight) {
        liveBreadthRefreshPending = false;
        if (liveMarketTimer) {
          window.clearTimeout(liveMarketTimer);
          liveMarketTimer = null;
        }
        liveFetchSnapshot();
      }
    }, wait);
  }

  function liveRetryAfterSeconds(value) {
    if (value == null || String(value).trim() === "") { return null; }
    var seconds = Number(value);
    if (isFinite(seconds) && seconds >= 0) { return Math.ceil(seconds); }
    var retryAt = Date.parse(String(value || ""));
    if (!isNaN(retryAt)) {
      return Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
    }
    return null;
  }

  function liveFetchSnapshot() {
    if (document.hidden) {
      liveNextRefreshAt = 0;
      liveUpdateCountdown();
      return;
    }
    if (liveRequestInFlight || !window.fetch) { return; }
    if (liveVisibleRefreshTimer) {
      window.clearTimeout(liveVisibleRefreshTimer);
      liveVisibleRefreshTimer = null;
    }
    liveRequestInFlight = true;
    liveLastRequestAt = Date.now();
    liveUpdateCountdown();
    var symbols = liveSymbols();
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = controller ? window.setTimeout(function () { controller.abort(); }, 15000) : null;
    var options = { cache: "no-store", headers: { "Accept": "application/json" } };
    if (controller) { options.signal = controller.signal; }
    window.fetch("/api/live/snapshot?symbols=" + encodeURIComponent(symbols.join(",")), options)
      .then(function (response) {
        if (!response.ok) {
          var error = new Error("live API HTTP " + response.status);
          if (response.status === 429) {
            error.retryAfterSeconds = liveRetryAfterSeconds(
              response.headers.get("Retry-After")
            );
          }
          throw error;
        }
        return response.json();
      })
      .then(function (snapshot) {
        liveApplySnapshot(snapshot || {});
        liveSchedule(snapshot.refresh_after_seconds || 60);
      })
      .catch(function (err) {
        liveInvalidateSnapshot(err.message || String(err));
        var bar = document.querySelector('[data-live-connection="true"]');
        if (bar) {
          bar.classList.remove("live-connection-loading", "live-connection-live", "live-connection-eod");
          bar.classList.add("live-connection-error");
        }
        liveText('[data-live-connection-title="true"]', "市場資料連線失敗");
        var retrySeconds = liveSchedule(err.retryAfterSeconds == null ? 15 : err.retryAfterSeconds);
        liveText(
          '[data-live-connection-detail="true"]',
          "將於 " + retrySeconds + " 秒後重試；" + (err.message || err)
        );
      })
      .then(function () {
        if (timeout) { window.clearTimeout(timeout); }
        liveRequestInFlight = false;
        liveUpdateCountdown();
        if (liveBreadthRefreshPending && !document.hidden) {
          liveBreadthRefreshPending = false;
          if (liveMarketTimer) {
            window.clearTimeout(liveMarketTimer);
            liveMarketTimer = null;
          }
          liveFetchSnapshot();
        }
      });
  }

  function initLiveMarket() {
    if (document.body.getAttribute("data-live-api-enabled") !== "true") { return; }
    loadMarketBreadth(false);
    var refresh = document.querySelector('[data-live-refresh="true"]');
    if (refresh) {
      refresh.addEventListener("click", function () {
        if (screenerUniverseMode === "US") {
          loadUsMarket(true);
          return;
        }
        if (marketBreadthRetryTimer) {
          window.clearTimeout(marketBreadthRetryTimer);
          marketBreadthRetryTimer = null;
        }
        liveBreadthRefreshPending = true;
        loadMarketBreadth(true);
      });
    }
    liveCountdownTimer = window.setInterval(liveUpdateCountdown, 1000);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        if (liveMarketTimer) {
          window.clearTimeout(liveMarketTimer);
          liveMarketTimer = null;
        }
        if (marketBreadthRefreshTimer) {
          window.clearTimeout(marketBreadthRefreshTimer);
          marketBreadthRefreshTimer = null;
        }
        liveUpdateCountdown();
        return;
      }
      if (marketBreadthNeedsRefresh(false, Date.now())) {
        loadMarketBreadth(false);
      } else {
        scheduleMarketBreadthRefresh();
      }
      if (Date.now() >= liveNextRefreshAt) {
        liveFetchSnapshot();
      } else {
        liveSchedule((liveNextRefreshAt - Date.now()) / 1000);
      }
    });
    if (!document.hidden) { liveFetchSnapshot(); }
  }

  initTabs();
  initTabJumps();
  initGlobalSearch();
  initScreener();
  initWatchlist();
  initMarketNotes();
  initIntelNewsFilters();
  initIndustryMap();
  initExpandToggles();
  initQueueFilters();
  initQueueFilterReset();
  initCopyButtons();
  initBulkSelection();
  initBulkStaticCopy();
  initIndustrySentimentSort();
  initActionApi();
  initEvidenceCompose();
  initLiveMarket();
})();
