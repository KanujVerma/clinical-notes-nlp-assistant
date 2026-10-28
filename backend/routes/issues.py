import json
from flask import Blueprint, g, jsonify, request
from models import OperationalIssue, IssueEvent
from utils.session import require_session
from config import Config

bp = Blueprint("issues", __name__)


@bp.get("/api/issues")
def list_issues():
    sid = require_session()
    query = g.db.query(OperationalIssue).filter(OperationalIssue.workspace_id == sid)

    note_id = request.args.get("note_id")
    if note_id:
        try:
            query = query.filter(OperationalIssue.note_id == int(note_id))
        except ValueError:
            pass

    status = request.args.get("status")
    if status:
        query = query.filter(OperationalIssue.status == status)

    severity = request.args.get("severity")
    if severity:
        query = query.filter(OperationalIssue.severity == severity)

    category = request.args.get("category")
    if category:
        query = query.filter(OperationalIssue.category == category)

    issues = query.order_by(OperationalIssue.created_at.desc()).all()

    return jsonify([
        {
            "id": iss.id,
            "note_id": iss.note_id,
            "source_revision_id": iss.source_revision_id,
            "extraction_id": iss.extraction_id,
            "issue_code": iss.issue_code,
            "severity": iss.severity,
            "category": iss.category,
            "item_id": iss.item_id,
            "field_path": iss.field_path,
            "evidence_span": json.loads(iss.evidence_span_json) if iss.evidence_span_json else None,
            "safe_explanation": iss.safe_explanation,
            "status": iss.status,
            "created_at": iss.created_at.isoformat() if iss.created_at else None,
        }
        for iss in issues
    ])


@bp.post("/api/issues/<string:issue_id>/disposition")
def update_issue_disposition(issue_id: str):
    # No free-form issue explanations from anonymous public visitors.
    # The hosted demo can still display curated issue metadata.
    if Config.APP_MODE == "hosted_demo":
        return jsonify({
            "error": "Issue dispositions are local-only until curated choices are available",
            "code": "FEATURE_RESTRICTED",
        }), 403
    sid = require_session()
    issue = g.db.query(OperationalIssue).filter(
        OperationalIssue.id == issue_id,
        OperationalIssue.workspace_id == sid,
    ).first()
    if not issue:
        return jsonify({"error": "Issue not found", "code": "NOT_FOUND"}), 404

    body = request.get_json(silent=True) or {}
    disposition = body.get("disposition")
    reason = body.get("reason", "")
    if disposition not in ("acknowledged", "dismissed", "resolved"):
        return jsonify({"error": "Invalid disposition", "code": "INVALID_DISPOSITION"}), 400

    # An integrity blocker is not resolved by a human acknowledgement. It
    # remains open until the underlying source/extraction is repaired and a
    # new bound check run supersedes the finding.
    if issue.severity == "critical_blocker":
        return jsonify({
            "error": "Critical source/evidence issues require correction and reprocessing",
            "code": "CRITICAL_ISSUE_NOT_DISMISSIBLE",
        }), 409

    if not isinstance(reason, str) or not reason.strip():
        return jsonify({
            "error": "A disposition reason is required",
            "code": "DISPOSITION_REASON_REQUIRED",
        }), 422

    issue.status = disposition
    evt = IssueEvent(
        issue_id=issue.id,
        action=disposition,
        reason=reason,
        actor=body.get("actor", "reviewer"),
    )
    g.db.add(evt)
    g.db.commit()

    return jsonify({
        "issue_id": issue.id,
        "status": issue.status,
        "reason": reason,
    })
