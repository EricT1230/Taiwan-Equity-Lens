# Research Methodology

Taiwan Equity Lens is a deterministic research workflow for Taiwan equity fundamental analysis. It organizes public financial-statement data, user-provided valuation assumptions, and research notes into reviewable artifacts.

## What The Tool Does

- Parses annual income statement, balance sheet, and cash-flow statement pages.
- Calculates profitability, growth, leverage, cash-flow, dividend, EPS, and valuation scenario metrics.
- Produces JSON, HTML, Markdown, dashboard, memo, pack, and comparison outputs.
- Preserves research notes, thesis fields, risks, triggers, follow-up questions, and optional market-rotation context from the research CSV.

## What The Tool Does Not Do

- It does not provide investment advice.
- It does not produce buy, sell, hold, allocation, or final decision labels.
- It does not verify live market data beyond the configured source behavior.
- It does not replace source filings, accounting review, or personal due diligence.
- It does not treat source-audit status as a recommendation or final assurance.

## Research CSV Fields

| Field | Purpose |
| --- | --- |
| `stock_id` | Taiwan stock identifier. |
| `company_name` | Display name used in reports. |
| `category` | User-defined grouping for review. |
| `priority` | Review priority: `high`, `medium`, or `low`. |
| `research_state` | Workflow state: `new`, `watching`, `review`, `done`, or `blocked`. |
| `notes` | Short analyst notes. |
| `thesis` | Working research thesis to verify. |
| `key_risks` | Main risks or uncertainty areas. |
| `watch_triggers` | Signals that should prompt another review. |
| `follow_up_questions` | Questions to answer before handoff. |
| `market_return_1d` | Optional descriptive 1-day market move for the dashboard Industry Map overlay. |
| `market_return_5d` | Optional descriptive 5-day market move for the dashboard Industry Map overlay. |
| `market_return_20d` | Optional descriptive 20-day market move for the dashboard Industry Map overlay. |
| `market_volume_signal` | Optional volume or liquidity observation to show in the Industry Map overlay. |
| `market_rotation_note` | Optional analyst note explaining the market-rotation context or missing data. |

Market-rotation fields are descriptive workflow inputs. They help the dashboard show coverage and recent movement context by category, but they are not recommendations, rankings, or trading signals.

## Industry Trend Price History

From v0.50.0 onward, the Industry Trend Report can calculate sector rotation context from a separate price-history CSV instead of relying only on manually filled research CSV overlay fields.

Required fields:

| Field | Purpose |
| --- | --- |
| `stock_id` | Taiwan stock identifier that matches the research CSV. |
| `date` | ISO date, for example `2026-05-29`. |
| `close` | Daily close price. |

Optional fields:

| Field | Purpose |
| --- | --- |
| `volume` | Daily volume used to estimate 5-day volume expansion or contraction. |
| `source` | Local source label for traceability, for example `fixture`, `manual`, or an internal data export name. |

The report calculates per-stock 1D, 5D, and 20D returns, 5-day volume ratio, category averages, leading/lagging descriptive rows, data blockers, and a non-advice notice. The output is written as JSON, Markdown, and HTML. It is still descriptive research context only; it does not rank sectors for investment action or produce buy, sell, hold, target price, or allocation recommendations.

## Industry Sentiment Cycle Methodology

From v0.53.0 onward, Market Intelligence uses methodology version `industry-sentiment-v1`. Current sentiment is a descriptive composite. Projection is deterministic and experimental. Peak/trough values are risk diagnostics, not probabilities, price targets, or exact dates.

All component and composite scores are clamped to `[-100, 100]`. Calculations retain full precision; displayed values are rounded to one decimal place only at the output boundary.

### Deterministic news component

The news scorer uses a versioned Traditional Chinese financial lexicon with positive, negative, negation, and intensity terms. It normalizes Unicode with NFKC, lowercases Latin text, collapses whitespace, and tokenizes with deterministic longest-match-first phrase scanning. Unmatched characters become single-character tokens; v1 does not use a runtime-dependent statistical tokenizer.

- Title weight is `0.65`; summary weight is `0.35`.
- A negation within three deterministic tokens flips the sign.
- The maximum intensity multiplier is `2.0`.
- The 5D exponential-recency half-life is `3` days; the 20D half-life is `7` days.
- Rows are deduplicated by canonical URL, falling back to normalized title.
- Each source is capped at `40%` of the uncapped recency-weight total for an industry.
- Weight clipped by the `40%` source cap remains neutral, unallocated coverage. It is never redistributed to the same one or two sources.
- Fewer than three mapped articles in a window produces a low-coverage warning.

