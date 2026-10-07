import json
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from auraltrans.api.app import create_app
from auraltrans.config import settings
from auraltrans.db.models import Job
from auraltrans.db.session import session_scope
from auraltrans.storage import get_storage
from auraltrans.storage.local import LocalStorage
from auraltrans.worker.runner import run_once
from tests.fakes import FakeModels, fake_prepare_audio

AUDIO = b"RIFF fake audio bytes for tests"


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auraltrans.pipeline.steps.prepare_audio", fake_prepare_audio)


@pytest.fixture
def client(db, storage: LocalStorage) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c


def upload(client: TestClient, title: str = "Weekly sync", name: str = "meeting.wav", **form: str) -> dict:  # type: ignore[type-arg]
    r = client.post(
        "/api/recordings", files={"file": (name, AUDIO, "audio/wav")}, data={"title": title, **form}
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def process(storage: LocalStorage, models: FakeModels | None = None) -> FakeModels:
    models = models or FakeModels()
    assert run_once(storage, models)
    return models


def ready_recording(client: TestClient, storage: LocalStorage) -> dict:  # type: ignore[type-arg]
    rec = upload(client)
    process(storage)
    return rec


# --- basics and upload -------------------------------------------------------------------------


def test_health_reports_which_features_exist(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "features": {"insights": False, "ask": False}}


def test_upload_creates_a_queued_recording_and_job(client: TestClient) -> None:
    rec = upload(client, language="auto", min_speakers="2", max_speakers="4")
    assert rec["status"] == "queued" and rec["title"] == "Weekly sync" and rec["language"] is None
    assert rec["job"]["status"] == "queued" and rec["job"]["progress"] == 0
    assert [s["status"] for s in rec["job"]["stages"]] == ["pending"] * 5
    assert [s["label"] for s in rec["job"]["stages"]][:3] == ["Preparing audio", "Transcribing", "Finding speakers"]
    assert client.get(f"/api/recordings/{rec['id']}").json()["id"] == rec["id"]
    assert [r["id"] for r in client.get("/api/recordings").json()] == [rec["id"]]


def test_title_defaults_to_the_file_name(client: TestClient) -> None:
    r = client.post("/api/recordings", files={"file": ("Team standup.mp3", AUDIO, "audio/mpeg")})
    assert r.status_code == 201 and r.json()["title"] == "Team standup"


@pytest.mark.parametrize(
    ("name", "data", "content", "expected"),
    [
        ("notes.txt", {}, AUDIO, 400),
        ("empty.wav", {}, b"", 400),
        ("a.wav", {"type": "podcast"}, AUDIO, 400),
        ("a.wav", {"min_speakers": "5", "max_speakers": "2"}, AUDIO, 400),
        ("a.wav", {"min_speakers": "0"}, AUDIO, 422),
    ],
)
def test_upload_validation(client: TestClient, name: str, data: dict, content: bytes, expected: int) -> None:  # type: ignore[type-arg]
    r = client.post("/api/recordings", files={"file": (name, content, "audio/wav")}, data=data)
    assert r.status_code == expected, r.text
    assert client.get("/api/recordings").json() == []


def test_oversize_upload_is_rejected_and_leaves_no_files(
    client: TestClient, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    r = client.post("/api/recordings", files={"file": ("big.wav", AUDIO, "audio/wav")})
    assert r.status_code == 413
    assert not [p for p in storage.root.rglob("*") if p.is_file()]


# --- the full flow -----------------------------------------------------------------------------


def test_transcript_is_not_served_until_processing_finishes(client: TestClient) -> None:
    rec = upload(client)
    assert client.get(f"/api/recordings/{rec['id']}/transcript").status_code == 409
    assert client.get(f"/api/recordings/{rec['id']}/analytics").status_code == 409
    assert client.get(f"/api/recordings/{rec['id']}/export", params={"format": "srt"}).status_code == 409


def test_upload_process_transcript_flow(client: TestClient, storage: LocalStorage) -> None:
    rec = upload(client)
    process(storage)

    done = client.get(f"/api/jobs/{rec['job']['id']}").json()
    assert done["status"] == "done" and done["progress"] == 1 and done["error"] is None
    assert [s["status"] for s in done["stages"]] == ["done"] * 5
    assert client.get(f"/api/recordings/{rec['id']}").json()["status"] == "ready"

    t = client.get(f"/api/recordings/{rec['id']}/transcript").json()
    assert [s["name"] for s in t["speakers"]] == ["Speaker 1", "Speaker 2"]
    assert all(s["color"].startswith("#") for s in t["speakers"])
    assert [u["uid"] for u in t["utterances"]] == ["u0", "u1"]
    first = t["utterances"][0]
    assert first["speaker_id"] == t["speakers"][0]["id"] and first["start_s"] == 0.0
    assert first["words"][0]["text"] == "Hello" and first["has_overlap"] is True
    assert t["language"] == "en" and t["duration_s"] == 9.0

    a = client.get(f"/api/recordings/{rec['id']}/analytics").json()
    assert {s["name"] for s in a["speakers"]} == {"Speaker 1", "Speaker 2"}
    assert abs(sum(s["talk_share"] for s in a["speakers"]) - 1) < 1e-6 and a["duration_s"] > 0


def test_audio_supports_range_requests_for_seeking(client: TestClient, storage: LocalStorage) -> None:
    rec = upload(client)
    assert client.get(f"/api/recordings/{rec['id']}/audio").content == AUDIO  # original, before processing
    process(storage)
    full = client.get(f"/api/recordings/{rec['id']}/audio")
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes"
    part = client.get(f"/api/recordings/{rec['id']}/audio", headers={"Range": "bytes=5-9"})
    assert part.status_code == 206 and part.content == AUDIO[5:10]
    assert part.headers["content-range"] == f"bytes 5-9/{len(AUDIO)}"


def test_unknown_ids_return_404(client: TestClient) -> None:
    missing = uuid.uuid4()
    for path in (f"/api/recordings/{missing}", f"/api/jobs/{missing}", f"/api/recordings/{missing}/audio"):
        assert client.get(path).status_code == 404
    assert client.delete(f"/api/recordings/{missing}").status_code == 404


# --- speakers, edits, search -------------------------------------------------------------------


def test_rename_speaker_flows_into_transcript_and_exports(client: TestClient, storage: LocalStorage) -> None:
    rec = ready_recording(client, storage)
    speakers = client.get(f"/api/recordings/{rec['id']}/transcript").json()["speakers"]
    r = client.patch(f"/api/recordings/{rec['id']}/speakers/{speakers[0]['id']}", json={"display_name": "  Priya "})
    assert r.status_code == 200 and r.json()["name"] == "Priya" and r.json()["display_name"] == "Priya"

    names = [s["name"] for s in client.get(f"/api/recordings/{rec['id']}/transcript").json()["speakers"]]
    assert names == ["Priya", "Speaker 2"]
    assert "Priya: Hello everyone." in client.get(f"/api/recordings/{rec['id']}/export", params={"format": "srt"}).text
    assert client.get(f"/api/recordings/{rec['id']}/analytics").json()["speakers"][0]["name"] == "Priya"

    reset = client.patch(f"/api/recordings/{rec['id']}/speakers/{speakers[0]['id']}", json={"display_name": None})
    assert reset.json()["name"] == "Speaker 1"


def test_rename_validation(client: TestClient, storage: LocalStorage) -> None:
    rec = ready_recording(client, storage)
    other = ready_recording_second(client, storage)
    sid = client.get(f"/api/recordings/{rec['id']}/transcript").json()["speakers"][0]["id"]
    assert client.patch(f"/api/recordings/{rec['id']}/speakers/{sid}", json={"display_name": "x" * 81}).status_code == 422
    assert client.patch(f"/api/recordings/{other['id']}/speakers/{sid}", json={"display_name": "A"}).status_code == 404
    assert client.patch(f"/api/recordings/{rec['id']}/speakers/{uuid.uuid4()}", json={"display_name": "A"}).status_code == 404


def ready_recording_second(client: TestClient, storage: LocalStorage) -> dict:  # type: ignore[type-arg]
    rec = upload(client, title="Second", name="second.wav")
    process(storage)
    return rec


def test_edit_utterance_marks_it_edited_and_updates_search(client: TestClient, storage: LocalStorage) -> None:
    rec = ready_recording(client, storage)
    uid = client.get(f"/api/recordings/{rec['id']}/transcript").json()["utterances"][1]["id"]
    assert client.get("/api/recordings", params={"q": "particulate"}).json() == []

    r = client.patch(f"/api/utterances/{uid}", json={"text": "Particulate matter is what we mean."})
    assert r.status_code == 200 and r.json()["edited"] is True and r.json()["text"].startswith("Particulate")
    assert [x["id"] for x in client.get("/api/recordings", params={"q": "particulate"}).json()] == [rec["id"]]
    assert client.patch(f"/api/utterances/{uid}", json={"text": "   "}).status_code == 422
    assert client.patch(f"/api/utterances/{uuid.uuid4()}", json={"text": "x"}).status_code == 404
    assert "Particulate matter is what we mean." in client.get(
        f"/api/recordings/{rec['id']}/export", params={"format": "txt"}
    ).text


def test_search_and_status_filter(client: TestClient, storage: LocalStorage) -> None:
    ready = ready_recording(client, storage)
    queued = upload(client, title="Budget review", name="b.wav")
    assert [r["id"] for r in client.get("/api/recordings", params={"q": "pollution"}).json()] == [ready["id"]]
    assert [r["id"] for r in client.get("/api/recordings", params={"q": "budget"}).json()] == [queued["id"]]
    assert client.get("/api/recordings", params={"q": "zebra"}).json() == []
    assert [r["id"] for r in client.get("/api/recordings", params={"status": "queued"}).json()] == [queued["id"]]
    assert {r["id"] for r in client.get("/api/recordings").json()} == {ready["id"], queued["id"]}


# --- export ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "content_type", "needle"),
    [
        ("srt", "application/x-subrip", "Speaker 1: Hello everyone."),
        ("vtt", "text/vtt", "WEBVTT"),
        ("txt", "text/plain", "[0:00] Speaker 1: Hello everyone."),
        ("md", "text/markdown", "## Transcript"),
        ("json", "application/json", '"utterances"'),
    ],
)
def test_every_export_format(client: TestClient, storage: LocalStorage, fmt: str, content_type: str, needle: str) -> None:
    rec = ready_recording(client, storage)
    r = client.get(f"/api/recordings/{rec['id']}/export", params={"format": fmt})
    assert r.status_code == 200 and r.headers["content-type"].startswith(content_type)
    assert r.headers["content-disposition"] == f'attachment; filename="Weekly-sync.{fmt}"'
    assert needle in r.text
    if fmt == "json":
        assert len(json.loads(r.text)["utterances"]) == 2


def test_export_rejects_unknown_format(client: TestClient, storage: LocalStorage) -> None:
    rec = ready_recording(client, storage)
    assert client.get(f"/api/recordings/{rec['id']}/export", params={"format": "docx"}).status_code == 400
    assert client.get(f"/api/recordings/{rec['id']}/export").status_code == 422


# --- retry and delete --------------------------------------------------------------------------


def test_retry_after_failure_resumes_and_skips_finished_stages(client: TestClient, storage: LocalStorage) -> None:
    rec = upload(client)
    jid = rec["job"]["id"]
    models = process(storage, FakeModels(diarizer_fail_with=RuntimeError("boom")))
    failed = client.get(f"/api/jobs/{jid}").json()
    assert failed["status"] == "failed" and "boom" in failed["error"]
    assert [s["status"] for s in failed["stages"]] == ["done", "done", "failed", "pending", "pending"]

    assert client.post(f"/api/jobs/{jid}/retry", params={"from_stage": "bogus"}).status_code == 400
    queued = client.post(f"/api/jobs/{jid}/retry").json()
    assert queued["status"] == "queued" and queued["error"] is None
    assert [s["status"] for s in queued["stages"]][:2] == ["done", "done"]

    process(storage, models)
    done = client.get(f"/api/jobs/{jid}").json()
    assert done["status"] == "done" and models.asr().calls == 1
    assert [s["status"] for s in done["stages"]][:2] == ["skipped", "skipped"]


def test_cannot_retry_or_delete_while_running(client: TestClient) -> None:
    rec = upload(client)
    with session_scope() as s:
        s.get(Job, uuid.UUID(rec["job"]["id"])).status = "running"  # type: ignore[union-attr]
    assert client.post(f"/api/jobs/{rec['job']['id']}/retry").status_code == 409
    assert client.delete(f"/api/recordings/{rec['id']}").status_code == 409


def test_delete_removes_rows_and_files(client: TestClient, storage: LocalStorage) -> None:
    rec = ready_recording(client, storage)
    assert storage.exists(f"recordings/{rec['id']}/artifacts/aligned.json")
    assert client.delete(f"/api/recordings/{rec['id']}").status_code == 204
    assert client.get(f"/api/recordings/{rec['id']}").status_code == 404
    assert client.get(f"/api/jobs/{rec['job']['id']}").status_code == 404
    assert not storage.exists(f"recordings/{rec['id']}/artifacts/aligned.json")
    assert client.get("/api/recordings").json() == []


# --- live progress (SSE) -----------------------------------------------------------------------


def parse_events(lines: Iterator[str]) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    events: list[tuple[str, dict]] = []  # type: ignore[type-arg]
    name = ""
    for line in lines:
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            events.append((name, json.loads(line.split(":", 1)[1])))
            if name in ("end", "error"):
                break
    return events


def test_sse_for_a_finished_job_sends_progress_then_end(client: TestClient, storage: LocalStorage) -> None:
    rec = upload(client)
    process(storage)
    with client.stream("GET", f"/api/jobs/{rec['job']['id']}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_events(r.iter_lines())
    assert [e[0] for e in events] == ["progress", "end"] and events[0][1]["status"] == "done"


def test_sse_streams_progress_while_the_worker_runs(client: TestClient, storage: LocalStorage) -> None:
    rec = upload(client)
    models = FakeModels()
    delay_asr = models.asr().transcribe

    def slow_transcribe(*a, **k):  # type: ignore[no-untyped-def]
        time.sleep(1.2)  # long enough for the stream to observe the 'running' state
        return delay_asr(*a, **k)

    models.asr().transcribe = slow_transcribe  # type: ignore[method-assign]
    worker = threading.Thread(target=lambda: (time.sleep(0.8), run_once(storage, models)))
    worker.start()
    with client.stream("GET", f"/api/jobs/{rec['job']['id']}/events") as r:
        events = parse_events(r.iter_lines())
    worker.join()
    statuses = [e[1]["status"] for e in events if e[0] == "progress"]
    assert statuses[0] == "queued" and "running" in statuses and statuses[-1] == "done"
    running = [e[1] for e in events if e[0] == "progress" and e[1]["status"] == "running"]
    assert any(s["status"] == "running" for ev in running for s in ev["stages"])
    assert events[-1][0] == "end"


def test_sse_for_unknown_job_reports_an_error(client: TestClient) -> None:
    with client.stream("GET", f"/api/jobs/{uuid.uuid4()}/events") as r:
        events = parse_events(r.iter_lines())
    assert events[0][0] == "error"
