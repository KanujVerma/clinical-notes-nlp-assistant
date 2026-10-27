import json
from flask import Blueprint, g, jsonify, request
from models import Job, Note
from utils.session import require_session

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
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    })


@bp.post("/api/jobs")
def create_job():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    kind = body.get("kind")
    if not kind:
        return jsonify({"error": "kind is required", "code": "MISSING_KIND"}), 400

    note_id = body.get("note_id")
    if note_id is not None:
        note = g.db.query(Note).filter(Note.id == note_id).first()
        if not note:
            return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
        if (note.workspace_id or note.session_id) != sid:
            return jsonify({"error": "Note does not belong to this workspace", "code": "FORBIDDEN"}), 403

    job = Job(
        workspace_id=sid,
        kind=kind,
        note_id=note_id,
        source_revision_id=body.get("source_revision_id"),
        idempotency_key=body.get("idempotency_key"),
        payload_json=json.dumps(body.get("payload", {})),
    )
    g.db.add(job)
    g.db.commit()

    return jsonify({
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
    }), 202
