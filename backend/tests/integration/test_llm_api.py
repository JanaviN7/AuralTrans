"""Insights and Ask through the API, with a scripted LLM and a transcript seeded straight into the DB."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from auraltrans.api.app import create_app
from auraltrans.db.models import Insight, LLMCall, QATurn, Recording, Speaker, Utterance
from auraltrans.db.session import session_scope
from auraltrans.insights import generate
from auraltrans.llm import LLM, get_llm
from tests.fakes import ScriptedLLM

LINES = [
    ("Marco", "Welcome everyone, today we plan the Q3 launch."),
    ("Priya", "We agreed to move the launch to September 14."),
    ("Marco", "Great. Priya will send the revised budget by Friday."),
    ("Priya", "Does anyone know whether legal has reviewed the contract?"),
    ("Marco", "No, not yet. We still have to ask them."),
    ("Priya", "Okay. Let's meet again next Tuesday."),
]
GOOD_INSIGHTS = {
    "summary": {"text": "The team planned the Q3 launch and moved it to September 14.", "evidence": ["u0", "u1"]},
    "key_points": [{"text": "Legal has not yet reviewed the contract.", "evidence": ["u3", "u4"]}],
    "decisions": [{"text": "The launch moves to September 14.", "evidence": ["u1"]}],
    "action_items": [
        {"task": "Send the revised budget", "owner": "Priya", "due": "Friday", "evidence": ["u2"]}
    ],
    "open_questions": [{"text": "Has legal reviewed the contract?", "evidence": ["u3"]}],
    "chapters": [{"title": "Launch plan", "start": "u0", "end": "u2"}, {"title": "Open items", "start": "u3", "end": "u5"}],
}


def seed(status: str = "ready") -> uuid.UUID:
    with session_scope() as s:
        rec = Recording(title="Launch sync", status=status, duration_s=60.0, language="en",
                        source_filename="x.wav", storage_prefix="recordings/x")
        s.add(rec)
        s.flush()
        speakers = {n: Speaker(recording_id=rec.id, label=f"S_{n}", display_name=n) for n in ("Marco", "Priya")}
        s.add_all(speakers.values())
        s.flush()
        for i, (who, text) in enumerate(LINES):
            s.add(Utterance(recording_id=rec.id, idx=i, speaker_id=speakers[who].id,
                            start_s=i * 8.0, end_s=i * 8.0 + 6, text=text, words=[]))
        return rec.id


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM(GOOD_INSIGHTS)


@pytest.fixture
def client(db, llm: ScriptedLLM) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app()
    holder: dict[str, LLM | None] = {"llm": llm}
    app.dependency_overrides[get_llm] = lambda: holder["llm"]
    with TestClient(app) as c:
        c.holder = holder  # type: ignore[attr-defined]
        yield c


def test_health_reports_features_on_only_when_a_model_is_configured(client: TestClient) -> None:
    assert client.get("/api/health").json()["features"] == {"insights": True, "ask": True}
    client.holder["llm"] = None  # type: ignore[attr-defined]
    assert client.get("/api/health").json()["features"] == {"insights": False, "ask": False}


def test_no_model_configured_gives_a_clear_503(client: TestClient) -> None:
    rid = seed()
    client.holder["llm"] = None  # type: ignore[attr-defined]
    for r in (client.post(f"/api/recordings/{rid}/insights"), client.post(f"/api/recordings/{rid}/ask", json={"question": "Who?"})):
        assert r.status_code == 503 and "LLM_BASE_URL" in r.json()["detail"]


def test_insights_start_as_none_then_generate_validate_and_persist(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    assert client.get(f"/api/recordings/{rid}/insights").json()["status"] == "none"
    r = client.post(f"/api/recordings/{rid}/insights")
    assert r.status_code == 202
    body = client.get(f"/api/recordings/{rid}/insights").json()
    assert body["status"] == "done" and body["model"] == "fake-llm" and body["stale"] is False
    data = body["data"]
    assert data["summary"]["evidence"] == [{"utterance_id": "u0"}, {"utterance_id": "u1"}]
    assert data["decisions"][0]["status"] == "verified"
    assert data["action_items"][0]["due_text"] == "Friday"
    with session_scope() as s:
        priya = s.scalar(select(Speaker.id).where(Speaker.display_name == "Priya"))
    assert data["action_items"][0]["owner_speaker_id"] == str(priya)
    assert [c["title"] for c in data["chapters"]] == ["Launch plan", "Open items"]
    assert body["validation"]["sections"]["decisions"]["kept"] == 1
    # The prompt carries transcript lines with citable ids and real speaker names.
    assert "[u1 00:08 Priya] We agreed to move the launch" in llm.calls[0][1]
    with session_scope() as s:
        call = s.scalars(select(LLMCall)).one()
        assert (call.purpose, call.status, call.model) == ("insights", "ok", "fake-llm")


def test_hallucinated_evidence_never_reaches_the_user(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    llm.replies = [{
        "summary": {"text": "The team planned the launch.", "evidence": ["u0", "u500"]},
        "decisions": [
            {"text": "Hire two engineers.", "evidence": ["u900"]},
            {"text": "The launch moves to September 14.", "evidence": ["u1"]},
        ],
        "action_items": [{"task": "Fire the intern", "owner": "Marco", "evidence": []}],
    }]
    client.post(f"/api/recordings/{rid}/insights")
    body = client.get(f"/api/recordings/{rid}/insights").json()
    assert [d["text"] for d in body["data"]["decisions"]] == ["The launch moves to September 14."]
    assert body["data"]["action_items"] == []
    assert body["data"]["summary"]["evidence"] == [{"utterance_id": "u0"}]
    sections = body["validation"]["sections"]
    assert sections["decisions"]["dropped_no_evidence"] == 1 and sections["action_items"]["dropped_no_evidence"] == 1


def test_invalid_json_is_repaired_once_with_the_error_fed_back(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    llm.replies = ["Sorry, here is your summary: it was a nice meeting.", GOOD_INSIGHTS]
    client.post(f"/api/recordings/{rid}/insights")
    assert client.get(f"/api/recordings/{rid}/insights").json()["status"] == "done"
    assert len(llm.calls) == 2 and "rejected" in llm.calls[1][1]
    with session_scope() as s:
        assert sorted(c.status for c in s.scalars(select(LLMCall))) == ["invalid", "repaired"]


def test_unrepairable_output_is_a_visible_failure_not_silent_garbage(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    llm.replies = ["not json at all"]
    client.post(f"/api/recordings/{rid}/insights")
    body = client.get(f"/api/recordings/{rid}/insights").json()
    assert body["status"] == "failed" and "valid JSON" in body["error"] and body["data"] is None


def test_a_failed_regeneration_keeps_the_previous_good_insights(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    client.post(f"/api/recordings/{rid}/insights")
    llm.replies = ["garbage"]
    client.post(f"/api/recordings/{rid}/insights")
    body = client.get(f"/api/recordings/{rid}/insights").json()
    assert body["status"] == "failed" and body["data"]["decisions"] and body["version"] == 1


def test_editing_the_transcript_marks_insights_stale(client: TestClient) -> None:
    rid = seed()
    client.post(f"/api/recordings/{rid}/insights")
    with session_scope() as s:
        u = s.scalar(select(Utterance).where(Utterance.recording_id == rid, Utterance.idx == 1))
        assert u is not None
        u.text = "We agreed to move the launch to September 21."
    assert client.get(f"/api/recordings/{rid}/insights").json()["stale"] is True


def test_long_transcripts_are_processed_in_chunks_and_merged(
    client: TestClient, llm: ScriptedLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = seed()
    monkeypatch.setattr("auraltrans.insights.generate.settings.llm_chunk_chars", 120)

    def reply(_system: str, user: str) -> str:
        import json

        # Each chunk answers only about ids it can see.
        first = "u1" if "[u1 " in user else "u0"
        return json.dumps({"decisions": [{"text": "The launch moves to September 14.", "evidence": [first]}]})

    llm.replies = [reply]
    client.post(f"/api/recordings/{rid}/insights")
    body = client.get(f"/api/recordings/{rid}/insights").json()
    assert len(llm.calls) > 1 and body["validation"]["chunks"] == len(llm.calls)
    assert len(body["data"]["decisions"]) == 1  # duplicates across chunks merged


def test_stuck_running_rows_are_reported_as_failed_and_can_be_restarted(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    rid = seed()
    iid = generate.start_run(rid, "fake-llm")
    assert client.post(f"/api/recordings/{rid}/insights").status_code == 409  # genuinely running
    with session_scope() as s:
        row = s.get(Insight, iid)
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(hours=1)
    assert client.get(f"/api/recordings/{rid}/insights").json()["status"] == "failed"
    assert client.post(f"/api/recordings/{rid}/insights").status_code == 202


def test_insights_require_a_ready_recording(client: TestClient) -> None:
    rid = seed(status="processing")
    assert client.get(f"/api/recordings/{rid}/insights").status_code == 409
    assert client.get(f"/api/recordings/{uuid.uuid4()}/insights").status_code == 404


# --- Ask ----------------------------------------------------------------------------------------


def ask(client: TestClient, rid: uuid.UUID, question: str = "When is the launch?"):  # type: ignore[no-untyped-def]
    return client.post(f"/api/recordings/{rid}/ask", json={"question": question})


def test_ask_returns_a_cited_answer_with_resolved_timestamps(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    llm.replies = [{
        "answerable": True,
        "answer": "The launch was moved to September 14.",
        "citations": [{"id": "u1", "quote": "agreed to move the launch to September 14"}],
    }]
    r = ask(client, rid)
    assert r.status_code == 200
    t = r.json()
    assert t["abstained"] is False and t["abstain_reason"] is None
    (c,) = t["citations"]
    assert (c["uid"], c["start_s"], c["end_s"]) == ("u1", 8.0, 14.0) and c["speaker_id"]
    # Question and the whole transcript go to the model; citations are in the persisted history.
    assert "When is the launch?" in llm.calls[0][1] and "[u5 00:40 Priya]" in llm.calls[0][1]
    assert client.get(f"/api/recordings/{rid}/ask").json()[0]["id"] == t["id"]


def test_ask_abstains_when_the_transcript_does_not_contain_the_answer(client: TestClient, llm: ScriptedLLM) -> None:
    rid = seed()
    llm.replies = [{"answerable": False, "answer": "", "citations": []}]
    t = ask(client, rid, "What was the final marketing budget?").json()
    assert t["abstained"] is True and t["abstain_reason"] == "model_declined" and t["citations"] == []
    assert "can't find" in t["answer"]


def test_ask_abstains_instead_of_trusting_an_answer_with_a_fabricated_citation(
    client: TestClient, llm: ScriptedLLM
) -> None:
    rid = seed()
    llm.replies = [{
        "answerable": True,
        "answer": "The marketing budget is 50 thousand dollars.",
        "citations": [{"id": "u2", "quote": "the marketing budget is fifty thousand dollars"}],
    }]
    t = ask(client, rid, "What is the marketing budget?").json()
    assert t["abstained"] and t["abstain_reason"] == "no_valid_citation" and t["citations"] == []
    with session_scope() as s:  # abstentions are stored too
        assert s.scalars(select(QATurn)).one().abstained is True


def test_ask_validates_the_question_and_recording(client: TestClient) -> None:
    rid = seed()
    assert client.post(f"/api/recordings/{rid}/ask", json={"question": "hi"}).status_code == 422
    assert ask(client, uuid.uuid4()).status_code == 404
    assert ask(client, seed(status="failed")).status_code == 409


def test_ask_says_so_when_the_transcript_exceeds_the_context_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = seed()
    monkeypatch.setattr("auraltrans.ask.service.settings.llm_context_chars", 50)
    r = ask(client, rid)
    assert r.status_code == 413 and "too long" in r.json()["detail"]


def test_a_broken_model_endpoint_is_a_502_not_a_crash(client: TestClient) -> None:
    from auraltrans.llm import LLMError

    class Down:
        model = "down"

        def complete(self, *a: object, **k: object) -> None:
            raise LLMError("could not reach the language model")

    client.holder["llm"] = Down()  # type: ignore[attr-defined,assignment]
    rid = seed()
    r = ask(client, rid)
    assert r.status_code == 502 and "could not reach" in r.json()["detail"]
