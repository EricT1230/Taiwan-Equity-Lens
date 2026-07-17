import json
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from taiwan_stock_analysis.dashboard import render_dashboard_html
from taiwan_stock_analysis.doctor import check_demo_readiness
from taiwan_stock_analysis.industry_sentiment import score_news_component
from taiwan_stock_analysis.industry_trends import load_price_history_rows
from taiwan_stock_analysis.market_intelligence import (
    _dedupe_news,
    _event_link,
    _freshness_entry,
    _hours_between,
    build_market_intelligence_report,
    write_market_intelligence_report,
)


AS_OF = datetime(2026, 7, 18, 12, tzinfo=timezone(timedelta(hours=8)))


def _dashboard_with_news(url: str, title: str) -> str:
    return render_dashboard_html(
        {
            "reports": [],
            "comparisons": [],
            "batch_summaries": [],
            "workflow_summaries": [],
            "research_summaries": [],
            "market_intelligence_reports": [
                {
                    "path": "market-intelligence/market_intelligence_report.json",
                    "quality_gate": {"status": "ready", "blockers": []},
                    "freshness": {},
                    "coverage": {},
                    "industries": [
                        {
                            "category": "Safety",
                            "market_trend": {},
                            "fund_flow": {},
                            "latest_news": [{"url": url, "title": title}],
                        }
                    ],
                }
            ],
        }
    )


def _news_row(url: str, title: str, *, minutes: int = 0) -> dict[str, str]:
    return {
        "published_at": (AS_OF - timedelta(minutes=minutes)).isoformat(),
        "title": title,
        "summary": "",
        "url": url,
        "source": "fixture",
    }


class ExternalNewsLinkSecurityTests(unittest.TestCase):
    def test_dashboard_renders_only_strict_external_http_links(self) -> None:
        unsafe_urls = (
            "javascript:alert(1)",
            "data:text/html,boom",
            "https://example.test/%0Aalert(1)",
            "https://user:password@example.test/news",
            "https://[bad-host/news",
        )
        for unsafe_url in unsafe_urls:
            with self.subTest(url=unsafe_url):
                html = _dashboard_with_news(unsafe_url, "Unsafe <news>")

                self.assertNotIn(f'href="{unsafe_url}"', html)
                self.assertIn("Unsafe &lt;news&gt;", html)

        valid_url = "https://example.test/news?item=1"
        html = _dashboard_with_news(valid_url, "Valid news")
        self.assertIn(f'<a href="{valid_url}">Valid news</a>', html)

    def test_standalone_renderer_uses_the_same_strict_url_contract(self) -> None:
        self.assertEqual(
            _event_link({"url": "https://[2001:db8::1]/news", "title": "IPv6"}),
            '<a href="https://[2001:db8::1]/news">IPv6</a>',
        )
        for unsafe_url in (
            "file:///C:/private.txt",
            "https://127.1/alias",
            "https://0x7f.0.0.1/alias",
            "https://example.test/%250aalert(1)",
        ):
            with self.subTest(url=unsafe_url):
                self.assertEqual(
                    _event_link({"url": unsafe_url, "title": "Unsafe"}), "Unsafe"
                )


class CanonicalNewsIdentityTests(unittest.TestCase):
    def test_tracking_variants_deduplicate_by_canonical_url_before_mapping_and_scoring(self) -> None:
        rows = [
            _news_row(
                "HTTPS://Example.TEST:443/story?b=2&utm_source=feed#fragment",
                "First title",
            ),
            _news_row(
                "https://example.test/story?utm_campaign=test&b=2",
                "Different title",
                minutes=1,
            ),
        ]

        self.assertEqual(len(_dedupe_news(rows)), 1)
        component = score_news_component(rows, as_of=AS_OF)
        self.assertEqual(component["coverage"]["articles_5d"], 1)
        self.assertEqual(component["coverage"]["excluded_duplicate"], 1)

    def test_meaningful_query_is_distinct_and_invalid_url_falls_back_to_title(self) -> None:
        meaningful_rows = [
            _news_row("https://example.test/story?edition=morning", "Morning"),
            _news_row("https://example.test/story?edition=evening", "Evening", minutes=1),
        ]
        self.assertEqual(len(_dedupe_news(meaningful_rows)), 2)
        self.assertEqual(
            score_news_component(meaningful_rows, as_of=AS_OF)["coverage"]["articles_5d"],
            2,
        )

        invalid_rows = [
            _news_row("javascript:alert(1)", "Same  headline"),
            _news_row("data:text/plain,nope", "same headline", minutes=1),
        ]
        self.assertEqual(len(_dedupe_news(invalid_rows)), 1)
        self.assertEqual(
            score_news_component(invalid_rows, as_of=AS_OF)["coverage"]["articles_5d"],
            1,
        )

    def test_canonical_deduplication_is_deterministic_under_input_permutations(self) -> None:
        rows = [
            _news_row("https://example.test/story?a=1&utm_medium=email", "One"),
            _news_row("https://EXAMPLE.test:443/story?a=1#top", "Two", minutes=1),
            _news_row("https://example.test/story?a=2", "Three", minutes=2),
        ]
        forward = score_news_component(rows, as_of=AS_OF)
        reverse = score_news_component(list(reversed(rows)), as_of=AS_OF)

        self.assertEqual(forward["coverage"], reverse["coverage"])
        self.assertEqual(forward["score_5d"], reverse["score_5d"])


class TemporalDependencyAndFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _inputs(
        self,
        *,
        trend_as_of: str = "2026-07-18",
        session_dates: list[str] | None = None,
        flow_dates: list[str] | None = None,
    ) -> tuple[Path, Path, list[dict[str, str]], list[dict[str, object]]]:
        sessions = session_dates or ["2026-07-16", "2026-07-17", "2026-07-18"]
        flows = flow_dates or sessions
        research = self.root / "research.csv"
        trend = self.root / "trend.json"
        research.write_text(
            "stock_id,company_name,category,priority,research_state,notes,news_keywords\n"
            "2330,Fixture,Semiconductor,high,watching,,chip\n",
            encoding="utf-8",
        )
        trend.write_text(
            json.dumps(
                {
                    "as_of_date": trend_as_of,
                    "session_dates": sessions,
                    "categories": [
                        {
                            "category": "Semiconductor",
                            "average_return_5d": 2.0,
                            "average_return_20d": 3.0,
                            "positive_breadth_5d": 1.0,
                            "positive_breadth_20d": 1.0,
                            "coverage_ratio_5d": 1.0,
                            "coverage_ratio_20d": 1.0,
                            "average_volume_ratio_5d": 1.1,
                            "covered_stock_ids": ["2330"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        news = [
            _news_row(
                f"https://example.test/story-{index}",
                f"chip story {index}",
                minutes=index,
            )
            for index in range(5)
        ]
        flow_rows = [
            {
                "date": flow_date,
                "stock_id": "2330",
                "total_net": 10.0,
                "traded_shares": 1000.0,
                "source": "official-fixture",
            }
            for flow_date in flows
        ]
        return research, trend, news, flow_rows

    def test_future_dependency_dates_fail_before_report_or_history_artifacts_exist(self) -> None:
        future_cases = (
            ("future trend as_of", {"trend_as_of": "2026-07-19"}, None, None),
            ("future trend session", {"session_dates": ["2026-07-18", "2026-07-19"]}, None, None),
            ("future flow", {}, None, ["2026-07-19"]),
            ("future news", {}, "2026-07-19T10:00:00+08:00", None),
        )
        for label, trend_kwargs, future_news, flow_dates in future_cases:
            with self.subTest(case=label):
                case_root = self.root / label.replace(" ", "-")
                case_root.mkdir()
                original_root = self.root
                self.root = case_root
                try:
                    research, trend, news, flows = self._inputs(
                        flow_dates=flow_dates,
                        **trend_kwargs,
                    )
                finally:
                    self.root = original_root
                if future_news is not None:
                    news[0]["published_at"] = future_news
                output_dir = case_root / "output"

                with self.assertRaisesRegex(ValueError, "future"):
                    write_market_intelligence_report(
                        research,
                        output_dir,
                        news_rows=news,
                        fund_flow_rows=flows,
                        industry_trend_report_path=trend,
                        as_of="2026-07-18T18:00:00+08:00",
                    )

                self.assertFalse((output_dir / "market_intelligence_report.json").exists())
                self.assertFalse((output_dir / "industry_sentiment_history.csv").exists())

    def test_session_set_requires_latest_or_immediately_preceding_price_and_flow_dates(self) -> None:
        research, trend, news, flows = self._inputs(
            trend_as_of="2026-07-16",
            session_dates=["2026-07-16", "2026-07-17", "2026-07-18"],
            flow_dates=["2026-07-17"],
        )

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend,
            as_of="2026-07-18T18:00:00+08:00",
        )

        sentiment = report["industries"][0]["sentiment"]
        self.assertEqual(report["freshness"]["price"]["status"], "stale")
        self.assertIn("latest or immediately preceding", report["freshness"]["price"]["warning"])
        self.assertEqual(sentiment["components"]["price"]["freshness"]["status"], "stale")
        self.assertIsNone(sentiment["components"]["price"]["contribution_5d"])
        self.assertEqual(report["freshness"]["fund_flow"]["status"], "fresh")

    def test_immediately_preceding_session_and_holiday_gap_remain_fresh(self) -> None:
        research, trend, news, flows = self._inputs(
            trend_as_of="2026-07-10",
            session_dates=["2026-07-10", "2026-07-13"],
            flow_dates=["2026-07-10"],
        )
        for index, row in enumerate(news):
            row["published_at"] = f"2026-07-13T{10 - index:02d}:00:00+08:00"

        report = build_market_intelligence_report(
            research,
            news_rows=news,
            fund_flow_rows=flows,
            industry_trend_report_path=trend,
            as_of="2026-07-13T18:00:00+08:00",
        )

        self.assertEqual(report["freshness"]["price"]["status"], "fresh")
        self.assertEqual(report["freshness"]["fund_flow"]["status"], "fresh")
        self.assertIsNotNone(report["industries"][0]["sentiment"]["components"]["price"]["contribution_5d"])

    def test_negative_input_age_is_never_classified_as_fresh(self) -> None:
        future = AS_OF + timedelta(hours=1)
        age = _hours_between(AS_OF, future)

        self.assertLess(age, 0.0)
        self.assertEqual(_freshness_entry(future.isoformat(), age, 48, "hours")["status"], "future")


class FinitePriceHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "prices.csv"

    def test_nonfinite_or_nonpositive_closes_are_rejected_with_row_context(self) -> None:
        for close in ("nan", "inf", "-inf", "0", "-1"):
            with self.subTest(close=close):
                self.path.write_text(
                    f"stock_id,date,close,volume,source\n2330,2026-07-18,{close},,fixture\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, r"row 2.*close"):
                    load_price_history_rows(self.path)

    def test_nonfinite_optional_volumes_are_rejected_but_blanks_remain_missing(self) -> None:
        for volume in ("nan", "inf", "-inf"):
            with self.subTest(volume=volume):
                self.path.write_text(
                    f"stock_id,date,close,volume,source\n2330,2026-07-18,100,{volume},fixture\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, r"row 2.*volume"):
                    load_price_history_rows(self.path)

        self.path.write_text(
            "stock_id,date,close,volume,source\n2330,2026-07-18,100,,fixture\n",
            encoding="utf-8",
        )
        self.assertIsNone(load_price_history_rows(self.path)[0]["volume"])


class DashboardIndustryUniverseTests(unittest.TestCase):
    def test_dashboard_keeps_all_industries_for_client_side_sorting(self) -> None:
        industries = [
            {
                "category": f"Industry {index:02d}",
                "market_trend": {},
                "fund_flow": {},
                "latest_news": [],
                "sentiment": {
                    "status": "ready",
                    "score_5d": 100 - index,
                    "change": 0,
                    "cycle_phase": "consolidation",
                    "confidence": "medium",
                    "forecast": {"status": "insufficient_history"},
                    "turning_risk": {
                        "status": "experimental",
                        "peak_risk": 1000 if index == 13 else index,
                    },
                },
            }
            for index in range(14)
        ]
        html = render_dashboard_html(
            {
                "reports": [],
                "comparisons": [],
                "batch_summaries": [],
                "workflow_summaries": [],
                "research_summaries": [],
                "market_intelligence_reports": [
                    {
                        "path": "market-intelligence/report.json",
                        "quality_gate": {"status": "ready", "blockers": []},
                        "freshness": {},
                        "coverage": {"industries_total": 14},
                        "industries": industries,
                    }
                ],
            }
        )

        self.assertEqual(html.count('data-market-intelligence-industry="Industry '), 14)
        self.assertIn('data-market-intelligence-industry="Industry 13"', html)

        node = shutil.which("node")
        if node is None:
            self.skipTest("Node runtime is not available")
        function_start = html.index("function sortIndustrySentimentCards(source, key)")
        function_end = html.index("function initIndustrySentimentSorting()", function_start)
        function_source = html[function_start:function_end]
        harness = function_source + r"""
const cards = Array.from({ length: 14 }, (_value, index) => ({
  dataset: {
    marketIntelligenceIndustry: 'Industry ' + String(index).padStart(2, '0'),
    industrySentimentPeakRisk: String(index === 13 ? 1000 : index)
  }
}));
const grid = {
  children: cards.slice(),
  querySelectorAll: () => grid.children,
  appendChild: (card) => { grid.children = grid.children.filter((item) => item !== card); grid.children.push(card); }
};
const source = { querySelector: () => grid };
sortIndustrySentimentCards(source, 'peak_risk');
if (grid.children[0].dataset.marketIntelligenceIndustry !== 'Industry 13') {
  throw new Error('13th-plus industry was not available to risk sorting');
}
"""
        result = subprocess.run(
            [node, "-e", harness],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


class DoctorArtifactEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output_dir = Path(self.temporary_directory.name) / "demo"
        self.output_dir.mkdir(parents=True)

    def test_doctor_reports_invalid_dashboard_json_and_html_encoding_without_raising(self) -> None:
        research_json = self.output_dir / "research_summary.json"
        dashboard_html = self.output_dir / "dashboard.html"
        research_json.write_bytes(b"\xff")
        dashboard_html.write_bytes(b"\xff")

        try:
            result = check_demo_readiness(self.output_dir)
        except UnicodeError as exc:
            self.fail(f"doctor leaked artifact decoding error: {exc}")

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                failure.startswith(f"invalid JSON encoding {research_json}:")
                for failure in result.failures
            )
        )
        self.assertTrue(
            any(
                failure.startswith(f"invalid dashboard encoding {dashboard_html}:")
                for failure in result.failures
            )
        )


if __name__ == "__main__":
    unittest.main()
