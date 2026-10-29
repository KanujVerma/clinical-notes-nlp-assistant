"""Workspace-scoped, current-source Metrics drilldowns.

No raw source or clinical values are returned in this index. Reviewers must
open the normal capability-protected Review page to inspect source evidence.
Historical events/issues do not appear as current evidence.
"""
from __future__ import annotations

import json
import re
from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_

from models import Note, ReviewEvent, Extraction, OperationalIssue
from utils.session import require_session

bp = Blueprint("metric_drilldown", __name__)

MAX_ROWS = 50
CATEGORIES = {"vitals", "instructions", "metadata", "medications"}
SEVERITIES = {"critical_blocker", "warning", "info"}
ISSUE_STATES = {"open", "acknowledged", "dismissed", "resolved"}
REVIEW_STATES = {"reviewed_unchanged", "reviewed_corrected"}


def _value(obj):
    if isinstance(obj, dict):
        return obj.get("value", obj)
    return obj


def _changed_paths(before: dict, after: dict) -> set[str]:
    """Detect all field-level changes without pairing drugs by their name.

    Medication drilldown uses the category (not a fabricated stable ID) until
    each source occurrence has authoritative geometry.
    """
    changed = set()
    for category in ("vitals", "metadata", "instructions"):
        b = before.get(category) or {}
        a = after.get(category) or {}
        if not isinstance(b, dict) or not isinstance(a, dict):
            continue
        for field in set(b) | set(a):
            if field not in b or field not in a or _value(b[field]) != _value(a[field]):
                changed.add(f"{category}.{field}")

    b_meds = before.get("medications") or []
    a_meds = after.get("medications") or []
    med_fields = (
        "name", "dose", "route", "frequency", "duration",
        "qualifier", "prn", "action", "status", "temporal_status",
    )

    def comparable_medications(items):
        if not isinstance(items, list):
            return []
        rows = []
        for index, med in enumerate(items):
            if not isinstance(med, dict):
                continue
            med_id = (
                med.get("source_occurrence_id")
                or med.get("occurrence_id")
                or med.get("id")
                or f"med_{index}"
            )
            semantic = tuple(
                (field, _value(med[field]))
                for field in med_fields if field in med and med[field] is not None
            )
            rows.append((str(med_id), semantic))
        return rows

    # A reviewed record may gain a server-assigned identity or additional
    # provenance metadata without changing a single medication fact.
    # Compare stable occurrences and their semantic attributes only.
    if comparable_medications(b_meds) != comparable_medications(a_meds):
        changed.add("medications")
    return changed


def _load_mapping(raw):
    try:
        obj = json.loads(raw or "{}")
        return obj if isinstance(obj, dict) else {}
    except (TypeError, ValueError):
        return {}


def _current_review_rows(sid):
    # All current event heads are selected *through Note*, never by simply
    # taking the latest ReviewEvent timestamp or including old extraction IDs.
    return (
        g.db.query(Note, ReviewEvent, Extraction)
        .join(ReviewEvent, ReviewEvent.id == Note.review_head_event_id)
        .join(Extraction, Extraction.public_id == Note.current_extraction_id)
        .filter(
            Note.workspace_id == sid,
            ReviewEvent.workspace_id == sid,
            Extraction.workspace_id == sid,
            ReviewEvent.note_id == Note.id,
            Extraction.note_id == Note.id,
            ReviewEvent.source_revision_id == Note.current_source_revision_id,
            ReviewEvent.extraction_id == Note.current_extraction_id,
            ReviewEvent.event_kind == "review_completed",
            ReviewEvent.derived_outcome.in_(REVIEW_STATES),
        )
        .order_by(Note.id.desc())
        .all()
    )


