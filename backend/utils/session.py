from flask import g, jsonify, make_response, abort


def require_session() -> str:
    """Return session_id from g, or abort with 400 MISSING_SESSION_ID."""
    sid = g.get("session_id", "")
    if not sid:
        abort(make_response(
            jsonify({"error": "X-Session-ID header is required", "code": "MISSING_SESSION_ID"}),
            400,
        ))
    return sid
