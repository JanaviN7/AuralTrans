"""Shared types and time formatting for exporters."""

from dataclasses import dataclass, field


@dataclass
class ExportWord:
    text: str
    start: float
    end: float


@dataclass
class ExportUtterance:
    idx: int
    speaker: str  # display name, already resolved
    start: float
    end: float
    text: str
    words: list[ExportWord] = field(default_factory=list)


@dataclass
class ExportSpeakerStats:
    name: str
    talk_time_s: float = 0.0
    talk_share: float = 0.0
    turns: int = 0
    words_per_minute: float = 0.0


@dataclass
class ExportData:
    title: str
    language: str | None
    duration_s: float | None
    utterances: list[ExportUtterance]
    speakers: list[ExportSpeakerStats] = field(default_factory=list)


def _split_ms(seconds: float) -> tuple[int, int, int, int]:
    """Whole milliseconds first, then divide, so 59.9996 s becomes 00:01:00.000 and never 00:00:60."""
    total_ms = max(0, round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return hours, minutes, secs, ms


def srt_time(seconds: float) -> str:
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def vtt_time(seconds: float) -> str:
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def clock(seconds: float) -> str:
    """H:MM:SS or M:SS for transcripts."""
    h, m, s, _ = _split_ms(seconds)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
