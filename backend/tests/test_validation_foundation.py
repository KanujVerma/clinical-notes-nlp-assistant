import json
import hashlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Base,
    Note,
    NoteRevision,
    Extraction,
    ReviewEvent,
    OperationalIssue,
    Workspace,
)
from schemas.review import ReviewMutationRequest, IssueDisposition
from services.review_service import (
    process_review_mutation,
    StaleReviewError,
    IdempotencyConflictError,
    IncompleteReviewError,
    BlockedReviewError,
)
from validation.checker import check_extraction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_independent_checker_detects_decimal_dose_canary():
    text = "Patient was prescribed .5 mg of digoxin daily."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rev = {"raw_text": text, "sha256": text_hash}
    extraction = {
        "extracted_json": {
            "medications": [
                {"name": "digoxin", "dose": ".5 mg", "action": "start"}
            ]
        }
    }
    issues = check_extraction(rev, extraction)
    codes = [i.issue_code for i in issues]
    assert "A09_DECIMAL_DOSE_LEADING_ZERO_MISSING" in codes


def test_independent_checker_detects_evidence_quote_mismatch():
    text = "Started on Metformin 500 mg PO daily."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rev = {"raw_text": text, "sha256": text_hash}
    extraction = {
        "extracted_json": {
            "medications": [
                {
                    "name": "Metformin",
                    "dose": "500 mg",
                    "evidence": {
                        "start": 0,
                        "end": 7,
                        "raw_quote": "Lisinopril",  # Mismatch!
                    },
                }
            ]
        }
    }
    issues = check_extraction(rev, extraction)
    codes = [i.issue_code for i in issues]
    assert "A08_EVIDENCE_QUOTE_MISMATCH" in codes
    assert any(i.severity == "critical_blocker" for i in issues)


def test_independent_checker_detects_missing_vital_unit():
    text = "Weight: 75. Temperature: 98.6."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rev = {"raw_text": text, "sha256": text_hash}
    extraction = {
        "extracted_json": {
            "vitals": [
                {"vital_type": "weight", "value": "75", "unit": None}
            ]
        }
    }
    issues = check_extraction(rev, extraction)
    codes = [i.issue_code for i in issues]
    assert "A03_MISSING_VITAL_UNIT" in codes


def test_independent_checker_detects_conflicting_duplicate_medications():
    text = "Lisinopril 10 mg daily. Later note: Lisinopril 20 mg daily."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rev = {"raw_text": text, "sha256": text_hash}
    extraction = {
        "extracted_json": {
            "medications": [
                {"name": "Lisinopril", "dose": "10 mg", "action": "start"},
                {"name": "Lisinopril", "dose": "20 mg", "action": "start"},
            ]
        }
    }
    issues = check_extraction(rev, extraction)
    codes = [i.issue_code for i in issues]
    assert "A02_DUPLICATE_MEDICATION_CONFLICT" in codes


def test_review_service_atomic_write_and_derived_outcome_unchanged(db_session):
    raw_text = "Patient seen for routine checkup."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    ws = Workspace(id="ws-123")
    db_session.add(ws)

    note = Note(id=1, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=0)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-1",
        note_id=1,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=1,
        public_id="ext-1",
        note_id=1,
        workspace_id="ws-123",
        source_revision_id="rev-1",
        extracted_json=json.dumps({"medications": [{"id": "m1", "name": "Aspirin"}]}),
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    note.current_source_revision_id = "rev-1"
    note.current_extraction_id = "ext-1"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=1,
        source_revision_id="rev-1",
        extraction_id="ext-1",
        source_hash=text_hash,
        expected_lock_version=0,
        expected_head_event_id=None,
        event_kind="review_completed",
        item_decisions={"m1": {"decision": "accept"}},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    )

    event, is_replay = process_review_mutation(db_session, "ws-123", req)
    assert not is_replay
    assert event.derived_outcome == "reviewed_unchanged"
    assert note.status == "reviewed_unchanged"
    assert note.lock_version == 1
    assert note.review_head_event_id == event.id


