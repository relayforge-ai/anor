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

    def test_adjacent_chronological_nav(self):
        """Prev/next binge path follows museum chronological order."""
        self.assertIn("function adjacentEpisodes", JS)
        self.assertIn("function goAdjacentEpisode", JS)
        self.assertIn("function paintWatchAdjacent", JS)
        self.assertIn("function handleWatchEpisodeEnded", JS)
        self.assertIn("fh:autoNextEpisode", JS)
        self.assertIn("videosChronological", JS)
        # Partial host inventories: binge skips unavailable media
        self.assertIn("preferAvailable", JS)
        self.assertIn("cand.available === false", JS)
        self.assertIn("Skipped missing media", JS)
        self.assertIn("on-host binge", JS)
        self.assertIn('id="watch-adjacent"', HTML)
        self.assertIn('id="watch-prev"', HTML)
        self.assertIn('id="watch-next"', HTML)
        self.assertIn('id="watch-auto-next"', HTML)
        self.assertIn(".watch-adjacent", CSS)
        self.assertIn(".watch-auto-next", CSS)


if __name__ == "__main__":
    unittest.main()
