import unittest

from taiwan_stock_analysis.fetcher import GoodinfoClient, build_metadata


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, headers, cookies, timeout):
        self.calls.append((url, headers, cookies, timeout))
        return "<html><body>ok</body></html>"


class FetcherTests(unittest.TestCase):
    def test_fetch_report_builds_goodinfo_url_cookie_and_headers(self):
        http = FakeHttpClient()
        client = GoodinfoClient(http_client=http, now=lambda: 0)

        html = client.fetch_report("2330", "IS_YEAR")

        self.assertIn("ok", html)
        url, headers, cookies, timeout = http.calls[0]
        self.assertIn("RPT_CAT=IS_YEAR", url)
        self.assertIn("STOCK_ID=2330", url)
        self.assertIn("REINIT=", url)
        self.assertEqual(headers["Referer"], "https://goodinfo.tw/")
        self.assertIn("Mozilla", headers["User-Agent"])
        self.assertIn("CLIENT_KEY", cookies)
        self.assertEqual(timeout, 15)

    def test_build_metadata_contains_source_and_mops_links(self):
        metadata = build_metadata("2317", ["2024", "2023"])

        self.assertEqual(metadata["source"], "Goodinfo.tw")
        self.assertEqual(metadata["source_mode"], "live")
        self.assertEqual(metadata["source_review"]["status"], "ok")
        self.assertEqual(metadata["years_covered"], ["2024", "2023"])
        self.assertIn("STOCK_ID=2317", metadata["source_urls"]["income_statement"])
        self.assertIn("co_id=2317", metadata["mops_url"])

    def test_build_metadata_records_fixture_source_review(self):
        metadata = build_metadata("2317", ["2024", "2023"], source_mode="fixture")

        self.assertEqual(metadata["source_mode"], "fixture")
        self.assertEqual(metadata["source_review"]["status"], "manual_review")
        self.assertIn("fixture", metadata["source_review"]["reason"])


if __name__ == "__main__":
    unittest.main()
