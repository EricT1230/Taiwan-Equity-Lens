import unittest
from datetime import datetime, timedelta, timezone

from taiwan_stock_analysis.industry_sentiment import (
    NewsSentimentReviewer,
    _current_sentiment_snapshot,
    build_industry_sentiment_base,
    classify_sentiment_cycle,
    classify_sentiment_label,
    combine_sentiment_components,
    finalize_industry_sentiment,
    score_fund_flow_component,
    score_news_component,
    score_price_component,
)
from taiwan_stock_analysis.sentiment_history import SENTIMENT_HISTORY_COLUMNS
from taiwan_stock_analysis.sentiment_lexicon import (
    INTENSIFIERS,
    LEXICON_VERSION,
    NEGATIONS,
    NEGATIVE_TERMS,
    POSITIVE_TERMS,
    normalize_sentiment_text,
    score_news_text,
    tokenize_sentiment_text,
)


AS_OF = datetime(2026, 7, 17, 12, tzinfo=timezone(timedelta(hours=8)))


def news_row(
    title: str,
    published_at: str,
    *,
    source: str = "source-a",
    summary: str = "",
    url: str = "",
    keywords: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "source": source,
        "url": url,
        "keywords": keywords or [],
    }


class SentimentLexiconTests(unittest.TestCase):
    def test_v1_lexicon_is_exact_and_versioned(self):
        self.assertEqual(LEXICON_VERSION, "zh-finance-v1")
        self.assertEqual(
            POSITIVE_TERMS,
            {
                "優於預期": 2.0,
                "創新高": 1.8,
                "上修": 1.6,
                "轉盈": 1.6,
                "強勁": 1.4,
                "擴產": 1.3,
                "成長": 1.2,
                "受惠": 1.2,
                "訂單增加": 1.2,
                "買超": 1.0,
                "資金流入": 1.0,
                "回溫": 0.9,
            },
        )
        self.assertEqual(
            NEGATIVE_TERMS,
            {
                "低於預期": -2.0,
                "創新低": -1.8,
                "下修": -1.6,
                "轉虧": -1.6,
                "衰退": -1.4,
                "減產": -1.3,
                "訂單減少": -1.2,
                "賣超": -1.0,
                "資金流出": -1.0,
                "降溫": -0.9,
                "裁員": -1.1,
                "違約": -1.8,
            },
        )
        self.assertEqual(NEGATIONS, {"未", "不", "無", "非", "尚未", "未見"})
        self.assertEqual(
            INTENSIFIERS,
            {"大幅": 1.5, "顯著": 1.4, "強烈": 1.3, "持續": 1.2},
        )

    def test_normalization_uses_nfkc_lowercase_and_collapsed_whitespace(self):
        self.assertEqual(normalize_sentiment_text("  ＡＢＣ\n\t成長  "), "abc 成長")

    def test_tokenization_uses_deterministic_longest_match(self):
        self.assertEqual(tokenize_sentiment_text("優於預期成長")[:2], ["優於預期", "成長"])

    def test_text_score_applies_sentiment_negation_and_intensity(self):
        self.assertGreater(score_news_text("營收大幅成長"), 0)
        self.assertLess(score_news_text("營收未成長"), 0)
        self.assertLess(score_news_text("獲利顯著下修"), score_news_text("獲利下修"))

    def test_text_score_uses_only_largest_intensity_once(self):
        self.assertAlmostEqual(score_news_text("大幅顯著成長"), 45.0)

    def test_text_score_limits_negation_lookback_to_three_tokens(self):
        self.assertLess(score_news_text("未甲乙成長"), 0)
        self.assertGreater(score_news_text("未甲乙丙成長"), 0)


