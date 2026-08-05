from __future__ import annotations

import copy
import csv
import math
import re
import ssl
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from taiwan_stock_analysis.bounded_loader import run_bounded_loaders


NASDAQ_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
)
NASDAQ_OTHER_LISTED_URL = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
)
NASDAQ_DIRECTORY_DOCS = "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs"
FINRA_SHORT_VOLUME_PAGE = (
    "https://www.finra.org/finra-data/daily-short-sale-volume-transaction-data"
)
FINRA_SHORT_VOLUME_URL = (
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{session}.txt"
)

_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_MIN_DIRECTORY_ROWS = 5_000
_SYMBOL_RE = re.compile(r"^[A-Z0-9./^_+=-]{1,16}$")
_EXCHANGE_NAMES = {
    "A": "NYSE American",
    "N": "NYSE",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}
_NASDAQ_CATEGORY_NAMES = {
    "Q": "Nasdaq Global Select",
    "G": "Nasdaq Global Market",
    "S": "Nasdaq Capital Market",
}

TextFetcher = Callable[..., str]
Clock = Callable[[], datetime]


class USMarketService:
    """Build a compliant US reference screener from public regulatory files.

    This intentionally does not scrape Nasdaq.com's internal website API.
    It joins Nasdaq Trader's official symbol directories with FINRA's public,
    non-commercial consolidated short-sale-volume file.  Price fields remain
    empty until a contracted EOD/market-data provider is configured.
    """

    def __init__(
        self,
        *,
        fetch_text: TextFetcher | None = None,
        clock: Clock | None = None,
        cache_seconds: float = 900.0,
        minimum_directory_rows: int = _MIN_DIRECTORY_ROWS,
        snapshot_deadline_seconds: float = 10.0,
    ) -> None:
        self._uses_default_fetcher = fetch_text is None
        self._fetch_text = fetch_text or _http_text
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache_seconds = max(60.0, float(cache_seconds))
        self._minimum_directory_rows = max(1, int(minimum_directory_rows))
        self._snapshot_deadline_seconds = max(
            0.05,
            float(snapshot_deadline_seconds),
        )
        self._cache_payload: dict[str, Any] | None = None
        self._cache_expires_at = 0.0
        self._cache_lock = threading.RLock()
        self._loader_lock = threading.Lock()
        self._component_capacity = threading.BoundedSemaphore(1)
        self._deadline_local = threading.local()

    def health(self) -> dict[str, Any]:
        with self._cache_lock:
            payload = self._cache_payload
        return {
            "ok": bool(payload and payload.get("ok")),
            "process_alive": True,
            "kind": "us_market_health",
            "status": str((payload or {}).get("status") or "NOT_LOADED"),
            "cached": payload is not None,
            "row_count": int((payload or {}).get("row_count") or 0),
            "short_volume_row_count": int(
                (payload or {}).get("short_volume_row_count") or 0
            ),
            "short_volume_joined_row_count": int(
                (payload or {}).get("short_volume_joined_row_count") or 0
            ),
            "short_volume_unmatched_row_count": int(
                (payload or {}).get("short_volume_unmatched_row_count") or 0
            ),
            "cache_seconds": self._cache_seconds,
            "snapshot_deadline_seconds": self._snapshot_deadline_seconds,
            "price_provider_configured": False,
            "local_noncommercial_reference": True,
        }

    def snapshot(self) -> dict[str, Any]:
        now_monotonic = time.monotonic()
        with self._cache_lock:
            if self._cache_payload is not None and self._cache_expires_at > now_monotonic:
                result = copy.deepcopy(self._cache_payload)
                result["cached"] = True
                return result

        with self._loader_lock:
            now_monotonic = time.monotonic()
            with self._cache_lock:
                if self._cache_payload is not None and self._cache_expires_at > now_monotonic:
                    result = copy.deepcopy(self._cache_payload)
                    result["cached"] = True
                    return result
                stale = copy.deepcopy(self._cache_payload)
            try:
                payload = self._load_with_deadline()
            except (OSError, ValueError, TimeoutError) as exc:
                if stale is not None:
                    payload = _mark_us_stale(
                        stale,
                        now=self._now(),
                        error=f"us-reference: {exc}",
                    )
                else:
                    payload = _unavailable(self._now(), str(exc))
                with self._cache_lock:
                    self._cache_payload = copy.deepcopy(payload)
                    self._cache_expires_at = time.monotonic() + 30.0
                return payload
            with self._cache_lock:
                self._cache_payload = copy.deepcopy(payload)
                self._cache_expires_at = time.monotonic() + self._cache_seconds
            return payload

    def _load_with_deadline(self) -> dict[str, Any]:
        deadline_at = time.monotonic() + self._snapshot_deadline_seconds
        cancelled = threading.Event()

        def load() -> dict[str, Any]:
            self._deadline_local.at = deadline_at
            self._deadline_local.cancelled = cancelled
            try:
                return self._load()
            finally:
                self._deadline_local.at = None
                self._deadline_local.cancelled = None

        try:
            results, failures = run_bounded_loaders(
                {"us-reference": load},
                timeout_seconds=self._snapshot_deadline_seconds,
                capacity=self._component_capacity,
            )
        finally:
            cancelled.set()
        if "us-reference" in failures:
            failure = failures["us-reference"]
            if isinstance(failure, (OSError, ValueError, TimeoutError)):
                raise failure
            raise RuntimeError("US reference loader failed") from failure
        payload = results.get("us-reference")
        if not isinstance(payload, dict):
            raise TimeoutError("US reference snapshot deadline exceeded")
        return payload

    def _now(self) -> datetime:
        now = self._clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)

    def _remaining_seconds(self) -> float:
        cancelled = getattr(self._deadline_local, "cancelled", None)
        if cancelled is not None and cancelled.is_set():
            raise TimeoutError("US reference snapshot deadline exceeded")
        deadline = getattr(self._deadline_local, "at", None)
        if deadline is None:
            return self._snapshot_deadline_seconds
        remaining = float(deadline) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("US reference snapshot deadline exceeded")
        return remaining

    def _fetch(self, url: str) -> str:
        remaining = self._remaining_seconds()
        if self._uses_default_fetcher:
            return self._fetch_text(
                url,
                timeout_seconds=min(4.0, remaining),
            )
        return self._fetch_text(url)

    def _load(self) -> dict[str, Any]:
        nasdaq_rows, nasdaq_created_at = parse_nasdaq_listed(
            self._fetch(NASDAQ_LISTED_URL)
        )
        other_rows, other_created_at = parse_other_listed(
            self._fetch(NASDAQ_OTHER_LISTED_URL)
        )
        directory = _dedupe_directory([*nasdaq_rows, *other_rows])
        if len(directory) < self._minimum_directory_rows:
            raise ValueError(
                "official US symbol directory returned an implausibly small "
                f"universe ({len(directory)} rows)"
            )

        short_rows, short_session, short_errors = self._load_latest_short_volume()
        (
            short_by_symbol,
            joined_short_rows,
            unmatched_short_rows,
            unmatched_short_symbols,
        ) = _join_short_volume(directory, short_rows)
        rows: list[dict[str, Any]] = []
        for listing in directory:
            symbol = str(listing["symbol"])
            short = short_by_symbol.get(symbol, {})
            total_volume = _number(short.get("total_volume"))
            short_volume = _number(short.get("short_volume"))
            short_ratio = (
                short_volume / total_volume * 100.0
                if short_volume is not None
                and total_volume is not None
                and total_volume > 0
                else None
            )
            rows.append(
                {
                    **listing,
                    "market": "US",
                    "industry_name": str(listing.get("exchange") or "US Listed"),
                    "price": None,
                    "change": None,
                    "change_percent": None,
                    "volume": None,
                    "market_cap": None,
                    "quote_status": "NOT_CONNECTED",
                    "session_date": short_session if short else "",
                    "short_volume": short_volume,
                    "short_exempt_volume": _number(
                        short.get("short_exempt_volume")
                    ),
                    "reported_total_volume": total_volume,
                    "short_volume_ratio": (
                        round(short_ratio, 6)
                        if short_ratio is not None
                        else None
                    ),
                    "short_volume_status": (
                        "EOD_REFERENCE" if short else "NO_ROW"
                    ),
                }
            )
        return {
            "schema_version": 1,
            "kind": "us_market_snapshot",
            "ok": bool(rows),
            "cached": False,
            "status": "EOD_REFERENCE" if short_rows else "DIRECTORY_ONLY",
            "generated_at": self._now().isoformat(),
            "as_of": short_session,
            "session_date": short_session,
            "row_count": len(rows),
            "short_volume_row_count": len(short_rows),
            "short_volume_source_row_count": len(short_rows),
            "short_volume_joined_row_count": joined_short_rows,
            "short_volume_unmatched_row_count": unmatched_short_rows,
            "short_volume_joined_security_count": len(short_by_symbol),
            "price_provider_configured": False,
            "rows": rows,
            "source_status": {
                "directory": {
                    "status": "FRESH",
                    "row_count": len(directory),
                    "nasdaq_created_at": nasdaq_created_at,
                    "other_created_at": other_created_at,
                    "source": "Nasdaq Trader Symbol Directory",
                    "url": NASDAQ_DIRECTORY_DOCS,
                },
                "short_volume": {
                    "status": "EOD" if short_rows else "UNAVAILABLE",
                    "row_count": len(short_rows),
                    "row_count_semantics": "source_rows",
                    "source_row_count": len(short_rows),
                    "joined_row_count": joined_short_rows,
                    "unmatched_row_count": unmatched_short_rows,
                    "joined_security_count": len(short_by_symbol),
                    "unmatched_symbol_sample": unmatched_short_symbols[:20],
                    "session_date": short_session,
                    "source": "FINRA Consolidated NMS Short Sale Volume",
                    "url": FINRA_SHORT_VOLUME_PAGE,
                    "coverage_note": (
                        "FINRA off-exchange TRF/ADF public volume only; "
                        "not exchange-consolidated and not short interest."
                    ),
                },
                "prices": {
                    "status": "NOT_CONNECTED",
                    "row_count": 0,
                    "note": (
                        "A licensed EOD price provider key is required; "
                        "price and return fields are intentionally blank."
                    ),
                },
            },
            "errors": short_errors,
        }

    def _load_latest_short_volume(
        self,
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        errors: list[str] = []
        start = self._now().astimezone(timezone.utc).date()
        for offset in range(8):
            candidate = start - timedelta(days=offset)
            if candidate.weekday() >= 5:
                continue
            url = FINRA_SHORT_VOLUME_URL.format(
                session=candidate.strftime("%Y%m%d")
            )
            try:
                raw = self._fetch(url)
            except HTTPError as exc:
                if exc.code in {403, 404}:
                    continue
                errors.append(
                    f"finra-short-volume-{candidate.isoformat()}: "
                    f"HTTP {exc.code}"
                )
                continue
            except (OSError, TimeoutError) as exc:
                errors.append(
                    f"finra-short-volume-{candidate.isoformat()}: "
                    f"{type(exc).__name__}"
                )
                continue
            rows = parse_finra_short_volume(raw)
            if rows:
                session = str(rows[0].get("date") or candidate.isoformat())
                return rows, session, errors
            errors.append(
                f"finra-short-volume-{candidate.isoformat()}: no usable rows"
            )
        if not errors:
            errors.append(
                "finra-short-volume: no published weekday file found "
                "within the bounded lookback"
            )
        return [], "", errors


def parse_nasdaq_listed(text: str) -> tuple[list[dict[str, Any]], str]:
    rows, created_at = _pipe_rows(text)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("Symbol") or "").strip().upper()
        name = str(row.get("Security Name") or "").strip()
        if (
            not symbol
            or not name
            or not _SYMBOL_RE.fullmatch(symbol)
            or str(row.get("Test Issue") or "").strip().upper() == "Y"
        ):
            continue
        category = str(row.get("Market Category") or "").strip().upper()
        normalized.append(
            {
                "symbol": symbol,
                "aliases": [symbol],
                "name": name,
                "company_name": name,
                "exchange": "NASDAQ",
                "listing_tier": _NASDAQ_CATEGORY_NAMES.get(category, category),
                "financial_status": str(
                    row.get("Financial Status") or ""
                ).strip(),
                "is_etf": str(row.get("ETF") or "").strip().upper() == "Y",
            }
        )
    return normalized, created_at


