"""Narrated explainer video: script → TTS → stills → ffmpeg.

Usage:
  python -m pipeline.cli video --scenario ELO-003 --choice historical
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .clients import ImageClient, TTSClient
from .config import PipelineConfig
from .fork_engine import load_scenario, run_fork

ProgressCb = Callable[[str, float, str], None]  # stage, pct 0-100, message

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "outputs" / "videos"


def _keep_work() -> bool:
    """When true, leave work/ intermediates for debugging (default: clean up)."""
    return (os.environ.get("ANOR_KEEP_VIDEO_WORK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def cleanup_video_work(work_dir: Path, *extra_files: Path) -> None:
    """Remove intermediate stills/audio/clips after a successful final MP4.

    Keeps the final deliverable directory lean (mp4 + script.md + build.json).
    Safe to call when paths are missing.
    """
    work_dir = Path(work_dir)
    if work_dir.is_dir():
        shutil.rmtree(work_dir, ignore_errors=True)
    for p in extra_files:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass


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


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def video_frame_size() -> tuple[int, int]:
    """Output frame size for Ken Burns clips (default 1080p)."""
    w = _env_int("ANOR_VIDEO_WIDTH", 1920)
    h = _env_int("ANOR_VIDEO_HEIGHT", 1080)
    # libx264 wants even dims
    return w - (w % 2), h - (h % 2)


def ken_burns_filter(
    duration_s: float,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: int = 30,
) -> str:
    """Build zoompan vf: slow zoom+pan into ``width``×``height``.

    Source stills should be *larger* than the frame (Comfy SDXL + Real-ESRGAN)
    so zoom has real pixel headroom. We avoid the old path that downscaled to
    frame size before zoompan (which destroyed headroom). Small mock stills are
    scaled up to ≥2× frame first so zoompan is not pure soft upscale.
    """
    w, h = video_frame_size() if width is None or height is None else (width, height)
    w, h = w - (w % 2), h - (h % 2)
    frames = max(int(duration_s * fps) + 1, fps)
    # Reach ~1.15× zoom over the clip under -loop 1 + d=1
    z_step = 0.15 / max(frames, 1)
    min_w, min_h = w * 2, h * 2
    vf = (
        f"scale='if(lt(iw\\,{min_w})\\,{min_w}\\,iw)':"
        f"'if(lt(ih\\,{min_h})\\,{min_h}\\,ih)':"
        f"force_original_aspect_ratio=increase,"
        f"zoompan="
        f"z='min(zoom+{z_step:.6f},1.15)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d=1:s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    return vf


def _ken_burns_clip(image: Path, audio: Path, out_clip: Path, duration: float) -> Path:
    """Slow zoom pan over a still, muxed with narration audio (1080p default)."""
    dur = max(duration, _ffprobe_duration(audio))
    w, h = video_frame_size()
    vf = ken_burns_filter(dur, width=w, height=h)
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
    on_progress: Optional[ProgressCb] = None,
) -> VideoBuildResult:
    def progress(stage: str, pct: float, message: str) -> None:
        if on_progress:
            on_progress(stage, max(0.0, min(100.0, pct)), message)

    cfg = cfg or PipelineConfig.from_env()
    progress("load", 5, "Loading scenario pack")
    scenario = load_scenario(scenario_id)
    progress("fork", 12, "Building decision narrative")
    fork = run_fork(scenario_id, choice_id, cfg=cfg, use_llm=use_llm)

    out_dir = Path(out_dir or DEFAULT_OUT / f"{scenario_id}-{choice_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    out_mp4 = out_dir / f"{scenario_id}-{choice_id}.mp4"
    list_file = out_mp4.with_suffix(".txt")
    success = False

    try:
        progress("script", 20, "Writing VO script and shot list")
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
        n = max(1, len(segments))

        for i, seg in enumerate(segments):
            # Segments occupy 25% → 85% of the bar
            base = 25 + (i / n) * 60
            progress("segment", base, f"Rendering segment {i + 1}/{n}: {seg['title']}")
            img_path = work / f"{i:02d}_{seg['id']}.png"
            audio_path = work / f"{i:02d}_{seg['id']}_vo"
            clip_path = work / f"{i:02d}_{seg['id']}.mp4"

            images.generate(seg["image_prompt"], img_path)
            progress("segment", base + (60 / n) * 0.35, f"TTS for segment {i + 1}/{n}")
            audio_file = tts.synthesize(seg["text"], audio_path)
            progress("segment", base + (60 / n) * 0.7, f"Muxing clip {i + 1}/{n}")
            dur = _ffprobe_duration(audio_file)
            _ken_burns_clip(img_path, audio_file, clip_path, duration=dur)
            clips.append(clip_path)
            # Relative names only — never absolute host paths in build.json
            seg_meta.append(
                {
                    "id": seg["id"],
                    "title": seg["title"],
                    "tag": seg["tag"],
                    "image": img_path.name,
                    "audio": Path(audio_file).name,
                    "clip": clip_path.name,
                    "duration_s": dur,
                }
            )

        progress("concat", 90, "Concatenating final MP4")
        _concat_clips(clips, out_mp4)

        cleaned = False
        if not _keep_work():
            progress("concat", 96, "Cleaning intermediate work files")
            cleanup_video_work(work, list_file)
            cleaned = True

        meta = {
            "scenario_id": scenario_id,
            "choice_id": choice_id,
            "out_mp4": out_mp4.name,
            "speculation_level": fork.speculation_level,
            "is_historical": fork.is_historical,
            "provenance_ribbon": fork.provenance_ribbon,
            "segments": seg_meta,
            "work_cleaned": cleaned,
            "config": cfg.describe(),
        }
        (out_dir / "build.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        progress("done", 100, "Render complete")
        success = True

        return VideoBuildResult(
            scenario_id=scenario_id,
            choice_id=choice_id,
            out_mp4=out_mp4,
            script_path=script_path,
            segments=seg_meta,
            mock_media=cfg.mock_media or not (cfg.image_url and cfg.tts_url),
        )
    finally:
        # Failed / cancelled / timed-out renders must not leave multi-MB work trees.
        # Successful path already cleaned above (unless ANOR_KEEP_VIDEO_WORK).
        if not success and not _keep_work():
            cleanup_video_work(work, list_file)
