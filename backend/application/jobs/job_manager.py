"""Background Job Manager with CPU/IO pools, deduplication, and progress tracking.

Architectural Guarantees:
- Separate CPU pool (max_workers=2) and IO pool (max_workers=8) preventing starvation.
- Deduplication via `job_key` — duplicate requests return active job without re-submitting.
- Graceful cancellation support via threading.Event / Future cancellation.
- Thread-safe job state updates and optional SSE progress notification.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from backend.domain.ports import IEventBroker

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """State of an asynchronous background job."""

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_key: Optional[str] = None
    pool_type: str = "io"
    status: str = "queued"  # "queued", "running", "completed", "failed", "cancelled"
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_requested: bool = False
    _future: Optional[concurrent.futures.Future[Any]] = field(
        default=None, repr=False
    )

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")


class JobManager:
    """Thread-safe Job Manager managing CPU and I/O execution pools."""

    def __init__(
        self,
        cpu_workers: int = 2,
        io_workers: int = 8,
        event_broker: Optional[IEventBroker] = None,
    ) -> None:
        self.cpu_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=cpu_workers,
            thread_name_prefix="job-cpu",
        )
        self.io_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=io_workers,
            thread_name_prefix="job-io",
        )
        self.event_broker = event_broker
        self._jobs: Dict[str, Job] = {}
        self._key_to_id: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._is_shutdown = False

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        job_key: Optional[str] = None,
        pool: str = "io",
        **kwargs: Any,
    ) -> Job:
        """Submit a background job to either CPU or IO pool with key-based deduplication."""
        with self._lock:
            if self._is_shutdown:
                raise RuntimeError("JobManager has already been shut down")

            # Deduplication: return active job if key exists and job is not done
            if job_key:
                existing_id = self._key_to_id.get(job_key)
                if existing_id and existing_id in self._jobs:
                    existing_job = self._jobs[existing_id]
                    if not existing_job.is_done:
                        logger.debug(
                            "Returning active job %s for key %s",
                            existing_id,
                            job_key,
                        )
                        return existing_job

            pool_type = "cpu" if pool == "cpu" else "io"
            executor = self.cpu_pool if pool_type == "cpu" else self.io_pool

            job = Job(
                job_key=job_key,
                pool_type=pool_type,
                status="queued",
            )
            self._jobs[job.job_id] = job
            if job_key:
                self._key_to_id[job_key] = job.job_id

            future = executor.submit(self._run_job, job, fn, *args, **kwargs)
            job._future = future
            return job

    def _run_job(
        self,
        job: Job,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        with self._lock:
            if job.cancel_requested or job.status == "cancelled":
                job.status = "cancelled"
                job.finished_at = time.time()
                return None
            job.status = "running"
            job.started_at = time.time()

        self._notify_event(
            "job.started",
            {"job_id": job.job_id, "job_key": job.job_key},
        )

        try:
            res = fn(*args, **kwargs)
            with self._lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                else:
                    job.status = "completed"
                    job.progress = 1.0
                    job.result = res
                job.finished_at = time.time()

            self._notify_event(
                "job.completed",
                {"job_id": job.job_id, "job_key": job.job_key, "status": job.status},
            )
            return res
        except Exception as exc:
            logger.exception("Job %s (%s) failed with error: %s", job.job_id, job.job_key, exc)
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = time.time()

            self._notify_event(
                "job.failed",
                {"job_id": job.job_id, "job_key": job.job_key, "error": str(exc)},
            )
            return None

    def get_job(self, job_id: str) -> Optional[Job]:
        """Fetch job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def get_job_by_key(self, job_key: str) -> Optional[Job]:
        """Fetch job by unique job_key."""
        with self._lock:
            job_id = self._key_to_id.get(job_key)
            if job_id:
                return self._jobs.get(job_id)
            return None

    def update_progress(
        self, job_id: str, progress: float, message: str = ""
    ) -> None:
        """Update job progress and publish SSE notification."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.is_done:
                return
            job.progress = max(0.0, min(1.0, progress))
            if message:
                job.message = message

        self._notify_event(
            "job.progress",
            {
                "job_id": job_id,
                "job_key": job.job_key,
                "progress": job.progress,
                "message": job.message,
            },
        )

    def cancel(self, job_id: str) -> bool:
        """Request cancellation of a queued or running job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.is_done:
                return False

            job.cancel_requested = True
            if job._future and job._future.cancel():
                job.status = "cancelled"
                job.finished_at = time.time()
                return True
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = time.time()
                return True
            # Running job: cancel_requested is marked; cooperative cancellation
            return True

    def _notify_event(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_broker is not None:
            try:
                self.event_broker.publish(event_type, data)
            except Exception as e:
                logger.warning("Failed to publish SSE event %s: %s", event_type, e)

    def shutdown(self, wait: bool = True) -> None:
        """Cleanly shutdown both CPU and IO thread pools."""
        with self._lock:
            self._is_shutdown = True
        self.cpu_pool.shutdown(wait=wait)
        self.io_pool.shutdown(wait=wait)
        logger.info("JobManager shut down successfully.")
