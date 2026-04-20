import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.corrections import compute_correction_count
from utils.session import require_session


bp = Blueprint("validate", __name__)


@bp.post("/api/validate")
def validate():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    note_id = body.get("note_id")
    validated_json = body.get("validated_json")
    status = body.get("status")
    if not note_id or validated_json is None or not status:
        return jsonify({"error": "note_id, validated_json, and status are required", "code": "MISSING_FIELDS"}), 400

    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    extraction = g.db.execute(
        select(Extraction).where(Extraction.note_id == note_id)
    ).scalar_one_or_none()
    extracted = json.loads(extraction.extracted_json) if extraction else {}
    correction_count = compute_correction_count(extracted, validated_json)

    existing = g.db.execute(
        select(Validation).where(Validation.note_id == note_id)
    ).scalar_one_or_none()

    if existing:
        existing.validated_json = json.dumps(validated_json)
        existing.status = status
        existing.review_duration_ms = body.get("review_duration_ms")
        existing.correction_count = correction_count
    else:
        val = Validation(
            note_id=note_id,
            validated_json=json.dumps(validated_json),
            status=status,
            review_duration_ms=body.get("review_duration_ms"),
            correction_count=correction_count,
        )
        g.db.add(val)

    g.db.commit()

    next_pending = g.db.execute(
        select(Note.id)
        .join(Extraction, Extraction.note_id == Note.id)
        .outerjoin(Validation, Validation.note_id == Note.id)
        .where(Validation.id == None)  # noqa: E711
        .where(Note.id != note_id)
        .where(Note.session_id == sid)
        .order_by(Note.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    return jsonify({"message": "Validation saved", "correction_count": correction_count, "next_pending_id": next_pending})
