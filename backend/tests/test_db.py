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
