"""The model-facing seam of the pipeline: real models in the worker, stubs in tests."""

from importlib import metadata
from pathlib import Path
from typing import Protocol

from auraltrans.config import settings
from auraltrans.speech.asr import ASRBackend
from auraltrans.speech.diarize import PIPELINE_ID, DiarizationResult


class Diarizer(Protocol):
    def diarize(
        self, audio_path: Path, min_speakers: int | None = None, max_speakers: int | None = None
    ) -> DiarizationResult: ...


class Models(Protocol):
    def asr(self) -> ASRBackend: ...
    def diarizer(self) -> Diarizer: ...
    def versions(self) -> dict[str, str]: ...


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


class LoadedModels:
    """Loads Whisper and pyannote once, on first use, and keeps them for the life of the worker."""

    def __init__(self) -> None:
        self._asr: ASRBackend | None = None
        self._diarizer: Diarizer | None = None

    def asr(self) -> ASRBackend:
        if self._asr is None:
            from auraltrans.speech.asr import FasterWhisperBackend

            self._asr = FasterWhisperBackend(
                settings.asr_model, settings.asr_device, settings.asr_compute_type
            )
        return self._asr

    def diarizer(self) -> Diarizer:
        if self._diarizer is None:
            from auraltrans.speech.diarize import PyannoteDiarizer

            self._diarizer = PyannoteDiarizer(settings.hf_token, settings.asr_device)
        return self._diarizer

    def warm_up(self) -> None:
        self.asr()
        self.diarizer()

    def versions(self) -> dict[str, str]:
        return {
            "asr": f"faster-whisper {_version('faster-whisper')} / {settings.asr_model} "
            f"{settings.asr_compute_type} on {settings.asr_device}",
            "diarization": f"{PIPELINE_ID} (pyannote.audio {_version('pyannote.audio')})",
        }
