"""The three speaker-attribution variants compared in the alignment ablation."""

from collections import defaultdict
from collections.abc import Callable

from auraltrans.schemas import Turn, Utterance, Word
from auraltrans.speech.align import (
    UNKNOWN_SPEAKER,
    LabeledWord,
    align,
    assign_speakers,
    regroup,
)
from auraltrans.speech.asr import AsrSegment

Variant = Callable[[list[AsrSegment], list[Turn], list[Turn]], list[Utterance]]


def _segment_speaker(seg: AsrSegment, turns: list[Turn]) -> str:
    """One label for the whole segment: the speaker with most overlapping time."""
    if not turns:
        return UNKNOWN_SPEAKER
    overlap: dict[str, float] = defaultdict(float)
    for t in turns:
        overlap[t.speaker] += max(0.0, min(seg.end, t.end) - max(seg.start, t.start))
    best = max(overlap.items(), key=lambda kv: kv[1])
    if best[1] > 0:
        return best[0]
    mid = (seg.start + seg.end) / 2
    return min(turns, key=lambda t: min(abs(t.start - mid), abs(t.end - mid))).speaker


def per_segment(
    segments: list[AsrSegment], exclusive: list[Turn], overlap: list[Turn]
) -> list[Utterance]:
    """(a) The original method: every Whisper segment gets one speaker label."""
    utterances: list[Utterance] = []
    for idx, seg in enumerate(segments):
        words: list[Word] = seg.words
        utterances.append(
            Utterance(
                id=f"u{idx}",
                idx=idx,
                speaker=_segment_speaker(seg, overlap),
                start=seg.start,
                end=seg.end,
                text=seg.text,
                words=words,
            )
        )
    return utterances


def per_word(
    segments: list[AsrSegment], exclusive: list[Turn], overlap: list[Turn]
) -> list[Utterance]:
    """(b) Per-word overlap assignment on the overlap-aware turns, no smoothing."""
    words = [w for s in segments for w in s.words]
    labeled: list[LabeledWord] = assign_speakers(words, overlap)
    return regroup(labeled)


def per_word_smoothed(
    segments: list[AsrSegment], exclusive: list[Turn], overlap: list[Turn]
) -> list[Utterance]:
    """(c) Per-word assignment on exclusive turns + smoothing + regrouping (the shipped method)."""
    return align([w for s in segments for w in s.words], exclusive, overlap)


VARIANTS: dict[str, Variant] = {
    "a_per_segment": per_segment,
    "b_per_word": per_word,
    "c_per_word_smoothed_exclusive": per_word_smoothed,
}