def test_review_service_atomic_write_and_derived_outcome_corrected(db_session):
    raw_text = "Patient on Lisinopril."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    ws = Workspace(id="ws-123")
    db_session.add(ws)

    note = Note(id=2, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=0)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-2",
        note_id=2,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=2,
        public_id="ext-2",
        note_id=2,
        workspace_id="ws-123",
        source_revision_id="rev-2",
        extracted_json=json.dumps({"medications": [{"id": "m2", "name": "Lisinopril"}]}),
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    note.current_source_revision_id = "rev-2"
    note.current_extraction_id = "ext-2"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=2,
        source_revision_id="rev-2",
        extraction_id="ext-2",
        source_hash=text_hash,
        expected_lock_version=0,
        expected_head_event_id=None,
        event_kind="review_completed",
        item_decisions={"m2.name": {"decision": "edit", "value": "Lisinopril 20mg"}},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    )

    event, is_replay = process_review_mutation(db_session, "ws-123", req)
    assert not is_replay
    assert event.derived_outcome == "reviewed_corrected"
    assert note.status == "reviewed_corrected"
    assert note.lock_version == 1


def test_review_service_rejects_stale_mutation(db_session):
    raw_text = "Some note text."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    note = Note(id=3, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=1)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-3",
        note_id=3,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=3,
        public_id="ext-3",
        note_id=3,
        workspace_id="ws-123",
        source_revision_id="rev-3",
        extracted_json="{}",
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    note.current_source_revision_id = "rev-3"
    note.current_extraction_id = "ext-3"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=3,
        source_revision_id="rev-3",
        extraction_id="ext-3",
        source_hash=text_hash,
        expected_lock_version=0,  # STALE: current is 1!
        expected_head_event_id=None,
        event_kind="review_completed",
        item_decisions={},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    )

    with pytest.raises(StaleReviewError):
        process_review_mutation(db_session, "ws-123", req)


def test_review_service_idempotency_replay_and_conflict(db_session):
    raw_text = "Idempotency test note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    note = Note(id=4, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=0)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-4",
        note_id=4,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=4,
        public_id="ext-4",
        note_id=4,
        workspace_id="ws-123",
        source_revision_id="rev-4",
        extracted_json="{}",
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    note.current_source_revision_id = "rev-4"
    note.current_extraction_id = "ext-4"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=4,
        source_revision_id="rev-4",
        extraction_id="ext-4",
        source_hash=text_hash,
        expected_lock_version=0,
        expected_head_event_id=None,
        idempotency_key="key-abc-123",
        event_kind="review_completed",
        item_decisions={},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    )

    # First attempt: succeeds
    ev1, is_replay1 = process_review_mutation(db_session, "ws-123", req)
    assert not is_replay1

    # Exact retry with same idempotency key: succeeds as replay
    ev2, is_replay2 = process_review_mutation(db_session, "ws-123", req)
    assert is_replay2
    assert ev2.id == ev1.id

    # Conflicting retry with same key but altered payload: raises IdempotencyConflictError
    req_conflict = req.model_copy(update={"event_kind": "draft_saved"})
    with pytest.raises(IdempotencyConflictError):
        process_review_mutation(db_session, "ws-123", req_conflict)


def test_review_service_rejects_incomplete_acknowledgments(db_session):
    raw_text = "Completeness check note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    note = Note(id=5, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=0)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-5",
        note_id=5,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=5,
        public_id="ext-5",
        note_id=5,
        workspace_id="ws-123",
        source_revision_id="rev-5",
        extracted_json="{}",
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    note.current_source_revision_id = "rev-5"
    note.current_extraction_id = "ext-5"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=5,
        source_revision_id="rev-5",
        extraction_id="ext-5",
        source_hash=text_hash,
        expected_lock_version=0,
        expected_head_event_id=None,
        event_kind="review_completed",
        item_decisions={},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            # Missing medications and instructions!
        },
    )

    with pytest.raises(IncompleteReviewError):
        process_review_mutation(db_session, "ws-123", req)


