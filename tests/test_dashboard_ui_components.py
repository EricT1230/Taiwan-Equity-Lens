import unittest

from taiwan_stock_analysis.dashboard_ui.components import badge, card, copy_button, esc, pill


class ComponentsTests(unittest.TestCase):
    def test_esc_escapes_and_stringifies(self):
        self.assertEqual(esc("<a>"), "&lt;a&gt;")
        self.assertEqual(esc(11), "11")

    def test_pill_tone_class_and_escaped_text(self):
        self.assertIn("ui-pill-blocked", pill("阻塞", tone="blocked"))
        self.assertIn("需注意", pill("需注意", tone="warn"))
        self.assertIn("&lt;x&gt;", pill("<x>"))

    def test_pill_invalid_tone_falls_back_to_info(self):
        self.assertIn("ui-pill-info", pill("x", tone="nope"))

    def test_badge_tone_class(self):
        self.assertIn("ui-badge-warn", badge("警示", tone="warn"))

    def test_card_wraps_title_and_body(self):
        out = card("研究池", "<p>body</p>")
        self.assertIn("<h4>研究池</h4>", out)
        self.assertIn("<p>body</p>", out)
        self.assertIn("ui-card", out)

    def test_card_wide_flag(self):
        self.assertIn("ui-card-wide", card("t", "b", wide=True))

    def test_copy_button_puts_command_in_data_attr_escaped(self):
        out = copy_button("複製", 'python -m x "2330"')
        self.assertIn('data-copy=', out)
        self.assertIn("&quot;2330&quot;", out)
        self.assertIn("複製", out)
