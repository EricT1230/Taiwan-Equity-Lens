---
status: ready-for-agent
workflow: matt-pocock
date: 2026-08-28
---

# Production Data Mode

## Problem Statement

The served dashboard currently combines official market APIs with artifacts discovered from a demo output directory. Live quotes, official breadth, exchange announcements, fixture research summaries, offline prices, synthetic sentiment, and example links can therefore coexist on one screen. A user cannot reliably tell which cards are current official data, which are stale research artifacts, and which are only demonstrations. The dashboard also loses its last validated full-market snapshot when the process stops, and its Fubon integration polls REST snapshots instead of using the provider's WebSocket stream during market hours.

The user needs the loopback dashboard to fail closed: production pages must contain only attributable official or licensed data, explicitly report missing or stale domains, preserve the last validated official snapshot without presenting it as current, and keep all demonstration content in a separate mode.

## Solution

Introduce an explicit production data mode at the served HTTP boundary. Before any generated artifact reaches a production page, one admission policy will validate its source, status, and observation time. Demo, fixture, offline, synthetic, example, missing-provenance, future-dated, and stale artifacts will be rejected from production rendering. A separate, visibly labelled Demo route will continue to render demonstration artifacts and will never become an automatic fallback for production.

The production dashboard will load official Taiwan market breadth, licensed Fubon quotes, exchange announcements, alert lists, fund flow, and available official financial summaries through the existing same-origin APIs. Successful official snapshots will be written atomically to a local ignored directory. When an upstream request fails, the server may return the last validated snapshot only as `STALE`, with its original observation time and cache provenance; it must never relabel cached data as live.

During Taiwan market hours, the Fubon SDK WebSocket will use Normal-mode aggregate quotes for the currently requested stocks and subscribe to benchmark indices. Fresh stream events will upgrade matching REST baselines to `LIVE`. A disconnected, quiet, malformed, future-dated, or expired stream is `STALE`; `DELAYED` is permitted only when the provider contract or payload explicitly labels the feed delayed. After the session, authoritative provider close data will remain `EOD`. REST remains the baseline and fail-closed fallback, not a second source of invented values.

Every production page will expose a consistent source/status/time contract. Unsupported research, detailed statements, strategy evidence, US prices, and similar domains will remain visible as `UNAVAILABLE` rather than being filled with demo content. Strategy cards remain transparent research rules only: no unstated backtest, win rate, prediction confidence, personalised recommendation, account access, order placement, or trading route.

## User Stories

