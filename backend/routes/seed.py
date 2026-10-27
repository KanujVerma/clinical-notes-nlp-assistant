import hashlib
import json
import os
import uuid
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models import Note, Extraction, NoteRevision, OperationalIssue
from validation.checker import check_extraction
from config import Config
from utils.session import require_session

bp = Blueprint("seed", __name__)
_SEED_SOURCES = ["dev", "showcase"]  # eval notes are held out


def seed_notes(db_session, session_id: str) -> dict:
    from extractors.pipeline import run_pipeline
    loaded = 0
    skipped = 0
    for source_dir in _SEED_SOURCES:
        notes_dir = os.path.join(Config.DATA_DIR, source_dir, "notes")
        if not os.path.isdir(notes_dir):
            continue
        for fname in sorted(os.listdir(notes_dir)):
            if not fname.endswith(".txt"):
                continue
            # Idempotency scoped to this session
            existing = db_session.execute(
                select(Note).where(Note.filename == fname,
                                   Note.session_id == session_id)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            fpath = os.path.join(notes_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
            extracted = run_pipeline(text)
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            note = Note(
                filename=fname,
                raw_text=text,
                source="demo",
                session_id=session_id,
                workspace_id=session_id,
                status="needs_review",
                lock_version=0,
            )
            db_session.add(note)
            db_session.flush()

            rev = NoteRevision(
                note_id=note.id,
                workspace_id=session_id,
                revision_number=1,
                raw_text=text,
                normalized_text=text,
                sha256=text_hash,
                creation_reason="demo_seed",
            )
            db_session.add(rev)
            db_session.flush()

            ext_id = str(uuid.uuid4())
            ext = Extraction(
                note_id=note.id,
                public_id=ext_id,
                workspace_id=session_id,
                source_revision_id=rev.id,
                source_text_hash=text_hash,
                extracted_json=json.dumps(extracted),
                pipeline_version=Config.PIPELINE_VERSION,
                schema_version="2.0.0",
                status="completed",
                check_policy_version="1.0.0",
            )
            db_session.add(ext)
            db_session.flush()

            note.current_source_revision_id = rev.id
            note.current_extraction_id = ext_id

            # Run deterministic check and persist issues
            issues = check_extraction(rev, ext)
            for iss in issues:
                db_iss = OperationalIssue(
                    workspace_id=session_id,
                    note_id=note.id,
                    source_revision_id=rev.id,
                    extraction_id=ext_id,
                    issue_code=iss.issue_code,
                    category=iss.category,
                    severity=iss.severity,
                    item_id=iss.item_id,
                    field_path=iss.field_path,
                    evidence_span_json=json.dumps(iss.evidence_span) if iss.evidence_span else None,
                    safe_explanation=iss.safe_explanation,
                    check_policy_version=iss.check_policy_version,
                    status="open",
                )
                db_session.add(db_iss)

            loaded += 1
    db_session.commit()
    return {"loaded": loaded, "skipped": skipped}


@bp.post("/api/seed-demo")
def seed_demo():
    sid = require_session()
    result = seed_notes(g.db, sid)
    return jsonify(result)
