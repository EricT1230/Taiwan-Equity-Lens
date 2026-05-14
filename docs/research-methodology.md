# Research Methodology

Taiwan Equity Lens is a deterministic research workflow for Taiwan equity fundamental analysis. It organizes public financial-statement data, user-provided valuation assumptions, and research notes into reviewable artifacts.

## What The Tool Does

- Parses annual income statement, balance sheet, and cash-flow statement pages.
- Calculates profitability, growth, leverage, cash-flow, dividend, EPS, and valuation scenario metrics.
- Produces JSON, HTML, Markdown, dashboard, memo, pack, and comparison outputs.
- Preserves research notes, thesis fields, risks, triggers, and follow-up questions from the research CSV.

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

## Disclaimer

All outputs are research workflow support only. They are not investment advice, recommendations, or decision labels.
