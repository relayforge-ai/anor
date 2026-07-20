"""Queue position enrichment for video job public payloads."""

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


def _clear_stale_render_locks() -> None:
    """Drop leftover .render.lock files so suite order cannot poison this test."""
    videos = ROOT / "outputs" / "videos"
    if not videos.is_dir():
        return
    for lock in videos.glob("*/*.render.lock"):
        try:
            lock.unlink()
        except OSError:
            pass
    try:
        from webapp import jobs as jobs_mod

        with jobs_mod._RENDER_PATH_LOCKS_GUARD:
            jobs_mod._RENDER_PATH_LOCKS.clear()
    except Exception:
        pass


class TestQueuePosition(unittest.TestCase):
    def setUp(self):
        # Must set concurrency here — other test modules rewrite these at import
        os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "1"
        os.environ["ANOR_VIDEO_MAX_QUEUED"] = "8"
        _clear_stale_render_locks()

    def tearDown(self):
        _clear_stale_render_locks()

    def test_queued_jobs_report_position(self):
        from webapp.jobs import VideoJobQueue

        q = VideoJobQueue()
        self.assertEqual(q.max_concurrent, 1, "test requires a single worker slot")
        # Block the single worker so later jobs stay queued
        gate = {"go": False}

        def blocked_render(*args, **kwargs):
            while not gate["go"]:
                time.sleep(0.02)
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress("done", 100, "ok")
            raise RuntimeError("stop test early")

        import pipeline.video_pipeline as vp
        from webapp import jobs as jobs_mod

        with patch.object(jobs_mod, "check_render_dependencies", return_value=(True, "ok")):
            with patch.object(jobs_mod, "acquire_render_lock", return_value=(None, None)):
                with patch.object(jobs_mod, "release_render_lock"):
                    # Disable disk cache so both jobs stay in the live queue
                    # (sibling video tests may leave MP4s under outputs/videos/).
                    with patch.object(jobs_mod, "find_cached_video", return_value=None):
                        with patch.object(vp, "render_video", side_effect=blocked_render):
                            try:
                                j1, _ = q.enqueue("ELO-001", "historical", use_llm=False)
                                j2, _ = q.enqueue("ELO-003", "historical", use_llm=False)
                                deadline = time.time() + 5
                                reached = False
                                while time.time() < deadline:
                                    a = q.get(j1.id)
                                    b = q.get(j2.id)
                                    if (
                                        a
                                        and b
                                        and a.status == "running"
                                        and b.status == "queued"
                                    ):
                                        reached = True
                                        break
                                    time.sleep(0.02)
                                self.assertTrue(
                                    reached,
                                    f"timed out waiting for running/queued; "
                                    f"j1={q.get(j1.id) and q.get(j1.id).status} "
                                    f"j2={q.get(j2.id) and q.get(j2.id).status} "
                                    f"max_concurrent={q.max_concurrent}",
                                )

                                p1 = q.to_public_enriched(q.get(j1.id))
                                p2 = q.to_public_enriched(q.get(j2.id))
                                self.assertEqual(p1["queue_position"], 0)
                                self.assertEqual(p1["jobs_ahead"], 0)
                                self.assertEqual(p2["queue_position"], 1)
                                self.assertEqual(p2["jobs_ahead"], 0)
                                # Running job may expose wall-clock remaining as eta_s
                                self.assertIn("eta_s", p1)
                                # Queued next-in-line → ~0 wait estimate
                                self.assertEqual(p2.get("eta_s"), 0)

                                j3, _ = q.enqueue("ELO-013", "historical", use_llm=False)
                                time.sleep(0.05)
                                p2b = q.to_public_enriched(q.get(j2.id))
                                p3 = q.to_public_enriched(q.get(j3.id))
                                self.assertEqual(p2b["jobs_ahead"], 0)
                                self.assertEqual(p2b["queue_position"], 1)
                                self.assertEqual(p3["jobs_ahead"], 1)
                                self.assertEqual(p3["queue_position"], 2)
                                # jobs_ahead=1 → one slot of heuristic ETA
                                eta_per = int(
                                    os.environ.get("ANOR_VIDEO_ETA_PER_JOB_S") or "120"
                                )
                                self.assertEqual(p3.get("eta_s"), eta_per)

                                gate["go"] = True
                                deadline = time.time() + 10
                                while time.time() < deadline:
                                    statuses = {
                                        j.id: j.status
                                        for j in (
                                            q.get(j1.id),
                                            q.get(j2.id),
                                            q.get(j3.id),
                                        )
                                        if j
                                    }
                                    if all(
                                        s
                                        in (
                                            "failed",
                                            "completed",
                                            "timed_out",
                                            "cancelled",
                                        )
                                        for s in statuses.values()
                                    ):
                                        break
                                    time.sleep(0.05)

                                term = q.to_public_enriched(q.get(j1.id))
                                self.assertIsNone(term["queue_position"])
                                self.assertIsNone(term["jobs_ahead"])
                            finally:
                                gate["go"] = True
                                try:
                                    q._executor.shutdown(
                                        wait=True, cancel_futures=True
                                    )
                                except TypeError:
                                    q._executor.shutdown(wait=True)
                                except Exception:
                                    pass


if __name__ == "__main__":
    unittest.main()