1. As a local dashboard user, I want the default 8877 page to open in production mode, so that I do not mistake demo artifacts for market data.
2. As a local dashboard user, I want a separate Demo route, so that I can still inspect the product layout without contaminating production.
3. As a local dashboard user, I want Demo mode to be visibly labelled, so that its purpose cannot be confused with official data.
4. As a local dashboard user, I want production mode to reject fixture financial summaries, so that fabricated company metrics never appear as real.
5. As a local dashboard user, I want production mode to reject offline prices, so that old placeholders never look like current quotes.
6. As a local dashboard user, I want production mode to reject synthetic sentiment, so that model demonstrations never look like observed market mood.
7. As a local dashboard user, I want production mode to reject example links and example-domain news, so that sample stories never appear in the news feed.
8. As a local dashboard user, I want every accepted artifact to have a recognised source, so that its provenance is auditable.
9. As a local dashboard user, I want every accepted artifact to have a valid status, so that availability is machine-readable and visible.
10. As a local dashboard user, I want every accepted artifact to have a valid observation time, so that I can judge freshness.
11. As a local dashboard user, I want future-dated artifacts rejected, so that clock or source errors fail closed.
12. As a local dashboard user, I want stale artifacts rejected from current research cards, so that old analysis is not silently promoted.
13. As a local dashboard user, I want unavailable cards to remain visible with an explanation, so that absence is not confused with zero.
14. As a local dashboard user, I want the page to show `LIVE`, `DELAYED`, `EOD`, `STALE`, or `UNAVAILABLE`, so that the quote state is unambiguous.
15. As a local dashboard user, I want Fubon WebSocket events used during market hours, so that visible subscribed quotes can update without REST-only polling.
16. As a local dashboard user, I want the stream to subscribe only to symbols the page requests, so that the provider subscription budget remains controlled.
17. As a local dashboard user, I want stream disconnections to be surfaced, so that the last event is not presented as a live connection.
18. As a local dashboard user, I want reconnects to resubscribe safely with bounded backoff, so that short outages can recover without rapid connection churn.
19. As a local dashboard user, I want authoritative REST quotes retained as the baseline, so that WebSocket trades do not invent reference prices or change percentages.
20. As a local dashboard user, I want post-close data labelled EOD with its trading date, so that closed-market data is not called streaming.
21. As a local dashboard user, I want the server to save successful official snapshots atomically, so that a restart does not discard the last verified state.
22. As a local dashboard user, I want cached snapshots labelled stale after an upstream failure, so that resilience does not weaken truthfulness.
23. As a local dashboard user, I want manual refresh to re-run official data acquisition, so that I can request an immediate update.
24. As a local dashboard user, I want initial page load to start official data acquisition, so that no extra command is required after launching 8877.
25. As a local dashboard user, I want news cards to show source, publication time, and original link, so that each item is traceable.
26. As a local dashboard user, I want industry and screener data to expose the official dataset status and observation time, so that rankings are not detached from their inputs.
27. As a local dashboard user, I want unsupported detailed statements and research summaries to say unavailable, so that empty integration work is not hidden by samples.
28. As a local dashboard user, I want strategy rules to disclose their inputs, activation conditions, and invalidation conditions, so that they are not black-box tips.
29. As a local dashboard user, I want unbacktested strategies to omit win rates and confidence claims, so that descriptive rules are not misrepresented as validated predictions.
30. As a local dashboard user, I want all production data to stay on loopback under the current licence, so that licensed quotes are not redistributed publicly.
31. As a maintainer, I want credentials to remain server-side and excluded from snapshots, so that cache files cannot leak secrets.
32. As a maintainer, I want one admission policy shared by every view, so that data truth rules do not drift between pages.
33. As a maintainer, I want production and Demo behavior verified through the actual HTTP server, so that tests cover the same boundary users open.
34. As a maintainer, I want the full existing suite to remain green, so that the new data boundary does not regress research workflows or demo generation.

## Implementation Decisions

- The served dashboard has two explicit modes: `production` is the default root route and `demo` is a separate route. Mode is machine-readable in the page shell and visible to the user.
- Data mode and live API availability are separate concepts. Enabling the same-origin API does not automatically make discovered artifacts production-safe.
- A single admission policy runs before rendering. Individual views receive already-admitted artifacts and do not infer trust independently.
- Admission is fail-closed. An artifact is rejected when its nested content identifies fixture, offline, synthetic, demo-only, example-domain, missing-provenance, invalid-time, future-time, or stale input.
- Recognised production data is limited to official or licensed Fubon, TWSE, TPEx, and MOPS data for numeric Taiwan market and financial fields. Public editorial news may be admitted only when source, publication time, and an HTTP(S) original link are present.
- Rejected artifacts are represented by a structured rejection summary. The production page may explain that content was blocked, but it must not render the rejected title, metric, URL, or path as current content.
- Demo mode may render the existing artifacts, but it is always visibly labelled and never used as a fallback after a production failure.
- A local snapshot store uses schema-versioned JSON envelopes, atomic replace, bounded file size, and an ignored local data directory. It stores public market payloads only, never credentials, SDK tokens, account responses, headers, or certificate paths.
- A snapshot is persisted only after its contract and provenance pass validation. A loaded fallback keeps its original observation time, records cache origin, and is downgraded to `STALE`.
- Fubon REST remains the source of the initial quote baseline, previous close, provider metadata, and after-hours EOD evidence.
- One Fubon WebSocket connection uses the Normal-mode stock `aggregates` and `indices` channels. The requested symbol set is bounded below the provider's documented subscription cap.
- WebSocket aggregate events update only fields the event actually supplies. Change and change percentage are derived only when an authoritative REST previous close exists.
- Stream state is based on connection state and the newest accepted provider event time. Fresh market-session events can publish `LIVE`; disconnected, quiet, malformed, future-dated, out-of-order, or expired streams publish `STALE`; no valid event publishes `UNAVAILABLE` or leaves the authoritative REST EOD state unchanged. `DELAYED` is used only when explicit provider metadata says the feed itself is delayed; delayed-opening or delayed-closing auction flags are not delayed-quote evidence.
- Reconnection uses one worker, bounded exponential backoff, and explicit resubscription. Closing the dashboard stops the stream and logs out through the existing session lifecycle.
- The browser continues to use same-origin JSON APIs and never receives the Fubon API key or SDK token.
- All pages include a consistent production provenance surface covering行情、全市場、新聞、財務摘要、研究／策略 and US reference domains.
- Strategy cards remain deterministic research playbooks. They expose rule inputs and invalidation conditions and make no claim of backtested performance unless separate evidence exists.
- The default start script launches production mode on `127.0.0.1:8877`. Demo mode remains reachable through the same loopback server.
- Existing uncommitted Fubon snapshot compatibility changes are preserved. No Git commit is made without separate user approval.

