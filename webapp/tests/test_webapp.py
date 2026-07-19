"""Smoke tests for Forked History webapp (no browser)."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from webapp.server import Handler  # noqa: E402
from http.server import ThreadingHTTPServer


class TestWebapp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Clear any rate-limit state left by security tests in the same process
        from webapp import security as sec

        sec.FORK_LIMITER.reset()
        sec.LLM_FORK_LIMITER.reset()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    def setUp(self):
        from webapp import security as sec

        sec.FORK_LIMITER.reset()
        sec.LLM_FORK_LIMITER.reset()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read(), r.headers

    def test_index(self):
        status, body, _ = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Forked History", body)

    def test_catalog(self):
        status, body, headers = self.get("/api/catalog")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("pricing", data)
        self.assertGreaterEqual(len(data.get("videos", [])), 1)
        self.assertEqual(data["freemium"]["full_videos_free"], 1)
        self.assertEqual(data["freemium"]["preview_fraction"], 0.25)
        etag = headers.get("ETag")
        self.assertTrue(etag)
        self.assertIn("max-age", (headers.get("Cache-Control") or "").lower())

    def test_catalog_etag_304(self):
        status, body, headers = self.get("/api/catalog")
        self.assertEqual(status, 200)
        etag = headers.get("ETag")
        self.assertTrue(etag)
        req = urllib.request.Request(
            self.base + "/api/catalog",
            headers={"If-None-Match": etag},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected 304")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 304)
            self.assertEqual(e.headers.get("ETag"), etag)

    def test_scenarios(self):
        status, body, headers = self.get("/api/scenarios")
        data = json.loads(body)
        self.assertTrue(any(s["scenario_id"] == "ELO-003" for s in data))
        self.assertTrue(headers.get("ETag"))

    def test_catalog_gzip_when_accepted(self):
        """Clients that Accept-Encoding: gzip get compressed JSON when it helps."""
        import gzip

        req = urllib.request.Request(
            self.base + "/api/catalog",
            headers={"Accept-Encoding": "gzip"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
            enc = (r.headers.get("Content-Encoding") or "").lower()
            raw = r.read()
            # Catalog is large enough to compress under the 512-byte threshold
            self.assertEqual(enc, "gzip")
            self.assertIn("accept-encoding", (r.headers.get("Vary") or "").lower())
            data = json.loads(gzip.decompress(raw))
            self.assertIn("pricing", data)
            self.assertIn("videos", data)

    def test_catalog_plain_without_gzip_accept(self):
        req = urllib.request.Request(
            self.base + "/api/catalog",
            headers={"Accept-Encoding": "identity"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
            enc = (r.headers.get("Content-Encoding") or "").lower()
            self.assertNotEqual(enc, "gzip")
            data = json.loads(r.read())
            self.assertIn("pricing", data)

    def test_server_header_hides_python_version(self):
        status, _, headers = self.get("/api/health")
        self.assertEqual(status, 200)
        server = headers.get("Server") or ""
        self.assertIn("ForkedHistory", server)
        self.assertNotIn("Python", server)
        self.assertNotIn("CPython", server)

    def test_scenario_detail_etag_304(self):
        status, body, headers = self.get("/api/scenario/ELO-003")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data.get("scenario_id"), "ELO-003")
        etag = headers.get("ETag")
        self.assertTrue(etag)
        self.assertIn("max-age", (headers.get("Cache-Control") or "").lower())
        req = urllib.request.Request(
            self.base + "/api/scenario/ELO-003",
            headers={"If-None-Match": etag},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected 304")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 304)
            self.assertEqual(e.headers.get("ETag"), etag)

    def test_fork(self):
        req = urllib.request.Request(
            self.base + "/api/fork",
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
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        self.assertEqual(data["scenario_id"], "ELO-003")
        self.assertTrue(data["is_historical"])


if __name__ == "__main__":
    unittest.main()
