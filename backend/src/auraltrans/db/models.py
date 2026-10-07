import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _fk_recording() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("recordings.id", ondelete="CASCADE"), index=True
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[uuid.UUID] = _id()
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(20), default="meeting")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    duration_s: Mapped[float | None] = mapped_column(Float)
    language: Mapped[str | None] = mapped_column(String(16))
    source_filename: Mapped[str] = mapped_column(String(500))
    storage_prefix: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = _created()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(40))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    stage_timings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(100))


class Speaker(Base):
    __tablename__ = "speakers"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    label: Mapped[str] = mapped_column(String(40))
    display_name: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(16))
    talk_time_s: Mapped[float] = mapped_column(Float, default=0.0)


class Utterance(Base):
    __tablename__ = "utterances"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    idx: Mapped[int] = mapped_column(Integer)
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("speakers.id", ondelete="SET NULL")
    )
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    words: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    has_overlap: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    __table_args__ = (Index("ix_utterances_tsv", "tsv", postgresql_using="gin"),)


class Insight(Base):
    __tablename__ = "insights"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    version: Mapped[int] = mapped_column(Integer, default=1)
    template: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="done", server_default="done")
    error: Mapped[str | None] = mapped_column(Text)
    # Hash of the utterance texts the insights were generated from; a mismatch means "stale".
    transcript_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class QATurn(Base):
    __tablename__ = "qa_turns"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(200))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    abstain_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = _created()


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[uuid.UUID] = _id()
    purpose: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = _created()


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = _id()
    recording_id: Mapped[uuid.UUID] = _fk_recording()
    stage: Mapped[str] = mapped_column(String(40))
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
