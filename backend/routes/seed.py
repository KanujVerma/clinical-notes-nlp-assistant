import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from config import Config
from utils.session import require_session

bp = Blueprint("seed", __name__)
_SEED_SOURCES = ["dev", "showcase"]  # eval notes are held out


def seed_notes(db_session, session_id: str) -> dict:
    from extractors.pipeline import run_pipeline
    loaded = 0
    skipped = 0
    for source_dir in _SEED_SOURCES:
        notes_dir = os.path.join(Config.DATA_DIR, source_dir, "notes")
        if not os.path.isdir(notes_dir):
            continue
        for fname in sorted(os.listdir(notes_dir)):
            if not fname.endswith(".txt"):
                continue
            # Idempotency scoped to this session
            existing = db_session.execute(
                select(Note).where(Note.filename == fname,
                                   Note.session_id == session_id)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            fpath = os.path.join(notes_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
            extracted = run_pipeline(text)
            note = Note(filename=fname, raw_text=text, source="demo",
                        session_id=session_id)
            db_session.add(note)
            db_session.flush()
            db_session.add(Extraction(
                note_id=note.id,
                extracted_json=json.dumps(extracted),
                pipeline_version=Config.PIPELINE_VERSION,
            ))
            loaded += 1
    db_session.commit()
    return {"loaded": loaded, "skipped": skipped}


@bp.post("/api/seed-demo")
def seed_demo():
    sid = require_session()
    result = seed_notes(g.db, sid)
    return jsonify(result)
