import json
import os
import io
import fitz
from flask import Blueprint, g, jsonify, request
from models import Note, NoteRevision, Extraction, InferenceRun, SourceAsset
from services.ollama_service import extract_candidates_with_local_ai, detect_discrepancies
from services.multimodal_service import glm_ocr_infer, qwen3_vl_infer
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

    body = request.get_json(silent=True) or {}
    adapter = body.get("adapter", "text")  # "text" | "qwen3_vl" | "glm_ocr"
    requested_model = body.get("model")

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

    # Check if multimodal image input is requested and available
    image_bytes = None
    if rev and rev.source_asset_id:
        asset = g.db.query(SourceAsset).filter(SourceAsset.id == rev.source_asset_id).first()
        if asset and os.path.exists(asset.storage_key):
            ext_name = os.path.splitext(asset.original_filename or "")[1].lower()
            if ext_name == ".pdf" or asset.mime_type == "application/pdf":
                doc = fitz.open(asset.storage_key)
                try:
                    if len(doc) > 0:
                        pix = doc[0].get_pixmap(dpi=150)
                        image_bytes = pix.tobytes("png")
                finally:
                    doc.close()
            else:
                with open(asset.storage_key, "rb") as f:
                    image_bytes = f.read()

    if adapter == "glm_ocr" and image_bytes:
        res = glm_ocr_infer(image_bytes=image_bytes, page_number=1, model=requested_model)
        task_type = "multimodal_ocr"
        candidates = {"transcribed_text": res.get("transcribed_text"), "boxes": res.get("boxes", [])}
        discrepancies = []
        model_name = res.get("model", "glm-ocr:q8_0")
        status = res.get("status", "completed")
        error_code = res.get("error_code")

    elif adapter == "qwen3_vl" and image_bytes:
        res = qwen3_vl_infer(image_bytes=image_bytes, rule_extraction=rule_data, model=requested_model)
        task_type = "multimodal_vl"
        candidates = res.get("candidates") or {}
        discrepancies = res.get("discrepancies", [])
        model_name = res.get("model", "qwen3-vl:4b")
        status = res.get("status", "completed")
        error_code = res.get("error_code")

    else:
        # Default text-based semantic candidates
        task_type = "semantic_candidates"
        ai_res = extract_candidates_with_local_ai(raw_text, model=requested_model or "qwen3-vl:4b")
        candidates = ai_res.get("candidates") or {}
        discrepancies = detect_discrepancies(rule_data, candidates) if candidates else []
        model_name = ai_res.get("model", "qwen3-vl:4b")
        status = ai_res.get("status", "completed")
        error_code = ai_res.get("error_code")

    # Save as InferenceRun without modifying authoritative extraction
    inf_run = InferenceRun(
        workspace_id=sid,
        note_id=note.id,
        source_revision_id=rev.id if rev else "rev_default",
        task_type=task_type,
        model_name=model_name,
        status=status,
        parsed_candidate_json=json.dumps(candidates),
        discrepancies_json=json.dumps(discrepancies),
        error_code=error_code,
    )
    g.db.add(inf_run)
    g.db.commit()

    return jsonify({
        "inference_run_id": inf_run.id,
        "task_type": inf_run.task_type,
        "status": inf_run.status,
        "model": inf_run.model_name,
        "candidates": candidates,
        "discrepancies": discrepancies,
        "error_code": inf_run.error_code,
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
            "task_type": r.task_type,
            "model_name": r.model_name,
            "status": r.status,
            "candidates": json.loads(r.parsed_candidate_json) if r.parsed_candidate_json else None,
            "discrepancies": json.loads(r.discrepancies_json) if r.discrepancies_json else None,
            "error_code": r.error_code,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ])
