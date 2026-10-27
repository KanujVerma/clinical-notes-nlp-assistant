import hashlib
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker, Session
from models import (  # noqa: F401
    Base,
    Note,
    Extraction,
    Validation,
    Workspace,
    SourceAsset,
    AcquisitionRun,
    NoteRevision,
    ReviewEvent,
    OperationalIssue,
    IssueEvent,
    InferenceRun,
    Job,
)


def get_engine(database_url: str):
    kwargs = {}
    if database_url.startswith("postgresql"):
        # Supabase requires SSL; connect_args passes through to psycopg2
        kwargs["connect_args"] = {"sslmode": "require"}
    return create_engine(database_url, echo=False, **kwargs)


def init_db(engine) -> None:
    # 1. Create all missing tables
    Base.metadata.create_all(engine)

    # 2. Add any missing columns to existing tables for backwards compatibility
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()

        if "notes" in tables:
            note_cols = {c["name"] for c in inspector.get_columns("notes")}
            missing_note_cols = [
                ("ocr_confidence", "REAL"),
                ("workspace_id", "VARCHAR(36)"),
                ("current_source_revision_id", "VARCHAR(36)"),
                ("current_extraction_id", "VARCHAR(36)"),
                ("review_head_event_id", "VARCHAR(36)"),
                ("lock_version", "INTEGER DEFAULT 0"),
                ("status", "VARCHAR(32) DEFAULT 'needs_review'"),
                ("updated_at", "TIMESTAMP"),
            ]
            for col_name, col_type in missing_note_cols:
                if col_name not in note_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE notes ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except (OperationalError, ProgrammingError, Exception):
                        pass

        if "extractions" in tables:
            ext_cols = {c["name"] for c in inspector.get_columns("extractions")}
            missing_ext_cols = [
                ("public_id", "VARCHAR(36)"),
                ("workspace_id", "VARCHAR(36)"),
                ("source_revision_id", "VARCHAR(36)"),
                ("source_text_hash", "VARCHAR(64)"),
                ("rules_hash", "VARCHAR(64)"),
                ("vocabulary_hash", "VARCHAR(64)"),
                ("schema_version", "VARCHAR(32) DEFAULT '2.0.0'"),
                ("status", "VARCHAR(32) DEFAULT 'completed'"),
                ("check_policy_version", "VARCHAR(32) DEFAULT '1.0.0'"),
                ("error_metadata_json", "TEXT"),
            ]
            for col_name, col_type in missing_ext_cols:
                if col_name not in ext_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE extractions ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except (OperationalError, ProgrammingError, Exception):
                        pass

    # 3. Baseline migration for legacy notes: synthesize NoteRevision for notes without current_source_revision_id
    with get_session(engine) as session:
        legacy_notes = session.query(Note).filter(Note.current_source_revision_id.is_(None)).all()
        for note in legacy_notes:
            raw = note.raw_text or ""
            text_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            rev = NoteRevision(
                note_id=note.id,
                workspace_id=note.workspace_id or note.session_id or "default-workspace",
                revision_number=1,
                raw_text=raw,
                normalized_text=raw,
                sha256=text_hash,
                creation_reason="acquisition",
            )
            session.add(rev)
            session.flush()

            note.current_source_revision_id = rev.id
            if not note.workspace_id:
                note.workspace_id = note.session_id or "default-workspace"

            # Check if an extraction exists for this note
            ext = session.query(Extraction).filter(Extraction.note_id == note.id).first()
            if ext:
                if not ext.public_id:
                    ext.public_id = str(ext.id)
                if not ext.workspace_id:
                    ext.workspace_id = note.workspace_id
                if not ext.source_revision_id:
                    ext.source_revision_id = rev.id
                if not ext.source_text_hash:
                    ext.source_text_hash = text_hash
                note.current_extraction_id = ext.public_id

            # Check if a validation exists for this note
            val = session.query(Validation).filter(Validation.note_id == note.id).first()
            if val:
                # Legacy validations are archived as legacy_unverified
                note.status = "legacy_unverified"
            elif not note.status:
                note.status = "needs_review"

        session.commit()


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
