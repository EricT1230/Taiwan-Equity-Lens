# Report Polish Design

## Goal

Phase 16B improves the single-stock HTML report so it is readable, structured, and consistent with the polished dashboard. The work is presentation-only.

## Scope

The report renderer will keep the existing `render_html_report(result, company_name=None)` API and continue embedding the full analysis JSON. It will replace corrupted labels with Traditional Chinese, add readable empty states, and make scorecard, valuation, diagnostics, and insights easier to scan.

## User Experience

The report should answer:

1. What stock and years does this report cover?
2. What are the latest core metrics?
3. What is the quality score and confidence?
4. Is valuation context available?
5. Are there data quality warnings?
6. What are the main operating, profitability, and financial health observations?

## Architecture

Keep `report.py` as the single static HTML renderer. Use private helpers for KPI cards, tables, empty states, scorecard, valuation, diagnostics, source links, and insights. Do not introduce JavaScript behavior or frontend dependencies.

## Non-Goals

- Do not change `AnalysisResult`.
- Do not change metrics, scorecard, valuation, diagnostics, or insight generation.
- Do not add charts or external UI libraries.
- Do not add investment advice language.
- Do not alter JSON output.

## Testing

Tests should assert:

- clean Traditional Chinese title and section labels
- key KPI values still render
- scorecard, valuation, diagnostics, and source links still render
- empty insights and missing valuation produce readable empty states
- embedded JSON remains available
