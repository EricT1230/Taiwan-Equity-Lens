from collections import Counter, defaultdict
from datetime import date, datetime
import math
from typing import Any, Mapping, Protocol, Sequence

from taiwan_stock_analysis.sentiment_lexicon import (
    normalize_sentiment_text,
    score_news_text,
)


METHODOLOGY_VERSION = "industry-sentiment-v1"
CONFIGURED_WEIGHTS = {"news": 0.40, "price": 0.30, "fund_flow": 0.30}
PHASE_ORDER = (
    "overheating",
    "capitulation",
    "recovery",
    "ignition",
    "expansion",
    "cooling",
    "consolidation",
)


class NewsSentimentReviewer(Protocol):
    def review(
        self,
        news_rows: Sequence[Mapping[str, Any]],
        deterministic_assessment: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise NotImplementedError


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _price_score(
    industry_return: float,
    return_scale: float,
    breadth: float,
    volume_ratio_5d: float,
) -> float:
    return_term = _clamp(industry_return / return_scale, -1.0, 1.0)
    breadth_term = 2.0 * breadth - 1.0
    volume_term = (
        math.copysign(
            _clamp(volume_ratio_5d - 1.0, 0.0, 1.0),
            industry_return,
        )
        if industry_return != 0
        else 0.0
    )
    combined = 0.60 * return_term + 0.25 * breadth_term + 0.15 * volume_term
    return 100.0 * _clamp(combined, -1.0, 1.0)


def _price_window(
    trend: Mapping[str, Any],
    *,
    window: str,
    return_scale: float,
) -> tuple[float | None, list[str]]:
    return_key = f"average_return_{window}"
    breadth_key = f"positive_breadth_{window}"
    required = {
        return_key: _finite_float(trend.get(return_key)),
        breadth_key: _finite_float(trend.get(breadth_key)),
        "average_volume_ratio_5d": _finite_float(
            trend.get("average_volume_ratio_5d")
        ),
    }
    invalid = [
        key
        for key, value in required.items()
        if value is None
        or (key == breadth_key and not 0.0 <= value <= 1.0)
        or (key == "average_volume_ratio_5d" and value < 0.0)
    ]
    if invalid:
        return None, [
            f"price {window} unavailable: missing or invalid {', '.join(invalid)}"
        ]
    return (
        _price_score(
            required[return_key],
            return_scale,
            required[breadth_key],
            required["average_volume_ratio_5d"],
        ),
        [],
    )


def score_price_component(trend: Mapping[str, Any]) -> dict[str, Any]:
    score_5d, warnings_5d = _price_window(
        trend,
        window="5d",
        return_scale=8.0,
    )
    score_20d, warnings_20d = _price_window(
        trend,
        window="20d",
        return_scale=15.0,
    )
    available = sum(score is not None for score in (score_5d, score_20d))
    status = (
        "ready"
        if available == 2
        else "partial"
        if available == 1
        else "insufficient_data"
    )
    return {
        "score_5d": score_5d,
        "score_20d": score_20d,
        "return_5d": _finite_float(trend.get("average_return_5d")),
        "return_20d": _finite_float(trend.get("average_return_20d")),
        "breadth_5d": _finite_float(trend.get("positive_breadth_5d")),
        "breadth_20d": _finite_float(trend.get("positive_breadth_20d")),
        "volume_ratio_5d": _finite_float(trend.get("average_volume_ratio_5d")),
        "coverage_ratio_5d": _finite_float(trend.get("coverage_ratio_5d")),
        "coverage_ratio_20d": _finite_float(trend.get("coverage_ratio_20d")),
        "high_count_20d": trend.get("high_count_20d"),
        "low_count_20d": trend.get("low_count_20d"),
        "status": status,
        "warnings": [*warnings_5d, *warnings_20d],
    }


def _flow_score(
    valid_rows: list[dict[str, Any]], valid_dates: list[str]
) -> float:
    net_shares = sum(float(row["total_net"]) for row in valid_rows)
    traded_shares = sum(float(row["traded_shares"]) for row in valid_rows)
    day_totals = {
        value: sum(
            float(row["total_net"])
            for row in valid_rows
            if row["date"] == value
        )
        for value in valid_dates
    }
    buy_days = sum(value > 0 for value in day_totals.values())
    sell_days = sum(value < 0 for value in day_totals.values())
    persistence = (buy_days - sell_days) / len(valid_dates)
    flow_ratio = net_shares / traded_shares
    return 100.0 * _clamp(
        0.75 * (flow_ratio / 0.05) + 0.25 * persistence,
        -1.0,
        1.0,
    )


def _flow_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    covered_stock_ids: set[str],
    expected_dates: list[str],
    minimum_valid_days: int,
    window: str,
) -> tuple[dict[str, Any], list[str]]:
    expected_stocks = len(covered_stock_ids)
    expected_date_set = set(expected_dates)
    joined_rows: list[dict[str, Any]] = []
    excluded_invalid = 0
    for row in rows:
        date_value = str(row.get("date") or "").strip()
        stock_id = str(row.get("stock_id") or "").strip()
        if date_value not in expected_date_set or stock_id not in covered_stock_ids:
            continue
        total_net = _finite_float(row.get("total_net"))
        traded_shares = _finite_float(row.get("traded_shares"))
        if total_net is None or traded_shares is None or traded_shares <= 0.0:
            excluded_invalid += 1
            continue
        joined_rows.append(
            {
                "date": date_value,
                "stock_id": stock_id,
                "total_net": total_net,
                "traded_shares": traded_shares,
            }
        )

    stock_ids_by_date = {
        value: {
            str(row["stock_id"])
            for row in joined_rows
            if row["date"] == value
        }
        for value in expected_dates
    }
    coverage_by_date = {
        value: (
            len(stock_ids_by_date[value]) / expected_stocks
            if expected_stocks
            else 0.0
        )
        for value in expected_dates
    }
    valid_dates = [
        value for value in expected_dates if coverage_by_date[value] >= 0.60
    ]
    valid_date_set = set(valid_dates)
    valid_rows = [row for row in joined_rows if row["date"] in valid_date_set]
    net_shares = sum(float(row["total_net"]) for row in valid_rows)
    traded_shares = sum(float(row["traded_shares"]) for row in valid_rows)
    day_totals = {
        value: sum(
            float(row["total_net"])
            for row in valid_rows
            if row["date"] == value
        )
        for value in valid_dates
    }
    buy_days = sum(value > 0 for value in day_totals.values())
    sell_days = sum(value < 0 for value in day_totals.values())
    persistence = (
        (buy_days - sell_days) / len(valid_dates) if valid_dates else None
    )
    score = (
        _flow_score(valid_rows, valid_dates)
        if len(valid_dates) >= minimum_valid_days
        else None
    )
    warnings: list[str] = []
    if score is None:
        warnings.append(
            f"fund_flow {window} unavailable: {len(valid_dates)} valid sessions; "
            f"requires {minimum_valid_days}"
        )
    if excluded_invalid:
        noun = "row" if excluded_invalid == 1 else "rows"
        warnings.append(
            f"fund_flow {window} excluded {excluded_invalid} {noun} without valid "
            "total_net and positive traded_shares"
        )
    return (
        {
            "score": score,
            "valid_days": len(valid_dates),
            "valid_dates": valid_dates,
            "missing_dates": [
                value for value in expected_dates if value not in valid_date_set
            ],
            "joined_stocks": len(
                {str(row["stock_id"]) for row in joined_rows}
            ),
            "joined_stock_ids": sorted(
                {str(row["stock_id"]) for row in joined_rows}
            ),
            "expected_stocks": expected_stocks,
            "coverage_by_date": coverage_by_date,
            "net_shares": net_shares,
            "traded_shares": traded_shares,
            "persistence": persistence,
        },
        warnings,
    )


