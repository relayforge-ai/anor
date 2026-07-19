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
os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "1"
os.environ["ANOR_VIDEO_MAX_QUEUED"] = "8"


class TestQueuePosition(unittest.TestCase):
    def test_queued_jobs_report_position(self):
        from webapp.jobs import VideoJobQueue

        q = VideoJobQueue()
        # Block the single worker so jobs stay queued
        gate = {"go": False}

        def blocked_render(*args, **kwargs):
            while not gate["go"]:
                time.sleep(0.02)
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress("done", 100, "ok")
            # Minimal fake result shape is not needed — we stop before complete
            raise RuntimeError("stop test early")

        import pipeline.video_pipeline as vp
        from webapp import jobs as jobs_mod

        with patch.object(jobs_mod, "check_render_dependencies", return_value=(True, "ok")):
            with patch.object(vp, "render_video", side_effect=blocked_render):
                j1, _ = q.enqueue("ELO-001", "historical", use_llm=False)
                j2, _ = q.enqueue("ELO-003", "historical", use_llm=False)
                # Wait until first is running and second still queued
                deadline = time.time() + 5
                while time.time() < deadline:
                    a = q.get(j1.id)
                    b = q.get(j2.id)
                    if a and b and a.status == "running" and b.status == "queued":
                        break
                    time.sleep(0.02)

                p1 = q.to_public_enriched(q.get(j1.id))
                p2 = q.to_public_enriched(q.get(j2.id))
                self.assertEqual(p1["queue_position"], 0)
                self.assertEqual(p1["jobs_ahead"], 0)
                self.assertEqual(p2["queue_position"], 1)
                self.assertEqual(p2["jobs_ahead"], 0)

                j3, _ = q.enqueue("ELO-013", "historical", use_llm=False)
                # Brief settle
                time.sleep(0.05)
                p2b = q.to_public_enriched(q.get(j2.id))
                p3 = q.to_public_enriched(q.get(j3.id))
                self.assertEqual(p2b["jobs_ahead"], 0)
                self.assertEqual(p2b["queue_position"], 1)
                self.assertEqual(p3["jobs_ahead"], 1)
                self.assertEqual(p3["queue_position"], 2)

                gate["go"] = True
                # Let workers drain
                deadline = time.time() + 10
                while time.time() < deadline:
                    statuses = {j.id: j.status for j in (q.get(j1.id), q.get(j2.id), q.get(j3.id))}
                    if all(
                        s in ("failed", "completed", "timed_out", "cancelled")
                        for s in statuses.values()
                        if s
                    ):
                        break
                    time.sleep(0.05)

                term = q.to_public_enriched(q.get(j1.id))
                self.assertIsNone(term["queue_position"])
                self.assertIsNone(term["jobs_ahead"])


if __name__ == "__main__":
    unittest.main()
