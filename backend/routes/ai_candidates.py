import json
import os
import io
import hashlib
import fitz
from flask import Blueprint, g, jsonify, request
from models import Note, NoteRevision, Extraction, InferenceRun, SourceAsset
from services.ollama_service import extract_candidates_with_local_ai, detect_discrepancies
from services.multimodal_service import (
    glm_ocr_infer, qwen3_vl_infer, DEFAULT_OCR_MODEL, DEFAULT_VL_MODEL,
)
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

    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return jsonify({"error": "JSON object required", "code": "INVALID_INPUT"}), 422
    adapter = body.get("adapter", "text")  # "text" | "qwen3_vl" | "glm_ocr"
    if adapter not in ("text", "qwen3_vl", "glm_ocr"):
        return jsonify({"error": "Unsupported AI adapter", "code": "INVALID_ADAPTER"}), 422
    expected_model = DEFAULT_OCR_MODEL if adapter == "glm_ocr" else DEFAULT_VL_MODEL
    requested_model = body.get("model")
    if requested_model is not None and requested_model != expected_model:
        return jsonify({
            "error": "AI model must match the configured local allowlisted model",
            "code": "UNSUPPORTED_MODEL",
        }), 422
    page_number = body.get("page_number", 1)
    if type(page_number) is not int or not 1 <= page_number <= 20:
        return jsonify({"error": "Invalid document page", "code": "INVALID_PAGE"}), 422

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    if not rev or rev.note_id != note.id or rev.workspace_id != sid:
        return jsonify({"error": "Current source revision is unavailable",
                        "code": "SOURCE_BINDING_REQUIRED"}), 409
    raw_text = rev.raw_text

    # Get current rule extraction
    ext = (
        g.db.query(Extraction)
        .filter(Extraction.public_id == note.current_extraction_id)
        .first()
    )
    if (not ext or ext.note_id != note.id
            or ext.source_revision_id != rev.id
            or ext.source_text_hash != rev.sha256
            or ext.status != "completed"):
        return jsonify({"error": "Current extraction must be source-bound",
                        "code": "EXTRACTION_BINDING_REQUIRED"}), 409
    rule_data = json.loads(ext.extracted_json or "{}")

    # Text-only proposals never require a page raster. Vision adapters must
    # operate on actual pixels: never silently fall back to text inference.
    image_bytes = None
    if adapter != "text" and rev and rev.source_asset_id:
        asset = g.db.query(SourceAsset).filter(SourceAsset.id == rev.source_asset_id).first()
        if asset and asset.workspace_id == sid and os.path.isfile(asset.storage_key):
            if os.path.getsize(asset.storage_key) > 10 * 1024 * 1024:
                return jsonify({"error": "Source asset exceeds inference budget",
                                "code": "IMAGE_TOO_LARGE"}), 413
            with open(asset.storage_key, "rb") as source_stream:
                original_bytes = source_stream.read(10 * 1024 * 1024 + 1)
            if hashlib.sha256(original_bytes).hexdigest() != asset.sha256:
                return jsonify({"error": "Original source asset checksum mismatch",
                                "code": "SOURCE_ASSET_INTEGRITY_FAILURE"}), 409
            ext_name = os.path.splitext(asset.original_filename or "")[1].lower()
            if ext_name == ".pdf" or asset.mime_type == "application/pdf":
                doc = fitz.open(asset.storage_key)
                try:
                    if len(doc) >= page_number:
                        page = doc[page_number - 1]
                        raster_pixels = (page.rect.width * 150 / 72) * (page.rect.height * 150 / 72)
                        if raster_pixels > 20_000_000:
                            return jsonify({"error": "Page exceeds raster budget", "code": "IMAGE_TOO_LARGE"}), 413
                        pix = page.get_pixmap(dpi=150)
                        image_bytes = pix.tobytes("png")
                finally:
                    doc.close()
            elif asset.mime_type.startswith("image/"):
                if page_number != 1:
                    return jsonify({"error": "Image source has one page", "code": "INVALID_PAGE"}), 422
                if os.path.getsize(asset.storage_key) > 10 * 1024 * 1024:
                    return jsonify({"error": "Image exceeds input budget", "code": "IMAGE_TOO_LARGE"}), 413
                with open(asset.storage_key, "rb") as f:
                    image_bytes = f.read()

    if adapter != "text" and not image_bytes:
        return jsonify({
            "error": "Vision inference requires an original image/PDF page",
            "code": "IMAGE_SOURCE_REQUIRED",
        }), 422

    if adapter == "glm_ocr" and image_bytes:
        res = glm_ocr_infer(image_bytes=image_bytes, page_number=page_number, model=expected_model)
        task_type = "multimodal_ocr"
        candidates = {"transcribed_text": res.get("transcribed_text"), "boxes": res.get("boxes", [])}
        discrepancies = []
        model_name = res.get("model", "glm-ocr:q8_0")
        status = res.get("status", "completed")
        error_code = res.get("error_code")

    elif adapter == "qwen3_vl" and image_bytes:
        res = qwen3_vl_infer(image_bytes=image_bytes, rule_extraction=rule_data, model=expected_model)
        task_type = "multimodal_vl"
        candidates = res.get("candidates") or {}
        discrepancies = res.get("discrepancies", [])
        model_name = res.get("model", "qwen3-vl:4b")
        status = res.get("status", "completed")
        error_code = res.get("error_code")

    else:
        # Default text-based semantic candidates
        task_type = "semantic_candidates"
        ai_res = extract_candidates_with_local_ai(raw_text, model=expected_model)
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
        input_hash=hashlib.sha256(
            image_bytes if image_bytes is not None else raw_text.encode("utf-8")
        ).hexdigest(),
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
