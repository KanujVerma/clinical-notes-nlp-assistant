"""Regression gates for fail-closed schema evolution and concurrent job IDs.

These use only disposable SQLite files, never a real account database.
"""
import datetime
import json
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from models import Job
from utils.db import get_engine, get_session, init_db
from worker import claim_next_job


def test_failed_migration_is_fatal_and_does_not_create_all(tmp_path, monkeypatch):
    from alembic import command

    engine = get_engine(f"sqlite:///{tmp_path / 'migration_failure.db'}")

    def fail(*args, **kwargs):
        raise RuntimeError("deliberately injected migration failure")

    monkeypatch.setattr(command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="deliberately injected"):
        init_db(engine)

    from sqlalchemy import inspect
    assert "notes" not in inspect(engine).get_table_names()


def test_hosted_schema_gate_rejects_blank_database(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'unmigrated.db'}")
    with pytest.raises(RuntimeError, match="revision"):
        init_db(engine, migrate=False)


def test_legacy_backfill_preserves_payloads_and_does_not_certify_review(tmp_path):
    dbfile = tmp_path / "legacy.db"
    connection = sqlite3.connect(dbfile)
    connection.executescript("""
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY, raw_text TEXT NOT NULL, source TEXT NOT NULL,
            session_id TEXT, created_at TEXT, filename TEXT, ocr_confidence REAL
        );
        CREATE TABLE extractions (
            id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL,
            extracted_json TEXT NOT NULL, pipeline_version TEXT NOT NULL,
            extracted_at TEXT
        );
        CREATE TABLE validations (
            id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL,
            validated_json TEXT NOT NULL, status TEXT NOT NULL,
            review_duration_ms INTEGER, correction_count INTEGER,
            validated_at TEXT
        );
        INSERT INTO notes VALUES (7, 'BP 120/80', 'paste', 'old-session',
          '2026-01-01 09:00:00', 'synthetic.txt', NULL);
        INSERT INTO extractions VALUES (13, 7,
          '{"vitals":{"blood_pressure":{"value":"120/80"}}}',
          'old-rules', '2026-01-01 09:01:00');
        INSERT INTO validations VALUES (19, 7,
          '{"vitals":{"blood_pressure":{"value":"130/85"}}}',
          'corrected', 5000, 1, '2026-01-01 09:02:00');
    """)
    connection.commit()
    connection.close()

    engine = get_engine(f"sqlite:///{dbfile}")
    init_db(engine)
    with get_session(engine) as session:
        from models import Note, NoteRevision, Extraction, Validation
        note = session.query(Note).filter_by(id=7).one()
        old_ext = session.query(Extraction).filter_by(id=13).one()
        old_val = session.query(Validation).filter_by(id=19).one()
        rev = session.query(NoteRevision).filter_by(id=note.current_source_revision_id).one()
        assert rev.raw_text == "BP 120/80"
        assert rev.creation_reason == "legacy_import_unverified"
        assert note.workspace_id == "old-session"
        assert note.status == "legacy_unverified"
        assert note.review_head_event_id is None
        assert old_ext.extracted_json == '{"vitals":{"blood_pressure":{"value":"120/80"}}}'
        assert old_ext.status == "legacy_unverified"
        assert old_val.validated_json == '{"vitals":{"blood_pressure":{"value":"130/85"}}}'
        assert old_val.status == "corrected"

    init_db(engine)
    with get_session(engine) as session:
        from models import NoteRevision
        assert session.query(NoteRevision).filter_by(note_id=7).count() == 1


def test_job_key_is_unique_in_database_and_body_changes_conflict(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'job_idempotency.db'}",
    })
    client = app.test_client()
    headers = {"X-Session-ID": "synthetic-test-workspace"}
    body = {"kind": "eval_run", "idempotency_key": "same-job-key"}
    first = client.post("/api/jobs", json=body, headers=headers)
    assert first.status_code == 202
    replay = client.post("/api/jobs", json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json["job_id"] == first.json["job_id"]

    # A *valid* but changed request must return the actual idempotency
    # conflict, not merely a 404 for an unrelated nonexistent note.
    note = client.post("/api/notes", json={"text": "Synthetic BP: 120/80."},
                       headers=headers)
    assert note.status_code == 201
    changed = client.post("/api/jobs", json={
        "kind": "extraction", "note_id": note.json["note_id"],
        "source_revision_id": note.json["revision_id"],
        "idempotency_key": "same-job-key",
    }, headers=headers)
    assert changed.status_code == 409
    assert changed.json["code"] == "IDEMPOTENCY_CONFLICT"

    engine = app.config["ENGINE"]
    with get_session(engine) as session:
        session.add(Job(workspace_id=headers["X-Session-ID"],
                        kind="eval_run", idempotency_key="same-job-key",
                        request_hash="different", payload_json="{}"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_worker_finalizes_exhausted_lease_even_with_empty_queue(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'worker_leases.db'}")
    init_db(engine)
    with get_session(engine) as session:
        row = Job(
            workspace_id="synthetic",
            kind="eval_run",
            status="running",
            attempt_number=3,
            lease_owner="worker-stopped",
            lease_expiry=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=1),
            payload_json="{}",
        )
        session.add(row)
        session.commit()
        row_id = row.id

    with get_session(engine) as session:
        assert claim_next_job(session, "replacement-worker") is None

    with get_session(engine) as session:
        row = session.query(Job).filter_by(id=row_id).one()
        assert row.status == "failed"
        assert row.error_code == "ATTEMPTS_EXHAUSTED"
