"""Static asset presence + progress UI markers (no browser)."""

from __future__ import annotations

import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"


class TestStaticProgressUI(unittest.TestCase):
    def test_css_has_progress_and_skeleton(self):
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        for needle in (
            ".sim-progress",
            ".sim-progress-bar",
            ".skeleton",
            "prefers-reduced-motion",
            ".fork-error",
        ):
            self.assertIn(needle, css, f"missing {needle}")

    def test_js_has_progress_helpers(self):
        js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
        for needle in (
            "renderSimProgress",
            "forkStages",
            "renderSkeletonStudio",
            "renderForkError",
            "aria-busy",
            'role="progressbar"',
            "queueVideoRender",
            "/api/video/jobs",
        ):
            self.assertIn(needle, js, f"missing {needle}")

    def test_index_fork_region_live(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="fork-result"', html)
        self.assertIn("aria-live", html)
        self.assertIn('role="status"', html)


if __name__ == "__main__":
    unittest.main()
