from flask import Blueprint, request, jsonify
from config import Config

bp = Blueprint("extract", __name__)


@bp.post("/api/extract")
def extract():
    if Config.APP_MODE == "hosted_demo":
        return jsonify({"error": "Arbitrary text extraction is disabled in the public sandbox", "code": "FEATURE_RESTRICTED"}), 403
    from extractors.pipeline import run_pipeline
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400
    result = run_pipeline(text)
    return jsonify(result)
