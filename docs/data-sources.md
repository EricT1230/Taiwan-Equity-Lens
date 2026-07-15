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

This is not a real-time quote feed. If the source is unavailable, delayed, or does not contain a stock ID, the tool attempts the TPEx source before leaving `price` blank.

## TPEx

Used by `price-template` as the fallback source for mainboard OTC stock closing prices when TWSE does not return a valid price.

The TPEx parser reads daily close quote rows and records `price_source` as `TPEX_DAILY_CLOSE` when a TPEx price is used. If neither TWSE nor TPEx can provide a valid closing price, the CSV keeps `price` blank and writes a warning.

## Source Freshness and Fallbacks

Price data can be marked `ok` when the primary source succeeds or `warning` when fallback behavior, missing values, or source warnings are detected.

Generated valuation CSV templates include:

- `price_date`
- `price_source`
- `price_status`
- `price_status_message`
- `price_retry_hint`

A warning does not mean the report is invalid. It means the source path should be reviewed before relying on the valuation context.

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

## Fundamental Expert Review

From v0.34.0 onward, `research_summary.json` can include a `fundamental_review` object for each research item. This layer is deterministic and uses existing generated raw analysis JSON, research CSV fields, valuation scenarios, source audit status, and reliability status.

The review checks moat evidence, fundamental quality, bear-case risk, and valuation margin-of-safety inputs. It creates workflow review tasks when data is incomplete or a manual check is needed. These checks are research workflow support only and do not constitute investment advice, buy/sell/hold advice, target-price promises, or position-sizing guidance.

## Data Quality Rules

- Missing source data remains `None` or blank.
- Diagnostics are shown when key fields or metrics are missing.
- Batch analysis records per-stock failures instead of stopping the whole run.
- Outputs should be checked against official filings before use.

## Market Intelligence Sources

The Market Intelligence Industry Map supports deterministic local CSV inputs and optional network adapters:

- TWSE News OpenAPI (`/v1/news/newsList`) for exchange announcements and news.
- TWSE T86 for daily listed-market foreign, investment-trust, dealer, and combined net trading by security.
- User-configured RSS or Atom feeds for broader current-events coverage.
- User-provided `market_news.csv` and `fund_flow.csv` snapshots for reproducible research and testing.

The TWSE news adapter is not a complete financial-news corpus, and T86 covers the TWSE listed market rather than every TPEx security. The report therefore shows source coverage, unmapped news, and missing research-stock flow rows instead of implying complete market coverage.

News freshness, fund-flow freshness, and industry-price freshness are evaluated independently. A combined report with missing or stale source families is marked `needs_data`.

## Official Market Data Importer

`research market-data` resolves each research stock against both official markets:

- TWSE `t187ap03_L` company profiles and `t187ap14_L` industry names.
- TWSE monthly `STOCK_DAY` daily price history.
- TPEx `mopsfin_t187ap03_O` company profiles and `mopsfin_t187ap14_O` industry names.
- TPEx monthly `tradingStock` daily price history.
- TWSE T86 and TPEx `tpex_3insti_daily_trading` institutional flow.

The importer preserves both research taxonomy and official taxonomy. It writes official market, industry code, and industry name into a separate enriched research CSV. Blank or `Uncategorized` categories adopt the official industry name; existing analytical categories are only replaced when explicitly requested.

The official-import quality gate requires at least 21 price points per research stock because the Industry Trend Report needs a complete 20-trading-day comparison window.
