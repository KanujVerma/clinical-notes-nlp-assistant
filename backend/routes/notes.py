import json
from flask import Blueprint, request, jsonify, g
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from config import Config
from utils.session import require_session

bp = Blueprint("notes", __name__)


@bp.post("/api/notes")
def create_note():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400

    extracted = run_pipeline(text)

    note = Note(raw_text=text, source="paste", session_id=sid)
    g.db.add(note)
    g.db.flush()

    extraction = Extraction(
        note_id=note.id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note.id, "extracted_json": extracted}), 201


@bp.put("/api/notes/<int:note_id>/text")
def update_note_text(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required", "code": "TEXT_REQUIRED"}), 400

    note.raw_text = text

    g.db.query(Extraction).filter_by(note_id=note_id).delete()

    # Re-run pipeline and create new extraction
    extracted = run_pipeline(text)
    extraction = Extraction(
        note_id=note_id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note_id, "extracted_json": extracted}), 200
