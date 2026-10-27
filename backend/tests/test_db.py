from sqlalchemy import inspect
from utils.db import get_engine, init_db

def test_init_db_creates_tables(tmp_path):
    engine = get_engine("sqlite:///" + str(tmp_path / "test.db"))
    init_db(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "notes" in tables
    assert "extractions" in tables
    assert "validations" in tables

def test_note_has_session_id_column(tmp_path):
    from models.note import Note
    col_names = [c.key for c in Note.__table__.columns]
    assert "session_id" in col_names


def test_migration_preserves_populated_legacy_sqlite_database(tmp_path):
    import sqlite3
    from alembic.config import Config as AlembicConfig
    from alembic import command

    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY, raw_text TEXT, source TEXT, ocr_confidence REAL, status TEXT, created_at TEXT, session_id TEXT)"
    )
    conn.execute(
        "INSERT INTO notes VALUES (1, 'BP: 120/80', 'paste', 1.0, 'needs_review', '2026-01-01', 'legacy-session-001')"
    )
    conn.commit()
    conn.close()

    cfg = AlembicConfig("backend/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, raw_text, session_id FROM notes")
    row = cur.fetchone()
    assert row == (1, "BP: 120/80", "legacy-session-001")
    conn.close()
