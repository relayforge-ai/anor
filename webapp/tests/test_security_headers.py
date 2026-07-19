"""Security response header tests."""

from __future__ import annotations

import importlib
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

os.environ["ANOR_MOCK_MEDIA"] = "1"
# HSTS off for default header tests
os.environ.pop("ANOR_HSTS_MAX_AGE", None)
os.environ.pop("ANOR_HSTS_SUBDOMAINS", None)
os.environ.pop("ANOR_HSTS_PRELOAD", None)

import webapp.security as security  # noqa: E402

importlib.reload(security)

from webapp.server import Handler  # noqa: E402


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
        os.environ.pop("ANOR_HSTS_MAX_AGE", None)
        importlib.reload(security)
        h = security.security_headers()
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
        self.assertNotIn("Strict-Transport-Security", h)
        expose = h.get("Access-Control-Expose-Headers", "")
        for name in (
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-Request-ID",
            "ETag",
        ):
            self.assertIn(name, expose)

    def test_hsts_when_configured(self):
        prev = os.environ.get("ANOR_HSTS_MAX_AGE")
        prev_sub = os.environ.get("ANOR_HSTS_SUBDOMAINS")
        prev_pre = os.environ.get("ANOR_HSTS_PRELOAD")
        os.environ["ANOR_HSTS_MAX_AGE"] = "31536000"
        os.environ["ANOR_HSTS_SUBDOMAINS"] = "1"
        os.environ.pop("ANOR_HSTS_PRELOAD", None)
        try:
            importlib.reload(security)
            h = security.security_headers()
            self.assertIn("Strict-Transport-Security", h)
            self.assertIn("max-age=31536000", h["Strict-Transport-Security"])
            self.assertIn("includeSubDomains", h["Strict-Transport-Security"])
            self.assertEqual(
                security.hsts_header_value(),
                "max-age=31536000; includeSubDomains",
            )
            # Zero / invalid → disabled
            os.environ["ANOR_HSTS_MAX_AGE"] = "0"
            importlib.reload(security)
            self.assertIsNone(security.hsts_header_value())
            os.environ["ANOR_HSTS_MAX_AGE"] = "nope"
            importlib.reload(security)
            self.assertIsNone(security.hsts_header_value())
        finally:
            if prev is None:
                os.environ.pop("ANOR_HSTS_MAX_AGE", None)
            else:
                os.environ["ANOR_HSTS_MAX_AGE"] = prev
            if prev_sub is None:
                os.environ.pop("ANOR_HSTS_SUBDOMAINS", None)
            else:
                os.environ["ANOR_HSTS_SUBDOMAINS"] = prev_sub
            if prev_pre is None:
                os.environ.pop("ANOR_HSTS_PRELOAD", None)
            else:
                os.environ["ANOR_HSTS_PRELOAD"] = prev_pre
            importlib.reload(security)

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
        data = json.loads(body)
        self.assertNotIn("videos_dir", data)
        self.assertNotIn("videos_present", data)
        self.assertIn("ready", data)
        self.assertFalse(data.get("detail"))
        self.assertNotIn(str(ROOT), body)

    def test_unknown_api_404_omits_path(self):
        try:
            urllib.request.urlopen(self.base + "/api/no-such-endpoint", timeout=5)
            self.fail("expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            data = json.loads(e.read().decode() or "{}")
            self.assertEqual(data.get("code"), "not_found")
            self.assertNotIn("path", data)
            self.assertNotIn("no-such-endpoint", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
