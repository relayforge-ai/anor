"""Narrated explainer video: script → TTS → stills → ffmpeg.

Usage:
  python -m pipeline.cli video --scenario ELO-003 --choice historical
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .clients import ImageClient, TTSClient
from .config import PipelineConfig
from .fork_engine import load_scenario, run_fork

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "outputs" / "videos"


@dataclass
class VideoBuildResult:
    scenario_id: str
    choice_id: str
    out_mp4: Path
    script_path: Path
    segments: list[dict]
    mock_media: bool


def _ffprobe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 5.0


def _ken_burns_clip(image: Path, audio: Path, out_clip: Path, duration: float) -> Path:
    """Slow zoom pan over a still, muxed with narration audio."""
    # Ensure duration at least audio length
    dur = max(duration, _ffprobe_duration(audio))
    # zoompan: gentle Ken Burns
    vf = (
        f"scale=1280:720:force_original_aspect_ratio=increase,"
        f"crop=1280:720,"
        f"zoompan=z='min(zoom+0.0008,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-i",
        str(audio),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-t",
        f"{dur:.2f}",
        "-pix_fmt",
        "yuv420p",
        str(out_clip),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_clip


def _concat_clips(clips: list[Path], out_mp4: Path) -> Path:
    list_file = out_mp4.with_suffix(".txt")
    list_file.write_text(
        "".join(f"file '{c.resolve()}'\n" for c in clips),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out_mp4),
        ],
        check=True,
        capture_output=True,
    )
    return out_mp4


def build_script(scenario: dict, choice_id: str, fork_narrative: str) -> list[dict]:
    """Three-act short explainer suitable for TikTok/YouTube drafts."""
    choice = next(c for c in scenario["choices"] if c["id"] == choice_id)
    cold = scenario["opening"]["cold_open"]
    knew = scenario["opening"]["what_they_knew"]
    vo_choice = choice.get("vo_script") or choice.get("summary") or ""
    tag = choice.get("speculation_level", "simulated")
    ribbon = (
        f"Provenance: baseline is documented history. "
        f"This branch is tagged {tag}."
        + (" This is the historical path." if choice.get("is_historical") else " This path is speculation — not a fact.")
    )

    return [
        {
            "id": "cold_open",
            "title": "Cold open",
            "text": cold,
            "image_prompt": choice.get("image_prompt") or scenario.get("style_lock", ""),
            "tag": "documented",
        },
        {
            "id": "what_they_knew",
            "title": "What they knew",
            "text": knew,
            "image_prompt": scenario.get("style_lock")
            or "historical map table, officers, period-accurate, painterly documentary, no text",
            "tag": "documented",
        },
        {
            "id": "fork",
            "title": "The fork",
            "text": vo_choice,
            "image_prompt": choice.get("image_prompt") or scenario.get("style_lock", ""),
            "tag": tag,
        },
        {
            "id": "ribbon",
            "title": "Receipts",
            "text": ribbon + " Sources in the description. Argue with us — we'll adjudicate.",
            "image_prompt": "old books and archival papers on a wooden desk, documentary still, no readable text",
            "tag": "documented",
        },
    ]


def render_video(
    scenario_id: str,
    choice_id: str = "historical",
    out_dir: Optional[Path] = None,
    cfg: Optional[PipelineConfig] = None,
    use_llm: bool = False,
) -> VideoBuildResult:
    cfg = cfg or PipelineConfig.from_env()
    scenario = load_scenario(scenario_id)
    fork = run_fork(scenario_id, choice_id, cfg=cfg, use_llm=use_llm)

    out_dir = Path(out_dir or DEFAULT_OUT / f"{scenario_id}-{choice_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)

    segments = build_script(scenario, choice_id, fork.narrative)
    # Attach fuller narrative as sidecar for long-form YouTube description drafts
    script_path = out_dir / "script.md"
    script_body = [
        f"# {scenario['title']}",
        f"Choice: {fork.label} (`{choice_id}`)",
        f"Speculation: {fork.speculation_level}",
        "",
        "## Fork narrative",
        fork.narrative,
        "",
        "## Segment VO",
    ]
    for seg in segments:
        script_body.append(f"### {seg['title']} [{seg['tag']}]")
        script_body.append(seg["text"])
        script_body.append("")
    script_path.write_text("\n".join(script_body), encoding="utf-8")

    images = ImageClient(cfg)
    tts = TTSClient(cfg)
    clips: list[Path] = []
    seg_meta: list[dict] = []

    for i, seg in enumerate(segments):
        img_path = work / f"{i:02d}_{seg['id']}.png"
        audio_path = work / f"{i:02d}_{seg['id']}_vo"
        clip_path = work / f"{i:02d}_{seg['id']}.mp4"

        images.generate(seg["image_prompt"], img_path)
        audio_file = tts.synthesize(seg["text"], audio_path)
        dur = _ffprobe_duration(audio_file)
        _ken_burns_clip(img_path, audio_file, clip_path, duration=dur)
        clips.append(clip_path)
        seg_meta.append(
            {
                "id": seg["id"],
                "title": seg["title"],
                "tag": seg["tag"],
                "image": str(img_path),
                "audio": str(audio_file),
                "clip": str(clip_path),
                "duration_s": dur,
            }
        )

    out_mp4 = out_dir / f"{scenario_id}-{choice_id}.mp4"
    _concat_clips(clips, out_mp4)

    meta = {
        "scenario_id": scenario_id,
        "choice_id": choice_id,
        "out_mp4": str(out_mp4),
        "speculation_level": fork.speculation_level,
        "is_historical": fork.is_historical,
        "provenance_ribbon": fork.provenance_ribbon,
        "segments": seg_meta,
        "config": cfg.describe(),
    }
    (out_dir / "build.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return VideoBuildResult(
        scenario_id=scenario_id,
        choice_id=choice_id,
        out_mp4=out_mp4,
        script_path=script_path,
        segments=seg_meta,
        mock_media=cfg.mock_media or not (cfg.image_url and cfg.tts_url),
    )
