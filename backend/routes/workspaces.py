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

    return jsonify({
        "workspace_id": ws.id,
        "token": token,
        "mode": ws.mode,
        "expires_at": ws.expires_at.isoformat() if ws.expires_at else None,
    }), 201


@bp.get("/api/capabilities")
def get_capabilities():
    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    return jsonify({
        "mode": "hosted_demo" if is_hosted else "local",
        "ocr_available": True,
        "local_ai_available": is_ollama_available(),
        "paid_ai_available": bool(getattr(Config, "ANTHROPIC_API_KEY", None)),
        "hosted_sandbox": is_hosted,
        "version": getattr(Config, "PIPELINE_VERSION", "2.0.0"),
    })
