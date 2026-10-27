"""Release-blocker regressions for version-bound reviews and API bypasses.

These are deliberately stronger than the legacy smoke suite. Any failure is a
release blocker until the corresponding authoritative service is corrected.
"""
import pytest
from app import create_app
from models import Note, Extraction, OperationalIssue
from utils.db import get_session
from config import Config


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'release_guards.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def _new_note(client, sid="f12d43be-11ba-4c46-aa13-f5869b129989"):
    headers = {"X-Session-ID": sid, "X-Workspace-ID": sid}
    res = client.post("/api/notes", json={"text": "Synthetic demo follow up in one week."}, headers=headers)
    assert res.status_code == 201, res.json
    return headers, res.json


def _review_payload(note, source_hash):
    extraction = note.get("extracted_json") or {}
    decisions = {}
    for category in ("vitals", "instructions", "metadata"):
        for key, item in (extraction.get(category) or {}).items():
            if item is not None:
                decisions[f"{category}.{key}"] = {"decision": "accept"}
    for idx, med in enumerate(extraction.get("medications") or []):
        med_id = med.get("id") or med.get("source_occurrence_id") or f"med_{idx}"
        decisions[f"med.{med_id}"] = {"decision": "accept"}
    return {
        "schema_version": "2.0.0",
        "note_id": note["note_id"],
        "source_revision_id": note["revision_id"],
        "extraction_id": note["extraction_id"],
        "source_hash": source_hash,
        "expected_lock_version": 0,
        "expected_head_event_id": None,
        "idempotency_key": "test-release-review-0001",
        "event_kind": "review_completed",
        "item_decisions": decisions,
        "category_acknowledgments": {
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    }


def test_legacy_mutable_validation_and_unbound_text_update_are_rejected(client):
    headers, note = _new_note(client)
    legacy = client.post(
        "/api/validate",
        headers=headers,
        json={"note_id": note["note_id"], "status": "accepted", "validated_json": {}},
    )
    assert legacy.status_code == 422
    assert legacy.json["code"] == "REVIEW_BINDING_REQUIRED"

    old_put = client.put(
        f'/api/notes/{note["note_id"]}/text',
        headers=headers,
        json={"text": "A different document"},
    )
    assert old_put.status_code == 422
    assert old_put.json["code"] == "REVISION_BINDING_REQUIRED"

    with get_session(client.application.config["ENGINE"]) as session:
        assert session.query(Extraction).filter(Extraction.note_id == note["note_id"]).count() == 1


def test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail(client):
    headers, note = _new_note(client)
    endpoint = f'/api/notes/{note["note_id"]}/revisions'
    payload = {
        "raw_text": "Synthetic updated text, with no real patient data.",
        "reason": "human_transcription_edit",
        "expected_source_revision_id": note["revision_id"],
        "expected_lock_version": 0,
    }
    new_revision = client.post(endpoint, headers=headers, json=payload)
    assert new_revision.status_code == 201, new_revision.json
    assert new_revision.json["revision_number"] == 2
    assert new_revision.json["extraction_id"] != note["extraction_id"]
    assert client.post(endpoint, headers=headers, json=payload).status_code == 409

    with get_session(client.application.config["ENGINE"]) as session:
        assert session.query(Extraction).filter(Extraction.note_id == note["note_id"]).count() == 2


def test_open_integrity_blocker_cannot_be_acknowledged_or_completed(client):
    headers, note = _new_note(client)
    source = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json
    with get_session(client.application.config["ENGINE"]) as session:
        issue = OperationalIssue(
            workspace_id=headers["X-Session-ID"],
            note_id=note["note_id"],
            source_revision_id=note["revision_id"],
            extraction_id=note["extraction_id"],
            issue_code="EVIDENCE_SPAN_INVALID",
            severity="critical_blocker",
            category="evidence_mismatch",
            safe_explanation="Deliberately corrupted source evidence",
        )
        session.add(issue)
        session.commit()
        issue_id = issue.id

    dismiss = client.post(
        f"/api/issues/{issue_id}/disposition",
        headers=headers,
        json={"disposition": "resolved", "reason": "I acknowledge the risk"},
    )
    assert dismiss.status_code == 409

    review = _review_payload(note, source["sha256"])
    review["issue_dispositions"] = {
        issue_id: {"disposition": "resolved", "reason": "I acknowledge the risk"}
    }
    response = client.post(
        f'/api/extractions/{note["extraction_id"]}/reviews',
        headers=headers,
        json=review,
    )
    assert response.status_code == 422
    assert response.json["code"] == "BLOCKED_REVIEW"


def test_hosted_mode_rejects_arbitrary_input_and_computation(client, monkeypatch):
    monkeypatch.setattr(Config, "APP_MODE", "hosted_demo")
    headers = {"X-Session-ID": "4adf2fe7-d4dd-4774-82f9-a2d74f0be118"}
    assert client.post("/api/notes", json={"text": "arbitrary"}, headers=headers).status_code == 403
    assert client.post("/api/upload", headers=headers).status_code == 403
    assert client.post("/api/evaluation/runs", headers=headers).status_code == 403
    assert client.post("/api/jobs", json={"kind": "eval_run"}, headers=headers).status_code == 403


def test_only_current_completed_head_removes_note_from_queue(client):
    headers, note = _new_note(client)
    source = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json
    result = client.post(
        f'/api/extractions/{note["extraction_id"]}/reviews',
        headers=headers,
        json=_review_payload(note, source["sha256"]),
    )
    assert result.status_code == 201, result.json
    pending = client.get("/api/queue", headers=headers).json
    assert note["note_id"] not in {n["id"] for n in pending["notes"]}

    changed = client.post(
        f'/api/notes/{note["note_id"]}/revisions',
        headers=headers,
        json={
            "raw_text": "New synthetic revision.",
            "expected_source_revision_id": note["revision_id"],
            "expected_lock_version": 1,
        },
    )
    assert changed.status_code == 201, changed.json
    pending_after = client.get("/api/queue", headers=headers).json
    assert note["note_id"] in {n["id"] for n in pending_after["notes"]}


def test_client_snapshot_cannot_invent_medication_without_matching_decisions(client):
    """P0 guard: this must reject client-controlled 'reviewed' JSON not derived from decisions."""
    headers, note = _new_note(client)
    source = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json
    payload = _review_payload(note, source["sha256"])
    payload["reviewed_snapshot"] = {
        "medications": [{"name": "invented drug", "dose": "999 mg"}],
        "vitals": {}, "instructions": {}, "metadata": {},
    }
    # Must fail closed until the server can derive and verify the snapshot.
    response = client.post(
        f'/api/extractions/{note["extraction_id"]}/reviews',
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422, response.json


def test_completion_requires_per_field_decisions_even_when_categories_checked(client):
    headers, note = _new_note(client)
    # The given extraction may or may not contain a named field depending on
    # parser rules; make a source-bound nonempty vital fixture explicitly.
    from models import Extraction
    with get_session(client.application.config["ENGINE"]) as session:
        ext = session.query(Extraction).filter(Extraction.public_id == note["extraction_id"]).one()
        import json
        extracted = json.loads(ext.extracted_json)
        extracted["vitals"] = {"heart_rate": {"value": "72 bpm"}}
        ext.extracted_json = json.dumps(extracted)
        session.commit()

    source = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json
    payload = _review_payload(note, source["sha256"])
    payload["item_decisions"] = {}
    response = client.post(
        f'/api/extractions/{note["extraction_id"]}/reviews',
        headers=headers, json=payload,
    )
    assert response.status_code == 422
    assert response.json["code"] == "INCOMPLETE_REVIEW"


def test_server_rejects_same_name_but_edited_client_medication(client):
    headers, note = _new_note(client)
    from models import Extraction
    import json
    with get_session(client.application.config["ENGINE"]) as session:
        ext = session.query(Extraction).filter(Extraction.public_id == note["extraction_id"]).one()
        ext.extracted_json = json.dumps({
            "pipeline_version": "0.1.0",
            "metadata": {}, "vitals": {}, "instructions": {},
            "medications": [{"name": "metformin", "dose": "500 mg", "route": "PO"}],
        })
        session.commit()
    source = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json
    payload = _review_payload(note, source["sha256"])
    payload["item_decisions"] = {"med.med_0": {"decision": "accept"}}
    payload["reviewed_snapshot"] = {
        "metadata": {}, "vitals": {}, "instructions": {},
        "medications": [{
            "id": "med_0", "name": "metformin", "dose": "5000 mg", "route": "PO",
        }],
    }
    response = client.post(
        f'/api/extractions/{note["extraction_id"]}/reviews',
        headers=headers, json=payload,
    )
    assert response.status_code == 422
    assert response.json["code"] == "INVALID_REVIEW_PAYLOAD"
