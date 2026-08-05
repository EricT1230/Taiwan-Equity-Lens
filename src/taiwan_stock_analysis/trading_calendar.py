from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any


TAIPEI = timezone(timedelta(hours=8), "Asia/Taipei")
TWSE_HOLIDAY_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
EOD_READY_TIME = time(15, 0)
CASH_MARKET_OPEN_TIME = time(9, 0)


def parse_twse_closed_dates(payload: Any) -> set[date]:
    """Parse official TWSE holiday rows into non-trading Gregorian dates."""

    if not isinstance(payload, list):
        return set()
    closed: set[date] = set()
    markers = ("無交易", "休市", "放假", "補假")
    for row in payload:
        if not isinstance(row, dict):
            continue
        description = " ".join(
            (
                str(row.get("Name") or ""),
                str(row.get("Description") or ""),
            )
        )
        if not any(marker in description for marker in markers):
            continue
        parsed = parse_market_date(row.get("Date"))
        if parsed is not None:
            closed.add(parsed)
    return closed


def expected_latest_completed_session(
    as_of: datetime,
    *,
    closed_dates: set[date],
) -> date:
    """Return the EOD session that should be complete at ``as_of``."""

    local = _taipei_time(as_of)
    target = local.date()
    if (
        not is_trading_date(target, closed_dates=closed_dates)
        or local.time() < EOD_READY_TIME
    ):
        target = previous_trading_date(target, closed_dates=closed_dates)
    return target


def expected_live_quote_session(
    as_of: datetime,
    *,
    closed_dates: set[date],
) -> date:
    """Return the session a live headline should currently represent.

    Before the cash market opens, the prior close remains authoritative. Once
    an open trading day begins, the current session is required.
    """

    local = _taipei_time(as_of)
    today = local.date()
    if (
        is_trading_date(today, closed_dates=closed_dates)
        and local.time() >= CASH_MARKET_OPEN_TIME
    ):
        return today
    return previous_trading_date(today, closed_dates=closed_dates)


def is_trading_date(value: date, *, closed_dates: set[date]) -> bool:
    return value.weekday() < 5 and value not in closed_dates


def previous_trading_date(value: date, *, closed_dates: set[date]) -> date:
    target = value - timedelta(days=1)
    while not is_trading_date(target, closed_dates=closed_dates):
        target -= timedelta(days=1)
    return target


def parse_market_date(value: Any) -> date | None:
    """Accept TWSE Gregorian or ROC compact dates."""

    text = re.sub(r"\D", "", str(value or ""))
    try:
        if len(text) == 8 and text.startswith("20"):
            return datetime.strptime(text, "%Y%m%d").date()
        if len(text) >= 7:
            return date(
                int(text[:-4]) + 1911,
                int(text[-4:-2]),
                int(text[-2:]),
            )
    except ValueError:
        return None
    return None


def _taipei_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=TAIPEI)
    return value.astimezone(TAIPEI)
