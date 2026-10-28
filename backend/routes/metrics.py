import json
import os
from flask import Blueprint, jsonify, g
from sqlalchemy import select, func, or_, and_
from models import Note, Extraction, Validation, ReviewEvent, OperationalIssue
from config import Config
from utils.session import require_session

bp = Blueprint("metrics", __name__)

_CATEGORIES = ("vitals", "medications", "instructions", "metadata")


def _compute_correction_rates(pairs):
    """Compute per-category and per-field correction rates from (extracted, validated) pairs."""
    by_category = {cat: {"reviewed": 0, "corrected": 0} for cat in _CATEGORIES}
    by_field = {}

    for ext_json, val_json in pairs:
        try:
            extracted = json.loads(ext_json) if isinstance(ext_json, str) else ext_json
            validated = json.loads(val_json) if isinstance(val_json, str) else val_json
        except (json.JSONDecodeError, TypeError):
            continue

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

        # medications
        ext_meds_list = extracted.get("medications") or []
        val_meds_list = validated.get("medications") or []

        def get_occ_id(m, idx):
            return m.get("source_occurrence_id") or m.get("occurrence_id") or m.get("id") or f"med_{idx}"

        ext_meds = {get_occ_id(m, i): m for i, m in enumerate(ext_meds_list)}
        val_meds = {get_occ_id(m, i): m for i, m in enumerate(val_meds_list)}
        all_med_keys = set(ext_meds) | set(val_meds)
        for k in all_med_keys:
            by_category["medications"]["reviewed"] += 1
            if k not in ext_meds or k not in val_meds:
                by_category["medications"]["corrected"] += 1
            else:
                e, v = ext_meds[k], val_meds[k]
                for field in ("name", "dose", "route", "frequency"):
                    if str(e.get(field, "")).strip().lower() != str(v.get(field, "")).strip().lower():
                        by_category["medications"]["corrected"] += 1
                        break

    def _with_rate(d):
        reviewed = d["reviewed"]
        corrected = d["corrected"]
        return {
            "reviewed": reviewed,
            "corrected": corrected,
            "rate": round(corrected / reviewed, 4) if reviewed > 0 else 0.0,
            "rate_display": f"{round(corrected / reviewed * 100, 1)}%" if reviewed > 0 else "N/A",
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

    # 1. Query only Authoritative Current Completions
    # Note must belong to workspace, have an active review_head_event_id, and
    # the event must be review_completed bound to current revision and extraction.
    notes_with_head = (
        g.db.query(Note)
        .filter(
            or_(Note.workspace_id == sid, Note.session_id == sid),
            Note.review_head_event_id.isnot(None),
        )
        .all()
    )

    current_completed_events = []
    reviewed_note_ids = set()
    for n in notes_with_head:
        ev = g.db.query(ReviewEvent).filter(ReviewEvent.id == n.review_head_event_id).first()
        if (
            ev
            and ev.event_kind == "review_completed"
            and ev.source_revision_id == n.current_source_revision_id
            and ev.extraction_id == n.current_extraction_id
            and ev.derived_outcome in ("reviewed_unchanged", "reviewed_corrected")
        ):
            current_completed_events.append(ev)
            reviewed_note_ids.add(n.id)

    # 2. Legacy validation fallback/support (excluding notes that have current ReviewEvents or are pending)
    legacy_query = (
        select(
            Validation.status,
            func.count().label("count"),
            func.avg(Validation.correction_count).label("avg_corrections"),
            func.avg(Validation.review_duration_ms).label("avg_review_ms"),
        )
        .join(Note, Note.id == Validation.note_id)
        .where(
            or_(Note.workspace_id == sid, Note.session_id == sid),
            Note.review_head_event_id.is_(None),
            Note.status.in_(["accepted", "corrected", "reviewed_unchanged", "reviewed_corrected"]),
        )
    )
    if reviewed_note_ids:
        legacy_query = legacy_query.where(Note.id.not_in(reviewed_note_ids))
    legacy_rows = g.db.execute(legacy_query.group_by(Validation.status)).all()

    # Collect pairs for correction rate
    val_query = (
        select(Extraction.extracted_json, Validation.validated_json)
        .join(Note, Note.id == Validation.note_id)
        .join(
            Extraction,
            or_(
                Extraction.public_id == Note.current_extraction_id,
                and_(Note.current_extraction_id.is_(None), Extraction.note_id == Note.id),
            ),
        )
        .where(
            or_(Note.workspace_id == sid, Note.session_id == sid),
            Note.review_head_event_id.is_(None),
            Note.status.in_(["accepted", "corrected", "reviewed_unchanged", "reviewed_corrected"]),
        )
    )
    if reviewed_note_ids:
        val_query = val_query.where(Note.id.not_in(reviewed_note_ids))
    val_rows = g.db.execute(val_query).all()

    pairs = [(r.extracted_json, r.validated_json) for r in val_rows]

    # Include authoritative current ReviewEvent pairs
    for ev in current_completed_events:
        ext = g.db.query(Extraction).filter(Extraction.public_id == ev.extraction_id).first()
        if not ext and ev.extraction_id.isdigit():
            ext = g.db.query(Extraction).filter(Extraction.id == int(ev.extraction_id)).first()
        if ext:
            pairs.append((ext.extracted_json, ev.reviewed_snapshot_json))

    correction_rates = _compute_correction_rates(pairs)

    status_counts = {}
    for r in legacy_rows:
        status_counts[r.status] = {
            "status": r.status,
            "count": r.count,
            "avg_corrections": float(r.avg_corrections or 0),
            "avg_review_ms": float(r.avg_review_ms or 0),
        }

    durations_by_outcome = {}
    corrections_by_outcome = {}
    for ev in current_completed_events:
        s = ev.derived_outcome
        if s not in status_counts:
            status_counts[s] = {"status": s, "count": 0, "avg_corrections": 0.0, "avg_review_ms": 0.0}
        status_counts[s]["count"] += 1

        corrections = 0
        try:
            decisions = json.loads(ev.item_decisions_json or "{}")
            for item_key, dec_val in decisions.items():
                if isinstance(dec_val, dict):
                    if dec_val.get("decision") in ("edit", "remove", "add"):
                        corrections += 1
                elif isinstance(dec_val, str) and dec_val in ("edit", "remove", "add"):
                    corrections += 1
        except Exception:
            pass
        corrections_by_outcome.setdefault(s, []).append(corrections)

        if ev.review_duration_ms:
            durations_by_outcome.setdefault(s, []).append(ev.review_duration_ms)

    for s, corrs in corrections_by_outcome.items():
        if corrs and s in status_counts:
            status_counts[s]["avg_corrections"] = float(sum(corrs) / len(corrs))

    for s, durs in durations_by_outcome.items():
        if durs and s in status_counts:
            status_counts[s]["avg_review_ms"] = float(sum(durs) / len(durs))

    # Issue counts for workspace: bound open counts to each note's current revision/extraction
    issues = (
        g.db.query(OperationalIssue)
        .filter(OperationalIssue.workspace_id == sid)
        .all()
    )
    current_notes = (
        g.db.query(Note)
        .filter(or_(Note.workspace_id == sid, Note.session_id == sid))
        .all()
    )
    current_ext_keys = {
        (n.id, n.current_extraction_id)
        for n in current_notes
        if n.current_extraction_id
    }
    current_issues = [
        i for i in issues
        if (i.note_id, i.extraction_id) in current_ext_keys or i.note_id is None
    ]
    issues_summary = {
        "total": len(issues),
        "open_blockers": sum(1 for i in current_issues if i.severity == "critical_blocker" and i.status == "open"),
        "open_warnings": sum(1 for i in current_issues if i.severity == "warning" and i.status == "open"),
        "resolved": sum(1 for i in current_issues if i.status == "resolved"),
    }

    db_stats = {
        "by_status": list(status_counts.values()),
        "correction_rates": correction_rates,
        "issues_summary": issues_summary,
    }

    return jsonify({"eval": eval_data, "db_stats": db_stats})
