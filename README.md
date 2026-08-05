# Taiwan Equity Lens

[![Tests](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml/badge.svg)](https://github.com/EricT1230/Taiwan-Equity-Lens/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.53.0-blue.svg)](CHANGELOG.md)

Taiwan Equity Lens is a local Taiwan stock fundamental-analysis workflow. It parses public annual financial statement pages, calculates quality and valuation context, and generates static HTML/JSON reports for research.

> This project is for research workflow support only. It does not provide investment advice. See [docs/disclaimer.md](docs/disclaimer.md).

## What It Does

- Generates single-stock HTML and JSON fundamental reports.
- Calculates profitability, growth, leverage, cash-flow, dividend, EPS, PE/PB, and valuation scenario metrics.
- Builds a quality scorecard with confidence handling.
- Produces data-quality diagnostics instead of silently hiding missing fields.
- Compares multiple stocks in a peer comparison report.
- Runs a watchlist workflow from CSV to reports, valuation template, comparison, dashboard, and workflow summary.
- Tracks a research CSV with priority, research state, notes, workflow status, and reliability context.
- Builds a universe-level review queue for deciding which research items need attention first.
- Overlays optional 1D/5D/20D market-rotation context on the industry research map.
- Generates an automatic Industry Trend Report from research universe and price-history CSV files, then feeds sector rotation context back into the dashboard.
- Generates deterministic Markdown or HTML research memos with executive summary, observations, risks, open questions, and next research actions.
- Generates consolidated Markdown and HTML research packs for local handoff and review.
- Carries working thesis, key risks, watch triggers, and follow-up questions through research summaries, memos, and packs.
- Adds lightweight traceability metadata so workflow, summary, memo, and pack outputs can be followed across a run.
- Tracks source mode, freshness, and source-audit status across workflow, pack, and dashboard outputs.
- Converts source-audit, reliability, valuation, and research-quality signals into deterministic review actions.
- Filters dashboard review actions by severity, category, priority, and search text.
- Persists review-action done, deferred, and ignored states in a local sidecar state file.
- Reports review-action state health, stale sidecar entries, and the next open actions from the CLI and dashboard.
- Guides dashboard handoff with an Expert Agent Console that shows readiness, the top 3 blockers, expert lenses, next actions, and a non-investment-advice notice; Top 3 blocker cards can be handled directly from the console.
- Adds a Next Action Workbench to the Expert Agent Console so the first screen shows one recommended primary button, post-action results, remaining gate blockers, and the next handoff step.
- Lets served dashboards create a local evidence markdown stub from the Next Action Workbench and mark the primary evidence-required blocker done in one flow.
- Shows a Reviewer Confidence gate and evidence preview after dashboard evidence creation so draft evidence is visible before final handoff.
- Checks handoff readiness with a reusable Handoff Quality Gate and `doctor handoff`, including open actions, stale state, missing required gate actions, and missing evidence on handled high-risk blockers.
- Generates a Handoff Evidence Pack with gate status, Top blockers, reviewer notes, evidence references, and non-investment-advice notice for final local review.
- Lets the dashboard generate or copy the Handoff Evidence Pack workflow, show output file paths, and point to missing evidence files before handoff.
- Shows a dashboard industry rotation map that groups research items by category, exposes stock-level evidence tasks in the selected sector, and validates the served HTTP evidence-update path without creating investment advice.
- Prunes stale review-action state entries explicitly with a dry-run-by-default CLI command.
- Backs up existing review-action state files before CLI writes.
- Lists available review-action state backup files before restore.
- Restores review-action state from explicit backup files after backing up the current state.
- Copies review-action state update commands directly from the static dashboard.
- Checks bundled demo output readiness with a local `doctor demo` command.
- Emits machine-readable demo doctor output with `doctor demo --json`.
- Opens the demo dashboard after a passing readiness check with `doctor demo --open`.
- Creates valuation CSV templates with TWSE first and TPEx fallback close-price lookup.
- Keeps reports fully local as static HTML and JSON.
- Builds a Market Intelligence Industry Map that joins price trend, current news keywords, and institutional fund flow with separate freshness gates.
- Imports official TWSE and TPEx company profiles, industry identity, daily price history, and institutional flow into one traceable market-data bundle.
- Scores current industry sentiment with the deterministic `industry-sentiment-v1` methodology and exposes component coverage, freshness, confidence, cycle phase, and missing-data reasons.
- Retains one daily sentiment snapshot per industry and provides experimental deterministic projections, peak/trough risk diagnostics, and a no-look-ahead walk-forward validation report.

## Quick Start

```powershell
git clone https://github.com/EricT1230/Taiwan-Equity-Lens.git
cd Taiwan-Equity-Lens
python -m pip install -e .
```

Run one stock:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir dist
```

Outputs:

- `dist/2330_raw_data.json`
- `dist/2330_analysis.html`

## One-Command Demo

Use the synthetic example fixtures and industry price-history sample for a fully offline local demo:

```powershell
python -m taiwan_stock_analysis.cli demo quickstart
```

The command prints the dashboard path and the next review-action commands. It also writes `demo-dist/industry-trends/industry_trend_report.json`, `.md`, and `.html`.

Verify that the demo produced the expected handoff files:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist
```

Open the dashboard after a passing check:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist --open
```

For scripts or CI:

```powershell
python -m taiwan_stock_analysis.cli doctor demo --output-dir demo-dist --json
```

Open:

```text
demo-dist/dashboard.html
```

## Connected Market Dashboard

Opening `dashboard.html` directly is only a static research snapshot. For live quotes, official news, attention／disposition lists, and institutional flow, run the same-origin local server:

```powershell
.\scripts\start-dashboard.ps1 -ScanDir demo-dist -Port 8877 -Open
```

The served page calls `/api/live/snapshot` automatically. It also loads `/api/market/breadth`, which joins the complete TWSE／TPEx company catalog with bulk official daily quotes, PE／PB／yield, quarterly EPS and operating results, monthly revenue, institutional flow, and attention／disposition events. The full-market response includes every listed and OTC company even when an upstream has no quote row; missing or suspended securities remain explicit instead of becoming zero-valued records. A first load must remain within 1% of the recently verified per-market catalog floor, and it cannot claim `EOD_FULL` unless both market counts meet the dated verified baseline. A later catalog that drops more than 1% cannot overwrite the last complete cache. The browser performs search, market／industry filters, sorting, and 25／50／100-row pagination over this full universe, while the per-page live adapter overlays only the currently visible symbols.

The loopback TWSE MIS development adapter and a local Fubon session refresh every 5 seconds during the Taiwan cash-market session; Fugle-backed and public pages use a minimum 30-second cadence. The full-market service keeps its official TWSE/TPEx catalog, EOD, valuation, and financial baseline for 300 seconds while refreshing only the Fubon price overlay every 5 seconds, so a live refresh does not refetch every official dataset. After close the page reports `EOD` and refreshes every 60 seconds. Every component exposes its own `LIVE`, `EOD`, `PARTIAL`, `STALE`, or `UNAVAILABLE` state, so fresh news cannot disguise a failed quote feed. A breadth snapshot is called full-market only when both TWSE and TPEx catalogs reconcile with the verified baseline. Its `EOD` status additionally requires dated quotes from both markets on the same latest completed session, calculated with the official TWSE holiday schedule and a 15:00 publication grace; future, undated, old, or cross-session rows are excluded from breadth signals. The quote lookback is limited to 15 calendar days, each upstream request has a 3-second timeout, and the complete cold-start breadth build has a 25-second service deadline. Incomplete alert or institutional batches are marked unknown and their authoritative filters are disabled rather than reporting a misleading zero. Valuation, financial-summary, and monthly-revenue sources are checked per market against catalog coverage; valuation dates must also match the latest completed session and are shown beside PE／PB／yield. `/api/market/health` separates process liveness from ready／usable cache state, and every breadth snapshot publishes per-market catalog plus quote, valuation, fundamental, revenue, institutional, alert, calendar, and industry coverage counts.

The loopback page also exposes `/api/us/market`. It joins Nasdaq Trader's official symbol-directory files with FINRA's latest published Consolidated NMS daily short-sale-volume file. This supplies a searchable U.S. reference universe plus the explicitly labelled `FINRA 場外短售成交比`; that ratio is not exchange-consolidated volume, a short position, or short interest. The public FINRA files are free for non-commercial use. U.S. price and return fields stay blank until a contracted price provider is configured, and this reference route is refused on non-loopback binds. The app does not scrape Nasdaq.com's internal website API or substitute mock prices.

The news component returns up to 96 validated exchange news and material-announcement rows per snapshot. The browser initially renders a compact batch and exposes a load-more control instead of permanently hiding everything after the first 12 rows.

The primary connected quote adapter is now Fubon Neo MarketData. It uses
[Fubon's API-key login](https://www.fbs.com.tw/TradeAPI/docs/trading/library/python/login/loginAPIKey/)
through the official Windows SDK, then reads only the
market-data session token; the application exposes no order-entry surface.
Install the pinned SDK into this project's `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-fubon-sdk.ps1
```

The installer targets this project's 64-bit Windows CPython 3.10 `.venv`.
It downloads the official `fubon-neo` 2.2.8 package, verifies the pinned
archive and wheel SHA-256 values, downloads every transitive runtime dependency
from a complete version-and-hash lock, and installs only those verified wheels.
The bootstrap first verifies and installs the pinned `pip` 26.1.2 wheel, so the
dependency lock is not processed by the older `pip` bundled with CPython 3.10.
It does not modify the system Python installation. Then open the project-root
`.env` in VS Code and fill in:

```dotenv
MARKET_DATA_PROVIDER=fubon
FUBON_PERSONAL_ID=your-personal-id
FUBON_API_KEY=your-market-data-only-api-key
FUBON_CERT_PATH=C:\absolute\path\to\your\certificate.pfx
FUBON_CERT_PASSWORD=your-certificate-password
FUBON_MARKET_DATA_ONLY_CONFIRMED=1
FUBON_REDISPLAY_LICENSED=0
```

Use a
[market-data-only API key and an IP allowlist](https://www.fbs.com.tw/TradeAPI/docs/trading/api-key-apply/)
in the Fubon developer portal. Keep the certificate outside the repository and point
`FUBON_CERT_PATH` at it. The `.env` file and `.env.*` variants are ignored by
Git, the credentials and SDK session token are never returned to the browser,
and errors are sanitized before they are logged. Set
`FUBON_MARKET_DATA_ONLY_CONFIRMED=1` only after the broker portal shows that
this dedicated key has market-data access, no trading scope, and the intended
IP allowlist. The SDK does not expose a reliable local scope-inspection API, so
this operator confirmation is a required fail-closed deployment gate.

Verify the provider before opening the dashboard:

```powershell
.\.venv\Scripts\python.exe -m taiwan_stock_analysis.cli doctor market-data --provider fubon --symbol 2330 --json
.\scripts\start-dashboard.ps1 -ScanDir demo-dist -Port 8877 -Open
```

The CLI reads `.env` once at startup. Existing process environment variables
take precedence, and an explicit `--market-data-provider` or doctor
`--provider` argument takes precedence over `MARKET_DATA_PROVIDER`. Only the
documented app settings in `.env.example` are accepted; unrelated variables
are ignored. Restart the dashboard after editing `.env`.

The `fubon` policy is fail-closed: a missing certificate, missing
market-data-only confirmation, rejected login, missing entitlement, unsupported
SDK version, or HTTP 401/403 makes quotes `UNAVAILABLE`. Authentication
failures never fall back to cached rows or TWSE MIS. They also open a
process-shared 60-second authentication circuit breaker with bounded
exponential backoff, preventing a broken credential from causing a rapid login
loop. Temporary network failures may expose an explicitly `STALE` cache, never
`LIVE`. The doctor command performs a real Fubon login plus market-data request
and returns sanitized connection evidence.

The adapter fetches Fubon's
[provider-native TSE and OTC bulk snapshots](https://www.fbs.com.tw/TradeAPI/docs/market-data/http-api/snapshot/quotes/)
rather
than issuing roughly two thousand per-symbol requests. The full-market
screener preserves TWSE/TPEx official EOD catalog, fundamentals, and financial
data as its completeness baseline, then overlays Fubon prices only when each
row and both market snapshots pass freshness checks. Live and EOD coverage are
reported separately; a partial feed cannot claim full-market live status.
TAIEX and TPEx benchmark symbols are discovered from the index ticker endpoint.
If an account uses different identifiers, set `FUBON_TAIEX_SYMBOL` and
`FUBON_TPEX_SYMBOL`.

Fubon traffic is guarded by a conservative 240-calls-per-minute process
budget, four-request concurrency limit, short negative cache, and a bounded
request deadline, below the provider's documented
[300 requests/minute limit](https://www.fbs.com.tw/TradeAPI/docs/market-data/rate-limit/)
for intraday and snapshot APIs. Run only one dashboard or provider doctor at a
given login; the in-process limiter cannot coordinate separate machines or
processes against an account-wide provider quota.

A personal brokerage market-data entitlement is not public redisplay
permission. For a public or multi-user deployment, first obtain written Fubon
and exchange redisplay permission, then configure:

```dotenv
MARKET_DATA_PROVIDER=fubon
FUBON_REDISPLAY_LICENSED=1
```

```powershell
.\.venv\Scripts\python.exe -m taiwan_stock_analysis.cli doctor market-data --provider fubon --symbol 2330 --public --json
.\.venv\Scripts\python.exe -m taiwan_stock_analysis.cli dashboard --scan-dir demo-dist --serve --host 127.0.0.1 --port 8877 --public-read-only
```

Legacy Fugle MarketData v1 settings remain available as an explicit alternate
provider in `.env.example`; they are not selected when
`MARKET_DATA_PROVIDER=fubon`.

A non-loopback bind is deliberately read-only: it can serve the dashboard and live snapshot, but all review-state, evidence, and handoff file-writing endpoints return `403`. A public snapshot accepts at most 20 symbols and rejects larger requests instead of silently truncating them. Public pages poll no faster than every 30 seconds and each connecting client is limited to two snapshot requests per minute. The shared provider-entry budget follows the active adapter's conservative capability report: a Fubon bulk request reserves six units, while a Fugle request reserves one unit per requested symbol plus four units for benchmark discovery and quotes. `429` responses include `Retry-After`, which the browser honors. Live snapshot assembly runs through a bounded worker pool. Full-market breadth refreshes use a separate single-flight worker, so an expired multi-source refresh cannot starve visible live quotes; a failed refresh is negative-cached briefly before retry. Both routes return bounded `504` deadline responses or generic JSON `500` errors instead of leaving an unbounded request thread or resetting the connection.

Do not expose the built-in `ThreadingHTTPServer` directly to the internet. Bind it to `127.0.0.1` behind an authenticated reverse proxy that terminates TLS, restricts access to approved users, forwards only the required dashboard and read-only live routes, and applies its own user/IP quotas. `--public-read-only` is mandatory behind the proxy so public redisplay checks and write blocking do not depend on the bind address. The CLI refuses a non-loopback bind unless the operator adds the explicit high-risk `--allow-direct-network-bind` acknowledgement; a cross-host proxy setup also requires firewall／ACL rules that prevent clients from reaching this port directly. Keep write endpoints loopback-only; do not use a proxy to bypass their `403` boundary. File operations remain available only in local desktop mode and require `Content-Type: application/json`. TWSE／TPEx OpenAPI remain the source for exchange news, material announcements, attention/disposition lists, and daily institutional flow.

The generated dashboard is now a desktop-first market research application with seven workspaces:

- `今日總覽`: market regime, temperature, breadth, institutional flow, event radar, and a guided three-step workflow.
- `產業地圖`: industry heatmap, sentiment composition, rotation, news, and fund-flow evidence.
- `智慧選股`: explainable filters for bullish research, bearish risk, disposition, industry, and US connectors.
- `市場情報`: source-linked news, financial review summaries, and a local market notebook.
- `市場策略`: transparent regime playbooks with prerequisites and invalidation rules.
- `研究工作台`: the existing evidence, review-action, and handoff quality workflow.
- `資料與紀錄`: report paths, source audit, market-data coverage, and traceability.

Static demo values are clearly labeled as a snapshot. The connected industry view is currently a 36-category official industry heatmap, not a 240+ theme or upstream／downstream supply-chain graph. The US screener uses the Nasdaq Trader directory and FINRA non-commercial short-volume reference data; it does not claim to provide U.S. prices until a licensed price feed is connected. Empty disposition results stay unknown or disabled when the official source is incomplete; the UI does not invent live market data.

Demo outputs:

- `demo-dist/reports/`
- `demo-dist/valuation.csv`
- `demo-dist/valuation-reports/`
- `demo-dist/comparison/`
- `demo-dist/memos/`
- `demo-dist/packs/`
- `demo-dist/dashboard.html`
- `demo-dist/workflow_summary.json`
- `demo-dist/research_summary.json`
- `demo-dist/market-intelligence/market_intelligence_report.json`
- `demo-dist/market-intelligence/market_intelligence_report.md`
- `demo-dist/market-intelligence/market_intelligence_report.html`
- `demo-dist/market-intelligence/industry_sentiment_history.csv`

First review-action checks:

```powershell
python -m taiwan_stock_analysis.cli research action list demo-dist/research_summary.json --state demo-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action report demo-dist/research_summary.json --state demo-dist/review_action_state.json
python -m taiwan_stock_analysis.cli research action set demo-dist/review_action_state.json 2330 source-audit-manual-review --status done --note "checked source freshness" --reviewer "source-audit-lead" --evidence-url "demo-dist/evidence/2330-source.md"
python -m taiwan_stock_analysis.cli research handoff-pack demo-dist/research_summary.json --state demo-dist/review_action_state.json --output-dir demo-dist/handoff-pack
python -m taiwan_stock_analysis.cli research action backups demo-dist/review_action_state.json
```

The first `set` command creates `demo-dist/review_action_state.json`. Later state-changing commands back up the existing valid state before writing.

Equivalent lower-level command:

```powershell
python -m taiwan_stock_analysis.cli research run examples/research.csv --fixture-root examples/fixtures --output-dir demo-dist --offline-prices
```

## Common Commands

Batch analyze a watchlist:

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

Compare multiple stocks:

```powershell
python -m taiwan_stock_analysis.cli compare 2330 2303 2454 --output-dir compare-dist
```

Generate a valuation CSV template:

```powershell
python -m taiwan_stock_analysis.cli price-template 2330 2303 --analysis-dir dist --output valuation.csv
```

Run a valuation-aware report:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

Create a research workbench CSV:

```powershell
python -m taiwan_stock_analysis.cli research init --output research.csv
```

Run the research workflow:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --offline-prices
```

Regenerate a research summary from existing workflow outputs:

```powershell
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json
```

Generate an industry trend report from a research universe and price-history CSV:

```powershell
python -m taiwan_stock_analysis.cli research industry-trends research.csv --price-history industry_price_history.csv --output-dir research-dist/industry-trends
python -m taiwan_stock_analysis.cli research summary research.csv --workflow-dir research-dist --output research-dist/research_summary.json --industry-trend-report research-dist/industry-trends/industry_trend_report.json
```

Combine the industry trend report with news, automatic keyword matching, and institutional fund flow:

```powershell
python -m taiwan_stock_analysis.cli research market-intelligence research.csv --industry-trend-report research-dist/industry-trends/industry_trend_report.json --news-csv market_news.csv --fund-flow-csv fund_flow.csv --as-of 2026-07-17T18:00:00+08:00 --output-dir research-dist/market-intelligence
python -m taiwan_stock_analysis.cli research sentiment-backtest research-dist/market-intelligence/industry_sentiment_history.csv --output research-dist/market-intelligence/sentiment_backtest_report.json
```

The Market Intelligence rerun replaces the existing snapshot with the same `(as_of_date, category, methodology_version)` key; it does not append a duplicate. The backtest remains `experimental` when promotion gates fail and still exits successfully for a valid report. Its future peak/trough labels exist only in validation and are never written into runtime reports or stable history.

Current sentiment is a descriptive composite. Its projection is deterministic and experimental. Peak/trough values are risk diagnostics, not probabilities, price targets, or exact dates. Inspect component coverage, freshness, warnings, and confidence before using an artifact; file existence alone does not establish live-data readiness.

Use the official TWSE news and T86 adapters, plus any additional RSS/Atom feeds:

```powershell
python -m taiwan_stock_analysis.cli research market-intelligence research.csv --industry-trend-report research-dist/industry-trends/industry_trend_report.json --fetch-twse-news --fetch-twse-fund-flow --news-feed https://example.com/feed.xml --output-dir research-dist/market-intelligence
```

Add `news_keywords` to the research CSV as a `|`-separated alias list, for example `TSMC|台積電|晶圓代工|AI|CoWoS`. The report preserves unmapped news so taxonomy gaps remain visible.

Fetch an official cross-market data bundle for the research universe:

```powershell
python -m taiwan_stock_analysis.cli research market-data research.csv --output-dir research-dist/market-data --history-months 3
```

Run the full workflow with automatic official price refresh, industry identity, listed/OTC institutional flow, baseline TWSE news, Industry Trend, and Market Intelligence:

```powershell
python -m taiwan_stock_analysis.cli research run research.csv --output-dir research-dist --fetch-market-data --market-data-history-months 3
```

The importer writes `research_official.csv` with `official_market`, `official_industry_code`, and `official_industry_name`. Custom research categories are preserved unless `--replace-category` or `--replace-category-with-official` is explicitly used.

Generate a single research memo from existing analysis JSON:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name TSMC --output-dir memo-dist
python -m taiwan_stock_analysis.cli memo memo-dist/2330_raw_data.json --output memos/2330_memo.md
```

Generate research memos from a research workflow directory:

```powershell
python -m taiwan_stock_analysis.cli research memo research.csv --workflow-dir research-dist --output-dir research-dist/memos
```

Generate a consolidated research pack:

```powershell
python -m taiwan_stock_analysis.cli research pack research.csv --workflow-dir research-dist --output-dir research-dist/packs
```

Generate a dashboard from existing outputs:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir dist --scan-dir batch-dist --scan-dir compare-dist --scan-dir workflow-dist --output dashboard-index.html
```

Run an interactive local dashboard with review-action API buttons:

```powershell
python -m taiwan_stock_analysis.cli dashboard --scan-dir demo-dist --serve --port 8765 --open
```

Check release readiness before tagging:

```powershell
python -m taiwan_stock_analysis.cli doctor release --version 0.53.0
```

## Example Files

- [examples/watchlist.csv](examples/watchlist.csv): sample watchlist for batch/workflow runs.
- [examples/valuation.csv](examples/valuation.csv): sample valuation assumptions.
- [examples/research.csv](examples/research.csv): sample research workbench universe.
- [examples/industry_price_history.csv](examples/industry_price_history.csv): synthetic price-history input for Industry Trend Report demos.
- [examples/research_cross_market.csv](examples/research_cross_market.csv): listed plus OTC universe for live official-import validation.
- [examples/fixtures/](examples/fixtures): synthetic financial-statement HTML for offline demos.
- [examples/README.md](examples/README.md): example command guide.

## Output Surfaces

Single-stock reports use Traditional Chinese sections for:

- KPIs
- quality score
- valuation scenarios
- data quality
- data reliability
- source audit and manual-review status
- operating observations
- profitability observations
- financial health observations

Research memos add a review-oriented layer for:

- executive summary
- key observations
- catalysts and risks
- open questions
- grouped next research actions

The workflow dashboard shows:

- workflow summary status
- data reliability status
- source audit status and per-stock review reasons
- successful and failed batch rows
- valuation CSV link
- comparison output or skipped reason
- report and JSON links

When a `research_summary.json` is present, the dashboard also shows:

- research item counts by state and priority
- stocks that need review because of research state, workflow status, or reliability warnings
- an industry rotation map that groups the research universe by `category`, highlights handoff blockers and evidence gaps, and links back to the matching review-action tasks
- a universe review queue for high-attention and blocked research items
- links back to generated workflow and research outputs
- links to generated Markdown and HTML research memos when memo outputs are present
- links to generated Markdown and HTML research packs when pack outputs are present

## Data Reliability

Generated workflow outputs include a reliability summary that explains which steps succeeded, which inputs used fallback sources, and which stocks failed or were skipped. They also include `source_audit` details that identify source mode, freshness status, and manual-review requirements for financial statements and prices.

Summary files also expose a lightweight traceability layer:

- `run_id`
- `generated_at`
- artifact dependencies
- downstream outputs derived from the same run

The source-audit layer uses source modes such as `live`, `fixture`, `offline`, `manual`, and `unknown`, and freshness statuses such as `fresh`, `stale`, `unknown`, and `manual_review`. Fixture, offline, and manually supplied data remain usable, but are flagged for review before research handoff.

Research summaries include a `universe_review` object for work prioritization. It groups the research universe by category, state, and priority, then builds a deterministic attention queue. This is a research workflow queue, not a portfolio ranking or investment recommendation.

Research summaries also include `review_actions`, `review_action_summary`, and `review_action_queue` so handoff artifacts show concrete source, workflow, reliability, valuation, and research-quality checks.

The project uses four status values:

- `ok`: the stage completed without detected data issues
- `warning`: output is usable, but a fallback, stale date, or missing field was detected
- `error`: the stage could not produce output
- `skipped`: the stage did not run because it was disabled or a prerequisite failed

Single-stock reports and dashboards surface the same reliability context, including price source status, workflow failure reasons, retry hints, source-audit status, and valuation assumption labels.

## Research Workflow

The research workbench starts from a CSV with `stock_id`, `company_name`, `category`, `priority`, `research_state`, and `notes`. It converts the research universe to the existing watchlist workflow, keeps research metadata in `research_summary.json`, and refreshes the static dashboard for local review.

Use `research init` to create an editable template, `research run` to produce reports and summaries from the CSV, and `research summary` to rebuild the research JSON after reviewing existing workflow outputs. The workflow is for organizing research status and data reliability review; it does not produce buy, sell, hold, or allocation recommendations.

By default, `research run` also writes memo files under `research-dist/memos/` and handoff packs under `research-dist/packs/`. Packs and dashboards surface the workflow source audit so fixture, offline, stale, unknown, or manually supplied data is visible during handoff. Pass `--skip-memos` to skip memo files or `--skip-packs` to skip pack files.

## Data Sources

See [docs/data-sources.md](docs/data-sources.md).

Current sources and inputs:

- Goodinfo annual financial statement pages
- TWSE listed-stock daily close data
- TPEx OTC daily close data as fallback
- MOPS links for manual official filing verification
- user-provided valuation CSV assumptions
- user-provided industry price-history CSV for sector rotation reporting
- user-provided news and institutional fund-flow CSV snapshots
- configurable RSS/Atom news feeds
- TWSE News OpenAPI and TWSE T86 institutional trading report
- TWSE company profile, industry EPS classification, and monthly `STOCK_DAY` history
- TPEx company profile, industry EPS classification, monthly `tradingStock` history, and three-institution daily trading

## Documentation

- [Research methodology](docs/research-methodology.md)
- [Usage workflow](docs/usage-workflow.md)
- [Data sources](docs/data-sources.md)
- [Project win condition](docs/project-win-condition.md)
- [Disclaimer](docs/disclaimer.md)
- [Changelog](CHANGELOG.md)
- [v0.53.0 release notes](docs/releases/v0.53.0.md)
- [v0.50.0 release notes](docs/releases/v0.50.0.md)
- [v0.49.0 release notes](docs/releases/v0.49.0.md)
- [v0.48.0 release notes](docs/releases/v0.48.0.md)
- [v0.47.0 release notes](docs/releases/v0.47.0.md)
- [v0.46.0 release notes](docs/releases/v0.46.0.md)
- [v0.45.0 release notes](docs/releases/v0.45.0.md)
- [v0.44.0 release notes](docs/releases/v0.44.0.md)
- [v0.43.0 release notes](docs/releases/v0.43.0.md)
- [v0.42.0 release notes](docs/releases/v0.42.0.md)
- [v0.41.0 release notes](docs/releases/v0.41.0.md)
- [v0.40.0 release notes](docs/releases/v0.40.0.md)
- [v0.39.0 release notes](docs/releases/v0.39.0.md)
- [v0.38.0 release notes](docs/releases/v0.38.0.md)
- [v0.37.0 release notes](docs/releases/v0.37.0.md)
- [v0.36.0 release notes](docs/releases/v0.36.0.md)
- [v0.35.0 release notes](docs/releases/v0.35.0.md)
- [v0.34.0 release notes](docs/releases/v0.34.0.md)
- [v0.33.0 release notes](docs/releases/v0.33.0.md)
- [v0.32.0 release notes](docs/releases/v0.32.0.md)
- [v0.31.0 release notes](docs/releases/v0.31.0.md)
- [v0.30.0 release notes](docs/releases/v0.30.0.md)
- [v0.29.0 release notes](docs/releases/v0.29.0.md)
- [v0.28.0 release notes](docs/releases/v0.28.0.md)
- [v0.27.0 release notes](docs/releases/v0.27.0.md)
- [v0.26.0 release notes](docs/releases/v0.26.0.md)
- [v0.25.0 release notes](docs/releases/v0.25.0.md)
- [v0.24.0 release notes](docs/releases/v0.24.0.md)
- [v0.23.0 release notes](docs/releases/v0.23.0.md)
- [v0.22.0 release notes](docs/releases/v0.22.0.md)
- [v0.21.0 release notes](docs/releases/v0.21.0.md)
- [v0.20.0 release notes](docs/releases/v0.20.0.md)
- [v0.19.0 release notes](docs/releases/v0.19.0.md)
- [v0.18.0 release notes](docs/releases/v0.18.0.md)
- [v0.17.0 release notes](docs/releases/v0.17.0.md)
- [v0.16.0 release notes](docs/releases/v0.16.0.md)
- [v0.15.0 release notes](docs/releases/v0.15.0.md)
- [v0.14.0 release notes](docs/releases/v0.14.0.md)
- [v0.13.0 release notes](docs/releases/v0.13.0.md)
- [v0.12.0 release notes](docs/releases/v0.12.0.md)
- [v0.11.0 release notes](docs/releases/v0.11.0.md)
- [v0.10.0 release notes](docs/releases/v0.10.0.md)
- [v0.9.1 release notes](docs/releases/v0.9.1.md)
- [v0.9.0 release notes](docs/releases/v0.9.0.md)
- [v0.8.0 release notes](docs/releases/v0.8.0.md)
- [v0.7.0 release notes](docs/releases/v0.7.0.md)
- [v0.6.0 release notes](docs/releases/v0.6.0.md)
- [v0.5.0 release notes](docs/releases/v0.5.0.md)
- [v0.4.0 release notes](docs/releases/v0.4.0.md)
- [v0.3.0 release notes](docs/releases/v0.3.0.md)
- [v0.2.0 release notes](docs/releases/v0.2.0.md)

## Verify

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

## Project Structure

```text
src/taiwan_stock_analysis/
|-- cli.py            # CLI orchestration
|-- comparison.py     # peer comparison model
|-- dashboard.py      # static dashboard renderer
|-- diagnostics.py    # data quality diagnostics
|-- fetcher.py        # Goodinfo network boundary
|-- insights.py       # Traditional Chinese trend observations
|-- market_price.py   # TWSE/TPEx valuation price template helper
|-- market_data_importer.py # official TWSE/TPEx taxonomy, price history, and flow importer
|-- market_intelligence.py  # news, keywords, trend, and capital-flow industry context
|-- memo.py           # Markdown and HTML research memo renderer
|-- pack.py           # consolidated research pack renderer
|-- traceability.py   # run metadata and artifact registry helpers
|-- metrics.py        # fundamental metric calculations
|-- models.py         # dataclasses
|-- parser.py         # HTML table parser
|-- price_data.py     # valuation CSV loader
|-- research.py       # research CSV and summary helpers
|-- reliability.py    # data reliability status model
|-- report.py         # single-stock HTML renderer
|-- report_compare.py # comparison HTML renderer
|-- score_rules.py    # scorecard rules
|-- scoring.py        # scorecard builder
|-- trends.py         # YoY / CAGR / trend helpers
|-- valuation.py      # PE/PB/yield/scenario valuation
|-- verification.py   # sanity checks
|-- workflow.py       # watchlist workflow orchestration
`-- watchlist.py      # watchlist CSV loader
```

## License

MIT License. See [LICENSE](LICENSE).
