"""Database engine, migration gate and scoped session helpers.

Alembic is the single DDL authority. In local/test SQLite, the application
may apply the packaged migration to the same connection. Hosted/PostgreSQL
deployments must apply migrations as an explicit deployment step *before*
starting Flask; they never silently mutate production schemas on startup.
"""
import os

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from models import (  # noqa: F401 -- ensure ORM models are available to Alembic
    Base, Note, Extraction, Validation, Workspace, SourceAsset,
    AcquisitionRun, NoteRevision, ReviewEvent, OperationalIssue,
    IssueEvent, InferenceRun, Job,
)

REQUIRED_TABLES = frozenset((
    "notes", "extractions", "validations", "workspaces",
    "source_assets", "acquisition_runs", "note_revisions",
    "review_events", "operational_issues", "issue_events",
    "inference_runs", "jobs", "alembic_version",
))


def get_engine(database_url: str):
    kwargs = {}
    if database_url.startswith("postgresql"):
        # Production Supabase connections require TLS. For a disposable local
        # PostgreSQL test service, set DATABASE_SSLMODE=disable explicitly.
        kwargs["connect_args"] = {
            "sslmode": os.environ.get("DATABASE_SSLMODE", "require")
        }
    elif database_url.startswith("sqlite"):
        kwargs["connect_args"] = {
            "timeout": 30.0,
            "check_same_thread": False,
        }
    return create_engine(database_url, echo=False, **kwargs)


def init_db(engine, *, migrate: bool = True) -> None:
    """Apply local migrations, or verify a pre-migrated hosted schema.

    An Alembic failure is fatal: no create_all fallback, ignored exception or
    post-hoc unversioned import can make a failed migration appear successful.
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(backend_dir, "alembic.ini")
    if not os.path.isfile(config_path):
        raise RuntimeError("Required Alembic configuration was not found")

    cfg = AlembicConfig(config_path)
    expected_head = ScriptDirectory.from_config(cfg).get_current_head()
    if not expected_head:
        raise RuntimeError("No Alembic migration head configured")

    # Using this very same connection also handles sqlite:///:memory: tests.
    # Avoid inserting database passwords into ConfigParser (percent escapes).
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        if migrate:
            command.upgrade(cfg, "head")

        revision = MigrationContext.configure(connection).get_current_revision()
        if revision != expected_head:
            raise RuntimeError("Database revision is not at the expected migration head")

        available = set(inspect(connection).get_table_names())
        if not REQUIRED_TABLES.issubset(available):
            raise RuntimeError("Database is missing required migrated tables")


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
