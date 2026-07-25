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
#
# Bulk queue operations (spec 3.3 "批次操作"): reads each row's
# `[data-queue-select="true"]` checkbox (carries `data-stock`/`data-action-id`
# and, static mode only, `data-command-done`/`data-command-deferred` -- all
# emitted by views/workbench.py's `_row_select_checkbox`), the toolbar's
# `[data-queue-select-visible="true"]` checkbox and `[data-queue-bulk-count="true"]`
# span, and `[data-queue-bulk-status]` buttons (`_bulk_tools_bar`). Selection only
# ever considers rows without the filter JS's own `.hidden` class -- "目前顯示"
# tracks `applyQueueFilters()`'s output, not a separate concept. Static-mode bulk
# buttons carry no `data-action-api` and copy each selected row's pre-baked
# `data-command-<status>` text directly; served-mode buttons reuse the
# `data-action-api` dispatch below with a new "bulk-review-action" kind, POSTing
# to the same `/api/review-actions/set` endpoint as the single-row path
# (`handleReviewAction`) once per selected row, sequentially (not in parallel --
# `set_review_action_state` is a read-modify-write on one shared JSON file, and
# dashboard_server.py's ThreadingHTTPServer would race concurrent writes to it).
# Served-mode bulk payloads deliberately OMIT note/reviewer/evidence_url --
# dashboard_server.py's set_review_action_status_from_payload now treats an
# absent key as "preserve", not "clear" (the CRITICAL data-loss fix). Rows that
# require evidence (`data-requires-evidence="true"`, from
# handoff.requires_handoff_evidence) and don't already have it on record
# (`data-has-evidence` != "true") are skipped rather than silently closed --
# restoring the pre-redesign bulk handler's refusal to close an
# evidence-required blocker without evidence -- and the skip count is reported
# in the final flash message alongside the success count.
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
        navigator.clipboard.writeText(commands.join("\\n")).then(function () {
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

  initTabs();
  initExpandToggles();
  initQueueFilters();
  initCopyButtons();
  initBulkSelection();
  initBulkStaticCopy();
  initIndustrySentimentSort();
  initActionApi();
})();
</script>"""
