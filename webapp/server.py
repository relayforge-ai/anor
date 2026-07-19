#!/usr/bin/env python3
"""Forked History product site — branded freemium surface for ANOR packs.

Serves:
  /                 SPA
  /static/*         CSS/JS
  /api/catalog      pricing + video catalog
  /api/scenarios    public packs list
  /api/scenario/:id pack detail
  /api/fork         decision fork (authored or LLM)
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


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "ForkedHistory/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[forked-history] {self.address_string()} {fmt % args}\n")

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def _file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._json(404, {"error": "not found", "path": str(path.name)})
            return
        data = path.read_bytes()
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        # Range support light-touch for video scrubbing
        range_h = self.headers.get("Range")
        if range_h and range_h.startswith("bytes=") and path.suffix.lower() in {".mp4", ".webm", ".mov"}:
            try:
                unit, rng = range_h.split("=", 1)
                start_s, end_s = (rng.split("-", 1) + [""])[:2]
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else len(data) - 1
                end = min(end, len(data) - 1)
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Accept-Ranges", "bytes")
                self._cors()
                self.end_headers()
                self.wfile.write(chunk)
                return
            except Exception:
                pass
        self._send(200, data, ctype, extra={"Accept-Ranges": "bytes"})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")

        if path.startswith("/static/"):
            rel = path[len("/static/") :]
            # path traversal guard
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
            # annotate which video files exist
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
                    "pipeline": healthcheck(cfg),
                    "videos_dir": str(VIDEOS),
                    "videos_present": sorted(
                        p.name for p in VIDEOS.iterdir() if p.is_dir()
                    )
                    if VIDEOS.exists()
                    else [],
                },
            )

        if path.startswith("/api/scenario/"):
            sid = urllib.parse.unquote(path[len("/api/scenario/") :])
            try:
                return self._json(200, scenario_payload(sid))
            except FileNotFoundError:
                return self._json(404, {"error": "scenario not found"})

        return self._json(404, {"error": "not found", "path": path})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/fork":
            return self._json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})

        scenario_id = data.get("scenario_id")
        choice_id = data.get("choice_id")
        use_llm = bool(data.get("use_llm"))
        custom_seed = (data.get("custom_seed") or "").strip()

        if not scenario_id or not choice_id:
            return self._json(400, {"error": "scenario_id and choice_id required"})

        cfg = PipelineConfig.from_env()
        try:
            result = run_fork(
                scenario_id,
                choice_id,
                cfg=cfg,
                use_llm=use_llm,
            )
            payload = result.to_dict()
            if custom_seed:
                # Scholar control: annotate seed into narrative without inventing facts
                payload["custom_seed"] = custom_seed
                payload["narrative"] = (
                    payload["narrative"]
                    + "\n\n---\n**Custom pressure seed (user-provided, not a historical source):** "
                    + custom_seed
                    + "\n*Treat this seed as a simulation prompt only.*"
                )
                ribbon = list(payload.get("provenance_ribbon") or [])
                ribbon.append("seed:user")
                payload["provenance_ribbon"] = ribbon
            return self._json(200, payload)
        except Exception as e:
            return self._json(400, {"error": str(e)})


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Forked History → http://{host}:{port}")
    print(f"  static: {STATIC}")
    print(f"  videos: {VIDEOS}")
    print(f"  packs:  {ROOT / 'scenarios' / 'public'}")
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
