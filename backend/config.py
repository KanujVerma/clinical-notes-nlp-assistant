import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_BASE)


class Config:
    PIPELINE_VERSION = "0.1.0"
    SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_sm")
    DB_PATH = os.path.join(_BASE, "app.db")
    DATA_DIR = os.path.join(_ROOT, "data")
    EVAL_RESULTS_PATH = os.path.join(_BASE, "evaluation", "results.json")
    SEED_SOURCES = ["dev", "showcase"]
