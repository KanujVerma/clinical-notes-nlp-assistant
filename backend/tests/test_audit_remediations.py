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
    assert "exact source evidence or a no-direct-span reason" in str(exc_info.value)


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


def test_nested_medication_edit_with_invalid_value_rejected():
    from services.review_service import derive_reviewed_snapshot, InvalidReviewPayloadError
    extracted = {
        "vitals": {}, "instructions": {}, "metadata": {},
        "medications": [{"id": "m1", "name": "aspirin", "dose": "81 mg"}],
    }
    # Nested edit with non-string/object value must be rejected
    decisions = {
        "med.m1": {
            "decision": "accept",
            "attribute_decisions": {
                "dose": {"decision": "edit", "value": {"malformed": "object"}}
            }
        }
    }
    with pytest.raises(InvalidReviewPayloadError) as exc_info:
        derive_reviewed_snapshot(
            extracted_data=extracted,
            item_decisions=decisions,
            category_acknowledgments={"vitals": True, "instructions": True, "metadata": True, "medications": True},
            is_completing=True,
            raw_text="aspirin 81 mg",
        )
    assert "requires a nonempty bounded string value" in str(exc_info.value)


def test_workspace_expiration_utc_isoformat(client):
    res = client.post("/api/workspaces")
    assert res.status_code == 201
    exp = res.json.get("expires_at")
    assert exp is not None
    # Must end with UTC timezone indicator (+00:00 or Z)
    assert "+00:00" in exp or exp.endswith("Z")


def test_worker_execution_updates_status_succeeded(app):
    from worker import run_worker_loop
    from models import Note, NoteRevision, Extraction, Job
    import uuid

    engine = app.config["ENGINE"]
    with get_session(engine) as session:
        ws_id = "test-ws"
        note = Note(workspace_id=ws_id, source="paste", raw_text="BP 120/80")
        session.add(note)
        session.flush()
        rev = NoteRevision(
            note_id=note.id, workspace_id=ws_id, raw_text="BP 120/80",
            normalized_text="BP 120/80", sha256="h1"
        )
        session.add(rev)
        session.flush()
        note.current_source_revision_id = rev.id
        ext = Extraction(
            note_id=note.id, workspace_id=ws_id, source_revision_id=rev.id,
            extracted_json="{}", pipeline_version="0.1.0", public_id="ext-orig"
        )
        session.add(ext)
        session.flush()
        note.current_extraction_id = ext.public_id
        session.commit()

        job = Job(
            id=str(uuid.uuid4()),
            workspace_id=ws_id,
            kind="extraction",
            note_id=note.id,
            source_revision_id=rev.id,
            payload_json=json.dumps({
                "expected_extraction_id": ext.public_id,
                "expected_lock_version": 0,
            }),
            status="queued",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    run_worker_loop(engine, once=True)

    with get_session(engine) as session:
        j = session.query(Job).filter(Job.id == job_id).one()
        assert j.status == "succeeded"
        assert j.result_json is not None
        assert j.finished_at is not None


def test_independent_canary_detects_source_naked_decimal_dropped_by_extractor():
    import hashlib
    from validation.checker import check_extraction
    text = "- Warfarin .5 mg PO daily"
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rev = {"raw_text": text, "sha256": text_hash}
    # Extractor erroneously dropped the leading decimal and extracted 5 mg
    extraction = {
        "extracted_json": {
            "medications": [
                {
                    "name": "Warfarin",
                    "dose": "5 mg",
                    "route": "PO",
                    "frequency": "daily",
                    "evidence": {"start": 2, "end": 25, "raw_quote": "Warfarin .5 mg PO daily"},
                }
            ]
        }
    }
    issues = check_extraction(rev, extraction)
    codes = [i.issue_code for i in issues]
    assert "A09_DECIMAL_DOSE_LEADING_ZERO_MISSING" in codes


def test_history_detail_endpoint_returns_review_head_with_decisions(client):
    import hashlib
    from models import Note, NoteRevision, Extraction, ReviewEvent
    engine = client.application.config["ENGINE"]
    with get_session(engine) as session:
        ws_id = "test-history-ws"
        note = Note(workspace_id=ws_id, source="paste", raw_text="Patient stable", status="reviewed_corrected")
        session.add(note)
        session.flush()
        rev = NoteRevision(note_id=note.id, workspace_id=ws_id, raw_text="Patient stable", normalized_text="Patient stable", sha256="h2")
        session.add(rev)
        session.flush()
        note.current_source_revision_id = rev.id
        ext = Extraction(note_id=note.id, workspace_id=ws_id, source_revision_id=rev.id, extracted_json='{"vitals":{"heart_rate":"72"}}', pipeline_version="0.1.0", public_id="ext-hist")
        session.add(ext)
        session.flush()
        note.current_extraction_id = ext.public_id

        event = ReviewEvent(
            workspace_id=ws_id,
            note_id=note.id,
            source_revision_id=rev.id,
            extraction_id=ext.public_id,
            event_kind="draft_saved",
            derived_outcome="review_in_progress",
            item_decisions_json=json.dumps({"vitals.heart_rate": "accept"}),
            category_acknowledgments_json=json.dumps({"vitals": True}),
            reviewed_snapshot_json='{"vitals":{"heart_rate":"72"}}',
            source_hash="h2",
            expected_lock_version=0,
            idempotency_key="idemp-hist-1",
        )
        session.add(event)
        session.flush()
        note.review_head_event_id = event.id
        session.commit()
        note_id = note.id

    res = client.get(f"/api/history/{note_id}", headers={"X-Workspace-ID": ws_id})
    assert res.status_code == 200
    data = res.json
    assert data.get("review_head") is not None
    assert data["review_head"]["event_kind"] == "draft_saved"
    assert data["review_head"]["item_decisions"] == {"vitals.heart_rate": "accept"}


def test_metrics_excludes_legacy_validations_when_note_needs_review(client):
    from models import Note, NoteRevision, Extraction, Validation
    engine = client.application.config["ENGINE"]
    with get_session(engine) as session:
        ws_id = "test-metrics-legacy-ws"
        # Note with legacy validation, but currently needs_review
        note = Note(workspace_id=ws_id, source="paste", raw_text="Test Note", status="needs_review")
        session.add(note)
        session.flush()
        val = Validation(
            note_id=note.id,
            status="accepted",
            validated_json='{"vitals":{"heart_rate":"80"}}',
            correction_count=0,
            review_duration_ms=5000,
        )
        session.add(val)
        session.commit()

    res = client.get("/api/metrics", headers={"X-Workspace-ID": ws_id})
    assert res.status_code == 200
    data = res.json
    # Because the note status is needs_review, the legacy validation must NOT be counted as accepted
    by_status = {item["status"]: item["count"] for item in data["db_stats"]["by_status"]}
    assert by_status.get("accepted", 0) == 0
