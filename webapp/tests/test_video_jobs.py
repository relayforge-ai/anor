"""Async video job queue API tests."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ANOR_MOCK_MEDIA"] = "1"
os.environ["ANOR_VIDEO_RATE_LIMIT"] = "50"
os.environ["ANOR_VIDEO_RATE_WINDOW"] = "60"

from webapp.server import Handler  # noqa: E402
from webapp.jobs import QUEUE  # noqa: E402
from webapp import security as sec  # noqa: E402


class TestVideoJobsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sec.VIDEO_JOB_LIMITER.reset()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def post_job(self, payload: dict):
        req = urllib.request.Request(
            self.base + "/api/video/jobs",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_enqueue_and_complete(self):
        status, job = self.post_job(
            {"scenario_id": "ELO-003", "choice_id": "historical", "use_llm": False}
        )
        self.assertEqual(status, 202, job)
        self.assertIn("id", job)
        self.assertIn(job["status"], ("queued", "running", "completed"))

        job_id = job["id"]
        deadline = time.time() + 120
        final = None
        while time.time() < deadline:
            with urllib.request.urlopen(
                self.base + "/api/video/jobs/" + job_id, timeout=10
            ) as r:
                final = json.loads(r.read())
            if final["status"] in ("completed", "failed"):
                break
            time.sleep(0.4)

        self.assertIsNotNone(final)
        self.assertEqual(final["status"], "completed", final)
        self.assertEqual(final["pct"], 100)
        self.assertIn("media_url", final.get("result") or {})
        self.assertTrue((final["result"]["media_url"] or "").startswith("/media/videos/"))
        # Absolute host paths must not leak to clients
        self.assertNotIn("out_mp4", final.get("result") or {})
        self.assertNotIn("script_path", final.get("result") or {})
        blob = json.dumps(final)
        self.assertNotIn(str(ROOT), blob)

    def test_rejects_bad_scenario(self):
        status, data = self.post_job(
            {"scenario_id": "../x", "choice_id": "historical"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data.get("code"), "bad_scenario_id")

    def test_list_jobs(self):
        with urllib.request.urlopen(self.base + "/api/video/jobs", timeout=5) as r:
            data = json.loads(r.read())
        self.assertIn("jobs", data)
        self.assertIn("queue", data)

    def test_health_includes_queue(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
            data = json.loads(r.read())
        self.assertIn("video_queue", data)
        self.assertIn("max_concurrent", data["video_queue"])


if __name__ == "__main__":
    unittest.main()
