"""The five stage implementations. Each reads its inputs from storage and writes its outputs there."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, text, update

from auraltrans.db.models import Recording, Speaker, Utterance
from auraltrans.db.session import session_scope
from auraltrans.pipeline.models import Models
from auraltrans.pipeline.stages import key
from auraltrans.schemas import Speaker as SpeakerSchema
from auraltrans.schemas import Transcript
from auraltrans.speech.align import align
from auraltrans.speech.analytics import compute_analytics
from auraltrans.speech.asr import AsrResult
from auraltrans.speech.audio import prepare_audio
from auraltrans.speech.diarize import DiarizationResult, read_rttm, write_rttm
from auraltrans.storage import Storage

PALETTE = ["#4F7CFF", "#E5574C", "#2FA37A", "#E0A030", "#9B59D0", "#2AA7C9", "#D6609A", "#7A8B99"]


@dataclass
class Ctx:
    recording_id: uuid.UUID
    storage: Storage
    models: Models
    options: dict[str, Any]  # language, min_speakers, max_speakers


def _k(ctx: Ctx, relative: str) -> str:
    return key(ctx.recording_id, relative)


def _original_key(ctx: Ctx) -> str:
    with session_scope() as s:
        rec = s.get(Recording, ctx.recording_id)
        assert rec is not None
        suffix = "." + rec.source_filename.rsplit(".", 1)[-1].lower() if "." in rec.source_filename else ""
    return _k(ctx, f"original{suffix}")


def prepare_audio_stage(ctx: Ctx) -> None:
    prepared = prepare_audio(
        ctx.storage.local_path(_original_key(ctx)), ctx.storage.local_path(_k(ctx, "audio_16k.wav"))
    )
    with session_scope() as s:
        s.execute(update(Recording).where(Recording.id == ctx.recording_id).values(duration_s=prepared.duration_s))


def asr_stage(ctx: Ctx) -> None:
    result = ctx.models.asr().transcribe(ctx.storage.local_path(_k(ctx, "audio_16k.wav")), ctx.options.get("language"))
    ctx.storage.put(_k(ctx, "artifacts/asr.json"), result.model_dump_json().encode())
    with session_scope() as s:
        s.execute(update(Recording).where(Recording.id == ctx.recording_id).values(language=result.language))


def diarize_stage(ctx: Ctx) -> None:
    result = ctx.models.diarizer().diarize(
        ctx.storage.local_path(_k(ctx, "audio_16k.wav")),
        ctx.options.get("min_speakers"),
        ctx.options.get("max_speakers"),
    )
    # If a crash leaves only one file, no checkpoint row exists yet, so this stage simply re-runs.
    write_rttm(result.overlap, ctx.storage.local_path(_k(ctx, "artifacts/diarization.rttm")), uri="audio")
    write_rttm(result.exclusive, ctx.storage.local_path(_k(ctx, "artifacts/diarization_exclusive.rttm")), uri="audio")


def _load_diarization(ctx: Ctx) -> DiarizationResult:
    return DiarizationResult(
        exclusive=read_rttm(ctx.storage.local_path(_k(ctx, "artifacts/diarization_exclusive.rttm"))),
        overlap=read_rttm(ctx.storage.local_path(_k(ctx, "artifacts/diarization.rttm"))),
    )


def align_stage(ctx: Ctx) -> None:
    asr = AsrResult.model_validate_json(ctx.storage.get(_k(ctx, "artifacts/asr.json")))
    diar = _load_diarization(ctx)
    utterances = align(asr.words, diar.exclusive, diar.overlap)

    labels: list[str] = []
    for u in utterances:  # first-appearance order gives stable "Speaker 1, 2, ..." numbering
        if u.speaker not in labels:
            labels.append(u.speaker)
    transcript = Transcript(
        recording_id=str(ctx.recording_id),
        language=asr.language,
        duration_s=asr.duration_s,
        speakers=[SpeakerSchema(id=label, color=PALETTE[i % len(PALETTE)]) for i, label in enumerate(labels)],
        utterances=utterances,
    )
    ctx.storage.put(_k(ctx, "artifacts/aligned.json"), transcript.model_dump_json().encode())

    # Rows are rebuilt from scratch, so re-running this stage is idempotent.
    with session_scope() as s:
        s.execute(delete(Utterance).where(Utterance.recording_id == ctx.recording_id))
        s.execute(delete(Speaker).where(Speaker.recording_id == ctx.recording_id))
        ids: dict[str, uuid.UUID] = {}
        for sp in transcript.speakers:
            row = Speaker(recording_id=ctx.recording_id, label=sp.id, color=sp.color)
            s.add(row)
            s.flush()
            ids[sp.id] = row.id
        for u in utterances:
            s.add(
                Utterance(
                    recording_id=ctx.recording_id,
                    idx=u.idx,
                    speaker_id=ids[u.speaker],
                    start_s=u.start,
                    end_s=u.end,
                    text=u.text,
                    words=[w.model_dump() for w in u.words],
                    has_overlap=u.has_overlap,
                )
            )
        s.flush()
        s.execute(
            text("UPDATE utterances SET tsv = to_tsvector('english', text) WHERE recording_id = :rid"),
            {"rid": ctx.recording_id},
        )


def analytics_stage(ctx: Ctx) -> None:
    transcript = Transcript.model_validate_json(ctx.storage.get(_k(ctx, "artifacts/aligned.json")))
    diar = _load_diarization(ctx)
    stats = compute_analytics(transcript.utterances, transcript.duration_s or 0.0, diar.overlap)
    ctx.storage.put(_k(ctx, "artifacts/analytics.json"), stats.model_dump_json().encode())
    with session_scope() as s:
        for row in s.scalars(select(Speaker).where(Speaker.recording_id == ctx.recording_id)):
            if row.label in stats.speakers:
                row.talk_time_s = stats.speakers[row.label].talk_time_s


STEPS: dict[str, Callable[[Ctx], None]] = {
    "prepare_audio": prepare_audio_stage,
    "asr": asr_stage,
    "diarize": diarize_stage,
    "align": align_stage,
    "analytics": analytics_stage,
}


def load_options(storage: Storage, recording_id: uuid.UUID, language: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {"language": language}
    options_key = key(recording_id, "options.json")
    if storage.exists(options_key):
        options.update(json.loads(storage.get(options_key)))
    return options
