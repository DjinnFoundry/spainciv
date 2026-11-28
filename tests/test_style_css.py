"""Static checks on web/css/style.css."""

import re
import unittest

from pipeline.core.paths import ROOT

CSS = (ROOT / "web" / "css" / "style.css").read_text()


class QuickRowIconsTest(unittest.TestCase):
    def test_hiding_a_quick_chips_label_never_hides_its_emoji(self):
        # glyph() (ui/icon.js) writes a lens without an SVG icon as span.emoji: a rule that hides a quick chip's text
        # spans must leave it, or the chip is an empty box (the .icons rule once forgot what the @container one said).
        body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", body)
        hiding = [sel.strip() for sels, decl in rules if re.search(r"display:\s*none", decl)
                  for sel in sels.split(",") if re.search(r"\.lens-btn\b.*\bspan\b", sel)]
        self.assertTrue(hiding)  # the check sees the rules it guards
        self.assertEqual([s for s in hiding if ":not(.emoji)" not in s], [])


if __name__ == "__main__":
    unittest.main()
