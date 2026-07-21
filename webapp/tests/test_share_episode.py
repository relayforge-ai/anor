"""Watch-page share helpers (static contract; no browser)."""

from __future__ import annotations

import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")


class TestShareEpisode(unittest.TestCase):
    def test_html_has_share_button(self):
        self.assertIn('id="watch-share"', HTML)
        self.assertIn("Share episode", HTML)
        self.assertIn("<kbd>S</kbd> share", HTML)
        # Guardrail language: share page ≠ auto-publish social
        self.assertRegex(HTML, r"[Hh]uman.?gate")
        # Host deliverable when media is available
        self.assertIn('id="watch-open-mp4"', HTML)
        self.assertIn("Open MP4", HTML)

    def test_js_paints_open_mp4_when_available(self):
        self.assertIn("function paintWatchOpenMp4", JS)
        self.assertIn("paintWatchOpenMp4(video)", JS)
        self.assertIn("/media/videos/", JS)
        self.assertIn('watch-open-mp4', JS)
        self.assertIn("download", JS)

    def test_js_share_payload_and_fallback(self):
        self.assertIn("function episodeSharePayload", JS)
        self.assertIn("function shareEpisode", JS)
        self.assertIn("navigator.share", JS)
        self.assertIn("Episode link copied", JS)
        self.assertIn("#/watch/", JS)
        # Speculation labels preserved in share text
        self.assertIn("Documented baseline", JS)
        self.assertIn("Labeled speculation", JS)

    def test_library_cards_have_share_control(self):
        """Home/library grids share public deep links without auto-publish."""
        self.assertIn("video-card-share", JS)
        self.assertIn("data-share-video", JS)
        self.assertIn("video-card-actions", JS)
        self.assertIn("shareEpisode(id)", JS)
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".video-card-share", css)
        self.assertIn(".video-card-actions", css)

    def test_route_share_meta_updates_canonical_and_og_url(self):
        """SPA routes refresh og:url + canonical for freemium discovery/share."""
        self.assertIn("function publicShareUrl", JS)
        self.assertIn("function routeHashPath", JS)
        self.assertIn("function syncShareMeta", JS)
        self.assertIn('meta[property="og:url"]', JS)
        self.assertIn('link[rel="canonical"]', JS)
        self.assertIn('property="og:url"', HTML)
        self.assertIn('rel="canonical"', HTML)

    def test_share_does_not_auto_publish(self):
        # Share must not invoke Postiz or draft publish paths
        self.assertNotIn("postiz", JS.lower())
        self.assertNotIn("auto-publish", JS.lower())


if __name__ == "__main__":
    unittest.main()
