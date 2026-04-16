import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select, func
from models.validation import Validation
from config import Config

bp = Blueprint("metrics", __name__)


@bp.get("/api/metrics")
def metrics():
    # Load eval results (may not exist yet)
    from flask import current_app
    eval_results_path = current_app.config.get("EVAL_RESULTS_PATH", Config.EVAL_RESULTS_PATH)
    eval_data = None
    if os.path.exists(eval_results_path):
        with open(eval_results_path) as f:
            eval_data = json.load(f)

    # DB-based correction stats
    rows = g.db.execute(
        select(
            Validation.status,
            func.count().label("count"),
            func.avg(Validation.correction_count).label("avg_corrections"),
            func.avg(Validation.review_duration_ms).label("avg_review_ms"),
        ).group_by(Validation.status)
    ).all()

    db_stats = {
        "by_status": [
            {
                "status": r.status,
                "count": r.count,
                "avg_corrections": round(r.avg_corrections or 0, 2),
                "avg_review_ms": round(r.avg_review_ms or 0),
            }
            for r in rows
        ]
    }

    return jsonify({"eval": eval_data, "db_stats": db_stats})