News count, novelty, and repeated-topic concentration are turning-risk diagnostics. Repetition does not make positive news more positive. Topic concentration is the largest share assigned to one normalized event-keyword group; an article without an event keyword receives its own unique group.

### Price component

For window `w`, the price score is:

```text
return_term = clamp(industry_return_w / return_scale_w, -1, 1)
breadth_term = 2 * positive_breadth_w - 1
volume_term = sign(industry_return_w) * clamp(average_volume_ratio_5d - 1, 0, 1)
price_score_w = 100 * clamp(
    0.60 * return_term + 0.25 * breadth_term + 0.15 * volume_term,
    -1,
    1
)
```

The versioned bootstrap return scales are `8%` for 5D and `15%` for 20D. Return, breadth, and volume weights are `0.60/0.25/0.15`. The report also exposes positive-return breadth, average 5D volume ratio, 20-day high/low counts, and industry coverage ratios.

### Institutional-flow component

For each window:

```text
flow_ratio_w = sum(total institutional net shares_w) / sum(traded shares_w)
persistence_w = (buy_days - sell_days) / valid_flow_days
flow_score_w = 100 * clamp(
    0.75 * (flow_ratio_w / 0.05) + 0.25 * persistence_w,
    -1,
    1
)
```

`total institutional net shares` is the normalized sum of official foreign-investor, investment-trust, and dealer net-share fields. The ratio/persistence weights are `0.75/0.25`, and the flow-ratio scale is `0.05`.

The numerator and denominator use only matching `(date, stock_id)` pairs with official flow and positive traded-share volume. A valid session covers at least `60%` of the industry's price-covered mapped stocks. The latest 5 expected sessions require at least `3` valid sessions; the latest 20 require at least `10`. Unjoined rows are excluded rather than treated as zero, and the report exposes valid days, missing dates, joined and expected stocks, market coverage, net shares, traded shares, and persistence.

### Composite, labels, freshness, and confidence

Configured weights are:

```text
news = 0.40
price = 0.30
fund_flow = 0.30
```

A numeric composite requires at least two fresh usable components. With exactly two, their configured weights are renormalized to one and returned as `effective_weight`; status is `partial`, and confidence cannot be `high`. Fewer than two produces `insufficient_data` with no numeric composite. Missing, stale, invalid, or source-error inputs remain explicit and are never converted to zero or neutral evidence.

```text
score_5d = weighted mean of available 5D component scores
baseline_20d = weighted mean of available 20D component scores
change = score_5d - baseline_20d
```

Temperature is `warming` at `change >= 10`, `cooling` at `change <= -10`, and `stable` otherwise. Labels use these exact boundaries:

- `extremely_optimistic`: score `>= 60`
- `optimistic`: `20 <= score < 60`
- `neutral`: `-20 < score < 20`
- `pessimistic`: `-60 < score <= -20`
- `extremely_pessimistic`: score `<= -60`

Confidence measures source freshness and coverage, not the absolute score. Price and flow are fresh when their latest valid row is from the report's latest completed Taiwan market session or the immediately preceding expected session. News is fresh when at least one mapped article is from the previous 48 hours. Holidays do not create staleness merely by adding calendar days.

- `high`: all three components are fresh, news has at least five 5D articles, price coverage is at least `80%`, and flow has at least four valid 5D sessions.
- `medium`: at least two components are fresh and no required component has a source error.
- `low`: two components are usable, but one has weak coverage or a partial-source warning.
- No confidence label is emitted when fewer than two components are usable.

Every downgrade adds a human-readable warning.

### Cycle phase

Cycle classification is ordered and deterministic. The latest three valid daily composite snapshots, including the current snapshot, produce an ordinary least-squares `recent_slope`. It is positive at `>= +2` sentiment points per session, negative at `<= -2`, and flat otherwise. It is unavailable with fewer than three snapshots. Rules that require `recent_slope` do not fire when it is unavailable; they fall through to `consolidation` instead of inferring direction from the 5D/20D change.

Breadth expands when `breadth_5d - breadth_20d >= 0.10` and contracts when the difference is `<= -0.10`. A crowding warning exists when any of these exact conditions holds:

