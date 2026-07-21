"""ImageClient backend selection, mock path, and remote fallback (no live GPU)."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.clients import ImageClient, PipelineError, healthcheck  # noqa: E402
from pipeline.config import PipelineConfig  # noqa: E402

# Default unit tests must not share still-cache state with each other or the host.
os.environ.setdefault("ANOR_STILL_CACHE", "0")

# 1x1 PNG
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _cfg(**kwargs) -> PipelineConfig:
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
        mock_media=False,
        style_prefix="STYLE:",
    )
    base.update(kwargs)
    return PipelineConfig(**base)


class TestImageBackendSelection(unittest.TestCase):
    def test_mock_when_no_url(self):
        self.assertEqual(ImageClient(_cfg())._backend(), "mock")

    def test_mock_when_mock_media(self):
        c = ImageClient(_cfg(image_url="http://127.0.0.1:8188", mock_media=True))
        self.assertEqual(c._backend(), "mock")

    def test_auto_openai_v1_suffix(self):
        c = ImageClient(_cfg(image_url="http://127.0.0.1:8000/v1"))
        self.assertEqual(c._backend(), "openai_images")

    def test_auto_openai_generations_path(self):
        c = ImageClient(
            _cfg(image_url="http://127.0.0.1:8000/v1/images/generations")
        )
        self.assertEqual(c._backend(), "openai_images")

    def test_auto_comfy_root(self):
        c = ImageClient(_cfg(image_url="http://127.0.0.1:8188"))
        self.assertEqual(c._backend(), "comfy")

    def test_explicit_backend_override(self):
        c = ImageClient(
            _cfg(image_url="http://127.0.0.1:8188", image_backend="openai_images")
        )
        self.assertEqual(c._backend(), "openai_images")


class TestImageGenerate(unittest.TestCase):
    def test_mock_writes_png(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "still.png"
            path = ImageClient(_cfg(mock_media=True, style_prefix="PRE:")).generate(
                "battlefield", out, width=64, height=36
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 20)
            # Style prefix applied to sidecar prompt
            prompt_side = path.with_suffix(".prompt.txt")
            self.assertTrue(prompt_side.is_file())
            self.assertTrue(prompt_side.read_text().startswith("PRE:"))

    def test_openai_b64_json_path(self):
        cfg = _cfg(image_url="http://img.local/v1", image_backend="openai_images")
        client = ImageClient(cfg)
        prev = os.environ.get("ANOR_IMAGE_FALLBACK_MOCK")
        os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = "0"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "gen.png"
                with patch("pipeline.clients._request_json") as rj:
                    rj.return_value = {
                        "data": [
                            {
                                "b64_json": base64.b64encode(_TINY_PNG).decode(
                                    "ascii"
                                )
                            }
                        ]
                    }
                    path = client.generate("prompt", out)
                self.assertEqual(path.read_bytes(), _TINY_PNG)
                self.assertTrue(rj.called)
                # Request went to .../images/generations
                url = rj.call_args[0][0]
                self.assertIn("/images/generations", url)
        finally:
            if prev is None:
                os.environ.pop("ANOR_IMAGE_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = prev

    def test_remote_failure_falls_back_to_mock(self):
        cfg = _cfg(image_url="http://img.local/v1", image_backend="openai_images")
        client = ImageClient(cfg)
        prev = os.environ.get("ANOR_IMAGE_FALLBACK_MOCK")
        os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "fb.png"
                with patch("pipeline.clients._request_json") as rj:
                    rj.side_effect = PipelineError("upstream 503", retryable=True)
                    path = client.generate("prompt", out)
                self.assertTrue(path.is_file())
                self.assertTrue(path.with_suffix(".fallback.txt").is_file())
        finally:
            if prev is None:
                os.environ.pop("ANOR_IMAGE_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = prev

    def test_ssrf_rejection_does_not_fallback(self):
        cfg = _cfg(image_url="http://img.local/v1", image_backend="openai_images")
        client = ImageClient(cfg)
        prev = os.environ.get("ANOR_IMAGE_FALLBACK_MOCK")
        os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "bad.png"
                with patch("pipeline.clients._request_json") as rj:
                    rj.return_value = {"data": [{"url": "file:///etc/passwd"}]}
                    with self.assertRaises(PipelineError) as ctx:
                        client.generate("prompt", out)
                self.assertIn("Rejected", str(ctx.exception))
                self.assertFalse(out.with_suffix(".fallback.txt").is_file())
        finally:
            if prev is None:
                os.environ.pop("ANOR_IMAGE_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = prev


class TestHealthImageBackend(unittest.TestCase):
    def test_health_reports_backends(self):
        os.environ["ANOR_MOCK_MEDIA"] = "1"
        h = healthcheck(PipelineConfig.from_env())
        self.assertIn(h["image_backend"], ("mock", "openai_images", "comfy"))
        self.assertIn("image_fallback_mock", h)
        self.assertIn("tts_backend", h)
        self.assertIn("image_still_size", h)
        self.assertEqual(len(h["image_still_size"]), 2)
        self.assertIn("image_upscale", h)
        self.assertIn("video_frame_size", h)
        self.assertEqual(h["video_frame_size"], [1920, 1080])
        self.assertIn("clip_cache", h)
        # No secrets
        blob = str(h)
        self.assertNotIn("sk-", blob)


class TestStillCache(unittest.TestCase):
    def test_cache_key_stable_and_sensitive(self):
        k1 = ImageClient.still_cache_key(
            full_prompt="a",
            width=1024,
            height=576,
            backend="comfy",
            image_model="sd_xl_base_1.0.safetensors",
            upscale=True,
            upscale_model="RealESRGAN_x4plus.pth",
            quality="s25|c7.000|euler|normal",
        )
        k2 = ImageClient.still_cache_key(
            full_prompt="a",
            width=1024,
            height=576,
            backend="comfy",
            image_model="sd_xl_base_1.0.safetensors",
            upscale=True,
            upscale_model="RealESRGAN_x4plus.pth",
            quality="s25|c7.000|euler|normal",
        )
        k3 = ImageClient.still_cache_key(
            full_prompt="b",
            width=1024,
            height=576,
            backend="comfy",
            image_model="sd_xl_base_1.0.safetensors",
            upscale=True,
            upscale_model="RealESRGAN_x4plus.pth",
            quality="s25|c7.000|euler|normal",
        )
        k4 = ImageClient.still_cache_key(
            full_prompt="a",
            width=1024,
            height=576,
            backend="comfy",
            image_model="sd_xl_base_1.0.safetensors",
            upscale=True,
            upscale_model="RealESRGAN_x4plus.pth",
            quality="s30|c7.000|euler|normal",
        )
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertNotEqual(k1, k4)
        self.assertEqual(len(k1), 28)

    def test_comfy_quality_fingerprint_tracks_env(self):
        prev = {
            k: os.environ.get(k)
            for k in (
                "ANOR_COMFY_STEPS",
                "ANOR_COMFY_CFG",
                "ANOR_COMFY_SAMPLER",
                "ANOR_COMFY_SCHEDULER",
            )
        }
        try:
            os.environ["ANOR_COMFY_STEPS"] = "25"
            os.environ["ANOR_COMFY_CFG"] = "7.0"
            os.environ["ANOR_COMFY_SAMPLER"] = "euler"
            os.environ["ANOR_COMFY_SCHEDULER"] = "normal"
            a = ImageClient.comfy_quality_fingerprint()
            os.environ["ANOR_COMFY_STEPS"] = "30"
            b = ImageClient.comfy_quality_fingerprint()
            self.assertNotEqual(a, b)
            self.assertIn("s25", a)
            self.assertIn("s30", b)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_mock_cache_hit_skips_second_generate_work(self):
        prev = {
            k: os.environ.get(k)
            for k in ("ANOR_STILL_CACHE", "ANOR_STILL_CACHE_MOCK", "ANOR_STILL_CACHE_DIR")
        }
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td) / "cache"
            os.environ["ANOR_STILL_CACHE"] = "1"
            os.environ["ANOR_STILL_CACHE_MOCK"] = "1"
            os.environ["ANOR_STILL_CACHE_DIR"] = str(cache_dir)
            try:
                client = ImageClient(_cfg(mock_media=True, style_prefix="PRE:"))
                out1 = Path(td) / "a" / "still.png"
                out2 = Path(td) / "b" / "still.png"
                p1 = client.generate("battlefield", out1, width=64, height=36)
                self.assertTrue(p1.is_file())
                # Cache should hold one png
                cached = list(cache_dir.glob("*.png"))
                self.assertEqual(len(cached), 1)
                p2 = client.generate("battlefield", out2, width=64, height=36)
                self.assertTrue(p2.is_file())
                self.assertTrue(p2.with_suffix(".cache.txt").is_file())
                self.assertEqual(p1.read_bytes(), p2.read_bytes())
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


class TestComfyWorkflow(unittest.TestCase):
    def test_workflow_includes_sdxl_ckpt_and_realesrgan(self):
        wf = ImageClient.build_comfy_workflow(
            "sepia battlefield, film grain",
            ckpt="sd_xl_base_1.0.safetensors",
            width=1024,
            height=576,
            seed=42,
            steps=20,
            upscale=True,
            upscale_model="RealESRGAN_x4plus.pth",
        )
        self.assertEqual(wf["1"]["inputs"]["ckpt_name"], "sd_xl_base_1.0.safetensors")
        self.assertEqual(wf["4"]["inputs"]["width"], 1024)
        self.assertEqual(wf["4"]["inputs"]["height"], 576)
        self.assertEqual(wf["8"]["class_type"], "UpscaleModelLoader")
        self.assertEqual(wf["8"]["inputs"]["model_name"], "RealESRGAN_x4plus.pth")
        self.assertEqual(wf["9"]["class_type"], "ImageUpscaleWithModel")
        # SaveImage reads upscaled node, not raw VAE
        self.assertEqual(wf["7"]["inputs"]["images"], ["9", 0])

    def test_workflow_can_skip_upscale(self):
        wf = ImageClient.build_comfy_workflow(
            "x",
            ckpt="sd_xl_base_1.0.safetensors",
            width=512,
            height=512,
            upscale=False,
        )
        self.assertNotIn("8", wf)
        self.assertNotIn("9", wf)
        self.assertEqual(wf["7"]["inputs"]["images"], ["6", 0])

    def test_resolve_ckpt_defaults_to_sdxl(self):
        self.assertEqual(
            ImageClient.resolve_comfy_ckpt("local-image"),
            "sd_xl_base_1.0.safetensors",
        )

    def test_reject_flux_dev(self):
        with self.assertRaises(PipelineError) as ctx:
            ImageClient.resolve_comfy_ckpt("flux1-dev.safetensors")
        self.assertIn("non-commercial", str(ctx.exception).lower())

    def test_still_size_multiples_of_eight(self):
        prev_w = os.environ.get("ANOR_STILL_WIDTH")
        prev_h = os.environ.get("ANOR_STILL_HEIGHT")
        os.environ["ANOR_STILL_WIDTH"] = "1000"
        os.environ["ANOR_STILL_HEIGHT"] = "575"
        try:
            w, h = ImageClient.still_size()
            self.assertEqual(w % 8, 0)
            self.assertEqual(h % 8, 0)
            self.assertEqual((w, h), (1000 // 8 * 8, 575 // 8 * 8))
        finally:
            if prev_w is None:
                os.environ.pop("ANOR_STILL_WIDTH", None)
            else:
                os.environ["ANOR_STILL_WIDTH"] = prev_w
            if prev_h is None:
                os.environ.pop("ANOR_STILL_HEIGHT", None)
            else:
                os.environ["ANOR_STILL_HEIGHT"] = prev_h

    def test_comfy_path_uses_serialized_lock_and_polls(self):
        """Comfy generate posts workflow once and fetches view (no live GPU)."""
        cfg = _cfg(image_url="http://127.0.0.1:8188", image_backend="comfy")
        client = ImageClient(cfg)
        prev = os.environ.get("ANOR_IMAGE_FALLBACK_MOCK")
        os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = "0"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "comfy.png"
                with patch("pipeline.clients._request_json") as rj, patch(
                    "pipeline.clients._request_bytes"
                ) as rb, patch(
                    "pipeline.clients.safe_get_bytes", return_value=_TINY_PNG
                ) as sg:
                    rj.return_value = {"prompt_id": "pid-1"}
                    rb.return_value = json.dumps(
                        {
                            "pid-1": {
                                "status": {"status_str": "success", "completed": True},
                                "outputs": {
                                    "7": {
                                        "images": [
                                            {
                                                "filename": "anor_00001_.png",
                                                "subfolder": "",
                                                "type": "output",
                                            }
                                        ]
                                    }
                                },
                            }
                        }
                    ).encode("utf-8")
                    path = client.generate("battlefield archival", out, width=64, height=64)
                self.assertEqual(path.read_bytes(), _TINY_PNG)
                # Workflow posted to /prompt
                self.assertTrue(rj.called)
                posted = rj.call_args[0][1]["prompt"]
                self.assertEqual(
                    posted["1"]["inputs"]["ckpt_name"],
                    "sd_xl_base_1.0.safetensors",
                )
                self.assertIn("8", posted)  # upscale loader
                self.assertTrue(sg.called)
        finally:
            if prev is None:
                os.environ.pop("ANOR_IMAGE_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_IMAGE_FALLBACK_MOCK"] = prev


class TestKenBurns(unittest.TestCase):
    def test_filter_targets_1080p_and_preserves_headroom_hint(self):
        from pipeline.video_pipeline import ken_burns_filter, video_frame_size

        prev = {
            k: os.environ.get(k)
            for k in ("ANOR_VIDEO_WIDTH", "ANOR_VIDEO_HEIGHT")
        }
        os.environ.pop("ANOR_VIDEO_WIDTH", None)
        os.environ.pop("ANOR_VIDEO_HEIGHT", None)
        try:
            self.assertEqual(video_frame_size(), (1920, 1080))
            vf = ken_burns_filter(5.0)
            self.assertIn("1920x1080", vf)
            self.assertIn("zoompan", vf)
            # Must not pre-crop to frame size (old 720p path)
            self.assertNotIn("crop=1280:720", vf)
            self.assertNotIn("s=1280x720", vf)
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_ken_burns_clip_writes_1080p(self):
        """End-to-end ffmpeg Ken Burns on a mock still (offline)."""
        import subprocess
        import tempfile

        from pipeline.video_pipeline import _ken_burns_clip

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            still = td_path / "still.png"
            audio = td_path / "vo.wav"
            clip = td_path / "out.mp4"
            # Larger-than-frame solid so zoom has pixels
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=0x3a2a1a:s=2048x1152:d=1",
                    "-frames:v",
                    "1",
                    str(still),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-t",
                    "1.0",
                    str(audio),
                ],
                check=True,
                capture_output=True,
            )
            prev = {
                k: os.environ.get(k)
                for k in ("ANOR_VIDEO_WIDTH", "ANOR_VIDEO_HEIGHT")
            }
            os.environ["ANOR_VIDEO_WIDTH"] = "640"
            os.environ["ANOR_VIDEO_HEIGHT"] = "360"
            try:
                _ken_burns_clip(still, audio, clip, duration=1.0)
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertTrue(clip.is_file())
            self.assertGreater(clip.stat().st_size, 500)
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0",
                    str(clip),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(probe.stdout.strip(), "640,360")


class TestClipCache(unittest.TestCase):
    """Content-addressed Ken Burns mux cache (skip ffmpeg on still+audio match)."""

    def _make_still_audio(self, td: Path) -> tuple[Path, Path]:
        import subprocess

        still = td / "still.png"
        audio = td / "vo.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x3a2a1a:s=640x360:d=1",
                "-frames:v",
                "1",
                str(still),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.5",
                str(audio),
            ],
            check=True,
            capture_output=True,
        )
        return still, audio

    def test_clip_cache_key_stable(self):
        from pipeline.video_pipeline import clip_cache_key

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            still, audio = self._make_still_audio(td_path)
            k1 = clip_cache_key(
                still, audio, duration_s=0.5, width=640, height=360
            )
            k2 = clip_cache_key(
                still, audio, duration_s=0.5, width=640, height=360
            )
            k3 = clip_cache_key(
                still, audio, duration_s=1.0, width=640, height=360
            )
            self.assertEqual(k1, k2)
            self.assertNotEqual(k1, k3)
            self.assertEqual(len(k1), 28)

    def test_clip_cache_key_tracks_ken_burns_quality(self):
        from pipeline.video_pipeline import (
            clip_cache_key,
            ken_burns_quality_fingerprint,
        )

        prev = {
            k: os.environ.get(k)
            for k in (
                "ANOR_VIDEO_FPS",
                "ANOR_KB_ZOOM_MAX",
                "ANOR_KB_ZOOM_DELTA",
                "ANOR_KB_MIN_SCALE",
            )
        }
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            still, audio = self._make_still_audio(td_path)
            try:
                os.environ["ANOR_VIDEO_FPS"] = "30"
                os.environ["ANOR_KB_ZOOM_MAX"] = "1.15"
                os.environ["ANOR_KB_ZOOM_DELTA"] = "0.15"
                os.environ["ANOR_KB_MIN_SCALE"] = "2"
                q1 = ken_burns_quality_fingerprint()
                k1 = clip_cache_key(
                    still, audio, duration_s=0.5, width=640, height=360, quality=q1
                )
                os.environ["ANOR_KB_ZOOM_MAX"] = "1.25"
                q2 = ken_burns_quality_fingerprint()
                k2 = clip_cache_key(
                    still, audio, duration_s=0.5, width=640, height=360, quality=q2
                )
                self.assertNotEqual(q1, q2)
                self.assertNotEqual(k1, k2)
                self.assertIn("z1.150", q1)
                self.assertIn("z1.250", q2)
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_clip_cache_hit_skips_ffmpeg(self):
        from pipeline.video_pipeline import _ken_burns_clip

        prev = {
            k: os.environ.get(k)
            for k in (
                "ANOR_CLIP_CACHE",
                "ANOR_CLIP_CACHE_DIR",
                "ANOR_VIDEO_WIDTH",
                "ANOR_VIDEO_HEIGHT",
            )
        }
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cache_dir = td_path / "ccache"
            still, audio = self._make_still_audio(td_path)
            os.environ["ANOR_CLIP_CACHE"] = "1"
            os.environ["ANOR_CLIP_CACHE_DIR"] = str(cache_dir)
            os.environ["ANOR_VIDEO_WIDTH"] = "320"
            os.environ["ANOR_VIDEO_HEIGHT"] = "180"
            try:
                out1 = td_path / "a" / "clip.mp4"
                out2 = td_path / "b" / "clip.mp4"
                p1 = _ken_burns_clip(still, audio, out1, duration=0.5)
                self.assertTrue(p1.is_file())
                self.assertGreater(p1.stat().st_size, 500)
                self.assertEqual(len(list(cache_dir.glob("*.mp4"))), 1)
                # First encode should not write a hit sidecar
                self.assertFalse(out1.with_suffix(".cache.txt").is_file())

                # Second call: still+audio fingerprint match → copy from cache
                # (prove via sidecar; also guard that ffmpeg encode is not re-run)
                import subprocess as _sp

                real_run = _sp.run
                encode_calls: list[list] = []

                def _track(*args, **kwargs):
                    cmd = list(args[0]) if args else list(kwargs.get("args") or [])
                    if cmd and Path(str(cmd[0])).name == "ffmpeg":
                        # Only count encode (has -vf / zoompan path), not still/audio gens
                        if any(a == "-vf" for a in cmd):
                            encode_calls.append(cmd)
                            raise AssertionError(
                                "ffmpeg encode must not run on clip cache hit"
                            )
                    return real_run(*args, **kwargs)

                with patch(
                    "pipeline.video_pipeline.subprocess.run",
                    side_effect=_track,
                ):
                    p2 = _ken_burns_clip(still, audio, out2, duration=0.5)
                self.assertTrue(p2.is_file())
                self.assertEqual(p1.read_bytes(), p2.read_bytes())
                self.assertTrue(out2.with_suffix(".cache.txt").is_file())
                note = out2.with_suffix(".cache.txt").read_text(encoding="utf-8")
                self.assertIn("clip_cache_hit", note)
                self.assertEqual(encode_calls, [])
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def test_clip_cache_disabled_encodes(self):
        from pipeline.video_pipeline import _ken_burns_clip

        prev = {
            k: os.environ.get(k)
            for k in (
                "ANOR_CLIP_CACHE",
                "ANOR_CLIP_CACHE_DIR",
                "ANOR_VIDEO_WIDTH",
                "ANOR_VIDEO_HEIGHT",
            )
        }
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cache_dir = td_path / "ccache"
            still, audio = self._make_still_audio(td_path)
            os.environ["ANOR_CLIP_CACHE"] = "0"
            os.environ["ANOR_CLIP_CACHE_DIR"] = str(cache_dir)
            os.environ["ANOR_VIDEO_WIDTH"] = "320"
            os.environ["ANOR_VIDEO_HEIGHT"] = "180"
            try:
                out = td_path / "clip.mp4"
                p = _ken_burns_clip(still, audio, out, duration=0.5)
                self.assertTrue(p.is_file())
                self.assertEqual(len(list(cache_dir.glob("*.mp4"))), 0)
            finally:
                for k, v in prev.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
