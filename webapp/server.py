#!/usr/bin/env python3
"""Forked History product site — branded freemium surface for ANOR packs.

Serves:
  /                 SPA
  /static/*         CSS/JS
  /api/catalog      pricing + video catalog
  /api/scenarios    public packs list
  /api/scenario/:id pack detail
  /api/fork         decision fork (authored or LLM) — rate-limited + validated
  /api/video/jobs   async video render queue (POST create, GET list/status)
  /api/member/demo  issue short-lived Scholar token (rate-limited demo)
  /media/videos/*   rendered explainers from outputs/videos

Usage:
  python -m webapp.server --port 8787
  python webapp/server.py --host 0.0.0.0 --port 8787
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import threading
import time
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = Path(__file__).resolve().parent
STATIC = WEBAPP / "static"
CATALOG = WEBAPP / "data" / "catalog.json"
VIDEOS = ROOT / "outputs" / "videos"
SCENARIOS_PUBLIC = ROOT / "scenarios" / "public"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import PipelineConfig  # noqa: E402
from pipeline.fork_engine import list_scenarios, run_fork, scenario_payload  # noqa: E402
from pipeline.clients import healthcheck  # noqa: E402
from pipeline.validate import ScenarioValidationError  # noqa: E402
from webapp import security as sec  # noqa: E402
from webapp import membership as mem  # noqa: E402
from webapp.jobs import QUEUE, sanitize_public_error  # noqa: E402
from webapp.paths import safe_join  # noqa: E402
from webapp.http_range import parse_byte_range  # noqa: E402

_CHUNK = 64 * 1024  # 64 KiB streaming chunks for media

# Built catalog (with available flags) — avoid re-statting every video on each GET
_catalog_cache_lock = threading.Lock()
_catalog_cache: Optional[dict[str, Any]] = None  # payload, sig, ts

# Public pack index — avoid re-reading/validating every JSON on each GET/health
_scenarios_list_cache_lock = threading.Lock()
_scenarios_list_cache: Optional[dict[str, Any]] = None  # payload, sig, ts

# Per-pack detail payloads (studio GET /api/scenario/:id)
_scenario_payload_cache_lock = threading.Lock()
_scenario_payload_cache: dict[str, dict[str, Any]] = {}  # id -> payload, sig, ts
_SCENARIO_PAYLOAD_MAX = 64


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _catalog_cache_ttl_s() -> int:
    """Seconds to reuse a built catalog body. 0 disables (always rebuild)."""
    raw = os.environ.get("ANOR_CATALOG_CACHE_S", "").strip()
    if raw == "0":
        return 0
    return _env_int("ANOR_CATALOG_CACHE_S", 15)


def _scenarios_list_cache_ttl_s() -> int:
    """Seconds to reuse the public pack list. 0 disables (always rebuild)."""
    raw = os.environ.get("ANOR_SCENARIOS_CACHE_S", "").strip()
    if raw == "0":
        return 0
    return _env_int("ANOR_SCENARIOS_CACHE_S", 30)


def _videos_fingerprint() -> str:
    """Cheap signature of outputs/videos so new renders invalidate catalog cache."""
    if not VIDEOS.exists():
        return "missing"
    try:
        st = VIDEOS.stat()
        # Include dir names + nested file mtimes for top-level packs only (cheap)
        parts: list[str] = [f"root:{getattr(st, 'st_mtime_ns', int(st.st_mtime * 1e9))}"]
        for child in sorted(VIDEOS.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            try:
                cst = child.stat()
                # Prefer mp4 mtime when present (availability signal)
                mp4s = list(child.glob("*.mp4"))
                if mp4s:
                    mt = max(
                        getattr(m.stat(), "st_mtime_ns", int(m.stat().st_mtime * 1e9))
                        for m in mp4s
                    )
                    parts.append(f"{child.name}:{mt}")
                else:
                    parts.append(
                        f"{child.name}:dir:{getattr(cst, 'st_mtime_ns', int(cst.st_mtime * 1e9))}"
                    )
            except OSError:
                parts.append(f"{child.name}:err")
        return "|".join(parts)
    except OSError:
        return "err"


def _catalog_file_mtime_ns() -> int:
    try:
        st = CATALOG.stat()
        return getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    except OSError:
        return 0


def clear_catalog_cache() -> None:
    """Drop built-catalog cache (tests / after operators add media)."""
    global _catalog_cache
    with _catalog_cache_lock:
        _catalog_cache = None


def clear_scenarios_list_cache() -> None:
    """Drop public pack list cache (tests / after operators add packs)."""
    global _scenarios_list_cache
    with _scenarios_list_cache_lock:
        _scenarios_list_cache = None


def clear_scenario_payload_cache() -> None:
    """Drop per-pack detail cache (tests / after operators edit packs)."""
    with _scenario_payload_cache_lock:
        _scenario_payload_cache.clear()


def _scenario_file_fingerprint(scenario_id: str) -> str:
    """mtime+size of one public pack file (missing → constant)."""
    path = SCENARIOS_PUBLIC / f"{scenario_id}.json"
    try:
        st = path.stat()
        return f"{getattr(st, 'st_mtime_ns', int(st.st_mtime * 1e9))}:{st.st_size}"
    except OSError:
        return "missing"


def scenario_payload_cached(scenario_id: str) -> dict[str, Any]:
    """API-safe pack detail with short TTL so studio switches skip re-validation.

    Invalidates when that pack file's mtime/size changes. Bounded entry count
    so a long-lived process cannot grow unbounded under id probing (failed
    loads are not cached).
    """
    ttl = _scenarios_list_cache_ttl_s()
    sig = _scenario_file_fingerprint(scenario_id)
    now = time.monotonic()
    if ttl > 0 and sig != "missing":
        with _scenario_payload_cache_lock:
            hit = _scenario_payload_cache.get(scenario_id)
            if hit is not None:
                if hit.get("sig") == sig and now - float(hit.get("ts", 0)) < ttl:
                    return hit["payload"]

    payload = scenario_payload(scenario_id)

    if ttl > 0:
        with _scenario_payload_cache_lock:
            _scenario_payload_cache[scenario_id] = {
                "payload": payload,
                "sig": sig,
                "ts": now,
            }
            # Evict coldest entries if over bound
            if len(_scenario_payload_cache) > _SCENARIO_PAYLOAD_MAX:
                ranked = sorted(
                    _scenario_payload_cache.items(),
                    key=lambda kv: float(kv[1].get("ts", 0)),
                )
                overflow = len(_scenario_payload_cache) - _SCENARIO_PAYLOAD_MAX
                for k, _ in ranked[:overflow]:
                    del _scenario_payload_cache[k]
    return payload


def _scenarios_dir_fingerprint() -> str:
    """Cheap signature of scenarios/public JSON so pack edits invalidate cache."""
    if not SCENARIOS_PUBLIC.exists():
        return "missing"
    try:
        st = SCENARIOS_PUBLIC.stat()
        parts: list[str] = [
            f"root:{getattr(st, 'st_mtime_ns', int(st.st_mtime * 1e9))}"
        ]
        for child in sorted(SCENARIOS_PUBLIC.glob("*.json"), key=lambda p: p.name):
            try:
                cst = child.stat()
                parts.append(
                    f"{child.name}:{getattr(cst, 'st_mtime_ns', int(cst.st_mtime * 1e9))}:"
                    f"{cst.st_size}"
                )
            except OSError:
                parts.append(f"{child.name}:err")
        return "|".join(parts)
    except OSError:
        return "err"


def list_scenarios_cached() -> list[dict[str, str]]:
    """Public pack index with short TTL so boot/health do not re-validate every JSON.

    Invalidates when any ``scenarios/public/*.json`` mtime/size changes.
    """
    global _scenarios_list_cache
    ttl = _scenarios_list_cache_ttl_s()
    sig = _scenarios_dir_fingerprint()
    now = time.monotonic()
    if ttl > 0:
        with _scenarios_list_cache_lock:
            if _scenarios_list_cache is not None:
                if (
                    _scenarios_list_cache.get("sig") == sig
                    and now - float(_scenarios_list_cache.get("ts", 0)) < ttl
                ):
                    return _scenarios_list_cache["payload"]

    payload = list_scenarios(SCENARIOS_PUBLIC)

    if ttl > 0:
        with _scenarios_list_cache_lock:
            _scenarios_list_cache = {"payload": payload, "sig": sig, "ts": now}
    return payload


def build_catalog_payload() -> dict[str, Any]:
    """Catalog JSON with per-video ``available`` flags (filesystem checked).

    Cached briefly so repeated boot/library hits do not re-stat every media file.
    Invalidates when catalog.json mtime or video pack fingerprint changes.
    """
    global _catalog_cache
    ttl = _catalog_cache_ttl_s()
    sig = f"{_catalog_file_mtime_ns()}:{_videos_fingerprint()}"
    now = time.monotonic()
    if ttl > 0:
        with _catalog_cache_lock:
            if _catalog_cache is not None:
                if (
                    _catalog_cache.get("sig") == sig
                    and now - float(_catalog_cache.get("ts", 0)) < ttl
                ):
                    return _catalog_cache["payload"]

    cat = _read_json(CATALOG)
    safe_videos = []
    for v in cat.get("videos", []):
        if not isinstance(v, dict):
            continue
        rel = v.get("file")
        target = safe_join(VIDEOS, rel) if isinstance(rel, str) else None
        entry = dict(v)
        entry["available"] = bool(target and target.is_file())
        if target is None:
            entry.pop("file", None)
            entry["available"] = False
        safe_videos.append(entry)
    cat = dict(cat)
    cat["videos"] = safe_videos

    if ttl > 0:
        with _catalog_cache_lock:
            _catalog_cache = {"payload": cat, "sig": sig, "ts": now}
    return cat


def request_timeout_s() -> float | None:
    """Per-request socket timeout in seconds (None = no timeout).

    Env ``ANOR_REQUEST_TIMEOUT_S`` (default 60). Set ``0`` / ``off`` / ``none``
    to disable. Bounds slowloris-style clients that never finish a request line
    or body without holding a thread forever.
    """
    raw = (os.environ.get("ANOR_REQUEST_TIMEOUT_S") or "60").strip().lower()
    if raw in ("0", "off", "none", "false", "no"):
        return None
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


class Handler(BaseHTTPRequestHandler):
    server_version = "ForkedHistory/1.21"
    # Do not advertise Python version (default is "BaseHTTP/x.y Python/a.b")
    sys_version = ""
    # Applied at import and refreshed in run_server() so env knobs work without reload hacks
    timeout = 60.0  # replaced below after class body

    def version_string(self) -> str:
        """Product token only — no CPython version fingerprint."""
        return self.server_version

    def log_message(self, fmt: str, *args) -> None:
        """Access log line. Health probes are silent by default (ops noise).

        Set ANOR_LOG_HEALTH=1 to log /api/health hits. Errors on health still
        surface if the handler raises before a normal completion log.
        """
        try:
            line = fmt % args
        except Exception:
            line = str(fmt)
        # BaseHTTPRequestHandler formats typically include the request path
        if "/api/health" in line:
            log_health = (os.environ.get("ANOR_LOG_HEALTH") or "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not log_health:
                return
        rid = getattr(self, "_request_id", "-")
        sys.stderr.write(
            f"[forked-history] rid={rid} {self.address_string()} {line}\n"
        )

    def _ensure_request_id(self) -> str:
        if not getattr(self, "_request_id", None):
            incoming = (self.headers.get("X-Request-ID") or "").strip()[:64]
            if incoming and all(c.isalnum() or c in "-_" for c in incoming):
                self._request_id = incoming
            else:
                self._request_id = uuid.uuid4().hex[:16]
        return self._request_id

    def _security_headers(self) -> None:
        for k, v in sec.security_headers().items():
            self.send_header(k, v)
        self.send_header("X-Request-ID", self._ensure_request_id())

    def _gzip_enabled(self) -> bool:
        raw = (os.environ.get("ANOR_GZIP") or "1").strip().lower()
        return raw not in ("0", "false", "no", "off")

    def _client_accepts_gzip(self) -> bool:
        accept = (self.headers.get("Accept-Encoding") or "").lower()
        # Crude token match is fine (q-values rare for gzip on our clients)
        return "gzip" in accept

    def _maybe_gzip(self, body: bytes, content_type: str) -> tuple[bytes, bool]:
        """Compress text-like bodies when the client accepts gzip and it shrinks.

        Skips already-small payloads and non-text types (media is streamed
        elsewhere without going through ``_send`` compression).
        """
        if not self._gzip_enabled() or not self._client_accepts_gzip():
            return body, False
        if not body or len(body) < 512:
            return body, False
        ct = (content_type or "").split(";")[0].strip().lower()
        compressible = (
            ct.startswith("text/")
            or ct in (
                "application/json",
                "application/javascript",
                "application/xml",
                "image/svg+xml",
            )
            or "javascript" in ct
            or "json" in ct
        )
        if not compressible:
            return body, False
        try:
            compressed = gzip.compress(body, compresslevel=5)
        except Exception:
            return body, False
        if len(compressed) >= len(body):
            return body, False
        return compressed, True

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra: dict | None = None,
    ) -> None:
        self._ensure_request_id()
        payload, used_gzip = self._maybe_gzip(body, content_type)
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if used_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        # Allow callers to override Cache-Control via extra (e.g. short-lived catalog)
        if not (extra and "Cache-Control" in extra):
            self.send_header("Cache-Control", "no-store")
        self._security_headers()
        if extra:
            for k, v in extra.items():
                # Don't let callers clobber encoding headers accidentally
                if used_gzip and k.lower() in ("content-encoding", "content-length"):
                    continue
                self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD" or not payload:
            return
        self.wfile.write(payload)

    def _json(self, code: int, obj, extra: dict | None = None) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8", extra=extra)

    def _client_error(
        self,
        status: int,
        exc: object,
        code: str,
        *,
        log: bool = False,
    ) -> None:
        """JSON error with path-redacted message for client delivery."""
        if log:
            sys.stderr.write(
                f"[forked-history] rid={self._ensure_request_id()} {code}: {exc!s}\n"
            )
        self._json(
            status,
            {"error": sanitize_public_error(exc, limit=300), "code": code},
        )

    def _json_revalidatable(self, obj, *, max_age: int = 30) -> None:
        """JSON with weak ETag + short public cache for semi-static catalog/scenarios.

        Conditional GET returns 304 when the body hash is unchanged — cuts bandwidth
        and eases the global API rate ceiling for SPA reloads.
        """
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        etag = 'W/"' + hashlib.sha256(raw).hexdigest()[:20] + '"'
        cache = f"public, max-age={max(0, int(max_age))}, must-revalidate"
        inm = self.headers.get("If-None-Match")
        if inm and etag in [t.strip() for t in inm.split(",")]:
            self._ensure_request_id()
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self._security_headers()
            self.end_headers()
            return
        self._send(
            200,
            raw,
            "application/json; charset=utf-8",
            extra={"ETag": etag, "Cache-Control": cache},
        )

    def _validation_error(self, err: sec.ValidationError) -> None:
        headers: dict[str, str] = {}
        if err.status == 429:
            retry = err.retry_after
            if retry is None:
                # Fallback: parse message "… retry in Ns"
                headers["Retry-After"] = "60"
                msg = err.error
                if "retry in " in msg:
                    try:
                        headers["Retry-After"] = msg.split("retry in ", 1)[1].rstrip("s")
                    except Exception:
                        pass
            else:
                headers["Retry-After"] = str(max(1, int(retry)))
            if err.limit is not None:
                headers["X-RateLimit-Limit"] = str(int(err.limit))
            if err.remaining is not None:
                headers["X-RateLimit-Remaining"] = str(max(0, int(err.remaining)))
        self._json(
            err.status,
            {"error": err.error, "code": err.code},
            extra=headers or None,
        )

    def _enforce_api_rate(self, path: str) -> bool:
        """Apply global /api/* rate limit. True if response already sent (blocked)."""
        if not path.startswith("/api/"):
            return False
        err = sec.check_api_rate(sec.client_key(self), path)
        if err:
            self._validation_error(err)
            return True
        return False

    def _etag_for(self, path: Path, size: int, mtime_ns: int) -> str:
        # Weak ETag from size+mtime — good enough for local static/media revalidation
        return f'W/"{size:x}-{mtime_ns:x}"'

    def _stream_file(
        self,
        path: Path,
        content_type: str | None = None,
        *,
        support_range: bool = False,
        cache_mode: str = "no-store",
    ) -> None:
        """Serve a file without loading the entire body into memory.

        cache_mode:
          - no-store: HTML and anything that must stay fresh
          - static: CSS/JS with revalidation (ETag + max-age)
          - media: short public cache + Range
        """
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not found", "code": "not_found"})
            return
        try:
            st = path.stat()
            size = st.st_size
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        except OSError:
            self._json(404, {"error": "not found", "code": "not_found"})
            return

        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        etag = self._etag_for(path, size, mtime_ns)

        # Conditional GET — 304 Not Modified (skip body)
        inm = self.headers.get("If-None-Match")
        if inm and etag in [t.strip() for t in inm.split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            if cache_mode == "static":
                self.send_header("Cache-Control", "public, max-age=3600, must-revalidate")
            elif cache_mode == "media":
                self.send_header("Cache-Control", "public, max-age=300")
            else:
                self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            return

        range_h = self.headers.get("Range") if support_range else None
        br = parse_byte_range(range_h, size)
        status, start, end = br.status, br.start, br.end
        length = br.length if size > 0 else 0

        # 416 Range Not Satisfiable — no body; advertise total size
        if status == 416:
            self.send_response(416)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", "0")
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", etag)
            if cache_mode == "media":
                self.send_header("Cache-Control", "public, max-age=300")
            else:
                self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            return

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("ETag", etag)
        self.send_header("Accept-Ranges", "bytes" if support_range else "none")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if cache_mode == "static":
            self.send_header("Cache-Control", "public, max-age=3600, must-revalidate")
        elif cache_mode == "media":
            self.send_header("Cache-Control", "public, max-age=300")
        else:
            self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()

        if self.command == "HEAD" or length <= 0:
            return

        with path.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _file(self, path: Path, content_type: str | None = None) -> None:
        # HTML: always revalidate; CSS/JS: cacheable with ETag
        suffix = path.suffix.lower()
        if suffix in {".css", ".js", ".woff2", ".woff", ".png", ".jpg", ".jpeg", ".svg", ".ico"}:
            mode = "static"
        else:
            mode = "no-store"
        self._stream_file(path, content_type, support_range=False, cache_mode=mode)

    def _media_file(self, path: Path) -> None:
        self._stream_file(path, support_range=True, cache_mode="media")

    def _method_not_allowed(self) -> None:
        """405 with Allow — prefer over default 501 for unsupported verbs."""
        self._json(
            405,
            {"error": "method not allowed", "code": "method_not_allowed"},
            extra={"Allow": "GET, HEAD, POST, DELETE, OPTIONS"},
        )

    def do_PUT(self) -> None:
        return self._method_not_allowed()

    def do_PATCH(self) -> None:
        return self._method_not_allowed()

    def do_TRACE(self) -> None:
        return self._method_not_allowed()

    def do_CONNECT(self) -> None:
        return self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._ensure_request_id()
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, DELETE, OPTIONS")
        self._security_headers()
        self.end_headers()

    def do_HEAD(self) -> None:
        """HEAD for static/media — headers only (body skipped in _stream_file)."""
        self.command = "HEAD"
        return self.do_GET()

    def do_GET(self) -> None:
        self._ensure_request_id()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            target = safe_join(STATIC, rel)
            if target is None:
                return self._json(403, {"error": "forbidden", "code": "bad_path"})
            return self._file(target)

        if path.startswith("/media/videos/"):
            rel = path[len("/media/videos/") :]
            target = safe_join(VIDEOS, rel)
            if target is None:
                return self._json(403, {"error": "forbidden", "code": "bad_path"})
            return self._media_file(target)

        # Global API ceiling (health exempt) before any catalog/scenario work
        if path.startswith("/api/") and self._enforce_api_rate(path):
            return

        if path == "/api/catalog":
            return self._json_revalidatable(build_catalog_payload(), max_age=30)

        if path == "/api/scenarios":
            return self._json_revalidatable(list_scenarios_cached(), max_age=60)

        if path == "/api/health":
            return self._json(200, self._health_payload())

        if path == "/api/video/jobs":
            # Privacy: only return jobs owned by this client (never all tenants)
            owner = sec.client_key(self)
            jobs = [
                QUEUE.to_public_enriched(j)
                for j in QUEUE.list_for_owner(owner, limit=30)
            ]
            return self._json(
                200,
                {
                    "jobs": jobs,
                    "queue": QUEUE.stats(),
                    "scoped": True,
                },
            )

        if path.startswith("/api/video/jobs/"):
            jid = path[len("/api/video/jobs/") :].strip("/")
            jerr = sec.validate_job_id(jid)
            if jerr:
                return self._validation_error(jerr)
            job = QUEUE.get(jid)
            owner = sec.client_key(self)
            # 404 on missing *or* wrong owner — do not confirm foreign job ids
            if not job or not QUEUE.visible_to(job, owner):
                return self._json(404, {"error": "job not found", "code": "not_found"})
            return self._json(200, QUEUE.to_public_enriched(job))

        if path.startswith("/api/scenario/"):
            sid = urllib.parse.unquote(path[len("/api/scenario/") :])
            err = sec.validate_scenario_id(sid)
            if err:
                return self._validation_error(err)
            try:
                # Semi-static public packs — in-process payload cache + ETag revalidation
                return self._json_revalidatable(
                    scenario_payload_cached(sid), max_age=120
                )
            except FileNotFoundError:
                return self._json(404, {"error": "scenario not found", "code": "not_found"})
            except ScenarioValidationError as e:
                return self._client_error(422, e, "invalid_scenario")

        # Do not echo the request path (recon / log-injection hygiene)
        return self._json(404, {"error": "not found", "code": "not_found"})

    def _health_detail_authorized(self) -> bool:
        """True when caller may receive full operator health (limits, pipeline, inventory).

        Public default is a slim readiness payload. Full detail requires either:
          - ANOR_HEALTH_DETAIL=1 (local/dev), or
          - matching X-ANOR-Health-Token header when ANOR_HEALTH_TOKEN is set
        """
        if (os.environ.get("ANOR_HEALTH_DETAIL") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return True
        expected = (os.environ.get("ANOR_HEALTH_TOKEN") or "").strip()
        if not expected:
            return False
        provided = (self.headers.get("X-ANOR-Health-Token") or "").strip()
        if not provided:
            return False
        try:
            return hmac.compare_digest(provided, expected)
        except (TypeError, ValueError):
            return False

    def _health_payload(self) -> dict:
        """Build health JSON — slim by default to reduce reconnaissance surface."""
        stats = QUEUE.stats()
        ffmpeg_ok = bool(stats.get("ffmpeg_ok"))
        disk_ok = bool(stats.get("disk_ok"))
        payload: dict = {
            "site": "ok",
            "version": self.server_version,
            "ready": ffmpeg_ok and disk_ok,
            "video_queue": {
                "jobs": stats.get("jobs", 0),
                "by_status": stats.get("by_status", {}),
                "ffmpeg_ok": ffmpeg_ok,
                "disk_ok": disk_ok,
            },
            "detail": False,
        }
        if not self._health_detail_authorized():
            return payload

        cfg = PipelineConfig.from_env()
        payload["detail"] = True
        payload["security"] = {
            "fork_rate_limit": sec.FORK_LIMITER.limit,
            "fork_rate_window_s": sec.FORK_LIMITER.window_s,
            "llm_fork_rate_limit": sec.LLM_FORK_LIMITER.limit,
            "video_rate_limit": sec.VIDEO_JOB_LIMITER.limit,
            "video_rate_window_s": sec.VIDEO_JOB_LIMITER.window_s,
            "api_rate_limit": sec.API_LIMITER.limit,
            "api_rate_window_s": sec.API_LIMITER.window_s,
            "trust_proxy": sec.trust_proxy(),
            "max_body_bytes": sec.MAX_BODY_BYTES,
            "max_seed_chars": sec.MAX_SEED_CHARS,
            "member_enforcement": mem.enforcement_enabled(),
        }
        payload["video_queue"] = stats
        payload["pipeline"] = healthcheck(cfg)
        payload["videos_present"] = (
            sorted(p.name for p in VIDEOS.iterdir() if p.is_dir())
            if VIDEOS.exists()
            else []
        )
        payload["videos_count"] = (
            sum(1 for p in VIDEOS.iterdir() if p.is_dir()) if VIDEOS.exists() else 0
        )
        payload["scenarios_count"] = len(list_scenarios_cached())
        return payload

    def _require_json_content_type(self) -> sec.ValidationError | None:
        """POST bodies must declare JSON (charset optional)."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        length = int(self.headers.get("Content-Length") or "0")
        # Empty body is treated as {} — allow missing Content-Type only then
        if length == 0 and not ctype:
            return None
        if ctype not in ("application/json", "text/json"):
            return sec.ValidationError(
                415,
                "Content-Type must be application/json",
                "unsupported_media_type",
            )
        return None

    def _read_json_body(self) -> tuple[dict | None, sec.ValidationError | None]:
        ct_err = self._require_json_content_type()
        if ct_err:
            return None, ct_err
        body_err = sec.check_body_size(self.headers.get("Content-Length"))
        if body_err:
            return None, body_err
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(min(length, sec.MAX_BODY_BYTES + 1)) if length else b"{}"
        if len(raw) > sec.MAX_BODY_BYTES:
            return None, sec.ValidationError(
                413,
                f"request body too large (max {sec.MAX_BODY_BYTES} bytes)",
                "body_too_large",
            )
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, sec.ValidationError(400, "invalid json", "bad_json")
        if not isinstance(data, dict):
            return None, sec.ValidationError(400, "body must be a JSON object", "bad_json")
        return data, None

    def do_DELETE(self) -> None:
        self._ensure_request_id()
        parsed = urllib.parse.urlparse(self.path)
        if self._enforce_api_rate(parsed.path):
            return
        if not parsed.path.startswith("/api/video/jobs/"):
            return self._json(404, {"error": "not found"})
        jid = parsed.path[len("/api/video/jobs/") :].strip("/")
        jerr = sec.validate_job_id(jid)
        if jerr:
            return self._validation_error(jerr)
        # Same membership gate as enqueue — cancel is a Scholar control when enforced
        denied = mem.require_member(self)
        if denied:
            status, body = denied
            return self._json(status, body)
        # Ownership: cannot cancel another client's job
        existing = QUEUE.get(jid)
        owner = sec.client_key(self)
        if not existing or not QUEUE.visible_to(existing, owner):
            return self._json(404, {"error": "job not found", "code": "not_found"})
        ok, reason, job = QUEUE.cancel(jid)
        if not ok and reason == "not_found":
            return self._json(404, {"error": "job not found", "code": "not_found"})
        if not ok and reason == "already_terminal":
            return self._json(
                409,
                {
                    "error": "job already finished",
                    "code": "already_terminal",
                    "job": QUEUE.to_public_enriched(job) if job else None,
                },
            )
        return self._json(
            200,
            {
                "ok": True,
                "reason": reason,
                "job": QUEUE.to_public_enriched(job) if job else None,
            },
        )

    def do_POST(self) -> None:
        self._ensure_request_id()
        parsed = urllib.parse.urlparse(self.path)
        if self._enforce_api_rate(parsed.path):
            return

        if parsed.path == "/api/member/demo":
            return self._post_member_demo()

        if parsed.path == "/api/video/jobs":
            return self._post_video_job()

        if parsed.path != "/api/fork":
            return self._json(404, {"error": "not found"})

        data, err = self._read_json_body()
        if err:
            return self._validation_error(err)
        assert data is not None

        scenario_id = data.get("scenario_id")
        choice_id = data.get("choice_id")
        use_llm = bool(data.get("use_llm"))

        for v_err in (
            sec.validate_scenario_id(scenario_id),
            sec.validate_choice_id(choice_id),
        ):
            if v_err:
                return self._validation_error(v_err)

        seed, seed_err = sec.sanitize_custom_seed(data.get("custom_seed"))
        if seed_err:
            return self._validation_error(seed_err)

        # Custom seeds and LLM re-renders are Scholar-tier server-side
        if use_llm or seed:
            denied = mem.require_member(self)
            if denied:
                status, body = denied
                return self._json(status, body)

        key = sec.client_key(self)
        rate_err, rate_headers = sec.check_fork_rate(key, use_llm=use_llm)
        if rate_err:
            return self._validation_error(rate_err)

        cfg = PipelineConfig.from_env()
        try:
            result = run_fork(
                scenario_id,
                choice_id,
                cfg=cfg,
                use_llm=use_llm,
            )
            payload = result.to_dict()
            if seed:
                payload["custom_seed"] = seed
                payload["narrative"] = (
                    payload["narrative"]
                    + "\n\n---\n**Custom pressure seed (user-provided, not a historical source):** "
                    + seed
                    + "\n*Treat this seed as a simulation prompt only.*"
                )
                ribbon = list(payload.get("provenance_ribbon") or [])
                ribbon.append("seed:user")
                payload["provenance_ribbon"] = ribbon
            return self._json(200, payload, extra=rate_headers or None)
        except FileNotFoundError:
            return self._json(404, {"error": "scenario not found", "code": "not_found"})
        except ScenarioValidationError as e:
            return self._client_error(422, e, "invalid_scenario")
        except KeyError as e:
            return self._client_error(400, e, "bad_choice")
        except Exception as e:
            return self._client_error(400, e, "fork_failed", log=True)

    def _post_video_job(self) -> None:
        data, err = self._read_json_body()
        if err:
            return self._validation_error(err)
        assert data is not None

        scenario_id = data.get("scenario_id")
        choice_id = data.get("choice_id")
        use_llm = bool(data.get("use_llm"))

        for v_err in (
            sec.validate_scenario_id(scenario_id),
            sec.validate_choice_id(choice_id),
        ):
            if v_err:
                return self._validation_error(v_err)

        denied = mem.require_member(self)
        if denied:
            status, body = denied
            return self._json(status, body)

        key = sec.client_key(self)
        rate_err, rate_headers = sec.check_video_job_rate(key)
        if rate_err:
            return self._validation_error(rate_err)

        force = bool(data.get("force"))
        # Cache hit needs no ffmpeg/disk headroom — skip dep check to serve
        # already-rendered library MP4s on lean hosts.
        from webapp.jobs import check_render_dependencies, find_cached_video

        will_cache = (not force) and find_cached_video(scenario_id, choice_id) is not None
        if not will_cache:
            ok, dep_msg = check_render_dependencies(force=True)
            if not ok:
                code = (
                    "insufficient_disk"
                    if "disk" in dep_msg.lower() or "space" in dep_msg.lower()
                    else "render_deps_missing"
                )
                return self._json(
                    503,
                    {"error": dep_msg, "code": code},
                )

        try:
            job, deduped = QUEUE.enqueue(
                scenario_id,
                choice_id,
                use_llm=use_llm,
                owner_key=key,
                force=force,
            )
        except RuntimeError as e:
            return self._client_error(503, e, "queue_full")
        except Exception as e:
            return self._client_error(400, e, "enqueue_failed", log=True)

        # 202 Accepted — client polls GET /api/video/jobs/{id}
        # Deduped responses reuse the active job (no second GPU worker)
        # Cache hits return completed immediately (result.cached=true)
        payload = QUEUE.to_public_enriched(job)
        payload["deduped"] = deduped
        cache_hit = bool(
            job.status == "completed"
            and isinstance(job.result, dict)
            and job.result.get("cached")
        )
        payload["cache_hit"] = cache_hit
        extra = {
            "X-Job-Deduped": "1" if deduped else "0",
            "X-Job-Cache-Hit": "1" if cache_hit else "0",
            **rate_headers,
        }
        return self._json(202, payload, extra=extra)

    def _post_member_demo(self) -> None:
        """Issue a short-lived Scholar token for demo unlock / review."""
        key = sec.client_key(self)
        rate_err, rate_headers = sec.check_demo_token_rate(key)
        if rate_err:
            return self._validation_error(rate_err)

        # Optional body for plan name
        plan = "scholar"
        length = int(self.headers.get("Content-Length") or "0")
        if length > 0:
            data, err = self._read_json_body()
            if err:
                return self._validation_error(err)
            if data and isinstance(data.get("plan"), str):
                plan = data["plan"][:32]

        token = mem.issue_token(plan)
        if not token:
            return self._json(
                503,
                {
                    "error": "membership tokens unavailable (set ANOR_MEMBER_SECRET)",
                    "code": "token_unavailable",
                },
            )
        return self._json(
            200,
            {
                "token": token,
                "plan": plan,
                "ttl_s": mem.token_ttl_s(),
                "enforcement": mem.enforcement_enabled(),
                "header": "X-ANOR-Member",
            },
            extra=rate_headers or None,
        )


# Sync class timeout from env once Handler is defined
Handler.timeout = request_timeout_s()


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    # Refresh from env each start (tests / process managers may set env late)
    Handler.timeout = request_timeout_s()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Forked History → http://{host}:{port}")
    print(f"  static: {STATIC}")
    print(f"  videos: {VIDEOS}")
    print(f"  packs:  {ROOT / 'scenarios' / 'public'}")
    to = Handler.timeout
    to_s = f"{to:.0f}s" if isinstance(to, (int, float)) else "off"
    print(
        f"  security: fork≤{sec.FORK_LIMITER.limit}/{int(sec.FORK_LIMITER.window_s)}s "
        f"llm≤{sec.LLM_FORK_LIMITER.limit}/{int(sec.LLM_FORK_LIMITER.window_s)}s "
        f"body≤{sec.MAX_BODY_BYTES}B seed≤{sec.MAX_SEED_CHARS}c "
        f"req_timeout={to_s}"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Forked History product site")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    args = p.parse_args(argv)
    run_server(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
