# Data Sources

Taiwan Equity Lens is a research workflow tool. It combines public financial statement pages, official market references, and user-provided assumptions.

## Goodinfo.tw

Used for annual financial statement pages:

- Income statement: `IS_YEAR`
- Balance sheet: `BS_YEAR`
- Cash flow statement: `CF_YEAR`

The parser is designed around the table format observed in these pages. If Goodinfo changes its layout, parsing can fail or produce missing fields. The tool keeps missing values as missing instead of silently converting them to zero.

## TWSE

Used by `price-template` for recent listed-stock closing prices through TWSE daily trading data.

This is not a real-time quote feed. If the source is unavailable, delayed, or does not contain a stock ID, the CSV keeps `price` blank and writes a warning.

## MOPS

Reports include a MOPS link for official filing verification. Taiwan Equity Lens does not currently parse MOPS financial statements directly.

## User-Provided CSV

Valuation inputs can be provided or edited through CSV:

- current price
- book value per share
- cash dividend per share
- normalized EPS
- target PE range
- EPS growth rate

These values are assumptions. The tool uses them to produce valuation scenarios, not predictions.

## Data Quality Rules

- Missing source data remains `None` or blank.
- Diagnostics are shown when key fields or metrics are missing.
- Batch analysis records per-stock failures instead of stopping the whole run.
- Outputs should be checked against official filings before use.
