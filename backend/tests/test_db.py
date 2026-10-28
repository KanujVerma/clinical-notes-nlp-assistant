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
        "INSERT INTO notes VALUES (1, 'BP: 120/80', 'paste', 1.0, 'needs_review', '2026-01-01 12:00:00', 'legacy-session-001')"
    )
    conn.commit()
    conn.close()

    cfg = AlembicConfig("backend/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, raw_text, session_id, created_at FROM notes")
    row = cur.fetchone()
    assert row == (1, "BP: 120/80", "legacy-session-001", "2026-01-01 12:00:00")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert "workspaces" in tables
    assert "note_revisions" in tables
    assert "review_events" in tables
    assert "alembic_version" in tables
    conn.close()

    # Now run init_db to test baseline synthesis of NoteRevision
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)
    inspector = inspect(engine)
    assert "note_revisions" in inspector.get_table_names()


def test_blank_database_migration_and_hosted_readiness(tmp_path):
    from alembic.config import Config as AlembicConfig
    from alembic import command
    from app import create_app
    from config import Config

    db_path = str(tmp_path / "blank_hosted.db")
    cfg = AlembicConfig("backend/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    app = create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{db_path}",
    })
    client = app.test_client()
    orig_mode = Config.APP_MODE
    try:
        Config.APP_MODE = "hosted_demo"
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200
        assert resp.json["status"] == "ready"
    finally:
        Config.APP_MODE = orig_mode


def test_init_db_then_alembic_upgrade_reconciliation(tmp_path):
    from alembic.config import Config as AlembicConfig
    from alembic import command

    db_path = str(tmp_path / "reconcile.db")
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    cfg = AlembicConfig("backend/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    # Upgrade should succeed idempotently even when create_all already ran
    command.upgrade(cfg, "head")
