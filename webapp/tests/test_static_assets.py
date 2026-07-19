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
            "apiHeaders",
            "FHFreemium.apiHeaders",
            "forkInFlight",
            "A fork is already in progress",
            "fh:cache:scenario:",
            "loadScenarioDetail",
            "onended",
            "pulse-cta",
            "watch-end-note",
            "Episode complete",
            "waitWhileDocumentHidden",
            "visibilitychange",
            "document.hidden",
            "hiddenPollMs",
            "syncShareMeta",
            "setMetaContent",
            'meta[property="og:title"]',
            "twitter:title",
            "formatForkMarkdown",
            "copyForkNarrative",
            "copyTextToClipboard",
            "bindForkCopyButtons",
            "btn-copy",
            "btn-copy-inline",
            "labeled speculation",
            "Documented baseline",
            "formatForkMarkdown",
            "parseRateLimitRemaining",
            "noteRateRemaining",
            "X-RateLimit-Remaining",
            "libraryFilter",
            "filterLibraryVideos",
            "bindLibraryFilters",
            "scenariosChronological",
            "eraSortKey",
            "data-lib-filter",
            "function compareBranches",
            "Authored pack text only",
            "Branch compare",
            "historical baseline",
            "compare-grid",
            "renderStudioSources",
            "studio-sources-body",
            "no MANDOS master sources",
            "Public sources",
        ):
            self.assertIn(needle, js, f"missing {needle}")
        freemium = (STATIC / "js" / "freemium.js").read_text(encoding="utf-8")
        for needle in ("newRequestId", "X-Request-ID", "apiHeaders"):
            self.assertIn(needle, freemium, f"missing {needle} in freemium.js")
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".fork-error.is-rate-limit", css)
        self.assertIn(".rate-wait", css)
        self.assertIn("body.modal-open", css)
        self.assertIn(".boot-error", css)
        self.assertIn(".pulse-cta", css)
        self.assertIn("pulseCta", css)
        self.assertIn(".library-filters", css)
        self.assertIn(".library-filter.active", css)

    def test_index_fork_region_live(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="fork-result"', html)
        self.assertIn("aria-live", html)
        self.assertIn('role="status"', html)
        self.assertIn('id="btn-copy"', html)
        self.assertIn("Copy narrative", html)
        self.assertIn('id="btn-export"', html)
        self.assertIn('id="library-filters"', html)
        self.assertIn("data-lib-filter", html)
        self.assertIn("Documented", html)
        self.assertIn("Simulated", html)
        self.assertIn('id="studio-sources"', html)
        self.assertIn("Sources", html)
        self.assertIn('id="studio-sources-body"', html)

    def test_index_noscript_guidance(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("<noscript>", html)
        self.assertIn("JavaScript required", html)
        self.assertIn("scenarios/public/", html)

    def test_index_share_and_seo_metadata(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for needle in (
            'name="description"',
            'name="theme-color"',
            'property="og:title"',
            'property="og:description"',
            'property="og:type"',
            'property="og:site_name"',
            'name="twitter:card"',
            'name="twitter:title"',
            "application/ld+json",
            "WebApplication",
            "Labeled speculation",
            'rel="icon"',
            "/static/favicon.svg",
        ):
            self.assertIn(needle, html, f"missing {needle}")
        # No hardcoded production hosts or secrets in the shell
        self.assertNotIn("sk-", html)
        fav = STATIC / "favicon.svg"
        self.assertTrue(fav.is_file(), "favicon.svg missing")
        self.assertIn("svg", fav.read_text(encoding="utf-8")[:200].lower())

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
