from pydantic import BaseModel, Field, model_validator


class Word(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _end_after_start(self) -> "Word":
        if self.end < self.start:
            raise ValueError("word end before start")
        return self


class Speaker(BaseModel):
    id: str  # diarization label, e.g. SPEAKER_00
    display_name: str | None = None
    color: str | None = None
    talk_time_s: float = 0.0


class Utterance(BaseModel):
    id: str  # stable id used in citations, e.g. u17
    idx: int
    speaker: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    words: list[Word] = []
    has_overlap: bool = False
    edited: bool = False


class Transcript(BaseModel):
    recording_id: str | None = None
    language: str | None = None
    duration_s: float | None = None
    speakers: list[Speaker] = []
    utterances: list[Utterance] = []
