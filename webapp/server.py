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
from webapp import security as sec  # noqa: E402
from webapp.jobs import QUEUE  # noqa: E402


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "ForkedHistory/1.3"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[forked-history] {self.address_string()} {fmt % args}\n")

    def _security_headers(self) -> None:
        for k, v in sec.security_headers().items():
            self.send_header(k, v)

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        extra: dict | None = None,
    ) -> None:
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

    def _file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not found", "path": str(path.name)})
            return
        data = path.read_bytes()
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        range_h = self.headers.get("Range")
        if range_h and range_h.startswith("bytes=") and path.suffix.lower() in {
            ".mp4",
            ".webm",
            ".mov",
        }:
            try:
                _, rng = range_h.split("=", 1)
                start_s, end_s = (rng.split("-", 1) + [""])[:2]
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else len(data) - 1
                end = min(end, len(data) - 1)
                if start < 0 or start > end:
                    raise ValueError("bad range")
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Accept-Ranges", "bytes")
                self._security_headers()
                self.end_headers()
                self.wfile.write(chunk)
                return
            except Exception:
                pass
        self._send(200, data, ctype, extra={"Accept-Ranges": "bytes"})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._security_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())):
                return self._json(403, {"error": "forbidden"})
            return self._file(target)

        if path.startswith("/media/videos/"):
            rel = path[len("/media/videos/") :]
            target = (VIDEOS / rel).resolve()
            if not str(target).startswith(str(VIDEOS.resolve())):
                return self._json(403, {"error": "forbidden"})
            return self._file(target)

        if path == "/api/catalog":
            cat = _read_json(CATALOG)
            for v in cat.get("videos", []):
                f = VIDEOS / v["file"]
                v["available"] = f.exists()
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
                    },
                    "video_queue": QUEUE.stats(),
                    "pipeline": healthcheck(cfg),
                    "videos_dir": str(VIDEOS),
                    "videos_present": sorted(
                        p.name for p in VIDEOS.iterdir() if p.is_dir()
                    )
                    if VIDEOS.exists()
                    else [],
                },
            )

        if path == "/api/video/jobs":
            jobs = [j.to_public() for j in QUEUE.list_recent(30)]
            return self._json(200, {"jobs": jobs, "queue": QUEUE.stats()})

        if path.startswith("/api/video/jobs/"):
            jid = path[len("/api/video/jobs/") :].strip("/")
            if not jid or "/" in jid or ".." in jid:
                return self._json(400, {"error": "invalid job id", "code": "bad_job_id"})
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

        return self._json(404, {"error": "not found", "path": path})

    def _read_json_body(self) -> tuple[dict | None, sec.ValidationError | None]:
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

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

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

        key = sec.client_key(self)
        rate_err = sec.check_video_job_rate(key)
        if rate_err:
            return self._validation_error(rate_err)

        try:
            job = QUEUE.enqueue(scenario_id, choice_id, use_llm=use_llm)
        except RuntimeError as e:
            return self._json(503, {"error": str(e), "code": "queue_full"})
        except Exception as e:
            return self._json(400, {"error": str(e)[:300], "code": "enqueue_failed"})

        # 202 Accepted — client polls GET /api/video/jobs/{id}
        return self._json(202, job.to_public())


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