class NewsComponentTests(unittest.TestCase):
    def test_deduplicates_url_then_normalized_title_and_weights_recent_news_more(self):
        rows = [
            news_row(
                "需求成長",
                "2026-07-17T11:00:00+08:00",
                source="source-a",
                url="https://example.test/recent",
            ),
            news_row(
                "重複網址但標題不同",
                "2026-07-17T10:00:00+08:00",
                source="source-b",
                url="https://example.test/recent",
            ),
            news_row(
                "  需求成長  ",
                "2026-07-17T09:00:00+08:00",
                source="source-c",
                url="https://example.test/duplicate-title",
            ),
            news_row(
                "獲利上修",
                "2026-07-13T12:00:00+08:00",
                source="source-a",
                url="https://example.test/old",
            ),
            news_row(
                "訂單減少",
                "2026-07-16T12:00:00+08:00",
                source="source-b",
                url="https://example.test/negative",
            ),
        ]

        component = score_news_component(rows, as_of=AS_OF)

        self.assertEqual(component["coverage"]["articles_5d"], 3)
        self.assertEqual(component["coverage"]["excluded_duplicate"], 2)
        self.assertEqual(len(component["article_scores"]), 3)
        weights = {
            article["normalized_title"]: article["raw_weight"]
            for article in component["article_scores"]
        }
        self.assertGreater(weights["需求成長"], weights["獲利上修"])
        self.assertLessEqual(component["source_concentration"], 0.4)
        self.assertIn("source concentration clipped", component["warnings"])
        self.assertEqual(component["status"], "ready")

    def test_out_of_window_duplicates_cannot_hide_valid_article_in_either_order(self):
        future = news_row(
            "未來上修",
            "2026-07-18T12:00:00+08:00",
            url="https://example.test/shared-url",
        )
        valid_url = news_row(
            "營收成長",
            "2026-07-17T11:00:00+08:00",
            url="https://example.test/shared-url",
        )
        stale = news_row(
            "  庫存成長  ",
            "2026-06-26T11:59:59+08:00",
            url="https://example.test/stale-title",
        )
        valid_title = news_row(
            "庫存成長",
            "2026-07-17T10:00:00+08:00",
            url="https://example.test/valid-title",
        )

        for rows in (
            [future, valid_url, stale, valid_title],
            [valid_title, stale, valid_url, future],
        ):
            with self.subTest(order=[row["url"] for row in rows]):
                component = score_news_component(rows, as_of=AS_OF)

                self.assertEqual(component["coverage"]["articles_5d"], 2)
                self.assertEqual(component["coverage"]["excluded_future"], 1)
                self.assertEqual(component["coverage"]["excluded_too_old"], 1)
                self.assertEqual(
                    {row["normalized_title"] for row in component["article_scores"]},
                    {"營收成長", "庫存成長"},
                )

    def test_latest_eligible_duplicate_is_selected_independent_of_input_order(self):
        older = news_row(
            "較早成長",
            "2026-07-16T12:00:00+08:00",
            url="https://example.test/same-story",
        )
        latest = news_row(
            "最新上修",
            "2026-07-17T11:00:00+08:00",
            url="https://example.test/same-story",
        )

        for rows in ([older, latest], [latest, older]):
            with self.subTest(order=[row["title"] for row in rows]):
                component = score_news_component(rows, as_of=AS_OF)

                self.assertEqual(component["coverage"]["articles_5d"], 1)
                self.assertEqual(component["coverage"]["excluded_duplicate"], 1)
                self.assertEqual(
                    component["article_scores"][0]["normalized_title"],
                    "最新上修",
                )

    def test_source_cap_leaves_clipped_weight_neutral_even_for_one_source(self):
        component = score_news_component(
            [
                news_row(
                    "營收成長",
                    "2026-07-17T12:00:00+08:00",
                    summary="營收成長",
                    url="https://example.test/only",
                )
            ],
            as_of=AS_OF,
        )

        self.assertAlmostEqual(component["article_scores"][0]["article_score"], 30.0)
        self.assertAlmostEqual(component["score_5d"], 12.0)
        self.assertAlmostEqual(component["source_concentration"], 0.4)
        self.assertEqual(component["status"], "partial")
        self.assertIn("low news coverage: fewer than 3 articles in 5d", component["warnings"])

    def test_ignores_future_and_too_old_rows_in_both_windows(self):
        component = score_news_component(
            [
                news_row("營收成長", "2026-07-17T11:00:00+08:00", url="recent"),
                news_row("未來上修", "2026-07-18T12:00:00+08:00", url="future"),
                news_row("很舊成長", "2026-06-26T11:59:59+08:00", url="old"),
            ],
            as_of=AS_OF,
        )

        self.assertEqual(component["coverage"]["articles_5d"], 1)
        self.assertEqual(component["coverage"]["articles_20d"], 1)
        self.assertEqual(component["coverage"]["excluded_future"], 1)
        self.assertEqual(component["coverage"]["excluded_too_old"], 1)
        self.assertEqual([row["normalized_title"] for row in component["article_scores"]], ["營收成長"])

    def test_future_and_too_old_exclusions_are_explicit_without_neutral_weight(self):
        valid_rows = [
            news_row("甲成長", "2026-07-17T11:00:00+08:00", source="a", url="a"),
            news_row("乙上修", "2026-07-17T10:00:00+08:00", source="b", url="b"),
            news_row("丙受惠", "2026-07-17T09:00:00+08:00", source="c", url="c"),
        ]
        component = score_news_component(
            [
                *valid_rows,
                news_row("未來下修", "2026-07-18T12:00:00+08:00", url="future"),
                news_row("過期下修", "2026-06-26T11:59:59+08:00", url="old"),
            ],
            as_of=AS_OF,
        )
        clean_component = score_news_component(valid_rows, as_of=AS_OF)

        self.assertEqual(component["coverage"]["articles_5d"], 3)
        self.assertEqual(component["coverage"]["articles_20d"], 3)
        self.assertEqual(component["coverage"]["excluded_future"], 1)
        self.assertEqual(component["coverage"]["excluded_too_old"], 1)
        self.assertEqual(component["score_5d"], clean_component["score_5d"])
        self.assertEqual(component["score_20d"], clean_component["score_20d"])
        self.assertEqual(component["status"], "partial")
        self.assertIn("future published_at: 1 article excluded", component["warnings"])
        self.assertIn("published_at older than 20d: 1 article excluded", component["warnings"])

    def test_invalid_timestamps_are_excluded_and_reported_as_partial(self):
        component = score_news_component(
            [
                news_row("有效成長", "2026-07-17T11:00:00+08:00", url="valid"),
                news_row("錯誤上修", "not-a-date", url="invalid"),
                {"title": "缺日期成長", "source": "source-c", "url": "missing"},
            ],
            as_of=AS_OF,
        )

        self.assertEqual(component["coverage"]["articles_5d"], 1)
        self.assertEqual(component["coverage"]["excluded_invalid_timestamp"], 2)
        self.assertEqual(len(component["article_scores"]), 1)
        self.assertEqual(component["status"], "partial")
        self.assertIn("invalid or missing published_at: 2 articles excluded", component["warnings"])

    def test_only_invalid_timestamps_produce_insufficient_data_not_neutral_evidence(self):
        component = score_news_component(
            [news_row("錯誤成長", "not-a-date", url="invalid")],
            as_of=AS_OF,
        )

        self.assertIsNone(component["score_5d"])
        self.assertIsNone(component["score_20d"])
        self.assertEqual(component["coverage"]["articles_5d"], 0)
        self.assertEqual(component["coverage"]["articles_20d"], 0)
        self.assertEqual(component["coverage"]["excluded_invalid_timestamp"], 1)
        self.assertEqual(component["status"], "insufficient_data")
        self.assertIn("invalid or missing published_at: 1 article excluded", component["warnings"])

    def test_rows_without_scorable_text_are_excluded_not_neutral_coverage(self):
        component = score_news_component(
            [
                news_row("", "2026-07-17T11:00:00+08:00", source="a", url="blank-a"),
                news_row("   ", "2026-07-17T10:00:00+08:00", source="b", url="blank-b"),
                {
                    "published_at": "2026-07-17T09:00:00+08:00",
                    "source": "c",
                    "url": "blank-c",
                },
            ],
            as_of=AS_OF,
        )

        self.assertEqual(component["coverage"]["articles_5d"], 0)
        self.assertEqual(component["coverage"]["articles_20d"], 0)
        self.assertEqual(component["coverage"]["excluded_unscorable_text"], 3)
        self.assertIsNone(component["score_5d"])
        self.assertIsNone(component["score_20d"])
        self.assertEqual(component["status"], "insufficient_data")
        self.assertIn("missing scorable text: 3 articles excluded", component["warnings"])

    def test_summary_only_articles_have_distinct_deterministic_event_signatures(self):
        url_article = news_row(
            "",
            "2026-07-17T11:00:00+08:00",
            source="SOURCE-A",
            summary="伺服器供應鏈近況",
            url="HTTPS://EXAMPLE.TEST/STORY",
        )
        composite_article = news_row(
            "",
            "2026-07-17T10:00:00+08:00",
            source="ＳＯＵＲＣＥ-B",
            summary="成熟製程供需觀察",
        )
        signatures_by_order = []

        for rows in ([url_article, composite_article], [composite_article, url_article]):
            with self.subTest(order=[row["summary"] for row in rows]):
                component = score_news_component(rows, as_of=AS_OF)
                signatures = {
                    row["summary"]: tuple(row["event_signature"])
                    for row in component["article_scores"]
                }
                signatures_by_order.append(signatures)

                self.assertEqual(component["coverage"]["articles_5d"], 2)
                self.assertEqual(component["topic_concentration"], 0.5)
                self.assertNotEqual(
                    signatures["伺服器供應鏈近況"],
                    signatures["成熟製程供需觀察"],
                )
                self.assertEqual(signatures["伺服器供應鏈近況"][0], "__url__")
                self.assertEqual(signatures["成熟製程供需觀察"][0], "__summary__")

        self.assertEqual(signatures_by_order[0], signatures_by_order[1])

    def test_summary_signature_exact_collisions_use_stable_occurrence_order(self):
        compact = news_row(
            "",
            "2026-07-17T11:00:00+08:00",
            source="source-a",
            summary="供需觀察",
        )
        padded = news_row(
            "",
            "2026-07-17T11:00:00+08:00",
            source="source-a",
            summary="  供需觀察  ",
        )
        signatures_by_order = []

        for rows in ([compact, padded], [padded, compact]):
            component = score_news_component(rows, as_of=AS_OF)
            signatures_by_order.append(
                {
                    row["summary"]: tuple(row["event_signature"])
                    for row in component["article_scores"]
                }
            )
            self.assertEqual(component["topic_concentration"], 0.5)

        self.assertEqual(signatures_by_order[0], signatures_by_order[1])

    def test_summary_signature_true_ties_use_canonical_retained_metadata(self):
        def tied_article(identifier: str, *, reverse_metadata: bool) -> dict[str, object]:
            article = news_row(
                "",
                "2026-07-17T11:00:00+08:00",
                source="source-a",
                summary="供需觀察",
            )
            article["id"] = identifier
            if reverse_metadata:
                article["metadata"] = {
                    "facts": {"beta": 2, "alpha": 1},
                    "tags": ["產業", 7, True, None],
                }
            else:
                article["metadata"] = {
                    "tags": ["產業", 7, True, None],
                    "facts": {"alpha": 1, "beta": 2},
                }
            return article

        signatures_by_order = []
        for rows in (
            [
                tied_article("a", reverse_metadata=False),
                tied_article("b", reverse_metadata=False),
            ],
            [
                tied_article("b", reverse_metadata=True),
                tied_article("a", reverse_metadata=True),
            ],
        ):
            component = score_news_component(rows, as_of=AS_OF)
            signatures_by_order.append(
                {
                    row["id"]: tuple(row["event_signature"])
                    for row in component["article_scores"]
                }
            )
            self.assertEqual(component["topic_concentration"], 0.5)

        self.assertEqual(signatures_by_order[0], signatures_by_order[1])

    def test_event_signatures_use_first_three_distinct_normalized_keywords(self):
        rows = [
            news_row(
                "甲成長",
                "2026-07-17T11:00:00+08:00",
                source="a",
                url="1",
                keywords=["ＡＩ", "ai", "伺服器", "晶片", "需求"],
            ),
            news_row(
                "乙上修",
                "2026-07-17T10:00:00+08:00",
                source="b",
                url="2",
                keywords=["ai", "伺服器", "晶片"],
            ),
            news_row(
                "丙受惠",
                "2026-07-17T09:00:00+08:00",
                source="c",
                url="3",
            ),
            news_row(
                "丁下修",
                "2026-07-17T08:00:00+08:00",
                source="d",
                url="4",
            ),
        ]

        component = score_news_component(rows, as_of=AS_OF)

        self.assertEqual(component["novelty"], 1.0)
        self.assertEqual(component["topic_concentration"], 0.5)
        self.assertAlmostEqual(component["positive_topic_concentration"], 2 / 3)
        self.assertEqual(component["negative_topic_concentration"], 1.0)

    def test_default_output_is_deterministic_channel_only(self):
        component = score_news_component([], as_of=AS_OF)

        self.assertEqual(
            set(component),
            {
                "score_5d",
                "score_20d",
                "coverage",
                "article_scores",
                "source_concentration",
                "topic_concentration",
                "positive_topic_concentration",
                "negative_topic_concentration",
                "novelty",
                "status",
                "warnings",
            },
        )
        self.assertTrue(hasattr(NewsSentimentReviewer, "review"))
        self.assertNotIn("llm_review", component)


