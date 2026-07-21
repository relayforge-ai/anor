"""Scenario pack validation tests."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "scenarios" / "public"
CATALOG = ROOT / "webapp" / "data" / "catalog.json"
sys.path.insert(0, str(ROOT))

from pipeline.fork_engine import list_scenarios, load_scenario
from pipeline.validate import ScenarioValidationError, validate_scenario


def _good_pack() -> dict:
    return json.loads((ROOT / "scenarios" / "public" / "ELO-003.json").read_text(encoding="utf-8"))


def _public_pack_paths() -> list[Path]:
    return sorted(PUBLIC.glob("ELO-*.json"))


class TestValidateScenario(unittest.TestCase):
    def test_real_packs_pass(self):
        for sid in ("ELO-001", "ELO-003", "ELO-013"):
            data = load_scenario(sid)
            self.assertEqual(data["scenario_id"], sid)

    def test_all_public_packs_pass_validation(self):
        """Every scenarios/public/ELO-*.json must load through the stdlib validator.

        Catches corrupt packs before Studio/video pipeline; keeps freemium
        catalog and social drafts honest against ELOSTIRION public canon only.
        """
        paths = _public_pack_paths()
        self.assertGreaterEqual(len(paths), 4, "expected a baseline public pack set")
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            data = validate_scenario(raw)
            self.assertEqual(data["scenario_id"], path.stem)
            # Round-trip via load_scenario (same path the product uses)
            loaded = load_scenario(path.stem)
            self.assertEqual(loaded["scenario_id"], path.stem)
            self.assertGreaterEqual(len(loaded.get("choices") or []), 2)

    def test_list_scenarios_covers_every_public_file(self):
        on_disk = {p.stem for p in _public_pack_paths()}
        listed = {
            item.get("scenario_id")
            for item in list_scenarios()
            if item.get("scenario_id")
        }
        self.assertEqual(on_disk, listed)

    def test_catalog_matches_public_packs(self):
        """Catalog rows ↔ public pack choices (no orphan rows, no missing cuts).

        Prevents half-shipped packs (scenario JSON without catalog/library rows
        or social draft targets that cannot render). Public ELO only.
        """
        self.assertTrue(CATALOG.is_file(), "webapp/data/catalog.json missing")
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        videos = catalog.get("videos") or []
        self.assertGreaterEqual(len(videos), 4)

        packs: dict[str, dict[str, dict]] = {}
        for path in _public_pack_paths():
            data = validate_scenario(json.loads(path.read_text(encoding="utf-8")))
            sid = data["scenario_id"]
            packs[sid] = {c["id"]: c for c in data["choices"]}

        seen: set[tuple[str, str]] = set()
        for v in videos:
            self.assertIsInstance(v, dict)
            sid = v.get("scenario_id")
            cid = v.get("choice_id")
            vid = v.get("id")
            self.assertTrue(sid and cid and vid, f"incomplete catalog row: {v!r}")
            self.assertIn(sid, packs, f"catalog {vid} references unknown pack {sid}")
            self.assertIn(cid, packs[sid], f"catalog {vid} unknown choice {cid}")
            self.assertEqual(
                vid,
                f"{sid}-{cid}",
                f"catalog id must be scenario_id-choice_id (got {vid})",
            )
            fpath = v.get("file") or ""
            self.assertTrue(
                fpath.startswith(f"{vid}/"),
                f"catalog file for {vid} should live under {vid}/ (got {fpath!r})",
            )
            pack_level = packs[sid][cid].get("speculation_level")
            cat_level = v.get("speculation")
            if cat_level is not None and pack_level is not None:
                self.assertEqual(
                    cat_level,
                    pack_level,
                    f"{vid} speculation mismatch catalog={cat_level} pack={pack_level}",
                )
            seen.add((sid, cid))

        missing = []
        for sid, choices in packs.items():
            for cid in choices:
                if (sid, cid) not in seen:
                    missing.append(f"{sid}-{cid}")
        self.assertEqual(
            missing,
            [],
            f"public pack choices missing from catalog: {missing}",
        )

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
