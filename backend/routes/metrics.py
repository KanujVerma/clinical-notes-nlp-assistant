import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select, func
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from config import Config
from utils.session import require_session

bp = Blueprint("metrics", __name__)

_CATEGORIES = ("vitals", "medications", "instructions", "metadata")


def _compute_correction_rates(validations):
    """Compute per-category and per-field correction rates from validated notes."""
    # category_name -> {"reviewed": int, "corrected": int}
    by_category = {cat: {"reviewed": 0, "corrected": 0} for cat in _CATEGORIES}
    # "category.field" -> {"reviewed": int, "corrected": int}
    by_field = {}

    for ext_json, val_json in validations:
        try:
            extracted = json.loads(ext_json) if isinstance(ext_json, str) else ext_json
            validated = json.loads(val_json) if isinstance(val_json, str) else val_json
        except (json.JSONDecodeError, TypeError):
            continue

        # vitals, instructions, metadata — scalar dict sections
        for cat in ("vitals", "instructions", "metadata"):
            ext_sec = extracted.get(cat) or {}
            val_sec = validated.get(cat) or {}
            if not isinstance(ext_sec, dict) or not isinstance(val_sec, dict):
                continue
            all_keys = set(ext_sec) | set(val_sec)
            for key in all_keys:
                field_key = f"{cat}.{key}"
                if field_key not in by_field:
                    by_field[field_key] = {"reviewed": 0, "corrected": 0}
                by_field[field_key]["reviewed"] += 1
                by_category[cat]["reviewed"] += 1
                if key not in ext_sec or key not in val_sec:
                    by_field[field_key]["corrected"] += 1
                    by_category[cat]["corrected"] += 1
                else:
                    ext_val = str(ext_sec[key].get("value", "") if isinstance(ext_sec[key], dict) else ext_sec[key]).strip()
                    val_val = str(val_sec[key].get("value", "") if isinstance(val_sec[key], dict) else val_sec[key]).strip()
                    if ext_val != val_val:
                        by_field[field_key]["corrected"] += 1
                        by_category[cat]["corrected"] += 1

        # medications — match by name
        ext_meds = {m.get("name", "").lower().strip(): m for m in (extracted.get("medications") or [])}
        val_meds = {m.get("name", "").lower().strip(): m for m in (validated.get("medications") or [])}
        all_med_keys = set(ext_meds) | set(val_meds)
        for k in all_med_keys:
            by_category["medications"]["reviewed"] += 1
            if k not in ext_meds or k not in val_meds:
                by_category["medications"]["corrected"] += 1
            else:
                e, v = ext_meds[k], val_meds[k]
                for field in ("name", "dose", "route", "frequency"):
                    if e.get(field, "").strip() != v.get(field, "").strip():
                        by_category["medications"]["corrected"] += 1
                        break

    # Build final dicts with rate
    def _with_rate(d):
        reviewed = d["reviewed"]
        corrected = d["corrected"]
        return {
            "reviewed": reviewed,
            "corrected": corrected,
            "rate": round(corrected / reviewed, 4) if reviewed else 0.0,
        }

    return {
        "by_category": {cat: _with_rate(by_category[cat]) for cat in _CATEGORIES},
        "by_field": {k: _with_rate(v) for k, v in by_field.items()},
    }


@bp.get("/api/metrics")
def metrics():
    sid = require_session()
    from flask import current_app
    eval_results_path = current_app.config.get("EVAL_RESULTS_PATH", Config.EVAL_RESULTS_PATH)
    eval_data = None
    if os.path.exists(eval_results_path):
        with open(eval_results_path) as f:
            eval_data = json.load(f)

    # DB-based correction stats by status — scoped to session via Note join
    rows = g.db.execute(
        select(
            Validation.status,
            func.count().label("count"),
            func.avg(Validation.correction_count).label("avg_corrections"),
            func.avg(Validation.review_duration_ms).label("avg_review_ms"),
        )
        .join(Note, Note.id == Validation.note_id)
        .where(Note.session_id == sid)
        .group_by(Validation.status)
    ).all()

    # Per-category and per-field correction rates — scoped to session
    val_rows = g.db.execute(
        select(Extraction.extracted_json, Validation.validated_json)
        .join(Note, Note.id == Extraction.note_id)
        .join(Validation, Validation.note_id == Extraction.note_id)
        .where(Note.session_id == sid)
    ).all()
    correction_rates = _compute_correction_rates([(r.extracted_json, r.validated_json) for r in val_rows])

    db_stats = {
        "by_status": [
            {
                "status": r.status,
                "count": r.count,
                "avg_corrections": float(r.avg_corrections or 0),
                "avg_review_ms": float(r.avg_review_ms or 0),
            }
            for r in rows
        ],
        "correction_rates": correction_rates,
    }

    return jsonify({"eval": eval_data, "db_stats": db_stats})