class PriceComponentTests(unittest.TestCase):
    def test_price_score_clamps_exact_bullish_and_bearish_boundaries(self):
        bullish = score_price_component(
            {
                "average_return_5d": 8.0,
                "average_return_20d": 15.0,
                "positive_breadth_5d": 1.0,
                "positive_breadth_20d": 1.0,
                "average_volume_ratio_5d": 2.0,
                "coverage_ratio_5d": 1.0,
                "coverage_ratio_20d": 1.0,
                "high_count_20d": 4,
                "low_count_20d": 0,
            }
        )
        bearish = score_price_component(
            {
                "average_return_5d": -8.0,
                "average_return_20d": -15.0,
                "positive_breadth_5d": 0.0,
                "positive_breadth_20d": 0.0,
                "average_volume_ratio_5d": 2.0,
                "coverage_ratio_5d": 1.0,
                "coverage_ratio_20d": 1.0,
                "high_count_20d": 0,
                "low_count_20d": 4,
            }
        )

        self.assertEqual(bullish["score_5d"], 100.0)
        self.assertEqual(bullish["score_20d"], 100.0)
        self.assertEqual(bearish["score_5d"], -100.0)
        self.assertEqual(bearish["score_20d"], -100.0)
        self.assertEqual(bullish["status"], "ready")
        self.assertEqual(bullish["high_count_20d"], 4)

    def test_price_window_is_unavailable_when_any_required_input_is_invalid(self):
        component = score_price_component(
            {
                "average_return_5d": 4.0,
                "average_return_20d": 7.5,
                "positive_breadth_5d": None,
                "positive_breadth_20d": 0.75,
                "average_volume_ratio_5d": 1.5,
                "coverage_ratio_5d": 0.5,
                "coverage_ratio_20d": 0.75,
                "high_count_20d": 2,
                "low_count_20d": 1,
            }
        )

        self.assertIsNone(component["score_5d"])
        self.assertAlmostEqual(component["score_20d"], 50.0)
        self.assertEqual(component["status"], "partial")
        self.assertEqual(component["coverage_ratio_5d"], 0.5)
        self.assertEqual(component["coverage_ratio_20d"], 0.75)
        self.assertIn(
            "price 5d unavailable: missing or invalid positive_breadth_5d",
            component["warnings"],
        )


