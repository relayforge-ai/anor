"""TTSClient backend selection, clipping, and mock fallback (no live TTS)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.clients import PipelineError, TTSClient, healthcheck  # noqa: E402
from pipeline.config import PipelineConfig  # noqa: E402


def _cfg(**kwargs) -> PipelineConfig:
    base = dict(
        llm_url=None,
        image_url=None,
        tts_url=None,
        llm_api_key=None,
        image_api_key=None,
        tts_api_key=None,
        llm_model="m",
        image_model="m",
        tts_model="tts-1",
        image_backend="auto",
        tts_backend="auto",
        mock_media=False,
        style_prefix="",
    )
    base.update(kwargs)
    return PipelineConfig(**base)


class TestTtsBackendSelection(unittest.TestCase):
    def test_mock_when_mock_media(self):
        c = TTSClient(_cfg(tts_url="http://127.0.0.1:8880/v1", mock_media=True))
        self.assertEqual(c._backend(), "mock")

    def test_auto_openai_v1(self):
        c = TTSClient(_cfg(tts_url="http://127.0.0.1:8880/v1"))
        self.assertEqual(c._backend(), "openai_audio")

    def test_auto_http_wav(self):
        c = TTSClient(_cfg(tts_url="http://127.0.0.1:9000/tts"))
        self.assertEqual(c._backend(), "http_wav")

    def test_system_when_no_url(self):
        c = TTSClient(_cfg(tts_url=None))
        self.assertEqual(c._backend(), "system")


class TestTtsSynthesize(unittest.TestCase):
    def test_empty_text_rejected(self):
        with self.assertRaises(PipelineError):
            TTSClient(_cfg(mock_media=True)).synthesize("  ", Path("/tmp/x.wav"))

    def test_clip_text(self):
        prev = os.environ.get("ANOR_TTS_MAX_CHARS")
        os.environ["ANOR_TTS_MAX_CHARS"] = "20"
        try:
            clipped = TTSClient._clip_text("x" * 100)
            self.assertEqual(len(clipped), 20)
        finally:
            if prev is None:
                os.environ.pop("ANOR_TTS_MAX_CHARS", None)
            else:
                os.environ["ANOR_TTS_MAX_CHARS"] = prev

    def test_mock_writes_wav(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "vo.wav"
            path = TTSClient(_cfg(mock_media=True)).synthesize(
                "Documented baseline narration.", out
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 100)
            self.assertTrue(str(path).endswith(".wav"))

    def test_remote_failure_falls_back_to_silent(self):
        cfg = _cfg(tts_url="http://tts.local/v1", tts_backend="openai_audio")
        client = TTSClient(cfg)
        prev = os.environ.get("ANOR_TTS_FALLBACK_MOCK")
        os.environ["ANOR_TTS_FALLBACK_MOCK"] = "1"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "fb.wav"
                with patch("pipeline.clients._request_bytes") as rb:
                    rb.side_effect = PipelineError("upstream 503", retryable=True)
                    path = client.synthesize("hello world narration", out)
                self.assertTrue(path.is_file())
                self.assertTrue(path.with_suffix(".fallback.txt").is_file())
        finally:
            if prev is None:
                os.environ.pop("ANOR_TTS_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_TTS_FALLBACK_MOCK"] = prev

    def test_strict_no_fallback_raises(self):
        cfg = _cfg(tts_url="http://tts.local/v1", tts_backend="openai_audio")
        client = TTSClient(cfg)
        prev = os.environ.get("ANOR_TTS_FALLBACK_MOCK")
        os.environ["ANOR_TTS_FALLBACK_MOCK"] = "0"
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td) / "strict.wav"
                with patch("pipeline.clients._request_bytes") as rb:
                    rb.side_effect = PipelineError("upstream 503", retryable=True)
                    with self.assertRaises(PipelineError):
                        client.synthesize("hello", out)
        finally:
            if prev is None:
                os.environ.pop("ANOR_TTS_FALLBACK_MOCK", None)
            else:
                os.environ["ANOR_TTS_FALLBACK_MOCK"] = prev


class TestHealthTts(unittest.TestCase):
    def test_health_reports_tts_fallback(self):
        os.environ["ANOR_MOCK_MEDIA"] = "1"
        h = healthcheck(PipelineConfig.from_env())
        self.assertIn("tts_backend", h)
        self.assertIn("tts_fallback_mock", h)


if __name__ == "__main__":
    unittest.main()
