"""In-process async job queue for long-running video renders.

No Redis required — single-process ThreadPool style worker so the HTTP
handler returns immediately (202) and clients poll for progress.

Env:
  ANOR_VIDEO_MAX_CONCURRENT  (default 1)
  ANOR_VIDEO_MAX_QUEUED      (default 8)
  ANOR_VIDEO_JOB_TTL_S       (default 3600) — finished jobs retained this long
  ANOR_VIDEO_JOB_TIMEOUT_S   (default 600) — max wall time for a running render
  ANOR_MIN_FREE_DISK_MB      (default 512) — refuse enqueue when free space under outputs/ is below this (0 = skip check)
  ANOR_FFMPEG_CHECK_CACHE_S  (default 30) — cache ffmpeg -version results for stats/health (0 = no cache)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, TextIO

ROOT = Path(__file__).resolve().parents[1]

# Absolute filesystem paths that must never reach clients in error strings
_ABS_PATH_RE = re.compile(
    r"(?:"
    r"/(?:Users|home|var|tmp|private|opt|System|Volumes|usr|etc|root)[^\s'\"\,\]\)]*"
    r"|[A-Za-z]:\\[^\s'\"\,\]\)]*"
    r")"
)

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover — Windows hosts
    _fcntl = None  # type: ignore

# In-process fallback when fcntl is unavailable (still serializes same out_dir)
_RENDER_PATH_LOCKS: dict[str, threading.Lock] = {}
_RENDER_PATH_LOCKS_GUARD = threading.Lock()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def video_artifact_dir(scenario_id: str, choice_id: str) -> Path:
    """Directory for a scenario/choice render under outputs/videos/."""
    return ROOT / "outputs" / "videos" / f"{scenario_id}-{choice_id}"


def find_cached_video(scenario_id: str, choice_id: str) -> Optional[Path]:
    """Return path to an existing MP4 if large enough to be a real render.

    Tiny files are ignored (failed/truncated artifacts). Override minimum with
    ANOR_VIDEO_CACHE_MIN_BYTES (default 2048).
    """
    out_dir = video_artifact_dir(scenario_id, choice_id)
    # Canonical name matches video_pipeline final deliverable
    candidates = [
        out_dir / f"{scenario_id}-{choice_id}.mp4",
        *sorted(out_dir.glob("*.mp4")),
    ]
    min_bytes = _env_int("ANOR_VIDEO_CACHE_MIN_BYTES", 2048)
    seen: set[Path] = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        try:
            if p.is_file() and p.stat().st_size >= min_bytes:
                return p
        except OSError:
            continue
    return None


def read_cached_video_metrics(mp4: Path) -> dict[str, Any]:
    """Public-safe deliverable metrics for an on-disk MP4 (build.json + size).

    Reads sibling ``build.json`` written by the video pipeline when present.
    Never returns host paths or cache keys — only ints/floats suitable for
    job results and freemium catalog rows.

    Keys (all optional):
      - bytes: final MP4 size
      - duration_s: runtime seconds
      - cache: {still_hits, tts_hits, clip_hits, segments} from ladder summary
    """
    out: dict[str, Any] = {}
    try:
        st_size = int(mp4.stat().st_size)
        if st_size >= 0:
            out["bytes"] = st_size
    except OSError:
        pass

    build_path = mp4.parent / "build.json"
    try:
        if not build_path.is_file():
            return out
        meta = json.loads(build_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return out
    if not isinstance(meta, dict):
        return out

    try:
        ob = meta.get("out_mp4_bytes")
        if ob is not None and int(ob) >= 0:
            out["bytes"] = int(ob)
    except (TypeError, ValueError):
        pass
    try:
        ds = meta.get("duration_s")
        if ds is not None and float(ds) > 0:
            out["duration_s"] = round(float(ds), 2)
    except (TypeError, ValueError):
        pass

    raw_cache = meta.get("cache")
    if isinstance(raw_cache, dict):
        try:
            segs = raw_cache.get("segments")
            if segs is None:
                segs = len(meta.get("segments") or [])
            out["cache"] = {
                "still_hits": int(raw_cache.get("still_hits") or 0),
                "tts_hits": int(raw_cache.get("tts_hits") or 0),
                "clip_hits": int(raw_cache.get("clip_hits") or 0),
                "segments": int(segs or 0),
            }
        except (TypeError, ValueError):
            pass
    return out


def media_url_for(scenario_id: str, choice_id: str, filename: str) -> str:
    """Public media URL for a finished MP4 (no absolute host paths)."""
    return f"/media/videos/{scenario_id}-{choice_id}/{filename}"


def estimate_running_eta_s(
    *,
    started_at: Optional[float],
    pct: float,
    deadline_at: Optional[float] = None,
    eta_per_job_s: int = 120,
    now: Optional[float] = None,
) -> Optional[int]:
    """Heuristic seconds remaining for a *running* render (UX, not SLA).

    Prefers work-based extrapolation once progress is meaningful:
      remaining ≈ elapsed * (100 - pct) / pct
    Falls back to a fraction of ANOR_VIDEO_ETA_PER_JOB_S early on.
    Always capped by wall-clock deadline remaining when known.
    """
    t = time.time() if now is None else float(now)
    deadline_left: Optional[int] = None
    if deadline_at is not None:
        deadline_left = max(0, int(deadline_at - t))

    work_eta: Optional[float] = None
    p = max(0.0, min(100.0, float(pct or 0.0)))
    if started_at is not None and p >= 5.0:
        elapsed = max(0.0, t - float(started_at))
        if elapsed > 0.5:
            work_eta = elapsed * (100.0 - p) / p
    if work_eta is None:
        # Early in the job — assume ~eta_per remaining scaled by progress
        frac_left = max(0.0, (100.0 - p) / 100.0)
        work_eta = float(max(1, eta_per_job_s)) * frac_left

    eta = int(max(0, round(work_eta)))
    if deadline_left is not None:
        eta = min(eta, deadline_left)
    return eta


def sanitize_public_error(message: object, *, limit: int = 400) -> str:
    """Redact absolute host paths from exception text before client delivery.

    ffmpeg and pipeline failures often embed full command lines with
    ``/Users/.../outputs/videos/...`` — useful for operators in logs, unsafe
    in job JSON polled by browsers.
    """
    text = str(message or "")
    root = str(ROOT)
    if root and root in text:
        text = text.replace(root, "<anor>")
    # Also replace resolved/symlink forms when present
    try:
        resolved = str(ROOT.resolve())
        if resolved != root and resolved in text:
            text = text.replace(resolved, "<anor>")
    except OSError:
        pass

    def _shorten(match: re.Match[str]) -> str:
        raw = match.group(0)
        name = Path(raw).name
        return f"<path>/{name}" if name else "<path>"

    text = _ABS_PATH_RE.sub(_shorten, text)
    # Collapse runs of whitespace from long argv dumps
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


# ffmpeg -version is relatively expensive; stats()/health called often.
_ffmpeg_cache_lock = threading.Lock()
_ffmpeg_cache: Optional[tuple[float, bool, str]] = None  # (monotonic_ts, ok, msg)


def clear_ffmpeg_cache() -> None:
    """Drop cached ffmpeg probe (tests / after install changes)."""
    global _ffmpeg_cache
    with _ffmpeg_cache_lock:
        _ffmpeg_cache = None


def _ffmpeg_cache_ttl_s() -> int:
    raw = os.environ.get("ANOR_FFMPEG_CHECK_CACHE_S", "").strip()
    if raw == "0":
        return 0
    return _env_int("ANOR_FFMPEG_CHECK_CACHE_S", 30)


def check_ffmpeg(*, force: bool = False) -> tuple[bool, str]:
    """Fail fast if ffmpeg is missing or not runnable.

    Results are cached briefly (ANOR_FFMPEG_CHECK_CACHE_S, default 30s) so
    frequent health/queue stats probes do not spawn ffmpeg on every request.
    Use ``force=True`` at enqueue/worker start for a live check.
    """
    global _ffmpeg_cache
    ttl = _ffmpeg_cache_ttl_s()
    now = time.monotonic()
    if not force and ttl > 0:
        with _ffmpeg_cache_lock:
            if _ffmpeg_cache is not None:
                ts, ok, msg = _ffmpeg_cache
                if now - ts < ttl:
                    return ok, msg

    if not shutil.which("ffmpeg"):
        ok, msg = False, "ffmpeg not found on PATH — install ffmpeg to render videos"
    else:
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            ok, msg = True, "ok"
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            ok, msg = False, f"ffmpeg not runnable: {e}"

    with _ffmpeg_cache_lock:
        _ffmpeg_cache = (now, ok, msg)
    return ok, msg


def check_disk_space(min_free_mb: int | None = None) -> tuple[bool, str, int]:
    """Ensure enough free space under ``outputs/`` for stills + intermediate clips + MP4.

    Returns (ok, message, free_mb). ``free_mb`` is -1 when the check is disabled.
    Set ANOR_MIN_FREE_DISK_MB=0 to skip (CI hosts with tiny disks can opt out).
    """
    if min_free_mb is None:
        # _env_int clamps to ≥1; allow explicit 0 via raw env to disable
        raw = os.environ.get("ANOR_MIN_FREE_DISK_MB", "").strip()
        if raw == "0":
            min_free_mb = 0
        else:
            min_free_mb = _env_int("ANOR_MIN_FREE_DISK_MB", 512)
    if min_free_mb <= 0:
        return True, "disk check disabled", -1

    out_root = ROOT / "outputs"
    try:
        out_root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(out_root)
    except OSError as e:
        return False, f"disk check failed: {e}", 0

    free_mb = int(usage.free // (1024 * 1024))
    if free_mb < min_free_mb:
        return (
            False,
            (
                f"insufficient disk space: {free_mb}MB free under outputs/ "
                f"(need ≥{min_free_mb}MB; set ANOR_MIN_FREE_DISK_MB to adjust)"
            ),
            free_mb,
        )
    return True, "ok", free_mb


def check_render_dependencies(*, force: bool = False) -> tuple[bool, str]:
    """Fail fast if the host cannot run the video pipeline (ffmpeg + free disk).

    ``force=True`` bypasses the ffmpeg probe cache (use at enqueue / worker start).
    """
    ok, msg = check_ffmpeg(force=force)
    if not ok:
        return False, msg
    ok, msg, _free = check_disk_space()
    if not ok:
        return False, msg
    return True, "ok"


class RenderLockBusy(RuntimeError):
    """Another worker (process or thread) is already writing this render dir."""


def acquire_render_lock(out_dir: Path) -> tuple[Optional[TextIO], Optional[threading.Lock]]:
    """Exclusive lock on a scenario-choice output directory.

    Prevents concurrent ffmpeg/concat from corrupting the same ``work/`` and
    final MP4 (cross-process via fcntl when available; in-process lock always).

    Returns (file_handle, thread_lock). Pass both to :func:`release_render_lock`.
    Raises :class:`RenderLockBusy` if the lock is held.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    key = str(out_dir.resolve())

    with _RENDER_PATH_LOCKS_GUARD:
        tlock = _RENDER_PATH_LOCKS.get(key)
        if tlock is None:
            tlock = threading.Lock()
            _RENDER_PATH_LOCKS[key] = tlock

    if not tlock.acquire(blocking=False):
        raise RenderLockBusy(
            f"render already in progress for {out_dir.name} — wait or cancel"
        )

    fh: Optional[TextIO] = None
    if _fcntl is not None:
        lock_path = out_dir / ".render.lock"
        try:
            fh = open(lock_path, "a+", encoding="utf-8")
            try:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                tlock.release()
                raise RenderLockBusy(
                    f"render already in progress for {out_dir.name} — wait or cancel"
                ) from None
            fh.seek(0)
            fh.truncate()
            fh.write(f"pid={os.getpid()} ts={time.time():.3f}\n")
            fh.flush()
        except RenderLockBusy:
            raise
        except OSError as e:
            tlock.release()
            raise RuntimeError(f"could not lock render dir: {e}") from e

    return fh, tlock


