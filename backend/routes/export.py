import io
import json
import zipfile
import hashlib
import html
from flask import Blueprint, g, jsonify, send_file
from models import ReviewEvent, Note, NoteRevision, Extraction, OperationalIssue
from utils.session import require_session

bp = Blueprint("export", __name__)


@bp.get("/api/review-events/<string:event_id>/export")
def export_reviewed_bundle(event_id: str):
    sid = require_session()
    ev = g.db.query(ReviewEvent).filter(
        ReviewEvent.id == event_id,
        ReviewEvent.workspace_id == sid,
    ).first()
    if not ev:
        return jsonify({"error": "Review event not found", "code": "NOT_FOUND"}), 404

    note = g.db.query(Note).filter(Note.id == ev.note_id).first()
    rev = g.db.query(NoteRevision).filter(NoteRevision.id == ev.source_revision_id).first()
    ext = (
        g.db.query(Extraction)
        .filter(
            (Extraction.public_id == ev.extraction_id) | (Extraction.id == int(ev.extraction_id) if ev.extraction_id.isdigit() else False)
        )
        .first()
    )

    reviewed_snapshot = json.loads(ev.reviewed_snapshot_json or "{}")
    item_decisions = json.loads(ev.item_decisions_json or "{}")
    category_ack = json.loads(ev.category_acknowledgments_json or "{}")
    issue_disp = json.loads(ev.issue_dispositions_json or "{}")
    original_extracted = json.loads(ext.extracted_json or "{}") if ext else {}

    source_meta = {
        "note_id": note.id if note else ev.note_id,
        "revision_id": rev.id if rev else ev.source_revision_id,
        "revision_number": rev.revision_number if rev else 1,
        "sha256": rev.sha256 if rev else ev.source_hash,
        "raw_text": rev.raw_text if rev else (note.raw_text if note else ""),
    }

    # Generate Human-Readable HTML Summary
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Reviewed Clinical Document — Note {ev.note_id}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #1e293b; line-height: 1.5; }}
    h1, h2, h3 {{ color: #0f172a; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
    .badge-success {{ background: #dcfce7; color: #166534; }}
    .badge-info {{ background: #e0f2fe; color: #0369a1; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; margin-bottom: 24px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; font-size: 14px; }}
    th {{ background: #f8fafc; font-weight: 600; }}
    .meta-box {{ background: #f1f5f9; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
    pre {{ background: #0f172a; color: #f8fafc; padding: 16px; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>Reviewed Clinical Extraction</h1>
  <div class="meta-box">
    <p><strong>Note ID:</strong> {html.escape(str(ev.note_id))} | <strong>Event ID:</strong> {html.escape(str(ev.id))}</p>
    <p><strong>Outcome:</strong> <span class="badge badge-success">{html.escape(str(ev.derived_outcome))}</span> | <strong>Event Kind:</strong> {html.escape(str(ev.event_kind))}</p>
    <p><strong>Source SHA-256:</strong> <code>{html.escape(str(ev.source_hash))}</code></p>
    <p><strong>Review Timestamp:</strong> {html.escape(ev.created_at.isoformat()) if ev.created_at else 'N/A'}</p>
  </div>

  <h2>Reviewed Medications</h2>
  <table>
    <thead>
      <tr><th>Name</th><th>Dose</th><th>Route</th><th>Frequency</th><th>Action</th></tr>
    </thead>
    <tbody>
"""
    raw_meds = reviewed_snapshot.get("medications", [])
    if isinstance(raw_meds, list):
        for m in raw_meds:
            if isinstance(m, dict):
                name = html.escape(str(m.get('name', '')))
                dose = html.escape(str(m.get('dose', '')))
                route = html.escape(str(m.get('route', '')))
                freq = html.escape(str(m.get('frequency', '')))
                act = html.escape(str(m.get('action', 'unspecified')))
                html_content += f"      <tr><td>{name}</td><td>{dose}</td><td>{route}</td><td>{freq}</td><td>{act}</td></tr>\n"

    html_content += """    </tbody>
  </table>

  <h2>Reviewed Vitals</h2>
  <table>
    <thead>
      <tr><th>Vital Type</th><th>Value</th><th>Unit</th></tr>
    </thead>
    <tbody>
"""
    raw_vitals = reviewed_snapshot.get("vitals", [])
    normalized_vitals = []
    if isinstance(raw_vitals, dict):
        for k, v in raw_vitals.items():
            normalized_vitals.append({"vital_type": k, "value": v, "unit": ""})
    elif isinstance(raw_vitals, list):
        normalized_vitals = raw_vitals

    for v in normalized_vitals:
        if isinstance(v, dict):
            v_type = html.escape(str(v.get("vital_type") or v.get("type") or ""))
            val = html.escape(str(v.get("value", "")))
            unit = html.escape(str(v.get("unit", "")))
            html_content += f"      <tr><td>{v_type}</td><td>{val}</td><td>{unit}</td></tr>\n"

    raw_body = rev.raw_text if rev else (note.raw_text if note else "")
    escaped_body = html.escape(raw_body or "")

    html_content += f"""    </tbody>
  </table>

  <h2>Source Text</h2>
  <pre>{escaped_body}</pre>
</body>
</html>
"""

    # Package files into ZIP archive with SHA-256 manifest
    zip_buffer = io.BytesIO()
    files_to_pack = {
        "reviewed_extraction.json": json.dumps(reviewed_snapshot, indent=2),
        "original_extraction.json": json.dumps(original_extracted, indent=2),
        "review_decisions.json": json.dumps({
            "event_id": ev.id,
            "derived_outcome": ev.derived_outcome,
            "item_decisions": item_decisions,
            "category_acknowledgments": category_ack,
            "review_duration_ms": ev.review_duration_ms,
        }, indent=2),
        "issue_dispositions.json": json.dumps(issue_disp, indent=2),
        "source_revision.json": json.dumps(source_meta, indent=2),
        "summary.html": html_content,
    }

    manifest = {}
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, fcontent in files_to_pack.items():
            encoded = fcontent.encode("utf-8")
            zf.writestr(fname, encoded)
            manifest[fname] = hashlib.sha256(encoded).hexdigest()

        # Add manifest.json itself
        zf.writestr("manifest.json", json.dumps(manifest, indent=2).encode("utf-8"))

    zip_buffer.seek(0)

    filename = f"reviewed_note_{ev.note_id}_{ev.id[:8]}.zip"
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )
