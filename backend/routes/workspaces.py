import uuid
import datetime
import hashlib
import secrets
from flask import Blueprint, g, jsonify, request
from models import Workspace
from config import Config
from services.ollama_service import is_ollama_available

bp = Blueprint("workspaces", __name__)


@bp.post("/api/workspaces")
def create_workspace():
    ws_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    mode = "hosted_demo" if getattr(Config, "APP_MODE", "local") == "hosted_demo" else "normal"

    ws = Workspace(
        id=ws_id,
        capability_token_hash=token_hash,
        mode=mode,
        expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24),
    )
    g.db.add(ws)
    g.db.commit()

    expires_dt = ws.expires_at
    if expires_dt and expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=datetime.timezone.utc)

    return jsonify({
        "workspace_id": ws.id,
        "token": token,
        "mode": ws.mode,
        "expires_at": expires_dt.isoformat() if expires_dt else None,
    }), 201


@bp.get("/api/capabilities")
def get_capabilities():
    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    return jsonify({
        "mode": "hosted_demo" if is_hosted else "local",
        "ocr_available": not is_hosted,
        "local_ai_available": (not is_hosted) and is_ollama_available(),
        "paid_ai_available": (not is_hosted)
            and Config.ENABLE_EXTERNAL_EXPLAINER
            and bool(getattr(Config, "ANTHROPIC_API_KEY", None)),
        "source_upload_allowed": not is_hosted,
        "review_mode": "accept_remove_only" if is_hosted else "full_synthetic",
        "hosted_sandbox": is_hosted,
        "version": getattr(Config, "PIPELINE_VERSION", "2.0.0"),
    })
