"""Related-episode discovery surface (static contract)."""

from __future__ import annotations

import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "app.css").read_text(encoding="utf-8")


class TestRelatedEpisodes(unittest.TestCase):
    def test_html_has_related_region(self):
        self.assertIn('id="watch-related"', HTML)
        self.assertIn('id="watch-related-grid"', HTML)
        self.assertIn("Related cuts", HTML)

    def test_js_ranks_same_pack_and_tags(self):
        self.assertIn("function relatedEpisodes", JS)
        self.assertIn("function paintWatchRelated", JS)
        self.assertIn("score += 100", JS)  # same scenario weight
        self.assertIn("score += 10", JS)  # tag overlap
        self.assertIn("paintWatchRelated(video)", JS)

    def test_css_hides_when_empty(self):
        self.assertIn(".watch-related[hidden]", CSS)


if __name__ == "__main__":
    unittest.main()
