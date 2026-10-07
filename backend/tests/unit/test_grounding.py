"""Schema and citation validation for Insights, and answer verification for Ask. No database."""

import pytest

from auraltrans.ask.service import ABSTAIN_MESSAGE, _RawAnswer, verify
from auraltrans.insights.support import quote_in, support_ratio
from auraltrans.insights.transcript import Line, chunk
from auraltrans.insights.validate import RawInsights, merge_raw, parse_uid, validate_insights
from auraltrans.llm.client import extract_json

TEXTS = [
    "Welcome everyone, today we plan the Q3 launch.",
    "We agreed to move the launch to September 14.",
    "Priya will send the revised budget by Friday.",
    "Does anyone know whether legal has reviewed the contract?",
    "No, not yet. We still have to ask them.",
    "Okay. Let's meet again next Tuesday.",
]
SPEAKERS = {"Priya": "id-priya", "Marco": "id-marco"}


def lines() -> list[Line]:
    return [
        Line(f"u{i}", i, i * 5.0, i * 5.0 + 4, None, "Priya" if i % 2 else "Marco", t)
        for i, t in enumerate(TEXTS)
    ]


def raw(**kw: object) -> RawInsights:
    return RawInsights.model_validate(kw)


def test_parse_uid_accepts_the_formats_models_actually_produce() -> None:
    assert [parse_uid(x) for x in ["u12", "U12", "[u12]", 12, "12", " u3 "]] == [12, 12, 12, 12, 12, 3]
    assert parse_uid("utterance 4") is None and parse_uid("") is None


def test_valid_cited_items_are_kept_and_verified() -> None:
    out, rep = validate_insights(
        raw(decisions=[{"text": "The launch moves to September 14.", "evidence": ["u1"]}]), lines(), SPEAKERS
    )
    assert out.decisions[0].status == "verified" and out.decisions[0].evidence[0].utterance_id == "u1"
    assert rep["sections"]["decisions"]["kept"] == 1


def test_invented_ids_are_stripped_and_uncited_items_dropped() -> None:
    out, rep = validate_insights(
        raw(
            decisions=[
                {"text": "The launch moves to September 14.", "evidence": ["u1", "u99"]},
                {"text": "Hire a new designer.", "evidence": ["u42"]},
                {"text": "Cut the budget in half.", "evidence": []},
            ]
        ),
        lines(),
        SPEAKERS,
    )
    assert [d.text for d in out.decisions] == ["The launch moves to September 14."]
    assert [c.utterance_id for c in out.decisions[0].evidence] == ["u1"]
    st = rep["sections"]["decisions"]
    assert (st["proposed"], st["kept"], st["dropped_no_evidence"], st["invalid_citations"]) == (3, 1, 2, 2)


def test_a_real_citation_that_does_not_support_the_claim_is_marked_unverified_not_trusted() -> None:
    out, _ = validate_insights(
        raw(decisions=[{"text": "The team approved the hiring plan.", "evidence": ["u5"]}]), lines(), SPEAKERS
    )
    assert out.decisions[0].status == "unverified"


def test_an_invented_number_is_unverified_even_with_matching_words() -> None:
    out, _ = validate_insights(
        raw(decisions=[{"text": "The launch moves to September 21.", "evidence": ["u1"]}]), lines(), SPEAKERS
    )
    assert out.decisions[0].status == "unverified"


def test_number_words_and_digits_are_equivalent() -> None:
    ratio, ok = support_ratio("Three people joined", ["3 people joined the call"])
    assert ok and ratio == 1.0


def test_action_item_owner_is_mapped_to_a_real_speaker_or_none() -> None:
    out, _ = validate_insights(
        raw(
            action_items=[
                {"task": "Send the revised budget", "owner": "priya", "due": "Friday", "evidence": ["u2"]},
                {"task": "Ask legal to review the contract", "owner": "Someone Else", "evidence": ["u4"]},
            ]
        ),
        lines(),
        SPEAKERS,
    )
    assert out.action_items[0].owner_speaker_id == "id-priya" and out.action_items[0].due_text == "Friday"
    assert out.action_items[1].owner_speaker_id is None


