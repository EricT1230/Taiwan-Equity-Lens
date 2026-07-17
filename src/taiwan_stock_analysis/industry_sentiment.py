from collections import Counter, defaultdict
from datetime import datetime
import math
from typing import Any, Mapping, Protocol, Sequence

from taiwan_stock_analysis._sentiment_composite import (
    _freshness_entry as _component_freshness_entry,
    combine_sentiment_components_impl as _combine_sentiment_components_impl,
    component_freshness_state as _component_freshness_state,
)
from taiwan_stock_analysis._sentiment_cycle import (
    classify_sentiment_cycle_impl as _classify_sentiment_cycle_impl,
)
from taiwan_stock_analysis._sentiment_flow import (
    score_fund_flow_component_impl as _score_fund_flow_component_impl,
)
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


def score_fund_flow_component(
    rows: Sequence[Mapping[str, Any]],
    *,
    price_covered_stock_ids: Sequence[str],
    expected_session_dates: Sequence[str],
) -> dict[str, Any]:
    return _score_fund_flow_component_impl(
        rows,
        price_covered_stock_ids=price_covered_stock_ids,
        expected_session_dates=expected_session_dates,
    )


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


def combine_sentiment_components(
    components: Mapping[str, Mapping[str, Any]],
    *,
    freshness: Mapping[str, Any],
    source_errors: Sequence[str],
) -> dict[str, Any]:
    return _combine_sentiment_components_impl(
        components,
        freshness=freshness,
        source_errors=source_errors,
        configured_weights=CONFIGURED_WEIGHTS,
        methodology_version=METHODOLOGY_VERSION,
        label_classifier=classify_sentiment_label,
    )


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
        "news": _component_freshness_state(
            _component_freshness_entry(freshness, "news"),
            local_fresh=_has_recent_news(news_component, as_of=as_of),
            local_failure="no_recent_industry_news_48h",
        ),
        "price": _component_freshness_state(
            _component_freshness_entry(freshness, "price"),
            local_fresh=True,
            local_failure="missing_price_coverage",
        ),
        "fund_flow": _component_freshness_state(
            _component_freshness_entry(freshness, "fund_flow"),
            local_fresh=_has_recent_flow(
                fund_flow_component,
                expected_session_dates,
            ),
            local_failure="no_recent_expected_flow_session",
        ),
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


def classify_sentiment_cycle(
    assessment: Mapping[str, Any],
    prior_history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _classify_sentiment_cycle_impl(
        assessment,
        prior_history,
        default_methodology_version=METHODOLOGY_VERSION,
    )


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
