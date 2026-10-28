import os
import json
import uuid
import datetime
import hashlib
import secrets
from flask import Blueprint, g, jsonify, request
from models import Workspace
from config import Config
from services.ollama_service import is_ollama_available

bp = Blueprint("workspaces", __name__)

MAX_HOSTED_WORKSPACES = 50
HOSTED_WORKSPACE_HOURS = 2
LOCAL_WORKSPACE_HOURS = 24


def purge_expired_workspaces(db, now: datetime.datetime):
    """Transactionally cleans up expired workspaces and all their associated records."""
    from models import (
        Note, NoteRevision, Extraction, OperationalIssue,
        ReviewEvent, InferenceRun, SourceAsset, Job, Validation
    )
    expired_ids = [w[0] for w in db.query(Workspace.id).filter(Workspace.expires_at < now).all()]
    if not expired_ids:
        return

    # Find all note IDs in expired workspaces
    expired_note_ids = [n[0] for n in db.query(Note.id).filter(Note.workspace_id.in_(expired_ids)).all()]
    if expired_note_ids:
        db.query(Validation).filter(Validation.note_id.in_(expired_note_ids)).delete(synchronize_session=False)

    db.query(ReviewEvent).filter(ReviewEvent.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(OperationalIssue).filter(OperationalIssue.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(InferenceRun).filter(InferenceRun.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(Extraction).filter(Extraction.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(NoteRevision).filter(NoteRevision.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(Job).filter(Job.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(Note).filter(Note.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(SourceAsset).filter(SourceAsset.workspace_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(Workspace).filter(Workspace.id.in_(expired_ids)).delete(synchronize_session=False)
    db.commit()


@bp.post("/api/workspaces")
def create_workspace():
    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    if is_hosted:
        # 1. Purge expired workspaces and data to maintain bounded sandbox storage
        purge_expired_workspaces(g.db, now)

        # 2. Enforce active workspace concurrency quota
        active_count = g.db.query(Workspace).filter(Workspace.mode == "hosted_demo").count()
        if active_count >= MAX_HOSTED_WORKSPACES:
            return jsonify({
                "error": "Public sandbox workspace quota reached. Please try again later.",
                "code": "WORKSPACE_QUOTA_EXCEEDED",
            }), 429

    ws_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    mode = "hosted_demo" if is_hosted else "normal"
    hours = HOSTED_WORKSPACE_HOURS if is_hosted else LOCAL_WORKSPACE_HOURS

    ws = Workspace(
        id=ws_id,
        capability_token_hash=token_hash,
        mode=mode,
        expires_at=now + datetime.timedelta(hours=hours),
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


@bp.get("/api/scenarios")
def list_scenarios():
    """Returns curated synthetic scenarios for precomputed sandbox inspection."""
    precomp_path = os.path.join(Config.DATA_DIR, "precomputed_scenarios.json")
    scenarios = []
    if os.path.isfile(precomp_path):
        try:
            with open(precomp_path, "r", encoding="utf-8") as f:
                items = json.load(f)
                for it in items:
                    scenarios.append({
                        "filename": it.get("filename"),
                        "title": it.get("title", it.get("filename", "")),
                        "sha256": it.get("sha256"),
                        "has_issues": len(it.get("issues", [])) > 0,
                        "issues_count": len(it.get("issues", [])),
                        "snippet": (it.get("raw_text", "")[:150] + "...") if len(it.get("raw_text", "")) > 150 else it.get("raw_text", ""),
                    })
        except Exception:
            pass
    return jsonify({"scenarios": scenarios, "count": len(scenarios)})


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