class FundFlowComponentTests(unittest.TestCase):
    @staticmethod
    def three_valid_day_rows() -> tuple[list[str], list[dict[str, object]]]:
        dates = [f"2026-07-{day:02d}" for day in range(1, 6)]
        rows = [
            {
                "date": value,
                "stock_id": stock_id,
                "total_net": 10.0,
                "traded_shares": 1000.0,
                "source": "primary",
            }
            for value in dates[:3]
            for stock_id in ("1111", "2222")
        ]
        return dates, rows

    def test_flow_uses_only_valid_expected_dates_for_both_windows(self):
        dates = [f"2026-06-{day:02d}" for day in range(1, 21)]
        valid_dates = {*dates[:7], *dates[-3:]}
        rows = []
        for value in dates:
            if value in valid_dates:
                rows.extend(
                    [
                        {
                            "date": value,
                            "stock_id": "1111",
                            "total_net": 50.0,
                            "traded_shares": 1000.0,
                        },
                        {
                            "date": value,
                            "stock_id": "2222",
                            "total_net": 50.0,
                            "traded_shares": 1000.0,
                        },
                    ]
                )
            else:
                rows.append(
                    {
                        "date": value,
                        "stock_id": "1111",
                        "total_net": -1_000_000.0,
                        "traded_shares": 1.0,
                    }
                )

        component = score_fund_flow_component(
            rows,
            price_covered_stock_ids=["1111", "2222", "3333"],
            expected_session_dates=dates,
        )

        self.assertEqual(component["valid_days_5d"], 3)
        self.assertEqual(component["valid_days_20d"], 10)
        self.assertEqual(component["missing_dates_5d"], dates[-5:-3])
        self.assertAlmostEqual(component["coverage_by_date_5d"][dates[-5]], 1 / 3)
        self.assertEqual(component["net_shares_5d"], 300.0)
        self.assertEqual(component["traded_shares_5d"], 6000.0)
        self.assertEqual(component["persistence_5d"], 1.0)
        self.assertEqual(component["score_5d"], 100.0)
        self.assertEqual(component["score_20d"], 100.0)
        self.assertEqual(component["status"], "ready")

    def test_flow_is_partial_when_only_the_five_day_minimum_is_met(self):
        dates = [f"2026-07-{day:02d}" for day in range(1, 6)]
        rows = [
            {
                "date": value,
                "stock_id": stock_id,
                "total_net": 10.0,
                "traded_shares": 1000.0,
            }
            for value in dates[-3:]
            for stock_id in ("1111", "2222")
        ]

        component = score_fund_flow_component(
            rows,
            price_covered_stock_ids=["1111", "2222"],
            expected_session_dates=dates,
        )

        self.assertIsNotNone(component["score_5d"])
        self.assertIsNone(component["score_20d"])
        self.assertEqual(component["status"], "partial")
        self.assertIn(
            "fund_flow 20d unavailable: 3 valid sessions; requires 10",
            component["warnings"],
        )

    def test_flow_without_price_covered_stocks_is_explicitly_insufficient(self):
        component = score_fund_flow_component(
            [],
            price_covered_stock_ids=[None, "", "   "],
            expected_session_dates=["2026-07-17"],
        )

        self.assertIsNone(component["score_5d"])
        self.assertIsNone(component["score_20d"])
        self.assertEqual(component["expected_stocks"], 0)
        self.assertEqual(component["status"], "insufficient_data")
        self.assertIn("fund_flow unavailable: no price-covered stocks", component["warnings"])

    def test_identical_flow_pairs_contribute_once_independent_of_input_order(self):
        dates, rows = self.three_valid_day_rows()
        duplicate = {**rows[0], "source": "backup"}

        results = [
            score_fund_flow_component(
                ordered_rows,
                price_covered_stock_ids=["1111", "2222"],
                expected_session_dates=dates,
            )
            for ordered_rows in ([*rows, duplicate], [duplicate, *rows])
        ]

        for component in results:
            self.assertEqual(component["valid_days_5d"], 3)
            self.assertEqual(component["net_shares_5d"], 60.0)
            self.assertEqual(component["traded_shares_5d"], 6000.0)
            self.assertIn(
                "fund_flow 5d collapsed identical duplicate pair "
                "(2026-07-01, 1111) from sources backup, primary",
                component["warnings"],
            )
        self.assertEqual(results[0], results[1])

    def test_conflicting_flow_pairs_are_rejected_from_coverage_and_sums(self):
        dates, rows = self.three_valid_day_rows()
        conflicting = {
            **rows[0],
            "total_net": 999.0,
            "source": "backup",
        }

        results = [
            score_fund_flow_component(
                ordered_rows,
                price_covered_stock_ids=["1111", "2222"],
                expected_session_dates=dates,
            )
            for ordered_rows in ([*rows, conflicting], [conflicting, *rows])
        ]

        for component in results:
            self.assertEqual(component["coverage_by_date_5d"][dates[0]], 0.5)
            self.assertEqual(component["valid_days_5d"], 2)
            self.assertEqual(component["net_shares_5d"], 40.0)
            self.assertEqual(component["traded_shares_5d"], 4000.0)
            self.assertIsNone(component["score_5d"])
            self.assertIn(
                "fund_flow 5d rejected conflicting duplicate pair "
                "(2026-07-01, 1111) from sources backup, primary",
                component["warnings"],
            )
        self.assertEqual(results[0], results[1])


