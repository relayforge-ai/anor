"""HTTP request socket timeout configuration."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import webapp.server as server_mod  # noqa: E402


class TestRequestTimeout(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("ANOR_REQUEST_TIMEOUT_S", None)
        server_mod.Handler.timeout = server_mod.request_timeout_s()

    def test_default_is_sixty(self):
        os.environ.pop("ANOR_REQUEST_TIMEOUT_S", None)
        self.assertEqual(server_mod.request_timeout_s(), 60.0)

    def test_custom_value(self):
        os.environ["ANOR_REQUEST_TIMEOUT_S"] = "30"
        self.assertEqual(server_mod.request_timeout_s(), 30.0)

    def test_minimum_one_second(self):
        os.environ["ANOR_REQUEST_TIMEOUT_S"] = "0.1"
        self.assertEqual(server_mod.request_timeout_s(), 1.0)

    def test_disable_with_zero(self):
        os.environ["ANOR_REQUEST_TIMEOUT_S"] = "0"
        self.assertIsNone(server_mod.request_timeout_s())

    def test_disable_with_off(self):
        os.environ["ANOR_REQUEST_TIMEOUT_S"] = "off"
        self.assertIsNone(server_mod.request_timeout_s())

    def test_invalid_falls_back_to_default(self):
        os.environ["ANOR_REQUEST_TIMEOUT_S"] = "nope"
        self.assertEqual(server_mod.request_timeout_s(), 60.0)

    def test_handler_timeout_attribute_exists(self):
        # BaseHTTPRequestHandler uses Handler.timeout for socket.settimeout
        self.assertTrue(hasattr(server_mod.Handler, "timeout"))
        server_mod.Handler.timeout = 45.0
        self.assertEqual(server_mod.Handler.timeout, 45.0)

    def test_server_version_bumped(self):
        self.assertIn("ForkedHistory", server_mod.Handler.server_version)


if __name__ == "__main__":
    unittest.main()
