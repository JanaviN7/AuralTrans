"""Deterministic speaker analytics from aligned utterances and overlap-aware turns."""

from collections import defaultdict

from pydantic import BaseModel

from auraltrans.schemas import Turn, Utterance


class SpeakerStats(BaseModel):
    talk_time_s: float = 0.0
    talk_share: float = 0.0
    turns: int = 0
    words: int = 0
    words_per_minute: float = 0.0
    longest_monologue_s: float = 0.0
    interruptions_made: int = 0


class Analytics(BaseModel):
    duration_s: float
    silence_ratio: float
    speakers: dict[str, SpeakerStats]


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _speaker_turns(utterances: list[Utterance]) -> list[tuple[str, float, float, int]]:
    """Maximal runs of consecutive utterances by one speaker: (speaker, start, end, words)."""
    runs: list[tuple[str, float, float, int]] = []
    for utt in utterances:
        n_words = len(utt.words) or len(utt.text.split())
        if runs and runs[-1][0] == utt.speaker:
            sp, start, _, n = runs[-1]
            runs[-1] = (sp, start, utt.end, n + n_words)
        else:
            runs.append((utt.speaker, utt.start, utt.end, n_words))
    return runs


def _interruptions(overlap_turns: list[Turn]) -> dict[str, int]:
    """A turn that starts while a different speaker's turn is active, counted per interrupter."""
    counts: dict[str, int] = defaultdict(int)
    for turn in overlap_turns:
        if any(
            other.speaker != turn.speaker and other.start < turn.start < other.end
            for other in overlap_turns
        ):
            counts[turn.speaker] += 1
    return counts


def compute_analytics(
    utterances: list[Utterance],
    duration_s: float,
    overlap_turns: list[Turn] | None = None,
) -> Analytics:
    stats: dict[str, SpeakerStats] = defaultdict(SpeakerStats)
    for utt in utterances:
        s = stats[utt.speaker]
        s.talk_time_s += utt.end - utt.start
        s.words += len(utt.words) or len(utt.text.split())
    for speaker, start, end, _ in _speaker_turns(utterances):
        s = stats[speaker]
        s.turns += 1
        s.longest_monologue_s = max(s.longest_monologue_s, end - start)

    total_talk = sum(s.talk_time_s for s in stats.values())
    for s in stats.values():
        s.talk_share = s.talk_time_s / total_talk if total_talk else 0.0
        s.words_per_minute = s.words / (s.talk_time_s / 60) if s.talk_time_s else 0.0
    for speaker, n in _interruptions(overlap_turns or []).items():
        stats[speaker].interruptions_made = n

    speech = sum(e - s for s, e in _merge_intervals([(u.start, u.end) for u in utterances]))
    silence = max(0.0, 1 - speech / duration_s) if duration_s > 0 else 0.0
    return Analytics(duration_s=duration_s, silence_ratio=silence, speakers=dict(stats))
