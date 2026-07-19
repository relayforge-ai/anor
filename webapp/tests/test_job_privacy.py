"""Video job list must not leak other clients' jobs."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")
os.environ["ANOR_VIDEO_MAX_CONCURRENT"] = "2"
os.environ["ANOR_VIDEO_MAX_QUEUED"] = "8"


class TestJobListPrivacy(unittest.TestCase):
    def test_list_for_owner_filters(self):
        from webapp.jobs import VideoJobQueue

        q = VideoJobQueue()
        with patch("webapp.jobs.check_render_dependencies", return_value=(True, "ok")):
            with patch("pipeline.video_pipeline.render_video", side_effect=RuntimeError("stop")):
                j1, _ = q.enqueue("ELO-001", "historical", owner_key="client-a")
                j2, _ = q.enqueue("ELO-003", "historical", owner_key="client-b")
                j3, _ = q.enqueue("ELO-013", "historical", owner_key="client-a")

        a_jobs = q.list_for_owner("client-a")
        a_ids = {j.id for j in a_jobs}
        self.assertIn(j1.id, a_ids)
        self.assertIn(j3.id, a_ids)
        self.assertNotIn(j2.id, a_ids)

        b_jobs = q.list_for_owner("client-b")
        self.assertEqual({j.id for j in b_jobs}, {j2.id})

        self.assertEqual(q.list_for_owner(""), [])
        self.assertEqual(q.list_for_owner("nobody"), [])

    def test_to_public_omits_owner_key(self):
        from webapp.jobs import VideoJob

        j = VideoJob(
            id="abcd1234abcd1234",
            scenario_id="ELO-001",
            choice_id="historical",
            use_llm=False,
            owner_key="secret-peer",
        )
        pub = j.to_public()
        self.assertNotIn("owner_key", pub)
        self.assertNotIn("secret-peer", json_dumps_safe(pub))


def json_dumps_safe(obj) -> str:
    import json

    return json.dumps(obj)


if __name__ == "__main__":
    unittest.main()
