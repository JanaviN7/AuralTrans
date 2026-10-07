"""Job claim loop: Postgres is the queue (SELECT ... FOR UPDATE SKIP LOCKED)."""

import logging
import socket
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Self

from sqlalchemy import select, update

from auraltrans.config import settings
from auraltrans.db.models import Job, Recording
from auraltrans.db.session import session_scope
from auraltrans.pipeline.models import Models
from auraltrans.pipeline.runner import run_job
from auraltrans.storage import Storage

log = logging.getLogger(__name__)


def worker_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def requeue_stale_jobs(stale_after_s: float) -> int:
    """Jobs whose worker stopped heartbeating (crash, kill) go back to the queue.

    They resume from their checkpoints, so finished stages are not repeated.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_s)
    with session_scope() as s:
        result = s.execute(
            update(Job)
            .where(Job.status == "running", Job.locked_at < cutoff)
            .values(status="queued", worker_id=None)
        )
        return int(getattr(result, "rowcount", 0) or 0)


def claim_next(wid: str) -> uuid.UUID | None:
    """Atomically take the oldest queued job; concurrent workers never get the same one."""
    with session_scope() as s:
        job = s.scalars(
            select(Job)
            .join(Recording, Recording.id == Job.recording_id)
            .where(Job.status == "queued")
            .order_by(Recording.created_at)
            .limit(1)
            .with_for_update(skip_locked=True, of=Job)
        ).first()
        if job is None:
            return None
        job.status = "running"
        job.worker_id = wid
        job.locked_at = datetime.now(UTC)
        job.attempts = (job.attempts or 0) + 1
        return job.id


class _Heartbeat:
    """Touches locked_at while a long stage runs, so a live job is never mistaken for a dead one."""

    def __init__(self, job_id: uuid.UUID, interval_s: float):
        self.job_id, self.interval_s = job_id, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                with session_scope() as s:
                    s.execute(update(Job).where(Job.id == self.job_id).values(locked_at=datetime.now(UTC)))
            except Exception:  # noqa: BLE001 - a missed beat is harmless; the next one will land
                log.warning("heartbeat failed for job %s", self.job_id)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def run_once(storage: Storage, models: Models, wid: str | None = None) -> bool:
    """Claim and process at most one job. Returns False when the queue is empty."""
    wid = wid or worker_id()
    requeue_stale_jobs(settings.job_stale_after_s)
    job_id = claim_next(wid)
    if job_id is None:
        return False
    log.info("worker %s picked up job %s", wid, job_id)
    with _Heartbeat(job_id, settings.worker_heartbeat_s):
        run_job(job_id, storage, models)
    return True


def run_forever(storage: Storage, models: Models) -> None:
    wid = worker_id()
    log.info("worker %s started; polling every %.1fs", wid, settings.worker_poll_s)
    while True:
        try:
            if not run_once(storage, models, wid):
                time.sleep(settings.worker_poll_s)
        except KeyboardInterrupt:
            log.info("worker stopping")
            return
        except Exception:  # keep the worker alive through transient DB errors
            log.exception("worker loop error")
            time.sleep(settings.worker_poll_s * 5)
