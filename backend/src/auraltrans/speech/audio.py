"""ffmpeg decode to 16 kHz mono WAV with EBU R128 loudness normalization."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_DURATION_S = 2 * 60 * 60
SAMPLE_RATE = 16_000


class AudioError(Exception):
    pass


@dataclass
class PreparedAudio:
    path: Path
    duration_s: float


def _require(binary: str) -> str:
    found = shutil.which(binary)
    if not found:
        raise AudioError(f"{binary} not found on PATH; install ffmpeg")
    return found


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            _require("ffprobe"), "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AudioError(f"cannot read {path.name}: {result.stderr.strip()}")
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError) as exc:
        raise AudioError(f"no audio duration found in {path.name}") from exc


def prepare_audio(src: Path, dst: Path, max_duration_s: float = MAX_DURATION_S) -> PreparedAudio:
    """Decode any audio/video container to 16 kHz mono 16-bit WAV at -16 LUFS."""
    duration = probe_duration(src)
    if duration > max_duration_s:
        raise AudioError(f"recording is {duration / 60:.0f} min; the limit is {max_duration_s / 60:.0f} min")
    dst.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _require("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(dst),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AudioError(f"ffmpeg failed: {result.stderr.strip()}")
    return PreparedAudio(path=dst, duration_s=probe_duration(dst))
