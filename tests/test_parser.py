import unittest

from taiwan_stock_analysis.parser import parse_financial_table


GOODINFO_SAMPLE = """
<html><body>
  <table><tr><td>ignore 0</td></tr></table>
  <table><tr><td>ignore 1</td></tr></table>
  <table><tr><td>ignore 2</td></tr></table>
  <table><tr><td>ignore 3</td></tr></table>
  <table><tr><td>ignore 4</td></tr></table>
  <table><tr><td>ignore 5</td></tr></table>
  <table>
    <tr><th>項目</th><th>2024</th><th>%</th><th>2023</th><th>%</th><th>2022</th><th>%</th></tr>
    <tr><td>營業收入合計</td><td>10,000</td><td>100</td><td>8,500</td><td>100</td><td>-</td><td>100</td></tr>
    <tr><td>每股稅後盈餘(元)</td><td>12.34</td><td></td><td>10.5</td><td></td><td>9.25</td><td></td></tr>
  </table>
</body></html>
"""


class ParserTests(unittest.TestCase):
    def test_parse_financial_table_reads_years_and_every_other_value_column(self):
        data, years = parse_financial_table(GOODINFO_SAMPLE)

        self.assertEqual(years, ["2024", "2023", "2022"])
        self.assertEqual(data["營業收入合計"]["2024"], 10000.0)
        self.assertEqual(data["營業收入合計"]["2023"], 8500.0)
        self.assertIsNone(data["營業收入合計"]["2022"])
        self.assertEqual(data["每股稅後盈餘(元)"]["2024"], 12.34)

    def test_parse_financial_table_returns_empty_when_report_table_missing(self):
        data, years = parse_financial_table("<table><tr><td>too small</td></tr></table>")

        self.assertEqual(data, {})
        self.assertEqual(years, [])


if __name__ == "__main__":
    unittest.main()
