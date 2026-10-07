"""Stand-ins for the real models: canned two-speaker conversation, with call counters."""

import json
from collections.abc import Callable
from pathlib import Path

from auraltrans.llm import LLMResult
from auraltrans.schemas import Turn, Word
from auraltrans.speech.asr import AsrResult, AsrSegment
from auraltrans.speech.audio import PreparedAudio
from auraltrans.speech.diarize import DiarizationResult

DURATION_S = 9.0


def _words(text: str, start: float, step: float = 0.4) -> list[Word]:
    return [Word(text=t, start=start + i * step, end=start + (i + 1) * step - 0.05) for i, t in enumerate(text.split())]


FIRST = _words("Hello everyone. What does air pollution mean?", 0.0)  # 0.0 - 2.75 s
SECOND = _words("Air pollution means harmful substances in the air.", 4.5)  # 4.5 - 8.5 s


class FakeASR:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio_path: Path, language: str | None = None) -> AsrResult:
        self.calls += 1
        seg = AsrSegment(
            start=0.0, end=8.5, text="Hello everyone. What does air pollution mean? Air pollution means ...",
            words=[*FIRST, *SECOND],
        )
        return AsrResult(
            language=language or "en", language_probability=0.99, duration_s=DURATION_S, model="fake", segments=[seg]
        )


class FakeDiarizer:
    def __init__(self, fail_with: BaseException | None = None) -> None:
        self.calls = 0
        self.fail_with = fail_with  # raised on the first call only

    def diarize(self, audio_path: Path, min_speakers: int | None = None, max_speakers: int | None = None) -> DiarizationResult:
        self.calls += 1
        if self.fail_with is not None and self.calls == 1:
            raise self.fail_with
        turns = [Turn(speaker="SPEAKER_00", start=0.0, end=4.0), Turn(speaker="SPEAKER_01", start=4.2, end=8.6)]
        return DiarizationResult(exclusive=turns, overlap=[*turns, Turn(speaker="SPEAKER_01", start=2.5, end=4.4)])


class FakeModels:
    def __init__(self, diarizer_fail_with: BaseException | None = None) -> None:
        self._asr = FakeASR()
        self._diarizer = FakeDiarizer(diarizer_fail_with)

    def asr(self) -> FakeASR:
        return self._asr

    def diarizer(self) -> FakeDiarizer:
        return self._diarizer

    def versions(self) -> dict[str, str]:
        return {"asr": "fake", "diarization": "fake"}


def fake_prepare_audio(src: Path, dst: Path, max_duration_s: float = 0) -> PreparedAudio:
    """Copies the upload instead of calling ffmpeg, so pipeline tests need no audio tooling."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    return PreparedAudio(path=dst, duration_s=DURATION_S)


class ScriptedLLM:
    """Returns canned replies in order (a str, a dict -> JSON, or a callable); the last one repeats."""

    model = "fake-llm"

    def __init__(self, *replies: "str | dict | Callable[[str, str], str]") -> None:  # type: ignore[type-arg]
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResult:
        self.calls.append((system, user))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if callable(reply):
            text = reply(system, user)
        else:
            text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResult(text=text, model=self.model, input_tokens=len(user) // 4, output_tokens=len(text) // 4, latency_ms=5)
