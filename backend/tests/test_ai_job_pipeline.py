"""Integration tests for the source-bound, durable, local-only AI job workflow.

No paid, external or real model calls. Separate live-model measurements are
covered by the optional vision_benchmark.py command on the owner's Mac.
"""
import json

import pytest

from app import create_app
from models import InferenceRun, Note, ReviewEvent
from services.inference_pipeline import InferenceBindingError
from utils.db import get_session
from worker import run_worker_loop


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'ai_jobs.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def _note(client, workspace_id="synthetic-ai-job-workspace"):
    headers = {"X-Session-ID": workspace_id}
    created = client.post(
        "/api/notes",
        headers=headers,
        json={"text": "Synthetic note. Lisinopril 10 mg PO daily. BP 120/80."},
    )
    assert created.status_code == 201, created.json
    return headers, created.json


def _request(note, **changes):
    payload = {
        "adapter": "text",
        "source_revision_id": note["revision_id"],
        "extraction_id": note["extraction_id"],
        "page_number": 1,
        "idempotency_key": "ai-job-idempotent-001",
    }
    payload.update(changes)
    return payload


def _fake_model(snapshot):
    return {
        "task_type": "semantic_candidates",
        "model": snapshot["model"],
        "model_digest": "test-local-model-digest",
        "candidates": {"medications": [{"name": "Lisinopril", "dose": "10 mg"}]},
        "discrepancies": [],
        "duration_ms": 9,
        "input_hash": snapshot["input_hash"],
        "prompt_template_hash": snapshot["prompt_template_hash"],
    }


def test_ai_endpoint_enqueues_without_calling_model_then_worker_persists_result(
    client, monkeypatch
):
    headers, note = _note(client)
    calls = []

    def mocked_model(snapshot):
        calls.append(snapshot["source_revision_id"])
        return _fake_model(snapshot)

    monkeypatch.setattr("services.inference_pipeline.run_local_inference", mocked_model)
    queued = client.post(
        f'/api/notes/{note["note_id"]}/ai-candidates',
        headers=headers,
        json=_request(note),
    )
    assert queued.status_code == 202, queued.json
    assert queued.json["status"] == "queued"
    assert not calls  # Proof Flask itself made no model call

    replay = client.post(
        f'/api/notes/{note["note_id"]}/ai-candidates',
        headers=headers, json=_request(note),
    )
    assert replay.status_code == 200
    assert replay.json["job_id"] == queued.json["job_id"]

    run_worker_loop(client.application.config["ENGINE"], once=True)
    assert calls == [note["revision_id"]]
    job = client.get(f'/api/jobs/{queued.json["job_id"]}', headers=headers)
    assert job.status_code == 200
    assert job.json["status"] == "succeeded"
    event_id = job.json["result"]["inference_run_id"]

    records = client.get(
        f'/api/notes/{note["note_id"]}/ai-candidates', headers=headers,
    )
    assert records.status_code == 200
    assert len(records.json) == 1
    assert records.json[0]["id"] == event_id
    assert records.json[0]["source_revision_id"] == note["revision_id"]
    assert records.json[0]["model_digest"] == "test-local-model-digest"
    assert records.json[0]["is_current"] is True
    assert records.json[0]["candidates"]["medications"][0]["dose"] == "10 mg"

    state = client.get(f'/api/notes/{note["note_id"]}', headers=headers)
    assert state.status_code == 200
    assert state.json["status"] == "needs_review"
    assert state.json["review_head"] is None
    assert state.json["current_extraction_id"] == note["extraction_id"]

    with get_session(client.application.config["ENGINE"]) as session:
        assert session.query(ReviewEvent).filter_by(note_id=note["note_id"]).count() == 0
        assert session.query(InferenceRun).filter_by(note_id=note["note_id"]).count() == 1


