import io
import json
import hashlib
import os
import fitz
from PIL import Image, ImageDraw
from flask import Blueprint, g, jsonify, request, send_file
from models import Note, NoteRevision, Extraction, OperationalIssue, SourceAsset
from utils.session import require_session
from extractors.pipeline import run_pipeline
from validation.checker import check_extraction
from utils.coordinates import transform_bbox, validate_bbox_geometry, check_source_image_agreement
from config import Config

bp = Blueprint("revisions", __name__)


@bp.post("/api/notes/<int:note_id>/revisions")
def append_revision(note_id: int):
    if Config.APP_MODE == "hosted_demo":
        return jsonify({"error": "Source replacement is disabled in the public sandbox", "code": "FEATURE_RESTRICTED"}), 403
    sid = require_session()
    body = request.get_json(silent=True) or {}
    new_text = body.get("raw_text") if "raw_text" in body else body.get("text")
    if not isinstance(new_text, str) or not new_text.strip():
        return jsonify({"error": "Nonempty text is required", "code": "EMPTY_TEXT"}), 422
    if len(new_text.encode("utf-8")) > 2 * 1024 * 1024:
        return jsonify({"error": "Text size exceeds local limit", "code": "TEXT_TOO_LARGE"}), 413

    note = g.db.query(Note).filter(Note.id == note_id).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.workspace_id != sid and note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    # A source edit must be explicitly based on the revision and lock state the
    # reviewer opened; a missing optimistic-concurrency token is not a wildcard.
    expected_revision = body.get("expected_source_revision_id")
    expected_lock_version = body.get("expected_lock_version")
    if not isinstance(expected_revision, str) or type(expected_lock_version) is not int:
        return jsonify({
            "error": "expected_source_revision_id and expected_lock_version are required",
            "code": "REVISION_BINDING_REQUIRED",
        }), 422

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

    # Retain binary page inventory and dimensions when editing text of an acquired asset
    inherited_pages_json = None
    if latest_rev and latest_rev.source_asset_id:
        raw_pages_str = latest_rev.pages_json
        if not raw_pages_str and latest_rev.acquisition_run_id:
            from models import AcquisitionRun
            acq = g.db.query(AcquisitionRun).filter(AcquisitionRun.id == latest_rev.acquisition_run_id).first()
            if acq and acq.pages_json:
                raw_pages_str = acq.pages_json
        if raw_pages_str:
            try:
                raw_pages = json.loads(raw_pages_str)
                clean_pages = [
                    {
                        "page_number": p.get("page_number", idx + 1),
                        "width": p.get("width", 800),
                        "height": p.get("height", 1100),
                        "acquisition_method": p.get("acquisition_method", "binary_asset"),
                        "confidence": p.get("confidence", 1.0),
                        "boxes": [],
                    }
                    for idx, p in enumerate(raw_pages)
                ]
                inherited_pages_json = json.dumps(clean_pages)
            except Exception:
                inherited_pages_json = None

    new_rev = NoteRevision(
        note_id=note.id,
        workspace_id=sid,
        revision_number=next_rev_num,
        parent_revision_id=latest_rev.id if latest_rev else None,
        source_asset_id=latest_rev.source_asset_id if latest_rev else None,
        raw_text=new_text,
        normalized_text=new_text,
        sha256=new_sha256,
        pages_json=inherited_pages_json,
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
    if rev:
        if rev.pages_json:
            try:
                pages = json.loads(rev.pages_json)
            except Exception:
                pages = []
        elif rev.acquisition_run_id:
            from models import AcquisitionRun
            acq = g.db.query(AcquisitionRun).filter(AcquisitionRun.id == rev.acquisition_run_id).first()
            if acq and acq.pages_json:
                try:
                    pages = json.loads(acq.pages_json)
                except Exception:
                    pages = []
        elif rev.source_asset_id:
            from models import AcquisitionRun
            acq = (
                g.db.query(AcquisitionRun)
                .filter(AcquisitionRun.source_asset_id == rev.source_asset_id)
                .order_by(AcquisitionRun.id.desc())
                .first()
            )
            if acq and acq.pages_json:
                try:
                    raw_pages = json.loads(acq.pages_json)
                    pages = [
                        {
                            "page_number": p.get("page_number", idx + 1),
                            "width": p.get("width", 800),
                            "height": p.get("height", 1100),
                            "acquisition_method": p.get("acquisition_method", "binary_asset"),
                            "confidence": p.get("confidence", 1.0),
                            "boxes": [],
                        }
                        for idx, p in enumerate(raw_pages)
                    ]
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


@bp.get("/api/notes/<int:note_id>/pages/<int:page_number>/image")
def get_page_image(note_id: int, page_number: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    try:
        rotation = int(request.args.get("rotation", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid rotation", "code": "INVALID_ROTATION"}), 422
    if rotation not in (0, 90, 180, 270):
        return jsonify({"error": "Rotation must be 0, 90, 180 or 270", "code": "INVALID_ROTATION"}), 422

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    if not rev:
        return jsonify({"error": "No revision found", "code": "NOT_FOUND"}), 404

    # If binary source asset exists
    if rev.source_asset_id:
        asset = g.db.query(SourceAsset).filter(SourceAsset.id == rev.source_asset_id).first()
        if asset and os.path.exists(asset.storage_key):
            ext = os.path.splitext(asset.original_filename or "")[1].lower()
            if ext == ".pdf" or asset.mime_type == "application/pdf":
                doc = fitz.open(asset.storage_key)
                try:
                    if page_number < 1 or page_number > len(doc):
                        return jsonify({"error": f"Page {page_number} out of bounds (1..{len(doc)})", "code": "PAGE_OUT_OF_BOUNDS"}), 404
                    page = doc[page_number - 1]
                    rot_deg = (rotation % 360 + 360) % 360
                    zoom = 150.0 / 72.0
                    estimated_pixels = page.rect.width * page.rect.height * zoom * zoom
                    if estimated_pixels > 20_000_000:
                        return jsonify({"error": "Page raster size exceeded", "code": "PAGE_TOO_LARGE"}), 413
                    mat = fitz.Matrix(zoom, zoom).prerotate(rot_deg)
                    pix = page.get_pixmap(matrix=mat)
                    img_bytes = pix.tobytes("png")
                    return send_file(io.BytesIO(img_bytes), mimetype="image/png")
                finally:
                    doc.close()
            elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif") or asset.mime_type.startswith("image/"):
                # Direct image asset
                if page_number != 1:
                    return jsonify({"error": "Image assets have only page 1", "code": "PAGE_OUT_OF_BOUNDS"}), 404
                with Image.open(asset.storage_key) as img:
                    rot_deg = (rotation % 360 + 360) % 360
                    if rot_deg != 0:
                        img = img.rotate(-rot_deg, expand=True)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    return send_file(buf, mimetype="image/png")

    # If no binary source asset, generate a clean rendered document page image
    if page_number != 1:
        return jsonify({"error": "Text notes have only page 1", "code": "PAGE_OUT_OF_BOUNDS"}), 404

    text = rev.raw_text or note.raw_text or ""
    img = Image.new("RGB", (800, 1100), color=(252, 252, 253))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 800, 40], fill=(241, 245, 249))
    draw.text((20, 12), f"CLINICAL NOTE #{note.id} — SOURCE TRANSCRIPT", fill=(71, 85, 105))

    lines = text.split("\n")
    y = 60
    for line in lines[:45]:
        draw.text((40, y), line[:85], fill=(15, 23, 42))
        y += 22

    rot_deg = (rotation % 360 + 360) % 360
    if rot_deg != 0:
        img = img.rotate(-rot_deg, expand=True)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@bp.post("/api/notes/<int:note_id>/verify-evidence-geometry")
def verify_evidence_geometry(note_id: int):
    sid = require_session()
    note = g.db.query(Note).filter(
        Note.id == note_id,
        (Note.workspace_id == sid) | (Note.session_id == sid),
    ).first()
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    body = request.get_json(silent=True) or {}
    span_text = body.get("span_text", "")
    bbox = body.get("bbox")
    try:
        page_number = int(body.get("page_number", 1))
    except (ValueError, TypeError):
        page_number = 1
    try:
        rotation = int(body.get("rotation", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid rotation", "code": "INVALID_ROTATION"}), 422
    if rotation not in (0, 90, 180, 270):
        return jsonify({"error": "Unsupported rotation", "code": "INVALID_ROTATION"}), 422

    rev = (
        g.db.query(NoteRevision)
        .filter(NoteRevision.id == note.current_source_revision_id)
        .first()
    )
    pages = []
    if rev and rev.pages_json:
        try:
            pages = json.loads(rev.pages_json)
        except Exception:
            pages = []

    target_page = None
    for p in pages:
        if p.get("page_number") == page_number:
            target_page = p
            break

    if pages and target_page is None:
        return jsonify({"error": "Source page is unavailable", "code": "PAGE_OUT_OF_BOUNDS"}), 404
    if not pages and page_number != 1:
        return jsonify({"error": "Transcript has only one rendered page", "code": "PAGE_OUT_OF_BOUNDS"}), 404

    page_width = target_page.get("width", 800.0) if target_page else 800.0
    page_height = target_page.get("height", 1100.0) if target_page else 1100.0
    page_boxes = target_page.get("boxes", []) if target_page else []

    is_valid, code, explanation = validate_bbox_geometry(bbox, page_width, page_height)
    transformed = None
    if is_valid:
        try:
            transformed = transform_bbox(bbox, page_width, page_height, rotation=rotation)
        except Exception:
            transformed = None

    agreement_res = check_source_image_agreement(
        span_text=span_text,
        bbox=bbox,
        page_boxes=page_boxes,
        page_width=page_width,
        page_height=page_height,
    )

    return jsonify({
        "note_id": note.id,
        "page_number": page_number,
        "is_valid_geometry": is_valid,
        "geometry_code": code,
        "geometry_message": explanation,
        "transformed_overlay": transformed,
        "agreement": agreement_res.get("agreement", False),
        "agreement_status": agreement_res.get("status"),
        "similarity": agreement_res.get("similarity", 0.0),
        "ocr_text": agreement_res.get("ocr_text", ""),
        "disagreement_reason": agreement_res.get("reason"),
    })
