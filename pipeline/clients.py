"""HTTP clients for LLM / IMAGE / TTS — all hosts from env, never hardcoded."""

from __future__ import annotations

import base64
import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from .config import PipelineConfig

T = TypeVar("T")

# Retry transient upstream failures (GPU warm-up, rate limits, brief outages).
# Never retries 4xx auth/validation errors.
_RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def http_retry_config() -> dict[str, Any]:
    """Env-tunable retry policy (Dawes/Nauvoo without code changes)."""
    return {
        "max_retries": _env_int("ANOR_HTTP_RETRIES", 3),
        "base_delay_s": _env_float("ANOR_HTTP_RETRY_BASE", 0.5),
        "max_delay_s": _env_float("ANOR_HTTP_RETRY_MAX", 8.0),
        "jitter": _env_float("ANOR_HTTP_RETRY_JITTER", 0.25),
    }


class PipelineError(RuntimeError):
    """Upstream or pipeline failure.

    Attributes:
        retryable: whether a caller/queue should try again
        status_code: HTTP status when known
        attempts: how many attempts were made
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: Optional[int] = None,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.attempts = attempts


def _is_retryable_http(code: int) -> bool:
    return code in _RETRYABLE_HTTP


def with_exponential_backoff(
    fn: Callable[[], T],
    *,
    max_retries: Optional[int] = None,
    base_delay_s: Optional[float] = None,
    max_delay_s: Optional[float] = None,
    jitter: Optional[float] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    label: str = "request",
) -> T:
    """Run ``fn`` with exponential backoff on retryable failures.

    Retries: URLError / timeouts / HTTP 408,425,429,5xx.
    Does not retry: other HTTPError (4xx validation/auth), PipelineError with retryable=False.
    """
    cfg = http_retry_config()
    max_retries = cfg["max_retries"] if max_retries is None else max_retries
    base_delay_s = cfg["base_delay_s"] if base_delay_s is None else base_delay_s
    max_delay_s = cfg["max_delay_s"] if max_delay_s is None else max_delay_s
    jitter = cfg["jitter"] if jitter is None else jitter

    attempts = 0
    last_err: Optional[BaseException] = None

    while attempts <= max_retries:
        attempts += 1
        try:
            return fn()
        except PipelineError as e:
            last_err = e
            if not e.retryable or attempts > max_retries:
                e.attempts = attempts
                raise
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            retryable = _is_retryable_http(e.code)
            last_err = PipelineError(
                f"HTTP {e.code} from {label}: {body}",
                retryable=retryable,
                status_code=e.code,
                attempts=attempts,
            )
            if not retryable or attempts > max_retries:
                raise last_err from e
        except urllib.error.URLError as e:
            last_err = PipelineError(
                f"Cannot reach {label}: {e}",
                retryable=True,
                attempts=attempts,
            )
            if attempts > max_retries:
                raise last_err from e
        except TimeoutError as e:
            last_err = PipelineError(
                f"Timeout talking to {label}: {e}",
                retryable=True,
                attempts=attempts,
            )
            if attempts > max_retries:
                raise last_err from e

        # Backoff: base * 2^(attempt-1) + jitter, capped
        delay = min(max_delay_s, base_delay_s * (2 ** (attempts - 1)))
        if jitter:
            delay += random.uniform(0, jitter * delay)
        sleep_fn(delay)

    assert last_err is not None
    raise last_err


def _request_json(
    url: str,
    payload: dict,
    api_key: Optional[str] = None,
    timeout: float = 120.0,
) -> dict:
    def once() -> dict:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}

    return with_exponential_backoff(once, label=url)


def _request_bytes(
    url: str,
    payload: Optional[dict] = None,
    api_key: Optional[str] = None,
    timeout: float = 180.0,
    method: str = "POST",
) -> bytes:
    def once() -> bytes:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "*/*"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    return with_exponential_backoff(once, label=url)


class LLMClient:
    """OpenAI-compatible chat completions against LLM_URL."""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    @property
    def available(self) -> bool:
        return bool(self.cfg.llm_url) and not self.cfg.mock_media

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int = 1200,
    ) -> str:
        if not self.available:
            raise PipelineError(
                "LLM unavailable. Set LLM_URL to an OpenAI-compatible base "
                "(e.g. http://<host>:11434/v1) or unset ANOR_MOCK_MEDIA."
            )
        base = self.cfg.llm_url.rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        payload = {
            "model": self.cfg.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        out = _request_json(url, payload, api_key=self.cfg.llm_api_key)
        try:
            return out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise PipelineError(f"Unexpected LLM response shape: {out!r}") from e


class ImageClient:
    """Image generation via IMAGE_URL.

    Backends:
      - openai_images: POST {IMAGE_URL}/images/generations
      - comfy:         ComfyUI-compatible root (queue + history + view)
      - mock:          solid placeholder PNG written locally
    """

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    def _backend(self) -> str:
        if self.cfg.mock_media or not self.cfg.image_url:
            return "mock"
        if self.cfg.image_backend != "auto":
            return self.cfg.image_backend
        # Heuristic: Comfy roots usually have no /v1 suffix
        u = self.cfg.image_url.rstrip("/")
        if u.endswith("/v1"):
            return "openai_images"
        return "comfy"

    def generate(self, prompt: str, out_path: Path, width: int = 1280, height: int = 720) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full_prompt = f"{self.cfg.style_prefix}{prompt}"
        backend = self._backend()

        if backend == "mock":
            return self._write_placeholder(out_path, width, height, prompt)

        if backend == "openai_images":
            base = self.cfg.image_url.rstrip("/")
            url = base if base.endswith("/images/generations") else f"{base}/images/generations"
            payload = {
                "model": self.cfg.image_model,
                "prompt": full_prompt,
                "size": f"{width}x{height}",
                "n": 1,
                "response_format": "b64_json",
            }
            out = _request_json(url, payload, api_key=self.cfg.image_api_key, timeout=300)
            try:
                b64 = out["data"][0]["b64_json"]
            except (KeyError, IndexError, TypeError) as e:
                # Some servers return URL
                try:
                    img_url = out["data"][0]["url"]
                    raw = _request_bytes(img_url, payload=None, method="GET", timeout=120)
                    out_path.write_bytes(raw)
                    return out_path
                except Exception:
                    raise PipelineError(f"Unexpected image response: {out!r}") from e
            out_path.write_bytes(base64.b64decode(b64))
            return out_path

        if backend == "comfy":
            return self._comfy_txt2img(full_prompt, out_path, width, height)

        raise PipelineError(f"Unknown IMAGE_BACKEND: {backend}")

    def _comfy_txt2img(self, prompt: str, out_path: Path, width: int, height: int) -> Path:
        """Minimal SD checkpoint workflow — works when Comfy has a default ckpt."""
        root = self.cfg.image_url.rstrip("/")
        ckpt = self.cfg.image_model if self.cfg.image_model != "local-image" else "v1-5-pruned-emaonly.safetensors"
        workflow = {
            "1": {"inputs": {"ckpt_name": ckpt}, "class_type": "CheckpointLoaderSimple"},
            "2": {"inputs": {"text": prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
            "3": {
                "inputs": {
                    "text": "text, watermark, logo, low quality, blurry, deformed",
                    "clip": ["1", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "4": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1,
                },
                "class_type": "EmptyLatentImage",
            },
            "5": {
                "inputs": {
                    "seed": int(time.time()) % 2_147_483_647,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
                "class_type": "KSampler",
            },
            "6": {
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode",
            },
            "7": {
                "inputs": {"filename_prefix": "anor", "images": ["6", 0]},
                "class_type": "SaveImage",
            },
        }
        queued = _request_json(f"{root}/prompt", {"prompt": workflow}, api_key=self.cfg.image_api_key)
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise PipelineError(f"ComfyUI did not return prompt_id: {queued!r}")

        deadline = time.time() + 600
        while time.time() < deadline:
            hist = json.loads(
                _request_bytes(f"{root}/history/{prompt_id}", method="GET").decode("utf-8")
            )
            if prompt_id in hist:
                outputs = hist[prompt_id].get("outputs", {})
                for node_out in outputs.values():
                    if not isinstance(node_out, dict):
                        continue
                    for img in node_out.get("images", []) or []:
                        fname = img.get("filename")
                        if not fname:
                            continue
                        sub = img.get("subfolder") or ""
                        typ = img.get("type") or "output"
                        view = f"{root}/view?filename={fname}&subfolder={sub}&type={typ}"
                        raw = _request_bytes(view, method="GET")
                        out_path.write_bytes(raw)
                        return out_path
            time.sleep(0.8)
        raise PipelineError(f"ComfyUI timed out for prompt_id={prompt_id}")

    def _write_placeholder(self, out_path: Path, width: int, height: int, prompt: str) -> Path:
        """Minimal valid PNG without external deps (1x1 scaled via ffmpeg if present)."""
        # 1x1 dark PNG
        tiny = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        tmp = out_path.with_suffix(".src.png")
        tmp.write_bytes(tiny)
        # Prefer ffmpeg scale with drawtext-free solid for pipeline demos
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x1a1a2e:s={width}x{height}:d=1",
                    "-frames:v",
                    "1",
                    str(out_path),
                ],
                check=True,
                capture_output=True,
            )
            tmp.unlink(missing_ok=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            out_path.write_bytes(tiny)
            tmp.unlink(missing_ok=True)
        # Sidecar prompt for review
        out_path.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
        return out_path


class TTSClient:
    """TTS via TTS_URL or local system fallback.

    Backends:
      - openai_audio: POST {TTS_URL}/audio/speech → audio bytes
      - http_wav:     POST TTS_URL with {"text": ...} → wav/mp3 bytes
      - system:       macOS `say` or espeak → aiff/wav then ffmpeg
      - mock:         short silent audio via ffmpeg
    """

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    def _backend(self) -> str:
        if self.cfg.mock_media:
            return "mock"
        if self.cfg.tts_backend != "auto":
            return self.cfg.tts_backend
        if self.cfg.tts_url:
            u = self.cfg.tts_url.rstrip("/")
            if u.endswith("/audio/speech") or u.endswith("/v1"):
                return "openai_audio"
            return "http_wav"
        return "system"

    def synthesize(self, text: str, out_path: Path, voice: str = "alloy") -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        backend = self._backend()

        if backend == "mock":
            return self._silent(out_path, duration=max(2.0, min(30.0, len(text) / 14.0)))

        if backend == "openai_audio":
            base = self.cfg.tts_url.rstrip("/")
            url = base if base.endswith("/audio/speech") else f"{base}/audio/speech"
            payload = {
                "model": self.cfg.tts_model,
                "input": text,
                "voice": voice,
                "response_format": "mp3",
            }
            raw = _request_bytes(url, payload=payload, api_key=self.cfg.tts_api_key)
            if not str(out_path).endswith(".mp3"):
                out_path = out_path.with_suffix(".mp3")
            out_path.write_bytes(raw)
            return out_path

        if backend == "http_wav":
            raw = _request_bytes(
                self.cfg.tts_url.rstrip("/"),
                payload={"text": text, "voice": voice, "model": self.cfg.tts_model},
                api_key=self.cfg.tts_api_key,
            )
            out_path.write_bytes(raw)
            return out_path

        if backend == "system":
            return self._system_say(text, out_path)

        raise PipelineError(f"Unknown TTS_BACKEND: {backend}")

    def _system_say(self, text: str, out_path: Path) -> Path:
        aiff = out_path.with_suffix(".aiff")
        wav = out_path.with_suffix(".wav")
        # macOS say
        try:
            subprocess.run(
                ["say", "-o", str(aiff), text],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(aiff), str(wav)],
                check=True,
                capture_output=True,
            )
            aiff.unlink(missing_ok=True)
            return wav
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        # espeak fallback
        try:
            subprocess.run(
                ["espeak", "-w", str(wav), text],
                check=True,
                capture_output=True,
            )
            return wav
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            raise PipelineError(
                "No TTS_URL and system TTS failed. Set TTS_URL or install say/espeak."
            ) from e

    def _silent(self, out_path: Path, duration: float) -> Path:
        wav = out_path.with_suffix(".wav")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=mono",
                "-t",
                f"{duration:.2f}",
                str(wav),
            ],
            check=True,
            capture_output=True,
        )
        return wav


def healthcheck(cfg: PipelineConfig) -> dict[str, Any]:
    """Report which endpoints are configured (not secret values)."""
    return {
        "config": cfg.describe(),
        "llm": "ready" if (cfg.llm_url and not cfg.mock_media) else "offline/mock",
        "image": "ready" if (cfg.image_url and not cfg.mock_media) else "offline/mock",
        "tts": "ready" if (cfg.tts_url and not cfg.mock_media) else "system/mock",
        "http_retry": http_retry_config(),
    }
