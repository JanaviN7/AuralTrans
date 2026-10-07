import io
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from auraltrans import recordings
from auraltrans.db.models import Artifact, Job, Recording, Speaker, Utterance
from auraltrans.db.session import session_scope
from auraltrans.pipeline.runner import run_job
from auraltrans.pipeline.stages import STAGES, checkpoint_valid, key
from auraltrans.storage.local import LocalStorage
from auraltrans.worker.runner import claim_next, requeue_stale_jobs, run_once
from tests.fakes import FakeModels, fake_prepare_audio


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("auraltrans.pipeline.steps.prepare_audio", fake_prepare_audio)


def make_recording(storage: LocalStorage, name: str = "meeting.wav") -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as s:
        rec, job = recordings.create_recording(s, storage, filename=name, stream=io.BytesIO(b"fake audio bytes"))
        return rec.id, job.id


def job_row(job_id: uuid.UUID) -> Job:
    with session_scope() as s:
        job = s.get(Job, job_id)
        assert job is not None
        return job


def test_full_run_produces_transcript_rows_checkpoints_and_timings(db, storage) -> None:  # type: ignore[no-untyped-def]
    rid, jid = make_recording(storage)
    models = FakeModels()
    assert run_once(storage, models) is True

    job = job_row(jid)
    assert job.status == "done" and job.progress == 1.0 and job.error is None
    assert job.attempts == 1 and job.model_versions == {"asr": "fake", "diarization": "fake"}
    assert [job.stage_timings[s.name]["status"] for s in STAGES] == ["done"] * 5

    with session_scope() as s:
        rec = s.get(Recording, rid)
        assert rec is not None and rec.status == "ready" and rec.duration_s == 9.0 and rec.language == "en"
        speakers = s.scalars(select(Speaker).where(Speaker.recording_id == rid).order_by(Speaker.label)).all()
        assert [sp.label for sp in speakers] == ["SPEAKER_00", "SPEAKER_01"]
        assert all(sp.color and sp.talk_time_s > 0 for sp in speakers)
        utts = s.scalars(select(Utterance).where(Utterance.recording_id == rid).order_by(Utterance.idx)).all()
        assert [u.text for u in utts] == [
            "Hello everyone. What does air pollution mean?",
            "Air pollution means harmful substances in the air.",
        ]
        assert utts[0].words[0]["text"] == "Hello" and utts[0].has_overlap and not utts[1].has_overlap  # SPEAKER_01 starts at 2.5 s, before the first utterance ends at 2.75 s
        hits = s.execute(
            text("SELECT idx FROM utterances WHERE recording_id=:r AND tsv @@ plainto_tsquery('english','pollution')"),
            {"r": rid},
        ).all()
        assert sorted(h[0] for h in hits) == [0, 1]  # full-text search works
        assert len(s.scalars(select(Artifact).where(Artifact.recording_id == rid)).all()) == 6
        assert all(checkpoint_valid(s, storage, rid, stage) for stage in STAGES)
    assert storage.exists(key(rid, "artifacts/aligned.json"))


def test_failed_diarization_then_retry_skips_asr(db, storage) -> None:  # type: ignore[no-untyped-def]
    rid, jid = make_recording(storage)
    models = FakeModels(diarizer_fail_with=RuntimeError("out of memory"))
    run_once(storage, models)

    job = job_row(jid)
    assert job.status == "failed" and job.current_stage == "diarize"
    assert "Finding speakers" in (job.error or "") and "out of memory" in (job.error or "")
    assert job.stage_timings["asr"]["status"] == "done" and job.stage_timings["diarize"]["status"] == "failed"
    with session_scope() as s:
        assert s.get(Recording, rid).status == "failed"  # type: ignore[union-attr]

    with session_scope() as s:
        recordings.retry_job(s, storage, jid)  # defaults to the failed stage
    run_once(storage, models)

    job = job_row(jid)
    assert job.status == "done" and job.attempts == 2
    assert models.asr().calls == 1  # ASR ran once in total
    assert job.stage_timings["prepare_audio"]["status"] == "skipped" and job.stage_timings["asr"]["status"] == "skipped"
    assert job.stage_timings["diarize"]["status"] == "done"


def test_killed_worker_resumes_from_checkpoints(db, storage) -> None:  # type: ignore[no-untyped-def]
    """A hard kill (not a normal exception) leaves the job 'running'; a later worker finishes it."""
    _, jid = make_recording(storage)
    models = FakeModels(diarizer_fail_with=SystemExit("killed"))
    with pytest.raises(SystemExit):
        run_once(storage, models)
    assert job_row(jid).status == "running"
    assert requeue_stale_jobs(stale_after_s=3600) == 0  # a fresh heartbeat is not stale

    with session_scope() as s:
        s.get(Job, jid).locked_at = datetime.now(UTC) - timedelta(hours=1)  # type: ignore[union-attr]
    assert requeue_stale_jobs(stale_after_s=60) == 1
    assert job_row(jid).status == "queued"

    run_once(storage, models)
    job = job_row(jid)
    assert job.status == "done" and models.asr().calls == 1
    assert job.stage_timings["asr"]["status"] == "skipped"


def test_editing_a_checkpoint_file_invalidates_it(db, storage) -> None:  # type: ignore[no-untyped-def]
    rid, _ = make_recording(storage)
    run_once(storage, FakeModels())
    storage.put(key(rid, "artifacts/asr.json"), b"{}")  # tampered after the checkpoint was recorded
    with session_scope() as s:
        asr_stage = STAGES[1]
        assert not checkpoint_valid(s, storage, rid, asr_stage)
        assert checkpoint_valid(s, storage, rid, STAGES[0])


def test_two_queued_jobs_run_one_after_another_in_creation_order(db, storage) -> None:  # type: ignore[no-untyped-def]
    first = make_recording(storage, "a.wav")
    second = make_recording(storage, "b.wav")
    models = FakeModels()
    assert run_once(storage, models) and job_row(first[1]).status == "done"
    assert job_row(second[1]).status == "queued"
    assert run_once(storage, models) and job_row(second[1]).status == "done"
    assert run_once(storage, models) is False  # queue is empty


def test_concurrent_workers_never_claim_the_same_job(db, storage) -> None:  # type: ignore[no-untyped-def]
    make_recording(storage)
    barrier = threading.Barrier(2)
    claimed: list[uuid.UUID | None] = []

    def worker(name: str) -> None:
        barrier.wait()
        claimed.append(claim_next(name))

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(c is not None for c in claimed) == [False, True]


def test_empty_audio_result_still_completes(db, storage, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    rid, jid = make_recording(storage)
    models = FakeModels()
    models.asr().transcribe = lambda *a, **k: __import__("auraltrans.speech.asr", fromlist=["x"]).AsrResult(  # type: ignore[method-assign]
        language="en", language_probability=0.5, duration_s=3.0, model="fake", segments=[]
    )
    run_once(storage, models)
    assert job_row(jid).status == "done"
    with session_scope() as s:
        assert s.scalars(select(Utterance).where(Utterance.recording_id == rid)).all() == []


def test_run_job_records_unexpected_errors_without_raising(db, storage) -> None:  # type: ignore[no-untyped-def]
    rid, jid = make_recording(storage)
    storage.delete_prefix(f"recordings/{rid}/original.wav")  # the upload vanished
    claim_next("w")
    assert run_job(jid, storage, FakeModels()) is False
    assert job_row(jid).status == "failed" and "Preparing audio" in (job_row(jid).error or "")