def release_render_lock(
    fh: Optional[TextIO],
    tlock: Optional[threading.Lock],
) -> None:
    """Release locks acquired by :func:`acquire_render_lock`."""
    if fh is not None:
        try:
            if _fcntl is not None:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass
    if tlock is not None:
        try:
            tlock.release()
        except RuntimeError:
            pass


class JobCancelled(Exception):
    """Raised cooperatively when a running render is cancelled."""


class JobTimedOut(Exception):
    """Raised cooperatively when a running render exceeds wall-clock timeout."""


@dataclass
class VideoJob:
    id: str
    scenario_id: str
    choice_id: str
    use_llm: bool
    status: str = "queued"  # queued | running | completed | failed | cancelled | timed_out
    stage: str = "queued"
    pct: float = 0.0
    message: str = "Queued"
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    deadline_at: Optional[float] = None
    cancel_requested: bool = False
    # Rate-limit client identity at enqueue — never exposed in to_public()
    owner_key: Optional[str] = None

    def to_public(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "scenario_id": self.scenario_id,
            "choice_id": self.choice_id,
            "use_llm": self.use_llm,
            "status": self.status,
            "stage": self.stage,
            "pct": round(self.pct, 1),
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "deadline_at": self.deadline_at,
            "cancel_requested": self.cancel_requested,
        }
        if self.result:
            d["result"] = self.result
        return d