class CompositeSentimentTests(unittest.TestCase):
    @staticmethod
    def components() -> dict[str, dict[str, object]]:
        return {
            "news": {
                "score_5d": 40.0,
                "score_20d": 20.0,
                "coverage": {"articles_5d": 5, "articles_20d": 12},
                "status": "ready",
                "warnings": [],
            },
            "price": {
                "score_5d": 20.0,
                "score_20d": 10.0,
                "breadth_5d": 0.62,
                "breadth_20d": 0.55,
                "coverage_ratio_5d": 0.85,
                "coverage_ratio_20d": 0.80,
                "status": "ready",
                "warnings": [],
            },
            "fund_flow": {
                "score_5d": 10.0,
                "score_20d": 0.0,
                "valid_days_5d": 4,
                "valid_days_20d": 12,
                "persistence_5d": 0.6,
                "status": "ready",
                "warnings": [],
            },
        }

    def test_label_boundaries_are_exact(self):
        self.assertEqual(classify_sentiment_label(60.0), "extremely_optimistic")
        self.assertEqual(classify_sentiment_label(20.0), "optimistic")
        self.assertEqual(classify_sentiment_label(-19.999), "neutral")
        self.assertEqual(classify_sentiment_label(-20.0), "pessimistic")
        self.assertEqual(classify_sentiment_label(-60.0), "extremely_pessimistic")

    def test_two_complete_fresh_components_renormalize_with_medium_confidence(self):
        components = self.components()
        components["fund_flow"] = {
            "score_5d": None,
            "score_20d": None,
            "status": "insufficient_data",
            "warnings": ["fund_flow 5d unavailable: 0 valid sessions; requires 3"],
        }

        assessment = combine_sentiment_components(
            components,
            freshness={"news": True, "price": True, "fund_flow": True},
            source_errors=[],
        )

        self.assertEqual(assessment["status"], "partial")
        self.assertEqual(assessment["confidence"], "medium")
        self.assertAlmostEqual(sum(assessment["effective_weights"].values()), 1.0)
        self.assertAlmostEqual(assessment["effective_weights"]["news"], 4 / 7)
        self.assertAlmostEqual(assessment["effective_weights"]["price"], 3 / 7)
        self.assertAlmostEqual(
            assessment["components"]["news"]["contribution_5d"],
            40.0 * 4 / 7,
        )
        self.assertEqual(assessment["temperature"], "warming")
        self.assertEqual(assessment["label"], "optimistic")
        self.assertLessEqual(len(assessment["reasons"]), 3)
        self.assertIn("news contribution +22.9", assessment["reasons"])
        self.assertIn("5-day breadth 62.0%", assessment["reasons"])
        self.assertTrue(
            any("fund_flow" in warning and "missing 5d" in warning for warning in assessment["warnings"])
        )

    def test_component_missing_either_window_is_removed_from_both_composites(self):
        components = self.components()
        components["price"]["score_20d"] = None

        assessment = combine_sentiment_components(
            components,
            freshness={"news": "fresh", "price": "fresh", "fund_flow": "fresh"},
            source_errors=[],
        )

        self.assertEqual(set(assessment["effective_weights"]), {"news", "fund_flow"})
        self.assertIsNone(assessment["components"]["price"]["contribution_5d"])
        self.assertIn(
            "price removed from composite: missing 20d score",
            assessment["warnings"],
        )

    def test_fewer_than_two_usable_fresh_components_has_no_numeric_evidence(self):
        components = self.components()
        components["price"]["score_5d"] = None
        components["fund_flow"]["score_20d"] = None

        assessment = combine_sentiment_components(
            components,
            freshness={"news": True, "price": True, "fund_flow": False},
            source_errors=[],
        )

        self.assertEqual(assessment["status"], "insufficient_data")
        self.assertIsNone(assessment["score_5d"])
        self.assertIsNone(assessment["baseline_20d"])
        self.assertIsNone(assessment["confidence"])
        self.assertIsNone(assessment["label"])

    def test_high_confidence_requires_all_fixed_coverage_gates(self):
        assessment = combine_sentiment_components(
            self.components(),
            freshness={
                "news": {"status": "fresh"},
                "price": {"status": "fresh"},
                "fund_flow": {"status": "fresh"},
            },
            source_errors=[],
        )

        self.assertEqual(assessment["status"], "ready")
        self.assertEqual(assessment["confidence"], "high")
        self.assertAlmostEqual(assessment["score_5d"], 25.0)
        self.assertAlmostEqual(assessment["baseline_20d"], 11.0)
        self.assertAlmostEqual(assessment["change"], 14.0)

    def test_source_error_and_weak_coverage_force_low_confidence_with_reasons(self):
        components = self.components()
        components["price"]["coverage_ratio_5d"] = 0.79

        assessment = combine_sentiment_components(
            components,
            freshness={"news": True, "price": True, "fund_flow": True},
            source_errors=["fund flow source timeout"],
        )

        self.assertEqual(assessment["confidence"], "low")
        self.assertIn(
            "confidence downgraded to low: price 5d coverage 79.0% is below 80.0%",
            assessment["warnings"],
        )
        self.assertIn("source error: fund flow source timeout", assessment["warnings"])

    def test_freshness_source_error_forces_low_confidence_without_duplicate_error(self):
        for fund_flow_freshness in (
            "source_error",
            {"status": "source_error", "error": "fund flow source timeout"},
        ):
            with self.subTest(fund_flow_freshness=fund_flow_freshness):
                assessment = combine_sentiment_components(
                    self.components(),
                    freshness={
                        "news": "fresh",
                        "price": "fresh",
                        "fund_flow": fund_flow_freshness,
                    },
                    source_errors=[],
                )

                self.assertEqual(assessment["status"], "partial")
                self.assertEqual(assessment["confidence"], "low")
                self.assertEqual(
                    assessment["components"]["fund_flow"]["freshness"]["status"],
                    "source_error",
                )
                self.assertIn(
                    "fund_flow removed from composite: freshness status source_error",
                    assessment["warnings"],
                )
                self.assertIn(
                    "confidence downgraded to low: required-source errors present",
                    assessment["warnings"],
                )

    def test_build_base_composes_current_inputs_without_history_coupling(self):
        dates = [f"2026-06-{day:02d}" for day in range(1, 21)]
        news_rows = [
            news_row(
                f"產業成長 {index}",
                f"2026-07-17T{11 - index:02d}:00:00+08:00",
                source=f"source-{index}",
                url=f"https://example.test/{index}",
            )
            for index in range(5)
        ]
        flow_rows = [
            {
                "date": value,
                "stock_id": stock_id,
                "total_net": 10.0,
                "traded_shares": 1000.0,
            }
            for value in dates
            for stock_id in ("1111", "2222")
        ]
        trend = {
            "average_return_5d": 4.0,
            "average_return_20d": 7.5,
            "positive_breadth_5d": 0.75,
            "positive_breadth_20d": 0.60,
            "average_volume_ratio_5d": 1.5,
            "coverage_ratio_5d": 1.0,
            "coverage_ratio_20d": 1.0,
            "high_count_20d": 1,
            "low_count_20d": 0,
            "covered_stock_ids": ["1111", "2222"],
        }

        assessment = build_industry_sentiment_base(
            news_rows=news_rows,
            trend=trend,
            flow_rows=flow_rows,
            expected_session_dates=dates,
            freshness={
                "news": {"status": "fresh"},
                "industry_trend": {"status": "fresh"},
                "fund_flow": {"status": "fresh"},
            },
            source_errors=[],
            as_of=AS_OF,
        )

        self.assertEqual(assessment["methodology_version"], "industry-sentiment-v1")
        self.assertEqual(assessment["as_of_date"], "2026-07-17")
        self.assertEqual(set(assessment["components"]), {"news", "price", "fund_flow"})
        self.assertEqual(assessment["status"], "ready")
        self.assertEqual(assessment["confidence"], "high")

    def test_build_preserves_specific_source_freshness_states(self):
        assessment = build_industry_sentiment_base(
            news_rows=[],
            trend={},
            flow_rows=[],
            expected_session_dates=[],
            freshness={
                "news": {"status": "stale", "latest": "2026-07-01"},
                "industry_trend": {"status": "missing", "latest": ""},
                "fund_flow": {
                    "status": "source_error",
                    "error": "TWSE timeout",
                },
            },
            source_errors=[],
            as_of=AS_OF,
        )

        self.assertIn(
            "news removed from composite: freshness status stale",
            assessment["warnings"],
        )
        self.assertIn(
            "price removed from composite: freshness status missing",
            assessment["warnings"],
        )
        self.assertIn(
            "fund_flow removed from composite: freshness status source_error",
            assessment["warnings"],
        )
        self.assertEqual(assessment["components"]["news"]["freshness"]["status"], "stale")
        self.assertEqual(assessment["components"]["price"]["freshness"]["status"], "missing")
        self.assertEqual(
            assessment["components"]["fund_flow"]["freshness"]["status"],
            "source_error",
        )

    def test_build_reports_industry_local_freshness_failures(self):
        dates = [f"2026-06-{day:02d}" for day in range(1, 21)]
        trend = {
            "average_return_5d": 4.0,
            "average_return_20d": 7.5,
            "positive_breadth_5d": 0.75,
            "positive_breadth_20d": 0.60,
            "average_volume_ratio_5d": 1.5,
            "coverage_ratio_5d": 1.0,
            "coverage_ratio_20d": 1.0,
            "high_count_20d": 1,
            "low_count_20d": 0,
            "covered_stock_ids": ["1111"],
        }
        flow_rows = [
            {
                "date": value,
                "stock_id": "1111",
                "total_net": 10.0,
                "traded_shares": 1000.0,
            }
            for value in dates[:18]
        ]

        assessment = build_industry_sentiment_base(
            news_rows=[
                news_row(
                    "產業成長",
                    "2026-07-14T11:00:00+08:00",
                    url="https://example.test/old-local-news",
                )
            ],
            trend=trend,
            flow_rows=flow_rows,
            expected_session_dates=dates,
            freshness={
                "news": {"status": "fresh"},
                "industry_trend": {"status": "fresh"},
                "fund_flow": {"status": "fresh"},
            },
            source_errors=[],
            as_of=AS_OF,
        )

        self.assertIn("freshness", assessment["components"]["news"])
        self.assertEqual(
            assessment["components"]["news"]["freshness"]["status"],
            "no_recent_industry_news_48h",
        )
        self.assertEqual(
            assessment["components"]["fund_flow"]["freshness"]["status"],
            "no_recent_expected_flow_session",
        )
        self.assertEqual(
            assessment["components"]["news"]["freshness"]["source_status"],
            "fresh",
        )
        self.assertEqual(
            assessment["components"]["fund_flow"]["freshness"]["source_status"],
            "fresh",
        )


