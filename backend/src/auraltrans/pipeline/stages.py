"""Stage definitions and checkpoint bookkeeping.

A stage is complete when every output file exists in storage and the `artifacts` table holds a row
with the same SHA-256. Anything else (missing file, edited file, no row) means the stage re-runs.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auraltrans.db.models import Artifact
from auraltrans.storage import Storage


@dataclass(frozen=True)
class Stage:
    name: str
    label: str
    outputs: tuple[str, ...]  # paths relative to recordings/{id}/


STAGES: tuple[Stage, ...] = (
    Stage("prepare_audio", "Preparing audio", ("audio_16k.wav",)),
    Stage("asr", "Transcribing", ("artifacts/asr.json",)),
    Stage("diarize", "Finding speakers", ("artifacts/diarization.rttm", "artifacts/diarization_exclusive.rttm")),
    Stage("align", "Aligning words to speakers", ("artifacts/aligned.json",)),
    Stage("analytics", "Speaker analytics", ("artifacts/analytics.json",)),
)
STAGE_NAMES = tuple(s.name for s in STAGES)


def prefix(recording_id: uuid.UUID) -> str:
    return f"recordings/{recording_id}"


def key(recording_id: uuid.UUID, relative: str) -> str:
    return f"{prefix(recording_id)}/{relative}"


def sha256_of(storage: Storage, storage_key: str) -> str:
    digest = hashlib.sha256()
    with storage.local_path(storage_key).open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def stage_by_name(name: str) -> Stage:
    for stage in STAGES:
        if stage.name == name:
            return stage
    raise KeyError(name)


def checkpoint_valid(session: Session, storage: Storage, recording_id: uuid.UUID, stage: Stage) -> bool:
    rows = {
        a.storage_key: a.sha256
        for a in session.scalars(
            select(Artifact).where(Artifact.recording_id == recording_id, Artifact.stage == stage.name)
        )
    }
    for rel in stage.outputs:
        storage_key = key(recording_id, rel)
        if not storage.exists(storage_key) or rows.get(storage_key) != sha256_of(storage, storage_key):
            return False
    return True


def save_checkpoint(session: Session, storage: Storage, recording_id: uuid.UUID, stage: Stage) -> None:
    """Record the outputs of a finished stage. Called only after every output file is written."""
    session.execute(
        delete(Artifact).where(Artifact.recording_id == recording_id, Artifact.stage == stage.name)
    )
    for rel in stage.outputs:
        storage_key = key(recording_id, rel)
        session.add(
            Artifact(
                recording_id=recording_id,
                stage=stage.name,
                storage_key=storage_key,
                sha256=sha256_of(storage, storage_key),
            )
        )


def invalidate_from(session: Session, storage: Storage, recording_id: uuid.UUID, from_stage: str) -> None:
    """Drop the checkpoints of `from_stage` and every later stage so they re-run."""
    start = STAGE_NAMES.index(from_stage)
    for stage in STAGES[start:]:
        session.execute(
            delete(Artifact).where(Artifact.recording_id == recording_id, Artifact.stage == stage.name)
        )
        for rel in stage.outputs:
            storage_key = key(recording_id, rel)
            if storage.exists(storage_key):
                storage.local_path(storage_key).unlink()
