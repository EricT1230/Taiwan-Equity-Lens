from __future__ import annotations


def yoy_change(values_by_year: dict[str, float | None], years: list[str]) -> float | None:
    if len(years) < 2:
        return None
    latest = values_by_year.get(years[0])
    previous = values_by_year.get(years[1])
    if latest is None or previous in {None, 0}:
        return None
    return (latest - previous) / previous * 100


def cagr(values_by_year: dict[str, float | None], years: list[str]) -> float | None:
    available = [(year, values_by_year.get(year)) for year in years if values_by_year.get(year) is not None]
    if len(available) < 2:
        return None
    latest_year, latest = available[0]
    oldest_year, oldest = available[-1]
    if latest is None or oldest is None or oldest <= 0 or latest < 0:
        return None
    years_delta = abs(int(latest_year) - int(oldest_year))
    if years_delta == 0:
        return None
    return ((latest / oldest) ** (1 / years_delta) - 1) * 100


def classify_trend(values: list[float | None], stable_tolerance_pct: float = 3.0) -> str:
    clean_values = [value for value in values if value is not None]
    if len(clean_values) < 2:
        return "insufficient"

    deltas = [curr - prev for prev, curr in zip(clean_values, clean_values[1:])]
    if all(delta > 0 for delta in deltas):
        return "improving"
    if all(delta < 0 for delta in deltas):
        return "worsening"

    average = sum(abs(value) for value in clean_values) / len(clean_values)
    movement = max(clean_values) - min(clean_values)
    if average and movement / average * 100 <= stable_tolerance_pct:
        return "stable"
    return "volatile"
