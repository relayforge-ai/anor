"""Unit tests for video job enqueue deduplication and disk cache hits."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ANOR_MOCK_MEDIA"] = "1"
os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "1"
os.environ["ANOR_VIDEO_MAX_QUEUED"] = "8"

from webapp.jobs import VideoJobQueue, find_cached_video, video_artifact_dir  # noqa: E402


class TestJobDedupe(unittest.TestCase):
    def test_second_enqueue_reuses_active(self):
        q = VideoJobQueue()
        # Avoid disk cache short-circuit while testing in-flight dedupe
        with patch("webapp.jobs.find_cached_video", return_value=None):
            j1, d1 = q.enqueue("ELO-003", "historical", use_llm=False)
            self.assertFalse(d1)
            j2, d2 = q.enqueue("ELO-003", "historical", use_llm=False)
            self.assertTrue(d2)
            self.assertEqual(j1.id, j2.id)

    def test_different_choice_is_separate(self):
        q = VideoJobQueue()
        with patch("webapp.jobs.find_cached_video", return_value=None):
            j1, _ = q.enqueue("ELO-003", "historical", use_llm=False)
            j2, d2 = q.enqueue("ELO-003", "march", use_llm=False)
            self.assertFalse(d2)
            self.assertNotEqual(j1.id, j2.id)

    def test_after_cancel_new_job_allowed(self):
        q = VideoJobQueue()
        with patch("webapp.jobs.find_cached_video", return_value=None):
            j1, _ = q.enqueue("ELO-001", "historical", use_llm=False)
            ok, reason, _ = q.cancel(j1.id)
            self.assertTrue(ok)
            # Wait briefly for worker to notice cancel if it started
            deadline = time.time() + 15
            while time.time() < deadline:
                j = q.get(j1.id)
                if j and j.status in ("cancelled", "completed", "failed"):
                    break
                time.sleep(0.1)
            j2, d2 = q.enqueue("ELO-001", "historical", use_llm=False)
            # New job after terminal — not deduped against cancelled
            if j1.status == "cancelled":
                self.assertFalse(d2)
                self.assertNotEqual(j1.id, j2.id)

    def test_cache_hit_returns_completed_without_worker(self):
        """Existing MP4 → immediate completed job; executor never used."""
        out_dir = video_artifact_dir("ELO-TEST", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-TEST-historical.mp4"
        mp4.write_bytes(b"\x00" * 4096)
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))

        q = VideoJobQueue()
        submit_calls = []
        real_submit = q._executor.submit

        def track_submit(*a, **k):
            submit_calls.append((a, k))
            return real_submit(*a, **k)

        with patch.object(q._executor, "submit", side_effect=track_submit):
            job, deduped = q.enqueue("ELO-TEST", "historical", use_llm=False)
        self.assertFalse(deduped)
        self.assertEqual(job.status, "completed")
        self.assertTrue(job.result and job.result.get("cached"))
        self.assertIn("/media/videos/ELO-TEST-historical/", job.result["media_url"])
        self.assertEqual(submit_calls, [], "cache hit must not schedule a worker")

    def test_force_bypasses_cache(self):
        out_dir = video_artifact_dir("ELO-FORCE", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-FORCE-historical.mp4"
        mp4.write_bytes(b"\x00" * 4096)
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))

        q = VideoJobQueue()
        with patch.object(q._executor, "submit") as submit:
            submit.return_value = None
            job, _ = q.enqueue("ELO-FORCE", "historical", use_llm=False, force=True)
        self.assertEqual(job.status, "queued")
        self.assertTrue(submit.called)

    def test_find_cached_ignores_tiny_files(self):
        out_dir = video_artifact_dir("ELO-TINY", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-TINY-historical.mp4"
        mp4.write_bytes(b"x")  # below min
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))
        self.assertIsNone(find_cached_video("ELO-TINY", "historical"))


if __name__ == "__main__":
    unittest.main()
