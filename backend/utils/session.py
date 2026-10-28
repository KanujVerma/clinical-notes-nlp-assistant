import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from flask import g, jsonify, make_response, abort, request
from config import Config
from models import Workspace


def hash_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def get_workspace_or_session_id() -> str:
    """Returns workspace_id or session_id from headers or g, or empty string."""
    wid = request.headers.get("X-Workspace-ID") or request.headers.get("X-Session-ID") or g.get("session_id", "")
    return wid.strip() if wid else ""


def get_capability_token() -> str:
    token = request.headers.get("X-Workspace-Token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    return token.strip() if token else ""


def require_session() -> str:
    """Return workspace/session_id from g, or abort with 400/401/403."""
    wid = get_workspace_or_session_id()
    if not wid:
        abort(make_response(
            jsonify({"error": "X-Workspace-ID or X-Session-ID header is required", "code": "MISSING_SESSION_ID"}),
            400,
        ))

    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    token = get_capability_token()

    ws = None
    if hasattr(g, "db") and g.db:
        ws = g.db.query(Workspace).filter(Workspace.id == wid).first()

    if ws:
        if is_hosted and ws.mode != "hosted_demo":
            abort(make_response(
                jsonify({"error": "Workspace is not a hosted synthetic sandbox", "code": "INVALID_WORKSPACE_MODE"}),
                403,
            ))
        # Check workspace state
        if ws.state != "active":
            abort(make_response(
                jsonify({"error": f"Workspace {wid} is {ws.state}", "code": "WORKSPACE_INACTIVE"}),
                403,
            ))
        # Check expiration
        expiry = ws.expires_at
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            ws.state = "expired"
            g.db.commit()
            abort(make_response(
                jsonify({"error": "Workspace capability token expired", "code": "TOKEN_EXPIRED"}),
                401,
            ))

        # Check capability token if workspace has capability_token_hash
        if ws.capability_token_hash:
            if not token:
                abort(make_response(
                    jsonify({"error": "Capability token required for this workspace", "code": "TOKEN_REQUIRED"}),
                    401,
                ))
            t_hash = hash_token(token)
            legacy_uuid5 = uuid.uuid5(uuid.NAMESPACE_DNS, token).hex
            if not (
                hmac.compare_digest(t_hash, ws.capability_token_hash)
                or hmac.compare_digest(legacy_uuid5, ws.capability_token_hash)
            ):
                abort(make_response(
                    jsonify({"error": "Invalid capability token", "code": "INVALID_TOKEN"}),
                    403,
                ))
    else:
        # Workspace not found in DB
        if is_hosted:
            abort(make_response(
                jsonify({"error": "Valid workspace and capability token required in hosted mode", "code": "WORKSPACE_NOT_FOUND"}),
                401,
            ))
        # Documented local migration path: in local mode, legacy ad-hoc session IDs are permitted

    return wid
