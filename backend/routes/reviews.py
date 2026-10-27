import json
from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from models import Note, ReviewEvent
from schemas.review import ReviewMutationRequest
from services.review_service import (
    process_review_mutation,
    StaleReviewError,
    IdempotencyConflictError,
    IncompleteReviewError,
    BlockedReviewError,
    InvalidReviewPayloadError,
)
from utils.session import require_session

bp = Blueprint("reviews", __name__)


@bp.post("/api/extractions/<string:ext_id>/reviews")
def submit_review(ext_id: str):
    sid = require_session()
    raw_body = request.get_json(silent=True) or {}

    # Extract Idempotency-Key header if not in body
    idemp_header = request.headers.get("Idempotency-Key")
    if idemp_header and not raw_body.get("idempotency_key"):
        raw_body["idempotency_key"] = idemp_header.strip()

    # Ensure extraction_id matches route
    raw_body["extraction_id"] = ext_id

    try:
        req = ReviewMutationRequest.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({
            "error": "Invalid review mutation request schema",
            "code": "SCHEMA_VALIDATION_ERROR",
            "details": e.errors(),
        }), 422

    try:
        review_event, is_replay = process_review_mutation(
            session=g.db,
            workspace_id=sid,
            req=req,
            raw_request_dict=raw_body,
        )
    except StaleReviewError as e:
        return jsonify({"error": str(e), "code": "STALE_REVIEW"}), 409
    except IdempotencyConflictError as e:
        return jsonify({"error": str(e), "code": "IDEMPOTENCY_CONFLICT"}), 409
    except IncompleteReviewError as e:
        return jsonify({"error": str(e), "code": "INCOMPLETE_REVIEW"}), 422
    except BlockedReviewError as e:
        return jsonify({"error": str(e), "code": "BLOCKED_REVIEW"}), 422
    except InvalidReviewPayloadError as e:
        return jsonify({"error": str(e), "code": "INVALID_REVIEW_PAYLOAD"}), 422
    except ValueError as e:
        return jsonify({"error": str(e), "code": "INVALID_MUTATION"}), 400

    status_code = 200 if is_replay else 201
    return jsonify({
        "event_id": review_event.id,
        "note_id": review_event.note_id,
        "derived_outcome": review_event.derived_outcome,
        "event_kind": review_event.event_kind,
        "is_replay": is_replay,
        "created_at": review_event.created_at.isoformat() if review_event.created_at else None,
    }), status_code


@bp.get("/api/notes/<int:note_id>/review-events")
def get_note_review_events(note_id: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    events = (
        g.db.query(ReviewEvent)
        .filter(ReviewEvent.note_id == note_id)
        .order_by(ReviewEvent.created_at.asc())
        .all()
    )

    return jsonify([
        {
            "id": ev.id,
            "parent_event_id": ev.parent_event_id,
            "event_kind": ev.event_kind,
            "derived_outcome": ev.derived_outcome,
            "source_revision_id": ev.source_revision_id,
            "extraction_id": ev.extraction_id,
            "source_hash": ev.source_hash,
            "review_duration_ms": ev.review_duration_ms,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in events
    ])
