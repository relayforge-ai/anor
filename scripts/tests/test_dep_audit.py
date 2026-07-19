"""Tests for scripts/dep_audit.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import dep_audit  # noqa: E402


class TestDepAudit(unittest.TestCase):
    def test_is_pinned(self):
        self.assertTrue(dep_audit.is_pinned("==1.2.3"))
        self.assertTrue(dep_audit.is_pinned(">=1.0,<2.0"))
        self.assertTrue(dep_audit.is_pinned("~=1.50"))
        self.assertFalse(dep_audit.is_pinned(""))
        self.assertFalse(dep_audit.is_pinned(">=0.40.0"))  # lower bound only

    def test_parse_sim_requirements(self):
        path = ROOT / "sim" / "requirements.txt"
        reqs = dep_audit.parse_requirements(path)
        names = {n for n, _ in reqs}
        self.assertIn("anthropic", names)
        self.assertIn("openai", names)

    def test_audit_files_runs(self):
        # non-strict should not fail the repo today
        rc = dep_audit.audit_files(strict=False)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
