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
    # 1. Apply versioned schema migrations via Alembic if available
    try:
        import os
        from alembic.config import Config as AlembicConfig
        from alembic import command
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(backend_dir, "alembic.ini")
        if os.path.exists(ini_path):
            cfg = AlembicConfig(ini_path)
            raw_url = engine.url.render_as_string(hide_password=False) if hasattr(engine.url, "render_as_string") else str(engine.url)
            cfg.set_main_option("sqlalchemy.url", raw_url)
            command.upgrade(cfg, "head")
    except Exception as exc:
        import logging
        logging.getLogger("db").warning("Alembic upgrade failed: %s", exc)

    # Ensure all tables exist
    Base.metadata.create_all(engine)

    # 2. Baseline migration for legacy notes: synthesize NoteRevision for notes without current_source_revision_id
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
