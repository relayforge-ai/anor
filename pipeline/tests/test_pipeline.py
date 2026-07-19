"""Offline tests — no network, no secrets."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Force mock media for CI
os.environ["ANOR_MOCK_MEDIA"] = "1"
os.environ.pop("LLM_URL", None)
os.environ.pop("IMAGE_URL", None)
os.environ.pop("TTS_URL", None)

from pipeline.config import PipelineConfig
from pipeline.fork_engine import list_scenarios, run_fork, scenario_payload, load_scenario
from pipeline.video_pipeline import build_script, render_video


class TestPublicPacks(unittest.TestCase):
    def test_core_packs_present(self):
        ids = {s["scenario_id"] for s in list_scenarios()}
        self.assertTrue(
            {
                "ELO-001",
                "ELO-003",
                "ELO-004",
                "ELO-005",
                "ELO-006",
                "ELO-007",
                "ELO-009",
                "ELO-013",
            }.issubset(ids),
            f"missing core packs; have {sorted(ids)}",
        )

    def test_schema_fields(self):
        # Validate every public pack on disk (not a hardcoded trio)
        ids = sorted(s["scenario_id"] for s in list_scenarios())
        self.assertGreaterEqual(len(ids), 4)
        for sid in ids:
            s = load_scenario(sid)
            self.assertIn("known_outcome", s)
            self.assertIn("decision_question", s)
            self.assertGreaterEqual(len(s["choices"]), 2)
            hist = [c for c in s["choices"] if c.get("is_historical")]
            self.assertEqual(len(hist), 1, f"{sid} needs exactly one historical choice")
            for c in s["choices"]:
                self.assertIn(c["speculation_level"], ("documented", "dramatized", "simulated"))
                if c.get("is_historical"):
                    self.assertEqual(c["speculation_level"], "documented")

    def test_elo_007_quarantine_is_documented_historical(self):
        r = run_fork("ELO-007", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        self.assertIn("quarantine", r.narrative.lower() + r.label.lower())

    def test_elo_007_strike_is_simulated(self):
        r = run_fork("ELO-007", "surgical_strike", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")

    def test_elo_009_halt_is_documented_historical(self):
        r = run_fork("ELO-009", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        blob = (r.narrative + r.label).lower()
        self.assertTrue("halt" in blob or "dunkirk" in blob or "dynamo" in blob)

    def test_elo_009_press_armor_is_simulated(self):
        r = run_fork("ELO-009", "press_armor", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")

    def test_elo_004_cross_is_documented_historical(self):
        r = run_fork("ELO-004", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        blob = (r.narrative + r.label).lower()
        self.assertTrue("cross" in blob or "rubicon" in blob or "civil" in blob)

    def test_elo_004_stand_down_is_simulated(self):
        r = run_fork("ELO-004", "stand_down", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")

    def test_elo_005_blank_cheque_is_documented_historical(self):
        r = run_fork("ELO-005", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        blob = (r.narrative + r.label).lower()
        self.assertTrue(
            "blank" in blob or "cheque" in blob or "check" in blob or "vienna" in blob
            or "support" in blob
        )

    def test_elo_005_restrain_is_simulated(self):
        r = run_fork("ELO-005", "restrain", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")

    def test_elo_006_airlift_is_documented_historical(self):
        r = run_fork("ELO-006", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        blob = (r.narrative + r.label).lower()
        self.assertTrue("airlift" in blob or "air" in blob or "berlin" in blob)

    def test_elo_006_force_corridors_is_simulated(self):
        r = run_fork("ELO-006", "force_corridors", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")

    def test_payload_hides_nothing_required(self):
        p = scenario_payload("ELO-003")
        self.assertEqual(p["scenario_id"], "ELO-003")
        self.assertTrue(p["choices"])

    def test_list_scenarios_no_host_paths(self):
        for item in list_scenarios():
            self.assertNotIn("path", item)
            self.assertNotIn(str(ROOT), json.dumps(item))


class TestForkEngine(unittest.TestCase):
    def test_historical_fork_authored(self):
        r = run_fork("ELO-003", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        self.assertEqual(r.source, "authored")
        self.assertIn("Cannae", r.narrative)

    def test_counterfactual_labeled(self):
        r = run_fork("ELO-013", "launch", use_llm=False)
        self.assertFalse(r.is_historical)
        self.assertEqual(r.speculation_level, "simulated")
        self.assertIn("SPECULATION", r.narrative.upper() + r.label.upper() + "SIMULATED")


class TestVideoPipeline(unittest.TestCase):
    def test_build_script_tags(self):
        s = load_scenario("ELO-003")
        segs = build_script(s, "march", "n/a")
        self.assertEqual(len(segs), 4)
        self.assertEqual(segs[0]["tag"], "documented")
        self.assertEqual(segs[2]["tag"], "simulated")

    def test_render_mock_mp4(self):
        cfg = PipelineConfig.from_env()
        # Ensure default cleanup path
        os.environ.pop("ANOR_KEEP_VIDEO_WORK", None)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            result = render_video(
                "ELO-013",
                choice_id="historical",
                out_dir=out,
                cfg=cfg,
                use_llm=False,
            )
            self.assertTrue(result.out_mp4.exists())
            self.assertGreater(result.out_mp4.stat().st_size, 1000)
            self.assertTrue(result.script_path.exists())
            meta = json.loads((out / "build.json").read_text())
            self.assertEqual(meta["scenario_id"], "ELO-013")
            self.assertTrue(meta.get("work_cleaned"))
            # Intermediate work/ and concat list must be gone after success
            self.assertFalse((out / "work").exists())
            self.assertFalse(result.out_mp4.with_suffix(".txt").exists())
            # No absolute host paths in build.json (path leak hygiene)
            blob = json.dumps(meta)
            self.assertNotIn(str(td), blob)
            self.assertNotIn(str(ROOT), blob)
            for seg in meta.get("segments") or []:
                for key in ("image", "audio", "clip"):
                    val = seg.get(key) or ""
                    self.assertNotIn("/", val)
                    self.assertNotIn("\\", val)

    def test_render_keep_work_when_flagged(self):
        cfg = PipelineConfig.from_env()
        prev = os.environ.get("ANOR_KEEP_VIDEO_WORK")
        os.environ["ANOR_KEEP_VIDEO_WORK"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "out"
                result = render_video(
                    "ELO-001",
                    choice_id="historical",
                    out_dir=out,
                    cfg=cfg,
                    use_llm=False,
                )
                self.assertTrue(result.out_mp4.exists())
                meta = json.loads((out / "build.json").read_text())
                self.assertFalse(meta.get("work_cleaned"))
                self.assertTrue((out / "work").is_dir())
                # At least one intermediate clip should remain
                clips = list((out / "work").glob("*.mp4"))
                self.assertGreaterEqual(len(clips), 1)
        finally:
            if prev is None:
                os.environ.pop("ANOR_KEEP_VIDEO_WORK", None)
            else:
                os.environ["ANOR_KEEP_VIDEO_WORK"] = prev

    def test_failed_render_cleans_work(self):
        """Mid-pipeline failure must not leave intermediate stills/clips on disk."""
        from unittest.mock import patch

        cfg = PipelineConfig.from_env()
        os.environ.pop("ANOR_KEEP_VIDEO_WORK", None)
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            with patch(
                "pipeline.video_pipeline._ken_burns_clip",
                side_effect=RuntimeError("simulated ffmpeg failure"),
            ):
                with self.assertRaises(RuntimeError):
                    render_video(
                        "ELO-003",
                        choice_id="historical",
                        out_dir=out,
                        cfg=cfg,
                        use_llm=False,
                    )
            self.assertFalse(
                (out / "work").exists(),
                "work/ must be removed after failed render",
            )
            # Concat list should not linger either
            self.assertFalse((out / "ELO-003-historical.txt").exists())


class TestConfig(unittest.TestCase):
    def test_no_hardcoded_hosts_in_describe(self):
        cfg = PipelineConfig.from_env()
        d = cfg.describe()
        self.assertIn("llm_url", d)
        # secret values never appear — only booleans for key presence
        blob = json.dumps(d)
        self.assertNotIn("sk-", blob)
        self.assertIsInstance(d["llm_api_key_set"], bool)


if __name__ == "__main__":
    unittest.main()
