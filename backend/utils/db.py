from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from models.base import Base
import models.note  # noqa: F401
import models.extraction  # noqa: F401
import models.validation  # noqa: F401


def get_engine(db_path: str):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    # Alembic-free migration: add ocr_confidence column if missing on existing DBs.
    with engine.connect() as conn:
        try:
            conn.execute(
                text("ALTER TABLE notes ADD COLUMN ocr_confidence REAL")
            )
            conn.commit()
        except OperationalError:
            # Column already exists (duplicate column error) — safe to ignore.
            pass


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
