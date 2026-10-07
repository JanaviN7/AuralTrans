"""Word-level speaker assignment: overlap assignment -> smoothing -> utterance regrouping."""

from dataclasses import dataclass

from auraltrans.schemas import Turn, Utterance, Word

UNKNOWN_SPEAKER = "UNKNOWN"
SMOOTH_MAX_DURATION_S = 0.3
SMOOTH_MIN_WORDS = 2
PAUSE_SPLIT_S = 1.0
LONG_UTTERANCE_S = 25.0
_SENTENCE_END = (".", "?", "!")


@dataclass
class LabeledWord:
    word: Word
    speaker: str


def _overlap(word: Word, turn: Turn) -> float:
    return max(0.0, min(word.end, turn.end) - max(word.start, turn.start))


def _distance(word: Word, turn: Turn) -> float:
    """Gap between a word and a turn; 0 when they touch or overlap."""
    return max(0.0, turn.start - word.end, word.start - turn.end)


def assign_speakers(words: list[Word], turns: list[Turn]) -> list[LabeledWord]:
    """Give each word the turn with the largest time overlap, else the nearest turn."""
    labeled: list[LabeledWord] = []
    for word in words:
        if not turns:
            labeled.append(LabeledWord(word, UNKNOWN_SPEAKER))
            continue
        best = max(turns, key=lambda t: (_overlap(word, t), -t.start))
        if _overlap(word, best) <= 0:
            best = min(turns, key=lambda t: (_distance(word, t), t.start))
        labeled.append(LabeledWord(word, best.speaker))
    return labeled


def _runs(labeled: list[LabeledWord]) -> list[list[LabeledWord]]:
    runs: list[list[LabeledWord]] = []
    for item in labeled:
        if runs and runs[-1][0].speaker == item.speaker:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def smooth(
    labeled: list[LabeledWord],
    max_duration_s: float = SMOOTH_MAX_DURATION_S,
    min_words: int = SMOOTH_MIN_WORDS,
) -> list[LabeledWord]:
    """Relabel short islands that sit between two runs of the same other speaker."""
    runs = _runs(labeled)
    for i in range(1, len(runs) - 1):
        prev_speaker, nxt_speaker = runs[i - 1][0].speaker, runs[i + 1][0].speaker
        if prev_speaker != nxt_speaker or runs[i][0].speaker == prev_speaker:
            continue
        duration = runs[i][-1].word.end - runs[i][0].word.start
        if len(runs[i]) < min_words or duration < max_duration_s:
            for item in runs[i]:
                item.speaker = prev_speaker
    return labeled


def regroup(
    labeled: list[LabeledWord],
    pause_s: float = PAUSE_SPLIT_S,
    long_s: float = LONG_UTTERANCE_S,
) -> list[Utterance]:
    """Split at speaker change, a long pause, or a sentence end once past `long_s`."""
    groups: list[list[LabeledWord]] = []
    for item in labeled:
        if groups:
            last = groups[-1]
            same_speaker = last[-1].speaker == item.speaker
            gap = item.word.start - last[-1].word.end
            too_long = (last[-1].word.end - last[0].word.start) > long_s and last[
                -1
            ].word.text.strip().endswith(_SENTENCE_END)
            if same_speaker and gap <= pause_s and not too_long:
                last.append(item)
                continue
        groups.append([item])

    utterances: list[Utterance] = []
    for idx, group in enumerate(groups):
        words = [g.word for g in group]
        utterances.append(
            Utterance(
                id=f"u{idx}",
                idx=idx,
                speaker=group[0].speaker,
                start=words[0].start,
                end=words[-1].end,
                text=" ".join(w.text.strip() for w in words),
                words=words,
            )
        )
    return utterances


def mark_overlap(utterances: list[Utterance], overlap_turns: list[Turn]) -> None:
    """Flag utterances during which a different speaker is also active."""
    for utt in utterances:
        utt.has_overlap = any(
            t.speaker != utt.speaker and min(utt.end, t.end) > max(utt.start, t.start)
            for t in overlap_turns
        )


def align(
    words: list[Word],
    exclusive_turns: list[Turn],
    overlap_turns: list[Turn] | None = None,
) -> list[Utterance]:
    utterances = regroup(smooth(assign_speakers(words, exclusive_turns)))
    if overlap_turns:
        mark_overlap(utterances, overlap_turns)
    return utterances
