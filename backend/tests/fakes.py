"""Stand-ins for the real models: canned two-speaker conversation, with call counters."""

from pathlib import Path

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
