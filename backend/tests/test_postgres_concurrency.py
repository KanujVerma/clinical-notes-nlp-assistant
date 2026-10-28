"""Disposable PostgreSQL integration test for schema migration and true multi-connection concurrency.

Spins up a lightweight isolated local PostgreSQL instance, executes Alembic migrations
to head, and tests multithreaded barrier concurrency with real database connections.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import hashlib
import pytest
from alembic.config import Config as AlembicConfig
from alembic import command
from utils.db import get_engine, init_db, get_session
from models import Note, NoteRevision, Extraction, ReviewEvent, Job
from schemas.review import ReviewMutationRequest
from services.review_service import process_review_mutation


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def postgres_service():
    """Boots an ephemeral PostgreSQL cluster on a random port, yielding its connection URL."""
    initdb_path = "/opt/homebrew/opt/postgresql@15/bin/initdb"
    pg_ctl_path = "/opt/homebrew/opt/postgresql@15/bin/pg_ctl"
    if not os.path.exists(initdb_path) or not os.path.exists(pg_ctl_path):
        pytest.skip("PostgreSQL 15 binary not available for disposable test cluster")

    temp_dir = tempfile.mkdtemp(prefix="test_pg_")
    data_dir = os.path.join(temp_dir, "data")
    log_file = os.path.join(temp_dir, "pg.log")
    port = find_free_port()

    try:
        # 1. Initialize cluster
        subprocess.run(
            [initdb_path, "-D", data_dir, "--no-sync", "-A", "trust"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2. Start server
        subprocess.run(
            [pg_ctl_path, "-D", data_dir, "-l", log_file, "-o", f"-k {temp_dir} -p {port}", "start"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        pg_url = f"postgresql://localhost:{port}/postgres?host={temp_dir}"
        os.environ["DATABASE_SSLMODE"] = "disable"

        yield pg_url

    finally:
        # 3. Stop server and clean up
        subprocess.run(
            [pg_ctl_path, "-D", data_dir, "stop", "-m", "immediate"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_postgres_alembic_upgrade_and_schema_verification(postgres_service):
    """Verifies that Alembic cleanly creates the complete schema on PostgreSQL."""
    engine = get_engine(postgres_service)
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = AlembicConfig(os.path.join(backend_dir, "alembic.ini"))

    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")

    init_db(engine, migrate=False)


def test_postgres_concurrent_review_writer_barrier(postgres_service):
    """Verifies atomic CAS concurrency on PostgreSQL across separate connections."""
    engine = get_engine(postgres_service)
    raw_text = "Postgres concurrent note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    ws_id = "pg-concurrency-ws"

    with get_session(engine) as session:
        note = Note(id=500, workspace_id=ws_id, raw_text=raw_text, source="paste", lock_version=0)
        session.add(note)
        session.flush()

        rev = NoteRevision(
            id="rev-pg-500", note_id=500, workspace_id=ws_id, revision_number=1,
            raw_text=raw_text, normalized_text=raw_text, sha256=text_hash
        )
        session.add(rev)

        ext = Extraction(
            id=500, public_id="ext-pg-500", note_id=500, workspace_id=ws_id,
            source_revision_id="rev-pg-500", extracted_json="{}", pipeline_version="1.0.0"
        )
        session.add(ext)

        note.current_source_revision_id = "rev-pg-500"
        note.current_extraction_id = "ext-pg-500"
        session.commit()

    barrier = threading.Barrier(2)
    results = {}

    def run_writer(writer_id: str, idempotency_key: str):
        session = get_session(engine)
        req = ReviewMutationRequest(
            note_id=500,
            source_revision_id="rev-pg-500",
            extraction_id="ext-pg-500",
            source_hash=text_hash,
            expected_lock_version=0,
            expected_head_event_id=None,
            event_kind="review_completed",
            item_decisions={},
            category_acknowledgments={
                "metadata": True, "vitals": True, "medications": True, "instructions": True
            },
            idempotency_key=idempotency_key,
        )
        try:
            barrier.wait(timeout=5)
            ev, is_replay = process_review_mutation(session, ws_id, req)
            results[writer_id] = ("success", ev.id, is_replay)
        except Exception as e:
            results[writer_id] = ("error", type(e).__name__, str(e))
        finally:
            session.close()

    t1 = threading.Thread(target=run_writer, args=("writer_1", "pg-key-1"))
    t2 = threading.Thread(target=run_writer, args=("writer_2", "pg-key-2"))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one succeeded and one failed with StaleReviewError
    statuses = [res[0] for res in results.values()]
    assert "success" in statuses
    assert "error" in statuses

    error_types = [res[1] for res in results.values() if res[0] == "error"]
    assert "StaleReviewError" in error_types

    # Assert exact event count in PostgreSQL database: only 1 event recorded
    with get_session(engine) as session:
        events = session.query(ReviewEvent).filter_by(note_id=500).all()
        assert len(events) == 1
        note = session.query(Note).filter_by(id=500).one()
        assert note.lock_version == 1
        assert note.review_head_event_id == events[0].id


def test_postgres_concurrent_job_creation_idempotency_barrier(postgres_service):
    """Verifies job creation idempotency barrier on PostgreSQL."""
    engine = get_engine(postgres_service)
    ws_id = "pg-job-idemp-ws"
    barrier = threading.Barrier(2)
    results = {}

    from app import create_app
    app = create_app({"TESTING": True, "DATABASE_URL": postgres_service})

    def run_creator(thread_id: str):
        client = app.test_client()
        barrier.wait(timeout=5)
        res = client.post(
            "/api/jobs",
            json={"kind": "eval_run", "idempotency_key": "pg-shared-job-key"},
            headers={"X-Workspace-ID": ws_id},
        )
        results[thread_id] = (res.status_code, res.json)

    t1 = threading.Thread(target=run_creator, args=("c1",))
    t2 = threading.Thread(target=run_creator, args=("c2",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Both must get 200/202 with the exact same job ID
    assert results["c1"][0] in (200, 202)
    assert results["c2"][0] in (200, 202)
    job_id_1 = results["c1"][1]["job_id"]
    job_id_2 = results["c2"][1]["job_id"]
    assert job_id_1 == job_id_2

    with get_session(engine) as session:
        jobs = session.query(Job).filter_by(workspace_id=ws_id, idempotency_key="pg-shared-job-key").all()
        assert len(jobs) == 1