- top-quartile ranking streak `>= 5`;
- repeated-topic news concentration `>= 60%`;
- average 5D volume ratio `>= 1.8` while the absolute composite score is at least `60`.

A deceleration warning exists when the score is at least `50`, the prior three-snapshot slope was positive, and the current slope has fallen by at least `50%`. The negative-score rule is symmetric.

The seven predicates are evaluated in this exact order:

1. `overheating`: (`score >= 70` or (`trailing percentile >= 90` and ranking streak `>= 3`)) and at least one crowding or deceleration warning.
2. `capitulation`: score `<= -60` and `recent_slope` is negative.
3. `recovery`: score `<= 20`, change `>= 10`, and `recent_slope` is positive.
4. `ignition`: `-20 <= score < 40`, change `>= 10`, `recent_slope` is positive, and breadth is expanding.
5. `expansion`: `20 <= score < 70`, `recent_slope` is positive, and 5D breadth is at least `55%`.
6. `cooling`: score `> -20` and either change `<= -10`, or `recent_slope` is negative while breadth contracts.
7. `consolidation`: none of the earlier predicates matches.

Ranking streak counts consecutive snapshots in which the industry is in the top sentiment quartile. It uses only prior/current snapshots and is never reconstructed from future information.

### History and experimental projection

Each run writes one stable history row per `(as_of_date, category, methodology_version)` to `market-intelligence/industry_sentiment_history.csv`. A same-date rerun replaces that key deterministically instead of adding a duplicate. Runtime features read only snapshots with `as_of_date <= current as_of_date`; the current builder supplies strictly prior compatible history and then adds the current snapshot for calculation. Backtest-only future labels stay in the validation module and are never stored in runtime history.

Forecast is suppressed below `20` valid snapshots. With at least 20, it fits an exponentially weighted linear trend to the latest ten scores with a three-session half-life, then applies mean reversion toward the current 20D baseline:

```text
daily_step = 0.70 * forecast_slope_10d + 0.30 * ((baseline_20d - score_5d) / 20)
forecast_h = clamp(score_5d + h * daily_step, -100, 100)
```

The interval uses `robust_sigma = 1.4826 * MAD` from one-step residuals and displays `forecast_h +/- 1.96 * robust_sigma * sqrt(h)`, clamped to `[-100, 100]`. Fewer than ten residuals omits the interval with a warning. From 20-59 valid days, the report can show experimental 1D/5D projections but no turning window. At 60 or more, turning risk and a turning window can also appear. These projections are deterministic extrapolations, not calibrated probabilities.

### Peak/trough risk and validation boundary

Turning risk is suppressed below `60` valid snapshots. At or above that gate, define the current and prior slopes plus diagnostic contributions exactly as follows:

```text
slope_now = (score_t - score_t_minus_2) / 2
slope_prior = (score_t_minus_3 - score_t_minus_5) / 2

level_peak = 15 * clamp((score_t - 50) / 30, 0, 1)
           + 10 * clamp((percentile_t - 80) / 15, 0, 1)
level_trough = 15 * clamp((-score_t - 40) / 30, 0, 1)
             + 10 * clamp((20 - percentile_t) / 15, 0, 1)

momentum_peak = 25 * clamp(
    (slope_prior - slope_now) / max(abs(slope_prior), 2), 0, 1
) when slope_prior > 0, otherwise 0
momentum_trough = 25 * clamp(
    (slope_now - slope_prior) / max(abs(slope_prior), 2), 0, 1
) when slope_prior < 0, otherwise 0

breadth_peak = 20 * clamp((breadth_20d - breadth_5d) / 0.20, 0, 1)
               when score_t > 20, otherwise 0
breadth_trough = 20 * clamp((breadth_5d - breadth_20d) / 0.20, 0, 1)
                 when score_t < -20, otherwise 0

flow_peak = 15 * clamp((flow_score_20d - flow_score_5d) / 40, 0, 1)
            when score_t > 20, otherwise 0
flow_trough = 15 * clamp((flow_score_5d - flow_score_20d) / 40, 0, 1)
              when score_t < -20, otherwise 0
```

`percentile_t` uses the prior `60` valid snapshots plus the current snapshot; it never uses a future value. Peak crowding adds exactly 5 points for each true condition:

- top-quartile streak `>= 5`;
- repeated positive-topic concentration `>= 60%`;
- average 5D volume ratio `>= 1.8` with positive 5D return.

