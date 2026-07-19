import unittest

from taiwan_stock_analysis.dashboard_ui.charts import sparkline


class SparklineTests(unittest.TestCase):
    def test_renders_svg_line_and_endpoint_for_multiple_points(self):
        out = sparkline([30.6, 30.1, 29.4, 29.1])
        self.assertIn("<svg", out)
        self.assertIn("#2ee0f7", out)          # accent stroke
        self.assertIn("<circle", out)          # end point
        self.assertIn('role="img"', out)

    def test_placeholder_when_fewer_than_two_points(self):
        self.assertNotIn("<svg", sparkline([29.1]))
        self.assertIn("歷史資料不足", sparkline([29.1]))
        self.assertIn("歷史資料不足", sparkline([]))

    def test_ignores_non_finite_values(self):
        out = sparkline([1.0, float("nan"), 2.0, float("inf")])
        self.assertIn("<svg", out)             # 2 finite points remain

    def test_deterministic(self):
        self.assertEqual(sparkline([1.0, 2.0, 3.0]), sparkline([1.0, 2.0, 3.0]))
