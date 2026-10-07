"""Validated insight payload. `utterance_id` in a Citation is the transcript's `uN` id."""

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    utterance_id: str


class _Cited(BaseModel):
    text: str
    evidence: list[Citation] = Field(default_factory=list)
    # "unverified": the cited lines exist but share little wording (or numbers) with the claim.
    status: Literal["verified", "unverified"] = "verified"


class SummaryPoint(_Cited):
    pass


class Decision(_Cited):
    pass


class OpenQuestion(_Cited):
    pass


class ActionItem(BaseModel):
    task: str
    owner_speaker_id: str | None = None
    due_text: str | None = None
    evidence: list[Citation] = Field(default_factory=list)
    status: Literal["verified", "unverified"] = "verified"


class Chapter(BaseModel):
    title: str
    start_uid: str
    end_uid: str


class Insights(BaseModel):
    summary: SummaryPoint | None = None
    key_points: list[SummaryPoint] = []
    decisions: list[Decision] = []
    action_items: list[ActionItem] = []
    chapters: list[Chapter] = []
    open_questions: list[OpenQuestion] = []
