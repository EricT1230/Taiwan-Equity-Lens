from __future__ import annotations

from pathlib import Path

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
#
# The body itself lives beside this module in script.js so it is real JavaScript
# to every editor, linter, and formatter; a 4,000-line Python string literal gets
# no static analysis at all. It is read at import time and inlined verbatim below,
# so a rendered dashboard.html stays a single self-contained file that needs no
# external fetch.
_SCRIPT_PATH = Path(__file__).with_name("script.js")

SCRIPT = "<script>" + _SCRIPT_PATH.read_text(encoding="utf-8") + "</script>"
