"""In-process async job queue for long-running video renders.

No Redis required — single-process ThreadPool style worker so the HTTP
handler returns immediately (202) and clients poll for progress.

Env:
  ANOR_VIDEO_MAX_CONCURRENT  (default 1)
  ANOR_VIDEO_MAX_QUEUED      (default 8)
  ANOR_VIDEO_JOB_TTL_S       (default 3600) — finished jobs retained this long
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


class JobCancelled(Exception):
    """Raised cooperatively when a running render is cancelled."""


@dataclass
class VideoJob:
    id: str
    scenario_id: str
    choice_id: str
    use_llm: bool
    status: str = "queued"  # queued | running | completed | failed | cancelled
    stage: str = "queued"
    pct: float = 0.0
    message: str = "Queued"
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_requested: bool = False

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
            return {
                "max_concurrent": self.max_concurrent,
                "max_queued": self.max_queued,
                "ttl_s": self.ttl_s,
                "jobs": len(self._jobs),
                "by_status": statuses,
            }

    def enqueue(
        self,
        scenario_id: str,
        choice_id: str,
        use_llm: bool = False,
    ) -> VideoJob:
        with self._lock:
            self._purge_locked()
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
            )
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id)
        return job

    def get(self, job_id: str) -> Optional[VideoJob]:
        with self._lock:
            self._purge_locked()
            return self._jobs.get(job_id)

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
            if job.status in ("completed", "failed", "cancelled"):
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
            job.stage = "starting"
            job.message = "Worker picked up job"
            job.pct = 1.0
            job.updated_at = time.time()

        def on_progress(stage: str, pct: float, message: str) -> None:
            if self.is_cancel_requested(job_id):
                raise JobCancelled("cancelled by user")
            self._update(job_id, stage=stage, pct=pct, message=message, status="running")

        try:
            # Import here so module import stays light for unit tests
            from pipeline.config import PipelineConfig
            from pipeline.video_pipeline import render_video

            cfg = PipelineConfig.from_env()
            out_dir = ROOT / "outputs" / "videos" / f"{scenario_id}-{choice_id}"
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

            # Public-safe result — never expose absolute filesystem paths to clients
            rel_mp4 = f"{scenario_id}-{choice_id}/{result.out_mp4.name}"
            payload = {
                "media_url": f"/media/videos/{rel_mp4}",
                "segments": len(result.segments),
                "mock_media": result.mock_media,
            }
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
                        job.message = "Render complete"
                        job.result = payload
                        job.finished_at = time.time()
                        job.updated_at = time.time()
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
        except Exception as e:
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
                        job.error = str(e)[:400]
                    job.finished_at = time.time()
                    job.updated_at = time.time()


# Process-wide singleton
QUEUE = VideoJobQueue()
