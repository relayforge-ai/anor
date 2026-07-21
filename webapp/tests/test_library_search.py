"""Library filter + search helper contracts (no browser)."""

from __future__ import annotations

import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
JS = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "css" / "app.css").read_text(encoding="utf-8")


class TestLibrarySearchSurface(unittest.TestCase):
    def test_html_has_search_input(self):
        self.assertIn('id="library-search"', HTML)
        self.assertIn('type="search"', HTML)
        self.assertIn("library-toolbar", HTML)
        self.assertIn('id="library-era-jumps"', HTML)
        self.assertIn("Jump to era in library", HTML)

    def test_js_exports_filter_with_query(self):
        self.assertIn("function filterLibraryVideos", JS)
        self.assertIn("normalizeLibraryQuery", JS)
        self.assertIn("bindLibrarySearch", JS)
        self.assertIn("libraryQuery", JS)
        # Multi-token AND match
        self.assertIn("tokens.every", JS)
        # Esc clears search
        self.assertIn('e.key === "Escape"', JS)
        # Freemium access chips (unlocked / preview-only / in progress)
        self.assertIn('f === "unlocked"', JS)
        self.assertIn('f === "preview"', JS)
        self.assertIn('f === "in_progress"', JS)
        self.assertIn("videoAccess", JS)
        self.assertIn("claimable_full", JS)
        self.assertIn("getWatchPosition", JS)
        # Museum chronological order (era → pack → documented → on-host first)
        self.assertIn("function videosChronological", JS)
        self.assertIn("function eraSortKey", JS)
        self.assertIn("videosChronological(", JS)
        self.assertIn("chronological", JS)
        self.assertIn("a.available === false", JS)
        self.assertIn("on-host first within era", JS)
        self.assertIn("video-card-on-host", JS)
        self.assertIn("on host", JS)
        # Era section heads + jump chips in chronological library
        self.assertIn("function libraryGridHtml", JS)
        self.assertIn("library-era-head", JS)
        self.assertIn("groupByEra", JS)
        self.assertIn("paintLibraryEraJumps", JS)
        self.assertIn("eraSectionId", JS)
        self.assertIn("library-era-jump", JS)
        self.assertIn("data-era-jump", JS)
        # Daily rotating freemium hero (prefers on-host when inventory is mixed)
        self.assertIn("function pickFeaturedOfDay", JS)
        self.assertIn("Featured today", JS)
        self.assertIn("v.available !== false", JS)
        self.assertIn("onHost.length", JS)
        # First-visit Library defaults to "On this host" on mixed inventories
        self.assertIn("function applySmartLibraryDefault", JS)
        self.assertIn("applySmartLibraryDefault()", JS)
        self.assertIn('state.libraryFilter = "available"', JS)
        self.assertIn("anyPlayable && anyMissing", JS)

    def test_html_has_freemium_access_filters(self):
        self.assertIn('data-lib-filter="unlocked"', HTML)
        self.assertIn('data-lib-filter="preview"', HTML)
        self.assertIn('data-lib-filter="in_progress"', HTML)
        self.assertIn("Preview only", HTML)
        self.assertIn("Unlocked", HTML)
        self.assertIn("In progress", HTML)
        self.assertIn("Filter episodes by access and speculation", HTML)

    def test_slash_focuses_library_search(self):
        self.assertIn('e.key === "/"', JS)
        self.assertIn('state.route === "library"', JS)

    def test_css_styles_search(self):
        self.assertIn(".library-search", CSS)
        self.assertIn(".library-toolbar", CSS)
        self.assertIn(".video-card-tags", CSS)
        self.assertIn(".video-card-actions", CSS)
        self.assertIn(".video-card-share", CSS)
        self.assertIn(".library-era-head", CSS)
        self.assertIn(".library-era-title", CSS)
        self.assertIn(".library-era-jumps", CSS)
        self.assertIn(".library-era-jump", CSS)
        self.assertIn(".library-era-head-flash", CSS)

    def test_video_tags_click_to_search(self):
        self.assertIn("videoCardTagsHtml", JS)
        self.assertIn("data-lib-tag", JS)

    def test_measured_runtime_prefers_host_metrics(self):
        """Library/watch use duration_s/bytes from catalog when media is on host."""
        self.assertIn("function videoRuntimeLabel", JS)
        self.assertIn("function formatBytes", JS)
        self.assertIn("v.duration_s", JS)
        self.assertIn("v.bytes", JS)
        self.assertIn("videoRuntimeLabel(v)", JS)
        self.assertIn("videoRuntimeLabel(video)", JS)
        # Falls back to authored estimate when no measured duration
        self.assertIn("runtime_label", JS)

    def test_unavailable_card_deep_links_studio_cut(self):
        """Missing media cards offer Queue in Studio with scenario+choice."""
        self.assertIn("function openStudioForCut", JS)
        self.assertIn("video-card-queue-studio", JS)
        self.assertIn("data-studio-scenario", JS)
        self.assertIn("data-studio-choice", JS)
        self.assertIn("Queue in Studio", JS)
        self.assertIn("studio/", JS)
        # One-shot intent pulses Queue video after Studio paint
        self.assertIn("queueIntent", JS)
        self.assertIn("applyQueueVideoIntent", JS)
        self.assertIn("fh:intentQueueVideo", JS)
        self.assertIn("applyLibraryTagSearch", JS)
        self.assertIn("fh:libraryPrefs", JS)
        self.assertIn("saveLibraryPrefs", JS)
        # Search haystack includes tags
        self.assertIn("v.tags", JS)


if __name__ == "__main__":
    unittest.main()
