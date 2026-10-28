from flask import Blueprint, jsonify, g
from sqlalchemy import or_
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from models.note_revision import NoteRevision
from models.review_event import ReviewEvent
from models.operational_issue import OperationalIssue, IssueEvent
from models.inference_run import InferenceRun
from utils.session import require_session

bp = Blueprint("reset", __name__)


@bp.delete("/api/reset")
def reset_workspace():
    sid = require_session()

    notes = g.db.query(Note).filter(or_(Note.session_id == sid, Note.workspace_id == sid)).all()
    note_ids = [n.id for n in notes]

    if not note_ids:
        return jsonify({"deleted_notes": 0, "deleted_extractions": 0, "deleted_validations": 0})

    deleted_extractions = g.db.query(Extraction).filter(Extraction.note_id.in_(note_ids)).count()
    deleted_validations = g.db.query(Validation).filter(Validation.note_id.in_(note_ids)).count()

    issues = g.db.query(OperationalIssue).filter(OperationalIssue.note_id.in_(note_ids)).all()
    issue_ids = [i.id for i in issues]
    if issue_ids:
        g.db.query(IssueEvent).filter(IssueEvent.issue_id.in_(issue_ids)).delete(synchronize_session=False)
        g.db.query(OperationalIssue).filter(OperationalIssue.id.in_(issue_ids)).delete(synchronize_session=False)

    g.db.query(ReviewEvent).filter(ReviewEvent.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(InferenceRun).filter(InferenceRun.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Validation).filter(Validation.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Extraction).filter(Extraction.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(NoteRevision).filter(NoteRevision.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Note).filter(or_(Note.session_id == sid, Note.workspace_id == sid)).delete(synchronize_session=False)
    g.db.commit()

    return jsonify({
        "deleted_notes": len(note_ids),
        "deleted_extractions": deleted_extractions,
        "deleted_validations": deleted_validations,
    })
