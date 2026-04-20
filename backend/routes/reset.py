from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("reset", __name__)


@bp.delete("/api/reset")
def reset_workspace():
    sid = require_session()

    note_ids = list(g.db.execute(
        select(Note.id).where(Note.session_id == sid)
    ).scalars())

    if not note_ids:
        return jsonify({"deleted_notes": 0, "deleted_extractions": 0, "deleted_validations": 0})

    deleted_extractions = g.db.query(Extraction).filter(
        Extraction.note_id.in_(note_ids)
    ).count()
    deleted_validations = g.db.query(Validation).filter(
        Validation.note_id.in_(note_ids)
    ).count()

    g.db.query(Validation).filter(Validation.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Extraction).filter(Extraction.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Note).filter(Note.session_id == sid).delete(synchronize_session=False)
    g.db.commit()

    return jsonify({
        "deleted_notes": len(note_ids),
        "deleted_extractions": deleted_extractions,
        "deleted_validations": deleted_validations,
    })
