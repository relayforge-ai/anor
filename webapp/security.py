"""Security helpers for the Forked History product site.

In-process rate limiting + strict request validation + response headers.
No external deps for the hot path.

Tune via env without code changes:
  ANOR_FORK_RATE_LIMIT   max fork requests per window (default 20)
  ANOR_FORK_RATE_WINDOW  window seconds (default 60)
  ANOR_FORK_LLM_RATE     max use_llm=true forks per window (default 5)
  ANOR_API_RATE_LIMIT    max /api/* requests per window (default 180; health exempt)
  ANOR_API_RATE_WINDOW   global API window seconds (default 60)
  ANOR_TRUST_PROXY       if 1/true, honor X-Forwarded-For / X-Real-IP for client_key
  ANOR_MAX_BODY_BYTES    max POST body size (default 16384)
  ANOR_MAX_SEED_CHARS    max custom_seed length (default 500)
  ANOR_CORS_ORIGIN       CORS allow-origin (default * for local dev)
  ANOR_CSP               override Content-Security-Policy entirely
  ANOR_HSTS_MAX_AGE      if set (seconds), send Strict-Transport-Security (HTTPS only)
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional


# Scenario IDs: ELO-001, ANOR-003, SYNTH-01 style — no path separators
_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
# Choice ids: historical, march, recon, etc.
_SAFE_CHOICE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
# Video job ids are 16 hex chars from uuid4().hex[:16]
_SAFE_JOB_ID = re.compile(r"^[a-f0-9]{16}$")
# Strip control chars except newline/tab from free text seeds
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class ValidationError:
    status: int
    error: str
    code: str


class RateLimiter:
    """Sliding-window rate limiter keyed by client identity.

    Stale keys are purged periodically and when the map exceeds ``max_keys`` so
    a long-lived process cannot grow unbounded under many distinct client keys
    (NAT churn, probes, or misconfigured trusted-proxy header floods).
    """

    def __init__(
        self,
        limit: int,
        window_s: float,
        *,
        max_keys: int | None = None,
    ):
        self.limit = limit
        self.window_s = window_s
        # Default cap: generous for real users, finite under attack
        self.max_keys = (
            max_keys
            if max_keys is not None
            else _env_int("ANOR_RATE_LIMIT_MAX_KEYS", 10_000)
        )
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._ops = 0

    def _purge_stale_locked(self, now: float) -> None:
        """Drop keys with no hits inside the active window."""
        cutoff = now - self.window_s
        dead = [
            k
            for k, q in self._hits.items()
            if not q or q[-1] < cutoff
        ]
        for k in dead:
            del self._hits[k]

    def _enforce_max_keys_locked(self, now: float) -> None:
        """If still over max_keys after stale purge, drop oldest-by-last-hit keys."""
        if len(self._hits) <= self.max_keys:
            return
        self._purge_stale_locked(now)
        if len(self._hits) <= self.max_keys:
            return
        # Sort by most recent hit ascending (evict coldest first)
        ranked = sorted(
            self._hits.items(),
            key=lambda kv: kv[1][-1] if kv[1] else 0.0,
        )
        overflow = len(self._hits) - self.max_keys
        for k, _ in ranked[:overflow]:
            del self._hits[k]

    def allow(self, key: str) -> tuple[bool, int, int]:
        """Return (allowed, remaining, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            self._ops += 1
            # Periodic maintenance (every 64 calls)
            if self._ops % 64 == 0:
                self._purge_stale_locked(now)
                self._enforce_max_keys_locked(now)

            q = self._hits[key]
            cutoff = now - self.window_s
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry = max(1, int(self.window_s - (now - q[0])) + 1)
                return False, 0, retry
            q.append(now)
            # New key may push over max — enforce after insert
            if len(self._hits) > self.max_keys:
                self._enforce_max_keys_locked(now)
                # If we were just evicted (extreme race), re-create
                if key not in self._hits:
                    self._hits[key].append(now)
            remaining = max(0, self.limit - len(self._hits[key]))
            return True, remaining, 0

    def key_count(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._ops = 0


# Module-level limiters (shared across handler instances in one process)
FORK_LIMITER = RateLimiter(
    limit=_env_int("ANOR_FORK_RATE_LIMIT", 20),
    window_s=float(_env_int("ANOR_FORK_RATE_WINDOW", 60)),
)
LLM_FORK_LIMITER = RateLimiter(
    limit=_env_int("ANOR_FORK_LLM_RATE", 5),
    window_s=float(_env_int("ANOR_FORK_RATE_WINDOW", 60)),
)
VIDEO_JOB_LIMITER = RateLimiter(
    limit=_env_int("ANOR_VIDEO_RATE_LIMIT", 3),
    window_s=float(_env_int("ANOR_VIDEO_RATE_WINDOW", 300)),
)
DEMO_TOKEN_LIMITER = RateLimiter(
    limit=_env_int("ANOR_DEMO_TOKEN_RATE_LIMIT", 10),
    window_s=float(_env_int("ANOR_DEMO_TOKEN_RATE_WINDOW", 3600)),
)
# Global ceiling for all /api/* traffic (scrape / poll flood protection).
# /api/health is exempt so operator probes never starve.
API_LIMITER = RateLimiter(
    limit=_env_int("ANOR_API_RATE_LIMIT", 180),
    window_s=float(_env_int("ANOR_API_RATE_WINDOW", 60)),
)

# Paths under /api that skip the global API limiter
_API_RATE_EXEMPT = frozenset({"/api/health"})

MAX_BODY_BYTES = _env_int("ANOR_MAX_BODY_BYTES", 16_384)
MAX_SEED_CHARS = _env_int("ANOR_MAX_SEED_CHARS", 500)


def trust_proxy() -> bool:
    """True when reverse-proxy client headers may be trusted for rate limiting.

    Default False: any client can send X-Forwarded-For and would otherwise mint
    a fresh rate-limit bucket per spoofed IP. Enable only behind a trusted proxy
    that overwrites these headers (ANOR_TRUST_PROXY=1).
    """
    return (os.environ.get("ANOR_TRUST_PROXY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def client_key(handler) -> str:
    """Best-effort client identity for rate limiting.

    Uses the TCP peer address unless ANOR_TRUST_PROXY is enabled, in which case
    X-Forwarded-For (leftmost / original client) or X-Real-IP is preferred.
    """
    if trust_proxy():
        xff = (handler.headers.get("X-Forwarded-For") or "").strip()
        if xff:
            # Leftmost hop is the original client when the proxy appends correctly
            hop = xff.split(",")[0].strip()[:128]
            if hop:
                return hop
        xri = (handler.headers.get("X-Real-IP") or "").strip()[:128]
        if xri:
            return xri
    return (handler.client_address[0] if handler.client_address else "unknown")[:128]


def validate_scenario_id(value: object) -> Optional[ValidationError]:
    if not isinstance(value, str) or not value:
        return ValidationError(400, "scenario_id required", "missing_scenario_id")
    if ".." in value or "/" in value or "\\" in value:
        return ValidationError(400, "invalid scenario_id", "bad_scenario_id")
    if not _SAFE_ID.match(value):
        return ValidationError(400, "invalid scenario_id format", "bad_scenario_id")
    return None


def validate_choice_id(value: object) -> Optional[ValidationError]:
    if not isinstance(value, str) or not value:
        return ValidationError(400, "choice_id required", "missing_choice_id")
    if not _SAFE_CHOICE.match(value):
        return ValidationError(400, "invalid choice_id format", "bad_choice_id")
    return None


def validate_job_id(value: object) -> Optional[ValidationError]:
    if not isinstance(value, str) or not value:
        return ValidationError(400, "job id required", "missing_job_id")
    if not _SAFE_JOB_ID.match(value):
        return ValidationError(400, "invalid job id format", "bad_job_id")
    return None


def sanitize_custom_seed(value: object) -> tuple[Optional[str], Optional[ValidationError]]:
    if value is None or value == "":
        return None, None
    if not isinstance(value, str):
        return None, ValidationError(400, "custom_seed must be a string", "bad_seed_type")
    # Normalize newlines, strip NULs/control chars
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text).strip()
    if len(text) > MAX_SEED_CHARS:
        return None, ValidationError(
            400,
            f"custom_seed exceeds {MAX_SEED_CHARS} characters",
            "seed_too_long",
        )
    # Soft reject obvious prompt-injection scaffolding (length still capped)
    lowered = text.lower()
    if "ignore previous" in lowered or "system prompt" in lowered:
        return None, ValidationError(
            400,
            "custom_seed rejected by safety filter",
            "seed_filtered",
        )
    return text, None


def check_body_size(content_length: Optional[str]) -> Optional[ValidationError]:
    if content_length is None or content_length == "":
        return None
    try:
        n = int(content_length)
    except ValueError:
        return ValidationError(400, "invalid Content-Length", "bad_content_length")
    if n < 0:
        return ValidationError(400, "invalid Content-Length", "bad_content_length")
    if n > MAX_BODY_BYTES:
        return ValidationError(
            413,
            f"request body too large (max {MAX_BODY_BYTES} bytes)",
            "body_too_large",
        )
    return None


def check_fork_rate(key: str, use_llm: bool) -> Optional[ValidationError]:
    ok, remaining, retry = FORK_LIMITER.allow(f"fork:{key}")
    if not ok:
        return ValidationError(
            429,
            f"rate limit exceeded — retry in {retry}s",
            "rate_limited",
        )
    if use_llm:
        ok_llm, _, retry_llm = LLM_FORK_LIMITER.allow(f"llm:{key}")
        if not ok_llm:
            return ValidationError(
                429,
                f"LLM fork rate limit exceeded — retry in {retry_llm}s",
                "llm_rate_limited",
            )
    return None


def check_video_job_rate(key: str) -> Optional[ValidationError]:
    ok, _, retry = VIDEO_JOB_LIMITER.allow(f"video:{key}")
    if not ok:
        return ValidationError(
            429,
            f"video render rate limit exceeded — retry in {retry}s",
            "video_rate_limited",
        )
    return None


def check_demo_token_rate(key: str) -> Optional[ValidationError]:
    ok, _, retry = DEMO_TOKEN_LIMITER.allow(f"demo:{key}")
    if not ok:
        return ValidationError(
            429,
            f"demo token rate limit exceeded — retry in {retry}s",
            "demo_rate_limited",
        )
    return None


def api_rate_exempt(path: str) -> bool:
    """True when path should not consume the global API budget."""
    if not path:
        return True
    # Strip query string if present
    bare = path.split("?", 1)[0].rstrip("/") or path
    if bare in _API_RATE_EXEMPT or path in _API_RATE_EXEMPT:
        return True
    if bare == "/api/health" or path.startswith("/api/health"):
        return True
    return False


def check_api_rate(key: str, path: str = "") -> Optional[ValidationError]:
    """Global per-client ceiling for /api/* (except health probes).

    Complements endpoint-specific limiters (fork/video/demo). Cheap GETs
    like catalog/scenarios/job polls are otherwise unlimited and can be
    used for scrape or connection floods.
    """
    if path and api_rate_exempt(path):
        return None
    ok, _, retry = API_LIMITER.allow(f"api:{key}")
    if not ok:
        return ValidationError(
            429,
            f"API rate limit exceeded — retry in {retry}s",
            "api_rate_limited",
        )
    return None


# --- Response security headers -------------------------------------------------

# Default CSP: same-origin app assets + Google Fonts (used by the product SPA).
# No inline script execution (app.js is external). style-src allows Google CSS.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "upgrade-insecure-requests"
)


def hsts_header_value() -> str | None:
    """Optional Strict-Transport-Security when ANOR_HSTS_MAX_AGE is a positive int.

    Off by default so local HTTP dev is not broken. Production HTTPS deployments
    should set e.g. ANOR_HSTS_MAX_AGE=31536000 (1 year).
    """
    raw = (os.environ.get("ANOR_HSTS_MAX_AGE") or "").strip()
    if not raw:
        return None
    try:
        max_age = int(raw)
    except ValueError:
        return None
    if max_age <= 0:
        return None
    # includeSubDomains is opt-in via ANOR_HSTS_SUBDOMAINS=1
    parts = [f"max-age={max_age}"]
    if (os.environ.get("ANOR_HSTS_SUBDOMAINS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        parts.append("includeSubDomains")
    if (os.environ.get("ANOR_HSTS_PRELOAD") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        parts.append("preload")
    return "; ".join(parts)


def security_headers() -> dict[str, str]:
    """Browser hardening headers applied to every response."""
    csp = os.environ.get("ANOR_CSP", "").strip() or _DEFAULT_CSP
    cors = os.environ.get("ANOR_CORS_ORIGIN", "*").strip() or "*"
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
        "Content-Security-Policy": csp,
        "Access-Control-Allow-Origin": cors,
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-ANOR-Member, Authorization, X-Request-ID",
        "Access-Control-Expose-Headers": "X-Request-ID, ETag, Retry-After",
    }
    hsts = hsts_header_value()
    if hsts:
        headers["Strict-Transport-Security"] = hsts
    return headers
