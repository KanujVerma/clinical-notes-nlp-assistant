"""Pending queue based on the *current* immutable source/extraction/review binding.

Legacy validation rows and historical ReviewEvents never remove a current note
from the queue. A draft is pending; only a matching completed head closes it.
"""
from flask import Blueprint, jsonify
from flask import g
from sqlalchemy import or_, select
from models import Note, Extraction, ReviewEvent
from utils.session import require_session

bp = Blueprint("queue", __name__)


@bp.get("/api/queue")
def get_queue():
    sid = require_session()

    current_completion = (
        select(ReviewEvent.id)
        .where(
            ReviewEvent.id == Note.review_head_event_id,
            ReviewEvent.note_id == Note.id,
            ReviewEvent.source_revision_id == Note.current_source_revision_id,
            ReviewEvent.extraction_id == Note.current_extraction_id,
            ReviewEvent.workspace_id == Note.workspace_id,
            ReviewEvent.event_kind == "review_completed",
            ReviewEvent.derived_outcome.in_(("reviewed_unchanged", "reviewed_corrected")),
        )
        .exists()
    )
    # Keep compatible read access for unreviewed legacy notes that have an
    # extraction but have not yet received a public current_extraction_id.
    has_extraction = (
        select(Extraction.id).where(Extraction.note_id == Note.id).exists()
    )

    notes = g.db.execute(
        select(Note)
        .where(
            or_(Note.session_id == sid, Note.workspace_id == sid),
            has_extraction,
            ~current_completion,
        )
        .order_by(Note.created_at.asc(), Note.id.asc())
    ).scalars().all()

    return jsonify({
        "notes": [
            {
                "id": note.id,
                "filename": note.filename,
                "source": note.source,
                "status": note.status,
                "created_at": note.created_at.isoformat() if note.created_at else None,
            }
            for note in notes
        ],
        "count": len(notes),
    })
