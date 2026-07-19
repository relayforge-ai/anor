#!/usr/bin/env python3
"""ANOR content pipeline CLI.

Examples:
  python -m pipeline.cli health
  python -m pipeline.cli list
  python -m pipeline.cli fork --scenario ELO-003 --choice march
  python -m pipeline.cli video --scenario ELO-013 --choice historical
  python -m pipeline.cli still --scenario ELO-008 --choice historical
  python -m pipeline.cli still --prompt "1944 map table archival" --out still.png
  python -m pipeline.cli site --port 8787
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .clients import ImageClient, healthcheck
from .config import PipelineConfig
from .fork_engine import list_scenarios, load_scenario, run_fork, scenario_payload
from .video_pipeline import _ken_burns_clip, render_video, video_frame_size


def _resolve_still_prompt(args: argparse.Namespace) -> str:
    """Build image prompt from free text or public pack choice metadata."""
    if getattr(args, "prompt", None):
        return str(args.prompt).strip()
    if not args.scenario:
        raise SystemExit("still requires --prompt or --scenario")
    scenario = load_scenario(args.scenario)
    choice_id = args.choice or "historical"
    choice = next(
        (c for c in scenario.get("choices", []) if c.get("id") == choice_id),
        None,
    )
    if not choice:
        raise SystemExit(f"unknown choice {choice_id!r} for {args.scenario}")
    prompt = (
        choice.get("image_prompt")
        or scenario.get("style_lock")
        or f"{scenario.get('title', args.scenario)} archival documentary still"
    )
    return str(prompt).strip()


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

    p_still = sub.add_parser(
        "still",
        help="Generate one archival still (Comfy/OpenAI/mock) for social or review",
    )
    p_still.add_argument(
        "--prompt",
        default=None,
        help="Freeform image prompt (style prefix still applied from env)",
    )
    p_still.add_argument("--scenario", default=None, help="Public pack id (uses choice image_prompt)")
    p_still.add_argument("--choice", default="historical")
    p_still.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG path (default: outputs/stills/<scenario>-<choice>.png)",
    )
    p_still.add_argument(
        "--ken-burns",
        action="store_true",
        help="Also write a short silent Ken Burns MP4 next to the still",
    )
    p_still.add_argument(
        "--ken-burns-seconds",
        type=float,
        default=3.0,
        help="Duration for --ken-burns clip (default 3)",
    )

    p_show = sub.add_parser("show", help="Print scenario packet (public fields)")
    p_show.add_argument("--scenario", required=True)

    p_site = sub.add_parser("site", help="Run Forked History product site (freemium library + studio)")
    p_site.add_argument("--host", default="127.0.0.1")
    p_site.add_argument("--port", type=int, default=8787)
    p_site.add_argument(
        "--legacy",
        action="store_true",
        help="Use the minimal pipeline fork UI instead of the product site",
    )

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

    if args.cmd == "still":
        if not args.prompt and not args.scenario:
            print("error: still requires --prompt or --scenario", file=sys.stderr)
            return 2
        prompt = _resolve_still_prompt(args)
        if args.out:
            out_path = Path(args.out)
        elif args.scenario:
            out_path = (
                Path("outputs")
                / "stills"
                / f"{args.scenario}-{args.choice or 'historical'}.png"
            )
        else:
            out_path = Path("outputs") / "stills" / "still.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        client = ImageClient(cfg)
        path = client.generate(prompt, out_path)
        payload: dict = {
            "out_png": str(path),
            "backend": client._backend(),
            "mock_media": cfg.mock_media,
            "prompt_preview": prompt[:200],
            "video_frame": list(video_frame_size()),
        }
        if args.ken_burns:
            kb = path.with_suffix(".kb.mp4")
            with tempfile.TemporaryDirectory() as td:
                audio = Path(td) / "silent.wav"
                dur = max(0.5, float(args.ken_burns_seconds))
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=44100:cl=mono",
                        "-t",
                        f"{dur:.2f}",
                        str(audio),
                    ],
                    check=True,
                    capture_output=True,
                )
                _ken_burns_clip(path, audio, kb, duration=dur)
            payload["out_mp4"] = str(kb)
            payload["ken_burns_s"] = dur
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "site":
        if args.legacy:
            from .site_app import run_server

            run_server(host=args.host, port=args.port)
        else:
            from webapp.server import run_server as run_product_site

            run_product_site(host=args.host, port=args.port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