def test_chapters_are_validated_ordered_and_made_non_overlapping() -> None:
    out, rep = validate_insights(
        raw(
            chapters=[
                {"title": "Wrap up", "start": "u4", "end": "u5"},
                {"title": "Planning", "start": "u0", "end": "u3"},
                {"title": "Ghost", "start": "u40", "end": "u50"},
                {"title": "Overlap", "start": "u2", "end": "u4"},
            ]
        ),
        lines(),
        SPEAKERS,
    )
    spans = [(c.title, c.start_uid, c.end_uid) for c in out.chapters]
    # Sorted by start; "Overlap" is trimmed to begin after "Planning"; "Wrap up" after that.
    assert spans == [("Planning", "u0", "u3"), ("Overlap", "u4", "u4"), ("Wrap up", "u5", "u5")]
    assert rep["chapters"] == {"proposed": 4, "kept": 3, "dropped": 1}


def test_schema_rejects_garbage_but_tolerates_nulls() -> None:
    with pytest.raises(ValueError):
        raw(decisions="nope")
    assert raw(decisions=None, key_points=None, summary=None).decisions == []


def test_merge_deduplicates_across_chunks() -> None:
    a = raw(decisions=[{"text": "Move the launch.", "evidence": ["u1"]}], summary={"text": "A.", "evidence": ["u0"]})
    b = raw(decisions=[{"text": "move the launch", "evidence": ["u1"]}], summary={"text": "B.", "evidence": ["u5"]})
    m = merge_raw([a, b])
    assert len(m.decisions) == 1 and m.summary is not None and m.summary.text == "A. B."


def test_chunking_splits_on_utterance_boundaries() -> None:
    parts = chunk(lines(), 120)
    assert len(parts) > 1 and [ln.idx for p in parts for ln in p] == list(range(6))


def test_extract_json_handles_fences_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": 2}} Hope that helps') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json here")


# --- Ask verification ---------------------------------------------------------------------------


def answer(**kw: object) -> _RawAnswer:
    return _RawAnswer.model_validate(kw)


def test_ask_accepts_a_grounded_answer_with_verbatim_quote() -> None:
    r = verify(
        answer(
            answerable=True,
            answer="Priya will send the revised budget by Friday.",
            citations=[{"id": "u2", "quote": "Priya will send the revised budget"}],
        ),
        lines(),
    )
    assert not r.abstained and r.citations == [{"uid": "u2", "quote": "Priya will send the revised budget"}]


def test_ask_abstains_when_the_model_declines() -> None:
    r = verify(answer(answerable=False, answer="", citations=[]), lines())
    assert r.abstained and r.abstain_reason == "model_declined" and r.answer == ABSTAIN_MESSAGE


def test_ask_abstains_when_quote_is_fabricated_or_id_is_invented() -> None:
    fake_quote = answer(
        answerable=True,
        answer="The launch moves to September 14.",
        citations=[{"id": "u1", "quote": "we will definitely cancel the launch entirely"}],
    )
    fake_id = answer(
        answerable=True,
        answer="The launch moves to September 14.",
        citations=[{"id": "u77", "quote": "move the launch to September 14"}],
    )
    for raw_answer in (fake_quote, fake_id):
        r = verify(raw_answer, lines())
        assert r.abstained and r.abstain_reason == "no_valid_citation" and r.citations == []


def test_ask_abstains_on_an_answer_its_citation_does_not_support() -> None:
    r = verify(
        answer(
            answerable=True,
            answer="The budget was approved at 40 thousand dollars.",
            citations=[{"id": "u1", "quote": "move the launch to September 14"}],
        ),
        lines(),
    )
    assert r.abstained and r.abstain_reason == "unsupported_answer"


def test_quote_matching_ignores_case_and_punctuation_but_not_content() -> None:
    assert quote_in("we AGREED to move the launch", TEXTS[1])
    assert not quote_in("we agreed to cancel the launch", TEXTS[1])
    assert not quote_in("", TEXTS[1])
