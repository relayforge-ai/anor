"""Public error redaction — no absolute host paths in client-facing job errors."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.jobs import (  # noqa: E402
    ROOT as JOBS_ROOT,
    VideoJobQueue,
    sanitize_public_error,
)


class TestSanitizePublicError(unittest.TestCase):
    def test_redacts_repo_root(self):
        raw = f"failed writing {JOBS_ROOT}/outputs/videos/ELO-003-historical/x.mp4"
        out = sanitize_public_error(raw)
        self.assertNotIn(str(JOBS_ROOT), out)
        self.assertIn("<anor>", out)
        self.assertIn("ELO-003-historical", out or "x.mp4")

    def test_redacts_users_home_paths(self):
        raw = (
            "Command '['ffmpeg', '-i', "
            "'/Users/sheldonclawd/secret/work/clip.mp4']' failed"
        )
        out = sanitize_public_error(raw)
        self.assertNotIn("/Users/sheldonclawd", out)
        self.assertIn("<path>/clip.mp4", out)

    def test_truncates(self):
        out = sanitize_public_error("x" * 1000, limit=50)
        self.assertLessEqual(len(out), 50)
        self.assertTrue(out.endswith("…"))

    def test_server_client_error_redacts_paths(self):
        """HTTP error helper must not echo absolute host paths."""
        import json
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch

        from webapp.server import Handler

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://{httpd.server_address[0]}:{port}"
        try:
            boom = RuntimeError(
                f"failed reading {JOBS_ROOT}/outputs/videos/ELO-003-historical/x.mp4"
            )
            with patch("webapp.server.run_fork", side_effect=boom):
                req = urllib.request.Request(
                    base + "/api/fork",
                    data=json.dumps(
                        {
                            "scenario_id": "ELO-003",
                            "choice_id": "historical",
                            "use_llm": False,
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    urllib.request.urlopen(req, timeout=10)
                    self.fail("expected error")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 400)
                    body = json.loads(e.read().decode() or "{}")
                    self.assertEqual(body.get("code"), "fork_failed")
                    err = body.get("error") or ""
                    self.assertNotIn(str(JOBS_ROOT), err)
                    self.assertNotIn("/Users/", err)
                    self.assertIn("<anor>", err)
        finally:
            httpd.shutdown()

    def test_worker_failed_job_error_has_no_host_path(self):
        q = VideoJobQueue()
        boom = RuntimeError(
            f"Command '['ffmpeg', '-i', '{JOBS_ROOT}/outputs/videos/x/a.mp4']' "
            f"returned non-zero exit status 254."
        )

        def fail_render(*args, **kwargs):
            raise boom

        with patch("webapp.jobs.check_render_dependencies", return_value=(True, "ok")):
            with patch("webapp.jobs.acquire_render_lock", return_value=(None, None)):
                with patch("webapp.jobs.release_render_lock"):
                    with patch(
                        "pipeline.video_pipeline.render_video",
                        side_effect=fail_render,
                    ):
                        job, _ = q.enqueue(
                            "ELO-001",
                            "historical",
                            use_llm=False,
                            owner_key="t",
                        )
                        import time

                        deadline = time.time() + 5
                        final = None
                        while time.time() < deadline:
                            final = q.get(job.id)
                            if final and final.status in (
                                "failed",
                                "completed",
                                "cancelled",
                                "timed_out",
                            ):
                                break
                            time.sleep(0.02)
                        self.assertIsNotNone(final)
                        self.assertEqual(final.status, "failed")
                        err = final.error or ""
                        self.assertNotIn(str(JOBS_ROOT), err)
                        self.assertNotIn("/Users/", err)
                        pub = final.to_public()
                        self.assertNotIn(str(JOBS_ROOT), str(pub.get("error") or ""))


if __name__ == "__main__":
    unittest.main()
