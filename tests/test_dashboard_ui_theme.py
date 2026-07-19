import unittest

from taiwan_stock_analysis.dashboard_ui.theme import TOKENS, base_css


class ThemeTests(unittest.TestCase):
    def test_tokens_have_required_keys(self):
        for key in ("bg", "panel", "accent", "up", "down", "blocked", "warn", "ok", "border"):
            self.assertIn(key, TOKENS)
        self.assertEqual(TOKENS["bg"], "#050810")
        self.assertEqual(TOKENS["accent"], "#2ee0f7")

    def test_base_css_embeds_token_values_and_core_selectors(self):
        css = base_css()
        self.assertIn("#050810", css)          # bg
        self.assertIn(".chart-hbar-fill.up", css)
        self.assertIn(".chart-hbar-fill.down", css)
        self.assertIn(".ui-pill", css)
        self.assertIn(".ui-tab", css)
        self.assertIn("tabular-nums", css)

    def test_base_css_is_deterministic(self):
        self.assertEqual(base_css(), base_css())
