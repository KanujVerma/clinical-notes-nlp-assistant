import json
import os
import tempfile
import hashlib
import pytesseract
from flask import Blueprint, g, jsonify, request
from config import Config
from models import Note, Extraction, NoteRevision, OperationalIssue, SourceAsset, AcquisitionRun
from utils.pdf import extract_text_from_image, extract_text_from_pdf
from utils.session import require_session
from extractors.pipeline import run_pipeline
from validation.checker import check_extraction

bp = Blueprint("upload", __name__)

_ALLOWED = {".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif"}
STORAGE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "storage")


@bp.post("/api/upload")
def upload():
    sid = require_session()

    # Rule A42: Hosted sandbox restricts arbitrary upload
    is_hosted = getattr(Config, "APP_MODE", "local") == "hosted_demo"
    if is_hosted:
        return jsonify({
            "error": "Arbitrary file upload is disabled in public hosted sandbox mode. Use curated fixtures or demo seed.",
            "code": "FEATURE_RESTRICTED",
        }), 403

    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in _ALLOWED:
        return jsonify(
            {"error": f"Unsupported file type: {ext}", "code": "UNSUPPORTED_FILE_TYPE"}
        ), 400

    file_bytes = f.read()
    if not file_bytes:
        return jsonify({"error": "Empty file provided", "code": "FILE_EMPTY"}), 400

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            text, source, ocr_confidence = extract_text_from_pdf(tmp_path)
        except ValueError as e:
            return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
        except pytesseract.TesseractNotFoundError:
            return jsonify({
                "error": "OCR engine not available. Install tesseract-ocr.",
                "code": "OCR_UNAVAILABLE",
            }), 503
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    elif ext in _IMAGE_EXTS:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            text, ocr_confidence = extract_text_from_image(tmp_path)
            source = "ocr"
        except ValueError as e:
            return jsonify({"error": str(e), "code": "OCR_EMPTY"}), 400
        except pytesseract.TesseractNotFoundError:
            return jsonify({
                "error": "OCR engine not available. Install tesseract-ocr.",
                "code": "OCR_UNAVAILABLE",
            }), 503
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    else:  # .txt
        text = file_bytes.decode("utf-8", errors="replace")
        source = "txt"
        ocr_confidence = None

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Persist SourceAsset in content-addressed storage
    raw_sha256 = hashlib.sha256(file_bytes).hexdigest()
    storage_dir = os.path.join(STORAGE_ROOT, raw_sha256[:2])
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{raw_sha256}.bin")
    if not os.path.exists(storage_path):
        with open(storage_path, "wb") as sf:
            sf.write(file_bytes)

    mime_type = f.mimetype or ("application/pdf" if ext == ".pdf" else "text/plain")
    source_asset = SourceAsset(
        workspace_id=sid,
        sha256=raw_sha256,
        storage_key=storage_path,
        mime_type=mime_type,
        byte_size=len(file_bytes),
        original_filename=os.path.basename(f.filename or "upload"),
        acquisition_kind="upload",
    )
    g.db.add(source_asset)
    g.db.flush()

    acq_run = AcquisitionRun(
        source_asset_id=source_asset.id,
        engine="pymupdf_tesseract" if ext != ".txt" else "text_utf8",
        status="completed",
        canonical_text=text,
    )
    g.db.add(acq_run)
    g.db.flush()

    # Create Note
    note = Note(
        filename=f.filename,
        raw_text=text,
        source=source,
        ocr_confidence=ocr_confidence,
        session_id=sid,
        workspace_id=sid,
        lock_version=0,
        status="needs_review",
    )
    g.db.add(note)
    g.db.flush()

    # Create initial NoteRevision (Revision 1)
    rev = NoteRevision(
        note_id=note.id,
        workspace_id=sid,
        revision_number=1,
        source_asset_id=source_asset.id,
        acquisition_run_id=acq_run.id,
        raw_text=text,
        normalized_text=text,
        sha256=text_hash,
        creation_reason="acquisition",
    )
    g.db.add(rev)
    g.db.flush()

    note.current_source_revision_id = rev.id

    # Run NLP Pipeline
    extracted = run_pipeline(text)
    ext_row = Extraction(
        note_id=note.id,
        workspace_id=sid,
        source_revision_id=rev.id,
        source_text_hash=text_hash,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(ext_row)
    g.db.flush()

    note.current_extraction_id = ext_row.public_id

    # Run Independent Validation Checker
    issues = check_extraction(rev, ext_row)
    for iss in issues:
        op_iss = OperationalIssue(
            workspace_id=sid,
            note_id=note.id,
            source_revision_id=rev.id,
            extraction_id=ext_row.public_id,
            issue_code=iss.issue_code,
            severity=iss.severity,
            category=iss.category,
            item_id=iss.item_id,
            field_path=iss.field_path,
            evidence_span_json=json.dumps(iss.evidence_span) if iss.evidence_span else None,
            safe_explanation=iss.safe_explanation,
            check_policy_version=iss.check_policy_version,
        )
        g.db.add(op_iss)

    g.db.commit()

    return jsonify({
        "note_id": note.id,
        "revision_id": rev.id,
        "extraction_id": ext_row.public_id,
        "extracted_json": extracted,
        "source": source,
        "raw_text": text,
        "ocr_confidence": ocr_confidence,
        "issues_count": len(issues),
    }), 201
