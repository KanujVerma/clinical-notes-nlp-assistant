import json, os, tempfile
from flask import Blueprint, request, jsonify, g
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from utils.pdf import extract_text_from_pdf
from config import Config

bp = Blueprint("upload", __name__)
_ALLOWED = {".txt", ".pdf"}


@bp.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in _ALLOWED:
        return jsonify({"error": f"Unsupported file type: {ext}", "code": "UNSUPPORTED_FILE_TYPE"}), 400

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            f.save(tmp.name)
            try:
                text = extract_text_from_pdf(tmp.name)
            except ValueError as e:
                return jsonify({"error": str(e), "code": "EMPTY_PDF_TEXT"}), 400
            finally:
                os.unlink(tmp.name)
        source = "pdf"
    else:
        text = f.read().decode("utf-8", errors="replace")
        source = "txt"

    extracted = run_pipeline(text)

    note = Note(filename=f.filename, raw_text=text, source=source)
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
