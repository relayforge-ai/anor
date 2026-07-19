"""ImageClient backend selection, mock path, and remote fallback (no live GPU)."""

from __future__ import annotations

import base64
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
        image_model="local-image",
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
        # No secrets
        blob = str(h)
        self.assertNotIn("sk-", blob)


if __name__ == "__main__":
    unittest.main()
