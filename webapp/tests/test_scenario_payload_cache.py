"""Per-pack scenario detail payload cache tests."""

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


class TestScenarioPayloadCache(unittest.TestCase):
    def setUp(self):
        server_mod.clear_scenario_payload_cache()
        os.environ["ANOR_SCENARIOS_CACHE_S"] = "60"

    def tearDown(self):
        server_mod.clear_scenario_payload_cache()
        os.environ.pop("ANOR_SCENARIOS_CACHE_S", None)

    def test_payload_has_choices(self):
        p = server_mod.scenario_payload_cached("ELO-003")
        self.assertEqual(p["scenario_id"], "ELO-003")
        self.assertIn("choices", p)
        self.assertGreaterEqual(len(p["choices"]), 1)
        self.assertNotIn("opening_internal", p)

    def test_second_load_skips_disk(self):
        server_mod.clear_scenario_payload_cache()
        p1 = server_mod.scenario_payload_cached("ELO-003")
        with patch(
            "webapp.server.scenario_payload",
            side_effect=AssertionError("should not rebuild"),
        ):
            p2 = server_mod.scenario_payload_cached("ELO-003")
        self.assertEqual(p1, p2)

    def test_cache_disabled_rebuilds(self):
        os.environ["ANOR_SCENARIOS_CACHE_S"] = "0"
        server_mod.clear_scenario_payload_cache()
        calls = {"n": 0}
        real = server_mod.scenario_payload

        def counting(sid, *a, **k):  # noqa: ANN001
            calls["n"] += 1
            return real(sid, *a, **k)

        with patch("webapp.server.scenario_payload", side_effect=counting):
            server_mod.scenario_payload_cached("ELO-003")
            n1 = calls["n"]
            server_mod.scenario_payload_cached("ELO-003")
            n2 = calls["n"]
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 2)

    def test_clear_forces_rebuild(self):
        server_mod.clear_scenario_payload_cache()
        server_mod.scenario_payload_cached("ELO-003")
        server_mod.clear_scenario_payload_cache()
        with patch(
            "webapp.server.scenario_payload",
            side_effect=AssertionError("rebuilt"),
        ):
            with self.assertRaises(AssertionError):
                server_mod.scenario_payload_cached("ELO-003")

    def test_missing_pack_not_cached(self):
        server_mod.clear_scenario_payload_cache()
        with self.assertRaises(FileNotFoundError):
            server_mod.scenario_payload_cached("NO-SUCH-PACK-XYZ")
        self.assertEqual(len(server_mod._scenario_payload_cache), 0)

    def test_cache_bound_evicts_oldest(self):
        server_mod.clear_scenario_payload_cache()
        prev_max = server_mod._SCENARIO_PAYLOAD_MAX
        server_mod._SCENARIO_PAYLOAD_MAX = 2
        try:
            # Seed three distinct ids using real packs when available
            packs = sorted(
                p.stem for p in server_mod.SCENARIOS_PUBLIC.glob("*.json")
            )
            self.assertGreaterEqual(len(packs), 2)
            # Force artificial multi-entry by reusing one real payload under fake keys
            real = server_mod.scenario_payload(packs[0])
            with patch("webapp.server.scenario_payload", return_value=real):
                with patch(
                    "webapp.server._scenario_file_fingerprint",
                    side_effect=lambda sid: f"sig-{sid}",
                ):
                    server_mod.scenario_payload_cached("A")
                    server_mod.scenario_payload_cached("B")
                    server_mod.scenario_payload_cached("C")
            self.assertLessEqual(
                len(server_mod._scenario_payload_cache), 2
            )
            self.assertNotIn("A", server_mod._scenario_payload_cache)
            self.assertIn("C", server_mod._scenario_payload_cache)
        finally:
            server_mod._SCENARIO_PAYLOAD_MAX = prev_max
            server_mod.clear_scenario_payload_cache()


if __name__ == "__main__":
    unittest.main()
