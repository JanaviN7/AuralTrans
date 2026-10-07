import io
import json
from pathlib import Path

import pytest

from auraltrans.exporters import (
    EXPORTERS,
    ExportData,
    ExportSpeakerStats,
    ExportUtterance,
    ExportWord,
)
from auraltrans.exporters.common import clock, srt_time, vtt_time
from auraltrans.exporters.subtitles import cues_for
from auraltrans.storage.local import LocalStorage


def words(text: str, start: float, step: float = 0.4) -> list[ExportWord]:
    return [
        ExportWord(t, start + i * step, start + (i + 1) * step - 0.05) for i, t in enumerate(text.split())
    ]


def sample() -> ExportData:
    return ExportData(
        title="Weekly sync",
        language="en",
        duration_s=75.0,
        speakers=[ExportSpeakerStats("Priya", 30.0, 0.6, 2, 140.0), ExportSpeakerStats("Sam", 20.0, 0.4, 1, 120.0)],
        utterances=[
            ExportUtterance(0, "Priya", 0.0, 2.0, "Hello there everyone.", words("Hello there everyone.", 0.0)),
            ExportUtterance(1, "Sam", 2.5, 4.0, "Thanks, café time?", words("Thanks, café time?", 2.5)),
        ],
    )


# --- time formatting ---------------------------------------------------------------------


def test_time_formats() -> None:
    assert srt_time(3661.5) == "01:01:01,500"
    assert vtt_time(3661.5) == "01:01:01.500"
    assert clock(75) == "1:15" and clock(3661) == "1:01:01"


def test_rounding_never_produces_sixty_seconds() -> None:
    assert srt_time(59.9996) == "00:01:00,000"
    assert vtt_time(119.9999) == "00:02:00.000"
    assert srt_time(-1) == "00:00:00,000"


# --- subtitles ---------------------------------------------------------------------------


def test_srt_numbering_timing_and_speaker_prefix() -> None:
    out = EXPORTERS["srt"][0](sample())
    blocks = out.strip().split("\n\n")
    assert blocks[0].splitlines()[0] == "1" and blocks[1].splitlines()[0] == "2"
    assert "00:00:00,000 --> 00:00:01,150" in blocks[0]
    assert "Priya: Hello there everyone." in out and "Sam: Thanks, café time?" in out


def test_vtt_has_header_and_voice_tags() -> None:
    out = EXPORTERS["vtt"][0](sample())
    assert out.startswith("WEBVTT\n\n")
    assert "<v Priya>" in out and "." in out.split("-->")[0]  # dot, not comma, in VTT times


def test_long_utterance_is_split_into_cues_with_word_times() -> None:
    long_text = " ".join(f"word{i}" for i in range(60))
    utt = ExportUtterance(0, "A", 0.0, 30.0, long_text, words(long_text, 0.0))
    cues = cues_for(utt)
    assert len(cues) > 1
    assert all(c.end - c.start <= 7.5 for c in cues)
    assert all(len(c.text) <= 90 for c in cues)
    assert " ".join(c.text for c in cues) == long_text


def test_utterance_without_words_is_one_cue() -> None:
    cues = cues_for(ExportUtterance(0, "A", 1.0, 3.0, "no word times"))
    assert [(c.start, c.end, c.text) for c in cues] == [(1.0, 3.0, "no word times")]


def test_zero_length_cue_gets_a_visible_duration() -> None:
    data = ExportData("t", None, None, [ExportUtterance(0, "A", 5.0, 5.0, "blip")])
    assert "00:00:05,000 --> 00:00:05,500" in EXPORTERS["srt"][0](data)


# --- text formats ------------------------------------------------------------------------


def test_txt_and_md() -> None:
    txt = EXPORTERS["txt"][0](sample())
    assert txt.splitlines()[0] == "[0:00] Priya: Hello there everyone."
    md = EXPORTERS["md"][0](sample())
    assert md.startswith("# Weekly sync") and "| Priya | 0:30 | 60% | 2 | 140 |" in md
    assert "**Sam** (0:02): Thanks" in md


def test_json_round_trips_with_unicode() -> None:
    data = json.loads(EXPORTERS["json"][0](sample()))
    assert data["utterances"][1]["text"] == "Thanks, café time?"
    assert data["speakers"][0]["name"] == "Priya" and len(data["utterances"][0]["words"]) == 3


def test_every_format_is_registered_with_a_content_type() -> None:
    assert set(EXPORTERS) == {"srt", "vtt", "txt", "md", "json"}
    assert all(ct and ext for _, ct, ext in EXPORTERS.values())


# --- storage -----------------------------------------------------------------------------


def test_storage_round_trip_and_atomic_write(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    s.put("recordings/r1/artifacts/asr.json", b'{"a": 1}')
    assert s.get("recordings/r1/artifacts/asr.json") == b'{"a": 1}'
    assert s.exists("recordings/r1/artifacts/asr.json")
    assert not list(tmp_path.rglob("*.part"))
    assert s.put_stream("recordings/r1/original.wav", io.BytesIO(b"x" * 1000)) == 1000


def test_storage_rejects_path_traversal(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path / "root")
    with pytest.raises(ValueError):
        s.put("../evil.txt", b"x")
    with pytest.raises(ValueError):
        s.local_path("a/../../evil")


def test_delete_prefix_removes_the_whole_recording_folder(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    s.put("recordings/r1/a.txt", b"1")
    s.put("recordings/r1/artifacts/b.txt", b"2")
    s.put("recordings/r2/c.txt", b"3")
    s.delete_prefix("recordings/r1")
    assert not s.exists("recordings/r1/a.txt") and s.exists("recordings/r2/c.txt")
    s.delete_prefix("recordings/never-existed")  # no error
