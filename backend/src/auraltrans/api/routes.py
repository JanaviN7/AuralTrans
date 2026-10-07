"""REST endpoints plus the SSE progress stream. Handlers commit their own transaction before returning."""

import asyncio
import mimetypes
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select, text

from auraltrans import recordings
from auraltrans.api.queries import export_data, job_out, load_analytics, speakers_out
from auraltrans.api.schemas import (
    AnalyticsOut,
    FeaturesOut,
    HealthOut,
    JobOut,
    RecordingOut,
    SpeakerOut,
    SpeakerPatch,
    SpeakerStatsOut,
    TranscriptOut,
    UtteranceOut,
    UtterancePatch,
    WordOut,
)
from auraltrans.db.models import Job, Recording, Speaker, Utterance
from auraltrans.db.session import session_scope
from auraltrans.exporters import EXPORTERS
from auraltrans.llm import LLM, get_llm
from auraltrans.pipeline.stages import key
from auraltrans.storage import Storage, get_storage

router = APIRouter(prefix="/api")
StorageDep = Annotated[Storage, Depends(get_storage)]


def _recording_out(rec: Recording, job: Job | None) -> RecordingOut:
    return RecordingOut(
        id=rec.id,
        title=rec.title,
        type=rec.type,
        status=rec.status,
        duration_s=rec.duration_s,
        language=rec.language,
        source_filename=rec.source_filename,
        created_at=rec.created_at,
        job=job_out(job) if job else None,
    )


def _utterance_out(u: Utterance) -> UtteranceOut:
    return UtteranceOut(
        id=u.id,
        idx=u.idx,
        uid=f"u{u.idx}",
        speaker_id=u.speaker_id,
        start_s=u.start_s,
        end_s=u.end_s,
        text=u.text,
        words=[WordOut(**w) for w in u.words],
        has_overlap=u.has_overlap,
        edited=u.edited,
    )


def _require_ready(rec: Recording | None) -> Recording:
    if rec is None:
        raise HTTPException(404, "recording not found")
    if rec.status != "ready":
        raise HTTPException(409, f"recording is {rec.status}, not ready")
    return rec


@router.get("/health", response_model=HealthOut)
def health(llm: Annotated[LLM | None, Depends(get_llm)]) -> HealthOut:
    # Insights and Ask need a configured language model; the UI reads these flags.
    on = llm is not None
    return HealthOut(status="ok", features=FeaturesOut(insights=on, ask=on))


# --- recordings --------------------------------------------------------------------------------


@router.post("/recordings", response_model=RecordingOut, status_code=201)
def upload_recording(
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    type: Annotated[str, Form()] = "meeting",
    language: Annotated[str | None, Form()] = None,
    min_speakers: Annotated[int | None, Form(ge=1, le=20)] = None,
    max_speakers: Annotated[int | None, Form(ge=1, le=20)] = None,
) -> RecordingOut:
    with session_scope() as s:
        rec, job = recordings.create_recording(
            s,
            storage,
            filename=file.filename or "",
            stream=file.file,
            title=title,
            recording_type=type,
            language=language,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        return _recording_out(rec, job)


@router.get("/recordings", response_model=list[RecordingOut])
def list_recordings(q: str | None = None, status: str | None = None) -> list[RecordingOut]:
    with session_scope() as s:
        stmt = (
            select(Recording, Job)
            .outerjoin(Job, Job.recording_id == Recording.id)
            .order_by(Recording.created_at.desc())
        )
        if status:
            stmt = stmt.where(Recording.status == status)
        if q and q.strip():
            term = q.strip()
            in_transcript = select(Utterance.recording_id).where(
                Utterance.tsv.op("@@")(func.plainto_tsquery("english", term))
            )
            stmt = stmt.where(or_(Recording.title.ilike(f"%{term}%"), Recording.id.in_(in_transcript)))
        return [_recording_out(rec, job) for rec, job in s.execute(stmt).all()]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
def get_recording(recording_id: uuid.UUID) -> RecordingOut:
    with session_scope() as s:
        rec = s.get(Recording, recording_id)
        if rec is None:
            raise HTTPException(404, "recording not found")
        job = s.scalars(select(Job).where(Job.recording_id == recording_id)).first()
        return _recording_out(rec, job)


@router.delete("/recordings/{recording_id}", status_code=204)
def delete_recording(recording_id: uuid.UUID, storage: StorageDep) -> Response:
    with session_scope() as s:
        if not recordings.delete_recording(s, storage, recording_id):
            raise HTTPException(404, "recording not found")
    return Response(status_code=204)


@router.get("/recordings/{recording_id}/audio")
def get_audio(recording_id: uuid.UUID, storage: StorageDep) -> FileResponse:
    """The 16 kHz copy once prepared (its timestamps are the reference), else the original upload."""
    with session_scope() as s:
        rec = s.get(Recording, recording_id)
        if rec is None:
            raise HTTPException(404, "recording not found")
        suffix = PurePath(rec.source_filename).suffix.lower()
    wav = key(recording_id, "audio_16k.wav")
    if storage.exists(wav):
        return FileResponse(storage.local_path(wav), media_type="audio/wav")
    original = key(recording_id, f"original{suffix}")
    if not storage.exists(original):
        raise HTTPException(404, "audio not found")
    media_type = mimetypes.guess_type(f"x{suffix}")[0] or "application/octet-stream"
    return FileResponse(storage.local_path(original), media_type=media_type)


# --- jobs --------------------------------------------------------------------------------------


def _job_snapshot(job_id: uuid.UUID) -> JobOut | None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        return job_out(job) if job else None


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID) -> JobOut:
    snapshot = _job_snapshot(job_id)
    if snapshot is None:
        raise HTTPException(404, "job not found")
    return snapshot


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: uuid.UUID, request: Request) -> StreamingResponse:
    """Server-Sent Events: a `progress` event whenever the job changes, then `end`."""

    async def stream() -> AsyncIterator[str]:
        last: str | None = None
        quiet = 0.0
        while not await request.is_disconnected():
            snapshot = await run_in_threadpool(_job_snapshot, job_id)
            if snapshot is None:
                yield 'event: error\ndata: {"detail": "job not found"}\n\n'
                return
            payload = snapshot.model_dump_json()
            if payload != last:
                yield f"event: progress\ndata: {payload}\n\n"
                last, quiet = payload, 0.0
            if snapshot.status in ("done", "failed"):
                yield "event: end\ndata: {}\n\n"
                return
            quiet += 0.5
            if quiet >= 15:
                yield ": ping\n\n"  # keeps proxies from closing an idle stream
                quiet = 0.0
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, storage: StorageDep, from_stage: str | None = None) -> JobOut:
    with session_scope() as s:
        job = recordings.retry_job(s, storage, job_id, from_stage)
        return job_out(job)


