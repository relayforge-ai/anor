"""Membership token + server enforcement tests."""

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

os.environ["ANOR_MOCK_MEDIA"] = "1"


def _reload_membership(secret: str | None, enforce: str | None):
    import importlib
    import webapp.membership as membership
    import webapp.server as server_mod

    if secret is None:
        os.environ.pop("ANOR_MEMBER_SECRET", None)
    else:
        os.environ["ANOR_MEMBER_SECRET"] = secret
    if enforce is None:
        os.environ.pop("ANOR_MEMBER_ENFORCE", None)
    else:
        os.environ["ANOR_MEMBER_ENFORCE"] = enforce
    importlib.reload(membership)
    server_mod.mem = membership
    return membership


class TestTokenCrypto(unittest.TestCase):
    def setUp(self):
        self.mem = _reload_membership("test-secret-for-unit-tests-only", "1")

    def tearDown(self):
        _reload_membership(None, None)

    def test_issue_and_verify(self):
        self.assertTrue(self.mem.enforcement_enabled())
        tok = self.mem.issue_token("scholar")
        self.assertIsNotNone(tok)
        ok, reason = self.mem.verify_token(tok)
        self.assertTrue(ok, reason)

    def test_reject_tampered(self):
        tok = self.mem.issue_token("scholar")
        bad = tok[:-4] + "dead"
        ok, reason = self.mem.verify_token(bad)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_signature")

    def test_reject_missing(self):
        ok, reason = self.mem.verify_token(None)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_token")


class TestMemberAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mem = _reload_membership("test-secret-for-unit-tests-only", "1")
        from webapp import security as sec
        from webapp.server import Handler

        sec.DEMO_TOKEN_LIMITER.reset()
        sec.VIDEO_JOB_LIMITER.reset()
        sec.FORK_LIMITER.reset()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        _reload_membership(None, None)

    def post(self, path: str, payload: dict, headers: dict | None = None):
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers=h,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def test_demo_token_and_video_with_header(self):
        status, data = self.post("/api/member/demo", {"plan": "scholar"})
        self.assertEqual(status, 200, data)
        self.assertIn("token", data)
        token = data["token"]

        status2, job = self.post(
            "/api/video/jobs",
            {"scenario_id": "ELO-003", "choice_id": "historical"},
            headers={"X-ANOR-Member": token},
        )
        self.assertEqual(status2, 202, job)
        self.assertIn("id", job)

    def test_video_without_token_rejected(self):
        status, data = self.post(
            "/api/video/jobs",
            {"scenario_id": "ELO-003", "choice_id": "historical"},
        )
        self.assertEqual(status, 401, data)
        self.assertEqual(data.get("code"), "member_required")

    def test_llm_fork_without_token_rejected(self):
        status, data = self.post(
            "/api/fork",
            {
                "scenario_id": "ELO-003",
                "choice_id": "historical",
                "use_llm": True,
            },
        )
        self.assertEqual(status, 401, data)
        self.assertEqual(data.get("code"), "member_required")

    def test_basic_fork_still_open(self):
        status, data = self.post(
            "/api/fork",
            {
                "scenario_id": "ELO-003",
                "choice_id": "historical",
                "use_llm": False,
            },
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data.get("source"), "authored")


if __name__ == "__main__":
    unittest.main()
