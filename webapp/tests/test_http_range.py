"""Unit tests for HTTP byte-range parsing (media seeking)."""

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

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.http_range import parse_byte_range, ByteRange  # noqa: E402
from webapp.server import Handler, VIDEOS  # noqa: E402


class TestParseByteRange(unittest.TestCase):
    def test_no_header_full(self):
        r = parse_byte_range(None, 100)
        self.assertEqual(r, ByteRange(200, 0, 99))
        self.assertEqual(r.length, 100)

    def test_closed_range(self):
        r = parse_byte_range("bytes=0-15", 1000)
        self.assertEqual(r.status, 206)
        self.assertEqual(r.start, 0)
        self.assertEqual(r.end, 15)
        self.assertEqual(r.length, 16)

    def test_open_ended(self):
        r = parse_byte_range("bytes=50-", 100)
        self.assertEqual(r, ByteRange(206, 50, 99))
        self.assertEqual(r.length, 50)

    def test_suffix_last_n(self):
        r = parse_byte_range("bytes=-20", 100)
        self.assertEqual(r, ByteRange(206, 80, 99))
        self.assertEqual(r.length, 20)

    def test_suffix_larger_than_file(self):
        r = parse_byte_range("bytes=-500", 100)
        self.assertEqual(r, ByteRange(206, 0, 99))

    def test_unsatisfiable_start(self):
        r = parse_byte_range("bytes=999-", 100)
        self.assertEqual(r.status, 416)

    def test_inverted_range(self):
        r = parse_byte_range("bytes=50-10", 100)
        self.assertEqual(r.status, 416)

    def test_clamps_end(self):
        r = parse_byte_range("bytes=0-9999", 50)
        self.assertEqual(r, ByteRange(206, 0, 49))

    def test_multi_range_uses_first(self):
        r = parse_byte_range("bytes=0-9, 20-29", 100)
        self.assertEqual(r, ByteRange(206, 0, 9))

    def test_empty_size(self):
        r = parse_byte_range("bytes=0-10", 0)
        self.assertEqual(r.status, 200)


class TestMediaRangeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        # Prefer real render output; else plant a tiny file under VIDEOS
        cls.sample_rel = None
        cls._tmpdir = None
        if VIDEOS.exists():
            for p in VIDEOS.rglob("*.mp4"):
                try:
                    cls.sample_rel = str(p.relative_to(VIDEOS.resolve()))
                    break
                except ValueError:
                    continue
        if not cls.sample_rel:
            VIDEOS.mkdir(parents=True, exist_ok=True)
            plant = VIDEOS / "_range_test" / "sample.bin"
            plant.parent.mkdir(parents=True, exist_ok=True)
            plant.write_bytes(bytes(range(256)))
            cls.sample_rel = "_range_test/sample.bin"
            cls._planted = True
        else:
            cls._planted = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if getattr(cls, "_planted", False):
            try:
                plant = VIDEOS / "_range_test"
                for p in plant.rglob("*"):
                    if p.is_file():
                        p.unlink()
                plant.rmdir()
            except OSError:
                pass

    def _url(self) -> str:
        return self.base + "/media/videos/" + self.sample_rel

    def test_partial_content_206(self):
        req = urllib.request.Request(self._url(), headers={"Range": "bytes=0-15"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 206)
            data = r.read()
            self.assertEqual(len(data), 16)
            self.assertTrue(r.headers.get("Content-Range", "").startswith("bytes 0-15/"))
            self.assertEqual(r.headers.get("Accept-Ranges"), "bytes")

    def test_suffix_range(self):
        # Read file size via HEAD
        hreq = urllib.request.Request(self._url(), method="HEAD")
        with urllib.request.urlopen(hreq, timeout=10) as r:
            size = int(r.headers.get("Content-Length") or "0")
        self.assertGreater(size, 10)
        n = 8
        req = urllib.request.Request(self._url(), headers={"Range": f"bytes=-{n}"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.status, 206)
            data = r.read()
            self.assertEqual(len(data), n)
            cr = r.headers.get("Content-Range", "")
            self.assertIn(f"/{size}", cr)
            self.assertTrue(cr.startswith(f"bytes {size - n}-{size - 1}/"))

    def test_unsatisfiable_416(self):
        req = urllib.request.Request(self._url(), headers={"Range": "bytes=999999999-"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected 416")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 416)
            self.assertTrue(
                (e.headers.get("Content-Range") or "").startswith("bytes */")
            )
            self.assertEqual(e.headers.get("Accept-Ranges"), "bytes")


if __name__ == "__main__":
    unittest.main()
