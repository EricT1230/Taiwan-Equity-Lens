# Security Policy

Taiwan Equity Lens is a financial research CLI and report generator. It does not provide investment advice, trading recommendations, or a guarantee that any data source is complete, current, or suitable for a specific decision.

## Reporting Security Issues

Please do not open a public issue for a suspected security vulnerability.

To report a security issue:

1. Use GitHub private vulnerability reporting if it is enabled for this repository.
2. If private reporting is not available, open a public issue that asks the maintainer to enable a private security contact, but do not include vulnerability details in that issue.
3. Include the affected version or commit, steps to reproduce, expected impact, and any proof-of-concept details that are safe to share.

We will acknowledge valid reports as soon as practical and coordinate a fix before public disclosure.

## What Counts as a Security Issue

Examples of security issues include:

- Unsafe file writes outside the requested output path.
- Command execution, path traversal, or template injection.
- Leaking credentials, local files, or private environment variables.
- Dependency or packaging behavior that can compromise a user's machine.

## Data Source Issues

Data quality problems are important, but they are usually not security vulnerabilities. Examples include:

- Goodinfo, TWSE, or other source pages changing format.
- Missing, stale, or inconsistent financial fields.
- Incorrect ratios, valuation assumptions, or report warnings.
- Network failures, rate limits, or source availability issues.

Please report those as normal bugs or data-source issues, with the stock ID, command used, source URL if available, and the generated output that looks wrong.

## Responsible Use

This project is for research and reproducible analysis workflows. Users are responsible for validating outputs against primary sources before making any financial decision.