## Testing Decisions

- The highest test seam is the real local HTTP server plus its rendered production and Demo pages. Tests assert externally visible content and JSON contracts, not private implementation calls.
- A mixed artifact directory will contain unique official and Demo sentinels. The production route must show only admitted official content or explicit unavailable states; the Demo route must show its sentinel and Demo label.
- Admission matrix tests cover nested fixture, offline, synthetic, example-domain, missing source, missing status, missing time, stale time, future time, and valid official artifacts.
- Snapshot-store tests cover atomic successful writes, secret-field rejection, corrupt or oversized cache rejection, and stale downgrade on fallback.
- Stream tests use an injected provider boundary and known message literals. They cover connect, subscribe, trade merge, index merge, disconnect, delayed/stale transitions, resubscription, malformed events, and close without authenticating against the real provider.
- Existing Fubon REST tests remain the authority for authenticated snapshot normalization, session invalidation, EOD classification, and missing-symbol behavior.
- Browser-script tests cover accepted quote states, provenance labels, and fail-closed clearing of static production content. They do not test internal function call counts.
- Targeted test files run after each vertical slice. The complete unittest suite, compile check, dependency check, diff check, live provider doctor, loopback HTTP probe, and browser visual review run at the end.
- A post-close live provider probe may establish current EOD availability but must not be reported as streaming readiness. WebSocket readiness requires an authenticated connection event and, during an open session, a fresh provider data event.

## Out of Scope

- US licensed prices, historical prices, fundamentals, or broad editorial news.
- Taiwan or commissioned-brokerage US account balances, inventory, cost basis, profit/loss, dividends, or asset allocation.
- Any order placement, trading route, conditional order, or account mutation.
- A Windows background scheduler or always-on service.
- A desktop installer, Electron/Tauri shell, auto-update, or system-tray integration.
- Public hosting or market-data redistribution while redisplay permission remains disabled.
- Automatic generation of audited MOPS detailed statements when no current adapter exists.
- Claims of strategy profitability, backtested win rate, predictive confidence, or personalised investment advice.
- Expanding the official industry taxonomy into a manually curated supply-chain graph.
- Creating a Git commit, release, deployment, or external issue without separate authorization.

## Further Notes

- The current repository has a GitHub remote but no Matt Pocock issue-tracker vocabulary or `ready-for-agent` label configuration in the checkout. This local document is therefore the canonical `ready-for-agent` spec for implementation; no external issue was created.
- Production truthfulness takes precedence over visual fullness. `UNAVAILABLE` is a successful fail-closed outcome when no qualifying source exists.
- The Fubon provider is configured for personal loopback use and redisplay permission is disabled. The server must remain bound to loopback for this stage.