class VideoJobQueue:
    """Thread-safe video render queue."""

    def __init__(self) -> None:
        self.max_concurrent = _env_int("ANOR_VIDEO_MAX_CONCURRENT", 1)
        self.max_queued = _env_int("ANOR_VIDEO_MAX_QUEUED", 8)
        self.ttl_s = _env_int("ANOR_VIDEO_JOB_TTL_S", 3600)
        self.timeout_s = _env_int("ANOR_VIDEO_JOB_TIMEOUT_S", 600)
        self._jobs: dict[str, VideoJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_concurrent,
            thread_name_prefix="anor-video",
        )

    def _purge_locked(self) -> None:
        now = time.time()
        dead = [
            jid
            for jid, j in self._jobs.items()
            if j.finished_at and (now - j.finished_at) > self.ttl_s
        ]
        for jid in dead:
            del self._jobs[jid]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            self._purge_locked()
            statuses = {}
            for j in self._jobs.values():
                statuses[j.status] = statuses.get(j.status, 0) + 1
            ff_ok, ff_msg = check_ffmpeg()
            disk_ok, disk_msg, free_mb = check_disk_space()
            raw_min = os.environ.get("ANOR_MIN_FREE_DISK_MB", "").strip()
            min_free = 0 if raw_min == "0" else _env_int("ANOR_MIN_FREE_DISK_MB", 512)
            return {
                "max_concurrent": self.max_concurrent,
                "max_queued": self.max_queued,
                "ttl_s": self.ttl_s,
                "timeout_s": self.timeout_s,
                "jobs": len(self._jobs),
                "by_status": statuses,
                "ffmpeg_ok": ff_ok,
                "ffmpeg_detail": ff_msg if not ff_ok else "ok",
                "disk_ok": disk_ok,
                "disk_free_mb": free_mb,
                "min_free_disk_mb": min_free,
                "disk_detail": disk_msg if not disk_ok else "ok",
            }

    def find_active(
        self,
        scenario_id: str,
        choice_id: str,
        use_llm: bool = False,
    ) -> Optional[VideoJob]:
        """Return an in-flight job for the same render key, if any."""
        with self._lock:
            self._purge_locked()
            for j in self._jobs.values():
                if (
                    j.status in ("queued", "running")
                    and j.scenario_id == scenario_id
                    and j.choice_id == choice_id
                    and bool(j.use_llm) == bool(use_llm)
                    and not j.cancel_requested
                ):
                    return j
            return None

    def enqueue(
        self,
        scenario_id: str,
        choice_id: str,
        use_llm: bool = False,
        *,
        dedupe: bool = True,
        owner_key: Optional[str] = None,
        force: bool = False,
    ) -> tuple[VideoJob, bool]:
        """Enqueue a render. Returns (job, deduped).

        When ``dedupe`` is True (default), a second request for the same
        scenario/choice/use_llm while one is queued or running reuses that job
        instead of spawning duplicate GPU work.

        When ``force`` is False (default) and a finished MP4 already exists on
        disk for this scenario/choice, return an immediate **completed** job
        with ``result.cached=true`` — no worker, no GPU/TTS. Set ``force=True``
        to re-render.

        ``owner_key`` is the rate-limit client identity used to scope job lists
        so one client cannot enumerate another's renders.
        """
        with self._lock:
            self._purge_locked()
            if dedupe:
                for j in self._jobs.values():
                    if (
                        j.status in ("queued", "running")
                        and j.scenario_id == scenario_id
                        and j.choice_id == choice_id
                        and bool(j.use_llm) == bool(use_llm)
                        and not j.cancel_requested
                    ):
                        # Attribute shared deduped job to this requester as well
                        # so both clients can see it in their scoped list.
                        if owner_key and not j.owner_key:
                            j.owner_key = owner_key
                        return j, True
            # Disk cache hit — skip queue slot and GPU entirely
            if not force:
                cached = find_cached_video(scenario_id, choice_id)
                if cached is not None:
                    now = time.time()
                    # Match full-render job results: size, duration, ladder summary
                    metrics = read_cached_video_metrics(cached)
                    result_payload: dict[str, Any] = {
                        "media_url": media_url_for(scenario_id, choice_id, cached.name),
                        "segments": None,
                        "mock_media": None,
                        "cached": True,
                    }
                    if "bytes" in metrics:
                        result_payload["bytes"] = metrics["bytes"]
                    if "duration_s" in metrics:
                        result_payload["duration_s"] = metrics["duration_s"]
                    if "cache" in metrics:
                        result_payload["cache"] = metrics["cache"]
                        # Prefer segments count from ladder when known
                        result_payload["segments"] = metrics["cache"].get("segments")
                    job = VideoJob(
                        id=uuid.uuid4().hex[:16],
                        scenario_id=scenario_id,
                        choice_id=choice_id,
                        use_llm=use_llm,
                        owner_key=owner_key,
                        status="completed",
                        stage="done",
                        pct=100.0,
                        message="Using existing render (cache hit)",
                        started_at=now,
                        finished_at=now,
                        result=result_payload,
                    )
                    self._jobs[job.id] = job
                    return job, False
            active = sum(
                1 for j in self._jobs.values() if j.status in ("queued", "running")
            )
            if active >= self.max_queued:
                raise RuntimeError(
                    f"video queue full ({self.max_queued} active jobs) — try later"
                )
            job = VideoJob(
                id=uuid.uuid4().hex[:16],
                scenario_id=scenario_id,
                choice_id=choice_id,
                use_llm=use_llm,
                owner_key=owner_key,
            )
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id)
        return job, False

    def get(self, job_id: str) -> Optional[VideoJob]:
        with self._lock:
            self._purge_locked()
            return self._jobs.get(job_id)

    def list_for_owner(self, owner_key: str, limit: int = 20) -> list[VideoJob]:
        """Jobs owned by this client only (privacy-scoped listing)."""
        with self._lock:
            self._purge_locked()
            if not owner_key:
                return []
            mine = [
                j
                for j in self._jobs.values()
                if j.owner_key and j.owner_key == owner_key
            ]
            mine.sort(key=lambda j: j.created_at, reverse=True)
            return mine[:limit]

    def visible_to(self, job: Optional[VideoJob], owner_key: str) -> bool:
        """Whether ``owner_key`` may poll/cancel this job.

        Jobs without ``owner_key`` (legacy / tests) remain readable so local
        tooling does not break. Owned jobs require an exact client key match.
        """
        if job is None:
            return False
        if not job.owner_key:
            return True
        return bool(owner_key) and job.owner_key == owner_key

    def to_public_enriched(self, job: VideoJob) -> dict[str, Any]:
        """Public job dict plus queue_position / jobs_ahead / eta_s for studio feedback.

        - running: queue_position=0, jobs_ahead=0;
          eta_s from work-based progress extrapolation (capped by deadline)
        - queued: 1-based position among queued (oldest first); jobs_ahead = position-1;
          eta_s ≈ jobs_ahead * ANOR_VIDEO_ETA_PER_JOB_S (heuristic for UX, not a SLA)
        - terminal: queue fields null
        """
        d = job.to_public()
        eta_per = _env_int("ANOR_VIDEO_ETA_PER_JOB_S", 120)
        with self._lock:
            live = self._jobs.get(job.id) or job
            status = live.status
            if status == "running":
                d["queue_position"] = 0
                d["jobs_ahead"] = 0
                d["eta_s"] = estimate_running_eta_s(
                    started_at=live.started_at,
                    pct=live.pct,
                    deadline_at=live.deadline_at,
                    eta_per_job_s=eta_per,
                )
            elif status == "queued":
                queued = sorted(
                    (j for j in self._jobs.values() if j.status == "queued"),
                    key=lambda j: j.created_at,
                )
                for i, j in enumerate(queued):
                    if j.id == live.id:
                        d["queue_position"] = i + 1
                        d["jobs_ahead"] = i
                        # Rough wait: each job ahead ≈ eta_per seconds of GPU/ffmpeg work
                        d["eta_s"] = int(i * eta_per) if eta_per > 0 else None
                        break
                else:
                    d["queue_position"] = None
                    d["jobs_ahead"] = None
                    d["eta_s"] = None
            else:
                d["queue_position"] = None
                d["jobs_ahead"] = None
                d["eta_s"] = None
        return d

    def list_recent(self, limit: int = 20) -> list[VideoJob]:
        with self._lock:
            self._purge_locked()
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.cancel_requested)

    def cancel(self, job_id: str) -> tuple[bool, str, Optional[VideoJob]]:
        """Request cancellation.

        Returns (ok, reason, job).
        - queued jobs flip to cancelled immediately
        - running jobs set cancel_requested; worker exits at next progress tick
        - terminal jobs return ok=False
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False, "not_found", None
            if job.status in ("completed", "failed", "cancelled", "timed_out"):
                return False, "already_terminal", job
            job.cancel_requested = True
            job.updated_at = time.time()
            if job.status == "queued":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled before start"
                job.finished_at = time.time()
            else:
                job.message = "Cancel requested — stopping at next segment…"
            return True, "cancel_requested", job

    def _update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        stage: Optional[str] = None,
        pct: Optional[float] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if pct is not None:
                job.pct = pct
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if result is not None:
                job.result = result
            job.updated_at = time.time()

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job.cancel_requested or job.status == "cancelled":
                job.status = "cancelled"
                job.stage = "cancelled"
                job.message = "Cancelled before start"
                job.finished_at = time.time()
                job.updated_at = time.time()
                return
            scenario_id = job.scenario_id
            choice_id = job.choice_id
            use_llm = job.use_llm
            job.status = "running"
            job.started_at = time.time()
            job.deadline_at = job.started_at + float(self.timeout_s)
            job.stage = "starting"
            job.message = f"Worker picked up job (timeout {self.timeout_s}s)"
            job.pct = 1.0
            job.updated_at = time.time()
            deadline_at = job.deadline_at

        def on_progress(stage: str, pct: float, message: str) -> None:
            if self.is_cancel_requested(job_id):
                raise JobCancelled("cancelled by user")
            if deadline_at is not None and time.time() > deadline_at:
                raise JobTimedOut(
                    f"render exceeded {self.timeout_s}s wall-clock limit"
                )
            self._update(job_id, stage=stage, pct=pct, message=message, status="running")

        lock_fh: Optional[TextIO] = None
        path_lock: Optional[threading.Lock] = None
        try:
            # Fail fast before burning LLM/image cycles
            ok, dep_msg = check_render_dependencies(force=True)
            if not ok:
                raise RuntimeError(dep_msg)

            # Import here so module import stays light for unit tests
            from pipeline.config import PipelineConfig
            from pipeline.video_pipeline import render_video

            cfg = PipelineConfig.from_env()
            out_dir = ROOT / "outputs" / "videos" / f"{scenario_id}-{choice_id}"
            # Serialize writers for this scenario-choice (cross-process when fcntl works)
            lock_fh, path_lock = acquire_render_lock(out_dir)
            self._update(
                job_id,
                stage="starting",
                pct=2.0,
                message="Acquired render lock",
                status="running",
            )
            result = render_video(
                scenario_id,
                choice_id=choice_id,
                out_dir=out_dir,
                cfg=cfg,
                use_llm=use_llm,
                on_progress=on_progress,
            )
            # Race: cancel arrived after last progress tick
            if self.is_cancel_requested(job_id):
                raise JobCancelled("cancelled by user")
            if deadline_at is not None and time.time() > deadline_at:
                raise JobTimedOut(
                    f"render exceeded {self.timeout_s}s wall-clock limit"
                )

            # Public-safe result — never expose absolute filesystem paths to clients
            rel_mp4 = f"{scenario_id}-{choice_id}/{result.out_mp4.name}"
            # Cost-ladder summary only (ints) — no host paths or cache keys
            cache_pub = None
            raw_cache = getattr(result, "cache", None)
            if isinstance(raw_cache, dict):
                cache_pub = {
                    "still_hits": int(raw_cache.get("still_hits") or 0),
                    "tts_hits": int(raw_cache.get("tts_hits") or 0),
                    "clip_hits": int(raw_cache.get("clip_hits") or 0),
                    "segments": int(
                        raw_cache.get("segments")
                        if raw_cache.get("segments") is not None
                        else len(result.segments or [])
                    ),
                }
            payload = {
                "media_url": f"/media/videos/{rel_mp4}",
                "segments": len(result.segments),
                "mock_media": result.mock_media,
            }
            # Deliverable metrics (public-safe ints/floats only)
            try:
                ob = getattr(result, "out_mp4_bytes", None)
                if ob is None and result.out_mp4 is not None:
                    ob = int(Path(result.out_mp4).stat().st_size)
                if ob is not None and int(ob) >= 0:
                    payload["bytes"] = int(ob)
            except (OSError, TypeError, ValueError):
                pass
            try:
                ds = getattr(result, "duration_s", None)
                if ds is not None and float(ds) > 0:
                    payload["duration_s"] = round(float(ds), 2)
            except (TypeError, ValueError):
                pass
            if cache_pub is not None:
                payload["cache"] = cache_pub
                # Friendly complete message when any ladder stage was reused
                hits = (
                    cache_pub["still_hits"]
                    + cache_pub["tts_hits"]
                    + cache_pub["clip_hits"]
                )
                if hits > 0:
                    complete_msg = (
                        f"Render complete — reused {cache_pub['still_hits']} still"
                        f"{'' if cache_pub['still_hits'] == 1 else 's'}, "
                        f"{cache_pub['tts_hits']} TTS, "
                        f"{cache_pub['clip_hits']} clip"
                        f"{'' if cache_pub['clip_hits'] == 1 else 's'}"
                    )
                else:
                    complete_msg = "Render complete"
            else:
                complete_msg = "Render complete"
            completed_ok = False
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    if job.cancel_requested:
                        job.status = "cancelled"
                        job.stage = "cancelled"
                        job.message = "Cancelled"
                        job.finished_at = time.time()
                        job.updated_at = time.time()
                    else:
                        job.status = "completed"
                        job.stage = "done"
                        job.pct = 100.0
                        job.message = complete_msg
                        job.result = payload
                        job.finished_at = time.time()
                        job.updated_at = time.time()
                        completed_ok = True
            # New MP4 on disk — drop catalog available-flag cache immediately
            # (mtime fingerprint alone can lag on coarse filesystems within TTL).
            if completed_ok:
                try:
                    from webapp.server import clear_catalog_cache

                    clear_catalog_cache()
                except Exception:
                    pass
        except JobCancelled:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.message = "Cancelled"
                    job.cancel_requested = True
                    job.finished_at = time.time()
                    job.updated_at = time.time()
        except JobTimedOut as e:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = "timed_out"
                    job.stage = "timeout"
                    job.message = "Timed out"
                    job.error = sanitize_public_error(e)
                    job.finished_at = time.time()
                    job.updated_at = time.time()
        except Exception as e:
            # Keep full text in process logs for operators
            sys.stderr.write(f"[forked-history] video job {job_id} failed: {e!s}\n")
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    if job.cancel_requested:
                        job.status = "cancelled"
                        job.stage = "cancelled"
                        job.message = "Cancelled"
                    else:
                        job.status = "failed"
                        job.stage = "error"
                        job.message = "Render failed"
                        job.error = sanitize_public_error(e)
                    job.finished_at = time.time()
                    job.updated_at = time.time()
        finally:
            release_render_lock(lock_fh, path_lock)


# Process-wide singleton
QUEUE = VideoJobQueue()