class SentimentCycleTests(unittest.TestCase):
    @staticmethod
    def assessment(
        score: float,
        *,
        change: float = 0.0,
        breadth_5d: float = 0.60,
        breadth_20d: float = 0.50,
        topic_concentration: float = 0.0,
        volume_ratio_5d: float = 1.0,
        rank: int = 1,
        ranked_count: int = 8,
    ) -> dict[str, object]:
        return {
            "methodology_version": "industry-sentiment-v1",
            "score_5d": score,
            "change": change,
            "rank": rank,
            "ranked_count": ranked_count,
            "components": {
                "price": {
                    "breadth_5d": breadth_5d,
                    "breadth_20d": breadth_20d,
                    "volume_ratio_5d": volume_ratio_5d,
                },
                "news": {"topic_concentration": topic_concentration},
                "fund_flow": {},
            },
        }

    @staticmethod
    def history(
        scores: list[float],
        *,
        rank: int = 1,
        ranked_count: int = 8,
        methodology_version: str = "industry-sentiment-v1",
    ) -> list[dict[str, object]]:
        return [
            {
                "as_of_date": f"2026-07-{index + 1:02d}",
                "methodology_version": methodology_version,
                "score_5d": score,
                "rank": rank,
                "ranked_count": ranked_count,
            }
            for index, score in enumerate(scores)
        ]

    def test_overheating_precedes_expansion(self):
        cycle = classify_sentiment_cycle(
            self.assessment(75.0, topic_concentration=0.60),
            self.history([55.0, 65.0]),
        )

        self.assertEqual(cycle["phase"], "overheating")
        self.assertEqual(cycle["slope_direction"], "positive")
        self.assertTrue(cycle["crowding"])

    def test_recovery_precedes_ignition(self):
        cycle = classify_sentiment_cycle(
            self.assessment(
                0.0,
                change=15.0,
                breadth_5d=0.65,
                breadth_20d=0.40,
            ),
            self.history([-20.0, -10.0]),
        )

        self.assertEqual(cycle["phase"], "recovery")
        self.assertEqual(cycle["breadth_state"], "expanding")

    def test_slope_rules_fall_to_consolidation_with_fewer_than_three_scores(self):
        cycle = classify_sentiment_cycle(
            self.assessment(
                30.0,
                change=15.0,
                breadth_5d=0.70,
                breadth_20d=0.40,
            ),
            self.history([20.0]),
        )

        self.assertIsNone(cycle["recent_slope"])
        self.assertEqual(cycle["slope_direction"], "unavailable")
        self.assertEqual(cycle["phase"], "consolidation")

    def test_cooling_needs_delta_or_negative_slope_with_contracting_breadth(self):
        prior = self.history([20.0, 10.0])

        neither = classify_sentiment_cycle(
            self.assessment(
                0.0,
                change=-9.0,
                breadth_5d=0.50,
                breadth_20d=0.50,
            ),
            prior,
        )
        delta = classify_sentiment_cycle(
            self.assessment(
                0.0,
                change=-10.0,
                breadth_5d=0.50,
                breadth_20d=0.50,
            ),
            prior,
        )
        contracting = classify_sentiment_cycle(
            self.assessment(
                0.0,
                change=0.0,
                breadth_5d=0.40,
                breadth_20d=0.60,
            ),
            prior,
        )

        self.assertEqual(neither["phase"], "consolidation")
        self.assertEqual(delta["phase"], "cooling")
        self.assertEqual(contracting["phase"], "cooling")

    def test_ols_percentile_deceleration_and_ranking_streak_are_diagnostic(self):
        prior = self.history([20.0, 40.0, 60.0])
        cycle = classify_sentiment_cycle(
            self.assessment(60.0, topic_concentration=0.60),
            prior,
        )

        self.assertAlmostEqual(cycle["recent_slope"], 10.0)
        self.assertAlmostEqual(cycle["prior_slope"], 20.0)
        self.assertTrue(cycle["decelerating"])
        self.assertEqual(cycle["ranking_streak"], 4)
        self.assertIsNone(cycle["trailing_percentile"])

        percentile = classify_sentiment_cycle(
            self.assessment(19.0, rank=1, ranked_count=4),
            self.history(list(map(float, range(19))), rank=1, ranked_count=4),
        )
        self.assertEqual(percentile["trailing_percentile"], 100.0)
        self.assertEqual(percentile["ranking_streak"], 20)

    def test_ranking_streak_stops_at_methodology_change_or_missing_rank(self):
        prior = self.history([10.0, 20.0, 30.0])
        prior[1]["methodology_version"] = "industry-sentiment-v0"
        changed = classify_sentiment_cycle(self.assessment(40.0), prior)

        prior = self.history([10.0, 20.0, 30.0])
        prior[-1]["rank"] = None
        missing = classify_sentiment_cycle(self.assessment(40.0), prior)

        self.assertEqual(changed["ranking_streak"], 2)
        self.assertEqual(missing["ranking_streak"], 1)

    def test_ranking_streak_reset_matrix_for_invalid_or_nonqualifying_rows(self):
        cases = (
            ("invalid ranked_count", {"ranked_count": 0}, None),
            ("missing score", {}, "score_5d"),
            ("invalid score", {"score_5d": "not-a-number"}, None),
            ("non-top-quartile", {"rank": 3, "ranked_count": 8}, None),
        )
        for name, updates, removed_key in cases:
            with self.subTest(name=name):
                prior = self.history([10.0, 20.0, 30.0])
                prior[-1].update(updates)
                if removed_key is not None:
                    prior[-1].pop(removed_key)

                cycle = classify_sentiment_cycle(self.assessment(40.0), prior)

                self.assertEqual(cycle["ranking_streak"], 1)

    def test_ranking_streak_treats_adjacent_supplied_sessions_as_consecutive(self):
        for prior_dates, current_date in (
            (("2026-07-02", "2026-07-03"), "2026-07-06"),
            (("2026-02-12", "2026-02-13"), "2026-02-23"),
        ):
            with self.subTest(prior_dates=prior_dates, current_date=current_date):
                prior = self.history([10.0, 20.0])
                for row, as_of_date in zip(prior, prior_dates, strict=True):
                    row["as_of_date"] = as_of_date
                assessment = self.assessment(30.0)
                assessment["as_of_date"] = current_date

                cycle = classify_sentiment_cycle(assessment, prior)

                self.assertEqual(cycle["ranking_streak"], 3)

    def test_finalize_attaches_shadow_payloads_without_hiding_current_score(self):
        assessment = self.assessment(35.0)
        assessment.update(
            {
                "status": "ready",
                "baseline_20d": 20.0,
                "confidence": "medium",
                "warnings": [],
                "reasons": [],
            }
        )

        finalized = finalize_industry_sentiment(
            assessment,
            prior_history=self.history([20.0, 25.0]),
            rank=2,
            ranked_count=8,
        )

        self.assertEqual(finalized["rank"], 2)
        self.assertEqual(finalized["ranked_count"], 8)
        self.assertEqual(finalized["cycle_phase"], "expansion")
        self.assertEqual(finalized["cycle_diagnostics"]["recent_slope"], 7.5)
        self.assertEqual(finalized["score_5d"], 35.0)
        self.assertEqual(finalized["forecast"]["status"], "insufficient_history")
        self.assertEqual(
            finalized["turning_risk"]["status"], "insufficient_history"
        )
        self.assertIsNone(
            finalized["turning_risk"]["calibrated_probability"]
        )

    def test_current_forecast_snapshot_uses_the_stable_history_shape(self):
        assessment = self.assessment(35.0)
        assessment["category"] = "Semiconductor"

        snapshot = _current_sentiment_snapshot(assessment)

        self.assertEqual(set(snapshot), set(SENTIMENT_HISTORY_COLUMNS))
        self.assertEqual(snapshot["category"], "Semiconductor")

    def test_finalize_appends_current_stable_snapshot_to_prior_history(self):
        prior_scores = [
            *[-30.0 + 0.5 * index for index in range(54)],
            30.0,
            45.0,
            60.0,
            75.0,
            76.0,
        ]
        prior = self.history(prior_scores, rank=1, ranked_count=8)
        for row in prior:
            row["baseline_20d"] = row["score_5d"]
        assessment = self.assessment(
            77.0,
            breadth_5d=0.50,
            breadth_20d=0.80,
            topic_concentration=0.65,
            volume_ratio_5d=2.0,
        )
        assessment.update(
            {
                "as_of_date": "2026-09-01",
                "status": "ready",
                "baseline_20d": 77.0,
                "confidence": "high",
                "warnings": [],
                "reasons": [],
            }
        )
        assessment["components"]["price"]["return_5d"] = 1.0
        assessment["components"]["news"].update(
            {
                "score_5d": 65.0,
                "positive_topic_concentration": 0.65,
                "negative_topic_concentration": 0.10,
            }
        )
        assessment["components"]["fund_flow"].update(
            {"score_5d": 0.0, "score_20d": 50.0}
        )

        finalized = finalize_industry_sentiment(
            assessment,
            prior_history=prior,
            rank=1,
            ranked_count=8,
        )

        self.assertEqual(len(prior), 59)
        self.assertEqual(finalized["forecast"]["history_days"], 60)
        self.assertEqual(finalized["forecast"]["status"], "experimental")
        self.assertEqual(finalized["turning_risk"]["history_days"], 60)
        self.assertEqual(finalized["turning_risk"]["status"], "experimental")
        self.assertEqual(finalized["turning_risk"]["direction"], "peak")
        self.assertIsNone(
            finalized["turning_risk"]["calibrated_probability"]
        )


if __name__ == "__main__":
    unittest.main()
