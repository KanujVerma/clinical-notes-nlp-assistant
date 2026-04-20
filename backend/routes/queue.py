from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("queue", __name__)


@bp.get("/api/queue")
def get_queue():
    sid = require_session()
    stmt = (
        select(Note)
        .join(Extraction, Extraction.note_id == Note.id)
        .outerjoin(Validation, Validation.note_id == Note.id)
        .where(Validation.id == None)  # noqa: E711
        .where(Note.session_id == sid)
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
