"""Scenario pack validation tests."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.fork_engine import list_scenarios, load_scenario
from pipeline.validate import ScenarioValidationError, validate_scenario


def _good_pack() -> dict:
    return json.loads((ROOT / "scenarios" / "public" / "ELO-003.json").read_text(encoding="utf-8"))


class TestValidateScenario(unittest.TestCase):
    def test_real_packs_pass(self):
        for sid in ("ELO-001", "ELO-003", "ELO-013"):
            data = load_scenario(sid)
            self.assertEqual(data["scenario_id"], sid)

    def test_list_has_no_filesystem_paths(self):
        for item in list_scenarios():
            self.assertNotIn("path", item)
            blob = json.dumps(item)
            self.assertNotIn(str(ROOT), blob)

    def test_missing_required(self):
        bad = _good_pack()
        del bad["known_outcome"]
        with self.assertRaises(ScenarioValidationError):
            validate_scenario(bad)

    def test_requires_exactly_one_historical(self):
        bad = _good_pack()
        for c in bad["choices"]:
            c["is_historical"] = False
            c["speculation_level"] = "simulated"
        with self.assertRaises(ScenarioValidationError) as ctx:
            validate_scenario(bad)
        self.assertIn("exactly one", str(ctx.exception))

    def test_historical_must_be_documented(self):
        bad = _good_pack()
        for c in bad["choices"]:
            if c["is_historical"]:
                c["speculation_level"] = "simulated"
        with self.assertRaises(ScenarioValidationError):
            validate_scenario(bad)

    def test_rejects_path_in_scenario_id(self):
        bad = _good_pack()
        bad["scenario_id"] = "../etc/passwd"
        with self.assertRaises(ScenarioValidationError):
            validate_scenario(bad)

    def test_duplicate_choice_ids(self):
        bad = _good_pack()
        bad["choices"][1]["id"] = bad["choices"][0]["id"]
        with self.assertRaises(ScenarioValidationError):
            validate_scenario(bad)

    def test_invalid_speculation_level(self):
        bad = _good_pack()
        bad["choices"][1]["speculation_level"] = "fanfic"
        with self.assertRaises(ScenarioValidationError):
            validate_scenario(bad)


if __name__ == "__main__":
    unittest.main()
