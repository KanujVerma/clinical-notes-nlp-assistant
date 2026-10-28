import os
import sys
import time
import json
import uuid
import datetime
import hashlib
from typing import Optional
from sqlalchemy import or_, and_, update
from sqlalchemy.orm import Session

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db import get_engine, get_session
from config import Config
from models import Job, Note, NoteRevision, Extraction, SourceAsset
from extractors.pipeline import run_pipeline
from validation.checker import check_extraction
from evaluation.strict_evaluator import evaluate_corpus_strictly
from evaluation.dataset import load_curated_corpus


WORKER_ID = f"worker_{uuid.uuid4().hex[:8]}"
MAX_JOB_ATTEMPTS = 3


def utc_now() -> datetime.datetime:
    """Return naive UTC datetime compatible with SQLAlchemy DateTime columns."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def claim_next_job(session: Session, worker_id: str = WORKER_ID) -> Optional[Job]:
    """Atomically claims the oldest queued or expired job using conditional update."""
    now = utc_now()
    lease_until = now + datetime.timedelta(seconds=60)

    # Expired jobs that have consumed all attempts are terminal; do not
    # leave them running forever or retry expensive inference indefinitely.
    exhausted = session.execute(
        update(Job).where(
            Job.status == "running",
            Job.lease_expiry < now,
            Job.attempt_number >= MAX_JOB_ATTEMPTS,
        ).values(
            status="failed",
            error_code="ATTEMPTS_EXHAUSTED",
            error_message="Retry budget exhausted",
            finished_at=now,
        ).execution_options(synchronize_session=False)
    )
    if exhausted.rowcount:
        session.commit()

    # Find candidate job
    candidate = (
        session.query(Job.id)
        .filter(
            or_(
                and_(Job.status == "queued", Job.attempt_number < MAX_JOB_ATTEMPTS),
                and_(Job.status == "running", Job.lease_expiry < now,
                     Job.attempt_number < MAX_JOB_ATTEMPTS),
            )
        )
        .order_by(Job.created_at.asc())
        .first()
    )

    if not candidate:
        return None

    candidate_id = candidate[0]

    # Atomic conditional update
    stmt = (
        update(Job)
        .where(
            Job.id == candidate_id,
            or_(
                and_(Job.status == "queued", Job.attempt_number < MAX_JOB_ATTEMPTS),
                and_(Job.status == "running", Job.lease_expiry < now,
                     Job.attempt_number < MAX_JOB_ATTEMPTS),
            ),
        )
        .values(
            status="running",
            lease_owner=worker_id,
            lease_expiry=lease_until,
            started_at=now,
            attempt_number=Job.attempt_number + 1,
        )
        .execution_options(synchronize_session=False)
    )
    res = session.execute(stmt)
    if res.rowcount != 1:
        session.rollback()
        return None

    session.commit()
    return session.query(Job).filter(Job.id == candidate_id).first()


def process_single_job(job: Job, session: Session) -> bool:
    """Processes a claimed job and records output."""
    claimed_lease_owner = job.lease_owner
    job_id = job.id
    try:
        payload = json.loads(job.payload_json or "{}")

        if job.kind == "extraction":
            note_id = job.note_id
            note = session.query(Note).filter(Note.id == note_id).first()
            if not note:
                raise ValueError(f"Note {note_id} not found")
            rev = (
                session.query(NoteRevision)
                .filter(NoteRevision.id == note.current_source_revision_id)
                .first()
            )
            if not rev or rev.id != job.source_revision_id:
                raise ValueError("JOB_STALE_SOURCE")
            expected_lock_version = note.lock_version
            expected_extraction_id = note.current_extraction_id
            raw_text = rev.raw_text
            extracted = run_pipeline(raw_text)

            # Store extraction
            ext = Extraction(
                note_id=note.id,
                workspace_id=note.workspace_id,
                source_revision_id=rev.id,
                source_text_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                extracted_json=json.dumps(extracted),
                pipeline_version=Config.PIPELINE_VERSION,
            )
            session.add(ext)
            session.flush()

            # Record operational issues for new extraction
            from models import OperationalIssue
            issues = check_extraction(rev, ext)
            for iss in issues:
                op_issue = OperationalIssue(
                    workspace_id=job.workspace_id,
                    note_id=note.id,
                    source_revision_id=rev.id,
                    extraction_id=ext.public_id,
                    issue_code=iss.issue_code,
                    severity=iss.severity,
                    category=iss.category,
                    item_id=iss.item_id,
                    field_path=iss.field_path,
                    evidence_span_json=json.dumps(iss.evidence_span) if iss.evidence_span else None,
                    safe_explanation=iss.safe_explanation,
                    check_policy_version=iss.check_policy_version,
                )
                session.add(op_issue)

            # Re-extraction, even for identical source text, invalidates a
            # previously completed review. Reject races with source edits.
            stmt = update(Note).where(
                Note.id == note.id,
                Note.workspace_id == job.workspace_id,
                Note.current_source_revision_id == job.source_revision_id,
                Note.current_extraction_id == expected_extraction_id,
                Note.lock_version == expected_lock_version,
            ).values(
                current_extraction_id=ext.public_id,
                review_head_event_id=None,
                status="needs_review",
                lock_version=Note.lock_version + 1,
            )
            if session.execute(stmt).rowcount != 1:
                raise ValueError("JOB_STALE_SOURCE")
            job.result_json = json.dumps({"extraction_id": ext.public_id, "fields_count": len(extracted.get("medications", []))})

        elif job.kind == "eval_run":
            # The run is deliberately restricted to the repository's pinned
            # synthetic evaluation data. Job JSON cannot select filesystem
            # paths or send private source data into benchmark artifacts.
            from pathlib import Path
            data_dir = Path(__file__).parent.parent / "data" / "eval"
            output_dir = str(Path(__file__).parent.parent / "artifacts" / "evaluation")
            pairs, dataset_manifest = load_curated_corpus(data_dir)
            bundle = evaluate_corpus_strictly(
                pairs, run_pipeline, output_dir=output_dir,
                dataset_manifest=dataset_manifest,
            )
            job.result_json = json.dumps({"run_id": bundle["run_id"], "overall": bundle["summary"]["overall"]})

        else:
            raise ValueError("INVALID_JOB_KIND")

        now_dt = utc_now()
        stmt = (
            update(Job)
            .where(
                Job.id == job.id,
                Job.lease_owner == claimed_lease_owner,
                Job.status == "running",
                Job.lease_expiry > now_dt,
            )
            .values(
                status="succeeded",
                result_json=job.result_json,
                finished_at=now_dt,
            )
            .execution_options(synchronize_session=False)
        )
        if session.execute(stmt).rowcount != 1:
            session.rollback()
            return False
        job.status = "succeeded"
        session.commit()
        return True

    except Exception as e:
        session.rollback()
        now_dt = utc_now()
        fail_stmt = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.lease_owner == claimed_lease_owner,
                Job.status == "running",
                Job.lease_expiry > now_dt,
            )
            .values(
                status="failed",
                error_code="PROCESSING_ERROR",
                error_message="Job failed; detailed exception not retained",
                finished_at=now_dt,
            )
            .execution_options(synchronize_session=False)
        )
        if session.execute(fail_stmt).rowcount == 1:
            session.commit()
        else:
            session.rollback()
        return False


def run_worker_loop(engine, poll_interval: float = 1.0, once: bool = False):
    """Main worker processing loop."""
    while True:
        with get_session(engine) as session:
            job = claim_next_job(session)
            if job:
                process_single_job(job, session)
        if once:
            break
        time.sleep(poll_interval)


if __name__ == "__main__":
    if Config.APP_MODE == "hosted_demo":
        raise RuntimeError("Background jobs are not enabled in hosted demo mode")
    engine = get_engine(Config.DATABASE_URL)
    run_worker_loop(engine)
