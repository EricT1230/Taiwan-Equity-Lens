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
4. Review reliability warnings and diagnostics.
5. Review memo and pack outputs.
6. Compare valuation scenarios with source filings and manually confirmed assumptions.

## Disclaimer

All outputs are research workflow support only. They are not investment advice, recommendations, or decision labels.
