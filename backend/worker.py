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


WORKER_ID = f"worker_{uuid.uuid4().hex[:8]}"


def claim_next_job(session: Session, worker_id: str = WORKER_ID) -> Optional[Job]:
    """Atomically claims the oldest queued or expired job using conditional update."""
    now = datetime.datetime.now(datetime.timezone.utc)
    lease_until = now + datetime.timedelta(seconds=60)

    # Find candidate job
    candidate = (
        session.query(Job.id)
        .filter(
            or_(
                Job.status == "queued",
                and_(Job.status == "running", Job.lease_expiry < now),
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
                Job.status == "queued",
                and_(Job.status == "running", Job.lease_expiry < now),
            ),
        )
        .values(
            status="running",
            lease_owner=worker_id,
            lease_expiry=lease_until,
            started_at=now,
            attempt_number=Job.attempt_number + 1,
        )
    )
    res = session.execute(stmt)
    if res.rowcount != 1:
        session.rollback()
        return None

    session.commit()
    return session.query(Job).filter(Job.id == candidate_id).first()


def process_single_job(job: Job, session: Session) -> bool:
    """Processes a claimed job and records output."""
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
            job.status = "succeeded"

        elif job.kind == "eval_run":
            # The run is deliberately restricted to the repository's pinned
            # synthetic evaluation data. Job JSON cannot select filesystem
            # paths or send private source data into benchmark artifacts.
            from pathlib import Path
            n_dir = Path(__file__).parent.parent / "data" / "eval" / "notes"
            l_dir = Path(__file__).parent.parent / "data" / "eval" / "labels"
            output_dir = str(Path(__file__).parent.parent / "artifacts" / "evaluation")

            pairs = []
            for n_path in sorted(n_dir.glob("*.txt")):
                l_path = l_dir / (n_path.stem + ".json")
                if l_path.exists():
                    with open(n_path) as f:
                        txt = f.read()
                    with open(l_path) as f:
                        lbl = json.load(f)
                    pairs.append((n_path.stem, txt, lbl))

            bundle = evaluate_corpus_strictly(pairs, run_pipeline, output_dir=output_dir)
            job.result_json = json.dumps({"run_id": bundle["run_id"], "overall": bundle["summary"]["overall"]})
            job.status = "succeeded"

        else:
            raise ValueError("INVALID_JOB_KIND")

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        stmt = update(Job).where(
            Job.id == job.id,
            Job.lease_owner == job.lease_owner,
            Job.status == "running",
        ).values(
            status="succeeded",
            result_json=job.result_json,
            finished_at=now_dt,
        )
        if session.execute(stmt).rowcount != 1:
            session.rollback()
            return False
        session.commit()
        return True

    except Exception as e:
        session.rollback()
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        target = session.query(Job).filter(Job.id == job.id).first()
        if target and target.lease_owner == job.lease_owner and target.status == "running":
            target.status = "failed"
            target.error_code = "PROCESSING_ERROR"
            target.error_message = str(e)
            target.finished_at = now_dt
            session.commit()
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
    engine = get_engine(Config.DATABASE_URL)
    run_worker_loop(engine)
