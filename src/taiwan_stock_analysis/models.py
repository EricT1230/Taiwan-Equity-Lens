from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FinancialTable = dict[str, dict[str, float | None]]
MetricsByYear = dict[str, dict[str, float | None]]


@dataclass(slots=True)
class AnalysisResult:
    stock_id: str
    years: list[str]
    income_statement: FinancialTable = field(default_factory=dict)
    balance_sheet: FinancialTable = field(default_factory=dict)
    cash_flow: FinancialTable = field(default_factory=dict)
    metrics_by_year: MetricsByYear = field(default_factory=dict)
    insights: dict[str, list[str]] = field(default_factory=dict)
    scorecard: dict[str, Any] = field(default_factory=dict)
    valuation: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
