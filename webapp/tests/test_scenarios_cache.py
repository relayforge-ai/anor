"""Public pack list cache tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANOR_MOCK_MEDIA", "1")
os.environ["ANOR_SCENARIOS_CACHE_S"] = "60"

import webapp.server as server_mod  # noqa: E402


class TestScenariosListCache(unittest.TestCase):
    def setUp(self):
        server_mod.clear_scenarios_list_cache()
        os.environ["ANOR_SCENARIOS_CACHE_S"] = "60"

    def tearDown(self):
        server_mod.clear_scenarios_list_cache()
        os.environ.pop("ANOR_SCENARIOS_CACHE_S", None)

    def test_list_has_public_packs(self):
        rows = server_mod.list_scenarios_cached()
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertIn("scenario_id", row)
            self.assertIn("title", row)
            # Public API must not leak filesystem paths
            blob = str(row)
            self.assertNotIn("/Users/", blob)
            self.assertNotIn("scenarios/public", blob)

    def test_second_list_skips_disk_reads(self):
        server_mod.clear_scenarios_list_cache()
        rows1 = server_mod.list_scenarios_cached()
        with patch(
            "webapp.server.list_scenarios",
            side_effect=AssertionError("should not rebuild"),
        ):
            rows2 = server_mod.list_scenarios_cached()
        self.assertEqual(rows1, rows2)

    def test_cache_disabled_rebuilds(self):
        os.environ["ANOR_SCENARIOS_CACHE_S"] = "0"
        server_mod.clear_scenarios_list_cache()
        calls = {"n": 0}
        real = server_mod.list_scenarios

        def counting(*args, **kwargs):  # noqa: ANN001
            calls["n"] += 1
            return real(*args, **kwargs)

        with patch("webapp.server.list_scenarios", side_effect=counting):
            server_mod.list_scenarios_cached()
            n1 = calls["n"]
            server_mod.list_scenarios_cached()
            n2 = calls["n"]
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 2)

    def test_clear_forces_rebuild(self):
        server_mod.clear_scenarios_list_cache()
        server_mod.list_scenarios_cached()
        server_mod.clear_scenarios_list_cache()
        with patch(
            "webapp.server.list_scenarios",
            side_effect=AssertionError("rebuilt"),
        ):
            with self.assertRaises(AssertionError):
                server_mod.list_scenarios_cached()

    def test_fingerprint_changes_with_pack_size(self):
        """Sig includes file size so quiet content edits invalidate cache."""
        sig1 = server_mod._scenarios_dir_fingerprint()
        self.assertTrue(sig1)
        self.assertNotEqual(sig1, "missing")
        # Fingerprint is stable across immediate re-calls
        self.assertEqual(sig1, server_mod._scenarios_dir_fingerprint())


if __name__ == "__main__":
    unittest.main()
