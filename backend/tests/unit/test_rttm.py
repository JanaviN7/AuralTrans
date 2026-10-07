from pathlib import Path

from auraltrans.schemas import Turn
from auraltrans.speech.diarize import read_rttm, write_rttm


def test_rttm_roundtrip(tmp_path: Path) -> None:
    turns = [Turn(speaker="SPEAKER_01", start=5.0, end=8.5), Turn(speaker="SPEAKER_00", start=0.0, end=4.25)]
    path = tmp_path / "x.rttm"
    write_rttm(turns, path)
    back = read_rttm(path)
    assert [(t.speaker, t.start, t.end) for t in back] == [("SPEAKER_00", 0.0, 4.25), ("SPEAKER_01", 5.0, 8.5)]