def parse_other_listed(text: str) -> tuple[list[dict[str, Any]], str]:
    rows, created_at = _pipe_rows(text)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        raw_aliases = (
            row.get("NASDAQ Symbol"),
            row.get("ACT Symbol"),
            row.get("CQS Symbol"),
        )
        aliases = sorted(
            {
                str(value or "").strip().upper()
                for value in raw_aliases
                if str(value or "").strip()
                and _SYMBOL_RE.fullmatch(str(value or "").strip().upper())
            }
        )
        symbol = str(
            row.get("NASDAQ Symbol")
            or row.get("ACT Symbol")
            or ""
        ).strip().upper()
        name = str(row.get("Security Name") or "").strip()
        if (
            not symbol
            or not name
            or not _SYMBOL_RE.fullmatch(symbol)
            or str(row.get("Test Issue") or "").strip().upper() == "Y"
        ):
            continue
        exchange_code = str(row.get("Exchange") or "").strip().upper()
        normalized.append(
            {
                "symbol": symbol,
                "aliases": aliases or [symbol],
                "name": name,
                "company_name": name,
                "exchange": _EXCHANGE_NAMES.get(
                    exchange_code,
                    exchange_code or "Other US",
                ),
                "listing_tier": "",
                "financial_status": "",
                "is_etf": str(row.get("ETF") or "").strip().upper() == "Y",
            }
        )
    return normalized, created_at


