import unittest
from datetime import datetime, timedelta, timezone

from taiwan_stock_analysis.industry_sentiment import (
    NewsSentimentReviewer,
    score_news_component,
)
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


if __name__ == "__main__":
    unittest.main()