def test_review_service_blocks_on_open_critical_issues(db_session):
    raw_text = "Critical blocker check note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    note = Note(id=6, workspace_id="ws-123", raw_text=raw_text, source="paste", lock_version=0)
    db_session.add(note)
    db_session.flush()

    rev = NoteRevision(
        id="rev-6",
        note_id=6,
        workspace_id="ws-123",
        revision_number=1,
        raw_text=raw_text,
        normalized_text=raw_text,
        sha256=text_hash,
    )
    db_session.add(rev)

    ext = Extraction(
        id=6,
        public_id="ext-6",
        note_id=6,
        workspace_id="ws-123",
        source_revision_id="rev-6",
        extracted_json="{}",
        pipeline_version="1.0.0",
    )
    db_session.add(ext)

    # Open critical issue
    issue = OperationalIssue(
        id="iss-crit-1",
        workspace_id="ws-123",
        note_id=6,
        source_revision_id="rev-6",
        issue_code="A08_EVIDENCE_QUOTE_MISMATCH",
        severity="critical_blocker",
        category="evidence_mismatch",
        safe_explanation="Quote mismatch",
        status="open",
    )
    db_session.add(issue)

    note.current_source_revision_id = "rev-6"
    note.current_extraction_id = "ext-6"
    db_session.commit()

    req = ReviewMutationRequest(
        note_id=6,
        source_revision_id="rev-6",
        extraction_id="ext-6",
        source_hash=text_hash,
        expected_lock_version=0,
        expected_head_event_id=None,
        event_kind="review_completed",
        item_decisions={},
        category_acknowledgments={
            "metadata": True,
            "vitals": True,
            "medications": True,
            "instructions": True,
        },
    )

    with pytest.raises(BlockedReviewError):
        process_review_mutation(db_session, "ws-123", req)


