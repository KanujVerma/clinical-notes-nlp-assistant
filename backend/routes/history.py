import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select, desc
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
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
        .where(Note.session_id == sid)
        .order_by(desc(Note.created_at))
        .limit(per_page)
        .offset(offset)
    ).scalars().all()

    result = []
    for note in notes:
        val = g.db.execute(
            select(Validation).where(Validation.note_id == note.id)
        ).scalar_one_or_none()
        result.append({
            "id": note.id,
            "filename": note.filename,
            "source": note.source,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "status": val.status if val else "pending",
            "correction_count": val.correction_count if val else 0,
        })

    return jsonify({"notes": result, "page": page, "per_page": per_page})


@bp.get("/api/history/<int:note_id>")
def get_history_detail(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    extraction = g.db.execute(
        select(Extraction).where(Extraction.note_id == note_id)
    ).scalar_one_or_none()

    validation = g.db.execute(
        select(Validation).where(Validation.note_id == note_id)
    ).scalar_one_or_none()

    return jsonify({
        "id": note.id,
        "filename": note.filename,
        "raw_text": note.raw_text,
        "source": note.source,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "extracted_json": json.loads(extraction.extracted_json) if extraction else None,
        "pipeline_version": extraction.pipeline_version if extraction else None,
        "validation": {
            "status": validation.status,
            "validated_json": json.loads(validation.validated_json),
            "correction_count": validation.correction_count,
            "review_duration_ms": validation.review_duration_ms,
        } if validation else None,
    })
