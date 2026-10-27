import json
from flask import Blueprint, g, jsonify, request
from models import Note, NoteRevision, Extraction, InferenceRun
from services.ollama_service import extract_candidates_with_local_ai, detect_discrepancies
from utils.session import require_session
from config import Config

bp = Blueprint("ai_candidates", __name__)


@bp.post("/api/notes/<int:note_id>/ai-candidates")
def generate_ai_candidates(note_id: int):
    sid = require_session()
    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    if is_hosted:
        return jsonify({
            "error": "Live local AI inference is disabled in public hosted sandbox mode. Curated fixtures only.",
            "code": "FEATURE_RESTRICTED",
        }), 403

    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    raw_text = rev.raw_text if rev else note.raw_text

    # Get current rule extraction
    ext = (
        g.db.query(Extraction)
        .filter(Extraction.public_id == note.current_extraction_id)
        .first()
    )
    rule_data = json.loads(ext.extracted_json) if (ext and ext.extracted_json) else {}

    ai_res = extract_candidates_with_local_ai(raw_text)
    candidates = ai_res.get("candidates") or {}

    discrepancies = detect_discrepancies(rule_data, candidates) if candidates else []

    inf_run = InferenceRun(
        workspace_id=sid,
        note_id=note.id,
        source_revision_id=rev.id if rev else "rev_default",
        task_type="semantic_candidates",
        model_name=ai_res.get("model", "qwen3-vl:4b"),
        status=ai_res.get("status", "completed"),
        parsed_candidate_json=json.dumps(candidates),
        discrepancies_json=json.dumps(discrepancies),
        error_code=ai_res.get("error_code"),
    )
    g.db.add(inf_run)
    g.db.commit()

    return jsonify({
        "inference_run_id": inf_run.id,
        "status": inf_run.status,
        "model": inf_run.model_name,
        "candidates": candidates,
        "discrepancies": discrepancies,
    }), 201


@bp.get("/api/notes/<int:note_id>/ai-candidates")
def get_ai_candidates(note_id: int):
    sid = require_session()
    runs = (
        g.db.query(InferenceRun)
        .filter(
            InferenceRun.note_id == note_id,
            InferenceRun.workspace_id == sid,
        )
        .order_by(InferenceRun.created_at.desc())
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "model_name": r.model_name,
            "status": r.status,
            "candidates": json.loads(r.parsed_candidate_json) if r.parsed_candidate_json else None,
            "discrepancies": json.loads(r.discrepancies_json) if r.discrepancies_json else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ])
