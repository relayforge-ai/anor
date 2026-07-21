"""Narrated explainer video: script → TTS → stills → ffmpeg.

Usage:
  python -m pipeline.cli video --scenario ELO-003 --choice historical
"""

from __future__ import annotations

import hashlib
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
_CLIP_CACHE_MIN_BYTES = 500


def media_cache_hit_sidecar(path: Path, *, kind: str) -> bool:
    """True when a still/tts/clip path has a hit sidecar from the cost caches.

    Sidecar layouts:
      still/clip: ``{stem}.cache.txt`` next to the asset
      tts:        ``{file}{suffix}.cache.txt`` (e.g. vo.wav.cache.txt)
    """
    path = Path(path)
    needle = {
        "still": "still_cache_hit",
        "tts": "tts_cache_hit",
        "clip": "clip_cache_hit",
    }.get(kind, "_cache_hit")
    candidates = [
        path.with_suffix(".cache.txt"),
        Path(str(path) + ".cache.txt"),
    ]
    for note in candidates:
        try:
            if note.is_file() and needle in note.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


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


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def video_frame_size() -> tuple[int, int]:
    """Output frame size for Ken Burns clips (default 1080p)."""
    w = _env_int("ANOR_VIDEO_WIDTH", 1920)
    h = _env_int("ANOR_VIDEO_HEIGHT", 1080)
    # libx264 wants even dims
    return w - (w % 2), h - (h % 2)


def ken_burns_params() -> dict:
    """Ken Burns quality knobs (env-tunable; defaults match historical filter).

    Included in clip-cache keys so changing zoom/FPS does not reuse a mux
    rendered under different motion settings.
    """
    fps = _env_int("ANOR_VIDEO_FPS", 30)
    zoom_max = max(1.01, min(2.0, _env_float("ANOR_KB_ZOOM_MAX", 1.15)))
    zoom_delta = max(0.01, min(1.0, _env_float("ANOR_KB_ZOOM_DELTA", 0.15)))
    min_scale = max(1, min(4, _env_int("ANOR_KB_MIN_SCALE", 2)))
    return {
        "fps": fps,
        "zoom_max": zoom_max,
        "zoom_delta": zoom_delta,
        "min_scale": min_scale,
    }


def clip_encode_params() -> dict:
    """ffmpeg encode knobs for Ken Burns muxes (env-tunable).

    Included in clip-cache keys so bitrate/tune changes do not reuse a mux
    encoded under different settings.
    """
    tune = (os.environ.get("ANOR_CLIP_X264_TUNE") or "stillimage").strip() or "stillimage"
    # Keep tune conservative — only allow a small known set
    if tune not in ("stillimage", "film", "animation", "grain", "fastdecode", "zerolatency"):
        tune = "stillimage"
    raw_br = (os.environ.get("ANOR_CLIP_AUDIO_BITRATE") or "192k").strip() or "192k"
    a_br = "192k"
    if len(raw_br) <= 16:
        low = raw_br.lower()
        if low.endswith("k") and low[:-1].isdigit():
            n = int(low[:-1])
            if 32 <= n <= 512:
                a_br = f"{n}k"
        elif raw_br.isdigit():
            n = int(raw_br)
            if 32 <= n <= 512:
                a_br = f"{n}k"
    return {
        "v_codec": "libx264",
        "v_tune": tune,
        "a_codec": "aac",
        "a_bitrate": a_br,
    }


def ken_burns_quality_fingerprint() -> str:
    """Compact quality string for clip-cache keys (motion + encode)."""
    p = ken_burns_params()
    e = clip_encode_params()
    return (
        f"fps{int(p['fps'])}|"
        f"z{float(p['zoom_max']):.3f}|"
        f"dz{float(p['zoom_delta']):.3f}|"
        f"min{int(p['min_scale'])}x|"
        f"enc:{e['v_tune']}|{e['a_bitrate']}"
    )


def ken_burns_filter(
    duration_s: float,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[int] = None,
) -> str:
    """Build zoompan vf: slow zoom+pan into ``width``×``height``.

    Source stills should be *larger* than the frame (Comfy SDXL + Real-ESRGAN)
    so zoom has real pixel headroom. We avoid the old path that downscaled to
    frame size before zoompan (which destroyed headroom). Small mock stills are
    scaled up to ≥min_scale× frame first so zoompan is not pure soft upscale.
    """
    params = ken_burns_params()
    fps_v = int(fps) if fps is not None else int(params["fps"])
    zoom_max = float(params["zoom_max"])
    zoom_delta = float(params["zoom_delta"])
    min_scale = int(params["min_scale"])
    w, h = video_frame_size() if width is None or height is None else (width, height)
    w, h = w - (w % 2), h - (h % 2)
    frames = max(int(duration_s * fps_v) + 1, fps_v)
    z_step = zoom_delta / max(frames, 1)
    min_w, min_h = w * min_scale, h * min_scale
    vf = (
        f"scale='if(lt(iw\\,{min_w})\\,{min_w}\\,iw)':"
        f"'if(lt(ih\\,{min_h})\\,{min_h}\\,ih)':"
        f"force_original_aspect_ratio=increase,"
        f"zoompan="
        f"z='min(zoom+{z_step:.6f},{zoom_max:.4f})':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d=1:s={w}x{h}:fps={fps_v},"
        f"format=yuv420p"
    )
    return vf


