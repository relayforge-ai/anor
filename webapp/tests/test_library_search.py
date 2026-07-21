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

    def test_js_exports_filter_with_query(self):
        self.assertIn("function filterLibraryVideos", JS)
        self.assertIn("normalizeLibraryQuery", JS)
        self.assertIn("bindLibrarySearch", JS)
        self.assertIn("libraryQuery", JS)
        # Multi-token AND match
        self.assertIn("tokens.every", JS)
        # Esc clears search
        self.assertIn('e.key === "Escape"', JS)

    def test_slash_focuses_library_search(self):
        self.assertIn('e.key === "/"', JS)
        self.assertIn('state.route === "library"', JS)

    def test_css_styles_search(self):
        self.assertIn(".library-search", CSS)
        self.assertIn(".library-toolbar", CSS)


if __name__ == "__main__":
    unittest.main()
