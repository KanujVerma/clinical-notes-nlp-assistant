import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select, desc, or_
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from models.review_event import ReviewEvent
from utils.session import require_session

bp = Blueprint("history", __name__)


@bp.get("/api/history")
def list_history():
    sid = require_session()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page

    notes = g.db.execute(
        select(Note)
        .where(or_(Note.session_id == sid, Note.workspace_id == sid))
        .order_by(desc(Note.created_at))
        .limit(per_page)
        .offset(offset)
    ).scalars().all()

    result = []
    for note in notes:
        val = (
            g.db.query(Validation)
            .filter(Validation.note_id == note.id)
            .first()
        )
        # A legacy Validation row is not a completion for the current source.
        # Current status is maintained by the version-bound review service.
        result.append({
            "id": note.id,
            "filename": note.filename,
            "source": note.source,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "status": note.status or ("legacy_unverified" if val else "needs_review"),
            "correction_count": None if val else 0,
        })

    return jsonify({"notes": result, "page": page, "per_page": per_page})


@bp.get("/api/history/<int:note_id>")
def get_history_detail(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid and note.workspace_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    extraction = None
    if note.current_extraction_id:
        extraction = (
            g.db.query(Extraction)
            .filter(
                Extraction.note_id == note_id,
                or_(
                    Extraction.public_id == note.current_extraction_id,
                    Extraction.id == int(note.current_extraction_id) if note.current_extraction_id.isdigit() else False,
                ),
            )
            .first()
        )
    if not extraction:
        extraction = (
            g.db.query(Extraction)
            .filter(Extraction.note_id == note_id)
            .order_by(desc(Extraction.id))
            .first()
        )

    current_review = None
    if note.review_head_event_id:
        event = (
            g.db.query(ReviewEvent)
            .filter(
                ReviewEvent.id == note.review_head_event_id,
                ReviewEvent.workspace_id == sid,
                ReviewEvent.note_id == note_id,
                ReviewEvent.source_revision_id == note.current_source_revision_id,
                ReviewEvent.extraction_id == note.current_extraction_id,
            )
            .first()
        )
        if event:
            decisions = json.loads(event.item_decisions_json or "{}")
            current_review = {
                "status": event.derived_outcome,
                "validated_json": json.loads(event.reviewed_snapshot_json or "{}"),
                "correction_count": sum(
                    1
                    for action in decisions.values()
                    if (action.get("decision") if isinstance(action, dict) else action)
                    in ("edit", "remove", "add")
                ),
                "review_duration_ms": event.review_duration_ms,
                "review_event_id": event.id,
                "source_revision_id": event.source_revision_id,
                "extraction_id": event.extraction_id,
            }
    # Legacy note-ID-only validations remain historical and unverified; do
    # not pass them to the editor as if they were a current completed review.

    return jsonify({
        "id": note.id,
        "filename": note.filename,
        "raw_text": note.raw_text,
        "source": note.source,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "extracted_json": json.loads(extraction.extracted_json) if extraction else None,
        "pipeline_version": extraction.pipeline_version if extraction else None,
        "validation": current_review,
    })
