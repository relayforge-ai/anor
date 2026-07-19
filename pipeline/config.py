"""Endpoint configuration from environment.

Required pattern (sovereign-first):
  LLM_URL   — OpenAI-compatible chat completions base, e.g. http://dawes:11434/v1
  IMAGE_URL — image generation endpoint (ComfyUI root or OpenAI-compatible images)
  TTS_URL   — text-to-speech endpoint (OpenAI-compatible audio or local TTS bridge)

Optional:
  LLM_API_KEY / IMAGE_API_KEY / TTS_API_KEY  — bearer tokens if needed
  LLM_MODEL / IMAGE_MODEL / TTS_MODEL        — model ids
  IMAGE_BACKEND — "openai_images" | "comfy" | "mock" (default: auto)
  TTS_BACKEND   — "openai_audio" | "http_wav" | "system" | "mock" (default: auto)
  ANOR_MOCK_MEDIA — if "1", never call remote media (deterministic offline)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


@dataclass(frozen=True)
class PipelineConfig:
    llm_url: Optional[str]
    image_url: Optional[str]
    tts_url: Optional[str]
    llm_api_key: Optional[str]
    image_api_key: Optional[str]
    tts_api_key: Optional[str]
    llm_model: str
    image_model: str
    tts_model: str
    image_backend: str
    tts_backend: str
    mock_media: bool
    style_prefix: str

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        mock = _env("ANOR_MOCK_MEDIA", "0") in ("1", "true", "TRUE", "yes")
        return cls(
            llm_url=_env("LLM_URL"),
            image_url=_env("IMAGE_URL"),
            tts_url=_env("TTS_URL"),
            llm_api_key=_env("LLM_API_KEY") or _env("OPENAI_API_KEY") or _env("XAI_API_KEY"),
            image_api_key=_env("IMAGE_API_KEY") or _env("LLM_API_KEY"),
            tts_api_key=_env("TTS_API_KEY") or _env("LLM_API_KEY"),
            llm_model=_env("LLM_MODEL", "local-model") or "local-model",
            image_model=_env("IMAGE_MODEL", "local-image") or "local-image",
            tts_model=_env("TTS_MODEL", "tts-1") or "tts-1",
            image_backend=_env("IMAGE_BACKEND", "auto") or "auto",
            tts_backend=_env("TTS_BACKEND", "auto") or "auto",
            mock_media=mock,
            style_prefix=_env(
                "ANOR_STYLE_PREFIX",
                "painterly historical documentary still, cinematic composition, no text, no watermark, ",
            )
            or "",
        )

    def describe(self) -> dict:
        """Safe for logs/README — never includes secret values."""
        return {
            "llm_url": self.llm_url or "(unset — fork LLM disabled)",
            "image_url": self.image_url or "(unset — image mock/placeholder)",
            "tts_url": self.tts_url or "(unset — system/mock TTS)",
            "llm_model": self.llm_model,
            "image_model": self.image_model,
            "tts_model": self.tts_model,
            "image_backend": self.image_backend,
            "tts_backend": self.tts_backend,
            "mock_media": self.mock_media,
            "llm_api_key_set": bool(self.llm_api_key),
            "image_api_key_set": bool(self.image_api_key),
            "tts_api_key_set": bool(self.tts_api_key),
        }