def test_concurrent_review_writer_race_detected_and_rejected(tmp_path):
    """A18: Real two-connection barrier test verifying optimistic lock CAS rejection."""
    import threading
    import hashlib
    from utils.db import get_engine, init_db, get_session
    from models import Note, NoteRevision, Extraction, ReviewEvent
    from schemas.review import ReviewMutationRequest
    from services.review_service import process_review_mutation

    db_path = str(tmp_path / "concurrent_review.db")
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    raw_text = "Concurrent CAS test note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    with get_session(engine) as session:
        note = Note(id=100, workspace_id="ws-barrier", raw_text=raw_text, source="paste", lock_version=0)
        session.add(note)
        session.flush()

        rev = NoteRevision(
            id="rev-100", note_id=100, workspace_id="ws-barrier", revision_number=1,
            raw_text=raw_text, normalized_text=raw_text, sha256=text_hash
        )
        session.add(rev)

        ext = Extraction(
            id=100, public_id="ext-100", note_id=100, workspace_id="ws-barrier",
            source_revision_id="rev-100", extracted_json="{}", pipeline_version="1.0.0"
        )
        session.add(ext)

        note.current_source_revision_id = "rev-100"
        note.current_extraction_id = "ext-100"
        session.commit()

    barrier = threading.Barrier(2)
    results = {}

    def run_writer(writer_id: str, idempotency_key: str):
        session = get_session(engine)
        req = ReviewMutationRequest(
            note_id=100,
            source_revision_id="rev-100",
            extraction_id="ext-100",
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
            ev, is_replay = process_review_mutation(session, "ws-barrier", req)
            results[writer_id] = ("success", ev.id, is_replay)
        except Exception as e:
            results[writer_id] = ("error", type(e).__name__, str(e))
        finally:
            session.close()

    t1 = threading.Thread(target=run_writer, args=("writer_1", "key-writer-1"))
    t2 = threading.Thread(target=run_writer, args=("writer_2", "key-writer-2"))

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

    # Assert exact event count in database: only 1 event recorded
    with get_session(engine) as session:
        events = session.query(ReviewEvent).filter_by(note_id=100).all()
        assert len(events) == 1
        note = session.query(Note).filter_by(id=100).one()
        assert note.lock_version == 1
        assert note.review_head_event_id == events[0].id


def test_idempotent_retry_and_conflicting_idempotency_key(tmp_path):
    """A19: Concurrent barrier test verifying identical replay vs conflicting payload."""
    import threading
    import hashlib
    from utils.db import get_engine, init_db, get_session
    from models import Note, NoteRevision, Extraction, ReviewEvent
    from schemas.review import ReviewMutationRequest
    from services.review_service import process_review_mutation, IdempotencyConflictError

    db_path = str(tmp_path / "concurrent_idemp.db")
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    raw_text = "Concurrent idempotency test note."
    text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    with get_session(engine) as session:
        note = Note(id=200, workspace_id="ws-idemp", raw_text=raw_text, source="paste", lock_version=0)
        session.add(note)
        session.flush()

        rev = NoteRevision(
            id="rev-200", note_id=200, workspace_id="ws-idemp", revision_number=1,
            raw_text=raw_text, normalized_text=raw_text, sha256=text_hash
        )
        session.add(rev)

        ext = Extraction(
            id=200, public_id="ext-200", note_id=200, workspace_id="ws-idemp",
            source_revision_id="rev-200", extracted_json="{}", pipeline_version="1.0.0"
        )
        session.add(ext)

        note.current_source_revision_id = "rev-200"
        note.current_extraction_id = "ext-200"
        session.commit()

    # Case 1: Two concurrent requests with IDENTICAL idempotency key and IDENTICAL payload
    barrier = threading.Barrier(2)
    results = {}

    def run_identical(writer_id: str):
        session = get_session(engine)
        req = ReviewMutationRequest(
            note_id=200,
            source_revision_id="rev-200",
            extraction_id="ext-200",
            source_hash=text_hash,
            expected_lock_version=0,
            expected_head_event_id=None,
            event_kind="review_completed",
            item_decisions={},
            category_acknowledgments={
                "metadata": True, "vitals": True, "medications": True, "instructions": True
            },
            idempotency_key="shared-idemp-key-1",
        )
        try:
            barrier.wait(timeout=5)
            ev, is_replay = process_review_mutation(session, "ws-idemp", req)
            results[writer_id] = ("success", ev.id, is_replay)
        except Exception as e:
            results[writer_id] = ("error", type(e).__name__, str(e))
        finally:
            session.close()

    t1 = threading.Thread(target=run_identical, args=("writer_A",))
    t2 = threading.Thread(target=run_identical, args=("writer_B",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Both must succeed and point to the same review event ID
    assert results["writer_A"][0] == "success"
    assert results["writer_B"][0] == "success"
    assert results["writer_A"][1] == results["writer_B"][1]
    # One created it (is_replay=False), the other replayed it (is_replay=True)
    replays = {results["writer_A"][2], results["writer_B"][2]}
    assert replays == {False, True}

    with get_session(engine) as session:
        events = session.query(ReviewEvent).filter_by(note_id=200).all()
        assert len(events) == 1

    # Case 2: Subsequent request with SAME idempotency key but CONFLICTING payload
    with get_session(engine) as session:
        conflicting_req = ReviewMutationRequest(
            note_id=200,
            source_revision_id="rev-200",
            extraction_id="ext-200",
            source_hash=text_hash,
            expected_lock_version=0,
            expected_head_event_id=None,
            event_kind="draft_saved",  # CONFLICT: different event_kind!
            item_decisions={},
            category_acknowledgments={
                "metadata": False, "vitals": False, "medications": False, "instructions": False
            },
            idempotency_key="shared-idemp-key-1",
        )
        with pytest.raises(IdempotencyConflictError):
            process_review_mutation(session, "ws-idemp", conflicting_req)

