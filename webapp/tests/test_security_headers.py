"""Security response header tests."""

from __future__ import annotations

import os
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["ANOR_MOCK_MEDIA"] = "1"

from webapp.server import Handler  # noqa: E402
from webapp.security import security_headers  # noqa: E402


class TestSecurityHeaders(unittest.TestCase):
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

    def test_header_dict_has_core_keys(self):
        h = security_headers()
        for key in (
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
            "Cross-Origin-Opener-Policy",
        ):
            self.assertIn(key, h)
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_html_response_sends_headers(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as r:
            headers = {k.lower(): v for k, v in r.headers.items()}
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        self.assertIn("content-security-policy", headers)
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertEqual(headers.get("referrer-policy"), "strict-origin-when-cross-origin")
        self.assertTrue(headers.get("x-request-id"))

    def test_json_api_also_hardened(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=5) as r:
            headers = {k.lower(): v for k, v in r.headers.items()}
            body = r.read().decode()
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        self.assertIn("content-security-policy", headers)
        # Health must not leak absolute host paths
        data = __import__("json").loads(body)
        self.assertNotIn("videos_dir", data)
        self.assertIn("videos_count", data)
        self.assertIn("scenarios_count", data)
        self.assertNotIn(str(ROOT), body)


if __name__ == "__main__":
    unittest.main()
