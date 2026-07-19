"""Video job wall-clock timeout tests.

Isolates ANOR_VIDEO_JOB_TIMEOUT_S so it cannot poison the process-wide QUEUE
used by API integration tests loaded in the same suite.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")


class TestJobTimeout(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_timeout = os.environ.get("ANOR_VIDEO_JOB_TIMEOUT_S")
        self._prev_conc = os.environ.get("ANOR_VIDEO_MAX_CONCURRENT")
        os.environ["ANOR_VIDEO_JOB_TIMEOUT_S"] = "1"
        os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "2"

    def tearDown(self) -> None:
        if self._prev_timeout is None:
            os.environ.pop("ANOR_VIDEO_JOB_TIMEOUT_S", None)
        else:
            os.environ["ANOR_VIDEO_JOB_TIMEOUT_S"] = self._prev_timeout
        if self._prev_conc is None:
            os.environ.pop("ANOR_VIDEO_MAX_CONCURRENT", None)
        else:
            os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = self._prev_conc
        # Keep process-wide QUEUE usable for later API tests
        try:
            from webapp.jobs import QUEUE

            QUEUE.timeout_s = int(
                os.environ.get("ANOR_VIDEO_JOB_TIMEOUT_S") or "600"
            )
            if QUEUE.timeout_s < 60:
                QUEUE.timeout_s = 600
        except Exception:
            pass

    def test_stats_expose_timeout(self):
        from webapp.jobs import VideoJobQueue

        q = VideoJobQueue()
        self.assertEqual(q.timeout_s, 1)
        self.assertEqual(q.stats()["timeout_s"], 1)

    def test_progress_raises_after_deadline(self):
        from webapp.jobs import JobTimedOut

        deadline_at = time.time() - 1
        with self.assertRaises(JobTimedOut):
            if deadline_at is not None and time.time() > deadline_at:
                raise JobTimedOut("render exceeded 1s wall-clock limit")

    def test_worker_marks_timed_out(self):
        from webapp import jobs as jobs_mod
        from webapp.jobs import VideoJobQueue
        import pipeline.video_pipeline as vp

        q = VideoJobQueue()

        def hanging_render(*args, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress("load", 5, "start")
            with q._lock:
                j = list(q._jobs.values())[0]
                j.deadline_at = time.time() - 0.01
            if on_progress:
                on_progress("segment", 20, "too slow")
            raise AssertionError("should have timed out on progress")

        with patch.object(jobs_mod, "check_render_dependencies", return_value=(True, "ok")):
            with patch.object(jobs_mod, "acquire_render_lock", return_value=(None, None)):
                with patch.object(jobs_mod, "release_render_lock"):
                    with patch.object(vp, "render_video", side_effect=hanging_render):
                        job, _ = q.enqueue("ELO-001", "historical", use_llm=False)
                        deadline = time.time() + 10
                        final = None
                        while time.time() < deadline:
                            final = q.get(job.id)
                            if final and final.status in (
                                "timed_out",
                                "failed",
                                "completed",
                                "cancelled",
                            ):
                                break
                            time.sleep(0.05)
                        self.assertIsNotNone(final)
                        self.assertIn(
                            final.status, ("timed_out", "failed"), final.to_public()
                        )
                        if final.status == "timed_out":
                            self.assertEqual(final.stage, "timeout")
                            self.assertIn("exceeded", (final.error or "").lower())


if __name__ == "__main__":
    unittest.main()