def score_fund_flow_component(
    rows: Sequence[Mapping[str, Any]],
    *,
    price_covered_stock_ids: Sequence[str],
    expected_session_dates: Sequence[str],
) -> dict[str, Any]:
    covered_stock_ids = {
        normalized
        for value in price_covered_stock_ids
        if value is not None and (normalized := str(value).strip())
    }
    dates = sorted(
        {
            normalized
            for value in expected_session_dates
            if value is not None and (normalized := str(value).strip())
        }
    )
    window_5d, warnings_5d = _flow_window(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=dates[-5:],
        minimum_valid_days=3,
        window="5d",
    )
    window_20d, warnings_20d = _flow_window(
        rows,
        covered_stock_ids=covered_stock_ids,
        expected_dates=dates[-20:],
        minimum_valid_days=10,
        window="20d",
    )
    available = sum(
        window["score"] is not None for window in (window_5d, window_20d)
    )
    status = (
        "ready"
        if available == 2
        else "partial"
        if available == 1
        else "insufficient_data"
    )
    warnings = [*warnings_5d, *warnings_20d]
    if not covered_stock_ids:
        warnings.insert(0, "fund_flow unavailable: no price-covered stocks")
    if not dates:
        warnings.insert(0, "fund_flow unavailable: no expected session dates")

    result: dict[str, Any] = {
        "score_5d": window_5d["score"],
        "score_20d": window_20d["score"],
        "expected_stocks": len(covered_stock_ids),
        "status": status,
        "warnings": warnings,
    }
    for suffix, window in (("5d", window_5d), ("20d", window_20d)):
        for name in (
            "valid_days",
            "valid_dates",
            "missing_dates",
            "joined_stocks",
            "joined_stock_ids",
            "expected_stocks",
            "coverage_by_date",
            "net_shares",
            "traded_shares",
            "persistence",
        ):
            result[f"{name}_{suffix}"] = window[name]
    return result


def _parse_published_at(value: Any, *, as_of: datetime) -> datetime | None:
    try:
        published = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=as_of.tzinfo)
    return published


