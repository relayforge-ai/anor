#!/usr/bin/env python3
"""ANOR content pipeline CLI.

Examples:
  python -m pipeline.cli health
  python -m pipeline.cli list
  python -m pipeline.cli fork --scenario ELO-003 --choice march
  python -m pipeline.cli video --scenario ELO-013 --choice historical
  python -m pipeline.cli site --port 8787
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .clients import healthcheck
from .config import PipelineConfig
from .fork_engine import list_scenarios, run_fork, scenario_payload
from .video_pipeline import render_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anor-pipeline", description="ANOR content pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="Show endpoint configuration (no secrets)")

    sub.add_parser("list", help="List public fork scenarios")

    p_fork = sub.add_parser("fork", help="Run a decision fork")
    p_fork.add_argument("--scenario", required=True)
    p_fork.add_argument("--choice", required=True)
    p_fork.add_argument("--no-llm", action="store_true")
    p_fork.add_argument("--out", type=Path, default=None)

    p_video = sub.add_parser("video", help="Render narrated explainer (script→TTS→stills→ffmpeg)")
    p_video.add_argument("--scenario", required=True)
    p_video.add_argument("--choice", default="historical")
    p_video.add_argument("--out-dir", type=Path, default=None)
    p_video.add_argument("--use-llm", action="store_true")

    p_show = sub.add_parser("show", help="Print scenario packet (public fields)")
    p_show.add_argument("--scenario", required=True)

    p_site = sub.add_parser("site", help="Run interactive fork site")
    p_site.add_argument("--host", default="127.0.0.1")
    p_site.add_argument("--port", type=int, default=8787)

    args = parser.parse_args(argv)
    cfg = PipelineConfig.from_env()

    if args.cmd == "health":
        print(json.dumps(healthcheck(cfg), indent=2))
        return 0

    if args.cmd == "list":
        print(json.dumps(list_scenarios(), indent=2))
        return 0

    if args.cmd == "show":
        print(json.dumps(scenario_payload(args.scenario), indent=2))
        return 0

    if args.cmd == "fork":
        result = run_fork(args.scenario, args.choice, cfg=cfg, use_llm=not args.no_llm)
        payload = result.to_dict()
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Wrote {args.out}")
        else:
            print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "video":
        result = render_video(
            args.scenario,
            choice_id=args.choice,
            out_dir=args.out_dir,
            cfg=cfg,
            use_llm=args.use_llm,
        )
        print(
            json.dumps(
                {
                    "out_mp4": str(result.out_mp4),
                    "script": str(result.script_path),
                    "segments": len(result.segments),
                    "mock_media": result.mock_media,
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "site":
        from .site_app import run_server

        run_server(host=args.host, port=args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
