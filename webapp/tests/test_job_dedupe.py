"""Unit tests for video job enqueue deduplication."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ANOR_MOCK_MEDIA"] = "1"
os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "1"
os.environ["ANOR_VIDEO_MAX_QUEUED"] = "8"

from webapp.jobs import VideoJobQueue  # noqa: E402


class TestJobDedupe(unittest.TestCase):
    def test_second_enqueue_reuses_active(self):
        q = VideoJobQueue()
        j1, d1 = q.enqueue("ELO-003", "historical", use_llm=False)
        self.assertFalse(d1)
        j2, d2 = q.enqueue("ELO-003", "historical", use_llm=False)
        self.assertTrue(d2)
        self.assertEqual(j1.id, j2.id)

    def test_different_choice_is_separate(self):
        q = VideoJobQueue()
        j1, _ = q.enqueue("ELO-003", "historical", use_llm=False)
        j2, d2 = q.enqueue("ELO-003", "march", use_llm=False)
        self.assertFalse(d2)
        self.assertNotEqual(j1.id, j2.id)

    def test_after_cancel_new_job_allowed(self):
        q = VideoJobQueue()
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


if __name__ == "__main__":
    unittest.main()
