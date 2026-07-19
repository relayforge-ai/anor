"""Public /api/health must not leak operator recon by default."""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")
# Ensure public slim mode for this module
os.environ.pop("ANOR_HEALTH_DETAIL", None)
os.environ.pop("ANOR_HEALTH_TOKEN", None)

from webapp.server import Handler  # noqa: E402


class TestHealthPrivacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_public_health_is_slim(self):
        os.environ.pop("ANOR_HEALTH_DETAIL", None)
        os.environ.pop("ANOR_HEALTH_TOKEN", None)
        with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
            data = json.loads(r.read())
        self.assertEqual(data.get("site"), "ok")
        self.assertIn("version", data)
        self.assertIn("ready", data)
        self.assertFalse(data.get("detail"))
        for leaked in (
            "security",
            "pipeline",
            "videos_present",
            "videos_count",
            "scenarios_count",
        ):
            self.assertNotIn(leaked, data, f"public health must not include {leaked}")
        vq = data.get("video_queue") or {}
        self.assertIn("ffmpeg_ok", vq)
        self.assertIn("disk_ok", vq)
        self.assertNotIn("timeout_s", vq)
        self.assertNotIn("max_concurrent", vq)

    def test_detail_with_env_flag(self):
        prev = os.environ.get("ANOR_HEALTH_DETAIL")
        os.environ["ANOR_HEALTH_DETAIL"] = "1"
        try:
            with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
                data = json.loads(r.read())
            self.assertTrue(data.get("detail"))
            self.assertIn("security", data)
            self.assertIn("api_rate_limit", data["security"])
            self.assertIn("pipeline", data)
            self.assertIn("max_concurrent", data.get("video_queue") or {})
        finally:
            if prev is None:
                os.environ.pop("ANOR_HEALTH_DETAIL", None)
            else:
                os.environ["ANOR_HEALTH_DETAIL"] = prev

    def test_detail_with_token_header(self):
        prev_d = os.environ.get("ANOR_HEALTH_DETAIL")
        prev_t = os.environ.get("ANOR_HEALTH_TOKEN")
        os.environ.pop("ANOR_HEALTH_DETAIL", None)
        os.environ["ANOR_HEALTH_TOKEN"] = "test-health-secret"
        try:
            # Without token → slim
            with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
                slim = json.loads(r.read())
            self.assertFalse(slim.get("detail"))
            self.assertNotIn("security", slim)
            # Wrong token → slim
            req_bad = urllib.request.Request(
                self.base + "/api/health",
                headers={"X-ANOR-Health-Token": "wrong"},
            )
            with urllib.request.urlopen(req_bad, timeout=5) as r:
                bad = json.loads(r.read())
            self.assertFalse(bad.get("detail"))
            # Correct token → full
            req = urllib.request.Request(
                self.base + "/api/health",
                headers={"X-ANOR-Health-Token": "test-health-secret"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                full = json.loads(r.read())
            self.assertTrue(full.get("detail"))
            self.assertIn("security", full)
            self.assertIn("pipeline", full)
        finally:
            if prev_d is None:
                os.environ.pop("ANOR_HEALTH_DETAIL", None)
            else:
                os.environ["ANOR_HEALTH_DETAIL"] = prev_d
            if prev_t is None:
                os.environ.pop("ANOR_HEALTH_TOKEN", None)
            else:
                os.environ["ANOR_HEALTH_TOKEN"] = prev_t


if __name__ == "__main__":
    unittest.main()
