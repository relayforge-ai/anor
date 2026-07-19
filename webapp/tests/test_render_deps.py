"""Render dependency preflight tests (ffmpeg + free disk)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from webapp.jobs import (  # noqa: E402
    check_disk_space,
    check_ffmpeg,
    check_render_dependencies,
    clear_ffmpeg_cache,
    QUEUE,
)


class TestRenderDeps(unittest.TestCase):
    def setUp(self):
        clear_ffmpeg_cache()

    def test_ffmpeg_present_on_this_host(self):
        ok, msg = check_ffmpeg(force=True)
        self.assertTrue(ok, msg)

    def test_disk_has_space_on_this_host(self):
        # Default threshold 512MB — CI runners and workstations should pass
        ok, msg, free_mb = check_disk_space()
        self.assertTrue(ok, msg)
        self.assertGreaterEqual(free_mb, 0)

    def test_stats_include_ffmpeg_and_disk(self):
        stats = QUEUE.stats()
        self.assertIn("ffmpeg_ok", stats)
        self.assertIsInstance(stats["ffmpeg_ok"], bool)
        self.assertIn("disk_ok", stats)
        self.assertIn("disk_free_mb", stats)
        self.assertIn("min_free_disk_mb", stats)
        self.assertIsInstance(stats["disk_ok"], bool)

    def test_missing_ffmpeg_detected(self):
        clear_ffmpeg_cache()
        with patch("webapp.jobs.shutil.which", return_value=None):
            ok, msg = check_render_dependencies(force=True)
        self.assertFalse(ok)
        self.assertIn("ffmpeg", msg.lower())

    def test_ffmpeg_probe_is_cached(self):
        clear_ffmpeg_cache()
        with patch("webapp.jobs.shutil.which", return_value="/usr/bin/ffmpeg") as which:
            with patch("webapp.jobs.subprocess.run") as run:
                run.return_value = MagicMock(returncode=0)
                ok1, _ = check_ffmpeg(force=True)
                ok2, _ = check_ffmpeg(force=False)
                ok3, _ = check_ffmpeg(force=False)
        self.assertTrue(ok1 and ok2 and ok3)
        # Only the forced probe should run ffmpeg -version once
        self.assertEqual(run.call_count, 1)
        self.assertEqual(which.call_count, 1)
        # force=True runs again
        clear_ffmpeg_cache()
        with patch("webapp.jobs.shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("webapp.jobs.subprocess.run") as run2:
                run2.return_value = MagicMock(returncode=0)
                check_ffmpeg(force=True)
                check_ffmpeg(force=True)
        self.assertEqual(run2.call_count, 2)

    def test_low_disk_detected(self):
        usage = MagicMock()
        usage.free = 10 * 1024 * 1024  # 10 MB free
        usage.total = 100 * 1024 * 1024
        usage.used = 90 * 1024 * 1024
        with patch("webapp.jobs.shutil.disk_usage", return_value=usage):
            ok, msg, free_mb = check_disk_space(min_free_mb=512)
        self.assertFalse(ok)
        self.assertEqual(free_mb, 10)
        self.assertIn("insufficient disk", msg.lower())
        # Combined preflight fails too (ffmpeg may pass)
        with patch("webapp.jobs.shutil.disk_usage", return_value=usage):
            with patch("webapp.jobs.check_ffmpeg", return_value=(True, "ok")):
                ok2, msg2 = check_render_dependencies()
        self.assertFalse(ok2)
        self.assertIn("disk", msg2.lower())

    def test_disk_check_disabled_with_zero(self):
        prev = os.environ.get("ANOR_MIN_FREE_DISK_MB")
        try:
            os.environ["ANOR_MIN_FREE_DISK_MB"] = "0"
            ok, msg, free_mb = check_disk_space()
            self.assertTrue(ok)
            self.assertEqual(free_mb, -1)
            self.assertIn("disabled", msg.lower())
        finally:
            if prev is None:
                os.environ.pop("ANOR_MIN_FREE_DISK_MB", None)
            else:
                os.environ["ANOR_MIN_FREE_DISK_MB"] = prev


if __name__ == "__main__":
    unittest.main()
