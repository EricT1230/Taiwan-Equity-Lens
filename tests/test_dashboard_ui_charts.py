import re
import unittest

from taiwan_stock_analysis.dashboard_ui.charts import sparkline, signed_hbar


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

    def test_endpoint_inside_viewbox(self):
        out = sparkline([1.0, 2.0, 3.0, 4.0])
        match = re.search(r'cx="([\d.]+)"', out)
        self.assertIsNotNone(match)
        cx = float(match.group(1))
        self.assertLessEqual(cx, 316, f"Endpoint circle cx={cx} exceeds width - pad (320 - 4)")  # width - pad


class SignedHbarTests(unittest.TestCase):
    def test_positive_uses_up_class(self):
        out = signed_hbar(5900, 5900)
        self.assertIn("chart-hbar-fill up", out)
        self.assertIn("width:100%", out)

    def test_negative_uses_down_class(self):
        out = signed_hbar(-800, 5900)
        self.assertIn("chart-hbar-fill down", out)

    def test_zero_and_none_and_zero_maxabs_render_empty_track(self):
        for out in (signed_hbar(0, 5900), signed_hbar(None, 5900), signed_hbar(100, 0)):
            self.assertIn("width:0%", out)

    def test_caps_at_100_percent(self):
        self.assertIn("width:100%", signed_hbar(99999, 100))
