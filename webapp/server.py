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
import json
import mimetypes
import sys
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = Path(__file__).resolve().parent
STATIC = WEBAPP / "static"
CATALOG = WEBAPP / "data" / "catalog.json"
VIDEOS = ROOT / "outputs" / "videos"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import PipelineConfig  # noqa: E402
from pipeline.fork_engine import list_scenarios, run_fork, scenario_payload  # noqa: E402
from pipeline.clients import healthcheck  # noqa: E402
from pipeline.validate import ScenarioValidationError  # noqa: E402
from webapp import security as sec  # noqa: E402
from webapp import membership as mem  # noqa: E402
from webapp.jobs import QUEUE  # noqa: E402
from webapp.paths import safe_join  # noqa: E402

_CHUNK = 64 * 1024  # 64 KiB streaming chunks for media


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "ForkedHistory/1.7"

    def log_message(self, fmt: str, *args) -> None:
        rid = getattr(self, "_request_id", "-")
        sys.stderr.write(
            f"[forked-history] rid={rid} {self.address_string()} {fmt % args}\n"
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

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra: dict | None = None,
    ) -> None:
        self._ensure_request_id()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj, extra: dict | None = None) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8", extra=extra)

    def _validation_error(self, err: sec.ValidationError) -> None:
        headers = {}
        if err.status == 429:
            # Extract retry seconds if present in message
            headers["Retry-After"] = "60"
            msg = err.error
            if "retry in " in msg:
                try:
                    headers["Retry-After"] = msg.split("retry in ", 1)[1].rstrip("s")
                except Exception:
                    pass
        self._json(
            err.status,
            {"error": err.error, "code": err.code},
            extra=headers or None,
        )

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
            self._json(404, {"error": "not found", "path": path.name})
            return
        try:
            st = path.stat()
            size = st.st_size
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
        except OSError:
            self._json(404, {"error": "not found", "path": path.name})
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
        start, end = 0, size - 1
        status = 200

        if range_h and range_h.startswith("bytes=") and size > 0:
            try:
                _, rng = range_h.split("=", 1)
                start_s, end_s = (rng.split("-", 1) + [""])[:2]
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else size - 1
                end = min(end, size - 1)
                if start < 0 or start > end:
                    raise ValueError("bad range")
                status = 206
            except Exception:
                start, end = 0, size - 1
                status = 200

        length = end - start + 1 if size > 0 else 0
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

    def do_OPTIONS(self) -> None:
        self._ensure_request_id()
        self.send_response(204)
        self._security_headers()
        self.end_headers()

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

        if path == "/api/catalog":
            cat = _read_json(CATALOG)
            safe_videos = []
            for v in cat.get("videos", []):
                if not isinstance(v, dict):
                    continue
                rel = v.get("file")
                target = safe_join(VIDEOS, rel) if isinstance(rel, str) else None
                entry = dict(v)
                entry["available"] = bool(target and target.is_file())
                # Never echo a path that failed safe_join
                if target is None:
                    entry.pop("file", None)
                    entry["available"] = False
                safe_videos.append(entry)
            cat = dict(cat)
            cat["videos"] = safe_videos
            return self._json(200, cat)

        if path == "/api/scenarios":
            return self._json(200, list_scenarios())

        if path == "/api/health":
            cfg = PipelineConfig.from_env()
            return self._json(
                200,
                {
                    "site": "ok",
                    "version": self.server_version,
                    "security": {
                        "fork_rate_limit": sec.FORK_LIMITER.limit,
                        "fork_rate_window_s": sec.FORK_LIMITER.window_s,
                        "llm_fork_rate_limit": sec.LLM_FORK_LIMITER.limit,
                        "video_rate_limit": sec.VIDEO_JOB_LIMITER.limit,
                        "video_rate_window_s": sec.VIDEO_JOB_LIMITER.window_s,
                        "max_body_bytes": sec.MAX_BODY_BYTES,
                        "max_seed_chars": sec.MAX_SEED_CHARS,
                        "member_enforcement": mem.enforcement_enabled(),
                    },
                    "video_queue": QUEUE.stats(),
                    "pipeline": healthcheck(cfg),
                    # Public health: names only — never absolute host paths
                    "videos_present": sorted(
                        p.name for p in VIDEOS.iterdir() if p.is_dir()
                    )
                    if VIDEOS.exists()
                    else [],
                    "videos_count": sum(1 for p in VIDEOS.iterdir() if p.is_dir())
                    if VIDEOS.exists()
                    else 0,
                    "scenarios_count": len(list_scenarios()),
                },
            )

        if path == "/api/video/jobs":
            jobs = [j.to_public() for j in QUEUE.list_recent(30)]
            return self._json(200, {"jobs": jobs, "queue": QUEUE.stats()})

        if path.startswith("/api/video/jobs/"):
            jid = path[len("/api/video/jobs/") :].strip("/")
            jerr = sec.validate_job_id(jid)
            if jerr:
                return self._validation_error(jerr)
            job = QUEUE.get(jid)
            if not job:
                return self._json(404, {"error": "job not found", "code": "not_found"})
            return self._json(200, job.to_public())

        if path.startswith("/api/scenario/"):
            sid = urllib.parse.unquote(path[len("/api/scenario/") :])
            err = sec.validate_scenario_id(sid)
            if err:
                return self._validation_error(err)
            try:
                return self._json(200, scenario_payload(sid))
            except FileNotFoundError:
                return self._json(404, {"error": "scenario not found", "code": "not_found"})
            except ScenarioValidationError as e:
                return self._json(
                    422,
                    {"error": str(e)[:300], "code": "invalid_scenario"},
                )

        return self._json(404, {"error": "not found", "path": path})

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
        ok, reason, job = QUEUE.cancel(jid)
        if not ok and reason == "not_found":
            return self._json(404, {"error": "job not found", "code": "not_found"})
        if not ok and reason == "already_terminal":
            return self._json(
                409,
                {
                    "error": "job already finished",
                    "code": "already_terminal",
                    "job": job.to_public() if job else None,
                },
            )
        return self._json(
            200,
            {
                "ok": True,
                "reason": reason,
                "job": job.to_public() if job else None,
            },
        )

    def do_POST(self) -> None:
        self._ensure_request_id()
        parsed = urllib.parse.urlparse(self.path)

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
        rate_err = sec.check_fork_rate(key, use_llm=use_llm)
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
            return self._json(200, payload)
        except FileNotFoundError:
            return self._json(404, {"error": "scenario not found", "code": "not_found"})
        except ScenarioValidationError as e:
            return self._json(422, {"error": str(e)[:300], "code": "invalid_scenario"})
        except KeyError as e:
            return self._json(400, {"error": str(e), "code": "bad_choice"})
        except Exception as e:
            return self._json(400, {"error": str(e)[:300], "code": "fork_failed"})

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
        rate_err = sec.check_video_job_rate(key)
        if rate_err:
            return self._validation_error(rate_err)

        try:
            job, deduped = QUEUE.enqueue(scenario_id, choice_id, use_llm=use_llm)
        except RuntimeError as e:
            return self._json(503, {"error": str(e), "code": "queue_full"})
        except Exception as e:
            return self._json(400, {"error": str(e)[:300], "code": "enqueue_failed"})

        # 202 Accepted — client polls GET /api/video/jobs/{id}
        # Deduped responses reuse the active job (no second GPU worker)
        payload = job.to_public()
        payload["deduped"] = deduped
        extra = {"X-Job-Deduped": "1" if deduped else "0"}
        return self._json(202, payload, extra=extra)

    def _post_member_demo(self) -> None:
        """Issue a short-lived Scholar token for demo unlock / review."""
        key = sec.client_key(self)
        rate_err = sec.check_demo_token_rate(key)
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
        )


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Forked History → http://{host}:{port}")
    print(f"  static: {STATIC}")
    print(f"  videos: {VIDEOS}")
    print(f"  packs:  {ROOT / 'scenarios' / 'public'}")
    print(
        f"  security: fork≤{sec.FORK_LIMITER.limit}/{int(sec.FORK_LIMITER.window_s)}s "
        f"llm≤{sec.LLM_FORK_LIMITER.limit}/{int(sec.LLM_FORK_LIMITER.window_s)}s "
        f"body≤{sec.MAX_BODY_BYTES}B seed≤{sec.MAX_SEED_CHARS}c"
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
