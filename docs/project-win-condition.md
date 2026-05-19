# Project Win Condition

Updated: 2026-05-20

Taiwan Equity Lens succeeds when it is a reliable local research-handoff workflow for Taiwan equities. It should help a user organize evidence, surface blockers, and decide whether a research package is ready for human review. It must not present investment advice, buy/sell/hold instructions, allocation guidance, or autonomous trading decisions.

## Current Win Condition

A research run is ready for handoff only when all of these are true:

- `doctor demo` passes for the generated demo or workflow output shape.
- `doctor handoff <research_summary.json>` reports `Handoff readiness OK`.
- The dashboard first screen answers:
  - whether the current research can be handed off,
  - the top 3 blockers to handle first,
  - which expert lens raised each blocker,
  - which next button or command to run,
  - that the output is not investment advice.
- The research pack and memo remain readable by a human reviewer without relying on hidden CLI state.

## Handoff Gate Contract

`doctor handoff` and the Expert Agent Console should use the same gate. The gate blocks handoff when any of these exist:

- open review actions after applying `review_action_state.json`,
- stale review-action state entries that no longer match generated actions,
- missing required gate actions inferred from source audit, workflow, reliability, valuation, fundamental-review, or research-state signals,
- invalid or unreadable summary/state shape.

## Premortem Risks Addressed

The 2027-05-20 premortem identified four risks that this contract directly reduces:

- Silent correctness degradation: the gate looks for missing required review actions instead of trusting a pleasant dashboard.
- Undefined win condition: this file defines the ready-for-handoff threshold.
- Backtest/live or research/handoff gap: the gate is an explicit bridge between generated artifacts and human review.
- Overreliance on agents: expert labels explain the blocker lens, but the pass/fail signal comes from deterministic data checks.

## Non-Goals

- No investment recommendation engine.
- No automatic portfolio allocation.
- No live-trading or order-routing workflow.
- No promise that complete research is financially correct; it only means the local handoff quality checks have passed.
