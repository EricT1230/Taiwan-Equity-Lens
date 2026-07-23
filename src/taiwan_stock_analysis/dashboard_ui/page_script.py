from __future__ import annotations

# Vanilla, dependency-free inline <script> for the page shell (Task 10). Split into
# its own leaf module (rather than a giant string literal inside page.py) purely for
# file-cohesion -- page.py owns HTML assembly/derivation, this module owns client-side
# behavior. No Python values are interpolated into this string: every DOM hook it
# reads (`.ui-tab`/`.ui-panel`, `[data-queue-filter]`, `[data-queue-toggle]` +
# `.queue-expand[data-expand-for]`, `[data-copy]`, `[data-action-api]` +
# `data-source-path`/`data-state-path`/`data-stock`/`data-action-id`/`data-status`,
# `.queue-evidence input`) is real markup already emitted by views/workbench.py --
# see that module for the exact producer of each attribute. The two POST endpoints
# and their JSON body field names are read verbatim from dashboard_server.py's
# `do_POST`/`set_review_action_status_from_payload`/`write_handoff_pack_from_payload`.
#
# Industry-sentiment sort control (spec 3.2 "產業排序控制"): reads
# `[data-industry-sentiment-sort="true"]` (the <select>) and
# `[data-market-sentiment-section="true"]` (the card container) plus each card's
# `data-sentiment-status`/`data-sentiment-category`/`data-sentiment-score`/
# `data-sentiment-change`/`data-peak-risk`/`data-trough-risk`/`data-confidence-order`
# attributes (note: `data-sentiment-category`, not the workbench queue rows' unrelated
# same-named-but-different-domain `data-category`) -- all emitted
# by views/market.py's `_industry_sentiment_sort_control`/`_sentiment_card_attrs`. Sort
# modes are ported from dashboard.py:1002-1009's <select> options; unlike the pre-
# redesign JS, this never force-sorts on page load -- the server's default order
# (views/market.py's `_industry_sort_key`, score desc) already matches the select's
# default "score" value, so the page is correct even if this script never runs.
SCRIPT = """<script>
(function () {
  "use strict";

  var TAB_KEYS = ["market", "workbench", "outputs"];

  function activateTab(name) {
    if (TAB_KEYS.indexOf(name) === -1) { name = "market"; }
    var tabs = document.querySelectorAll(".ui-tab");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle("active", tabs[i].getAttribute("data-tab") === name);
    }
    var panels = document.querySelectorAll(".ui-panel");
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.toggle("active", panels[j].id === name);
    }
  }

  function initTabs() {
    var tabs = document.querySelectorAll(".ui-tab");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener("click", function (event) {
        var name = event.currentTarget.getAttribute("data-tab");
        activateTab(name);
        location.hash = name;
      });
    }
    var initial = (location.hash || "").replace("#", "");
    activateTab(initial || "market");
  }

  function initExpandToggles() {
    var toggles = document.querySelectorAll("[data-queue-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].addEventListener("click", function (event) {
        var btn = event.currentTarget;
        var targetId = btn.getAttribute("data-queue-toggle");
        var expand = document.querySelector('.queue-expand[data-expand-for="' + targetId + '"]');
        if (!expand) { return; }
        if (expand.hasAttribute("hidden")) {
          expand.removeAttribute("hidden");
          btn.textContent = "收合 ▲";
        } else {
          expand.setAttribute("hidden", "");
          btn.textContent = "展開 ▼";
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
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle("hidden", !rowMatchesFilters(rows[i], state));
    }
  }

  function initQueueFilters() {
    var controls = document.querySelectorAll("[data-queue-filter]");
    for (var i = 0; i < controls.length; i++) {
      var eventName = controls[i].tagName === "SELECT" ? "change" : "input";
      controls[i].addEventListener(eventName, applyQueueFilters);
    }
    if (controls.length) { applyQueueFilters(); }
  }

  function flashLabel(el, text, delayMs) {
    var original = el.textContent;
    el.textContent = text;
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
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
    // than showing a fabricated 0/0.
    var byStatus = data.by_status;
    if (!byStatus || typeof byStatus !== "object") { return; }
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

  function handleReviewAction(btn) {
    var expand = btn.closest ? btn.closest(".queue-expand") : null;
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
    btn.disabled = true;
    postJson("/api/review-actions/set", payload).then(function (data) {
      var rowId = expand ? expand.getAttribute("data-expand-for") : null;
      updateRowStatus(rowId ? document.getElementById(rowId) : null, payload.status);
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
        }
      });
    }
  }

  initTabs();
  initExpandToggles();
  initQueueFilters();
  initCopyButtons();
  initIndustrySentimentSort();
  initActionApi();
})();
</script>"""
