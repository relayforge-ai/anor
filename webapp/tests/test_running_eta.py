"""Work-based running ETA heuristic for video job public payloads."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.jobs import VideoJob, VideoJobQueue, estimate_running_eta_s  # noqa: E402


class TestEstimateRunningEta(unittest.TestCase):
    def test_extrapolates_from_progress(self):
        # 50% done after 60s → ~60s remaining
        eta = estimate_running_eta_s(
            started_at=1000.0,
            pct=50.0,
            deadline_at=1000.0 + 600,
            eta_per_job_s=120,
            now=1060.0,
        )
        self.assertEqual(eta, 60)

    def test_caps_at_deadline(self):
        eta = estimate_running_eta_s(
            started_at=1000.0,
            pct=10.0,
            deadline_at=1005.0,  # 5s left
            eta_per_job_s=120,
            now=1000.0,
        )
        # Work-based would be huge (elapsed 0 → early path) but deadline caps
        self.assertLessEqual(eta, 5)

    def test_early_progress_uses_eta_per_fraction(self):
        # pct < 5 → frac of eta_per
        eta = estimate_running_eta_s(
            started_at=1000.0,
            pct=0.0,
            deadline_at=None,
            eta_per_job_s=100,
            now=1001.0,
        )
        self.assertEqual(eta, 100)

    def test_enriched_running_job_includes_work_eta(self):
        q = VideoJobQueue()
        job = VideoJob(
            id="abc123deadbeef00",
            scenario_id="ELO-001",
            choice_id="historical",
            use_llm=False,
            status="running",
            stage="still",
            pct=25.0,
            started_at=1000.0,
            deadline_at=1000.0 + 600,
        )
        q._jobs[job.id] = job
        # Monkey-patch time via estimate by setting started far enough
        # Call estimate with fixed now by temporarily setting started relative
        pub = q.to_public_enriched(job)
        self.assertEqual(pub["queue_position"], 0)
        self.assertIn("eta_s", pub)
        self.assertIsNotNone(pub["eta_s"])
        self.assertGreaterEqual(pub["eta_s"], 0)


if __name__ == "__main__":
    unittest.main()
