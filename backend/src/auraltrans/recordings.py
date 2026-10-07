"""Recording lifecycle shared by the API and the tests: create from an upload, retry, delete."""

import json
import uuid
from pathlib import PurePath
from typing import BinaryIO

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auraltrans.config import settings
from auraltrans.db.models import Job, Recording
from auraltrans.pipeline.stages import STAGE_NAMES, invalidate_from, key, prefix
from auraltrans.storage import Storage

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".webm"}
RECORDING_TYPES = {"meeting", "interview", "lecture", "call"}


class UploadError(Exception):
    """A rejected upload. `status` is the HTTP status the API should answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class _LimitedReader:
    def __init__(self, stream: BinaryIO, limit: int):
        self.stream, self.limit, self.read_bytes = stream, limit, 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.stream.read(size)
        self.read_bytes += len(chunk)
        if self.read_bytes > self.limit:
            raise UploadError(f"file is larger than the {self.limit // (1024 * 1024)} MB limit", 413)
        return chunk


def create_recording(
    session: Session,
    storage: Storage,
    *,
    filename: str,
    stream: BinaryIO,
    title: str | None = None,
    recording_type: str = "meeting",
    language: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> tuple[Recording, Job]:
    name = PurePath(filename or "").name
    suffix = PurePath(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadError(f"unsupported file type {suffix or '(none)'}; use one of {sorted(ALLOWED_EXTENSIONS)}")
    if recording_type not in RECORDING_TYPES:
        raise UploadError(f"type must be one of {sorted(RECORDING_TYPES)}")
    if min_speakers and max_speakers and min_speakers > max_speakers:
        raise UploadError("min speakers cannot be larger than max speakers")

    recording_id = uuid.uuid4()
    original = key(recording_id, f"original{suffix}")
    try:
        size = storage.put_stream(original, _LimitedReader(stream, settings.max_upload_mb * 1024 * 1024))  # type: ignore[arg-type]
    except UploadError:
        storage.delete_prefix(prefix(recording_id))
        raise
    if size == 0:
        storage.delete_prefix(prefix(recording_id))
        raise UploadError("the uploaded file is empty")

    storage.put(
        key(recording_id, "options.json"),
        json.dumps({"min_speakers": min_speakers or None, "max_speakers": max_speakers or None}).encode(),
    )
    recording = Recording(
        id=recording_id,
        title=(title or "").strip() or PurePath(name).stem or "Untitled recording",
        type=recording_type,
        status="queued",
        language=None if language in (None, "", "auto") else language,
        source_filename=name,
        storage_prefix=prefix(recording_id),
    )
    session.add(recording)
    session.flush()
    job = Job(recording_id=recording_id, status="queued", progress=0.0)
    session.add(job)
    session.flush()
    return recording, job


def retry_job(session: Session, storage: Storage, job_id: uuid.UUID, from_stage: str | None = None) -> Job:
    """Re-queue a failed job. Stages before `from_stage` keep their checkpoints."""
    job = session.get(Job, job_id)
    if job is None:
        raise LookupError("job not found")
    if job.status == "running":
        raise UploadError("job is running; wait for it to finish", 409)
    stage = from_stage or job.current_stage or STAGE_NAMES[0]
    if stage not in STAGE_NAMES:
        raise UploadError(f"unknown stage {stage!r}; use one of {list(STAGE_NAMES)}")
    invalidate_from(session, storage, job.recording_id, stage)
    timings = {k: v for k, v in (job.stage_timings or {}).items() if STAGE_NAMES.index(k) < STAGE_NAMES.index(stage)}
    job.stage_timings = timings
    job.status = "queued"
    job.error = None
    job.worker_id = None
    job.progress = 0.0
    rec = session.get(Recording, job.recording_id)
    if rec is not None:
        rec.status = "queued"
    return job


def delete_recording(session: Session, storage: Storage, recording_id: uuid.UUID) -> bool:
    recording = session.get(Recording, recording_id)
    if recording is None:
        return False
    if session.scalars(select(Job).where(Job.recording_id == recording_id, Job.status == "running")).first():
        raise UploadError("recording is being processed; wait for it to finish", 409)
    session.execute(delete(Recording).where(Recording.id == recording_id))  # children cascade
    storage.delete_prefix(prefix(recording_id))
    return True
