from flask import Blueprint, request, jsonify
from extractors.pipeline import run_pipeline

bp = Blueprint("extract", __name__)


@bp.post("/api/extract")
def extract():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400
    result = run_pipeline(text)
    return jsonify(result)
