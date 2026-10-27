import io
import json
import pytest
from app import create_app
from models import Note, NoteRevision, Extraction, OperationalIssue, Job
from utils.db import get_session
from config import Config
from services.review_service import derive_reviewed_snapshot, InvalidReviewPayloadError
from validation.checker import check_extraction


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'audit_remed.db'}",
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_unknown_event_kind_is_rejected(client):
    headers = {"X-Session-ID": "test-remed-session"}
    res = client.post("/api/notes", json={"text": "Metformin 500 mg"}, headers=headers)
    assert res.status_code == 201
    note = res.json

    src = client.get(f'/api/notes/{note["note_id"]}/source', headers=headers).json

    payload = {
        "schema_version": "2.0.0",
        "note_id": note["note_id"],
        "source_revision_id": note["revision_id"],
        "extraction_id": note["extraction_id"],
        "source_hash": src["sha256"],
        "expected_lock_version": 0,
        "event_kind": "finish",  # Unsupported event kind!
        "item_decisions": {},
        "category_acknowledgments": {
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    }
    r = client.post(f'/api/extractions/{note["extraction_id"]}/reviews', headers=headers, json=payload)
    assert r.status_code == 422
    assert r.json["code"] in ("INVALID_REVIEW_PAYLOAD", "SCHEMA_VALIDATION_ERROR")


def test_job_idempotency_key_deduplication(client):
    headers = {"X-Session-ID": "test-job-idempotency"}
    payload = {"kind": "eval_run", "idempotency_key": "unique-idemp-001"}
    r1 = client.post("/api/jobs", headers=headers, json=payload)
    assert r1.status_code == 202
    job1_id = r1.json["job_id"]

    r2 = client.post("/api/jobs", headers=headers, json=payload)
    assert r2.status_code == 200
    assert r2.json["job_id"] == job1_id


def test_added_item_with_unsupported_evidence_rejected():
    empty = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    decisions = {
        "med.new": {
            "decision": "add",
            "value": {"name": "Fabricated drug"},
            "evidence": {"start": 9000, "end": 9010, "raw_quote": "fabricated"},
        }
    }
    with pytest.raises(InvalidReviewPayloadError) as exc_info:
        derive_reviewed_snapshot(
            extracted_data=empty,
            item_decisions=decisions,
            category_acknowledgments={},
            is_completing=True,
            raw_text="BP 120/80 HR 72",
        )
    assert "must carry valid source evidence" in str(exc_info.value)


def test_vitals_with_embedded_units_do_not_raise_missing_unit_warning(app):
    with app.app_context():
        with get_session(app.config["ENGINE"]) as session:
            note = Note(workspace_id="w", source="paste", raw_text="Temp 98.6 F, Weight 172 lbs")
            session.add(note)
            session.flush()
            rev = NoteRevision(
                note_id=note.id,
                workspace_id="w",
                raw_text=note.raw_text,
                normalized_text=note.raw_text,
                sha256="hash",
            )
            session.add(rev)
            session.flush()
            ext = Extraction(
                note_id=note.id,
                workspace_id="w",
                source_revision_id=rev.id,
                extracted_json=json.dumps({
                    "vitals": {
                        "temperature": {"value": "98.6 F", "span": [5, 11]},
                        "weight": {"value": "172 lbs", "span": [20, 27]},
                    },
                    "medications": [],
                    "instructions": {},
                    "metadata": {},
                }),
                pipeline_version="0.1.0",
            )
            session.add(ext)
            session.flush()

            issues = check_extraction(rev, ext)
            unit_issues = [i for i in issues if i.issue_code == "A03_MISSING_VITAL_UNIT"]
            assert len(unit_issues) == 0