def parse_finra_short_volume(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(StringIO(str(text or "").lstrip("\ufeff")), delimiter="|")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        symbol = str(raw.get("Symbol") or "").strip().upper()
        session = _yyyymmdd(str(raw.get("Date") or ""))
        if not symbol or not session or not _SYMBOL_RE.fullmatch(symbol):
            continue
        rows.append(
            {
                "date": session,
                "symbol": symbol,
                "short_volume": _number(raw.get("ShortVolume")),
                "short_exempt_volume": _number(raw.get("ShortExemptVolume")),
                "total_volume": _number(raw.get("TotalVolume")),
                "market_centers": str(raw.get("Market") or "").strip(),
            }
        )
    return rows


def _pipe_rows(text: str) -> tuple[list[dict[str, str]], str]:
    lines = [
        line.rstrip("\r")
        for line in str(text or "").lstrip("\ufeff").splitlines()
        if line.strip()
    ]
    created_at = ""
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("File Creation Time:"):
            created_at = line.split("|", 1)[0].partition(":")[2].strip()
        else:
            data_lines.append(line)
    if not data_lines:
        return [], created_at
    return list(csv.DictReader(StringIO("\n".join(data_lines)), delimiter="|")), created_at


def _dedupe_directory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol and symbol not in by_symbol:
            by_symbol[symbol] = row
    return [by_symbol[symbol] for symbol in sorted(by_symbol)]


def _join_short_volume(
    directory: list[dict[str, Any]],
    short_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], int, int, list[str]]:
    """Join FINRA and Nasdaq Trader symbols without guessing collisions."""

    primary_candidates: dict[str, set[str]] = defaultdict(set)
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    compact_candidates: dict[str, set[str]] = defaultdict(set)
    for listing in directory:
        symbol = str(listing.get("symbol") or "").strip().upper()
        for variant in _symbol_variants(symbol):
            primary_candidates[variant].add(symbol)
        aliases = {
            symbol,
            *(
                str(value or "").strip().upper()
                for value in listing.get("aliases") or []
            ),
        }
        for alias in aliases:
            if not alias:
                continue
            for variant in _symbol_variants(alias):
                alias_candidates[variant].add(symbol)
            compact = _compact_symbol(alias)
            if compact:
                compact_candidates[compact].add(symbol)

    joined: dict[str, dict[str, Any]] = {}
    joined_row_count = 0
    unmatched_symbols: set[str] = set()
    for row in short_rows:
        raw_symbol = str(row.get("symbol") or "").strip().upper()
        candidates: set[str] = set()
        for variant in _symbol_variants(raw_symbol):
            candidates.update(primary_candidates.get(variant) or set())
        if len(candidates) != 1:
            alias_matches: set[str] = set()
            for variant in _symbol_variants(raw_symbol):
                alias_matches.update(alias_candidates.get(variant) or set())
            candidates = alias_matches if len(alias_matches) == 1 else set()
        if len(candidates) != 1:
            compact_matches = compact_candidates.get(
                _compact_symbol(raw_symbol),
                set(),
            )
            candidates = set(compact_matches) if len(compact_matches) == 1 else set()
        if len(candidates) != 1:
            unmatched_symbols.add(raw_symbol)
            continue
        directory_symbol = next(iter(candidates))
        joined_row_count += 1
        if directory_symbol in joined:
            joined[directory_symbol] = _merge_short_rows(
                joined[directory_symbol],
                row,
            )
        else:
            joined[directory_symbol] = copy.deepcopy(row)

    unmatched_row_count = max(0, len(short_rows) - joined_row_count)
    return (
        joined,
        joined_row_count,
        unmatched_row_count,
        sorted(symbol for symbol in unmatched_symbols if symbol),
    )


