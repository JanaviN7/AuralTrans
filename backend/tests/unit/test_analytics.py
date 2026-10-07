from auraltrans.schemas import Turn, Utterance, Word
from auraltrans.speech.analytics import compute_analytics


def utt(i: int, speaker: str, start: float, end: float, n_words: int) -> Utterance:
    step = (end - start) / n_words
    words = [Word(text=f"w{k}", start=start + k * step, end=start + (k + 1) * step) for k in range(n_words)]
    return Utterance(id=f"u{i}", idx=i, speaker=speaker, start=start, end=end, text=" ".join(w.text for w in words), words=words)


def test_talk_time_turns_wpm_monologue() -> None:
    utts = [utt(0, "A", 0, 30, 60), utt(1, "A", 31, 40, 10), utt(2, "B", 40, 60, 20)]
    a = compute_analytics(utts, duration_s=100)
    assert a.speakers["A"].talk_time_s == 39
    assert a.speakers["A"].turns == 1  # consecutive utterances merge into one turn
    assert a.speakers["A"].longest_monologue_s == 40
    assert a.speakers["B"].turns == 1
    assert round(a.speakers["B"].words_per_minute) == 60
    assert round(a.speakers["A"].talk_share + a.speakers["B"].talk_share, 6) == 1
    assert round(a.silence_ratio, 2) == 0.41  # speech covers 0-30 and 31-60 = 59 of 100 s


def test_interruptions_counted_per_interrupter() -> None:
    turns = [Turn(speaker="A", start=0, end=10), Turn(speaker="B", start=5, end=12), Turn(speaker="A", start=13, end=15)]
    a = compute_analytics([utt(0, "A", 0, 10, 5), utt(1, "B", 5, 12, 5)], 20, turns)
    assert a.speakers["B"].interruptions_made == 1
    assert a.speakers["A"].interruptions_made == 0


def test_empty() -> None:
    a = compute_analytics([], duration_s=10)
    assert a.speakers == {} and a.silence_ratio == 1.0
