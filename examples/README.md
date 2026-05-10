# Examples

## Watchlist

Use `watchlist.csv` for batch analysis:

```powershell
python -m taiwan_stock_analysis.cli batch examples/watchlist.csv --output-dir batch-dist
```

## Valuation

Use `valuation.csv` for valuation-aware reports:

```powershell
python -m taiwan_stock_analysis.cli 2330 --company-name 台積電 --valuation-csv examples/valuation.csv --output-dir valuation-dist
```

The valuation file contains scenario assumptions. Edit prices, EPS, PE ranges, and growth rates before relying on the report.