def _symbol_variants(symbol: str) -> set[str]:
    value = str(symbol or "").strip().upper()
    if not value:
        return set()
    return {
        value,
        value.replace("/", "."),
        value.replace(".", "/"),
    }


def _compact_symbol(symbol: str) -> str:
    return re.sub(r"[./^_+=-]", "", str(symbol or "").strip().upper())


def _merge_short_rows(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(left)
    for key in ("short_volume", "short_exempt_volume", "total_volume"):
        left_value = _number(result.get(key))
        right_value = _number(right.get(key))
        if left_value is None:
            result[key] = right_value
        elif right_value is not None:
            result[key] = left_value + right_value
    result["date"] = max(
        str(result.get("date") or ""),
        str(right.get("date") or ""),
    )
    markets = {
        value
        for raw in (
            str(result.get("market_centers") or ""),
            str(right.get("market_centers") or ""),
        )
        for value in raw.split(",")
        if value
    }
    result["market_centers"] = ",".join(sorted(markets))
    return result


def _http_text(url: str, *, timeout_seconds: float = 4.0) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/plain, text/csv, */*",
            "User-Agent": (
                "Taiwan-Equity-Lens/0.54 "
                "(local non-commercial market research)"
            ),
        },
    )
    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        context.verify_flags &= ~strict_flag
    with urlopen(
        request,
        timeout=max(0.05, float(timeout_seconds)),
        context=context,
    ) as response:  # noqa: S310
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("US reference response exceeded size limit")
    return raw.decode("utf-8-sig", errors="strict")


def _number(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "N/A", "NA", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _yyyymmdd(value: str) -> str:
    try:
        return datetime.strptime(str(value or ""), "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def _mark_us_stale(
    payload: dict[str, Any],
    *,
    now: datetime,
    error: str,
) -> dict[str, Any]:
    stale = copy.deepcopy(payload)
    stale["cached"] = True
    stale["last_observed_status"] = str(stale.get("status") or "")
    stale["status"] = "STALE"
    stale["stale_at"] = now.isoformat()
    stale["errors"] = [*list(stale.get("errors") or []), error]
    for source in (stale.get("source_status") or {}).values():
        status = str(source.get("status") or "").upper()
        if status and status not in {"UNAVAILABLE", "NOT_CONNECTED", "STALE"}:
            source["last_observed_status"] = str(source.get("status") or "")
            source["status"] = "STALE"
    for row in stale.get("rows") or []:
        short_status = str(row.get("short_volume_status") or "")
        if short_status == "EOD_REFERENCE":
            row["last_observed_short_volume_status"] = short_status
            row["short_volume_status"] = "STALE"
    return stale


def _unavailable(now: datetime, error: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "us_market_snapshot",
        "ok": False,
        "cached": False,
        "status": "UNAVAILABLE",
        "generated_at": now.isoformat(),
        "as_of": "",
        "session_date": "",
        "row_count": 0,
        "short_volume_row_count": 0,
        "short_volume_source_row_count": 0,
        "short_volume_joined_row_count": 0,
        "short_volume_unmatched_row_count": 0,
        "short_volume_joined_security_count": 0,
        "price_provider_configured": False,
        "rows": [],
        "source_status": {},
        "errors": [f"us-reference: {error}"],
    }
