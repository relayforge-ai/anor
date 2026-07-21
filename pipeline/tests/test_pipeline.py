"""Offline tests — no network, no secrets."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


def _mock_cfg(**kwargs) -> PipelineConfig:
    """PipelineConfig with mock_media forced on (fleet URLs may still be set)."""
    base = dict(
        llm_url=None,
        image_url=None,
        tts_url=None,
        llm_api_key=None,
        image_api_key=None,
        tts_api_key=None,
        llm_model="m",
        image_model="sd_xl_base_1.0.safetensors",
        tts_model="m",
        image_backend="auto",
        tts_backend="auto",
        mock_media=True,
        style_prefix="STYLE:",
    )
    base.update(kwargs)
    return PipelineConfig(**base)


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
                "ELO-008",
                "ELO-009",
                "ELO-010",
                "ELO-013",
                "ELO-014",
                "ELO-015",
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

    def test_elo_008_go_is_documented_historical(self):
        r = run_fork("ELO-008", "historical", use_llm=False)
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        blob = (r.narrative + r.label).lower()
        self.assertTrue("june" in blob or "go" in blob or "normandy" in blob or "overlord" in blob)

    def test_elo_008_delay_longer_is_simulated(self):
        r = run_fork("ELO-008", "delay_longer", use_llm=False)
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
            # Deliverable metrics for ops / freemium feedback
            self.assertIn("out_mp4_bytes", meta)
            self.assertGreater(int(meta["out_mp4_bytes"]), 1000)
            self.assertEqual(meta["out_mp4_bytes"], result.out_mp4.stat().st_size)
            self.assertIn("duration_s", meta)
            self.assertGreater(float(meta["duration_s"]), 0)
            self.assertIsNotNone(result.out_mp4_bytes)
            self.assertIsNotNone(result.duration_s)
            # Cost ladder accounting (hits may be 0 under mock defaults)
            cache = meta.get("cache") or {}
            self.assertIn("still_hits", cache)
            self.assertIn("tts_hits", cache)
            self.assertIn("clip_hits", cache)
            self.assertEqual(cache.get("segments"), len(meta.get("segments") or []))
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
                self.assertIn("still_cache_hit", seg)
                self.assertIn("tts_cache_hit", seg)
                self.assertIn("clip_cache_hit", seg)
                self.assertIsInstance(seg["still_cache_hit"], bool)
                self.assertIsInstance(seg["tts_cache_hit"], bool)
                self.assertIsInstance(seg["clip_cache_hit"], bool)

    def test_render_elo015_mock_never_hits_network(self):
        """ELO-015 Appomattox + fleet URLs still must not open Comfy/TTS/LLM HTTP in mock.

        End-to-end offline guarantee for the Civil War pack social drafts target
        (batch-013): still → TTS → Ken Burns → mux with ANOR_MOCK_MEDIA discipline.
        """
        os.environ.pop("ANOR_KEEP_VIDEO_WORK", None)
        # Disable still/clip caches so generate always runs the mock path under patch
        prev_still = os.environ.get("ANOR_STILL_CACHE")
        prev_clip = os.environ.get("ANOR_CLIP_CACHE")
        prev_tts = os.environ.get("ANOR_TTS_CACHE")
        os.environ["ANOR_STILL_CACHE"] = "0"
        os.environ["ANOR_CLIP_CACHE"] = "0"
        os.environ["ANOR_TTS_CACHE"] = "0"
        cfg = _mock_cfg(
            llm_url="http://127.0.0.1:11434/v1",
            image_url="http://192.168.4.27:8188",
            tts_url="http://127.0.0.1:8880/v1",
            image_backend="comfy",
            tts_backend="openai_audio",
        )
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "elo015"
                with (
                    patch("pipeline.clients._request_json") as rj,
                    patch("pipeline.clients._request_bytes") as rb,
                    patch("pipeline.clients.safe_get_bytes") as sg,
                ):
                    result = render_video(
                        "ELO-015",
                        choice_id="historical",
                        out_dir=out,
                        cfg=cfg,
                        use_llm=False,
                    )
                    rj.assert_not_called()
                    rb.assert_not_called()
                    sg.assert_not_called()
                self.assertTrue(result.out_mp4.is_file())
                self.assertGreater(result.out_mp4.stat().st_size, 1000)
                meta = json.loads((out / "build.json").read_text(encoding="utf-8"))
                self.assertEqual(meta["scenario_id"], "ELO-015")
                self.assertEqual(meta.get("choice_id"), "historical")
                self.assertTrue(meta.get("mock_media") or cfg.mock_media)
        finally:
            if prev_still is None:
                os.environ.pop("ANOR_STILL_CACHE", None)
            else:
                os.environ["ANOR_STILL_CACHE"] = prev_still
            if prev_clip is None:
                os.environ.pop("ANOR_CLIP_CACHE", None)
            else:
                os.environ["ANOR_CLIP_CACHE"] = prev_clip
            if prev_tts is None:
                os.environ.pop("ANOR_TTS_CACHE", None)
            else:
                os.environ["ANOR_TTS_CACHE"] = prev_tts

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


class TestForkMockMedia(unittest.TestCase):
    def test_run_fork_mock_media_never_hits_llm_http(self):
        """use_llm=True + mock_media must stay authored and never call Ollama HTTP."""
        cfg = _mock_cfg(llm_url="http://127.0.0.1:11434/v1")
        with patch("pipeline.clients._request_json") as rj:
            r = run_fork("ELO-015", "historical", cfg=cfg, use_llm=True)
            rj.assert_not_called()
        self.assertTrue(r.is_historical)
        self.assertEqual(r.speculation_level, "documented")
        self.assertEqual(r.source, "authored")
        self.assertIn("generator:authored", r.provenance_ribbon)
        self.assertIn("Appomattox", r.narrative + r.label)
        self.assertGreater(len(r.narrative), 40)


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
