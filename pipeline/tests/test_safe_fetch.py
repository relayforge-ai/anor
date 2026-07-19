"""SSRF / size-cap tests for secondary media fetches."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.safe_fetch import (  # noqa: E402
    max_media_bytes,
    read_response_limited,
    safe_get_bytes,
    validate_http_url,
)
from pipeline.clients import ImageClient, PipelineError  # noqa: E402
from pipeline.config import PipelineConfig  # noqa: E402


class TestValidateHttpUrl(unittest.TestCase):
    def test_allows_http_https(self):
        for u in (
            "http://dawes.local:8188/view?filename=x.png",
            "https://cdn.example.com/img.png",
        ):
            p = validate_http_url(u)
            self.assertIn(p.scheme, ("http", "https"))

    def test_rejects_file_scheme(self):
        with self.assertRaises(ValueError) as ctx:
            validate_http_url("file:///etc/passwd")
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_rejects_gopher(self):
        with self.assertRaises(ValueError):
            validate_http_url("gopher://evil/1")

    def test_rejects_empty_host(self):
        with self.assertRaises(ValueError):
            validate_http_url("http:///nohost")

    def test_rejects_userinfo(self):
        with self.assertRaises(ValueError):
            validate_http_url("http://user:pass@example.com/x")

    def test_rejects_metadata_host(self):
        with self.assertRaises(ValueError):
            validate_http_url("http://169.254.169.254/latest/meta-data/")
        with self.assertRaises(ValueError):
            validate_http_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_rejects_link_local(self):
        with self.assertRaises(ValueError):
            validate_http_url("http://169.254.1.1/x")

    def test_rejects_control_chars(self):
        with self.assertRaises(ValueError):
            validate_http_url("http://example.com/a\nb")


class TestReadLimited(unittest.TestCase):
    def test_under_limit(self):
        resp = MagicMock()
        resp.headers = {}
        resp.read = MagicMock(side_effect=[b"hello", b""])
        self.assertEqual(read_response_limited(resp, 100), b"hello")

    def test_over_limit(self):
        resp = MagicMock()
        resp.headers = {"Content-Length": "10"}
        with self.assertRaises(ValueError) as ctx:
            read_response_limited(resp, 5)
        self.assertIn("exceeds", str(ctx.exception).lower())

    def test_stream_over_limit(self):
        resp = MagicMock()
        resp.headers = {}
        # First chunk 4 bytes, second 4 — limit 5
        resp.read = MagicMock(side_effect=[b"abcd", b"efgh", b""])
        with self.assertRaises(ValueError):
            read_response_limited(resp, 5)


class TestImageUrlFetchHardening(unittest.TestCase):
    def _cfg(self) -> PipelineConfig:
        return PipelineConfig(
            llm_url=None,
            image_url="http://img.local/v1",
            tts_url=None,
            llm_api_key=None,
            image_api_key=None,
            tts_api_key=None,
            llm_model="m",
            image_model="m",
            tts_model="m",
            image_backend="openai_images",
            tts_backend="mock",
            mock_media=False,
            style_prefix="",
        )

    def test_rejects_file_url_from_api(self):
        client = ImageClient(self._cfg())
        with patch("pipeline.clients._request_json") as rj:
            rj.return_value = {
                "data": [{"url": "file:///etc/passwd"}],
            }
            with self.assertRaises(PipelineError) as ctx:
                client.generate("test prompt", Path("/tmp/anor-test-img.png"))
            self.assertIn("Rejected", str(ctx.exception))
            self.assertFalse(ctx.exception.retryable)

    def test_rejects_metadata_url_from_api(self):
        client = ImageClient(self._cfg())
        with patch("pipeline.clients._request_json") as rj:
            rj.return_value = {
                "data": [{"url": "http://169.254.169.254/latest/meta-data/"}],
            }
            with self.assertRaises(PipelineError) as ctx:
                client.generate("test prompt", Path("/tmp/anor-test-img2.png"))
            self.assertIn("Rejected", str(ctx.exception))

    def test_safe_get_uses_no_redirect_opener(self):
        # Ensure validate is called before open
        with patch("pipeline.safe_fetch.validate_http_url") as v:
            v.side_effect = ValueError("blocked for test")
            with self.assertRaises(ValueError):
                safe_get_bytes("http://example.com/x")
            v.assert_called_once()

    def test_max_media_bytes_default_positive(self):
        self.assertGreater(max_media_bytes(), 1024)


if __name__ == "__main__":
    unittest.main()
