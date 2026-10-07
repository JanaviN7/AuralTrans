"""Insights and Ask endpoints. Both need a configured language model (503 otherwise)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from auraltrans.api.schemas import AskCitationOut, AskIn, AskTurnOut, InsightsOut
from auraltrans.ask.service import TranscriptTooLong, ask
from auraltrans.db.models import Insight, QATurn, Recording, Utterance
from auraltrans.db.session import session_scope
from auraltrans.insights.generate import is_stuck, run_insights, start_run
from auraltrans.insights.transcript import load_lines, transcript_hash
from auraltrans.llm import LLM, get_llm
from auraltrans.schemas.insights import Insights

router = APIRouter(prefix="/api")
LLMDep = Annotated[LLM | None, Depends(get_llm)]


def _need_llm(llm: LLM | None) -> LLM:
    if llm is None:
        raise HTTPException(
            503, "No language model is configured. Set LLM_BASE_URL and LLM_MODEL (and LLM_API_KEY) in backend/.env."
        )
    return llm


def _ready(s, recording_id: uuid.UUID) -> Recording:  # type: ignore[no-untyped-def]
    rec = s.get(Recording, recording_id)
    if rec is None:
        raise HTTPException(404, "recording not found")
    if rec.status != "ready":
        raise HTTPException(409, f"recording is {rec.status}, not ready")
    return rec  # type: ignore[no-any-return]


def _insights_out(s, recording_id: uuid.UUID) -> InsightsOut:  # type: ignore[no-untyped-def]
    rows = s.scalars(
        select(Insight).where(Insight.recording_id == recording_id).order_by(Insight.version.desc())
    ).all()
    if not rows:
        return InsightsOut(status="none")
    latest = rows[0]
    status, error = latest.status, latest.error
    if is_stuck(latest):
        status, error = "failed", "Generation was interrupted. Try again."
    done = next((r for r in rows if r.status == "done"), None)
    out = InsightsOut(status=status, error=error, model=latest.model, version=latest.version, created_at=latest.created_at)
    if done is not None:
        out.model, out.version, out.created_at = done.model, done.version, done.created_at
        out.data = Insights.model_validate(done.payload)
        out.validation = done.validation
        out.stale = done.transcript_hash != transcript_hash(load_lines(s, recording_id))
    return out


@router.get("/recordings/{recording_id}/insights", response_model=InsightsOut)
def get_insights(recording_id: uuid.UUID) -> InsightsOut:
    with session_scope() as s:
        _ready(s, recording_id)
        return _insights_out(s, recording_id)


@router.post("/recordings/{recording_id}/insights", response_model=InsightsOut, status_code=202)
def generate_insights(recording_id: uuid.UUID, tasks: BackgroundTasks, llm: LLMDep) -> InsightsOut:
    model = _need_llm(llm)
    with session_scope() as s:
        _ready(s, recording_id)
        current = _insights_out(s, recording_id)
        if current.status == "running":
            raise HTTPException(409, "insights are already being generated")
    insight_id = start_run(recording_id, model.model)  # committed before the task starts
    tasks.add_task(run_insights, insight_id, model)
    with session_scope() as s:
        return _insights_out(s, recording_id)


def _turn_out(s, t: QATurn, utterances: dict[str, Utterance]) -> AskTurnOut:  # type: ignore[no-untyped-def]
    cites = []
    for c in t.citations:
        u = utterances.get(c["uid"])
        if u is not None:  # utterance still exists (edits keep ids stable)
            cites.append(
                AskCitationOut(
                    uid=c["uid"], utterance_id=u.id, speaker_id=u.speaker_id,
                    start_s=u.start_s, end_s=u.end_s, quote=c.get("quote", ""),
                )
            )
    return AskTurnOut(
        id=t.id, question=t.question, answer=t.answer, abstained=t.abstained,
        abstain_reason=t.abstain_reason,
        citations=cites, model=t.model, created_at=t.created_at,
    )


def _utterance_map(s, recording_id: uuid.UUID) -> dict[str, Utterance]:  # type: ignore[no-untyped-def]
    rows = s.scalars(select(Utterance).where(Utterance.recording_id == recording_id)).all()
    return {f"u{u.idx}": u for u in rows}


@router.get("/recordings/{recording_id}/ask", response_model=list[AskTurnOut])
def ask_history(recording_id: uuid.UUID) -> list[AskTurnOut]:
    with session_scope() as s:
        _ready(s, recording_id)
        utts = _utterance_map(s, recording_id)
        turns = s.scalars(
            select(QATurn).where(QATurn.recording_id == recording_id).order_by(QATurn.created_at, QATurn.id)
        ).all()
        return [_turn_out(s, t, utts) for t in turns]


@router.post("/recordings/{recording_id}/ask", response_model=AskTurnOut)
def ask_question(recording_id: uuid.UUID, body: AskIn, llm: LLMDep) -> AskTurnOut:
    model = _need_llm(llm)
    question = body.question.strip()
    with session_scope() as s:
        rec = _ready(s, recording_id)
        title = rec.title
        lines = load_lines(s, recording_id)
    try:
        result = ask(model, question, title, lines)  # slow network call: no DB session held open
    except TranscriptTooLong as exc:
        raise HTTPException(413, str(exc)) from exc
    with session_scope() as s:
        turn = QATurn(
            recording_id=recording_id, question=question, answer=result.answer,
            citations=result.citations, model=result.model, latency_ms=result.latency_ms,
            abstained=result.abstained, abstain_reason=result.abstain_reason,
        )
        s.add(turn)
        s.flush()
        s.refresh(turn)
        return _turn_out(s, turn, _utterance_map(s, recording_id))