def test_ai_job_rejects_stale_source_before_model_is_run(client, monkeypatch):
    headers, note = _note(client)
    invoked = []
    monkeypatch.setattr(
        "services.inference_pipeline.run_local_inference",
        lambda snapshot: invoked.append(snapshot) or _fake_model(snapshot),
    )
    queued = client.post(
        f'/api/notes/{note["note_id"]}/ai-candidates',
        headers=headers,
        json=_request(note),
    )
    assert queued.status_code == 202
    changed = client.post(
        f'/api/notes/{note["note_id"]}/revisions',
        headers=headers,
        json={
            "raw_text": "New synthetic source revision, BP 110/70.",
            "expected_source_revision_id": note["revision_id"],
            "expected_lock_version": 0,
        },
    )
    assert changed.status_code == 201, changed.json

    run_worker_loop(client.application.config["ENGINE"], once=True)
    assert invoked == []
    status = client.get(f'/api/jobs/{queued.json["job_id"]}', headers=headers).json
    assert status["status"] == "failed"
    assert status["error_code"] == "AI_STALE_SOURCE"
    with get_session(client.application.config["ENGINE"]) as session:
        assert session.query(InferenceRun).filter_by(note_id=note["note_id"]).count() == 0


def test_ai_job_reports_model_error_without_touching_extraction(client, monkeypatch):
    headers, note = _note(client)

    def model_unavailable(snapshot):
        raise InferenceBindingError("MODEL_NOT_INSTALLED")

    monkeypatch.setattr("services.inference_pipeline.run_local_inference", model_unavailable)
    queued = client.post(
        f'/api/notes/{note["note_id"]}/ai-candidates',
        headers=headers, json=_request(note),
    )
    assert queued.status_code == 202
    run_worker_loop(client.application.config["ENGINE"], once=True)
    state = client.get(f'/api/jobs/{queued.json["job_id"]}', headers=headers)
    assert state.json["status"] == "failed"
    assert state.json["error_code"] == "MODEL_NOT_INSTALLED"
    assert "Synthetic note" not in (state.json.get("error_message") or "")
    note_state = client.get(f'/api/notes/{note["note_id"]}', headers=headers).json
    assert note_state["current_extraction_id"] == note["extraction_id"]


def test_inference_idempotency_conflict_and_per_workspace_queue_limit(client):
    headers, note = _note(client)
    path = f'/api/notes/{note["note_id"]}/ai-candidates'
    queued = client.post(path, headers=headers, json=_request(note))
    assert queued.status_code == 202
    changed = client.post(
        path, headers=headers,
        json=_request(note, page_number=2),
    )
    assert changed.status_code == 409
    assert changed.json["code"] == "IDEMPOTENCY_CONFLICT"
    independent = client.post(
        path, headers=headers,
        json=_request(note, idempotency_key="another-job-key"),
    )
    assert independent.status_code == 429
    assert independent.json["code"] == "INFERENCE_BUSY"


def test_same_source_reextraction_marks_prior_ai_candidate_historical(client, monkeypatch):
    headers, note = _note(client)
    monkeypatch.setattr(
        "services.inference_pipeline.run_local_inference", _fake_model
    )
    queued = client.post(
        f'/api/notes/{note["note_id"]}/ai-candidates',
        headers=headers, json=_request(note),
    )
    assert queued.status_code == 202
    run_worker_loop(client.application.config["ENGINE"], once=True)
    current = client.get(
        f'/api/notes/{note["note_id"]}/ai-candidates', headers=headers,
    ).json
    assert len(current) == 1
    assert current[0]["is_current"] is True

    rerun = client.post("/api/jobs", headers=headers, json={
        "kind": "extraction",
        "note_id": note["note_id"],
        "source_revision_id": note["revision_id"],
        "idempotency_key": "source-reextraction-001",
    })
    assert rerun.status_code == 202, rerun.json
    run_worker_loop(client.application.config["ENGINE"], once=True)
    rerun_status = client.get(f'/api/jobs/{rerun.json["job_id"]}', headers=headers)
    assert rerun_status.json["status"] == "succeeded", rerun_status.json

    old = client.get(
        f'/api/notes/{note["note_id"]}/ai-candidates', headers=headers,
    ).json
    assert len(old) == 1
    assert old[0]["is_current"] is False
    assert old[0]["extraction_id"] == note["extraction_id"]


def test_hosted_blocks_local_ai_jobs_at_server(client, monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    response = client.post("/api/notes/99/ai-candidates", json={})
    assert response.status_code == 403
    assert response.json["code"] == "FEATURE_RESTRICTED"
