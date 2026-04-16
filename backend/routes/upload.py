# backend/routes/upload.py
import json
import os
import tempfile

import pytesseract
from flask import Blueprint, g, jsonify, request

from config import Config
from extractors.pipeline import run_pipeline
from models.extraction import Extraction
from models.note import Note
from utils.pdf import extract_text_from_image, extract_text_from_pdf

bp = Blueprint("upload", __name__)

_ALLOWED = {".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}


@bp.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in _ALLOWED:
        return jsonify(
            {"error": f"Unsupported file type: {ext}", "code": "UNSUPPORTED_FILE_TYPE"}
        ), 400

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            f.save(tmp.name)
            try:
                text, source, _ocr_confidence = extract_text_from_pdf(tmp.name)
            except ValueError as e:
                return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
            except pytesseract.TesseractNotFoundError:
                return jsonify({
                    "error": "OCR engine not available. Install tesseract-ocr.",
                    "code": "OCR_UNAVAILABLE",
                }), 503
            finally:
                os.unlink(tmp.name)

    elif ext in _IMAGE_EXTS:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            try:
                text, _ocr_confidence = extract_text_from_image(tmp.name)
                source = "ocr"
            except ValueError as e:
                return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
            except pytesseract.TesseractNotFoundError:
                return jsonify({
                    "error": "OCR engine not available. Install tesseract-ocr.",
                    "code": "OCR_UNAVAILABLE",
                }), 503
            finally:
                os.unlink(tmp.name)

    else:  # .txt
        text = f.read().decode("utf-8", errors="replace")
        source = "txt"
        _ocr_confidence = None

    extracted = run_pipeline(text)

    note = Note(filename=f.filename, raw_text=text, source=source, ocr_confidence=_ocr_confidence)
    g.db.add(note)
    g.db.flush()

    extraction = Extraction(
        note_id=note.id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({
        "note_id": note.id,
        "extracted_json": extracted,
        "source": source,
        "raw_text": text,
        "ocr_confidence": _ocr_confidence,
    }), 201
