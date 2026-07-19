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
            "setPlayerLoading",
            "pollMs",
            "libraryEmptyHtml",
            "video-card-unavailable",
            "fh:activeVideoJob",
            "tryResumeVideoJob",
            "jobProgressLabel",
            "jobs_ahead",
            "pollVideoJob",
            "fh:lastFork",
            "saveLastFork",
            "parseRetryAfter",
            "bindRateLimitRetry",
            "is-rate-limit",
            "openPaywall",
            "closePaywall",
            "paywallFocusable",
            "paywallKeyHandler",
            "modal-open",
            "formatDuration",
            "jobTimeSuffix",
            "deadline_at",
            "elapsed",
            "showBootError",
            "btn-boot-retry",
            "boot-failed",
            "Unable to open the ledger",
            "fetchJsonRevalidatable",
            "If-None-Match",
            "fh:cache:catalog",
            "refreshCatalog",
            "focusMainForRoute",
            "routeFocusReady",
            "preventScroll",
            "updateDocumentTitle",
            "document.title",
            "Library —",
            "Membership —",
        ):
            self.assertIn(needle, js, f"missing {needle}")
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".fork-error.is-rate-limit", css)
        self.assertIn(".rate-wait", css)
        self.assertIn("body.modal-open", css)
        self.assertIn(".boot-error", css)

    def test_index_fork_region_live(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="fork-result"', html)
        self.assertIn("aria-live", html)
        self.assertIn('role="status"', html)

    def test_index_a11y_and_mobile_nav(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("skip-link", html)
        self.assertIn('id="main-content"', html)
        self.assertIn('id="nav-toggle"', html)
        self.assertIn('aria-controls="primary-nav"', html)
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".nav-toggle", css)
        self.assertIn(":focus-visible", css)
        self.assertIn(".skip-link", css)
        self.assertIn(".player-loading", css)
        # Must not hide all non-cta nav links permanently on mobile
        self.assertNotIn(".nav-links a:not(.btn) {\n    display: none;", css)
        js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("setNavOpen", js)
        self.assertIn("selectChoice", js)
        self.assertIn("ArrowDown", js)
        html_idx = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="player-loading"', html_idx)

    def test_paywall_dialog_a11y(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="paywall"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn('aria-labelledby="pay-title"', html)
        self.assertIn('aria-describedby="pay-copy"', html)
        self.assertIn("hidden", html)
        js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
        # Focus trap + Escape + restore
        self.assertIn('e.key === "Escape"', js)
        self.assertIn('e.key !== "Tab"', js)
        self.assertIn("paywallPrevFocus", js)
        self.assertIn("document.contains(prev)", js)


if __name__ == "__main__":
    unittest.main()
