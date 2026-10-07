import pytest

from auraltrans.evaluation.metrics import (
    SpeakerText,
    cpwer_fallback,
    cpwer_meeteval,
    der,
    meeteval_available,
    wer,
)
from auraltrans.schemas import Turn


def st(speaker: str, start: float, text: str) -> SpeakerText:
    return SpeakerText(speaker, start, start + 1, text)


def test_wer_counts_one_substitution_in_six_words() -> None:
    c = wer(["The cat sat on the mat."], ["the cat sat on a mat"])
    assert (c.errors, c.length, c.substitutions) == (1, 6, 1)
    assert round(c.rate, 4) == round(1 / 6, 4)


def test_wer_is_corpus_level_and_skips_empty_references() -> None:
    c = wer(["a b c d", "", "e f"], ["a b c d", "ignored words", "e x"])
    assert (c.errors, c.length) == (1, 6)


def test_der_confusion_only() -> None:
    ref = [Turn(speaker="A", start=0, end=5), Turn(speaker="B", start=5, end=10)]
    hyp = [Turn(speaker="x", start=0, end=6), Turn(speaker="y", start=6, end=10)]
    r = der(ref, hyp, uem=(0, 10))
    assert round(r.der, 3) == 0.1 and round(r.confusion, 3) == 0.1
    assert r.missed == 0 and r.false_alarm == 0


def test_der_missed_and_false_alarm() -> None:
    ref = [Turn(speaker="A", start=0, end=5)]
    hyp = [Turn(speaker="x", start=1, end=7)]
    r = der(ref, hyp, uem=(0, 10))
    assert round(r.missed, 3) == 0.2  # 1 s of 5 s reference speech missed
    assert round(r.false_alarm, 3) == 0.4  # 2 s after the reference ends


def test_der_collar_forgives_boundary_error() -> None:
    ref = [Turn(speaker="A", start=0, end=5), Turn(speaker="B", start=5, end=10)]
    hyp = [Turn(speaker="x", start=0, end=5.2), Turn(speaker="y", start=5.2, end=10)]
    assert der(ref, hyp, (0, 10), collar=0.0).der > 0
    assert der(ref, hyp, (0, 10), collar=0.25).der == 0  # 0.2 s boundary error is inside +/-0.25 s
    far = [Turn(speaker="x", start=0, end=5.6), Turn(speaker="y", start=5.6, end=10)]
    assert der(ref, far, (0, 10), collar=0.25).der > 0  # 0.6 s is outside it


def test_cpwer_ignores_speaker_label_names() -> None:
    ref = [st("A", 0, "hello there"), st("B", 2, "good morning")]
    hyp = [st("spk1", 0, "good morning"), st("spk0", 2, "hello there")]
    # times differ but cpWER concatenates per speaker, so only the assignment matters
    swapped = [st("spk0", 0, "hello there"), st("spk1", 2, "good morning")]
    assert cpwer_fallback(ref, swapped).errors == 0
    assert cpwer_fallback(ref, hyp).errors == 0


def test_cpwer_penalises_words_given_to_the_wrong_speaker() -> None:
    ref = [st("A", 0, "what does air pollution mean"), st("B", 5, "it means dirty air")]
    hyp = [st("x", 0, "what does"), st("y", 2, "air pollution mean it means dirty air")]
    c = cpwer_fallback(ref, hyp)
    # "air pollution mean" lands on the wrong speaker: 3 deletions for A, 3 insertions for B
    assert (c.length, c.deletions, c.insertions, c.errors) == (9, 3, 3, 6)


def test_cpwer_extra_and_missing_speakers() -> None:
    ref = [st("A", 0, "red green blue")]  # not number words: the normalizer would merge those
    assert cpwer_fallback(ref, ref + [st("B", 1, "cat dog")]).insertions == 2
    two_ref = [st("A", 0, "red green"), st("B", 1, "blue")]
    assert cpwer_fallback(two_ref, [st("x", 0, "red green")]).deletions == 1


@pytest.mark.skipif(not meeteval_available(), reason="meeteval is Linux-only (no Windows wheel)")
def test_fallback_matches_meeteval() -> None:
    ref = [st("A", 0, "what does air pollution mean"), st("B", 5, "it means dirty air"), st("C", 9, "thanks")]
    hyp = [st("x", 0, "what does air"), st("y", 2, "pollution mean it means dirty air"), st("z", 9, "thank you")]
    a, b = cpwer_fallback(ref, hyp), cpwer_meeteval(ref, hyp)
    assert (a.errors, a.length) == (b.errors, b.length)
