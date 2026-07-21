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
            ".sim-progress-pct",
            ".skeleton",
            "prefers-reduced-motion",
            ".fork-error",
            ".studio-dock",
            ".studio-dock-status",
            "scroll-padding-top",
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
            "cache_hit",
            "Using existing render",
            "force: force",
            "btn-force-rerender",
            "bindForceRerenderButton",
            "Force re-render",
            "paintStudioMediaStrip",
            "findCatalogVideo",
            "studio-media-strip",
            "MP4 on this host",
            "setPlayerLoading",
            "pollMs",
            "libraryEmptyHtml",
            "filterLibraryVideos",
            "library-search",
            "bindLibrarySearch",
            "video-tag",
            "applyLibraryTagSearch",
            "fh:libraryPrefs",
            "video-card-unavailable",
            "fh:activeVideoJob",
            "tryResumeVideoJob",
            "jobProgressLabel",
            "jobs_ahead",
            "eta_s",
            "~${formatDuration(st.eta_s)} left",
            "updateStudioDockProgress",
            "dock-status",
            "dock-cancel",
            "sim-progress-pct",
            "videoStageIndex",
            "studio-dock",
            "syncStudioDock",
            "dock-fork",
            "Ken Burns clips",
            "pollVideoJob",
            'retryAction: "video"',
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
            "publicShareUrl",
            "routeHashPath",
            'meta[property="og:title"]',
            'meta[property="og:url"]',
            'link[rel="canonical"]',
            "twitter:title",
            "shareEpisode",
            "episodeSharePayload",
            "navigator.share",
            "watch-share",
            "relatedEpisodes",
            "paintWatchRelated",
            "watch-related",
            "paintHomeContinue",
            "home-continue",
            "home-continue-grid",
            "recordWatch",
            "recentWatches",
            "saveWatchPosition",
            "getWatchPosition",
            "persistWatchPos",
            "resumePillHtml",
            "video-card-resume",
            "video-card-on-host",
            "on-host first within era",
            "PLAYBACK_RATE_KEY",
            "fh:playbackRate",
            "applyPlaybackRate",
            "bindPlayerSpeedControls",
            "playbackRate",
            "bindWatchKeyboardShortcuts",
            "seekWatchPlayer",
            "toggleWatchPlayback",
            "toggleWatchMute",
            "toggleWatchFullscreen",
            "PLAYBACK_MUTE_KEY",
            "fh:playbackMuted",
            "previewCeiling",
            'key === "j"',
            'key === "ArrowLeft"',
            'key === "m"',
            'key === "f"',
            "adjacentEpisodes",
            "goAdjacentEpisode",
            "paintWatchAdjacent",
            "handleWatchEpisodeEnded",
            "AUTO_NEXT_KEY",
            "fh:autoNextEpisode",
            "watch-auto-next",
            "watch-end-next",
            "watch-adjacent",
            'key === "["',
            'key === "]"',
            "Resume ${pct}%",
            "Resumed where you left off",
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
            "videosChronological",
            "pickFeaturedOfDay",
            "Featured today",
            "eraSortKey",
            "data-lib-filter",
            'f === "in_progress"',
            "most recent first",
            "saveLastStudioScenario",
            "loadLastStudioScenario",
            "resolveStudioScenarioId",
            "fh:lastStudioScenario",
            "saveLastStudioChoice",
            "loadLastStudioChoice",
            "fh:lastStudioChoices",
            "paintHomeStudioCta",
            "Resume Studio ·",
            "hero-studio",
            "result.cache",
            "Cost ladder:",
            "cache assists",
            "Deliverable:",
            "duration_s",
            "result.bytes",
            "function videoRuntimeLabel",
            "function formatBytes",
            "videoRuntimeLabel(v)",
            "videoRuntimeLabel(video)",
            "function compareBranches",
            "Authored pack text only",
            "Branch compare",
            "historical baseline",
            "compare-grid",
            "renderStudioSources",
            "studio-sources-body",
            "no MANDOS master sources",
            "Public sources",
            "bindStudioKeyboardShortcuts",
            "isEditableTarget",
            "e.ctrlKey || e.metaKey",
            'e.key !== "Enter"',
            "studioKbd",
            "runFork({ useLlm: false })",
            "runFork({ useLlm: true })",
        ):
            self.assertIn(needle, js, f"missing {needle}")
        freemium = (STATIC / "js" / "freemium.js").read_text(encoding="utf-8")
        for needle in (
            "newRequestId",
            "X-Request-ID",
            "apiHeaders",
            "recordWatch",
            "recentWatches",
            "clearWatchHistory",
            "forked_history_watch_history_v1",
            "saveWatchPosition",
            "getWatchPosition",
            "clearWatchPosition",
            "forked_history_watch_pos_v1",
        ):
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
        self.assertIn(".studio-kbd-hint", css)
        self.assertIn("studio-kbd-hint kbd", css)
        self.assertIn(".home-continue", css)
        self.assertIn(".video-card-resume", css)
        self.assertIn(".video-card-has-resume", css)
        self.assertIn(".player-speed", css)
        self.assertIn(".player-speed-btn", css)
        self.assertIn(".player-column", css)
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="home-continue"', html)
        self.assertIn('id="home-continue-grid"', html)
        self.assertIn("Continue watching", html)
        self.assertIn('id="player-speed"', html)
        self.assertIn('data-rate="1.25"', html)
        self.assertIn("Playback speed", html)
        self.assertIn('id="player-kbd-hint"', html)
        self.assertIn("−10s", html)
        self.assertIn("mute", html)
        self.assertIn("full", html)
        self.assertIn('id="watch-adjacent"', html)
        self.assertIn('id="watch-prev"', html)
        self.assertIn('id="watch-next"', html)
        self.assertIn('id="watch-auto-next"', html)
        self.assertIn("Auto-next", html)
        self.assertIn(".player-kbd-hint", css)
        self.assertIn(".watch-adjacent", css)
        self.assertIn(".watch-auto-next", css)

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
        self.assertIn("studio-kbd-hint", html)
        self.assertIn("aria-keyshortcuts", html)
        self.assertIn("<kbd>", html)

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
            'property="og:url"',
            'name="twitter:card"',
            'name="twitter:title"',
            "application/ld+json",
            "WebApplication",
            "Labeled speculation",
            'rel="icon"',
            'rel="canonical"',
            "/static/favicon.svg",
            'rel="sitemap"',
            "/sitemap.xml",
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
