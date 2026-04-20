from flask import Blueprint, request, jsonify
from utils.session import require_session
from utils import ai_provider
from utils.rate_limit import check_rate_limit
from utils.ai_provider import AIDisabled, AIError

bp = Blueprint("explain", __name__)

VALID_KINDS = {"medication", "abbreviation"}
MAX_VALUE_LEN = 80
MAX_CONTEXT_VALUE_LEN = 40
MODEL_USED = "claude-haiku-4-5-20251001"


@bp.post("/api/explain")
def explain():
    session_id = require_session()

    body = request.get_json(silent=True) or {}

    # Validate kind
    kind = body.get("kind")
    if kind not in VALID_KINDS:
        return jsonify({"error": "kind must be 'medication' or 'abbreviation'", "code": "INVALID_INPUT"}), 400

    # Validate value
    value = body.get("value")
    if not isinstance(value, str):
        return jsonify({"error": "value must be a string", "code": "INVALID_INPUT"}), 400
    if len(value) > MAX_VALUE_LEN:
        return jsonify({"error": f"value must be {MAX_VALUE_LEN} chars or fewer", "code": "INVALID_INPUT"}), 400
    if "\n" in value:
        return jsonify({"error": "value must not contain newlines", "code": "INVALID_INPUT"}), 400

    # Validate context (optional)
    context = body.get("context", {})
    if not isinstance(context, dict):
        return jsonify({"error": "context must be an object", "code": "INVALID_INPUT"}), 400
    if context:
        for k, v in context.items():
            if not isinstance(v, str):
                return jsonify({"error": "context values must be strings", "code": "INVALID_INPUT"}), 400
            if len(v) > MAX_CONTEXT_VALUE_LEN:
                return jsonify(
                    {"error": f"context values must be {MAX_CONTEXT_VALUE_LEN} chars or fewer", "code": "INVALID_INPUT"}
                ), 400

    # Rate limit check
    allowed, retry_after = check_rate_limit(session_id)
    if not allowed:
        return jsonify({"error": "Rate limit exceeded", "code": "RATE_LIMITED", "retry_after": retry_after}), 429

    # Call AI provider
    try:
        explanation = ai_provider.explain(kind, value, context or {})
    except AIDisabled:
        return jsonify({"error": "AI is not configured", "code": "AI_DISABLED"}), 503
    except AIError:
        return jsonify({"error": "AI service error", "code": "AI_ERROR"}), 502

    return jsonify({"explanation": explanation, "modelUsed": MODEL_USED}), 200


@bp.get("/api/explain/status")
def explain_status():
    available = ai_provider.is_available()
    return jsonify({"available": available}), 200
