"""API response and request models. These also drive the generated TypeScript client."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

StageStatus = Literal["pending", "running", "done", "skipped", "failed"]


class StageOut(BaseModel):
    name: str
    label: str
    status: StageStatus
    seconds: float | None = None


class JobOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "done", "failed"]
    current_stage: str | None
    progress: float
    attempts: int
    error: str | None
    stages: list[StageOut]


class RecordingOut(BaseModel):
    id: uuid.UUID
    title: str
    type: str
    status: Literal["queued", "processing", "ready", "failed"]
    duration_s: float | None
    language: str | None
    source_filename: str
    created_at: datetime
    job: JobOut | None = None


class SpeakerOut(BaseModel):
    id: uuid.UUID
    label: str
    name: str  # what the UI shows: display_name, else "Speaker N"
    display_name: str | None
    color: str | None
    talk_time_s: float


class WordOut(BaseModel):
    text: str
    start: float
    end: float
    probability: float | None = None


class UtteranceOut(BaseModel):
    id: uuid.UUID
    idx: int
    uid: str  # "u<idx>", the id used in citations
    speaker_id: uuid.UUID | None
    start_s: float
    end_s: float
    text: str
    words: list[WordOut]
    has_overlap: bool
    edited: bool


class TranscriptOut(BaseModel):
    recording_id: uuid.UUID
    language: str | None
    duration_s: float | None
    speakers: list[SpeakerOut]
    utterances: list[UtteranceOut]


class SpeakerStatsOut(BaseModel):
    speaker_id: uuid.UUID
    name: str
    color: str | None
    talk_time_s: float
    talk_share: float
    turns: int
    words: int
    words_per_minute: float
    longest_monologue_s: float
    interruptions_made: int


class AnalyticsOut(BaseModel):
    duration_s: float
    silence_ratio: float
    speakers: list[SpeakerStatsOut]


class SpeakerPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class UtterancePatch(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class FeaturesOut(BaseModel):
    insights: bool
    ask: bool


class HealthOut(BaseModel):
    status: Literal["ok"]
    features: FeaturesOut