Trough capitulation is symmetric and adds exactly 5 points each for bottom-quartile streak `>= 5`, repeated negative-topic concentration `>= 60%`, and average 5D volume ratio `>= 1.8` with negative 5D return.

Peak risk is the bounded 0-100 sum of positive level/percentile (`0-25`), positive slope losing momentum (`0-25`), breadth deterioration (`0-20`), institutional-flow reversal (`0-15`), and crowding (`0-15`). Trough risk uses the symmetric negative level, downside deceleration, breadth recovery, selling exhaustion, and capitulation contributions with the same family caps. Each family is capped at its stated maximum.

A family agrees when its contribution reaches `40%` of its maximum: level `10`, momentum `10`, breadth `8`, flow `6`, and crowding/capitulation `6`. The window is `1_to_3_days` when risk `>= 70` and at least three families agree; `4_to_7_days` when risk is `50-69` and at least two families agree; and `unclear` otherwise. Direction is `peak` or `trough` for the qualifying side with higher risk. It is `unclear` when neither side qualifies or both sides exceed `50`. When both exceed `50`, the window is also `unclear` and a regime-uncertainty warning is required. Peak and trough risk may both be low.

Until calibration, these bounded 0-100 values are named `risk`, never `probability`, and `calibrated_probability` remains `null`. A window is an experimental diagnostic category, not a price target or exact turning date.

Future peak/trough labels exist only in `research sentiment-backtest`. A validation-only sentiment peak is the local maximum in a `+/-5`-session window followed by a fall of at least `15` points over the next five sessions. A trough is the symmetric local minimum followed by a rise of at least `15` points over the next five sessions. Runtime features and stable history never contain these future labels.

Validation uses expanding-window walk-forward evaluation by date; random train/test splits are prohibited. Each prediction receives only observations through its prediction date, so validation labels never leak into runtime inputs. Promotion from `experimental` requires all of these gates:

- at least `252` market sessions;
- at least `30` peak and `30` trough events in the pooled validation universe;
- an automated audit with no look-ahead or revised-input leakage;
- Brier score better than the unconditional event-rate baseline for both targets;
- precision and recall reported at the `50` and `70` risk thresholds;
- stable results in at least two non-overlapping holdout periods;
- a written model-validity report and separate human-reviewed promotion decision.

Failing any gate leaves the output in shadow mode. Thresholds are not tuned merely to obtain a pass, and `promotion_ready=true` in a validation artifact does not by itself change runtime status.

### Future LLM reviewer boundary

`NewsSentimentReviewer` is a typed protocol that accepts normalized news plus the deterministic assessment and returns a separate review payload. v1 has no default reviewer, LLM provider, SDK, API-key lookup, or runtime `llm_review`. A future implementation may add a separate `llm_review` payload, but it cannot overwrite `deterministic_score` without a later explicit, tested promotion policy.

## Valuation Method

Valuation output is scenario context. EPS scenarios and target PE values are combined into low, base, and high target-price scenarios. The valuation confidence score measures assumption completeness, not investment attractiveness.

## Review Workflow

1. Start with the offline demo to understand the output shape.
2. Create or edit a research CSV.
3. Run the research workflow.
4. Review source-audit status, reliability warnings, and diagnostics.
5. Review memo and pack outputs.
6. Compare valuation scenarios with source filings and manually confirmed assumptions.

## Source Audit and Manual Review

The source audit is a workflow control. It records whether financial statements and price inputs came from `live`, `fixture`, `offline`, `manual`, or `unknown` source modes, then classifies each item as `fresh`, `stale`, `unknown`, or `manual_review`.

`manual_review` is expected for fixture demos, offline prices, and user-supplied assumptions. It means the artifact can support local workflow review, but the underlying data should be checked against official filings, market data, or maintained internal assumptions before research handoff.

The source audit does not rank securities, approve data quality, or remove the need for accounting and source-document review. It only makes source freshness and review boundaries visible across workflow summaries, research packs, and dashboards.

## Review Actions

Review actions convert workflow state into a deterministic checklist. They can flag source-audit review, workflow failures, reliability warnings, missing valuation output, and missing high-priority research fields.

They are operational tasks only. They do not rank securities, approve a thesis, or create buy, sell, hold, or allocation recommendations.

## Disclaimer

All outputs are research workflow support only. They are not investment advice, recommendations, or decision labels.