def _event_signature(
    row: Mapping[str, Any],
    normalized_title: str,
    *,
    normalized_summary: str,
    published_at: str,
    source: str,
    url: str,
) -> tuple[str, ...]:
    raw_keywords = row.get("keywords")
    if isinstance(raw_keywords, Sequence) and not isinstance(raw_keywords, (str, bytes)):
        keywords = raw_keywords
    elif raw_keywords:
        keywords = [raw_keywords]
    else:
        keywords = []

    normalized_keywords: list[str] = []
    seen: set[str] = set()
    for value in keywords:
        normalized = normalize_sentiment_text(str(value))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_keywords.append(normalized)
        if len(normalized_keywords) == 3:
            break
    if normalized_keywords:
        return tuple(normalized_keywords)
    if normalized_title:
        return ("__title__", normalized_title)
    normalized_url = normalize_sentiment_text(url)
    if normalized_url:
        return ("__url__", normalized_url)
    return (
        "__summary__",
        normalized_summary,
        published_at,
        normalize_sentiment_text(source),
    )


def _uniquify_summary_signatures(rows: Sequence[dict[str, Any]]) -> None:
    occurrences: dict[tuple[str, ...], int] = defaultdict(int)
    for row in rows:
        signature = tuple(row["event_signature"])
        if not signature or signature[0] != "__summary__":
            continue
        occurrences[signature] += 1
        row["event_signature"] = (
            *signature,
            f"occurrence:{occurrences[signature]}",
        )


def _canonical_row_identity(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", "1" if value else "0")
    if isinstance(value, int):
        return ("int", str(value))
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, bytes):
        return ("bytes", value.hex())
    if isinstance(value, Mapping):
        items = (
            (_canonical_row_identity(key), _canonical_row_identity(item))
            for key, item in value.items()
        )
        return ("mapping", tuple(sorted(items)))
    if isinstance(value, list):
        return ("list", tuple(_canonical_row_identity(item) for item in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_canonical_row_identity(item) for item in value))
    if isinstance(value, (set, frozenset)):
        return (
            "set",
            tuple(sorted(_canonical_row_identity(item) for item in value)),
        )
    value_type = type(value)
    return ("object", value_type.__module__, value_type.__qualname__)


