"""Runs one job through the stages, skipping any stage whose checkpoint is still valid."""

import logging
import time
import traceback
import uuid
from typing import Any

from sqlalchemy import update

from auraltrans.db.models import Job, Recording
from auraltrans.db.session import session_scope
from auraltrans.pipeline.models import Models
from auraltrans.pipeline.stages import (
    STAGES,
    checkpoint_valid,
    save_checkpoint,
)
from auraltrans.pipeline.steps import STEPS, Ctx, load_options
from auraltrans.storage import Storage

log = logging.getLogger(__name__)


def _set_job(job_id: uuid.UUID, **values: Any) -> None:
    with session_scope() as s:
        s.execute(update(Job).where(Job.id == job_id).values(**values))


def _record_timing(job_id: uuid.UUID, stage: str, seconds: float, status: str) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        assert job is not None
        timings = dict(job.stage_timings or {})
        timings[stage] = {"seconds": round(seconds, 3), "status": status}
        job.stage_timings = timings  # reassign so SQLAlchemy sees the JSONB change


def run_job(job_id: uuid.UUID, storage: Storage, models: Models) -> bool:
    """Process a claimed job. Returns True on success; failures are recorded on the job."""
    with session_scope() as s:
        job = s.get(Job, job_id)
        assert job is not None
        rec = s.get(Recording, job.recording_id)
        assert rec is not None
        recording_id, language = rec.id, rec.language
        s.execute(update(Recording).where(Recording.id == recording_id).values(status="processing"))
    _set_job(job_id, status="running", error=None, model_versions=models.versions())

    ctx = Ctx(recording_id, storage, models, load_options(storage, recording_id, language))
    total = len(STAGES)
    for index, stage in enumerate(STAGES):
        _set_job(job_id, current_stage=stage.name, progress=index / total)
        with session_scope() as s:
            reusable = checkpoint_valid(s, storage, recording_id, stage)
        if reusable:
            _record_timing(job_id, stage.name, 0.0, "skipped")
            continue
        started = time.perf_counter()
        try:
            STEPS[stage.name](ctx)
            with session_scope() as s:
                save_checkpoint(s, storage, recording_id, stage)
        except Exception as exc:  # noqa: BLE001 - recorded on the job so the UI can show it and offer a retry
            log.error("job %s failed in %s:\n%s", job_id, stage.name, traceback.format_exc())
            _record_timing(job_id, stage.name, time.perf_counter() - started, "failed")
            _set_job(job_id, status="failed", error=f"{stage.label}: {exc}", progress=index / total)
            with session_scope() as s:
                s.execute(update(Recording).where(Recording.id == recording_id).values(status="failed"))
            return False
        _record_timing(job_id, stage.name, time.perf_counter() - started, "done")

    _set_job(job_id, status="done", progress=1.0, current_stage=None)
    with session_scope() as s:
        s.execute(update(Recording).where(Recording.id == recording_id).values(status="ready"))
    return True
