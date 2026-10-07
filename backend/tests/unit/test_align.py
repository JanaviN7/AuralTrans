from auraltrans.schemas import Turn, Word
from auraltrans.speech.align import align, assign_speakers, mark_overlap, regroup, smooth


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def speakers(labeled: list) -> list[str]:  # type: ignore[type-arg]
    return [item.speaker for item in labeled]


def test_word_spanning_two_turns_goes_to_larger_overlap() -> None:
    turns = [Turn(speaker="A", start=0, end=1.0), Turn(speaker="B", start=1.0, end=3.0)]
    labeled = assign_speakers([w("x", 0.8, 1.9)], turns)  # 0.2 in A, 0.9 in B
    assert speakers(labeled) == ["B"]


def test_word_with_no_overlap_goes_to_nearest_turn() -> None:
    turns = [Turn(speaker="A", start=0, end=1.0), Turn(speaker="B", start=5.0, end=6.0)]
    assert speakers(assign_speakers([w("x", 1.2, 1.4)], turns)) == ["A"]
    assert speakers(assign_speakers([w("y", 4.5, 4.8)], turns)) == ["B"]


def test_no_turns_gives_unknown() -> None:
    assert speakers(assign_speakers([w("x", 0, 1)], [])) == ["UNKNOWN"]


def test_single_word_island_is_smoothed() -> None:
    turns = [
        Turn(speaker="A", start=0, end=2.0),
        Turn(speaker="B", start=2.0, end=2.5),
        Turn(speaker="A", start=2.5, end=5.0),
    ]
    words = [w("what", 0, 1), w("does", 1, 2), w("air", 2.0, 2.5), w("pollution", 2.5, 3.5), w("mean?", 3.5, 4.5)]
    labeled = smooth(assign_speakers(words, turns))
    assert speakers(labeled) == ["A"] * 5


def test_long_island_between_same_speaker_is_kept() -> None:
    turns = [
        Turn(speaker="A", start=0, end=1.0),
        Turn(speaker="B", start=1.0, end=3.0),
        Turn(speaker="A", start=3.0, end=4.0),
    ]
    words = [w("a", 0, 1), w("b1", 1, 2), w("b2", 2, 3), w("c", 3, 4)]
    assert speakers(smooth(assign_speakers(words, turns))) == ["A", "B", "B", "A"]


def test_island_between_different_speakers_is_kept() -> None:
    turns = [
        Turn(speaker="A", start=0, end=1.0),
        Turn(speaker="B", start=1.0, end=1.2),
        Turn(speaker="C", start=1.2, end=2.0),
    ]
    words = [w("a", 0, 1), w("b", 1.0, 1.2), w("c", 1.2, 2.0)]
    assert speakers(smooth(assign_speakers(words, turns))) == ["A", "B", "C"]


def test_regroup_splits_on_speaker_change_and_pause() -> None:
    turns = [Turn(speaker="A", start=0, end=10), Turn(speaker="B", start=10, end=12)]
    words = [w("hi", 0, 0.5), w("there", 0.6, 1.0), w("again", 3.0, 3.5), w("yes", 10.2, 10.6)]
    utts = regroup(assign_speakers(words, turns))
    assert [(u.speaker, u.text) for u in utts] == [("A", "hi there"), ("A", "again"), ("B", "yes")]
    assert [u.id for u in utts] == ["u0", "u1", "u2"]


def test_regroup_splits_long_utterance_at_sentence_end() -> None:
    words = [w(f"w{i}.", i * 3.0, i * 3.0 + 2.5) if i == 9 else w(f"w{i}", i * 3.0, i * 3.0 + 2.5) for i in range(12)]
    turns = [Turn(speaker="A", start=0, end=40)]
    utts = regroup(assign_speakers(words, turns))
    assert len(utts) == 2
    assert utts[0].text.endswith("w9.")


def test_speaker_change_inside_one_asr_segment_splits_at_the_right_word() -> None:
    """Whisper emits one segment for a question plus its answer; labels must follow the words."""
    words = [
        w("what", 0.0, 0.4), w("does", 0.5, 0.9), w("air", 1.0, 1.3),
        w("pollution", 1.4, 2.0), w("mean?", 2.1, 2.5),
        w("It", 2.7, 2.9), w("means", 3.0, 3.4), w("dirty", 3.5, 3.9), w("air.", 4.0, 4.4),
    ]
    turns = [Turn(speaker="S2", start=0, end=2.6), Turn(speaker="S1", start=2.6, end=5.0)]
    utts = align(words, turns)
    assert [(u.speaker, u.text) for u in utts] == [
        ("S2", "what does air pollution mean?"),
        ("S1", "It means dirty air."),
    ]


def test_mark_overlap() -> None:
    utts = regroup(assign_speakers([w("hi", 0, 1)], [Turn(speaker="A", start=0, end=1)]))
    mark_overlap(utts, [Turn(speaker="A", start=0, end=1), Turn(speaker="B", start=0.5, end=1.5)])
    assert utts[0].has_overlap


def test_empty_input() -> None:
    assert align([], []) == []