def clip_cache_enabled() -> bool:
    """Reuse Ken Burns mux when still+audio+frame+quality match (default on)."""
    raw = (os.environ.get("ANOR_CLIP_CACHE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def clip_cache_dir() -> Path:
    raw = (os.environ.get("ANOR_CLIP_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return REPO_ROOT / "outputs" / "clip_cache"


def _file_fingerprint(path: Path) -> str:
    """Compact content fingerprint (size + mtime + head sample)."""
    st = path.stat()
    h = hashlib.sha256()
    h.update(f"{st.st_size}:{st.st_mtime_ns}".encode("ascii"))
    with open(path, "rb") as f:
        h.update(f.read(8192))
    return h.hexdigest()[:24]


def clip_cache_key(
    image: Path,
    audio: Path,
    *,
    duration_s: float,
    width: int,
    height: int,
    fps: Optional[int] = None,
    quality: Optional[str] = None,
) -> str:
    params = ken_burns_params()
    fps_v = int(fps) if fps is not None else int(params["fps"])
    q = quality if quality is not None else ken_burns_quality_fingerprint()
    material = "|".join(
        [
            _file_fingerprint(Path(image)),
            _file_fingerprint(Path(audio)),
            f"{float(duration_s):.2f}",
            f"{int(width)}x{int(height)}",
            str(int(fps_v)),
            q,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


def _try_clip_cache_hit(key: str, out_clip: Path) -> Optional[Path]:
    src = clip_cache_dir() / f"{key}.mp4"
    try:
        if not src.is_file() or src.stat().st_size < _CLIP_CACHE_MIN_BYTES:
            return None
        out_clip = Path(out_clip)
        out_clip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out_clip)
        out_clip.with_suffix(".cache.txt").write_text(
            f"clip_cache_hit key={key}\n", encoding="utf-8"
        )
        return out_clip
    except OSError:
        return None


def _store_clip_cache(key: str, out_clip: Path) -> None:
    try:
        out_clip = Path(out_clip)
        if not out_clip.is_file() or out_clip.stat().st_size < _CLIP_CACHE_MIN_BYTES:
            return
        dest = clip_cache_dir() / f"{key}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        shutil.copy2(out_clip, tmp)
        tmp.replace(dest)
    except OSError:
        pass


def _ken_burns_clip(image: Path, audio: Path, out_clip: Path, duration: float) -> Path:
    """Slow zoom pan over a still, muxed with narration audio (1080p default)."""
    image = Path(image)
    audio = Path(audio)
    out_clip = Path(out_clip)
    out_clip.parent.mkdir(parents=True, exist_ok=True)
    dur = max(duration, _ffprobe_duration(audio))
    w, h = video_frame_size()
    cache_on = clip_cache_enabled()
    cache_key = ""
    if cache_on:
        try:
            cache_key = clip_cache_key(
                image,
                audio,
                duration_s=dur,
                width=w,
                height=h,
                quality=ken_burns_quality_fingerprint(),
            )
            hit = _try_clip_cache_hit(cache_key, out_clip)
            if hit is not None:
                return hit
        except OSError:
            cache_key = ""

    vf = ken_burns_filter(dur, width=w, height=h)
    enc = clip_encode_params()
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
        enc["v_codec"],
        "-tune",
        enc["v_tune"],
        "-c:a",
        enc["a_codec"],
        "-b:a",
        enc["a_bitrate"],
        "-shortest",
        "-t",
        f"{dur:.2f}",
        "-pix_fmt",
        "yuv420p",
        str(out_clip),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if cache_on and cache_key:
        _store_clip_cache(cache_key, out_clip)
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
            # Segments occupy 25% → 85% of the bar; sub-stages still → tts → clip
            # so the studio can paint a finer progress ladder (not one flat "segment").
            span = 60.0 / n
            base = 25.0 + i * span
            title = seg.get("title") or seg.get("id") or f"shot {i + 1}"
            progress(
                "still",
                base,
                f"Still {i + 1}/{n}: {title} (image)",
            )
            img_path = work / f"{i:02d}_{seg['id']}.png"
            audio_path = work / f"{i:02d}_{seg['id']}_vo"
            clip_path = work / f"{i:02d}_{seg['id']}.mp4"

            images.generate(seg["image_prompt"], img_path)
            still_hit = media_cache_hit_sidecar(img_path, kind="still")
            progress(
                "tts",
                base + span * 0.4,
                f"Narration {i + 1}/{n}: {title} (TTS)",
            )
            audio_file = tts.synthesize(seg["text"], audio_path)
            tts_hit = media_cache_hit_sidecar(Path(audio_file), kind="tts")
            progress(
                "clip",
                base + span * 0.75,
                f"Ken Burns clip {i + 1}/{n}: {title}",
            )
            dur = _ffprobe_duration(audio_file)
            _ken_burns_clip(img_path, audio_file, clip_path, duration=dur)
            clip_hit = media_cache_hit_sidecar(clip_path, kind="clip")
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
                    "still_cache_hit": still_hit,
                    "tts_cache_hit": tts_hit,
                    "clip_cache_hit": clip_hit,
                }
            )

        progress("concat", 90, "Concatenating final MP4")
        _concat_clips(clips, out_mp4)

        cleaned = False
        if not _keep_work():
            progress("concat", 96, "Cleaning intermediate work files")
            cleanup_video_work(work, list_file)
            cleaned = True

        cache_summary = {
            "still_hits": sum(1 for s in seg_meta if s.get("still_cache_hit")),
            "tts_hits": sum(1 for s in seg_meta if s.get("tts_cache_hit")),
            "clip_hits": sum(1 for s in seg_meta if s.get("clip_cache_hit")),
            "segments": len(seg_meta),
        }
        meta = {
            "scenario_id": scenario_id,
            "choice_id": choice_id,
            "out_mp4": out_mp4.name,
            "speculation_level": fork.speculation_level,
            "is_historical": fork.is_historical,
            "provenance_ribbon": fork.provenance_ribbon,
            "segments": seg_meta,
            "cache": cache_summary,
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
