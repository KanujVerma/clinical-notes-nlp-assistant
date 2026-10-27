from flask import Blueprint, jsonify, g
from sqlalchemy import select, or_
from models.note import Note
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("queue", __name__)


@bp.get("/api/queue")
def get_queue():
    sid = require_session()
    stmt = (
        select(Note)
        .outerjoin(Validation, Validation.note_id == Note.id)
        .where(
            or_(Note.session_id == sid, Note.workspace_id == sid),
            Validation.id.is_(None),
            Note.review_head_event_id.is_(None),
            or_(Note.status == "needs_review", Note.status == "pending", Note.status.is_(None)),
        )
        .distinct()
        .order_by(Note.created_at.asc())
    )
    notes = g.db.execute(stmt).scalars().all()

    result = [
        {
            "id": note.id,
            "filename": note.filename,
            "source": note.source,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }
        for note in notes
    ]

    return jsonify({"notes": result, "count": len(result)})
