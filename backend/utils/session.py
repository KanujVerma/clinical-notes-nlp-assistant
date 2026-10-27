from flask import g, jsonify, make_response, abort, request


def get_workspace_or_session_id() -> str:
    """Returns workspace_id or session_id from headers or g, or empty string."""
    wid = request.headers.get("X-Workspace-ID") or request.headers.get("X-Session-ID") or g.get("session_id", "")
    return wid.strip() if wid else ""


def require_session() -> str:
    """Return workspace/session_id from g, or abort with 400 MISSING_SESSION_ID."""
    sid = get_workspace_or_session_id()
    if not sid:
        abort(make_response(
            jsonify({"error": "X-Workspace-ID or X-Session-ID header is required", "code": "MISSING_SESSION_ID"}),
            400,
        ))
    return sid
