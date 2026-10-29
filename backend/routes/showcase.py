"""Public read-only synthetic evaluation showcase (no LLM calls or writes)."""
from flask import Blueprint, jsonify
from services.showcase_evidence import ShowcaseEvidenceError, public_showcase

bp = Blueprint("showcase", __name__)


@bp.get("/api/showcase-evidence")
def get_public_showcase_evidence():
    try:
        result = public_showcase()
    except ShowcaseEvidenceError:
        return jsonify({
            "status": "unavailable",
            "error": "Published synthetic evidence could not be verified",
            "code": "SHOWCASE_EVIDENCE_UNAVAILABLE",
        }), 503

    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
