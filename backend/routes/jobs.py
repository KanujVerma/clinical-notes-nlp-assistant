import json
import hashlib
from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from models import Job, Note
from utils.session import require_session
from config import Config

bp = Blueprint("jobs", __name__)


@bp.get("/api/jobs/<string:job_id>")
def get_job_status(job_id: str):
    sid = require_session()
    job = g.db.query(Job).filter(
        Job.id == job_id,
        Job.workspace_id == sid,
    ).first()
    if not job:
        return jsonify({"error": "Job not found", "code": "NOT_FOUND"}), 404

    return jsonify({
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "result": json.loads(job.result_json) if job.result_json else None,
        "error_code": job.error_code,
        "error_message": "Job failed; inspect safe error_code" if job.status == "failed" else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    })


@bp.post("/api/jobs")
def create_job():
    # Only the local workbench can launch computation. The public sandbox
    # exposes immutable published synthetic fixtures, not arbitrary jobs.
    if Config.APP_MODE != "local":
        return jsonify({"error": "Jobs are disabled in the hosted sandbox", "code": "FEATURE_RESTRICTED"}), 403

    sid = require_session()
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON object required", "code": "SCHEMA_INVALID"}), 422

    kind = body.get("kind")
    if kind not in ("extraction", "eval_run"):
        return jsonify({"error": "Unsupported job kind", "code": "INVALID_JOB_KIND"}), 422

    # Never accept arbitrary dataset directories, output paths, model URLs,
    # or raw shell arguments from a client.
    payload = body.get("payload", {})
    if payload not in ({}, None):
        return jsonify({"error": "Custom job payloads are not supported", "code": "INVALID_JOB_PAYLOAD"}), 422

    note_id = body.get("note_id")
    revision_id = body.get("source_revision_id")

    idempotency_key = body.get("idempotency_key")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str) or not idempotency_key.strip()
        or len(idempotency_key) > 128
    ):
        return jsonify({"error": "Invalid idempotency key", "code": "INVALID_IDEMPOTENCY_KEY"}), 422

    request_hash = hashlib.sha256(json.dumps({
        "kind": kind,
        "note_id": note_id,
        "source_revision_id": revision_id,
        "payload": {},
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def replay_or_conflict(existing):
        if existing.request_hash != request_hash:
            return jsonify({
                "error": "Idempotency key reused for a different job",
                "code": "IDEMPOTENCY_CONFLICT",
            }), 409
        return jsonify({
            "job_id": existing.id, "kind": existing.kind,
            "status": existing.status,
        }), 200

    # Replay matching existing job before checking current source revision freshness
    if idempotency_key:
        existing = g.db.query(Job).filter(
            Job.workspace_id == sid,
            Job.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return replay_or_conflict(existing)

    if kind == "extraction":
        if type(note_id) is not int or not isinstance(revision_id, str):
            return jsonify({"error": "A bound note/revision is required", "code": "JOB_BINDING_REQUIRED"}), 422
        note = g.db.query(Note).filter(
            Note.id == note_id,
            (Note.workspace_id == sid) | (Note.session_id == sid),
        ).first()
        if not note:
            return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
        if note.current_source_revision_id != revision_id:
            return jsonify({"error": "Source revision changed", "code": "STALE_REVISION_BASE"}), 409
    else:
        if note_id is not None or revision_id is not None:
            return jsonify({"error": "Benchmark jobs cannot reference workspace notes", "code": "INVALID_JOB_BINDING"}), 422

    job = Job(
        workspace_id=sid,
        kind=kind,
        note_id=note_id,
        source_revision_id=revision_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        payload_json="{}",
    )
    g.db.add(job)
    try:
        g.db.commit()
    except IntegrityError:
        g.db.rollback()
        if not idempotency_key:
            raise
        # Unique DB index catches two simultaneous creators of the same key.
        existing = g.db.query(Job).filter(
            Job.workspace_id == sid,
            Job.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return replay_or_conflict(existing)
        raise
    return jsonify({"job_id": job.id, "kind": job.kind, "status": job.status}), 202
