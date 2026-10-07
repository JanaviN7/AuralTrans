import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from auraltrans.speech.audio import AudioError, prepare_audio

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make_tone(path: Path, seconds: float = 2.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", str(path)],
        check=True,
    )


@pytest.mark.parametrize("ext", ["wav", "mp3", "m4a", "webm"])
def test_converts_formats_to_16k_mono_wav(tmp_path: Path, ext: str) -> None:
    src = tmp_path / f"in.{ext}"
    _make_tone(src)
    out = prepare_audio(src, tmp_path / "out" / "audio_16k.wav")
    with wave.open(str(out.path)) as wav:
        assert wav.getframerate() == 16_000 and wav.getnchannels() == 1
    assert 1.8 < out.duration_s < 2.3


def test_rejects_too_long(tmp_path: Path) -> None:
    src = tmp_path / "in.wav"
    _make_tone(src, 3.0)
    with pytest.raises(AudioError, match="limit"):
        prepare_audio(src, tmp_path / "o.wav", max_duration_s=1.0)


def test_rejects_garbage(tmp_path: Path) -> None:
    src = tmp_path / "bad.mp3"
    src.write_bytes(b"not audio")
    with pytest.raises(AudioError):
        prepare_audio(src, tmp_path / "o.wav")
