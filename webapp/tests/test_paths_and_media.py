"""Safe path join + streaming media tests."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ANOR_MOCK_MEDIA"] = "1"

from webapp.paths import safe_join  # noqa: E402
from webapp.server import Handler, VIDEOS  # noqa: E402


class TestSafeJoin(unittest.TestCase):
    def test_allows_nested_relative(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a").mkdir()
            f = root / "a" / "b.mp4"
            f.write_bytes(b"x" * 10)
            got = safe_join(root, "a/b.mp4")
            self.assertEqual(got, f.resolve())

    def test_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertIsNone(safe_join(root, "../etc/passwd"))
            self.assertIsNone(safe_join(root, "a/../../etc/passwd"))
            self.assertIsNone(safe_join(root, "/etc/passwd"))
            self.assertIsNone(safe_join(root, ".."))

    def test_rejects_null_and_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertIsNone(safe_join(root, ""))
            self.assertIsNone(safe_join(root, "a\x00b"))


class TestMediaStreaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        # Ensure a known media file exists
        cls.sample_rel = None
        if VIDEOS.exists():
            for p in VIDEOS.rglob("*.mp4"):
                try:
                    cls.sample_rel = str(p.relative_to(VIDEOS.resolve()))
                    break
                except ValueError:
                    continue

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_traversal_media_forbidden(self):
        try:
            urllib.request.urlopen(
                self.base + "/media/videos/../../etc/passwd", timeout=5
            )
            self.fail("expected error")
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (403, 404))

    def test_range_request_when_media_present(self):
        if not self.sample_rel:
            self.skipTest("no sample mp4 under outputs/videos")
        url = self.base + "/media/videos/" + self.sample_rel
        req = urllib.request.Request(url, headers={"Range": "bytes=0-15"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 206)
            data = r.read()
            self.assertEqual(len(data), 16)
            self.assertTrue(r.headers.get("Content-Range", "").startswith("bytes 0-15/"))
            self.assertEqual(r.headers.get("Accept-Ranges"), "bytes")
            self.assertTrue(r.headers.get("ETag"))

    def test_static_css_etag_and_304(self):
        url = self.base + "/static/css/app.css"
        with urllib.request.urlopen(url, timeout=10) as r:
            self.assertEqual(r.status, 200)
            etag = r.headers.get("ETag")
            self.assertTrue(etag)
            self.assertIn("max-age", (r.headers.get("Cache-Control") or "").lower())
        req = urllib.request.Request(url, headers={"If-None-Match": etag})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected 304")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 304)

    def test_head_static_and_media(self):
        req = urllib.request.Request(self.base + "/static/css/app.css", method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(int(r.headers.get("Content-Length") or "0") > 0)
            self.assertEqual(r.read(), b"")
        if self.sample_rel:
            mreq = urllib.request.Request(
                self.base + "/media/videos/" + self.sample_rel, method="HEAD"
            )
            with urllib.request.urlopen(mreq, timeout=10) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.headers.get("Accept-Ranges"), "bytes")
                self.assertEqual(r.read(), b"")

    def test_catalog_available_flags(self):
        with urllib.request.urlopen(self.base + "/api/catalog", timeout=5) as r:
            import json

            cat = json.loads(r.read())
        self.assertIn("videos", cat)
        for v in cat["videos"]:
            self.assertIn("available", v)
            self.assertIsInstance(v["available"], bool)


if __name__ == "__main__":
    unittest.main()