@bp.get("/api/metrics/drilldown")
def metric_drilldown():
    sid = require_session()
    kind = request.args.get("kind", "").strip()
    if kind not in ("issues", "corrections", "status"):
        return jsonify({"error": "Invalid drilldown", "code": "INVALID_DRILLDOWN"}), 422

    rows = []
    title = ""
    if kind == "issues":
        severity = request.args.get("severity", "")
        state = request.args.get("state", "open")
        if (severity and severity not in SEVERITIES) or state not in ISSUE_STATES:
            return jsonify({"error": "Invalid issue filter", "code": "INVALID_ISSUE_FILTER"}), 422
        title = f"{severity.replace('_', ' ').title() if severity else 'All'} issues ({state})"
        q = (
            g.db.query(OperationalIssue, Note)
            .join(Note, Note.id == OperationalIssue.note_id)
            .filter(
                Note.workspace_id == sid,
                OperationalIssue.workspace_id == sid,
                OperationalIssue.source_revision_id == Note.current_source_revision_id,
                or_(
                    OperationalIssue.extraction_id == Note.current_extraction_id,
                    OperationalIssue.extraction_id.is_(None),
                ),
                OperationalIssue.status == state,
            )
        )
        if severity:
            q = q.filter(OperationalIssue.severity == severity)
        for issue, note in q.order_by(OperationalIssue.created_at.desc()).limit(MAX_ROWS + 1):
            rows.append({
                "note_id": note.id,
                "source_revision_id": note.current_source_revision_id,
                "extraction_id": note.current_extraction_id,
                "issue_id": issue.id,
                "field_path": issue.field_path,
                "kind": "issue",
                "label": issue.issue_code,
                "severity": issue.severity,
                "detail": issue.safe_explanation[:240],
            })
    else:
        if kind == "status":
            status = request.args.get("status", "")
            if status not in REVIEW_STATES:
                return jsonify({"error": "Invalid review status", "code": "INVALID_STATUS"}), 422
            title = f"Current reviews: {status.replace('_', ' ')}"
        else:
            field = request.args.get("field", "")
            category = request.args.get("category", "")
            if field and (
                not re.fullmatch(r"(vitals|instructions|metadata)\.[a-zA-Z0-9_]{1,80}", field)
            ):
                return jsonify({"error": "Invalid field key", "code": "INVALID_FIELD"}), 422
            if category and category not in CATEGORIES:
                return jsonify({"error": "Invalid category", "code": "INVALID_CATEGORY"}), 422
            if not field and not category:
                return jsonify({"error": "Field or category is required", "code": "MISSING_FILTER"}), 422
            if field and category and not field.startswith(category + "."):
                return jsonify({"error": "Conflicting filters", "code": "INVALID_FILTER"}), 422
            title = f"Corrected field: {field}" if field else f"Corrections: {category}"
        for note, event, extraction in _current_review_rows(sid):
            if kind == "status" and event.derived_outcome != status:
                continue
            changed = _changed_paths(
                _load_mapping(extraction.extracted_json),
                _load_mapping(event.reviewed_snapshot_json),
            )
            if kind == "corrections":
                if field and field not in changed:
                    continue
                if category and not any(
                    name == category or name.startswith(category + ".") for name in changed
                ):
                    continue
            rows.append({
                "note_id": note.id,
                "source_revision_id": note.current_source_revision_id,
                "extraction_id": note.current_extraction_id,
                "review_event_id": event.id,
                "field_path": field if kind == "corrections" and field else None,
                "kind": kind,
                "label": event.derived_outcome.replace("_", " ").title(),
                "detail": (
                    f"{len(changed)} changed field group(s) in the current review"
                    if kind == "corrections" else "Current completed review"
                ),
            })
            if len(rows) > MAX_ROWS:
                break

    has_more = len(rows) > MAX_ROWS
    return jsonify({
        "kind": kind,
        "title": title,
        "rows": rows[:MAX_ROWS],
        "count_returned": min(len(rows), MAX_ROWS),
        "has_more": has_more,
        "max_rows": MAX_ROWS,
        "current_binding_only": True,
        "contains_raw_source": False,
    })
