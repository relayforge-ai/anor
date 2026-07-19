"""Access-log noise control (health probes silent by default)."""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")

from webapp.server import Handler  # noqa: E402


class _FakeHandler(Handler):
    """Minimal stand-in to call log_message without a real socket."""

    def __init__(self):
        # Skip BaseHTTPRequestHandler.__init__ (needs request, client, server)
        self._request_id = "test-rid"
        self.client_address = ("127.0.0.1", 9)

    def address_string(self) -> str:
        return "127.0.0.1"


class TestAccessLog(unittest.TestCase):
    def test_health_probe_silent_by_default(self):
        prev = os.environ.pop("ANOR_LOG_HEALTH", None)
        try:
            h = _FakeHandler()
            buf = io.StringIO()
            with redirect_stderr(buf):
                h.log_message('%s - "%s" %s', "127.0.0.1", "GET /api/health HTTP/1.1", "200")
                h.log_message('%s - "%s" %s', "127.0.0.1", "GET /api/catalog HTTP/1.1", "200")
            out = buf.getvalue()
            self.assertNotIn("/api/health", out)
            self.assertIn("/api/catalog", out)
            self.assertIn("test-rid", out)
        finally:
            if prev is not None:
                os.environ["ANOR_LOG_HEALTH"] = prev

    def test_health_probe_logged_when_enabled(self):
        prev = os.environ.get("ANOR_LOG_HEALTH")
        os.environ["ANOR_LOG_HEALTH"] = "1"
        try:
            h = _FakeHandler()
            buf = io.StringIO()
            with redirect_stderr(buf):
                h.log_message('%s - "%s" %s', "127.0.0.1", "GET /api/health HTTP/1.1", "200")
            self.assertIn("/api/health", buf.getvalue())
        finally:
            if prev is None:
                os.environ.pop("ANOR_LOG_HEALTH", None)
            else:
                os.environ["ANOR_LOG_HEALTH"] = prev


if __name__ == "__main__":
    unittest.main()
