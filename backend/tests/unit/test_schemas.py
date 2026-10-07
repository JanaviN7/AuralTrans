import pytest
from pydantic import ValidationError

from auraltrans.schemas import (
    ActionItem,
    Citation,
    Insights,
    Speaker,
    Transcript,
    Utterance,
    Word,
)


def _sample() -> Transcript:
    words = [Word(text="Hello", start=0.0, end=0.4, probability=0.98), Word(text="there", start=0.4, end=0.9)]
    return Transcript(
        recording_id="r1",
        language="en",
        duration_s=1.0,
        speakers=[Speaker(id="SPEAKER_00", display_name="Priya")],
        utterances=[Utterance(id="u1", idx=0, speaker="SPEAKER_00", start=0.0, end=0.9, text="Hello there", words=words)],
    )


def test_transcript_roundtrip() -> None:
    t = _sample()
    assert Transcript.model_validate_json(t.model_dump_json()) == t


def test_word_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError):
        Word(text="x", start=2.0, end=1.0)


def test_insights_roundtrip() -> None:
    ins = Insights(
        action_items=[ActionItem(task="Send report", owner_speaker_id="SPEAKER_00", evidence=[Citation(utterance_id="u1")])]
    )
    assert Insights.model_validate_json(ins.model_dump_json()) == ins
