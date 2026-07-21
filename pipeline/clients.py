"""HTTP clients for LLM / IMAGE / TTS — all hosts from env, never hardcoded."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from .config import PipelineConfig
from .safe_fetch import safe_get_bytes, validate_http_url  # noqa: F401

T = TypeVar("T")

# Retry transient upstream failures (GPU warm-up, rate limits, brief outages).
# Never retries 4xx auth/validation errors.
_RETRYABLE_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})

# ComfyUI shares VRAM with Ollama on --lowvram fleets (Dawes). Serialize image
# jobs so concurrent video segments do not thrash the GPU.
_COMFY_LOCK = threading.Lock()

# Content-addressed stills: avoid re-paying SDXL+ESRGAN for identical prompts.
# Tiny mock 1×1 PNGs are ~70 bytes; real Comfy/ESRGAN stills are MiB-scale.
_STILL_CACHE_MIN_BYTES = 32
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Default negative for archival / documentary stills (no text overlays).
_DEFAULT_COMFY_NEGATIVE = (
    "text, watermark, logo, signature, low quality, blurry, deformed, "
    "modern clothing, anachronism, cartoon, anime, oversaturated"
)


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
    *,
    max_bytes: Optional[int] = None,
    allow_redirects: bool = True,
) -> bytes:
    """HTTP bytes request against operator-configured endpoints.

    For untrusted secondary URLs (e.g. image CDN from a generation response),
    prefer :func:`pipeline.safe_fetch.safe_get_bytes` instead.
    """
    from .safe_fetch import _NO_REDIRECT_OPENER, read_response_limited, max_media_bytes

    def once() -> bytes:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "*/*"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        opener = (
            urllib.request.urlopen
            if allow_redirects
            else lambda r, timeout=timeout: _NO_REDIRECT_OPENER.open(r, timeout=timeout)
        )
        limit = max_media_bytes() if max_bytes is None else max_bytes
        with opener(req, timeout=timeout) as resp:
            if limit and limit > 0:
                return read_response_limited(resp, limit)
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
        if u.endswith("/v1") or u.endswith("/images/generations"):
            return "openai_images"
        return "comfy"

    @staticmethod
    def mock_fallback_enabled() -> bool:
        """When remote IMAGE_URL fails, write a placeholder so video can finish.

        Default on so Dawes warm-up / brief Comfy outages do not kill a long
        render. Set ANOR_IMAGE_FALLBACK_MOCK=0 for strict remote-only stills.
        """
        raw = (os.environ.get("ANOR_IMAGE_FALLBACK_MOCK") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    @staticmethod
    def still_size(width: Optional[int] = None, height: Optional[int] = None) -> tuple[int, int]:
        """Native still resolution before optional Comfy upscale.

        Defaults favor SDXL landscape (1024×576) so Real-ESRGAN 4× yields
        ~4K sources — larger than 1080p frames for Ken Burns zoom headroom.
        Override with ANOR_STILL_WIDTH / ANOR_STILL_HEIGHT.
        """
        w = width if width is not None else _env_int("ANOR_STILL_WIDTH", 1024)
        h = height if height is not None else _env_int("ANOR_STILL_HEIGHT", 576)
        # Comfy latents need multiples of 8
        w = max(64, (int(w) // 8) * 8)
        h = max(64, (int(h) // 8) * 8)
        return w, h

    @staticmethod
    def still_cache_enabled(*, backend: str) -> bool:
        """Reuse identical stills across renders (default on for remote backends).

        Mock is opt-in via ANOR_STILL_CACHE_MOCK=1 (CI/offline usually skips).
        Disable entirely with ANOR_STILL_CACHE=0.
        """
        raw = (os.environ.get("ANOR_STILL_CACHE") or "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if backend == "mock":
            m = (os.environ.get("ANOR_STILL_CACHE_MOCK") or "0").strip().lower()
            return m in ("1", "true", "yes", "on")
        return True

    @staticmethod
    def still_cache_dir() -> Path:
        raw = (os.environ.get("ANOR_STILL_CACHE_DIR") or "").strip()
        if raw:
            return Path(raw).expanduser()
        return _REPO_ROOT / "outputs" / "still_cache"

    @staticmethod
    def still_cache_key(
        *,
        full_prompt: str,
        width: int,
        height: int,
        backend: str,
        image_model: str,
        upscale: bool,
        upscale_model: str,
    ) -> str:
        """Stable short key for prompt + geometry + model path (not a secret)."""
        material = "|".join(
            [
                full_prompt.strip(),
                str(int(width)),
                str(int(height)),
                backend,
                image_model or "",
                "up1" if upscale else "up0",
                upscale_model if upscale else "",
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]

    def _still_cache_path(self, key: str) -> Path:
        return self.still_cache_dir() / f"{key}.png"

    def _try_still_cache_hit(self, key: str, out_path: Path, full_prompt: str) -> Optional[Path]:
        src = self._still_cache_path(key)
        try:
            if not src.is_file() or src.stat().st_size < _STILL_CACHE_MIN_BYTES:
                return None
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_path)
            # Sidecar for human review / draft pipeline
            out_path.with_suffix(".prompt.txt").write_text(full_prompt, encoding="utf-8")
            note = out_path.with_suffix(".cache.txt")
            note.write_text(f"still_cache_hit key={key}\n", encoding="utf-8")
            return out_path
        except OSError:
            return None

    def _store_still_cache(self, key: str, out_path: Path) -> None:
        try:
            if not out_path.is_file() or out_path.stat().st_size < _STILL_CACHE_MIN_BYTES:
                return
            dest = self._still_cache_path(key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            shutil.copy2(out_path, tmp)
            tmp.replace(dest)
        except OSError:
            pass

    def generate(
        self,
        prompt: str,
        out_path: Path,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        w, h = self.still_size(width, height)
        full_prompt = f"{self.cfg.style_prefix}{prompt}"
        backend = self._backend()
        upscale = self.comfy_upscale_enabled() if backend == "comfy" else False
        up_model = self.comfy_upscale_model() if upscale else ""
        cache_on = self.still_cache_enabled(backend=backend)
        cache_key = (
            self.still_cache_key(
                full_prompt=full_prompt,
                width=w,
                height=h,
                backend=backend,
                image_model=self.cfg.image_model,
                upscale=upscale,
                upscale_model=up_model,
            )
            if cache_on
            else ""
        )
        if cache_on and cache_key:
            hit = self._try_still_cache_hit(cache_key, out_path, full_prompt)
            if hit is not None:
                return hit

        if backend == "mock":
            path = self._write_placeholder(out_path, w, h, full_prompt)
            if cache_on and cache_key:
                self._store_still_cache(cache_key, path)
            return path

        try:
            if backend == "openai_images":
                path = self._openai_images(full_prompt, out_path, w, h)
            elif backend == "comfy":
                path = self._comfy_txt2img(full_prompt, out_path, w, h)
            else:
                raise PipelineError(f"Unknown IMAGE_BACKEND: {backend}")
            if cache_on and cache_key:
                self._store_still_cache(cache_key, path)
            return path
        except PipelineError as err:
            # Never soft-fail SSRF/policy rejections; optional mock for outages only
            if "rejected" in str(err).lower():
                raise
            if self.mock_fallback_enabled():
                note = out_path.with_suffix(".fallback.txt")
                note.write_text(
                    f"image backend={backend} failed; wrote mock placeholder\n"
                    f"error: {err}\n",
                    encoding="utf-8",
                )
                return self._write_placeholder(out_path, w, h, full_prompt)
            raise

    def _openai_images(
        self, full_prompt: str, out_path: Path, width: int, height: int
    ) -> Path:
        base = (self.cfg.image_url or "").rstrip("/")
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
            # Some servers return a download URL — treat as untrusted secondary fetch
            try:
                img_url = out["data"][0]["url"]
            except (KeyError, IndexError, TypeError):
                raise PipelineError(f"Unexpected image response: {out!r}") from e
            try:
                raw = safe_get_bytes(img_url, timeout=120.0)
            except ValueError as ve:
                raise PipelineError(
                    f"Rejected image download URL: {ve}",
                    retryable=False,
                ) from ve
            except Exception as fe:
                raise PipelineError(
                    f"Failed to download image URL: {fe}",
                    retryable=True,
                ) from fe
            out_path.write_bytes(raw)
            return out_path
        out_path.write_bytes(base64.b64decode(b64))
        return out_path

    @staticmethod
    def comfy_upscale_enabled() -> bool:
        """Real-ESRGAN (or other) ImageUpscaleWithModel after VAE decode.

        Default on so Ken Burns has pixel headroom. Disable with
        ANOR_COMFY_UPSCALE=0 when VRAM is tight.
        """
        raw = (os.environ.get("ANOR_COMFY_UPSCALE") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    @staticmethod
    def comfy_upscale_model() -> str:
        return (
            os.environ.get("ANOR_COMFY_UPSCALE_MODEL") or "RealESRGAN_x4plus.pth"
        ).strip()

    @staticmethod
    def resolve_comfy_ckpt(image_model: str) -> str:
        """Map config model id to a Comfy checkpoint filename.

        Prefers SDXL base (OpenRAIL, commercial-ok). Never defaults to Flux.1-dev.
        """
        if not image_model or image_model in ("local-image", "auto"):
            return "sd_xl_base_1.0.safetensors"
        # Reject non-commercial Flux.1-dev on the monetized path
        low = image_model.lower()
        if "flux" in low and "dev" in low and "schnell" not in low:
            raise PipelineError(
                "IMAGE_MODEL appears to be Flux.1-dev (non-commercial). "
                "Use sd_xl_base_1.0.safetensors (OpenRAIL) or Flux.1-schnell (Apache).",
                retryable=False,
            )
        return image_model

    @staticmethod
    def build_comfy_workflow(
        prompt: str,
        *,
        ckpt: str,
        width: int,
        height: int,
        seed: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        negative: Optional[str] = None,
        upscale: bool = True,
        upscale_model: str = "RealESRGAN_x4plus.pth",
        filename_prefix: str = "anor",
    ) -> dict[str, Any]:
        """SDXL/SD checkpoint → optional Real-ESRGAN → SaveImage graph."""
        steps = steps if steps is not None else _env_int("ANOR_COMFY_STEPS", 25)
        cfg_scale = cfg if cfg is not None else _env_float("ANOR_COMFY_CFG", 7.0)
        seed_v = seed if seed is not None else int(time.time() * 1000) % 2_147_483_647
        neg = negative if negative is not None else (
            os.environ.get("ANOR_COMFY_NEGATIVE") or _DEFAULT_COMFY_NEGATIVE
        )
        # SDXL likes slightly longer schedules; euler_ancestral is stable on lowvram
        sampler = (os.environ.get("ANOR_COMFY_SAMPLER") or "euler").strip()
        scheduler = (os.environ.get("ANOR_COMFY_SCHEDULER") or "normal").strip()

        workflow: dict[str, Any] = {
            "1": {
                "inputs": {"ckpt_name": ckpt},
                "class_type": "CheckpointLoaderSimple",
            },
            "2": {
                "inputs": {"text": prompt, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
            },
            "3": {
                "inputs": {"text": neg, "clip": ["1", 1]},
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
                    "seed": seed_v,
                    "steps": max(1, int(steps)),
                    "cfg": float(cfg_scale),
                    "sampler_name": sampler,
                    "scheduler": scheduler,
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
        }
        if upscale and upscale_model:
            workflow["8"] = {
                "inputs": {"model_name": upscale_model},
                "class_type": "UpscaleModelLoader",
            }
            workflow["9"] = {
                "inputs": {
                    "upscale_model": ["8", 0],
                    "image": ["6", 0],
                },
                "class_type": "ImageUpscaleWithModel",
            }
            image_src: list[Any] = ["9", 0]
        else:
            image_src = ["6", 0]
        workflow["7"] = {
            "inputs": {
                "filename_prefix": filename_prefix,
                "images": image_src,
            },
            "class_type": "SaveImage",
        }
        return workflow

    def _comfy_txt2img(self, prompt: str, out_path: Path, width: int, height: int) -> Path:
        """SDXL (or other ckpt) txt2img + optional Real-ESRGAN, serialized."""
        root = (self.cfg.image_url or "").rstrip("/")
        if not root:
            raise PipelineError("IMAGE_URL unset for comfy backend", retryable=False)
        ckpt = self.resolve_comfy_ckpt(self.cfg.image_model)
        upscale = self.comfy_upscale_enabled()
        upscale_model = self.comfy_upscale_model()
        workflow = self.build_comfy_workflow(
            prompt,
            ckpt=ckpt,
            width=width,
            height=height,
            upscale=upscale,
            upscale_model=upscale_model,
        )

        # One-at-a-time: shared GPU with Ollama on Dawes
        with _COMFY_LOCK:
            queued = _request_json(
                f"{root}/prompt",
                {"prompt": workflow},
                api_key=self.cfg.image_api_key,
                timeout=120,
            )
            prompt_id = queued.get("prompt_id")
            if not prompt_id:
                raise PipelineError(f"ComfyUI did not return prompt_id: {queued!r}")

            deadline = time.time() + _env_int("ANOR_COMFY_TIMEOUT_S", 600)
            while time.time() < deadline:
                hist = json.loads(
                    _request_bytes(
                        f"{root}/history/{prompt_id}", method="GET"
                    ).decode("utf-8")
                )
                if prompt_id in hist:
                    entry = hist[prompt_id]
                    # Surface Comfy node errors instead of spinning until timeout
                    status = entry.get("status") or {}
                    if status.get("status_str") == "error" or status.get(
                        "completed"
                    ) is False:
                        msgs = status.get("messages") or []
                        raise PipelineError(
                            f"ComfyUI prompt failed: {msgs!r}",
                            retryable=True,
                        )
                    outputs = entry.get("outputs", {})
                    for node_out in outputs.values():
                        if not isinstance(node_out, dict):
                            continue
                        for img in node_out.get("images", []) or []:
                            fname = img.get("filename")
                            if not fname:
                                continue
                            sub = img.get("subfolder") or ""
                            typ = img.get("type") or "output"
                            view = (
                                f"{root}/view?filename={urllib.parse.quote(str(fname))}"
                                f"&subfolder={urllib.parse.quote(str(sub))}"
                                f"&type={urllib.parse.quote(str(typ))}"
                            )
                            try:
                                raw = safe_get_bytes(view, timeout=120.0)
                            except ValueError as ve:
                                raise PipelineError(
                                    f"Rejected Comfy view URL: {ve}",
                                    retryable=False,
                                ) from ve
                            out_path.write_bytes(raw)
                            # Sidecar prompt for human review / social drafts
                            out_path.with_suffix(".prompt.txt").write_text(
                                prompt, encoding="utf-8"
                            )
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

    @staticmethod
    def mock_fallback_enabled() -> bool:
        """When remote/system TTS fails, write silent audio so video can finish.

        Default on (matches image fallback). Set ANOR_TTS_FALLBACK_MOCK=0 for strict.
        """
        raw = (os.environ.get("ANOR_TTS_FALLBACK_MOCK") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    @staticmethod
    def _clip_text(text: str) -> str:
        """Bound TTS input length (abuse / accidental huge scripts)."""
        s = (text or "").strip()
        if not s:
            raise PipelineError("empty TTS text", retryable=False)
        max_chars = _env_int("ANOR_TTS_MAX_CHARS", 8_000)
        if len(s) > max_chars:
            return s[:max_chars]
        return s

    @staticmethod
    def tts_cache_enabled(*, backend: str) -> bool:
        """Reuse identical VO clips across renders (default on for remote/system).

        Mock is opt-in via ANOR_TTS_CACHE_MOCK=1. Disable with ANOR_TTS_CACHE=0.
        """
        raw = (os.environ.get("ANOR_TTS_CACHE") or "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if backend == "mock":
            m = (os.environ.get("ANOR_TTS_CACHE_MOCK") or "0").strip().lower()
            return m in ("1", "true", "yes", "on")
        return True

    @staticmethod
    def tts_cache_dir() -> Path:
        raw = (os.environ.get("ANOR_TTS_CACHE_DIR") or "").strip()
        if raw:
            return Path(raw).expanduser()
        return _REPO_ROOT / "outputs" / "tts_cache"

    @staticmethod
    def tts_cache_key(
        *,
        text: str,
        voice: str,
        backend: str,
        tts_model: str,
    ) -> str:
        material = "|".join(
            [text.strip(), voice or "", backend, tts_model or ""]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]

    def _tts_cache_glob(self, key: str) -> list[Path]:
        d = self.tts_cache_dir()
        if not d.is_dir():
            return []
        return sorted(d.glob(f"{key}.*"))

    def _try_tts_cache_hit(self, key: str, out_path: Path) -> Optional[Path]:
        hits = [
            p
            for p in self._tts_cache_glob(key)
            if p.suffix.lower() in (".wav", ".mp3", ".aiff", ".m4a", ".ogg")
            and p.stat().st_size >= _STILL_CACHE_MIN_BYTES
        ]
        if not hits:
            return None
        src = hits[0]
        try:
            dest = out_path if out_path.suffix else out_path.with_suffix(src.suffix)
            if dest.suffix.lower() != src.suffix.lower():
                dest = out_path.with_suffix(src.suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            dest.with_suffix(dest.suffix + ".cache.txt").write_text(
                f"tts_cache_hit key={key}\n",
                encoding="utf-8",
            )
            return dest
        except OSError:
            return None

    def _store_tts_cache(self, key: str, out_path: Path) -> None:
        try:
            if not out_path.is_file() or out_path.stat().st_size < _STILL_CACHE_MIN_BYTES:
                return
            dest = self.tts_cache_dir() / f"{key}{out_path.suffix.lower() or '.wav'}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            shutil.copy2(out_path, tmp)
            tmp.replace(dest)
        except OSError:
            pass

    def synthesize(self, text: str, out_path: Path, voice: str = "alloy") -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clip_text(text)
        backend = self._backend()
        cache_on = self.tts_cache_enabled(backend=backend)
        cache_key = (
            self.tts_cache_key(
                text=text,
                voice=voice,
                backend=backend,
                tts_model=self.cfg.tts_model,
            )
            if cache_on
            else ""
        )
        if cache_on and cache_key:
            hit = self._try_tts_cache_hit(cache_key, out_path)
            if hit is not None:
                return hit

        if backend == "mock":
            path = self._silent(
                out_path, duration=max(2.0, min(30.0, len(text) / 14.0))
            )
            if cache_on and cache_key:
                self._store_tts_cache(cache_key, path)
            return path

        try:
            if backend == "openai_audio":
                path = self._openai_audio(text, out_path, voice)
            elif backend == "http_wav":
                path = self._http_wav(text, out_path, voice)
            elif backend == "system":
                path = self._system_say(text, out_path)
            else:
                raise PipelineError(f"Unknown TTS_BACKEND: {backend}")
            if cache_on and cache_key:
                self._store_tts_cache(cache_key, path)
            return path
        except PipelineError as err:
            if self.mock_fallback_enabled():
                note = out_path.with_suffix(".fallback.txt")
                note.write_text(
                    f"tts backend={backend} failed; wrote silent mock audio\n"
                    f"error: {err}\n",
                    encoding="utf-8",
                )
                return self._silent(
                    out_path,
                    duration=max(2.0, min(30.0, len(text) / 14.0)),
                )
            raise

    def _openai_audio(self, text: str, out_path: Path, voice: str) -> Path:
        base = (self.cfg.tts_url or "").rstrip("/")
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

    def _http_wav(self, text: str, out_path: Path, voice: str) -> Path:
        raw = _request_bytes(
            (self.cfg.tts_url or "").rstrip("/"),
            payload={"text": text, "voice": voice, "model": self.cfg.tts_model},
            api_key=self.cfg.tts_api_key,
        )
        out_path.write_bytes(raw)
        return out_path

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
    img = ImageClient(cfg)
    tts = TTSClient(cfg)
    still_w, still_h = ImageClient.still_size()
    # Lazy import keeps clients import light for pure unit tests
    try:
        from .video_pipeline import video_frame_size

        frame_w, frame_h = video_frame_size()
    except Exception:
        frame_w, frame_h = 1920, 1080
    return {
        "config": cfg.describe(),
        "llm": "ready" if (cfg.llm_url and not cfg.mock_media) else "offline/mock",
        "image": "ready" if (cfg.image_url and not cfg.mock_media) else "offline/mock",
        "image_backend": img._backend(),
        "image_fallback_mock": ImageClient.mock_fallback_enabled(),
        "image_still_size": [still_w, still_h],
        "image_upscale": ImageClient.comfy_upscale_enabled(),
        "image_upscale_model": (
            ImageClient.comfy_upscale_model()
            if ImageClient.comfy_upscale_enabled()
            else None
        ),
        "still_cache": ImageClient.still_cache_enabled(
            backend=img._backend()
        ),
        "video_frame_size": [frame_w, frame_h],
        "tts": "ready" if (cfg.tts_url and not cfg.mock_media) else "system/mock",
        "tts_backend": tts._backend(),
        "tts_fallback_mock": TTSClient.mock_fallback_enabled(),
        "tts_cache": TTSClient.tts_cache_enabled(backend=tts._backend()),
        "http_retry": http_retry_config(),
    }