def _prepare_news(
    rows: Sequence[Mapping[str, Any]], *, as_of: datetime
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates: list[tuple[datetime, dict[str, Any], str]] = []
    exclusions = {
        "invalid_timestamp": 0,
        "future": 0,
        "too_old": 0,
        "unscorable_text": 0,
        "duplicate": 0,
    }

    for row in rows:
        published = _parse_published_at(row.get("published_at"), as_of=as_of)
        if published is None:
            exclusions["invalid_timestamp"] += 1
            continue
        age_days = (as_of - published).total_seconds() / 86400.0
        if age_days < 0:
            exclusions["future"] += 1
            continue
        if age_days > 20:
            exclusions["too_old"] += 1
            continue

        title = str(row.get("title") or "")
        summary = str(row.get("summary") or "")
        normalized_title = normalize_sentiment_text(title)
        normalized_summary = normalize_sentiment_text(summary)
        if not normalized_title and not normalized_summary:
            exclusions["unscorable_text"] += 1
            continue

        url = str(row.get("url") or "").strip()
        source = str(row.get("source") or "unknown").strip() or "unknown"
        item = dict(row)
        item.update(
            {
                "published_at": published.isoformat(),
                "title": title,
                "summary": summary,
                "url": url,
                "source": source,
                "normalized_title": normalized_title,
                "article_score": _clamp(
                    0.65 * score_news_text(title) + 0.35 * score_news_text(summary),
                    -100.0,
                    100.0,
                ),
                "event_signature": _event_signature(
                    row,
                    normalized_title,
                    normalized_summary=normalized_summary,
                    published_at=published.isoformat(),
                    source=source,
                    url=url,
                ),
            }
        )
        candidates.append((published, item, normalized_summary))

    candidates.sort(
        key=lambda candidate: (
            -candidate[0].timestamp(),
            str(candidate[1]["url"]),
            str(candidate[1]["normalized_title"]),
            candidate[2],
            str(candidate[1]["summary"]),
            str(candidate[1]["source"]),
            tuple(candidate[1]["event_signature"]),
            _canonical_row_identity(candidate[1]),
        )
    )

    prepared: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for _, item, _ in candidates:
        url = str(item["url"])
        normalized_title = str(item["normalized_title"])
        if (url and url in seen_urls) or (
            normalized_title and normalized_title in seen_titles
        ):
            exclusions["duplicate"] += 1
            continue
        if url:
            seen_urls.add(url)
        if normalized_title:
            seen_titles.add(normalized_title)
        prepared.append(item)
    _uniquify_summary_signatures(prepared)
    return prepared, exclusions


def _eligible_news(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
    window_days: int,
    half_life_days: float,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        published = datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=as_of.tzinfo)
        age_days = (as_of - published).total_seconds() / 86400.0
        if age_days < 0 or age_days > window_days:
            continue
        item = dict(row)
        item["raw_weight"] = 0.5 ** (age_days / half_life_days)
        selected.append(item)
    return selected


def _score_news_window(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime,
    window_days: int,
    half_life_days: float,
) -> tuple[float | None, list[dict[str, Any]], float]:
    eligible = _eligible_news(
        rows,
        as_of=as_of,
        window_days=window_days,
        half_life_days=half_life_days,
    )
    if not eligible:
        return None, [], 0.0
    total_raw = sum(float(row["raw_weight"]) for row in eligible)
    by_source: dict[str, float] = defaultdict(float)
    for row in eligible:
        by_source[str(row["source"])] += float(row["raw_weight"])
    source_scale = {
        source: min(weight, total_raw * 0.40) / weight
        for source, weight in by_source.items()
    }
    numerator = sum(
        float(row["article_score"])
        * float(row["raw_weight"])
        * source_scale[str(row["source"])]
        for row in eligible
    )
    concentration = max(
        min(weight, total_raw * 0.40) / total_raw for weight in by_source.values()
    )
    return _clamp(numerator / total_raw, -100.0, 100.0), eligible, concentration


def _source_weight_is_clipped(rows: Sequence[Mapping[str, Any]]) -> bool:
    if not rows:
        return False
    by_source: dict[str, float] = defaultdict(float)
    for row in rows:
        by_source[str(row["source"])] += float(row["raw_weight"])
    total_raw = sum(by_source.values())
    return any(weight > total_raw * 0.40 for weight in by_source.values())


def _largest_signature_share(rows: Sequence[Mapping[str, Any]]) -> float:
    if not rows:
        return 0.0
    counts = Counter(tuple(row["event_signature"]) for row in rows)
    return max(counts.values()) / len(rows)


def score_news_component(
    rows: Sequence[Mapping[str, Any]], *, as_of: datetime
) -> dict[str, Any]:
    prepared, exclusions = _prepare_news(rows, as_of=as_of)
    score_5d, articles_5d, source_concentration = _score_news_window(
        prepared,
        as_of=as_of,
        window_days=5,
        half_life_days=3,
    )
    score_20d, articles_20d, _ = _score_news_window(
        prepared,
        as_of=as_of,
        window_days=20,
        half_life_days=7,
    )

    warnings: list[str] = []
    if exclusions["invalid_timestamp"]:
        count = exclusions["invalid_timestamp"]
        noun = "article" if count == 1 else "articles"
        warnings.append(
            f"invalid or missing published_at: {count} {noun} excluded"
        )
    if exclusions["future"]:
        count = exclusions["future"]
        noun = "article" if count == 1 else "articles"
        warnings.append(f"future published_at: {count} {noun} excluded")
    if exclusions["too_old"]:
        count = exclusions["too_old"]
        noun = "article" if count == 1 else "articles"
        warnings.append(f"published_at older than 20d: {count} {noun} excluded")
    if exclusions["unscorable_text"]:
        count = exclusions["unscorable_text"]
        noun = "article" if count == 1 else "articles"
        warnings.append(f"missing scorable text: {count} {noun} excluded")
    if _source_weight_is_clipped(articles_5d) or _source_weight_is_clipped(articles_20d):
        warnings.append("source concentration clipped")
    if len(articles_5d) < 3:
        warnings.append("low news coverage: fewer than 3 articles in 5d")
    if len(articles_20d) < 3:
        warnings.append("low news coverage: fewer than 3 articles in 20d")

    if not articles_20d:
        status = "insufficient_data"
    elif (
        any(
            exclusions[key]
            for key in ("invalid_timestamp", "future", "too_old", "unscorable_text")
        )
        or len(articles_5d) < 3
        or len(articles_20d) < 3
    ):
        status = "partial"
    else:
        status = "ready"

    normalized_titles = {str(row["normalized_title"]) for row in articles_5d}
    positive_articles = [row for row in articles_5d if float(row["article_score"]) > 0]
    negative_articles = [row for row in articles_5d if float(row["article_score"]) < 0]
    return {
        "score_5d": score_5d,
        "score_20d": score_20d,
        "coverage": {
            "articles_5d": len(articles_5d),
            "articles_20d": len(articles_20d),
            "excluded_invalid_timestamp": exclusions["invalid_timestamp"],
            "excluded_future": exclusions["future"],
            "excluded_too_old": exclusions["too_old"],
            "excluded_unscorable_text": exclusions["unscorable_text"],
            "excluded_duplicate": exclusions["duplicate"],
        },
        "article_scores": articles_5d,
        "source_concentration": source_concentration,
        "topic_concentration": _largest_signature_share(articles_5d),
        "positive_topic_concentration": _largest_signature_share(positive_articles),
        "negative_topic_concentration": _largest_signature_share(negative_articles),
        "novelty": len(normalized_titles) / len(articles_5d) if articles_5d else 0.0,
        "status": status,
        "warnings": warnings,
    }


def classify_sentiment_label(score: float) -> str:
    if score >= 60.0:
        return "extremely_optimistic"
    if score >= 20.0:
        return "optimistic"
    if score > -20.0:
        return "neutral"
    if score > -60.0:
        return "pessimistic"
    return "extremely_pessimistic"


def _effective_weights(names: list[str]) -> dict[str, float]:
    total = sum(CONFIGURED_WEIGHTS[name] for name in names)
    return {name: CONFIGURED_WEIGHTS[name] / total for name in names}


def _freshness_entry(
    freshness: Mapping[str, Any], component_name: str
) -> Any:
    if component_name in freshness:
        return freshness[component_name]
    if component_name == "price":
        return freshness.get("industry_trend")
    return None


def _is_fresh(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        if "fresh" in value:
            return value.get("fresh") is True
        value = value.get("status")
    return str(value or "").strip().lower() == "fresh"


def _freshness_description(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("status", value.get("fresh"))
    if value is True:
        return "fresh"
    if value is False:
        return "not fresh"
    return str(value or "missing")


def _component_warning(name: str, warning: Any) -> str:
    text = str(warning).strip()
    if text.startswith(f"{name} ") or text.startswith(f"{name}:"):
        return text
    return f"{name}: {text}"


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _component_reason(
    name: str,
    component: Mapping[str, Any],
    contribution: float,
) -> str:
    if name == "news":
        return f"news contribution {contribution:+.1f}"
    if name == "price":
        breadth = _finite_float(component.get("breadth_5d"))
        if breadth is not None:
            return f"5-day breadth {breadth * 100.0:.1f}%"
        return f"price contribution {contribution:+.1f}"
    persistence = _finite_float(component.get("persistence_5d"))
    if persistence is not None:
        return f"institutional flow persistence {persistence:+.2f}"
    return f"fund flow contribution {contribution:+.1f}"


def _coverage_downgrades(
    components: Mapping[str, Mapping[str, Any]], usable: Sequence[str]
) -> list[str]:
    downgrades: list[str] = []
    if "news" in usable:
        coverage = components["news"].get("coverage")
        articles = (
            _finite_float(coverage.get("articles_5d"))
            if isinstance(coverage, Mapping)
            else None
        )
        if articles is None or articles < 3.0:
            value = "missing" if articles is None else str(int(articles))
            downgrades.append(
                f"news 5d coverage {value} articles is below the 3-article minimum"
            )
    if "price" in usable:
        coverage = _finite_float(
            components["price"].get("coverage_ratio_5d")
        )
        if coverage is None:
            downgrades.append("price 5d coverage is missing or invalid")
        elif coverage < 0.80:
            downgrades.append(
                f"price 5d coverage {coverage * 100.0:.1f}% is below 80.0%"
            )
    if "fund_flow" in usable:
        valid_days = _finite_float(
            components["fund_flow"].get("valid_days_5d")
        )
        if valid_days is None:
            downgrades.append("fund_flow 5d valid-session coverage is missing")
        elif valid_days < 4.0:
            downgrades.append(
                f"fund_flow 5d has {int(valid_days)} valid sessions; high confidence requires 4"
            )
    for name in usable:
        component = components[name]
        if str(component.get("status") or "") == "partial":
            downgrades.append(f"{name} component has partial-source status")
        if component.get("warnings"):
            downgrades.append(f"{name} component has partial-source warnings")
    return downgrades


def combine_sentiment_components(
    components: Mapping[str, Mapping[str, Any]],
    *,
    freshness: Mapping[str, Any],
    source_errors: Sequence[str],
) -> dict[str, Any]:
    normalized_components: dict[str, dict[str, Any]] = {
        name: dict(components.get(name, {})) for name in CONFIGURED_WEIGHTS
    }
    warnings: list[str] = []
    usable: list[str] = []
    fresh_names: list[str] = []

    for name in CONFIGURED_WEIGHTS:
        component = normalized_components[name]
        component["configured_weight"] = CONFIGURED_WEIGHTS[name]
        component["effective_weight"] = None
        component["contribution_5d"] = None
        component["contribution_20d"] = None
        for warning in component.get("warnings") or []:
            _append_unique(warnings, _component_warning(name, warning))

        score_5d = _finite_float(component.get("score_5d"))
        score_20d = _finite_float(component.get("score_20d"))
        missing_windows = [
            window
            for window, score in (("5d", score_5d), ("20d", score_20d))
            if score is None
        ]
        if missing_windows:
            if len(missing_windows) == 1:
                missing_text = f"missing {missing_windows[0]} score"
            else:
                missing_text = "missing 5d and 20d scores"
            _append_unique(
                warnings,
                f"{name} removed from composite: {missing_text}",
            )

        freshness_value = _freshness_entry(freshness, name)
        fresh = _is_fresh(freshness_value)
        if fresh:
            fresh_names.append(name)
        else:
            _append_unique(
                warnings,
                f"{name} removed from composite: freshness status "
                f"{_freshness_description(freshness_value)}",
            )
        if not missing_windows and fresh:
            usable.append(name)

    normalized_source_errors = sorted(
        {str(error).strip() for error in source_errors if str(error).strip()}
    )
    for error in normalized_source_errors:
        _append_unique(warnings, f"source error: {error}")

    if len(usable) >= 2:
        effective_weights = _effective_weights(usable)
        score_5d = 0.0
        baseline_20d = 0.0
        reason_rows: list[tuple[float, str, str]] = []
        for name in usable:
            component = normalized_components[name]
            effective_weight = effective_weights[name]
            component_score_5d = float(component["score_5d"])
            component_score_20d = float(component["score_20d"])
            contribution_5d = component_score_5d * effective_weight
            contribution_20d = component_score_20d * effective_weight
            component["effective_weight"] = effective_weight
            component["contribution_5d"] = contribution_5d
            component["contribution_20d"] = contribution_20d
            score_5d += contribution_5d
            baseline_20d += contribution_20d
            reason_rows.append(
                (
                    -abs(contribution_5d),
                    name,
                    _component_reason(name, component, contribution_5d),
                )
            )
        change = score_5d - baseline_20d
        temperature = (
            "warming"
            if change >= 10.0
            else "cooling"
            if change <= -10.0
            else "stable"
        )
        label = classify_sentiment_label(score_5d)
        reasons = [row[2] for row in sorted(reason_rows)[:3]]
        status = "ready" if len(usable) == len(CONFIGURED_WEIGHTS) else "partial"
    else:
        effective_weights = {}
        score_5d = None
        baseline_20d = None
        change = None
        temperature = None
        label = None
        reasons = []
        status = "insufficient_data"

    if len(usable) < 2:
        confidence = None
        _append_unique(
            warnings,
            "confidence unavailable: fewer than two usable fresh components",
        )
    else:
        coverage_downgrades = _coverage_downgrades(
            normalized_components,
            usable,
        )
        if normalized_source_errors or coverage_downgrades:
            confidence = "low"
            for reason in coverage_downgrades:
                _append_unique(
                    warnings,
                    f"confidence downgraded to low: {reason}",
                )
            if normalized_source_errors:
                _append_unique(
                    warnings,
                    "confidence downgraded to low: required-source errors present",
                )
        else:
            news_coverage = normalized_components["news"].get("coverage")
            news_articles_5d = (
                _finite_float(news_coverage.get("articles_5d"))
                if isinstance(news_coverage, Mapping)
                else None
            )
            high = (
                len(usable) == 3
                and len(fresh_names) == 3
                and news_articles_5d is not None
                and news_articles_5d >= 5.0
                and _finite_float(
                    normalized_components["price"].get("coverage_ratio_5d")
                )
                is not None
                and float(
                    normalized_components["price"]["coverage_ratio_5d"]
                )
                >= 0.80
                and _finite_float(
                    normalized_components["fund_flow"].get("valid_days_5d")
                )
                is not None
                and float(normalized_components["fund_flow"]["valid_days_5d"])
                >= 4.0
            )
            confidence = "high" if high else "medium"
            if confidence == "medium":
                if len(usable) < 3:
                    reason = "fewer than three complete fresh components"
                else:
                    article_count = (
                        "missing"
                        if news_articles_5d is None
                        else str(int(news_articles_5d))
                    )
                    reason = (
                        f"news has {article_count} articles in 5d; high confidence requires 5"
                    )
                _append_unique(
                    warnings,
                    f"confidence downgraded to medium: {reason}",
                )

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "status": status,
        "score_5d": score_5d,
        "baseline_20d": baseline_20d,
        "change": change,
        "temperature": temperature,
        "label": label,
        "confidence": confidence,
        "components": normalized_components,
        "effective_weights": effective_weights,
        "reasons": reasons,
        "warnings": warnings,
    }


def _has_recent_news(component: Mapping[str, Any], *, as_of: datetime) -> bool:
    for row in component.get("article_scores") or []:
        if not isinstance(row, Mapping):
            continue
        published = _parse_published_at(row.get("published_at"), as_of=as_of)
        if published is None:
            continue
        age_hours = (as_of - published).total_seconds() / 3600.0
        if 0.0 <= age_hours <= 48.0:
            return True
    return False


def _has_recent_flow(
    component: Mapping[str, Any], expected_session_dates: Sequence[str]
) -> bool:
    expected_dates = sorted(
        {
            normalized
            for value in expected_session_dates
            if value is not None and (normalized := str(value).strip())
        }
    )
    acceptable_dates = set(expected_dates[-2:])
    valid_dates = {
        str(value) for value in component.get("valid_dates_20d") or []
    }
    return bool(acceptable_dates.intersection(valid_dates))


def build_industry_sentiment_base(
    *,
    news_rows: Sequence[Mapping[str, Any]],
    trend: Mapping[str, Any],
    flow_rows: Sequence[Mapping[str, Any]],
    expected_session_dates: Sequence[str],
    freshness: Mapping[str, Any],
    source_errors: Sequence[str],
    as_of: datetime,
) -> dict[str, Any]:
    news_component = score_news_component(news_rows, as_of=as_of)
    price_component = score_price_component(trend)
    fund_flow_component = score_fund_flow_component(
        flow_rows,
        price_covered_stock_ids=trend.get("covered_stock_ids") or [],
        expected_session_dates=expected_session_dates,
    )
    local_freshness = {
        "news": _is_fresh(_freshness_entry(freshness, "news"))
        and _has_recent_news(news_component, as_of=as_of),
        "price": _is_fresh(_freshness_entry(freshness, "price")),
        "fund_flow": _is_fresh(_freshness_entry(freshness, "fund_flow"))
        and _has_recent_flow(fund_flow_component, expected_session_dates),
    }
    assessment = combine_sentiment_components(
        {
            "news": news_component,
            "price": price_component,
            "fund_flow": fund_flow_component,
        },
        freshness=local_freshness,
        source_errors=source_errors,
    )
    assessment["as_of_date"] = as_of.date().isoformat()
    return assessment


def _ols_slope(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    selected = list(values[-3:])
    x_mean = (len(selected) - 1) / 2.0
    y_mean = sum(selected) / len(selected)
    denominator = sum(
        (index - x_mean) ** 2 for index in range(len(selected))
    )
    return sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(selected)
    ) / denominator


def _slope_direction(slope: float | None) -> str:
    if slope is None:
        return "unavailable"
    if slope >= 2.0:
        return "positive"
    if slope <= -2.0:
        return "negative"
    return "flat"


def _nested_component(
    assessment: Mapping[str, Any], name: str
) -> Mapping[str, Any]:
    components = assessment.get("components")
    if not isinstance(components, Mapping):
        return {}
    component = components.get(name)
    return component if isinstance(component, Mapping) else {}


def _assessment_number(
    assessment: Mapping[str, Any],
    flat_key: str,
    *,
    component_name: str,
    component_key: str,
) -> float | None:
    value = _finite_float(assessment.get(flat_key))
    if value is not None:
        return value
    return _finite_float(
        _nested_component(assessment, component_name).get(component_key)
    )


def _ordered_prior_history(
    prior_history: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    indexed = [(index, dict(row)) for index, row in enumerate(prior_history)]
    indexed.sort(key=lambda item: (str(item[1].get("as_of_date") or ""), item[0]))
    return [row for _, row in indexed]


def _compatible_history_tail(
    prior_history: Sequence[Mapping[str, Any]],
    methodology_version: str,
) -> list[dict[str, Any]]:
    compatible_reversed: list[dict[str, Any]] = []
    for row in reversed(_ordered_prior_history(prior_history)):
        row_version = str(row.get("methodology_version") or methodology_version)
        if row_version != methodology_version:
            break
        compatible_reversed.append(row)
    return list(reversed(compatible_reversed))


def _positive_int(value: Any) -> int | None:
    number = _finite_float(value)
    if number is None or number <= 0.0 or not number.is_integer():
        return None
    return int(number)


def _ranking_streak(
    prior_history: Sequence[Mapping[str, Any]],
    current: Mapping[str, Any],
    methodology_version: str,
) -> int:
    rows = [*_ordered_prior_history(prior_history), dict(current)]
    streak = 0
    later_date: date | None = None
    for row in reversed(rows):
        raw_date = str(row.get("as_of_date") or "")
        try:
            row_date = date.fromisoformat(raw_date) if raw_date else None
        except ValueError:
            break
        if later_date is not None and (
            row_date is None or (later_date - row_date).days != 1
        ):
            break
        row_version = str(row.get("methodology_version") or methodology_version)
        if row_version != methodology_version:
            break
        rank = _positive_int(row.get("rank"))
        ranked_count = _positive_int(row.get("ranked_count"))
        if rank is None or ranked_count is None:
            break
        if _finite_float(row.get("score_5d")) is None:
            break
        top_quartile_count = max(1, math.ceil(ranked_count * 0.25))
        if rank > top_quartile_count:
            break
        streak += 1
        if row_date is not None:
            later_date = row_date
    return streak


def _trailing_percentile(
    scores: Sequence[float], current_score: float | None
) -> float | None:
    if current_score is None or len(scores) < 20:
        return None
    return 100.0 * sum(value <= current_score for value in scores) / len(scores)


def classify_sentiment_cycle(
    assessment: Mapping[str, Any],
    prior_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    methodology_version = str(
        assessment.get("methodology_version") or METHODOLOGY_VERSION
    )
    compatible_prior = _compatible_history_tail(
        prior_history,
        methodology_version,
    )
    score = _finite_float(assessment.get("score_5d"))
    prior_scores = [
        value
        for row in compatible_prior
        if (value := _finite_float(row.get("score_5d"))) is not None
    ]
    scores_with_current = [*prior_scores]
    if score is not None:
        scores_with_current.append(score)
    recent_slope = _ols_slope(scores_with_current)
    prior_slope = _ols_slope(prior_scores)
    slope_direction = _slope_direction(recent_slope)

    breadth_5d = _assessment_number(
        assessment,
        "breadth_5d",
        component_name="price",
        component_key="breadth_5d",
    )
    breadth_20d = _assessment_number(
        assessment,
        "breadth_20d",
        component_name="price",
        component_key="breadth_20d",
    )
    breadth_change = (
        breadth_5d - breadth_20d
        if breadth_5d is not None and breadth_20d is not None
        else None
    )
    breadth_state = (
        "expanding"
        if breadth_change is not None and breadth_change >= 0.10
        else "contracting"
        if breadth_change is not None and breadth_change <= -0.10
        else "stable"
        if breadth_change is not None
        else "unavailable"
    )

    topic_concentration = _assessment_number(
        assessment,
        "news_topic_concentration_5d",
        component_name="news",
        component_key="topic_concentration",
    )
    volume_ratio_5d = _assessment_number(
        assessment,
        "volume_ratio_5d",
        component_name="price",
        component_key="volume_ratio_5d",
    )
    ranking_streak = _ranking_streak(
        prior_history,
        assessment,
        methodology_version,
    )
    trailing_percentile = _trailing_percentile(scores_with_current, score)

    crowding_signals: list[str] = []
    if ranking_streak >= 5:
        crowding_signals.append("top_quartile_streak")
    if topic_concentration is not None and topic_concentration >= 0.60:
        crowding_signals.append("topic_concentration")
    if (
        volume_ratio_5d is not None
        and volume_ratio_5d >= 1.8
        and score is not None
        and abs(score) >= 60.0
    ):
        crowding_signals.append("high_volume_extreme_score")
    crowding = bool(crowding_signals)

    positive_deceleration = (
        score is not None
        and score >= 50.0
        and prior_slope is not None
        and prior_slope >= 2.0
        and recent_slope is not None
        and recent_slope <= 0.5 * prior_slope
    )
    negative_deceleration = (
        score is not None
        and score <= -50.0
        and prior_slope is not None
        and prior_slope <= -2.0
        and recent_slope is not None
        and recent_slope >= 0.5 * prior_slope
    )
    decelerating = positive_deceleration or negative_deceleration
    deceleration_direction = (
        "positive"
        if positive_deceleration
        else "negative"
        if negative_deceleration
        else None
    )
    change = _finite_float(assessment.get("change"))

    if (
        score is not None
        and (
            score >= 70.0
            or (
                trailing_percentile is not None
                and trailing_percentile >= 90.0
                and ranking_streak >= 3
            )
        )
        and (crowding or decelerating)
    ):
        phase = "overheating"
    elif score is not None and score <= -60.0 and slope_direction == "negative":
        phase = "capitulation"
    elif (
        score is not None
        and score <= 20.0
        and change is not None
        and change >= 10.0
        and slope_direction == "positive"
    ):
        phase = "recovery"
    elif (
        score is not None
        and -20.0 <= score < 40.0
        and change is not None
        and change >= 10.0
        and slope_direction == "positive"
        and breadth_state == "expanding"
    ):
        phase = "ignition"
    elif (
        score is not None
        and 20.0 <= score < 70.0
        and slope_direction == "positive"
        and breadth_5d is not None
        and breadth_5d >= 0.55
    ):
        phase = "expansion"
    elif (
        score is not None
        and score > -20.0
        and (
            (change is not None and change <= -10.0)
            or (
                slope_direction == "negative"
                and breadth_state == "contracting"
            )
        )
    ):
        phase = "cooling"
    else:
        phase = "consolidation"

    return {
        "phase": phase,
        "recent_slope": recent_slope,
        "prior_slope": prior_slope,
        "slope_direction": slope_direction,
        "breadth_5d": breadth_5d,
        "breadth_20d": breadth_20d,
        "breadth_change": breadth_change,
        "breadth_state": breadth_state,
        "trailing_percentile": trailing_percentile,
        "ranking_streak": ranking_streak,
        "topic_concentration": topic_concentration,
        "volume_ratio_5d": volume_ratio_5d,
        "crowding": crowding,
        "crowding_signals": crowding_signals,
        "decelerating": decelerating,
        "deceleration_direction": deceleration_direction,
        "history_scores": len(scores_with_current),
    }


def finalize_industry_sentiment(
    assessment: Mapping[str, Any],
    *,
    prior_history: Sequence[Mapping[str, Any]],
    rank: int | None,
    ranked_count: int,
) -> dict[str, Any]:
    finalized = dict(assessment)
    finalized["rank"] = rank
    finalized["ranked_count"] = ranked_count
    cycle = classify_sentiment_cycle(finalized, prior_history)
    finalized["cycle_phase"] = cycle["phase"]
    finalized["cycle_diagnostics"] = {
        key: value for key, value in cycle.items() if key != "phase"
    }
    return finalized
