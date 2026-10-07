from pathlib import Path

from auraltrans.evaluation import ami
from auraltrans.evaluation.baselines import VARIANTS
from auraltrans.schemas import Turn, Word
from auraltrans.speech.asr import AsrSegment

WORDS_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<nite:root nite:id="ES2004a.A.words" xmlns:nite="http://nite.sourceforge.net/">
<w nite:id="ES2004a.A.words0" starttime="1.00" endtime="1.40">Okay</w>
<w nite:id="ES2004a.A.words1" starttime="1.40" endtime="1.40" punc="true">.</w>
<vocalsound nite:id="ES2004a.A.vs0" starttime="1.50" endtime="1.80" type="laugh"/>
<w nite:id="ES2004a.A.words2" starttime="1.60" endtime="2.00">so</w>
<w nite:id="ES2004a.A.words3" starttime="9.00" endtime="9.30">next</w>
<w nite:id="ES2004a.A.words4" starttime="9.30">broken</w>
</nite:root>"""


def test_parse_words_skips_punctuation_vocalsounds_and_untimed_words() -> None:
    words = ami.parse_words_xml(WORDS_XML)
    assert [w.text for w in words] == ["Okay", "so", "next"]
    assert words[0].start == 1.0 and words[0].end == 1.4


def test_speaker_segments_split_on_long_pause() -> None:
    segs = ami.speaker_segments("A", ami.parse_words_xml(WORDS_XML))
    assert [(s.speaker, s.text) for s in segs] == [("A", "Okay so"), ("A", "next")]


def test_load_reference_reads_speaker_from_filename(tmp_path: Path) -> None:
    d = tmp_path / "ami" / "words"
    d.mkdir(parents=True)
    (d / "ES2004a.A.words.xml").write_text(WORDS_XML, encoding="utf-8")
    (d / "ES2004a.B.words.xml").write_text(WORDS_XML.replace("Okay", "Right"), encoding="utf-8")
    ref = ami.load_reference(tmp_path, "ES2004a")
    assert {s.speaker for s in ref} == {"A", "B"}


def test_subset_is_ten_official_test_meetings() -> None:
    assert len(ami.TEST_SUBSET) == 10 and len(set(ami.TEST_SUBSET)) == 10


def _w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_variants_differ_when_one_asr_segment_spans_two_speakers() -> None:
    words = [_w("what", 0, 0.4), _w("does", 0.5, 0.9), _w("air", 1.0, 1.3), _w("pollution", 1.4, 2.0),
             _w("mean?", 2.1, 2.5), _w("It", 2.7, 2.9), _w("means", 3.0, 3.4), _w("dirty", 3.5, 3.9)]
    segments = [AsrSegment(start=0, end=3.9, text="what does air pollution mean? It means dirty", words=words)]
    exclusive = [Turn(speaker="S2", start=0, end=2.6), Turn(speaker="S1", start=2.6, end=4.0)]
    out = {name: v(segments, exclusive, exclusive) for name, v in VARIANTS.items()}
    assert len(out["a_per_segment"]) == 1  # the original bug: one label for question and answer
    assert [u.speaker for u in out["b_per_word"]] == ["S2", "S1"]
    assert [u.speaker for u in out["c_per_word_smoothed_exclusive"]] == ["S2", "S1"]


def test_librispeech_subset_is_200_utterances_from_full_row_groups() -> None:
    from auraltrans.evaluation import librispeech

    assert len(librispeech.ROW_GROUPS) * librispeech.PER_GROUP == 200
    assert 26 not in librispeech.ROW_GROUPS  # the last row group has only 20 rows
