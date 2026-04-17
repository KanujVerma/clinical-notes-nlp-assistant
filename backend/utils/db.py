from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, Session
from models.base import Base
import models.note  # noqa: F401
import models.extraction  # noqa: F401
import models.validation  # noqa: F401


def get_engine(database_url: str):
    kwargs = {}
    if database_url.startswith("postgresql"):
        # Supabase requires SSL; connect_args passes through to psycopg2
        kwargs["connect_args"] = {"sslmode": "require"}
    return create_engine(database_url, echo=False, **kwargs)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)

    # SQLite-only migration: add ocr_confidence column on existing DBs that
    # pre-date the column. Postgres gets the column via create_all above.
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            try:
                conn.execute(
                    text("ALTER TABLE notes ADD COLUMN ocr_confidence REAL")
                )
                conn.commit()
            except OperationalError:
                # Column already exists — safe to ignore.
                pass


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
