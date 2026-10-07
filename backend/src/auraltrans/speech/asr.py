"""ASR interface and the faster-whisper backend."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from auraltrans.schemas import Word


class AsrSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word]


class AsrResult(BaseModel):
    language: str
    language_probability: float
    duration_s: float
    model: str
    segments: list[AsrSegment]

    @property
    def words(self) -> list[Word]:
        return [w for seg in self.segments for w in seg.words]


class ASRBackend(Protocol):
    def transcribe(self, audio_path: Path, language: str | None = None) -> AsrResult: ...


class FasterWhisperBackend:
    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        vad_filter: bool = True,
    ):
        from faster_whisper import WhisperModel

        self.model_size = model_size
        self.vad_filter = vad_filter
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._batched = None
        if device == "cuda":
            from faster_whisper import BatchedInferencePipeline

            self._batched = BatchedInferencePipeline(model=self._model)  # type: ignore[no-untyped-call]

    def transcribe(self, audio_path: Path, language: str | None = None) -> AsrResult:
        runner = self._batched or self._model
        segments, info = runner.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            vad_filter=self.vad_filter,
            condition_on_previous_text=False,
        )
        out: list[AsrSegment] = []
        for seg in segments:
            words = [
                Word(text=w.word.strip(), start=w.start, end=max(w.end, w.start), probability=w.probability)
                for w in (seg.words or [])
                if w.word.strip()
            ]
            out.append(AsrSegment(start=seg.start, end=seg.end, text=seg.text.strip(), words=words))
        return AsrResult(
            language=info.language,
            language_probability=info.language_probability,
            duration_s=info.duration,
            model=self.model_size,
            segments=out,
        )
