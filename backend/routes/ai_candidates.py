"""Local AI candidate job API.

All model inference occurs in the separate Python worker; a Flask request
cannot run Ollama or silently fall back to a non-image model for vision tasks.
"""
import hashlib
import json

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from config import Config
from models import InferenceRun, Job, Note, NoteRevision
from services.inference_pipeline import (
    InferenceBindingError, SUPPORTED_ADAPTERS, check_binding, model_for,
)
from utils.session import require_session

bp = Blueprint("ai_candidates", __name__)


def _create_hash(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@bp.post("/api/notes/<int:note_id>/ai-candidates")
def generate_ai_candidates(note_id: int):
    if Config.APP_MODE != "local":
        return jsonify({
            "error": "Live model inference is local-only",
            "code": "FEATURE_RESTRICTED",
        }), 403

    workspace_id = require_session()
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON object required", "code": "INVALID_INPUT"}), 422

    adapter = body.get("adapter", "text")
    source_revision_id = body.get("source_revision_id")
    extraction_id = body.get("extraction_id")
    page_number = body.get("page_number", 1)
    idempotency_key = body.get("idempotency_key")
    if (adapter not in SUPPORTED_ADAPTERS or
            not isinstance(source_revision_id, str) or
            not isinstance(extraction_id, str) or
            type(page_number) is not int or not (1 <= page_number <= 20)):
        return jsonify({
            "error": "A supported adapter and exact source/extraction IDs are required",
            "code": "INFERENCE_BINDING_REQUIRED",
        }), 422
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str) or
        not (1 <= len(idempotency_key) <= 128) or
        not idempotency_key.strip()
    ):
        return jsonify({"error": "Invalid idempotency key", "code": "INVALID_IDEMPOTENCY_KEY"}), 422

    model_name = model_for(adapter)
    if body.get("model") not in (None, model_name):
        return jsonify({"error": "Only configured local models may be selected",
                        "code": "UNSUPPORTED_MODEL"}), 422

    revision = g.db.query(NoteRevision).filter(
        NoteRevision.id == source_revision_id,
        NoteRevision.note_id == note_id,
        NoteRevision.workspace_id == workspace_id,
    ).first()
    if not revision:
        return jsonify({"error": "Source revision not found", "code": "NOT_FOUND"}), 404

    try:
        check_binding(
            g.db, workspace_id, note_id, source_revision_id,
            extraction_id, revision.sha256, adapter, page_number,
        )
    except InferenceBindingError as exc:
        status = 404 if exc.code == "NOTE_NOT_FOUND" else (
            422 if exc.code in ("IMAGE_SOURCE_REQUIRED", "INVALID_IMAGE_PAGE") else 409
        )
        return jsonify({"error": "Inference source validation failed", "code": exc.code}), status

    payload = {
        "adapter": adapter,
        "page_number": page_number,
        "source_revision_id": source_revision_id,
        "extraction_id": extraction_id,
        "source_hash": revision.sha256,
        "model": model_name,
    }
    request_hash = _create_hash({
        "workspace_id": workspace_id, "note_id": note_id, "payload": payload,
    })

    def replay_or_conflict(job):
        if job.request_hash != request_hash:
            return jsonify({"error": "Idempotency key used for another inference",
                            "code": "IDEMPOTENCY_CONFLICT"}), 409
        return jsonify({
            "job_id": job.id, "status": job.status, "is_replay": True,
            "adapter": adapter, "source_revision_id": source_revision_id,
        }), 200

    if idempotency_key:
        existing = g.db.query(Job).filter(
            Job.workspace_id == workspace_id,
            Job.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return replay_or_conflict(existing)

    # Keep optional model work bounded to a single queued/running task per
    # workspace. A single local worker further serializes model execution.
    active = g.db.query(Job.id).filter(
        Job.workspace_id == workspace_id,
        Job.kind == "ai_inference",
        Job.status.in_(("queued", "running")),
    ).first()
    if active:
        return jsonify({
            "error": "A local AI inference is already queued or running",
            "code": "INFERENCE_BUSY",
        }), 429

    job = Job(
        workspace_id=workspace_id,
        kind="ai_inference",
        note_id=note_id,
        source_revision_id=source_revision_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        payload_json=json.dumps(payload, sort_keys=True),
    )
    g.db.add(job)
    try:
        g.db.commit()
    except IntegrityError:
        g.db.rollback()
        if idempotency_key:
            existing = g.db.query(Job).filter(
                Job.workspace_id == workspace_id,
                Job.idempotency_key == idempotency_key,
            ).first()
            if existing:
                return replay_or_conflict(existing)
        raise

    return jsonify({
        "job_id": job.id,
        "status": "queued",
        "adapter": adapter,
        "source_revision_id": source_revision_id,
    }), 202


@bp.get("/api/notes/<int:note_id>/ai-candidates")
def get_ai_candidates(note_id: int):
    workspace_id = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id, Note.workspace_id == workspace_id,
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    records = g.db.query(InferenceRun).filter(
        InferenceRun.workspace_id == workspace_id,
        InferenceRun.note_id == note_id,
    ).order_by(InferenceRun.created_at.desc()).all()

    return jsonify([{
        "id": run.id,
        "source_revision_id": run.source_revision_id,
        "is_current": run.source_revision_id == note.current_source_revision_id,
        "task_type": run.task_type,
        "model_name": run.model_name,
        "model_digest": run.model_digest,
        "input_hash": run.input_hash,
        "duration_ms": run.duration_ms,
        "status": run.status,
        "candidates": json.loads(run.parsed_candidate_json or "{}"),
        "discrepancies": json.loads(run.discrepancies_json or "[]"),
        "error_code": run.error_code,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    } for run in records])
