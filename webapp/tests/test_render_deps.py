"""Render dependency preflight tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from webapp.jobs import check_render_dependencies, QUEUE  # noqa: E402


class TestRenderDeps(unittest.TestCase):
    def test_ffmpeg_present_on_this_host(self):
        ok, msg = check_render_dependencies()
        # CI and Io both install ffmpeg for video tests
        self.assertTrue(ok, msg)

    def test_stats_include_ffmpeg_flag(self):
        stats = QUEUE.stats()
        self.assertIn("ffmpeg_ok", stats)
        self.assertIsInstance(stats["ffmpeg_ok"], bool)

    def test_missing_ffmpeg_detected(self):
        with patch("webapp.jobs.shutil.which", return_value=None):
            ok, msg = check_render_dependencies()
        self.assertFalse(ok)
        self.assertIn("ffmpeg", msg.lower())


if __name__ == "__main__":
    unittest.main()
