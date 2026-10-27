import json
import hashlib
from flask import Blueprint, request, jsonify, g
from models import Note, Extraction, NoteRevision, OperationalIssue, ReviewEvent
from extractors.pipeline import run_pipeline
from validation.checker import check_extraction
from config import Config
from utils.session import require_session

bp = Blueprint("notes", __name__)


@bp.post("/api/notes")
def create_note():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400

    extracted = run_pipeline(text)
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    note = Note(
        raw_text=text,
        source=body.get("source", "paste"),
        session_id=sid,
        workspace_id=sid,
        lock_version=0,
        status="needs_review",
    )
    g.db.add(note)
    g.db.flush()

    rev = NoteRevision(
        note_id=note.id,
        workspace_id=sid,
        revision_number=1,
        raw_text=text,
        normalized_text=text,
        sha256=text_hash,
        creation_reason="acquisition",
    )
    g.db.add(rev)
    g.db.flush()

    note.current_source_revision_id = rev.id

    ext = Extraction(
        note_id=note.id,
        workspace_id=sid,
        source_revision_id=rev.id,
        source_text_hash=text_hash,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(ext)
    g.db.flush()

    note.current_extraction_id = ext.public_id

    # Run independent validation checker
    issues = check_extraction(rev, ext)
    for iss in issues:
        op_iss = OperationalIssue(
            workspace_id=sid,
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
        g.db.add(op_iss)

    g.db.commit()

    return jsonify({
        "note_id": note.id,
        "revision_id": rev.id,
        "extraction_id": ext.public_id,
        "extracted_json": extracted,
        "status": note.status,
        "lock_version": note.lock_version,
        "issues_count": len(issues),
    }), 201


@bp.get("/api/notes/<int:note_id>")
def get_note(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid and note.workspace_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    # Current extraction
    ext = None
    if note.current_extraction_id:
        ext = g.db.query(Extraction).filter(Extraction.public_id == note.current_extraction_id).first()
    if not ext:
        ext = (
            g.db.query(Extraction)
            .filter(Extraction.note_id == note.id)
            .order_by(Extraction.extracted_at.desc())
            .first()
        )

    extracted_data = json.loads(ext.extracted_json) if (ext and ext.extracted_json) else {}

    # Open issues for current revision
    issues = (
        g.db.query(OperationalIssue)
        .filter(
            OperationalIssue.note_id == note.id,
            OperationalIssue.source_revision_id == note.current_source_revision_id,
        )
        .all()
    )

    review_head = None
    if note.review_head_event_id:
        rev_event = g.db.query(ReviewEvent).filter(ReviewEvent.id == note.review_head_event_id).first()
        if rev_event:
            review_head = {
                "event_id": rev_event.id,
                "derived_outcome": rev_event.derived_outcome,
                "event_kind": rev_event.event_kind,
                "reviewed_snapshot": json.loads(rev_event.reviewed_snapshot_json or "{}"),
            }

    return jsonify({
        "id": note.id,
        "filename": note.filename,
        "raw_text": note.raw_text,
        "source": note.source,
        "ocr_confidence": note.ocr_confidence,
        "status": note.status,
        "lock_version": note.lock_version,
        "current_source_revision_id": note.current_source_revision_id,
        "current_extraction_id": ext.public_id if ext else None,
        "review_head": review_head,
        "extracted_json": extracted_data,
        "issues": [
            {
                "id": i.id,
                "issue_code": i.issue_code,
                "severity": i.severity,
                "category": i.category,
                "safe_explanation": i.safe_explanation,
                "status": i.status,
            }
            for i in issues
        ],
    })


@bp.put("/api/notes/<int:note_id>/text")
def update_note_text(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid and note.workspace_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required", "code": "TEXT_REQUIRED"}), 400

    note.raw_text = text
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Determine next revision number
    latest_rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.note_id == note_id)
        .order_by(NoteRevision.revision_number.desc())
        .first()
    )
    next_rev_num = (latest_rev.revision_number + 1) if latest_rev else 1

    rev = NoteRevision(
        note_id=note.id,
        workspace_id=sid,
        revision_number=next_rev_num,
        parent_revision_id=latest_rev.id if latest_rev else None,
        raw_text=text,
        normalized_text=text,
        sha256=text_hash,
        creation_reason="human_edit",
    )
    g.db.add(rev)
    g.db.flush()

    note.current_source_revision_id = rev.id

    # For legacy backwards compatibility: delete old extractions if requested by legacy test
    g.db.query(Extraction).filter_by(note_id=note_id).delete()

    # Re-run pipeline and create new extraction
    extracted = run_pipeline(text)
    extraction = Extraction(
        note_id=note_id,
        workspace_id=sid,
        source_revision_id=rev.id,
        source_text_hash=text_hash,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.flush()

    note.current_extraction_id = extraction.public_id
    note.review_head_event_id = None
    note.lock_version += 1
    note.status = "needs_review"
    g.db.commit()

    return jsonify({
        "note_id": note_id,
        "revision_id": rev.id,
        "extraction_id": extraction.public_id,
        "extracted_json": extracted,
        "status": note.status,
    }), 200
