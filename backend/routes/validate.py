"""Legacy /api/validate adapter.

The original note-ID-only API overwrote a mutable Validation row and could
'complete' a stale source. Only requests with the full version binding are
routed to the authoritative append-only review service.
"""
from flask import Blueprint, request, jsonify
from routes.reviews import submit_review

bp = Blueprint("validate", __name__)


@bp.post("/api/validate")
def validate():
    body = request.get_json(silent=True)
    required = {
        "note_id",
        "source_revision_id",
        "extraction_id",
        "source_hash",
        "expected_lock_version",
        "event_kind",
        "item_decisions",
        "category_acknowledgments",
    }
    if (
        not isinstance(body, dict)
        or not required.issubset(body.keys())
        or "validated_json" in body
        or "status" in body
    ):
        return jsonify({
            "error": "The legacy validation payload is no longer supported; use the version-bound reviews API",
            "code": "REVIEW_BINDING_REQUIRED",
        }), 422

    # The modern route validates schema, scope, current source/extraction,
    # idempotency and optimistic concurrency in the same review service.
    return submit_review(str(body["extraction_id"]))
