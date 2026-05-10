import unittest
from pathlib import Path

from taiwan_stock_analysis.watchlist import load_watchlist


class WatchlistTests(unittest.TestCase):
    def test_load_watchlist_reads_stock_ids_and_optional_names(self):
        path = Path(".tmp-cli-test/watchlist.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stock_id,company_name\n2330,台積電\n2303,聯電\n", encoding="utf-8")

        rows = load_watchlist(path)

        self.assertEqual(rows[0]["stock_id"], "2330")
        self.assertEqual(rows[0]["company_name"], "台積電")
        self.assertEqual(rows[1]["stock_id"], "2303")

    def test_load_watchlist_rejects_missing_stock_id_column(self):
        path = Path(".tmp-cli-test/bad-watchlist.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("symbol\n2330\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            load_watchlist(path)


if __name__ == "__main__":
    unittest.main()
