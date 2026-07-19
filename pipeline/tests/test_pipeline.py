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
    def test_three_packs_present(self):
        ids = {s["scenario_id"] for s in list_scenarios()}
        self.assertTrue({"ELO-001", "ELO-003", "ELO-013"}.issubset(ids))

    def test_schema_fields(self):
        for sid in ("ELO-001", "ELO-003", "ELO-013"):
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
        with tempfile.TemporaryDirectory() as td:
            result = render_video(
                "ELO-013",
                choice_id="historical",
                out_dir=Path(td) / "out",
                cfg=cfg,
                use_llm=False,
            )
            self.assertTrue(result.out_mp4.exists())
            self.assertGreater(result.out_mp4.stat().st_size, 1000)
            self.assertTrue(result.script_path.exists())
            meta = json.loads((Path(td) / "out" / "build.json").read_text())
            self.assertEqual(meta["scenario_id"], "ELO-013")


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
