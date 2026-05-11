# Contributing

Thanks for helping improve Taiwan Equity Lens. This project is a financial research CLI, so changes should favor reproducible outputs, clear assumptions, and conservative wording.

## Ground Rules

- Do not present generated analysis as investment advice or a trading recommendation.
- Keep source attribution visible when adding or changing financial data inputs.
- Prefer deterministic tests and local fixtures over live network calls.
- Keep changes scoped. Documentation, parser, CLI, report, and data-source changes should be easy to review independently.

## Development Setup

```powershell
python -m pip install -e .
```

Run the test suite before opening a pull request:

```powershell
python -m unittest discover -s tests -v
```

For CLI smoke testing, use a fixture or a small output directory:

```powershell
$env:PYTHONPATH='src'
python -m taiwan_stock_analysis.cli 2330 --fixture fixtures --output-dir dist
```

## Contribution Flow

1. Open or find an issue that describes the change.
2. Keep the implementation focused on one behavior or document set.
3. Add or update tests for parser, metrics, valuation, diagnostics, CLI, or report behavior when applicable.
4. Run `python -m unittest discover -s tests -v`.
5. Open a pull request with the motivation, test results, and any data-source assumptions.

## Adding or Changing Data Sources

When adding a data source or changing how a source is parsed:

- Document the source name, URL pattern, fields consumed, and any known limitations.
- Keep raw fetched data and parsed output separate where practical.
- Add fixtures that represent realistic source HTML, CSV, or JSON.
- Handle missing, renamed, or malformed fields with clear diagnostics instead of silent failures.
- Avoid embedding credentials, session cookies, or private API keys.
- Respect source terms, rate limits, and robots or access restrictions.

Data-source breakage should normally be handled as a bug report, not as a security report. If a source issue can cause unsafe local file access, command execution, credential exposure, or another direct security impact, report it through the security process in `SECURITY.md`.

## Financial Disclaimer

Taiwan Equity Lens is for research support only. Outputs may be incomplete, delayed, or wrong. Contributors should avoid language that tells users to buy, sell, hold, or rely on the tool as a substitute for professional advice.
