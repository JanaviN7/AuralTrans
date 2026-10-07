"""Database reads shared by the routes: job view, speaker naming, export data."""

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auraltrans.api.schemas import JobOut, SpeakerOut, StageOut, StageStatus
from auraltrans.db.models import Job, Recording, Speaker, Utterance
from auraltrans.exporters import ExportData, ExportSpeakerStats, ExportUtterance, ExportWord
from auraltrans.pipeline.stages import STAGES, key
from auraltrans.speech.analytics import Analytics
from auraltrans.storage import Storage


def job_out(job: Job) -> JobOut:
    timings = job.stage_timings or {}
    stages: list[StageOut] = []
    for stage in STAGES:
        entry = timings.get(stage.name)
        status: StageStatus
        if entry:
            status, seconds = entry["status"], entry.get("seconds")
        elif job.status == "running" and job.current_stage == stage.name:
            status, seconds = "running", None
        else:
            status, seconds = "pending", None
        stages.append(StageOut(name=stage.name, label=stage.label, status=status, seconds=seconds))
    return JobOut(
        id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        progress=job.progress or 0.0,
        attempts=job.attempts or 0,
        error=job.error,
        stages=stages,
    )


def speakers_out(session: Session, recording_id: uuid.UUID) -> list[SpeakerOut]:
    """Speakers numbered by when they first speak, so the default names read 'Speaker 1, 2, ...'."""
    first = (
        select(Utterance.speaker_id, func.min(Utterance.idx).label("first_idx"))
        .where(Utterance.recording_id == recording_id)
        .group_by(Utterance.speaker_id)
        .subquery()
    )
    rows = session.execute(
        select(Speaker)
        .outerjoin(first, first.c.speaker_id == Speaker.id)
        .where(Speaker.recording_id == recording_id)
        .order_by(first.c.first_idx.nulls_last(), Speaker.label)
    ).scalars()
    return [
        SpeakerOut(
            id=sp.id,
            label=sp.label,
            name=sp.display_name or f"Speaker {n}",
            display_name=sp.display_name,
            color=sp.color,
            talk_time_s=sp.talk_time_s or 0.0,
        )
        for n, sp in enumerate(rows, start=1)
    ]


def load_analytics(storage: Storage, recording_id: uuid.UUID) -> Analytics | None:
    analytics_key = key(recording_id, "artifacts/analytics.json")
    if not storage.exists(analytics_key):
        return None
    return Analytics.model_validate(json.loads(storage.get(analytics_key)))


def export_data(session: Session, storage: Storage, recording: Recording) -> ExportData:
    speakers = speakers_out(session, recording.id)
    names = {sp.id: sp.name for sp in speakers}
    utterances = session.scalars(
        select(Utterance).where(Utterance.recording_id == recording.id).order_by(Utterance.idx)
    ).all()
    analytics = load_analytics(storage, recording.id)
    stats: list[ExportSpeakerStats] = []
    for sp in speakers:
        a = analytics.speakers.get(sp.label) if analytics else None
        stats.append(
            ExportSpeakerStats(
                name=sp.name,
                talk_time_s=a.talk_time_s if a else sp.talk_time_s,
                talk_share=a.talk_share if a else 0.0,
                turns=a.turns if a else 0,
                words_per_minute=a.words_per_minute if a else 0.0,
            )
        )
    return ExportData(
        title=recording.title,
        language=recording.language,
        duration_s=recording.duration_s,
        speakers=stats,
        utterances=[
            ExportUtterance(
                idx=u.idx,
                speaker=names.get(u.speaker_id, "Unknown") if u.speaker_id else "Unknown",
                start=u.start_s,
                end=u.end_s,
                text=u.text,
                # Edited text no longer matches the original word timings, so cue splitting falls back
                # to the utterance as a whole.
                words=[] if u.edited else [ExportWord(w["text"], w["start"], w["end"]) for w in u.words],
            )
            for u in utterances
        ],
    )