# --- transcript --------------------------------------------------------------------------------


@router.get("/recordings/{recording_id}/transcript", response_model=TranscriptOut)
def get_transcript(recording_id: uuid.UUID) -> TranscriptOut:
    with session_scope() as s:
        rec = _require_ready(s.get(Recording, recording_id))
        utterances = s.scalars(
            select(Utterance).where(Utterance.recording_id == recording_id).order_by(Utterance.idx)
        ).all()
        return TranscriptOut(
            recording_id=rec.id,
            language=rec.language,
            duration_s=rec.duration_s,
            speakers=speakers_out(s, recording_id),
            utterances=[_utterance_out(u) for u in utterances],
        )


@router.patch("/recordings/{recording_id}/speakers/{speaker_id}", response_model=SpeakerOut)
def rename_speaker(recording_id: uuid.UUID, speaker_id: uuid.UUID, body: SpeakerPatch) -> SpeakerOut:
    with session_scope() as s:
        speaker = s.get(Speaker, speaker_id)
        if speaker is None or speaker.recording_id != recording_id:
            raise HTTPException(404, "speaker not found")
        speaker.display_name = (body.display_name or "").strip() or None
        s.flush()
        return next(sp for sp in speakers_out(s, recording_id) if sp.id == speaker_id)


@router.patch("/utterances/{utterance_id}", response_model=UtteranceOut)
def edit_utterance(utterance_id: uuid.UUID, body: UtterancePatch) -> UtteranceOut:
    with session_scope() as s:
        utt = s.get(Utterance, utterance_id)
        if utt is None:
            raise HTTPException(404, "utterance not found")
        new_text = body.text.strip()
        if not new_text:
            raise HTTPException(422, "text cannot be empty")
        utt.text, utt.edited = new_text, True
        s.flush()
        s.execute(
            text("UPDATE utterances SET tsv = to_tsvector('english', text) WHERE id = :id"), {"id": utterance_id}
        )
        return _utterance_out(utt)


@router.get("/recordings/{recording_id}/analytics", response_model=AnalyticsOut)
def get_analytics(recording_id: uuid.UUID, storage: StorageDep) -> AnalyticsOut:
    with session_scope() as s:
        _require_ready(s.get(Recording, recording_id))
        analytics = load_analytics(storage, recording_id)
        if analytics is None:
            raise HTTPException(404, "analytics not available")
        stats: list[SpeakerStatsOut] = []
        for sp in speakers_out(s, recording_id):
            a = analytics.speakers.get(sp.label)
            if a is None:
                continue
            stats.append(
                SpeakerStatsOut(
                    speaker_id=sp.id,
                    name=sp.name,
                    color=sp.color,
                    talk_time_s=a.talk_time_s,
                    talk_share=a.talk_share,
                    turns=a.turns,
                    words=a.words,
                    words_per_minute=a.words_per_minute,
                    longest_monologue_s=a.longest_monologue_s,
                    interruptions_made=a.interruptions_made,
                )
            )
        return AnalyticsOut(duration_s=analytics.duration_s, silence_ratio=analytics.silence_ratio, speakers=stats)


# --- export ------------------------------------------------------------------------------------


@router.get("/recordings/{recording_id}/export")
def export_recording(
    recording_id: uuid.UUID, storage: StorageDep, format: Annotated[str, Query()]
) -> Response:
    if format not in EXPORTERS:
        raise HTTPException(400, f"format must be one of {sorted(EXPORTERS)}")
    render, content_type, extension = EXPORTERS[format]
    with session_scope() as s:
        rec = _require_ready(s.get(Recording, recording_id))
        body = render(export_data(s, storage, rec))
        title = rec.title
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-") or "recording"
    return Response(
        content=body.encode("utf-8"),
        media_type=f"{content_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}.{extension}"'},
    )
