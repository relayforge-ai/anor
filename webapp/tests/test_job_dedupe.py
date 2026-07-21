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

from webapp.jobs import (  # noqa: E402
    VideoJobQueue,
    find_cached_video,
    read_cached_video_metrics,
    video_artifact_dir,
)


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
        import json

        out_dir = video_artifact_dir("ELO-TEST", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-TEST-historical.mp4"
        mp4.write_bytes(b"\x00" * 4096)
        build = out_dir / "build.json"
        build.write_text(
            json.dumps(
                {
                    "scenario_id": "ELO-TEST",
                    "choice_id": "historical",
                    "out_mp4": mp4.name,
                    "out_mp4_bytes": 4096,
                    "duration_s": 42.5,
                    "cache": {
                        "still_hits": 2,
                        "tts_hits": 1,
                        "clip_hits": 0,
                        "segments": 3,
                    },
                    "segments": [{}, {}, {}],
                }
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))
        self.addCleanup(lambda: build.unlink(missing_ok=True))

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
        # Disk-cache hits carry same deliverable metrics as full renders
        self.assertEqual(job.result.get("bytes"), 4096)
        self.assertEqual(job.result.get("duration_s"), 42.5)
        self.assertEqual(
            job.result.get("cache"),
            {"still_hits": 2, "tts_hits": 1, "clip_hits": 0, "segments": 3},
        )
        self.assertEqual(job.result.get("segments"), 3)

    def test_read_cached_video_metrics_from_build_json(self):
        import json

        out_dir = video_artifact_dir("ELO-METRICS", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-METRICS-historical.mp4"
        mp4.write_bytes(b"\x00" * 8192)
        build = out_dir / "build.json"
        build.write_text(
            json.dumps(
                {
                    "out_mp4_bytes": 9999,
                    "duration_s": 12.345,
                    "cache": {"still_hits": 1, "tts_hits": 0, "clip_hits": 1, "segments": 2},
                }
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))
        self.addCleanup(lambda: build.unlink(missing_ok=True))

        m = read_cached_video_metrics(mp4)
        self.assertEqual(m["bytes"], 9999)  # prefers build.json over st_size
        self.assertEqual(m["duration_s"], 12.35)
        self.assertEqual(m["cache"]["still_hits"], 1)
        self.assertEqual(m["cache"]["clip_hits"], 1)

    def test_read_cached_video_metrics_mp4_only(self):
        """No build.json → still report bytes from the MP4 size."""
        out_dir = video_artifact_dir("ELO-MP4ONLY", "historical")
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "ELO-MP4ONLY-historical.mp4"
        mp4.write_bytes(b"\x00" * 5000)
        build = out_dir / "build.json"
        if build.exists():
            build.unlink()
        self.addCleanup(lambda: mp4.unlink(missing_ok=True))

        m = read_cached_video_metrics(mp4)
        self.assertEqual(m.get("bytes"), 5000)
        self.assertNotIn("duration_s", m)
        self.assertNotIn("cache", m)

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
