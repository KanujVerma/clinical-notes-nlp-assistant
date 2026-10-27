import json
import hashlib
import os
from flask import Blueprint, g, jsonify, request, send_file
from models import Note, NoteRevision, Extraction, OperationalIssue, SourceAsset
from utils.session import require_session
from extractors.pipeline import run_pipeline
from validation.checker import check_extraction
from config import Config

bp = Blueprint("revisions", __name__)


@bp.post("/api/notes/<int:note_id>/revisions")
def append_revision(note_id: int):
    sid = require_session()
    body = request.get_json(silent=True) or {}
    new_text = body.get("raw_text") if "raw_text" in body else body.get("text")
    if not isinstance(new_text, str) or not new_text.strip():
        return jsonify({"error": "Nonempty text is required", "code": "EMPTY_TEXT"}), 422
    if len(new_text.encode("utf-8")) > 2 * 1024 * 1024:
        return jsonify({"error": "Text size exceeds local limit", "code": "TEXT_TOO_LARGE"}), 413

    # A source edit must be explicitly based on the revision and lock state the
    # reviewer opened; a missing optimistic-concurrency token is not a wildcard.
    expected_revision = body.get("expected_source_revision_id")
    expected_lock_version = body.get("expected_lock_version")
    if not isinstance(expected_revision, str) or type(expected_lock_version) is not int:
        return jsonify({
            "error": "expected_source_revision_id and expected_lock_version are required",
            "code": "REVISION_BINDING_REQUIRED",
        }), 422

    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    if (
        note.current_source_revision_id != expected_revision
        or note.lock_version != expected_lock_version
    ):
        return jsonify({
            "error": "Source revision changed; refresh before editing",
            "code": "STALE_REVISION_BASE",
        }), 409

    # Determine next revision number
    latest_rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.note_id == note_id)
        .order_by(NoteRevision.revision_number.desc())
        .first()
    )
    next_rev_num = (latest_rev.revision_number + 1) if latest_rev else 1
    new_sha256 = hashlib.sha256(new_text.encode("utf-8")).hexdigest()

    new_rev = NoteRevision(
        note_id=note.id,
        workspace_id=sid,
        revision_number=next_rev_num,
        parent_revision_id=latest_rev.id if latest_rev else None,
        source_asset_id=latest_rev.source_asset_id if latest_rev else None,
        raw_text=new_text,
        normalized_text=new_text,
        sha256=new_sha256,
        creation_reason=body.get("reason", "human_edit"),
    )
    g.db.add(new_rev)
    g.db.flush()

    # Run extraction on new text
    extracted = run_pipeline(new_text)
    ext = Extraction(
        note_id=note.id,
        workspace_id=sid,
        source_revision_id=new_rev.id,
        source_text_hash=new_sha256,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(ext)
    g.db.flush()

    # Run independent validation checks
    issues = check_extraction(new_rev, ext)
    for iss in issues:
        op_issue = OperationalIssue(
            workspace_id=sid,
            note_id=note.id,
            source_revision_id=new_rev.id,
            extraction_id=ext.public_id,
            issue_code=iss.issue_code,
            severity=iss.severity,
            category=iss.category,
            item_id=iss.item_id,
            field_path=iss.field_path,
            evidence_span_json=json.dumps(iss.evidence_span) if iss.evidence_span else None,
            safe_explanation=iss.safe_explanation,
            check_policy_version=iss.check_policy_version,
        )
        g.db.add(op_issue)

    # Atomically advance the head only if it still matches the caller's exact
    # source and lock; a competing writer rolls back this entire new revision,
    # extraction and its issues instead of silently winning the last write.
    from sqlalchemy import update
    result = g.db.execute(
        update(Note)
        .where(
            Note.id == note.id,
            Note.workspace_id == sid,
            Note.current_source_revision_id == expected_revision,
            Note.lock_version == expected_lock_version,
        )
        .values(
            raw_text=new_text,
            current_source_revision_id=new_rev.id,
            current_extraction_id=ext.public_id,
            review_head_event_id=None,
            lock_version=Note.lock_version + 1,
            status="needs_review",
        )
    )
    if result.rowcount != 1:
        g.db.rollback()
        return jsonify({
            "error": "Source changed concurrently; refresh and compare",
            "code": "STALE_REVISION_BASE",
        }), 409

    # Historical Validation rows are deliberately retained as unverified
    # history, not deleted to simplify queue queries.
    g.db.commit()
    updated_lock_version = expected_lock_version + 1

    return jsonify({
        "note_id": note.id,
        "revision_id": new_rev.id,
        "revision_number": new_rev.revision_number,
        "extraction_id": ext.public_id,
        "status": note.status,
        "lock_version": updated_lock_version,
        "issues_count": len(issues),
    }), 201


@bp.get("/api/notes/<int:note_id>/revisions")
def get_revisions(note_id: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    revisions = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.note_id == note_id)
        .order_by(NoteRevision.revision_number.asc())
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "revision_number": r.revision_number,
            "parent_revision_id": r.parent_revision_id,
            "sha256": r.sha256,
            "creation_reason": r.creation_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "char_count": len(r.raw_text or ""),
        }
        for r in revisions
    ])


@bp.get("/api/notes/<int:note_id>/source")
def get_note_source(note_id: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    raw_text = rev.raw_text if rev else note.raw_text
    sha256 = rev.sha256 if rev else hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    pages = []
    if rev and rev.pages_json:
        try:
            pages = json.loads(rev.pages_json)
        except Exception:
            pages = []

    return jsonify({
        "note_id": note.id,
        "revision_id": rev.id if rev else None,
        "revision_number": rev.revision_number if rev else 1,
        "raw_text": raw_text,
        "sha256": sha256,
        "pages": pages,
        "filename": note.filename,
        "source": note.source,
    })


@bp.get("/api/notes/<int:note_id>/source-file")
def get_source_file(note_id: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    if not rev or not rev.source_asset_id:
        return jsonify({"error": "No binary source asset associated with this note", "code": "NO_ASSET"}), 404

    asset = g.db.query(SourceAsset).filter(SourceAsset.id == rev.source_asset_id).first()
    if not asset or not os.path.exists(asset.storage_key):
        return jsonify({"error": "Source asset file not found on disk", "code": "FILE_NOT_FOUND"}), 404

    return send_file(
        asset.storage_key,
        mimetype=asset.mime_type,
        as_attachment=False,
        download_name=asset.original_filename or f"note_{note_id}.bin",
    )
