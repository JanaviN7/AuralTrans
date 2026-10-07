"""pyannote diarization wrapper plus RTTM read/write."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from auraltrans.schemas import Turn

PIPELINE_ID = "pyannote/speaker-diarization-community-1"


class DiarizationResult(BaseModel):
    exclusive: list[Turn]  # one active speaker at a time; used for word alignment
    overlap: list[Turn]  # overlap-aware; used for analytics


def write_rttm(turns: list[Turn], path: Path, uri: str = "audio") -> None:
    lines = [
        f"SPEAKER {uri} 1 {t.start:.3f} {t.end - t.start:.3f} <NA> <NA> {t.speaker} <NA> <NA>"
        for t in sorted(turns, key=lambda t: t.start)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_rttm(path: Path) -> list[Turn]:
    turns: list[Turn] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0] == "SPEAKER":
            start, dur = float(parts[3]), float(parts[4])
            turns.append(Turn(speaker=parts[7], start=start, end=start + dur))
    return turns


class PyannoteDiarizer:
    def __init__(self, hf_token: str, device: str = "cpu"):
        if not hf_token:
            raise ValueError("HF_TOKEN is required for the gated pyannote pipeline")
        import torch
        from pyannote.audio import Pipeline

        pipeline: Any = Pipeline.from_pretrained(PIPELINE_ID, token=hf_token)
        if pipeline is None:
            raise RuntimeError(
                "could not load the pyannote pipeline; accept its terms on Hugging Face"
            )
        pipeline.to(torch.device(device))
        self._pipeline: Any = pipeline

    def diarize(
        self,
        audio_path: Path,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> DiarizationResult:
        output = self._pipeline(str(audio_path), min_speakers=min_speakers, max_speakers=max_speakers)

        def to_turns(annotation: Any) -> list[Turn]:
            return [
                Turn(speaker=str(label), start=seg.start, end=seg.end)
                for seg, _, label in annotation.itertracks(yield_label=True)
            ]

        return DiarizationResult(
            exclusive=to_turns(output.exclusive_speaker_diarization),
            overlap=to_turns(output.speaker_diarization),
        )
