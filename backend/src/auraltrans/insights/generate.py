"""Insight generation: chunk the transcript, call the model, validate, persist."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from auraltrans.config import settings
from auraltrans.db.models import Insight, Recording
from auraltrans.db.session import session_scope
from auraltrans.insights import prompts
from auraltrans.insights.transcript import chunk, load_lines, render, transcript_hash
from auraltrans.insights.validate import RawInsights, merge_raw, validate_insights
from auraltrans.llm import LLM, complete_validated

# A "running" row older than this is treated as interrupted (the API process was restarted).
RUN_TIMEOUT = timedelta(minutes=15)


def is_stuck(row: Insight) -> bool:
    return row.status == "running" and datetime.now(UTC) - row.created_at > RUN_TIMEOUT


def start_run(recording_id: uuid.UUID, model: str) -> uuid.UUID:
    """Create the 'running' row. Call before scheduling run_insights."""
    with session_scope() as s:
        version = (
            s.scalar(select(func.max(Insight.version)).where(Insight.recording_id == recording_id)) or 0
        ) + 1
        row = Insight(
            recording_id=recording_id,
            version=version,
            template="meeting",
            model=model,
            prompt_version=prompts.PROMPT_VERSION,
            payload={},
            status="running",
        )
        s.add(row)
        s.flush()
        return row.id


def run_insights(insight_id: uuid.UUID, llm: LLM) -> None:
    """Fill in a 'running' row. Never raises: any failure is recorded on the row."""
    try:
        payload, report, digest = _generate(insight_id, llm)
        _finish(insight_id, "done", payload=payload, validation=report, digest=digest)
    except Exception as exc:  # noqa: BLE001 - the row is the error channel for a background task
        _finish(insight_id, "failed", error=str(exc)[:500] or type(exc).__name__)


def _generate(insight_id: uuid.UUID, llm: LLM) -> tuple[dict, dict, str]:  # type: ignore[type-arg]
    with session_scope() as s:
        row = s.get(Insight, insight_id)
        assert row is not None
        rec = s.get(Recording, row.recording_id)
        assert rec is not None
        lines = load_lines(s, rec.id)
        speakers = _speaker_names(s, rec.id)
        title, kind = rec.title, rec.type
    if not lines:
        raise ValueError("the transcript is empty, so there is nothing to analyse")

    chunks = chunk(lines, settings.llm_chunk_chars)
    parts: list[RawInsights] = []
    repaired = 0
    for i, window in enumerate(chunks, 1):
        user = prompts.user_prompt(
            title, kind, list(speakers), render(window), i, len(chunks), window[0].uid, window[-1].uid
        )
        raw, was_repaired = complete_validated(
            llm, prompts.SYSTEM, user, RawInsights,
            purpose="insights", prompt_version=prompts.PROMPT_VERSION, max_tokens=2500,
        )
        parts.append(raw)
        repaired += was_repaired
    insights, report = validate_insights(merge_raw(parts), lines, speakers)
    report.update(chunks=len(chunks), repaired_calls=repaired, utterances=len(lines))
    return insights.model_dump(), report, transcript_hash(lines)


def _speaker_names(s, recording_id: uuid.UUID) -> dict[str, str]:  # type: ignore[no-untyped-def]
    from auraltrans.api.queries import speakers_out

    return {sp.name: str(sp.id) for sp in speakers_out(s, recording_id)}


def _finish(
    insight_id: uuid.UUID, status: str, *, payload: dict | None = None,  # type: ignore[type-arg]
    validation: dict | None = None, digest: str | None = None, error: str | None = None,  # type: ignore[type-arg]
) -> None:
    with session_scope() as s:
        row = s.get(Insight, insight_id)
        if row is None:  # recording deleted while running
            return
        row.status = status
        row.error = error
        if payload is not None:
            row.payload = payload
            row.validation = validation or {}
            row.transcript_hash = digest
