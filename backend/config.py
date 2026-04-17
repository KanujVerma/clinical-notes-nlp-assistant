import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_BASE)

_sqlite_fallback = f"sqlite:///{os.path.join(_BASE, 'app.db')}"


class Config:
    PIPELINE_VERSION = "0.1.0"
    SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_sm")
    # Production: set DATABASE_URL to a Postgres connection string.
    # Local dev: falls back to SQLite if DATABASE_URL is not set.
    DATABASE_URL = os.environ.get("DATABASE_URL", _sqlite_fallback)
    # Supabase/Render ship "postgres://" URLs; SQLAlchemy requires "postgresql://"
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "")  # e.g. https://your-app.vercel.app
    DATA_DIR = os.path.join(_ROOT, "data")
    EVAL_RESULTS_PATH = os.path.join(_BASE, "evaluation", "results.json")
    SEED_SOURCES = ["dev", "showcase"]
