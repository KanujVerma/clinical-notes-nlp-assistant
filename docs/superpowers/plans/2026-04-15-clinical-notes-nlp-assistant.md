# Clinical Notes NLP Assistant — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, deployable full-stack web app that extracts structured information from clinical notes using medSpaCy + regex, lets a reviewer correct the output, persists corrections in SQLite, and reports evaluation metrics on a labeled synthetic dataset.

**Architecture:** Flask backend (Python 3.11) with a modular NLP pipeline (medSpaCy + regex), SQLite via SQLAlchemy for persistence, and a Vite + React + TypeScript + Tailwind frontend. In dev, two processes (Flask :5000, Vite :5173 with proxy); in prod, Flask serves the built React bundle. Docker multi-stage build for single-container deployment.

**Tech Stack:** Python 3.11, Flask 3, SQLAlchemy 2, medSpaCy, spaCy (en_core_web_sm), PyMuPDF, React 18, Vite, TypeScript, Tailwind CSS 3, Recharts, react-router-dom v6, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-04-15-clinical-notes-nlp-assistant-design.md`

---

## Chunk 1: Project Scaffold

### Task 1: Create directory structure

**Files:**
- Create: `backend/` (with subdirs)
- Create: `frontend/` (Vite scaffold)
- Create: `data/dev/notes/`, `data/eval/notes/`, `data/eval/labels/`, `data/showcase/notes/`
- Create: `scripts/`, `docs/superpowers/plans/`

- [ ] **Step 1: Scaffold directories**

```bash
mkdir -p backend/{routes,extractors/patterns,models,evaluation,utils,tests}
mkdir -p data/{dev/notes,eval/notes,eval/labels,showcase/notes}
mkdir -p scripts
```

- [ ] **Step 2: Create frontend with Vite**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install react-router-dom recharts
npm install -D tailwindcss@3 postcss autoprefixer vitest @testing-library/react @testing-library/jest-dom jsdom
npx tailwindcss init -p
```

- [ ] **Step 3: Configure Tailwind** — edit `frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 4: Add Tailwind directives** — replace contents of `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 5: Configure Vite proxy** — edit `frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:5000', changeOrigin: true }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
  }
})
```

- [ ] **Step 6: Create Vitest setup** — create `frontend/src/test-setup.ts`:

```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 7: Add test script** — in `frontend/package.json` add to `"scripts"`:

```json
"test": "vitest run"
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: scaffold project directories and Vite frontend"
```

---

### Task 2: requirements.txt

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.0.3
flask-cors==4.0.1
sqlalchemy==2.0.30
medspacy==1.3.1
spacy==3.7.4
pymupdf==1.24.3
gunicorn==22.0.0
pytest==8.2.0
pytest-flask==1.3.0
```

- [ ] **Step 2: Install and download spaCy model**

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # run this before ALL subsequent python/pytest commands
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Expected: `Successfully installed` for all packages, `✔ Download and installation successful` for model.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Python requirements"
```

---

### Task 3: config.py

**Files:**
- Create: `backend/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import Config

def test_config_has_pipeline_version():
    assert isinstance(Config.PIPELINE_VERSION, str)
    assert len(Config.PIPELINE_VERSION) > 0

def test_config_spacy_model_default():
    assert Config.SPACY_MODEL == "en_core_web_sm"

def test_config_paths_are_absolute():
    assert os.path.isabs(Config.DB_PATH)
    assert os.path.isabs(Config.DATA_DIR)
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
python -m pytest backend/tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Implement config.py**

```python
# backend/config.py
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_BASE)


class Config:
    PIPELINE_VERSION = "0.1.0"
    SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_sm")
    DB_PATH = os.path.join(_BASE, "app.db")
    DATA_DIR = os.path.join(_ROOT, "data")
    EVAL_RESULTS_PATH = os.path.join(_BASE, "evaluation", "results.json")
```

- [ ] **Step 4: Run test — verify PASS**

```bash
python -m pytest backend/tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "feat: add Config with PIPELINE_VERSION, SPACY_MODEL, paths"
```

---

### Task 4: Database setup (SQLAlchemy)

**Files:**
- Create: `backend/utils/db.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/conftest.py
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.db import init_db, get_engine

@pytest.fixture
def engine(tmp_path):
    db_path = str(tmp_path / "test.db")
    engine = get_engine(db_path)
    init_db(engine)
    return engine
```

```python
# backend/tests/test_db.py
from sqlalchemy import inspect
from utils.db import get_engine, init_db

def test_init_db_creates_tables(tmp_path):
    engine = get_engine(str(tmp_path / "test.db"))
    init_db(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "notes" in tables
    assert "extractions" in tables
    assert "validations" in tables
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
python -m pytest backend/tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'utils.db'`

- [ ] **Step 3: Implement utils/db.py**

```python
# backend/utils/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models.base import Base
import models.note  # noqa: F401 — registers ORM classes
import models.extraction  # noqa: F401
import models.validation  # noqa: F401


def get_engine(db_path: str):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
```

- [ ] **Step 4: Create models/base.py**

```python
# backend/models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

- [ ] **Step 5: Create model stubs** (full implementation in Task 5)

```python
# backend/models/__init__.py
```

```python
# backend/models/note.py
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from models.base import Base

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # paste|txt|pdf|demo
    created_at = Column(DateTime, server_default=func.now())
```

```python
# backend/models/extraction.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from models.base import Base

class Extraction(Base):
    __tablename__ = "extractions"
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False)
    extracted_json = Column(Text, nullable=False)
    pipeline_version = Column(String, nullable=False)
    extracted_at = Column(DateTime, server_default=func.now())
```

```python
# backend/models/validation.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from models.base import Base

class Validation(Base):
    __tablename__ = "validations"
    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, unique=True)
    validated_json = Column(Text, nullable=False)
    status = Column(String, nullable=False)  # pending|accepted|corrected
    review_duration_ms = Column(Integer, nullable=True)
    correction_count = Column(Integer, nullable=False, default=0)
    validated_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 6: Run test — verify PASS**

```bash
python -m pytest backend/tests/test_db.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/utils/db.py backend/models/ backend/tests/
git commit -m "feat: add SQLAlchemy models (Note, Extraction, Validation) and db init"
```

---

### Task 5: Flask app factory

**Files:**
- Create: `backend/app.py`
- Test: `backend/tests/test_app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_app.py
import pytest
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_app.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Implement app.py**

```python
# backend/app.py
import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from utils.db import get_engine, init_db, get_session


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    CORS(app)

    # Config
    app.config["DB_PATH"] = Config.DB_PATH
    app.config["PIPELINE_VERSION"] = Config.PIPELINE_VERSION
    if test_config:
        app.config.update(test_config)

    # DB
    engine = get_engine(app.config["DB_PATH"])
    init_db(engine)
    app.config["ENGINE"] = engine

    # Session helper
    @app.before_request
    def open_session():
        from flask import g
        g.db = get_session(engine)

    @app.teardown_request
    def close_session(exc):
        from flask import g
        db = g.pop("db", None)
        if db:
            db.close()

    # Health
    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "pipeline_version": app.config["PIPELINE_VERSION"]})

    # Register blueprints (imported lazily to avoid circular imports)
    from routes.extract import bp as extract_bp
    from routes.notes import bp as notes_bp
    from routes.upload import bp as upload_bp
    from routes.validate import bp as validate_bp
    from routes.history import bp as history_bp
    from routes.metrics import bp as metrics_bp
    from routes.seed import bp as seed_bp

    app.register_blueprint(extract_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(validate_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(seed_bp)

    # SPA catch-all (prod)
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        static = app.static_folder
        if static and os.path.exists(os.path.join(static, path)):
            return send_from_directory(static, path)
        if static and os.path.exists(os.path.join(static, "index.html")):
            return send_from_directory(static, "index.html")
        return jsonify({"error": "Not found"}), 404

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
```

- [ ] **Step 4: Create empty route stubs** so imports don't fail

```python
# backend/routes/__init__.py
```

For each of: `extract.py`, `notes.py`, `upload.py`, `validate.py`, `history.py`, `metrics.py`, `seed.py` — create a stub:

```python
# backend/routes/extract.py  (repeat pattern for others)
from flask import Blueprint
bp = Blueprint("extract", __name__)
```

- [ ] **Step 5: Run — verify PASS**

```bash
python -m pytest backend/tests/test_app.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/routes/
git commit -m "feat: Flask app factory with health endpoint and blueprint stubs"
```

---

---

## Chunk 2: Extraction Pipeline — Preprocess, Sections, Vitals, Metadata

> **Note:** All `python -m pytest` commands assume `.venv` is activated (`source .venv/bin/activate`). Run pytest from the repo root unless stated otherwise.

### Task 6: Preprocessing (preprocess.py)

**Files:**
- Create: `backend/extractors/preprocess.py`
- Test: `backend/tests/test_preprocess.py`

The preprocessor collapses multiple blank lines, normalizes whitespace within lines, and returns both the cleaned text and a character-delta map so downstream spans can be remapped to raw_text offsets.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_preprocess.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.preprocess import preprocess

def test_collapses_blank_lines():
    raw = "Line one\n\n\n\nLine two"
    result = preprocess(raw)
    assert result.clean_text.count("\n\n\n") == 0

def test_preserves_content():
    raw = "BP: 120/80\nHR: 72"
    result = preprocess(raw)
    assert "BP: 120/80" in result.clean_text
    assert "HR: 72" in result.clean_text

def test_offset_map_is_list_of_tuples():
    raw = "Hello   world"
    result = preprocess(raw)
    assert isinstance(result.offset_map, list)
    assert all(isinstance(t, tuple) and len(t) == 2 for t in result.offset_map)

def test_remap_span_returns_raw_offset():
    raw = "A\n\n\nB"
    result = preprocess(raw)
    # 'B' is at offset 4 in raw; find it in clean and remap
    clean_idx = result.clean_text.index("B")
    raw_idx = result.remap(clean_idx)
    assert raw[raw_idx] == "B"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_preprocess.py -v
```

Expected: `ModuleNotFoundError: No module named 'extractors.preprocess'`

- [ ] **Step 3: Implement preprocess.py**

```python
# backend/extractors/preprocess.py
from dataclasses import dataclass


@dataclass
class PreprocessResult:
    clean_text: str
    raw_text: str
    offset_map: list[tuple[int, int]]  # (clean_pos, raw_pos) for each char in clean_text

    def remap(self, clean_pos: int) -> int:
        """Return the raw_text character offset for a clean_text position."""
        if clean_pos >= len(self.offset_map):
            return len(self.raw_text)
        return self.offset_map[clean_pos][1]

    def remap_span(self, clean_start: int, clean_end: int) -> tuple[int, int]:
        raw_start = self.remap(clean_start)
        if clean_end >= len(self.offset_map):
            raw_end = len(self.raw_text)
        else:
            raw_end = self.offset_map[clean_end][1]
        return raw_start, raw_end


def preprocess(raw_text: str) -> PreprocessResult:
    """
    Clean the text for NLP while building a character-level offset map
    from clean positions back to raw positions.
    """
    # Step 1: collapse 3+ consecutive newlines to 2
    # We build the mapping manually to track offsets.
    clean_chars: list[str] = []
    offset_map: list[tuple[int, int]] = []  # (clean_idx, raw_idx)

    raw_pos = 0
    while raw_pos < len(raw_text):
        ch = raw_text[raw_pos]
        # Count consecutive newlines
        if ch == "\n":
            newline_count = 0
            start = raw_pos
            while raw_pos < len(raw_text) and raw_text[raw_pos] == "\n":
                newline_count += 1
                raw_pos += 1
            # Emit at most 2 newlines
            emit = min(newline_count, 2)
            for i in range(emit):
                offset_map.append((len(clean_chars), start + i))
                clean_chars.append("\n")
        else:
            offset_map.append((len(clean_chars), raw_pos))
            clean_chars.append(ch)
            raw_pos += 1

    clean_text = "".join(clean_chars)

    # Step 2: strip trailing whitespace from each line (in-place on clean_chars)
    # Rebuild after newline normalization to keep offset_map valid — skip for now,
    # trailing space stripping is not offset-sensitive for span highlighting purposes.

    return PreprocessResult(
        clean_text=clean_text,
        raw_text=raw_text,
        offset_map=offset_map,
    )
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_preprocess.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractors/preprocess.py backend/tests/test_preprocess.py
git commit -m "feat: add preprocess module with clean_text and raw offset map"
```

---

### Task 7: Section detection (sections.py)

**Files:**
- Create: `backend/extractors/sections.py`
- Create: `backend/extractors/__init__.py`
- Test: `backend/tests/test_sections.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sections.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.sections import detect_sections

NOTE = """
DISCHARGE INSTRUCTIONS:
Take lisinopril 10mg daily.

FOLLOW UP:
See your doctor in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain worsens.
"""

def test_detects_discharge_section():
    sections = detect_sections(NOTE)
    assert any(s["category"] == "discharge_instructions" for s in sections)

def test_detects_follow_up_section():
    sections = detect_sections(NOTE)
    assert any(s["category"] == "follow_up" for s in sections)

def test_section_has_text():
    sections = detect_sections(NOTE)
    dis = next(s for s in sections if s["category"] == "discharge_instructions")
    assert "lisinopril" in dis["text"].lower() or len(dis["text"]) > 0

def test_no_sections_returns_empty():
    sections = detect_sections("This note has no headers.")
    assert isinstance(sections, list)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_sections.py -v
```

- [ ] **Step 3: Implement sections.py**

```python
# backend/extractors/sections.py
"""Section detection using regex header matching."""
import re
from typing import Any

# Section header patterns mapped to canonical category names
_SECTION_PATTERNS = [
    (r"discharge\s+instructions?", "discharge_instructions"),
    (r"follow[\s\-]?up", "follow_up"),
    (r"return\s+precautions?", "return_precautions"),
    (r"medications?(\s+list)?", "medications"),
    (r"assessment\s*/\s*plan|a\s*/\s*p", "assessment_plan"),
    (r"(assessment|plan)", "assessment_plan"),
    (r"history\s+of\s+present\s+illness|hpi", "hpi"),
    (r"(physical\s+exam|pe|examination)", "physical_exam"),
    (r"vital\s*signs?|vitals?", "vitals"),
    (r"(past\s+medical\s+history|pmh)", "pmh"),
    (r"(chief\s+complaint|cc)", "chief_complaint"),
]

_COMPILED = [
    (re.compile(rf"(?i)^[ \t]*{pat}[ \t]*:?[ \t]*$", re.MULTILINE), cat)
    for pat, cat in _SECTION_PATTERNS
]


def detect_sections(text: str) -> list[dict[str, Any]]:
    """
    Return a list of detected sections with keys:
        category, header, text, start (char offset in text), end (char offset).
    """
    hits: list[tuple[int, int, str, str]] = []  # (start, end, category, header)
    for pattern, category in _COMPILED:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), category, m.group().strip()))

    if not hits:
        return []

    # Sort by position
    hits.sort(key=lambda h: h[0])

    sections = []
    for i, (start, end, category, header) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        section_text = text[end:next_start].strip()
        sections.append({
            "category": category,
            "header": header,
            "text": section_text,
            "start": start,
            "end": next_start,
        })
    return sections
```

- [ ] **Step 4: Create `backend/extractors/__init__.py`** (empty)

- [ ] **Step 5: Run — verify PASS**

```bash
python -m pytest backend/tests/test_sections.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/extractors/__init__.py backend/extractors/sections.py backend/tests/test_sections.py
git commit -m "feat: add section detector with regex header matching"
```

---

### Task 8: Vitals extractor

**Files:**
- Create: `backend/extractors/vitals.py`
- Test: `backend/tests/test_vitals.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_vitals.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.vitals import extract_vitals

SIMPLE = "BP: 140/90. HR 78. Temp 98.6F. RR: 16. SpO2 98%. Wt 185 lbs."

def test_extracts_blood_pressure():
    v = extract_vitals(SIMPLE)
    assert v["blood_pressure"]["value"] == "140/90"

def test_extracts_heart_rate():
    v = extract_vitals(SIMPLE)
    assert v["heart_rate"]["value"] == "78"

def test_extracts_temperature():
    v = extract_vitals(SIMPLE)
    assert v["temperature"]["value"] == "98.6"

def test_extracts_respiratory_rate():
    v = extract_vitals(SIMPLE)
    assert v["respiratory_rate"]["value"] == "16"

def test_extracts_oxygen_saturation():
    v = extract_vitals(SIMPLE)
    assert v["oxygen_saturation"]["value"] == "98"

def test_extracts_weight():
    v = extract_vitals(SIMPLE)
    assert v["weight"]["value"] == "185"

def test_missing_vital_not_in_output():
    v = extract_vitals("No vitals here.")
    assert len(v) == 0

def test_confidence_is_float():
    v = extract_vitals(SIMPLE)
    for field in v.values():
        assert isinstance(field["confidence"], float)

def test_span_is_tuple():
    v = extract_vitals(SIMPLE)
    for field in v.values():
        assert isinstance(field["span"], list)
        assert len(field["span"]) == 2
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_vitals.py -v
```

- [ ] **Step 3: Implement vitals.py**

```python
# backend/extractors/vitals.py
import re
from typing import Any

# Each entry: (field_name, compiled_pattern, is_bp)
_PATTERNS: list[tuple[str, re.Pattern, bool]] = [
    (
        "blood_pressure",
        re.compile(r"(?i)(?:\bb\.?p\.?\b|blood\s+pressure)\s*:?\s*(\d{2,3})\s*/\s*(\d{2,3})"),
        True,
    ),
    (
        "heart_rate",
        re.compile(r"(?i)(?:\b(?:h\.?r\.?|pulse)\b|heart\s+rate)\s*:?\s*(\d{2,3})\s*(?:bpm)?"),
        False,
    ),
    (
        "temperature",
        re.compile(r"(?i)(?:\btemp(?:erature)?)\s*:?\s*(\d{2,3}(?:\.\d)?)\s*°?\s*[fc]?"),
        False,
    ),
    (
        "respiratory_rate",
        re.compile(r"(?i)(?:\b(?:r\.?r\.?|respirations?)\b|resp(?:iratory)?\s+rate)\s*:?\s*(\d{1,3})"),
        False,
    ),
    (
        "oxygen_saturation",
        re.compile(r"(?i)(?:\bspo2?\b|o2\s+sat(?:uration)?|oxygen\s+sat(?:uration)?)\s*:?\s*(\d{2,3})\s*%?"),
        False,
    ),
    (
        "weight",
        re.compile(r"(?i)(?:\bwt\.?\b|weight)\s*:?\s*(\d{2,4}(?:\.\d)?)\s*(?:lbs?|kg|pounds?|kilograms?)?"),
        False,
    ),
]


def extract_vitals(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, pattern, is_bp in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        value = f"{m.group(1)}/{m.group(2)}" if is_bp else m.group(1)
        results[name] = {
            "value": value,
            "span": [m.start(), m.end()],
            "source": "regex",
            "confidence": 1.0,
        }
    return results
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_vitals.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractors/vitals.py backend/tests/test_vitals.py
git commit -m "feat: add vitals extractor (BP, HR, temp, RR, SpO2, weight)"
```

---

### Task 9: Metadata extractor

**Files:**
- Create: `backend/extractors/metadata.py`
- Test: `backend/tests/test_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_metadata.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.metadata import extract_metadata

NOTE_WITH_META = """
Patient: John Doe
Date of Service: 2024-01-15
Provider: Dr. Jane Smith

Chief complaint: chest pain.
"""

def test_extracts_patient_name():
    m = extract_metadata(NOTE_WITH_META)
    assert m["patient_name"]["value"] == "John Doe"

def test_extracts_date_of_service():
    m = extract_metadata(NOTE_WITH_META)
    assert m["date_of_service"]["value"] == "2024-01-15"

def test_extracts_provider():
    m = extract_metadata(NOTE_WITH_META)
    assert "Smith" in m["provider_name"]["value"]

def test_no_metadata_returns_empty():
    m = extract_metadata("This note has no metadata headers.")
    assert len(m) == 0

def test_partial_metadata_ok():
    m = extract_metadata("Patient: Jane Doe\nNo other headers.")
    assert "patient_name" in m
    assert "date_of_service" not in m
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_metadata.py -v
```

- [ ] **Step 3: Implement metadata.py**

```python
# backend/extractors/metadata.py
import re
from typing import Any

_PATTERNS = [
    ("patient_name",   re.compile(r"(?i)patient\s*:\s*(.+)")),
    ("date_of_service", re.compile(r"(?i)(?:date\s+of\s+service|dos)\s*:\s*(\S+)")),
    ("provider_name",  re.compile(r"(?i)(?:provider|attending|physician)\s*:\s*(.+)")),
]


def extract_metadata(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for field, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            results[field] = {
                "value": m.group(1).strip(),
                "span": [m.start(), m.end()],
                "source": "regex",
                "confidence": 0.9,
            }
    return results
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_metadata.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractors/metadata.py backend/tests/test_metadata.py
git commit -m "feat: add metadata extractor (patient, DOS, provider)"
```

---

---

## Chunk 3: Extraction Pipeline — Medications, Instructions, Normalize, Orchestrator

### Task 10: Medications extractor

**Files:**
- Create: `backend/extractors/medications.py`
- Create: `backend/extractors/patterns/medications.json`
- Test: `backend/tests/test_medications.py`

**Context:** Uses medSpaCy `TargetMatcher` with a curated ~50-word prototype vocabulary, then regex sweeps around each match for dose/route/frequency. `ConText` handles negation. Framed in README as prototype — not a production drug-normalization system.

- [ ] **Step 1: Create medications vocabulary**

```json
// backend/extractors/patterns/medications.json
[
  "lisinopril", "metformin", "atorvastatin", "albuterol", "amoxicillin",
  "amlodipine", "omeprazole", "metoprolol", "losartan", "levothyroxine",
  "simvastatin", "hydrochlorothiazide", "gabapentin", "sertraline", "fluoxetine",
  "escitalopram", "pantoprazole", "prednisone", "tramadol", "ibuprofen",
  "acetaminophen", "aspirin", "warfarin", "clopidogrel", "furosemide",
  "spironolactone", "carvedilol", "bisoprolol", "enalapril", "ramipril",
  "ciprofloxacin", "azithromycin", "doxycycline", "trimethoprim", "cephalexin",
  "insulin", "glipizide", "glimepiride", "sitagliptin", "empagliflozin",
  "allopurinol", "colchicine", "hydroxychloroquine", "montelukast", "tiotropium",
  "fluticasone", "budesonide", "ipratropium", "salmeterol", "cetirizine"
]
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_medications.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.medications import extract_medications

NOTE_SIMPLE = "Patient takes lisinopril 10 mg PO daily for hypertension."
NOTE_NEGATED = "Patient is NOT taking metformin. Denies use of atorvastatin."
NOTE_MULTI = "Medications: albuterol 2.5 mg nebulized BID and omeprazole 20 mg PO QHS."

def test_extracts_medication_name():
    meds = extract_medications(NOTE_SIMPLE)
    assert len(meds) >= 1
    names = [m["name"] for m in meds]
    assert "lisinopril" in names

def test_extracts_dose():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["dose"] == "10 mg"

def test_extracts_route():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["route"].upper() == "PO"

def test_extracts_frequency():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["frequency"].lower() == "daily"

def test_negated_medication_excluded():
    meds = extract_medications(NOTE_NEGATED)
    names = [m["name"] for m in meds]
    assert "metformin" not in names
    assert "atorvastatin" not in names

def test_multiple_medications():
    meds = extract_medications(NOTE_MULTI)
    names = [m["name"] for m in meds]
    assert "albuterol" in names
    assert "omeprazole" in names

def test_returns_list():
    meds = extract_medications("No medications here.")
    assert isinstance(meds, list)
```

- [ ] **Step 3: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_medications.py -v
```

Expected: `ModuleNotFoundError: No module named 'extractors.medications'`

- [ ] **Step 4: Implement medications.py**

```python
# backend/extractors/medications.py
"""
Medication extraction using medSpaCy TargetMatcher + regex.
Prototype vocabulary — not a production drug-normalization system.
No RxNorm, no brand/generic resolution, no dose unit conversion.
"""
import re
import json
import os
from typing import Any

import spacy
import medspacy
from medspacy.target_matcher import TargetRule

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "patterns", "medications.json")
_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|mEq))", re.IGNORECASE)
_ROUTE_RE = re.compile(
    r"\b(PO|IV|IM|SQ|subq|subcutaneous|inhaled|inhalation|topical|sublingual|SL|PR|transdermal)\b",
    re.IGNORECASE,
)
_FREQ_RE = re.compile(
    r"\b(once\s+daily|twice\s+daily|BID|TID|QID|QHS|QAM|daily|q\.?d\.?|q\d+h|PRN|as\s+needed|at\s+bedtime|bedtime|weekly|monthly)\b",
    re.IGNORECASE,
)

_WINDOW = 60  # characters to scan around each medication match for dose/route/freq

# Module-level NLP pipeline (loaded once)
_nlp: spacy.language.Language | None = None


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is not None:
        return _nlp

    from config import Config
    try:
        nlp = medspacy.load(Config.SPACY_MODEL)
    except OSError:
        if Config.SPACY_MODEL == "en_core_web_sm":
            raise  # en_core_web_sm not installed — run: python -m spacy download en_core_web_sm
        import warnings
        warnings.warn(f"Model {Config.SPACY_MODEL!r} not found, falling back to en_core_web_sm")
        nlp = medspacy.load("en_core_web_sm")

    with open(_VOCAB_PATH) as f:
        vocab: list[str] = json.load(f)

    target_matcher = nlp.get_pipe("medspacy_target_matcher")
    rules = [TargetRule(name, "MEDICATION") for name in vocab]
    target_matcher.add(rules)

    _nlp = nlp
    return _nlp


def _scan_window(text: str, start: int, end: int) -> dict[str, str]:
    """Scan a character window around [start, end) for dose, route, frequency."""
    window_start = max(0, start - _WINDOW)
    window_end = min(len(text), end + _WINDOW)
    snippet = text[window_start:window_end]

    result: dict[str, str] = {}
    dm = _DOSE_RE.search(snippet)
    if dm:
        result["dose"] = dm.group(1).strip()
    rm = _ROUTE_RE.search(snippet)
    if rm:
        result["route"] = rm.group(1)
    fm = _FREQ_RE.search(snippet)
    if fm:
        result["frequency"] = fm.group(1)
    return result


def extract_medications(text: str) -> list[dict[str, Any]]:
    nlp = _get_nlp()
    doc = nlp(text)
    results: list[dict[str, Any]] = []

    for ent in doc.ents:
        if ent.label_ != "MEDICATION":
            continue
        # Skip negated mentions via medSpaCy ConText
        if ent._.is_negated:
            continue

        extra = _scan_window(text, ent.start_char, ent.end_char)
        med: dict[str, Any] = {
            "name": ent.text.lower(),
            "dose": extra.get("dose", ""),
            "route": extra.get("route", ""),
            "frequency": extra.get("frequency", ""),
            "span": [ent.start_char, ent.end_char],
            "source": "medspacy",
            "confidence": 0.9,
        }
        results.append(med)

    return results
```

- [ ] **Step 5: Run — verify PASS**

```bash
python -m pytest backend/tests/test_medications.py -v
```

Expected: 7 passed. (If negation test flickers due to ConText context window, pin window size — the negated pattern `"NOT taking metformin"` is 3 tokens left of the entity, well within ConText's default window.)

- [ ] **Step 6: Commit**

```bash
git add backend/extractors/medications.py backend/extractors/patterns/medications.json \
        backend/tests/test_medications.py
git commit -m "feat: add medication extractor (TargetMatcher + regex dose/route/freq)"
```

---

### Task 11: Instructions extractor (dual-path)

**Files:**
- Create: `backend/extractors/instructions.py`
- Test: `backend/tests/test_instructions.py`

**Context:** Primary = section-scoped (confidence 0.9). Fallback = sentence/keyword (confidence 0.6). Primary fills categories; fallback fills only what primary missed.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_instructions.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.instructions import extract_instructions
from extractors.sections import detect_sections

NOTE_SECTIONED = """
DISCHARGE INSTRUCTIONS:
Take medications as prescribed. Rest for 48 hours.

FOLLOW UP:
See Dr. Smith in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if fever exceeds 101 F or chest pain worsens.
"""

NOTE_NO_SECTIONS = """
Patient should follow up in 2 weeks with their PCP.
Return to ER if shortness of breath develops.
Call the clinic if pain is not improving.
"""

def test_primary_path_discharge():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "discharge_instructions" in result
    assert result["discharge_instructions"]["source"] == "section"
    assert result["discharge_instructions"]["confidence"] == 0.9

def test_primary_path_follow_up():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "follow_up" in result
    assert "smith" in result["follow_up"]["value"].lower()

def test_primary_path_return_precautions():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "return_precautions" in result
    assert result["return_precautions"]["source"] == "section"

def test_fallback_path_follow_up():
    result = extract_instructions(NOTE_NO_SECTIONS, [])
    assert "follow_up" in result
    assert result["follow_up"]["source"] == "fallback"
    assert result["follow_up"]["confidence"] == 0.6

def test_fallback_path_return():
    result = extract_instructions(NOTE_NO_SECTIONS, [])
    assert "return_precautions" in result

def test_returns_dict():
    result = extract_instructions("No instructions here.", [])
    assert isinstance(result, dict)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_instructions.py -v
```

- [ ] **Step 3: Implement instructions.py**

```python
# backend/extractors/instructions.py
import re
from typing import Any

_CATEGORIES = ["discharge_instructions", "follow_up", "return_precautions"]

# Keyword triggers for the fallback sentence-level path
_FALLBACK_TRIGGERS: dict[str, list[re.Pattern]] = {
    "follow_up": [
        re.compile(r"(?i)\bfollow[\s\-]?up\b"),
        re.compile(r"(?i)\bsee\s+(dr\.?|your\s+doctor|pcp)\b"),
        re.compile(r"(?i)\breturn\s+to\s+(clinic|office|pcp)\b"),
    ],
    "return_precautions": [
        re.compile(r"(?i)\breturn\s+to\s+(er|emergency|hospital)\b"),
        re.compile(r"(?i)\bcall\s+(if|when|the)\b"),
        re.compile(r"(?i)\bif\s+(you\s+)?(develop|experience|notice|have)\b"),
        re.compile(r"(?i)\bseek\s+(medical|immediate|emergency)\b"),
    ],
    "discharge_instructions": [
        re.compile(r"(?i)\btake\s+your\s+(medication|medicine)\b"),
        re.compile(r"(?i)\brest\s+for\b"),
        re.compile(r"(?i)\bavoid\s+(activity|lifting|exercise)\b"),
        re.compile(r"(?i)\bdo\s+not\b"),
    ],
}


def _sentence_split(text: str) -> list[tuple[str, int, int]]:
    """Naive sentence splitter. Returns (sentence, start, end) triples."""
    sentences = []
    pattern = re.compile(r"(?<=[.!?])\s+")
    last = 0
    for m in pattern.finditer(text):
        sent = text[last:m.start()].strip()
        if sent:
            sentences.append((sent, last, m.start()))
        last = m.end()
    remaining = text[last:].strip()
    if remaining:
        sentences.append((remaining, last, len(text)))
    return sentences


def extract_instructions(
    text: str,
    sections: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    # --- Primary: section-scoped ---
    for section in sections:
        cat = section["category"]
        if cat in _CATEGORIES and cat not in result:
            result[cat] = {
                "value": section["text"],
                "span": [section["start"], section["end"]],
                "source": "section",
                "confidence": 0.9,
            }

    # --- Fallback: sentence/keyword (fills only missing categories) ---
    missing = [c for c in _CATEGORIES if c not in result]
    if not missing:
        return result

    for sent, start, end in _sentence_split(text):
        for cat in list(missing):
            for trigger in _FALLBACK_TRIGGERS[cat]:
                if trigger.search(sent):
                    result[cat] = {
                        "value": sent,
                        "span": [start, end],
                        "source": "fallback",
                        "confidence": 0.6,
                    }
                    missing.remove(cat)
                    break
        if not missing:
            break

    return result
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_instructions.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractors/instructions.py backend/tests/test_instructions.py
git commit -m "feat: add instructions extractor (section-scoped primary + keyword fallback)"
```

---

### Task 12: Normalize output

**Files:**
- Create: `backend/extractors/normalize.py`
- Test: `backend/tests/test_normalize.py`

Produces the canonical JSON structure that the API returns and the DB stores.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_normalize.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.normalize import normalize_output

RAW_VITALS = {
    "blood_pressure": {"value": "140/90", "span": [10, 20], "source": "regex", "confidence": 1.0},
}
RAW_MEDS = [{"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily",
              "span": [30, 40], "source": "medspacy", "confidence": 0.9}]
RAW_INSTR = {
    "follow_up": {"value": "See Dr. Smith in 2 weeks.", "span": [50, 75], "source": "section", "confidence": 0.9}
}
RAW_META = {"patient_name": {"value": "John Doe", "span": [0, 8], "source": "regex", "confidence": 0.9}}

def test_output_has_required_keys():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert "pipeline_version" in out
    assert "vitals" in out
    assert "medications" in out
    assert "instructions" in out
    assert "metadata" in out

def test_pipeline_version_stamped():
    out = normalize_output("0.2.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert out["pipeline_version"] == "0.2.0"

def test_vitals_preserved():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert out["vitals"]["blood_pressure"]["value"] == "140/90"

def test_medications_list():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert isinstance(out["medications"], list)
    assert out["medications"][0]["name"] == "lisinopril"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_normalize.py -v
```

- [ ] **Step 3: Implement normalize.py**

```python
# backend/extractors/normalize.py
from typing import Any


def normalize_output(
    pipeline_version: str,
    vitals: dict[str, Any],
    medications: list[dict[str, Any]],
    instructions: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the canonical extraction JSON."""
    return {
        "pipeline_version": pipeline_version,
        "vitals": vitals,
        "medications": medications,
        "instructions": instructions,
        "metadata": metadata,
    }
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_normalize.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/extractors/normalize.py backend/tests/test_normalize.py
git commit -m "feat: add normalize module for canonical extraction JSON"
```

---

### Task 13: Pipeline orchestrator

**Files:**
- Create: `backend/extractors/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

The orchestrator wires all extractors together: preprocess → sections → [vitals, medications, instructions, metadata] → normalize. Remaps all spans from clean offsets to raw offsets before returning.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pipeline.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.pipeline import run_pipeline

NOTE = """Patient: Jane Doe
Date of Service: 2024-03-10



Vitals: BP 132/84. HR: 80. Temp 98.4F. RR 14. SpO2: 97%. Wt 160 lbs.

Medications:
- lisinopril 10 mg PO daily
- metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take all medications as prescribed. Avoid strenuous activity for 1 week.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain, shortness of breath, or fever > 101F.
"""

def test_pipeline_returns_dict():
    out = run_pipeline(NOTE)
    assert isinstance(out, dict)

def test_pipeline_has_version():
    out = run_pipeline(NOTE)
    assert "pipeline_version" in out

def test_pipeline_extracts_bp():
    out = run_pipeline(NOTE)
    assert "blood_pressure" in out["vitals"]

def test_pipeline_extracts_medications():
    out = run_pipeline(NOTE)
    names = [m["name"] for m in out["medications"]]
    assert "lisinopril" in names

def test_pipeline_extracts_follow_up():
    out = run_pipeline(NOTE)
    assert "follow_up" in out["instructions"]

def test_pipeline_extracts_metadata():
    out = run_pipeline(NOTE)
    assert "patient_name" in out["metadata"]

def test_spans_are_raw_offsets():
    out = run_pipeline(NOTE)
    bp = out["vitals"]["blood_pressure"]
    start, end = bp["span"]
    # The value should appear in the raw note at [start, end)
    assert "132" in NOTE[start:end] or "84" in NOTE[start:end]
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_pipeline.py -v
```

- [ ] **Step 3: Implement pipeline.py**

```python
# backend/extractors/pipeline.py
from typing import Any

from config import Config
from extractors.preprocess import preprocess
from extractors.sections import detect_sections
from extractors.vitals import extract_vitals
from extractors.medications import extract_medications
from extractors.instructions import extract_instructions
from extractors.metadata import extract_metadata
from extractors.normalize import normalize_output


def _remap_field(field: dict[str, Any], pr) -> dict[str, Any]:
    """Replace clean-text span with raw-text span in a field dict."""
    if "span" in field and isinstance(field["span"], (list, tuple)):
        s, e = field["span"]
        field = dict(field)
        field["span"] = list(pr.remap_span(s, e))
    return field


def run_pipeline(raw_text: str) -> dict[str, Any]:
    # 1. Preprocess
    pr = preprocess(raw_text)
    clean = pr.clean_text

    # 2. Section detection (operates on clean text)
    sections = detect_sections(clean)

    # 3. Parallel extraction on clean text
    vitals_raw = extract_vitals(clean)
    meds_raw = extract_medications(clean)
    instr_raw = extract_instructions(clean, sections)
    meta_raw = extract_metadata(clean)

    # 4. Remap all spans from clean → raw offsets
    vitals = {k: _remap_field(v, pr) for k, v in vitals_raw.items()}
    medications = [_remap_field(m, pr) for m in meds_raw]
    instructions = {k: _remap_field(v, pr) for k, v in instr_raw.items()}
    metadata = {k: _remap_field(v, pr) for k, v in meta_raw.items()}

    # 5. Normalize and stamp version
    return normalize_output(Config.PIPELINE_VERSION, vitals, medications, instructions, metadata)
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_pipeline.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run full backend test suite**

```bash
python -m pytest backend/tests/ -v
```

Expected: all tests from Tasks 3–13 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/extractors/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrator (preprocess → sections → extract → remap spans)"
```

---

---

## Chunk 4: Flask API Routes

### Task 14: POST /extract (ephemeral dry-run)

**Files:**
- Modify: `backend/routes/extract.py`
- Test: `backend/tests/test_routes_extract.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_routes_extract.py
import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_extract_returns_200(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    assert resp.status_code == 200

def test_extract_returns_pipeline_version(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    data = resp.get_json()
    assert "pipeline_version" in data

def test_extract_returns_vitals(client):
    resp = client.post("/api/extract", json={"text": "BP: 120/80. HR: 72."})
    data = resp.get_json()
    assert "vitals" in data
    assert "blood_pressure" in data["vitals"]

def test_extract_missing_text_returns_400(client):
    resp = client.post("/api/extract", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()

def test_extract_no_db_write(client, tmp_path):
    """POST /extract must not persist anything to the DB."""
    client.post("/api/extract", json={"text": "BP: 120/80."})
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    conn.close()
    assert count == 0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_routes_extract.py -v
```

Expected: 404 on POST /api/extract (stub has no routes).

- [ ] **Step 3: Implement routes/extract.py**

```python
# backend/routes/extract.py
from flask import Blueprint, request, jsonify
from extractors.pipeline import run_pipeline

bp = Blueprint("extract", __name__)


@bp.post("/api/extract")
def extract():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400
    result = run_pipeline(text)
    return jsonify(result)
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_routes_extract.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/routes/extract.py backend/tests/test_routes_extract.py
git commit -m "feat: POST /api/extract — ephemeral pipeline dry-run"
```

---

### Task 15: POST /notes (persist pasted text)

**Files:**
- Modify: `backend/routes/notes.py`
- Test: `backend/tests/test_routes_notes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_routes_notes.py
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_notes_returns_note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    assert resp.status_code == 201
    data = resp.get_json()
    assert "note_id" in data
    assert isinstance(data["note_id"], int)

def test_notes_returns_extracted_json(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    data = resp.get_json()
    assert "extracted_json" in data
    assert "pipeline_version" in data["extracted_json"]

def test_notes_persists_to_db(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    note_id = resp.get_json()["note_id"]
    resp2 = client.get(f"/api/history/{note_id}")
    assert resp2.status_code == 200

def test_notes_missing_text_returns_400(client):
    resp = client.post("/api/notes", json={})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_routes_notes.py -v
```

- [ ] **Step 3: Implement routes/notes.py**

```python
# backend/routes/notes.py
import json
from flask import Blueprint, request, jsonify, g
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from config import Config

bp = Blueprint("notes", __name__)


@bp.post("/api/notes")
def create_note():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400

    extracted = run_pipeline(text)

    note = Note(raw_text=text, source="paste")
    g.db.add(note)
    g.db.flush()  # assigns note.id

    extraction = Extraction(
        note_id=note.id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note.id, "extracted_json": extracted}), 201
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_routes_notes.py -v
```

Expected: 4 passed (test_notes_persists_to_db requires history route from Task 17 — skip it for now if needed; add `@pytest.mark.skip` and come back after Task 17).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/notes.py backend/tests/test_routes_notes.py
git commit -m "feat: POST /api/notes — persist pasted text and extraction"
```

---

### Task 16: POST /upload (txt + PDF)

**Files:**
- Modify: `backend/routes/upload.py`
- Create: `backend/utils/pdf.py`
- Test: `backend/tests/test_routes_upload.py`

- [ ] **Step 1: Implement utils/pdf.py**

```python
# backend/utils/pdf.py
import fitz  # PyMuPDF

_MIN_TEXT_LEN = 50


def extract_text_from_pdf(filepath: str) -> str:
    doc = fitz.open(filepath)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    if len(text.strip()) < _MIN_TEXT_LEN:
        raise ValueError("PDF appears to be image-only (no embedded text layer). OCR is not supported.")
    return text
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_routes_upload.py
import sys, os, io, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_upload_txt_returns_note_id(client):
    content = b"BP: 120/80. HR: 72. Patient takes lisinopril 10 mg PO daily."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert "note_id" in resp.get_json()

def test_upload_returns_extracted_json(client):
    content = b"BP: 130/85. HR: 68."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert "extracted_json" in body
    assert "vitals" in body["extracted_json"]

def test_upload_no_file_returns_400(client):
    resp = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400

def test_upload_unsupported_extension_returns_400(client):
    data = {"file": (io.BytesIO(b"hello"), "note.doc", "application/msword")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "UNSUPPORTED_FILE_TYPE"
```

- [ ] **Step 3: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_routes_upload.py -v
```

- [ ] **Step 4: Implement routes/upload.py**

```python
# backend/routes/upload.py
import json, os, tempfile
from flask import Blueprint, request, jsonify, g
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from utils.pdf import extract_text_from_pdf
from config import Config

bp = Blueprint("upload", __name__)
_ALLOWED = {".txt", ".pdf"}


@bp.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided", "code": "NO_FILE"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in _ALLOWED:
        return jsonify({"error": f"Unsupported file type: {ext}", "code": "UNSUPPORTED_FILE_TYPE"}), 400

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            f.save(tmp.name)
            try:
                text = extract_text_from_pdf(tmp.name)
            except ValueError as e:
                return jsonify({"error": str(e), "code": "EMPTY_PDF_TEXT"}), 400
            finally:
                os.unlink(tmp.name)
        source = "pdf"
    else:
        text = f.read().decode("utf-8", errors="replace")
        source = "txt"

    extracted = run_pipeline(text)

    note = Note(filename=f.filename, raw_text=text, source=source)
    g.db.add(note)
    g.db.flush()

    extraction = Extraction(
        note_id=note.id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note.id, "extracted_json": extracted}), 201
```

- [ ] **Step 5: Run — verify PASS**

```bash
python -m pytest backend/tests/test_routes_upload.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/upload.py backend/utils/pdf.py backend/tests/test_routes_upload.py
git commit -m "feat: POST /api/upload — txt and PDF upload with PyMuPDF extraction"
```

---

### Task 17: GET /history and GET /history/<id>

**Files:**
- Modify: `backend/routes/history.py`
- Test: `backend/tests/test_routes_history.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_routes_history.py
import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

@pytest.fixture
def seeded_client(client):
    """Create one note via the API so there's something to query."""
    client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    return client

def test_history_returns_list(seeded_client):
    resp = seeded_client.get("/api/history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "notes" in data
    assert isinstance(data["notes"], list)
    assert len(data["notes"]) == 1

def test_history_note_has_required_fields(seeded_client):
    resp = seeded_client.get("/api/history")
    note = resp.get_json()["notes"][0]
    for field in ["id", "filename", "source", "created_at", "status", "correction_count"]:
        assert field in note

def test_history_detail_returns_full_record(seeded_client):
    list_resp = seeded_client.get("/api/history")
    note_id = list_resp.get_json()["notes"][0]["id"]
    resp = seeded_client.get(f"/api/history/{note_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "raw_text" in data
    assert "extracted_json" in data

def test_history_detail_404_for_missing(client):
    resp = client.get("/api/history/9999")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_routes_history.py -v
```

- [ ] **Step 3: Implement routes/history.py**

```python
# backend/routes/history.py
import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select, desc
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation

bp = Blueprint("history", __name__)


@bp.get("/api/history")
def list_history():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page

    notes = g.db.execute(
        select(Note).order_by(desc(Note.created_at)).limit(per_page).offset(offset)
    ).scalars().all()

    result = []
    for note in notes:
        val = g.db.execute(
            select(Validation).where(Validation.note_id == note.id)
        ).scalar_one_or_none()
        result.append({
            "id": note.id,
            "filename": note.filename,
            "source": note.source,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "status": val.status if val else "pending",
            "correction_count": val.correction_count if val else 0,
        })

    return jsonify({"notes": result, "page": page, "per_page": per_page})


@bp.get("/api/history/<int:note_id>")
def get_history_detail(note_id: int):
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    extraction = g.db.execute(
        select(Extraction).where(Extraction.note_id == note_id)
    ).scalar_one_or_none()

    validation = g.db.execute(
        select(Validation).where(Validation.note_id == note_id)
    ).scalar_one_or_none()

    return jsonify({
        "id": note.id,
        "filename": note.filename,
        "raw_text": note.raw_text,
        "source": note.source,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "extracted_json": json.loads(extraction.extracted_json) if extraction else None,
        "pipeline_version": extraction.pipeline_version if extraction else None,
        "validation": {
            "status": validation.status,
            "validated_json": json.loads(validation.validated_json),
            "correction_count": validation.correction_count,
            "review_duration_ms": validation.review_duration_ms,
        } if validation else None,
    })
```

- [ ] **Step 4: Run — verify PASS**

```bash
python -m pytest backend/tests/test_routes_history.py backend/tests/test_routes_notes.py -v
```

Expected: all pass (including the previously skipped `test_notes_persists_to_db`).

- [ ] **Step 5: Commit**

```bash
git add backend/routes/history.py backend/tests/test_routes_history.py
git commit -m "feat: GET /api/history and GET /api/history/<id>"
```

---

### Task 18: POST /validate, GET /metrics, POST /seed-demo

**Files:**
- Modify: `backend/routes/validate.py`, `backend/routes/metrics.py`, `backend/routes/seed.py`
- Create: `backend/utils/corrections.py`
- Test: `backend/tests/test_routes_validate.py`

- [ ] **Step 1: Implement correction counter**

```python
# backend/utils/corrections.py
"""
Compute correction_count between extracted and validated JSON.

Rules:
- Vitals/metadata/instructions: compare `.value` of each field dict (trimmed string).
  +1 per changed/added/removed field. Does NOT compare span/source/confidence.
- Medications: match by name (only), then check if any visible field changed.
  +1 per added, removed, or changed item. No sub-field breakdown within an item.
"""
from typing import Any


def _get_value(field_data: Any) -> str:
    """Extract the .value string from a field dict, or stringify the whole thing."""
    if isinstance(field_data, dict):
        return str(field_data.get("value", "")).strip()
    return str(field_data).strip()


def _leaf_diff(extracted: dict, validated: dict) -> int:
    """Compare two section dicts (e.g. vitals, instructions, metadata) by .value only."""
    count = 0
    all_keys = set(extracted) | set(validated)
    for key in all_keys:
        if key not in extracted:
            count += 1  # field added by reviewer
        elif key not in validated:
            count += 1  # field removed by reviewer
        else:
            if _get_value(extracted[key]) != _get_value(validated[key]):
                count += 1
    return count


def _med_name_key(med: dict) -> str:
    """Match medications by name only — dose changes are corrections, not new items."""
    return med.get("name", "").lower().strip()


def compute_correction_count(extracted: dict[str, Any], validated: dict[str, Any]) -> int:
    count = 0

    # Scalar sections: compare .value of each field
    for section in ("vitals", "instructions", "metadata"):
        ext_sec = extracted.get(section, {})
        val_sec = validated.get(section, {})
        if isinstance(ext_sec, dict) and isinstance(val_sec, dict):
            count += _leaf_diff(ext_sec, val_sec)

    # Medications: match by name, count adds/removes/changes as +1 each
    ext_meds = {_med_name_key(m): m for m in (extracted.get("medications") or [])}
    val_meds = {_med_name_key(m): m for m in (validated.get("medications") or [])}
    all_keys = set(ext_meds) | set(val_meds)
    for k in all_keys:
        if k not in ext_meds or k not in val_meds:
            count += 1  # added or removed
        else:
            # Check if any visible field changed (excluding span/source/confidence)
            e, v = ext_meds[k], val_meds[k]
            for field in ("name", "dose", "route", "frequency"):
                if e.get(field, "").strip() != v.get(field, "").strip():
                    count += 1
                    break

    return count
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_routes_validate.py
import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app
from utils.corrections import compute_correction_count

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

@pytest.fixture
def note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."})
    return resp.get_json()["note_id"]

def test_validate_returns_200(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 5000,
    })
    assert resp.status_code == 200

def test_validate_upserts(client, note_id):
    payload = {
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 3000,
    }
    client.post("/api/validate", json=payload)
    payload["status"] = "corrected"
    resp = client.post("/api/validate", json=payload)
    assert resp.status_code == 200
    # Should be one validation row, not two
    detail = client.get(f"/api/history/{note_id}").get_json()
    assert detail["validation"]["status"] == "corrected"

def test_correction_count_computed():
    ext = {"vitals": {"blood_pressure": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"blood_pressure": {"value": "130/85"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_validate_missing_note_id_returns_400(client):
    resp = client.post("/api/validate", json={"status": "accepted"})
    assert resp.status_code == 400

def test_validate_nonexistent_note_returns_404(client):
    resp = client.post("/api/validate", json={
        "note_id": 9999,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    })
    assert resp.status_code == 404

def test_metrics_null_eval_when_no_results_file(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "eval" in data
    assert data["eval"] is None
    assert "db_stats" in data
```

- [ ] **Step 3: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_routes_validate.py -v
```

- [ ] **Step 4: Implement routes/validate.py**

```python
# backend/routes/validate.py
import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.corrections import compute_correction_count

bp = Blueprint("validate", __name__)


@bp.post("/api/validate")
def validate():
    body = request.get_json(silent=True) or {}
    note_id = body.get("note_id")
    validated_json = body.get("validated_json")
    status = body.get("status")
    if not note_id or validated_json is None or not status:
        return jsonify({"error": "note_id, validated_json, and status are required", "code": "MISSING_FIELDS"}), 400

    # Verify note exists
    if not g.db.get(Note, note_id):
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404

    # Compute correction_count vs latest extraction
    extraction = g.db.execute(
        select(Extraction).where(Extraction.note_id == note_id)
    ).scalar_one_or_none()
    extracted = json.loads(extraction.extracted_json) if extraction else {}
    correction_count = compute_correction_count(extracted, validated_json)

    # Upsert (one validation row per note)
    existing = g.db.execute(
        select(Validation).where(Validation.note_id == note_id)
    ).scalar_one_or_none()

    if existing:
        existing.validated_json = json.dumps(validated_json)
        existing.status = status
        existing.review_duration_ms = body.get("review_duration_ms")
        existing.correction_count = correction_count
    else:
        val = Validation(
            note_id=note_id,
            validated_json=json.dumps(validated_json),
            status=status,
            review_duration_ms=body.get("review_duration_ms"),
            correction_count=correction_count,
        )
        g.db.add(val)

    g.db.commit()
    return jsonify({"ok": True, "correction_count": correction_count})
```

- [ ] **Step 5: Implement routes/metrics.py**

```python
# backend/routes/metrics.py
import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select, func
from models.validation import Validation
from config import Config

bp = Blueprint("metrics", __name__)


@bp.get("/api/metrics")
def metrics():
    # Load eval results (may not exist yet)
    eval_data = None
    if os.path.exists(Config.EVAL_RESULTS_PATH):
        with open(Config.EVAL_RESULTS_PATH) as f:
            eval_data = json.load(f)

    # DB-based correction stats
    rows = g.db.execute(
        select(
            Validation.status,
            func.count().label("count"),
            func.avg(Validation.correction_count).label("avg_corrections"),
            func.avg(Validation.review_duration_ms).label("avg_review_ms"),
        ).group_by(Validation.status)
    ).all()

    db_stats = {
        "by_status": [
            {"status": r.status, "count": r.count,
             "avg_corrections": round(r.avg_corrections or 0, 2),
             "avg_review_ms": round(r.avg_review_ms or 0)}
            for r in rows
        ]
    }

    return jsonify({"eval": eval_data, "db_stats": db_stats})
```

- [ ] **Step 6: Implement routes/seed.py**

```python
# backend/routes/seed.py
import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from config import Config

bp = Blueprint("seed", __name__)
_SEED_SOURCES = ["dev", "showcase"]  # eval notes are held out


def seed_notes(db_session) -> dict:
    loaded = 0
    skipped = 0
    for source_dir in _SEED_SOURCES:
        notes_dir = os.path.join(Config.DATA_DIR, source_dir, "notes")
        if not os.path.isdir(notes_dir):
            continue
        for fname in sorted(os.listdir(notes_dir)):
            if not fname.endswith(".txt"):
                continue
            # Idempotent: skip if filename already in DB
            existing = db_session.execute(
                select(Note).where(Note.filename == fname)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            fpath = os.path.join(notes_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
            extracted = run_pipeline(text)
            note = Note(filename=fname, raw_text=text, source="demo")
            db_session.add(note)
            db_session.flush()
            db_session.add(Extraction(
                note_id=note.id,
                extracted_json=json.dumps(extracted),
                pipeline_version=Config.PIPELINE_VERSION,
            ))
            loaded += 1
    db_session.commit()
    return {"loaded": loaded, "skipped": skipped}


@bp.post("/api/seed-demo")
def seed_demo():
    result = seed_notes(g.db)
    return jsonify(result)
```

- [ ] **Step 7: Run — verify PASS**

```bash
python -m pytest backend/tests/test_routes_validate.py -v
```

Expected: 5 passed.

- [ ] **Step 8: Run full backend test suite**

```bash
python -m pytest backend/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/routes/validate.py backend/routes/metrics.py backend/routes/seed.py \
        backend/utils/corrections.py backend/tests/test_routes_validate.py
git commit -m "feat: POST /api/validate, GET /api/metrics, POST /api/seed-demo"
```

---

---

## Chunk 5: Synthetic Data

### Task 19: Dev note generator (50 programmatic notes)

**Files:**
- Create: `scripts/generate_dev_notes.py`
- Creates: `data/dev/notes/dev_001.txt` … `dev_050.txt`

- [ ] **Step 1: Implement generator**

```python
#!/usr/bin/env python3
# scripts/generate_dev_notes.py
"""
Generate 50 synthetic clinical notes for dev/demo use.
All data is entirely synthetic — no real patient information.
"""
import os, random
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).parent.parent / "data" / "dev" / "notes"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NAMES = ["John Smith", "Maria Garcia", "James Lee", "Sarah Johnson", "Robert Brown",
         "Emily Davis", "Michael Wilson", "Jennifer Taylor", "William Anderson", "Lisa Martinez"]
PROVIDERS = ["Dr. Alice Chen", "Dr. Robert Evans", "Dr. Priya Patel", "Dr. Mark Torres"]
MEDS = [
    ("lisinopril", ["5 mg", "10 mg", "20 mg"], "PO", "daily"),
    ("metformin", ["500 mg", "1000 mg"], "PO", "BID"),
    ("atorvastatin", ["10 mg", "20 mg", "40 mg"], "PO", "daily"),
    ("albuterol", ["2.5 mg", "90 mcg"], "inhaled", "PRN"),
    ("omeprazole", ["20 mg", "40 mg"], "PO", "QHS"),
    ("amoxicillin", ["500 mg", "875 mg"], "PO", "TID"),
    ("amlodipine", ["5 mg", "10 mg"], "PO", "daily"),
    ("metoprolol", ["25 mg", "50 mg"], "PO", "BID"),
    ("sertraline", ["50 mg", "100 mg"], "PO", "daily"),
    ("gabapentin", ["300 mg", "600 mg"], "PO", "TID"),
]
NOTE_TYPES = ["discharge", "followup", "progress"]
HEADER_STYLES = {
    "discharge_instructions": ["DISCHARGE INSTRUCTIONS:", "Discharge Instructions:", "DISCHARGE INSTRUCTIONS", "D/C Instructions:"],
    "follow_up": ["FOLLOW UP:", "Follow-Up:", "FOLLOW-UP:", "Follow Up Instructions:"],
    "return_precautions": ["RETURN PRECAUTIONS:", "Return Precautions:", "PRECAUTIONS:"],
}
FOLLOW_UPS = [
    "Follow up with PCP in {days} weeks.",
    "Return to clinic in {days} days.",
    "See Dr. {provider_last} in {days} weeks for re-evaluation.",
]
RETURN_PREC = [
    "Return to ED if fever > 101.5F, chest pain, or shortness of breath.",
    "Call the clinic if symptoms worsen or if you develop new symptoms.",
    "Go to the ER immediately if you experience severe chest pain or difficulty breathing.",
]
DISCHARGE_INSTRS = [
    "Take all medications as prescribed. Rest and avoid strenuous activity for {days} days.",
    "Follow a low-sodium diet. Take medications with food. Avoid alcohol.",
    "Continue current medications. Monitor blood pressure daily. Record readings.",
]

def random_bp():
    systolic = random.randint(110, 160)
    diastolic = random.randint(65, 95)
    return f"{systolic}/{diastolic}"

def random_vitals(style="labeled"):
    bp = random_bp()
    hr = random.randint(58, 105)
    temp = round(random.uniform(97.4, 99.2), 1)
    rr = random.randint(12, 20)
    spo2 = random.randint(94, 100)
    wt = random.randint(120, 240)
    if style == "labeled":
        return (f"BP: {bp}. HR: {hr} bpm. Temp: {temp}F. RR: {rr}. "
                f"SpO2: {spo2}%. Wt: {wt} lbs.")
    elif style == "abbreviated":
        return f"BP {bp} HR {hr} T {temp} RR {rr} O2 {spo2}% Wt {wt}#"
    else:
        return (f"Blood pressure {bp} mmHg, heart rate {hr} beats/min, "
                f"temperature {temp} degrees F, respirations {rr}/min, "
                f"oxygen saturation {spo2}% on room air, weight {wt} lbs.")

def random_meds(count=None):
    n = count or random.randint(1, 4)
    chosen = random.sample(MEDS, min(n, len(MEDS)))
    lines = []
    for name, doses, route, freq in chosen:
        dose = random.choice(doses)
        lines.append(f"- {name} {dose} {route} {freq}")
    return "\n".join(lines)

def random_negation():
    if random.random() < 0.3:
        neg_med = random.choice(MEDS)[0]
        return f"\nPatient denies use of {neg_med}. Not currently taking {neg_med}.\n"
    return ""

def make_note(i: int) -> str:
    note_type = random.choice(NOTE_TYPES)
    name = random.choice(NAMES)
    provider = random.choice(PROVIDERS)
    provider_last = provider.split()[-1]
    days = random.randint(1, 4) * 7
    vitals_style = random.choice(["labeled", "abbreviated", "prose"])
    dis_hdr = random.choice(HEADER_STYLES["discharge_instructions"])
    fu_hdr = random.choice(HEADER_STYLES["follow_up"])
    rp_hdr = random.choice(HEADER_STYLES["return_precautions"])

    header = f"Patient: {name}\nDate of Service: 2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}\nProvider: {provider}\n\n"
    vitals_section = f"Vitals:\n{random_vitals(vitals_style)}\n\n"
    meds_section = f"Medications:\n{random_meds()}{random_negation()}\n"

    if note_type == "discharge":
        body = (
            f"{dis_hdr}\n"
            f"{random.choice(DISCHARGE_INSTRS).format(days=days // 7)}\n\n"
            f"{fu_hdr}\n"
            f"{random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n\n"
            f"{rp_hdr}\n"
            f"{random.choice(RETURN_PREC)}\n"
        )
    elif note_type == "followup":
        body = (
            f"Patient presents for follow-up. Doing well overall.\n\n"
            f"{fu_hdr}\n"
            f"{random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n\n"
            f"{rp_hdr}\n"
            f"{random.choice(RETURN_PREC)}\n"
        )
    else:
        body = (
            f"Brief progress note. Patient stable.\n\n"
            f"Plan: Continue current management. {random.choice(FOLLOW_UPS).format(days=days // 7, provider_last=provider_last)}\n"
        )

    return header + vitals_section + meds_section + "\n" + body

if __name__ == "__main__":
    for i in range(1, 51):
        note = make_note(i)
        path = OUT_DIR / f"dev_{i:03d}.txt"
        path.write_text(note, encoding="utf-8")
    print(f"Generated 50 notes in {OUT_DIR}")
```

- [ ] **Step 2: Run generator**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
python scripts/generate_dev_notes.py
```

Expected: `Generated 50 notes in .../data/dev/notes`

- [ ] **Step 3: Verify output**

```bash
ls data/dev/notes/ | wc -l  # should print 50
head data/dev/notes/dev_001.txt
```

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_dev_notes.py data/dev/
git commit -m "feat: generate 50 synthetic dev notes"
```

---

### Task 20: Hand-written evaluation notes (20 notes + ground-truth labels)

**Files:**
- Create: `data/eval/notes/eval_001.txt` … `eval_020.txt`
- Create: `data/eval/labels/eval_001.json` … `eval_020.json`

Each eval note is written with deliberate variation the generator does not replicate. The corresponding label file is the ground truth used by `run_evaluation.py`.

**Note on authoring approach:** Create each note as a Python write call for reproducibility. Run the block below as a script.

- [ ] **Step 1: Create eval note author script**

```python
#!/usr/bin/env python3
# scripts/create_eval_data.py
"""Write 20 hand-crafted eval notes and their ground-truth labels."""
import json
from pathlib import Path

NOTES_DIR = Path(__file__).parent.parent / "data" / "eval" / "notes"
LABELS_DIR = Path(__file__).parent.parent / "data" / "eval" / "labels"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
LABELS_DIR.mkdir(parents=True, exist_ok=True)

EVAL_DATA = [
  # (filename, note_text, label_dict)
  ("eval_001", """Patient: Alice Morgan
Date of Service: 2024-02-14
Provider: Dr. Samuel Reyes

VITALS: BP 138/88. HR 82 bpm. Temp 98.8F. RR: 16. SpO2 97%. Wt 172 lbs.

MEDICATIONS:
lisinopril 10 mg PO daily
metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take medications as prescribed. Follow a low-sodium diet.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if BP exceeds 180/110 or chest pain develops.""",
  {
    "vitals": {"blood_pressure": "138/88", "heart_rate": "82", "temperature": "98.8",
               "respiratory_rate": "16", "oxygen_saturation": "97", "weight": "172 lbs"},
    "medications": [
      {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
      {"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Take medications as prescribed. Follow a low-sodium diet.",
      "follow_up": "Return to clinic in 2 weeks.",
      "return_precautions": "Return to ER if BP exceeds 180/110 or chest pain develops.",
    },
    "metadata": {"patient_name": "Alice Morgan", "date_of_service": "2024-02-14", "provider_name": "Dr. Samuel Reyes"},
  }),
  ("eval_002", """Patient: Brian Cho
DOS: 2024-03-05
Attending: Dr. Lisa Pham

vitals: b/p 155/95, hr: 90, temp 99.1, rr 18, o2 sat 96%, wt 198#

meds: atorvastatin 20mg po daily, amlodipine 5 mg oral qd

d/c instructions: low fat diet, exercise 30 min 3x/wk.

f/u: see dr pham in 4 wks.

precautions: call if chest tightness or leg swelling.""",
  {
    "vitals": {"blood_pressure": "155/95", "heart_rate": "90", "temperature": "99.1",
               "respiratory_rate": "18", "oxygen_saturation": "96", "weight": "198 lbs"},
    "medications": [
      {"name": "atorvastatin", "dose": "20 mg", "route": "PO", "frequency": "daily"},
      {"name": "amlodipine", "dose": "5 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "low fat diet, exercise 30 min 3x/wk.",
      "follow_up": "see dr pham in 4 wks.",
      "return_precautions": "call if chest tightness or leg swelling.",
    },
    "metadata": {"patient_name": "Brian Cho", "date_of_service": "2024-03-05", "provider_name": "Dr. Lisa Pham"},
  }),
  ("eval_003", """62-year-old male presenting for hypertension follow-up.

Vital Signs: Blood pressure 148/92 mmHg, heart rate 76 beats/min,
temperature 98.2 degrees F, respirations 14/min, O2 sat 99% on RA, weight 185 lbs.

Current medications include metoprolol 50 mg twice daily by mouth and
lisinopril 20mg orally once daily. Patient denies use of any NSAIDs.

Plan: follow up in 6 weeks. Return to ER if severe headache or vision changes.""",
  {
    "vitals": {"blood_pressure": "148/92", "heart_rate": "76", "temperature": "98.2",
               "respiratory_rate": "14", "oxygen_saturation": "99", "weight": "185 lbs"},
    "medications": [
      {"name": "metoprolol", "dose": "50 mg", "route": "PO", "frequency": "BID"},
      {"name": "lisinopril", "dose": "20 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "follow up in 6 weeks.",
      "return_precautions": "Return to ER if severe headache or vision changes.",
    },
    "metadata": {},
  }),
  ("eval_004", """Patient: Carol Diaz
Date of Service: 2024-04-01
Provider: Dr. James Okafor

V/S: BP 122/78 HR 68 T 97.9 RR 12 SpO2 100% Wt 145 lbs

Rx: omeprazole 40mg PO QHS; sertraline 100mg PO daily

DISCHARGE INSTRUCTIONS: Take omeprazole 30 min before breakfast. Continue sertraline as directed. Avoid caffeine and spicy foods.

FOLLOW UP: Follow up with gastroenterology in 3 weeks.

RETURN PRECAUTIONS: Return if vomiting blood or severe abdominal pain.""",
  {
    "vitals": {"blood_pressure": "122/78", "heart_rate": "68", "temperature": "97.9",
               "respiratory_rate": "12", "oxygen_saturation": "100", "weight": "145 lbs"},
    "medications": [
      {"name": "omeprazole", "dose": "40 mg", "route": "PO", "frequency": "QHS"},
      {"name": "sertraline", "dose": "100 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Take omeprazole 30 min before breakfast. Continue sertraline as directed. Avoid caffeine and spicy foods.",
      "follow_up": "Follow up with gastroenterology in 3 weeks.",
      "return_precautions": "Return if vomiting blood or severe abdominal pain.",
    },
    "metadata": {"patient_name": "Carol Diaz", "date_of_service": "2024-04-01", "provider_name": "Dr. James Okafor"},
  }),
  ("eval_005", """SHORT PROGRESS NOTE

Patient stable. No acute distress.
BP: 130/80. Pulse 72. Temp 98.4. RR 14. Sat 98% RA.

Meds: albuterol 2.5 mg nebulized PRN, fluticasone 110 mcg inhaled BID.
Patient NOT on oral steroids. Denies use of beta blockers.

Follow patient in 1 month. Call clinic if wheezing worsens.""",
  {
    "vitals": {"blood_pressure": "130/80", "heart_rate": "72", "temperature": "98.4",
               "respiratory_rate": "14", "oxygen_saturation": "98"},
    "medications": [
      {"name": "albuterol", "dose": "2.5 mg", "route": "inhaled", "frequency": "PRN"},
      {"name": "fluticasone", "dose": "110 mcg", "route": "inhaled", "frequency": "BID"},
    ],
    "instructions": {
      "follow_up": "Follow patient in 1 month.",
      "return_precautions": "Call clinic if wheezing worsens.",
    },
    "metadata": {},
  }),
  ("eval_006", """Patient: Edward Park
DOS: 2024-05-12
Provider: Dr. Nina Russo

VITALS
BP 142/88 | HR 88 bpm | Temp 98.6°F | RR 16 | O2 Sat 97% | Wt 210 lbs

MEDICATIONS
- gabapentin 300 mg PO TID
- amoxicillin 875 mg PO BID x 7 days

DISCHARGE INSTRUCTIONS
Take gabapentin with food to minimize nausea. Complete full course of amoxicillin.

FOLLOW UP
Return to neurology in 4 weeks.

RETURN PRECAUTIONS
Return to ED if seizure activity, severe dizziness, or inability to walk.""",
  {
    "vitals": {"blood_pressure": "142/88", "heart_rate": "88", "temperature": "98.6",
               "respiratory_rate": "16", "oxygen_saturation": "97", "weight": "210 lbs"},
    "medications": [
      {"name": "gabapentin", "dose": "300 mg", "route": "PO", "frequency": "TID"},
      {"name": "amoxicillin", "dose": "875 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Take gabapentin with food to minimize nausea. Complete full course of amoxicillin.",
      "follow_up": "Return to neurology in 4 weeks.",
      "return_precautions": "Return to ED if seizure activity, severe dizziness, or inability to walk.",
    },
    "metadata": {"patient_name": "Edward Park", "date_of_service": "2024-05-12", "provider_name": "Dr. Nina Russo"},
  }),
  ("eval_007", """Follow-Up Visit

Pt: Fiona Wells  Date: 2024-06-18  MD: Dr. Carl Wong

Assessment: Stable chronic hypertension, well-controlled.

VS: BP 128/76. HR 64. Temp 98.2F. RR 13. SpO2 99%. Wt 158 lbs.

Active medications: losartan 50mg PO daily, hydrochlorothiazide 25mg PO daily.

No medication changes today.
RTC in 3 months or sooner if BP > 160/100.""",
  {
    "vitals": {"blood_pressure": "128/76", "heart_rate": "64", "temperature": "98.2",
               "respiratory_rate": "13", "oxygen_saturation": "99", "weight": "158 lbs"},
    "medications": [
      {"name": "losartan", "dose": "50 mg", "route": "PO", "frequency": "daily"},
      {"name": "hydrochlorothiazide", "dose": "25 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "RTC in 3 months or sooner if BP > 160/100.",
    },
    "metadata": {"patient_name": "Fiona Wells", "date_of_service": "2024-06-18", "provider_name": "Dr. Carl Wong"},
  }),
  ("eval_008", """DISCHARGE SUMMARY

Name: George Hill     Admit Date: 2024-07-02     Discharge Date: 2024-07-04
Attending: Dr. Yara Solis

Discharge Vitals: bp 118/74, heart rate 72, temperature 98.4F, resp rate 16, O2 sat 98 percent, wt 195 lbs.

Discharge Medications:
furosemide 40 mg oral once daily
spironolactone 25 mg PO daily
carvedilol 12.5 mg PO BID

Discharge Instructions:
Weigh yourself daily. If weight increases by more than 3 lbs in a day or 5 lbs in a week, call the clinic immediately. Fluid restriction to 1.5L/day.

Follow-Up:
Cardiology follow-up in 1 week.

Return Precautions:
Return to ED for shortness of breath at rest, leg swelling, or weight gain > 3 lbs/day.""",
  {
    "vitals": {"blood_pressure": "118/74", "heart_rate": "72", "temperature": "98.4",
               "respiratory_rate": "16", "oxygen_saturation": "98", "weight": "195 lbs"},
    "medications": [
      {"name": "furosemide", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "spironolactone", "dose": "25 mg", "route": "PO", "frequency": "daily"},
      {"name": "carvedilol", "dose": "12.5 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Weigh yourself daily. If weight increases by more than 3 lbs in a day or 5 lbs in a week, call the clinic immediately. Fluid restriction to 1.5L/day.",
      "follow_up": "Cardiology follow-up in 1 week.",
      "return_precautions": "Return to ED for shortness of breath at rest, leg swelling, or weight gain > 3 lbs/day.",
    },
    "metadata": {"patient_name": "George Hill", "provider_name": "Dr. Yara Solis"},  # date_of_service omitted: note uses Admit/Discharge Date headers, not DOS
  }),
  ("eval_009", """PATIENT: Helen Grant
Date of Service: 08/15/2024
CLINICIAN: Dr. Paulo Mendes

Vitals this visit: BP was 165/100, HR = 95, T 99.0 degrees, RR = 20, SpO2 = 95%, weight = 220 lbs.

Patient is on the following:
escitalopram 10 mg po qd
amlodipine 10mg once daily by mouth

Patient denies taking any blood thinners. Not on aspirin.

Instructions given:
Continue medications. Reduce salt intake.

Return to see me in 2 weeks.
Call immediately if BP is above 180 or you feel confused.""",
  {
    "vitals": {"blood_pressure": "165/100", "heart_rate": "95", "temperature": "99.0",
               "respiratory_rate": "20", "oxygen_saturation": "95", "weight": "220 lbs"},
    "medications": [
      {"name": "escitalopram", "dose": "10 mg", "route": "PO", "frequency": "daily"},
      {"name": "amlodipine", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue medications. Reduce salt intake.",
      "follow_up": "Return to see me in 2 weeks.",
      "return_precautions": "Call immediately if BP is above 180 or you feel confused.",
    },
    "metadata": {"patient_name": "Helen Grant", "date_of_service": "08/15/2024", "provider_name": "Dr. Paulo Mendes"},
  }),
  ("eval_010", """Follow up note - Ian Russo

Seen today for diabetes management. A1c improved.

Vitals today - 126/80 HR 70 Temp 98.0 RR 13 O2 100% weight: 190 pounds

medications: metformin 1000mg po bid, glipizide 5 mg oral once daily

No changes to medication list.
Continue current plan.
RTC in 3 months for repeat labs.
Go to ER immediately if blood sugar < 60 or > 400.""",
  {
    "vitals": {"blood_pressure": "126/80", "heart_rate": "70", "temperature": "98.0",
               "respiratory_rate": "13", "oxygen_saturation": "100", "weight": "190 lbs"},
    "medications": [
      {"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"},
      {"name": "glipizide", "dose": "5 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "RTC in 3 months for repeat labs.",
      "return_precautions": "Go to ER immediately if blood sugar < 60 or > 400.",
    },
    "metadata": {},  # no structured headers; patient name is in prose, not extractable
  }),
  ("eval_011", """Patient: Julia Kim   DOS: 2024-09-03   MD: Dr. Anne Foster

subjective: patient feels well, no complaints.

objective:
BP: 119/76, Pulse: 66, Temperature: 97.8, Resp: 12, O2 Sat: 100%, Wt: 132 lbs

assessment & plan:
Continue pantoprazole 40mg PO daily and cetirizine 10mg PO daily.
Return for annual exam in 12 months.
No urgent concerns at this time.""",
  {
    "vitals": {"blood_pressure": "119/76", "heart_rate": "66", "temperature": "97.8",
               "respiratory_rate": "12", "oxygen_saturation": "100", "weight": "132 lbs"},
    "medications": [
      {"name": "pantoprazole", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "cetirizine", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "follow_up": "Return for annual exam in 12 months.",
    },
    "metadata": {"patient_name": "Julia Kim", "date_of_service": "2024-09-03", "provider_name": "Dr. Anne Foster"},
  }),
  ("eval_012", """EMERGENCY DEPARTMENT DISCHARGE NOTE

Patient: Kevin Nash
Date: 10/20/2024

Discharge VS: blood pressure 135/85 mmHg | heart rate 88 | temp 99.5F | resp 18 | sat 96% | weight not recorded

Rx at Discharge:
ciprofloxacin 500 mg oral BID x 5 days
ibuprofen 400 mg PO TID PRN pain

DISCHARGE INSTRUCTIONS: Take ciprofloxacin with food and water. Complete the full course. Ibuprofen for pain as needed, not to exceed 1200 mg/day. Avoid if stomach upset.

FOLLOW UP: Follow up with your primary care doctor in 3-5 days.

RETURN TO ED IF: fever worsens, unable to keep fluids down, or symptoms not improving in 48 hours.""",
  {
    "vitals": {"blood_pressure": "135/85", "heart_rate": "88", "temperature": "99.5",
               "respiratory_rate": "18", "oxygen_saturation": "96"},
    "medications": [
      {"name": "ciprofloxacin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
      {"name": "ibuprofen", "dose": "400 mg", "route": "PO", "frequency": "TID"},
    ],
    "instructions": {
      "discharge_instructions": "Take ciprofloxacin with food and water. Complete the full course. Ibuprofen for pain as needed, not to exceed 1200 mg/day. Avoid if stomach upset.",
      "follow_up": "Follow up with your primary care doctor in 3-5 days.",
      "return_precautions": "fever worsens, unable to keep fluids down, or symptoms not improving in 48 hours.",
    },
    "metadata": {"patient_name": "Kevin Nash", "date_of_service": "10/20/2024"},
  }),
  ("eval_013", """Name: Laura Chen       Provider: Dr. Raj Kapoor      Visit: 2024-11-01

Quick visit for routine refills.

Vitals: 124/78, 74 bpm, 98.4°F, 14 breaths/min, 99% O2, 155 lb.

Continuing levothyroxine 75 mcg PO daily and simvastatin 40mg by mouth at bedtime.
Patient reports compliance. No new complaints.

Plan: refills provided, labs in 6 months, return PRN.""",
  {
    "vitals": {"blood_pressure": "124/78", "heart_rate": "74", "temperature": "98.4",
               "respiratory_rate": "14", "oxygen_saturation": "99", "weight": "155 lbs"},
    "medications": [
      {"name": "levothyroxine", "dose": "75 mcg", "route": "PO", "frequency": "daily"},
      {"name": "simvastatin", "dose": "40 mg", "route": "PO", "frequency": "QHS"},  # "at bedtime" maps to QHS
    ],
    "instructions": {
      "follow_up": "refills provided, labs in 6 months, return PRN.",
    },
    "metadata": {"patient_name": "Laura Chen", "date_of_service": "2024-11-01", "provider_name": "Dr. Raj Kapoor"},
  }),
  ("eval_014", """Discharge paperwork

Mike Torres
11/15/2024
Discharge attending: Dr. Sasha Bell

Vitals on discharge: bp 145/90, HR 82, T 99.0F, breathing 16x/min, sats 95%, wt 230lbs.

Discharge Medications:
1. metformin 500mg orally twice daily with meals
2. enalapril 5mg once daily PO
3. aspirin 81 mg oral daily

INSTRUCTIONS: Continue metformin with meals. Take enalapril in the morning. Aspirin daily for heart protection. Monitor blood sugars at home.

Follow up with primary care in 2 weeks. Cardiology referral placed.

Call 911 or go to nearest ER for chest pain, trouble breathing, or sudden weakness.""",
  {
    "vitals": {"blood_pressure": "145/90", "heart_rate": "82", "temperature": "99.0",
               "respiratory_rate": "16", "oxygen_saturation": "95", "weight": "230 lbs"},
    "medications": [
      {"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
      {"name": "enalapril", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "aspirin", "dose": "81 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue metformin with meals. Take enalapril in the morning. Aspirin daily for heart protection. Monitor blood sugars at home.",
      "follow_up": "Follow up with primary care in 2 weeks. Cardiology referral placed.",
      "return_precautions": "Call 911 or go to nearest ER for chest pain, trouble breathing, or sudden weakness.",
    },
    "metadata": {"patient_name": "Mike Torres", "date_of_service": "11/15/2024", "provider_name": "Dr. Sasha Bell"},
  }),
  ("eval_015", """Patient: Nancy Rivera
Date of visit: December 2, 2024
Treating physician: Dr. Omar Farouk

Vitals: BP 110/68. HR 58. Temp 97.5 F. RR 11. O2 sat 100%. Weight 118 lbs.

On allopurinol 300 mg PO daily and colchicine 0.6 mg PO daily for gout management.
Not taking any OTC pain medications at this time.

Discharge plan:
Stay well hydrated. Avoid high-purine foods (red meat, shellfish, beer).

See Dr. Farouk in 4 weeks.

Come to ER if sudden severe joint pain, fever, or confusion.""",
  {
    "vitals": {"blood_pressure": "110/68", "heart_rate": "58", "temperature": "97.5",
               "respiratory_rate": "11", "oxygen_saturation": "100", "weight": "118 lbs"},
    "medications": [
      {"name": "allopurinol", "dose": "300 mg", "route": "PO", "frequency": "daily"},
      {"name": "colchicine", "dose": "0.6 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Stay well hydrated. Avoid high-purine foods (red meat, shellfish, beer).",
      "follow_up": "See Dr. Farouk in 4 weeks.",
      "return_precautions": "Come to ER if sudden severe joint pain, fever, or confusion.",
    },
    "metadata": {"patient_name": "Nancy Rivera", "date_of_service": "December 2, 2024", "provider_name": "Dr. Omar Farouk"},
  }),
  ("eval_016", """2024-12-10
Patient: Oscar Bell
Seen by: Dr. Tina Shore

Vitals: 132/82 / 78 / 98.6 / 15 / 97% / 176lbs

MEDS: warfarin 5mg po qd, furosemide 20mg oral daily.
Patient denies missing any doses. INR therapeutic.

DISCHARGE INSTRUCTIONS: Continue warfarin daily. No grapefruit. Avoid alcohol. Soft diet.

FOLLOW UP: INR check and clinic visit in 1 week.

RETURN: Call if bleeding gums, blood in urine, or bruising increases.""",
  {
    "vitals": {"blood_pressure": "132/82", "heart_rate": "78", "temperature": "98.6",
               "respiratory_rate": "15", "oxygen_saturation": "97", "weight": "176 lbs"},
    "medications": [
      {"name": "warfarin", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "furosemide", "dose": "20 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "Continue warfarin daily. No grapefruit. Avoid alcohol. Soft diet.",
      "follow_up": "INR check and clinic visit in 1 week.",
      "return_precautions": "Call if bleeding gums, blood in urine, or bruising increases.",
    },
    "metadata": {"patient_name": "Oscar Bell", "date_of_service": "2024-12-10", "provider_name": "Dr. Tina Shore"},
  }),
  ("eval_017", """Patient name: Priya Sharma
Date: January 5, 2025
Physician: Dr. Lin Zhao

Vitals: Bp 120/75 Pulse: 68 Temp: 98.1F RR 13 O2 Sat 100% Wt 142lbs

Plan: add ramipril 5mg daily for microalbuminuria. Continue existing metformin 1000 mg PO BID.

patient to return in 1 month for repeat urine microalbumin.
ER if sudden swelling of face or throat (angioedema).""",
  {
    "vitals": {"blood_pressure": "120/75", "heart_rate": "68", "temperature": "98.1",
               "respiratory_rate": "13", "oxygen_saturation": "100", "weight": "142 lbs"},
    "medications": [
      {"name": "ramipril", "dose": "5 mg", "route": "PO", "frequency": "daily"},
      {"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "follow_up": "patient to return in 1 month for repeat urine microalbumin.",
      "return_precautions": "ER if sudden swelling of face or throat (angioedema).",
    },
    "metadata": {"patient_name": "Priya Sharma", "date_of_service": "January 5, 2025", "provider_name": "Dr. Lin Zhao"},
  }),
  ("eval_018", """CLINIC NOTE — BRIEF

Pt: Quinn Adams     Date: 02/12/2025     Provider: Dr. Sam Patel

V/S: 136/86 / 84 / 99.1 / 18 / 95% / 215 lbs

On doxycycline 100mg oral bid and montelukast 10mg PO qd.
Pt declines prednisone at this time.

Instructions: take doxycycline with full glass of water, avoid lying down for 30 min. Stay out of direct sunlight.

F/U: return in 3 weeks or sooner if rash appears.

Return to ED: if difficulty breathing, throat tightness, or severe skin reaction.""",
  {
    "vitals": {"blood_pressure": "136/86", "heart_rate": "84", "temperature": "99.1",
               "respiratory_rate": "18", "oxygen_saturation": "95", "weight": "215 lbs"},
    "medications": [
      {"name": "doxycycline", "dose": "100 mg", "route": "PO", "frequency": "BID"},
      {"name": "montelukast", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    ],
    "instructions": {
      "discharge_instructions": "take doxycycline with full glass of water, avoid lying down for 30 min. Stay out of direct sunlight.",
      "follow_up": "return in 3 weeks or sooner if rash appears.",
      "return_precautions": "if difficulty breathing, throat tightness, or severe skin reaction.",
    },
    "metadata": {"patient_name": "Quinn Adams", "date_of_service": "02/12/2025", "provider_name": "Dr. Sam Patel"},
  }),
  ("eval_019", """Encounter date 3/1/2025
Patient: Rosa Mendez   Attending: Dr. Felix Grant

Chief complaint: shortness of breath follow-up.

VS 118/72 66 98.0 12 99 158

Medications continued:
- tiotropium 18 mcg inhaled once daily
- budesonide 160 mcg inhaled BID
- albuterol 90 mcg inhaled PRN

No prednisone burst at this time.

Follow up in pulmonary clinic 6 weeks.
Call clinic if rescue inhaler needed more than 2x per week.""",
  {
    "vitals": {"blood_pressure": "118/72", "heart_rate": "66", "temperature": "98.0",
               "respiratory_rate": "12", "oxygen_saturation": "99", "weight": "158 lbs"},
    "medications": [
      {"name": "tiotropium", "dose": "18 mcg", "route": "inhaled", "frequency": "daily"},
      {"name": "budesonide", "dose": "160 mcg", "route": "inhaled", "frequency": "BID"},
      {"name": "albuterol", "dose": "90 mcg", "route": "inhaled", "frequency": "PRN"},
    ],
    "instructions": {
      "follow_up": "Follow up in pulmonary clinic 6 weeks.",
      "return_precautions": "Call clinic if rescue inhaler needed more than 2x per week.",
    },
    "metadata": {"patient_name": "Rosa Mendez", "date_of_service": "3/1/2025", "provider_name": "Dr. Felix Grant"},
  }),
  ("eval_020", """Note created: April 1, 2025
Patient: Sam Young
Provider: Dr. Karen Lim

Vitals: Blood pressure 149/94. Heart rate 92. Temperature 98.9 degrees Fahrenheit. Respiratory rate 20 breaths per minute. Oxygen saturation 94 percent. Weight 250 lbs.

Current medication regimen:
clopidogrel 75 mg by mouth once daily
aspirin 81mg PO daily
atorvastatin 40mg oral at bedtime
metoprolol 100mg by mouth twice daily

Patient reports good compliance. Denies chest pain at rest.

Discharge instructions: Continue all medications. Follow up with cardiologist.

Follow up appointment: see cardiologist in 2 weeks.

Return precautions: Return to ED for chest pain, jaw pain, left arm pain, or sudden severe headache.""",
  {
    "vitals": {"blood_pressure": "149/94", "heart_rate": "92", "temperature": "98.9",
               "respiratory_rate": "20", "oxygen_saturation": "94", "weight": "250 lbs"},
    "medications": [
      {"name": "clopidogrel", "dose": "75 mg", "route": "PO", "frequency": "daily"},
      {"name": "aspirin", "dose": "81 mg", "route": "PO", "frequency": "daily"},
      {"name": "atorvastatin", "dose": "40 mg", "route": "PO", "frequency": "daily"},
      {"name": "metoprolol", "dose": "100 mg", "route": "PO", "frequency": "BID"},
    ],
    "instructions": {
      "discharge_instructions": "Continue all medications. Follow up with cardiologist.",
      "follow_up": "see cardiologist in 2 weeks.",
      "return_precautions": "Return to ED for chest pain, jaw pain, left arm pain, or sudden severe headache.",
    },
    "metadata": {"patient_name": "Sam Young", "date_of_service": "April 1, 2025", "provider_name": "Dr. Karen Lim"},
  }),
]  # end EVAL_DATA

for stem, note_text, label in EVAL_DATA:
    (NOTES_DIR / f"{stem}.txt").write_text(note_text.strip(), encoding="utf-8")
    (LABELS_DIR / f"{stem}.json").write_text(json.dumps(label, indent=2), encoding="utf-8")

print(f"Wrote {len(EVAL_DATA)} eval notes and labels.")
```

- [ ] **Step 2: Run the script**

```bash
python scripts/create_eval_data.py
```

Expected: `Wrote 20 eval notes and labels.`

- [ ] **Step 3: Verify**

```bash
ls data/eval/notes/ | wc -l   # 20
ls data/eval/labels/ | wc -l  # 20
python -c "import json; d=json.load(open('data/eval/labels/eval_001.json')); print(list(d.keys()))"
# ['vitals', 'medications', 'instructions', 'metadata']
```

- [ ] **Step 4: Commit**

```bash
git add scripts/create_eval_data.py data/eval/
git commit -m "feat: add 20 hand-written eval notes with ground-truth labels"
```

---

### Task 21: Showcase notes (10 polished notes) + seed script

**Files:**
- Create: `data/showcase/notes/showcase_001.txt` … `showcase_010.txt`
- Create: `scripts/seed_demo_data.py`

- [ ] **Step 1: Create showcase notes** — each exercises a distinct UI state

Create `data/showcase/notes/showcase_001.txt` through `showcase_010.txt`. Use 10 distinct clinical scenarios:

```
001 — Full data: all vitals, 3 meds, all instruction sections
002 — Missing vitals (patient declined): only BP and HR recorded
003 — Long med list: 5 medications
004 — Negations: 2 denied medications + 2 active
005 — Prose-embedded meds: medications mentioned in flowing text
006 — Short progress note: no sections, fallback extraction only
007 — PDF-style (dense formatting): minimal whitespace
008 — Multiple blank lines and inconsistent headers
009 — Follow-up only note: no discharge instructions
010 — Pediatric-style: weight in kg, temp in Celsius (tests normalization edge cases)
```

Write each file with a distinctive clinical scenario, 50–300 words. Keep notes plausible and clearly synthetic (no PHI).

Example for `showcase_001.txt`:

```
Patient: Demo Patient One
Date of Service: 2025-01-15
Provider: Dr. Demo Provider

VITALS: BP 130/82. HR 76 bpm. Temp 98.6F. RR 14. SpO2 98%. Wt 175 lbs.

MEDICATIONS:
- lisinopril 10 mg PO daily
- metformin 500 mg PO BID
- atorvastatin 20 mg PO daily

DISCHARGE INSTRUCTIONS:
Take all medications as prescribed. Follow a heart-healthy diet. Weigh yourself daily.

FOLLOW UP:
Return to clinic in 2 weeks for follow-up labs and blood pressure check.

RETURN PRECAUTIONS:
Return to the emergency department if you experience chest pain, shortness of breath, or blood pressure above 180/110 mmHg.
```

Write all 10 by adapting the clinical context. They will be used for screenshots and live demos.

- [ ] **Step 2: Create seed_demo_data.py**

```python
#!/usr/bin/env python3
# scripts/seed_demo_data.py
"""
Load dev + showcase notes (60 total) into the database.
Eval notes are held out — they are never seeded into the reviewer DB.
Run this script before demoing the app.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from utils.db import get_engine, init_db, get_session
from routes.seed import seed_notes
from config import Config

if __name__ == "__main__":
    engine = get_engine(Config.DB_PATH)
    init_db(engine)
    session = get_session(engine)
    result = seed_notes(session)
    session.close()
    print(f"Seeded: {result['loaded']} loaded, {result['skipped']} already existed.")
```

- [ ] **Step 3: Run seed script**

```bash
python scripts/seed_demo_data.py
```

Expected output (first run): `Seeded: 60 loaded, 0 already existed.`
Second run: `Seeded: 0 loaded, 60 already existed.` (idempotent)

- [ ] **Step 4: Commit**

```bash
git add data/showcase/ scripts/seed_demo_data.py
git commit -m "feat: add 10 showcase notes and seed_demo_data.py"
```

---

---

## Chunk 6: Evaluation Pipeline

### Task 22: compare.py + metrics.py

**Files:**
- Create: `backend/evaluation/compare.py`
- Create: `backend/evaluation/metrics.py`
- Create: `backend/evaluation/__init__.py`
- Test: `backend/tests/test_evaluation.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_evaluation.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from evaluation.compare import compare_vitals, compare_medications, compare_instructions
from evaluation.metrics import compute_metrics

# ------- compare_vitals -------
PRED_VITALS = {
    "blood_pressure": {"value": "138/88", "source": "regex", "confidence": 1.0, "span": [0, 10]},
    "heart_rate":     {"value": "82",      "source": "regex", "confidence": 1.0, "span": [11, 20]},
    "weight":         {"value": "172 lbs", "source": "regex", "confidence": 1.0, "span": [21, 30]},
}
LABEL_VITALS = {
    "blood_pressure": "138/88",
    "heart_rate": "82",
    "temperature": "98.8",   # predicted but not in label? no — missing from pred
    "weight": "172 lbs",
}

def test_compare_vitals_correct_match():
    tp, fp, fn = compare_vitals(PRED_VITALS, LABEL_VITALS)
    assert tp == 3  # bp, hr, weight all match
    assert fp == 0
    assert fn == 1  # temperature in label but not in pred

def test_compare_vitals_unit_stripping():
    pred = {"weight": {"value": "185 lbs"}}
    label = {"weight": "185 lbs"}
    tp, fp, fn = compare_vitals(pred, label)
    assert tp == 1
    assert fn == 0

def test_compare_vitals_no_predictions():
    tp, fp, fn = compare_vitals({}, {"blood_pressure": "120/80"})
    assert tp == 0
    assert fn == 1

# ------- compare_medications -------
PRED_MEDS = [
    {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    {"name": "metformin",  "dose": "500 mg", "route": "PO", "frequency": "BID"},
]
LABEL_MEDS = [
    {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    {"name": "metformin",  "dose": "500 mg", "route": "PO", "frequency": "BID"},
    {"name": "atorvastatin", "dose": "20 mg", "route": "PO", "frequency": "daily"},
]

def test_compare_medications_correct():
    tp, fp, fn = compare_medications(PRED_MEDS, LABEL_MEDS)
    assert tp == 2
    assert fn == 1  # atorvastatin missing from pred

def test_compare_medications_empty_pred():
    tp, fp, fn = compare_medications([], LABEL_MEDS)
    assert tp == 0
    assert fn == 3

# ------- compute_metrics -------
def test_compute_metrics_perfect():
    m = compute_metrics(tp=5, fp=0, fn=0)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0

def test_compute_metrics_no_predictions():
    m = compute_metrics(tp=0, fp=0, fn=5)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python -m pytest backend/tests/test_evaluation.py -v
```

- [ ] **Step 3: Implement evaluation/compare.py**

```python
# backend/evaluation/compare.py
"""
Compare pipeline predictions against ground-truth labels.
All string comparisons: trimmed, lowercased, units stripped.
"""
import re
from typing import Any


def _normalize(s: str) -> str:
    """Strip common vital units, lowercase, trim. Use for vitals/metadata fields only."""
    s = s.lower().strip()
    # Strip common units from end of string (vitals only — do NOT apply to free text)
    s = re.sub(r'\s*(lbs?|kg|pounds?|kilograms?|bpm|mmhg|%)\s*$', '', s).strip()
    return s


def _normalize_text(s: str) -> str:
    """Lowercase and trim only — for free-text fields like instructions."""
    return s.lower().strip()


def _get_value(field_data: Any) -> str:
    if isinstance(field_data, dict):
        return _normalize(str(field_data.get("value", "")))
    return _normalize(str(field_data))


def _get_text(field_data: Any) -> str:
    """Extract value as plain normalized text (no unit stripping)."""
    if isinstance(field_data, dict):
        return _normalize_text(str(field_data.get("value", "")))
    return _normalize_text(str(field_data))


def compare_vitals(pred: dict, label: dict) -> tuple[int, int, int]:
    """Returns (true_positives, false_positives, false_negatives)."""
    tp = fp = fn = 0
    all_keys = set(pred) | set(label)
    for key in all_keys:
        if key in pred and key in label:
            if _get_value(pred[key]) == _get_value(label[key]):
                tp += 1
            else:
                fp += 1
                fn += 1
        elif key in pred:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn


def compare_instructions(pred: dict, label: dict) -> tuple[int, int, int]:
    """Substring match: label value must appear within predicted value.
    Uses text normalization (lowercase+strip only, no unit stripping) to preserve
    free-text content correctly.
    """
    tp = fp = fn = 0
    all_keys = set(pred) | set(label)
    for key in all_keys:
        if key in pred and key in label:
            pred_val = _get_text(pred[key])
            label_val = _normalize_text(str(label[key]))
            if label_val in pred_val:
                tp += 1
            else:
                fp += 1
                fn += 1
        elif key in pred:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn


def compare_metadata(pred: dict, label: dict) -> tuple[int, int, int]:
    """Same as vitals: exact match after normalization."""
    return compare_vitals(pred, label)


def compare_medications(pred: list, label: list) -> tuple[int, int, int]:
    """
    Match by name (lowercased). For matched pairs, check dose match.
    Route and frequency are optional (scored if present in label).
    +1 TP per matched item where name + dose match.
    """
    tp = fp = fn = 0
    pred_by_name = {m["name"].lower().strip(): m for m in pred}
    label_by_name = {m["name"].lower().strip(): m for m in label}
    all_names = set(pred_by_name) | set(label_by_name)
    for name in all_names:
        if name in pred_by_name and name in label_by_name:
            pm = pred_by_name[name]
            lm = label_by_name[name]
            # Dose must match
            if _normalize(pm.get("dose", "")) == _normalize(lm.get("dose", "")):
                tp += 1
            else:
                fp += 1
                fn += 1
        elif name in pred_by_name:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn
```

- [ ] **Step 4: Implement evaluation/metrics.py**

```python
# backend/evaluation/metrics.py
from typing import Any


def compute_metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def aggregate_metrics(
    vitals_tpfpfn: tuple,
    meds_tpfpfn: tuple,
    instructions_tpfpfn: tuple,
    metadata_tpfpfn: tuple,
) -> dict[str, Any]:
    categories = {
        "vitals": vitals_tpfpfn,
        "medications": meds_tpfpfn,
        "instructions": instructions_tpfpfn,
        "metadata": metadata_tpfpfn,
    }
    by_category = {cat: compute_metrics(*tpfpfn) for cat, tpfpfn in categories.items()}

    total_tp = sum(t[0] for t in categories.values())
    total_fp = sum(t[1] for t in categories.values())
    total_fn = sum(t[2] for t in categories.values())
    overall = compute_metrics(total_tp, total_fp, total_fn)

    return {"overall": overall, "by_category": by_category}
```

- [ ] **Step 5: Create `backend/evaluation/__init__.py`** (empty)

- [ ] **Step 6: Run — verify PASS**

```bash
python -m pytest backend/tests/test_evaluation.py -v
```

Expected: 9 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/evaluation/__init__.py backend/evaluation/compare.py \
        backend/evaluation/metrics.py backend/tests/test_evaluation.py
git commit -m "feat: add evaluation compare and metrics modules"
```

---

### Task 23: run_evaluation.py CLI + report.py

**Files:**
- Create: `backend/evaluation/report.py`
- Create: `scripts/run_evaluation.py`

- [ ] **Step 1: Implement evaluation/report.py**

```python
# backend/evaluation/report.py
import json
from datetime import datetime, timezone
from typing import Any


def build_report(
    pipeline_version: str,
    overall: dict,
    by_category: dict,
    per_note: list[dict],
) -> dict[str, Any]:
    return {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": pipeline_version,
        "overall": overall,
        "by_category": by_category,
        "per_note": per_note,
    }


def print_summary(report: dict) -> None:
    ov = report["overall"]
    print("\n" + "=" * 60)
    print(f"  Clinical NLP Evaluation — pipeline v{report['pipeline_version']}")
    print("=" * 60)
    print(f"  {'Category':<20} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("  " + "-" * 54)
    for cat, m in report["by_category"].items():
        print(f"  {cat:<20} {m['precision']:>10.3f} {m['recall']:>10.3f} {m['f1']:>10.3f}")
    print("  " + "-" * 54)
    print(f"  {'OVERALL':<20} {ov['precision']:>10.3f} {ov['recall']:>10.3f} {ov['f1']:>10.3f}")
    print("=" * 60)
    print(f"  Notes evaluated: {len(report['per_note'])}")
    print()
```

- [ ] **Step 2: Implement scripts/run_evaluation.py**

```python
#!/usr/bin/env python3
# scripts/run_evaluation.py
"""
Run evaluation on the 20 labeled eval notes.
Writes results to backend/evaluation/results.json.
Prints a formatted summary.
Usage: python scripts/run_evaluation.py
"""
import sys, os, json
from pathlib import Path

_BACKEND = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from config import Config
from extractors.pipeline import run_pipeline
from evaluation.compare import (
    compare_vitals, compare_instructions, compare_medications, compare_metadata
)
from evaluation.metrics import compute_metrics, aggregate_metrics
from evaluation.report import build_report, print_summary

EVAL_NOTES_DIR = Path(__file__).parent.parent / "data" / "eval" / "notes"
EVAL_LABELS_DIR = Path(__file__).parent.parent / "data" / "eval" / "labels"


def evaluate_note(note_text: str, label: dict) -> dict:
    prediction = run_pipeline(note_text)

    v_tp, v_fp, v_fn = compare_vitals(prediction.get("vitals", {}), label.get("vitals", {}))
    m_tp, m_fp, m_fn = compare_medications(prediction.get("medications", []), label.get("medications", []))
    i_tp, i_fp, i_fn = compare_instructions(prediction.get("instructions", {}), label.get("instructions", {}))
    mt_tp, mt_fp, mt_fn = compare_metadata(prediction.get("metadata", {}), label.get("metadata", {}))

    return {
        "vitals_f1": compute_metrics(v_tp, v_fp, v_fn)["f1"],
        "medications_f1": compute_metrics(m_tp, m_fp, m_fn)["f1"],
        "instructions_f1": compute_metrics(i_tp, i_fp, i_fn)["f1"],
        "metadata_f1": compute_metrics(mt_tp, mt_fp, mt_fn)["f1"],
        "_tp": (v_tp, m_tp, i_tp, mt_tp),
        "_fp": (v_fp, m_fp, i_fp, mt_fp),
        "_fn": (v_fn, m_fn, i_fn, mt_fn),
    }


def main():
    note_files = sorted(EVAL_NOTES_DIR.glob("*.txt"))
    if not note_files:
        print(f"No eval notes found in {EVAL_NOTES_DIR}")
        sys.exit(1)

    per_note = []
    totals = {"vitals": [0,0,0], "medications": [0,0,0], "instructions": [0,0,0], "metadata": [0,0,0]}
    cats = ["vitals", "medications", "instructions", "metadata"]

    for note_path in note_files:
        label_path = EVAL_LABELS_DIR / (note_path.stem + ".json")
        if not label_path.exists():
            print(f"  SKIP {note_path.name}: no label file found")
            continue

        note_text = note_path.read_text(encoding="utf-8")
        label = json.loads(label_path.read_text(encoding="utf-8"))

        result = evaluate_note(note_text, label)

        for i, cat in enumerate(cats):
            totals[cat][0] += result["_tp"][i]
            totals[cat][1] += result["_fp"][i]
            totals[cat][2] += result["_fn"][i]

        per_note.append({
            "note": note_path.name,
            "vitals_f1": result["vitals_f1"],
            "medications_f1": result["medications_f1"],
            "instructions_f1": result["instructions_f1"],
            "metadata_f1": result["metadata_f1"],
        })
        print(f"  Evaluated {note_path.name}")

    agg = aggregate_metrics(
        tuple(totals["vitals"]),
        tuple(totals["medications"]),
        tuple(totals["instructions"]),
        tuple(totals["metadata"]),
    )

    report = build_report(Config.PIPELINE_VERSION, agg["overall"], agg["by_category"], per_note)

    results_path = Path(Config.EVAL_RESULTS_PATH)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Results written to {results_path}")

    print_summary(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run evaluation as smoke test**

```bash
python scripts/run_evaluation.py
```

Expected: evaluates 20 notes, prints summary table with F1 > 0 for all categories, writes `backend/evaluation/results.json`.

- [ ] **Step 4: Verify results.json**

```bash
python -c "
import json
r = json.load(open('backend/evaluation/results.json'))
print('Keys:', list(r.keys()))
print('Overall F1:', r['overall']['f1'])
print('Notes evaluated:', len(r['per_note']))
"
```

Expected: all required keys present, F1 > 0.

- [ ] **Step 5: Commit**

```bash
git add backend/evaluation/report.py scripts/run_evaluation.py
git commit -m "feat: add evaluation CLI (run_evaluation.py) and report module"
```

---

---

## Chunk 7: Frontend, Tests, Docker, README

### Task 24: Frontend types and API wrappers

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// frontend/src/types.ts

export interface FieldValue {
  value: string;
  span: [number, number];
  source: "regex" | "medspacy" | "section" | "fallback";
  confidence: number;
}

export interface Medication {
  name: string;
  dose: string;
  route: string;
  frequency: string;
  span: [number, number];
  source: string;
  confidence: number;
}

export interface Instructions {
  discharge_instructions?: FieldValue;
  follow_up?: FieldValue;
  return_precautions?: FieldValue;
}

export interface Vitals {
  blood_pressure?: FieldValue;
  heart_rate?: FieldValue;
  temperature?: FieldValue;
  respiratory_rate?: FieldValue;
  oxygen_saturation?: FieldValue;
  weight?: FieldValue;
}

export interface Metadata {
  patient_name?: FieldValue;
  date_of_service?: FieldValue;
  provider_name?: FieldValue;
}

export interface ExtractionResult {
  pipeline_version: string;
  vitals: Vitals;
  medications: Medication[];
  instructions: Instructions;
  metadata: Metadata;
}

export interface NoteListItem {
  id: number;
  filename: string | null;
  source: string;
  created_at: string;
  status: "pending" | "accepted" | "corrected";
  correction_count: number;
}

export interface NoteDetail {
  id: number;
  filename: string | null;
  raw_text: string;
  source: string;
  created_at: string;
  extracted_json: ExtractionResult | null;
  pipeline_version: string | null;
  validation: {
    status: string;
    validated_json: ExtractionResult;
    correction_count: number;
    review_duration_ms: number | null;
  } | null;
}

export interface MetricsResponse {
  eval: {
    run_at: string;
    pipeline_version: string;
    overall: { precision: number; recall: number; f1: number };
    by_category: Record<string, { precision: number; recall: number; f1: number }>;
    per_note: Array<{ note: string; vitals_f1: number; medications_f1: number; instructions_f1: number; metadata_f1: number }>;
  } | null;
  db_stats: {
    by_status: Array<{ status: string; count: number; avg_corrections: number; avg_review_ms: number }>;
  };
}
```

- [ ] **Step 2: Create api/client.ts**

```typescript
// frontend/src/api/client.ts
const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || "Request failed");
  }
  return resp.json();
}

export const api = {
  extractText: (text: string) =>
    request<any>("/extract", { method: "POST", body: JSON.stringify({ text }) }),

  createNote: (text: string) =>
    request<{ note_id: number; extracted_json: any }>("/notes", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  uploadFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/upload`, { method: "POST", body: form })
      .then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ error: r.statusText }));
          throw new Error(err.error || "Upload failed");
        }
        return r.json() as Promise<{ note_id: number; extracted_json: any }>;
      });
  },

  validate: (payload: {
    note_id: number;
    validated_json: any;
    status: string;
    review_duration_ms: number;
  }) =>
    request<{ ok: boolean; correction_count: number }>("/validate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getHistory: (page = 1) =>
    request<{ notes: any[]; page: number }>(`/history?page=${page}`),

  getNoteDetail: (id: number) =>
    request<any>(`/history/${id}`),

  getMetrics: () => request<any>("/metrics"),

  seedDemo: () =>
    request<{ loaded: number; skipped: number }>("/seed-demo", { method: "POST" }),
};
```

- [ ] **Step 3: Delete Vite boilerplate** — remove `frontend/src/App.tsx` contents and replace:

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import Review from "./pages/Review";
import History from "./pages/History";
import Metrics from "./pages/Metrics";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/review" element={<Review />} />
        <Route path="/review/:noteId" element={<Review />} />
        <Route path="/history" element={<History />} />
        <Route path="/metrics" element={<Metrics />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/ frontend/src/App.tsx
git commit -m "feat: add TypeScript types, API client, and app routing"
```

---

### Task 25: Home page

**Files:**
- Create: `frontend/src/pages/Home.tsx`

- [ ] **Step 1: Implement Home.tsx**

```tsx
// frontend/src/pages/Home.tsx
import { useState, useRef } from "react";
import React from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Home() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const SAMPLE_NOTE = `Patient: Sample Patient
Date of Service: 2025-01-15
Provider: Dr. Demo

Vitals: BP 130/82. HR 76 bpm. Temp 98.6F. RR 14. SpO2 98%. Wt 175 lbs.

Medications:
- lisinopril 10 mg PO daily
- metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take all medications as prescribed.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain or shortness of breath.`;

  async function handleSubmitText() {
    if (!text.trim()) return;
    setLoading(true); setError(null);
    try {
      const { note_id, extracted_json } = await api.createNote(text);
      navigate("/review", { state: { note_id, extracted_json, raw_text: text } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFile(file: File) {
    setLoading(true); setError(null);
    try {
      const { note_id, extracted_json } = await api.uploadFile(file);
      // Fetch the note detail to get the raw_text (not part of extraction output)
      const detail = await api.getNoteDetail(note_id);
      navigate("/review", { state: { note_id, extracted_json, raw_text: detail.raw_text } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  async function handleSeedDemo() {
    setLoading(true);
    try {
      const result = await api.seedDemo();
      alert(`Seeded: ${result.loaded} loaded, ${result.skipped} already existed. Check History.`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Clinical Notes NLP Assistant</h1>
          <p className="text-xs text-amber-600 mt-0.5">Demo mode — all data is synthetic</p>
        </div>
        <nav className="flex gap-4 text-sm text-slate-600">
          <a href="/history" className="hover:text-blue-600">History</a>
          <a href="/metrics" className="hover:text-blue-600">Metrics</a>
        </nav>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center p-6 gap-6 max-w-3xl mx-auto w-full">
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-slate-800">Extract structured data from a clinical note</h2>
          <p className="text-slate-500 mt-1">Paste note text, upload a .txt or .pdf file, or load a sample note.</p>
        </div>

        {/* Text area */}
        <textarea
          className="w-full h-48 border border-slate-300 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
          placeholder="Paste clinical note text here..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
            ${dragging ? "border-blue-400 bg-blue-50" : "border-slate-300 hover:border-blue-300"}`}
        >
          <p className="text-slate-500 text-sm">Drop a .txt or .pdf file here, or click to browse</p>
          <input ref={fileRef} type="file" accept=".txt,.pdf" className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <div className="flex gap-3 flex-wrap justify-center">
          <button onClick={handleSubmitText} disabled={!text.trim() || loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {loading ? "Extracting..." : "Extract →"}
          </button>
          <button onClick={() => setText(SAMPLE_NOTE)}
            className="px-4 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm hover:bg-slate-100">
            Load sample note
          </button>
          <button onClick={handleSeedDemo} disabled={loading}
            className="px-4 py-2 border border-slate-300 text-slate-500 rounded-lg text-sm hover:bg-slate-100">
            Seed demo data
          </button>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Home.tsx
git commit -m "feat: Home page with paste, drag-drop upload, and seed demo"
```

---

### Task 26: Review page (merged Results + Review)

**Files:**
- Create: `frontend/src/pages/Review.tsx`
- Create: `frontend/src/components/NoteViewer.tsx`
- Create: `frontend/src/components/FieldEditor.tsx`

- [ ] **Step 1: Create NoteViewer.tsx** — highlights spans in raw_text

```tsx
// frontend/src/components/NoteViewer.tsx
import { ExtractionResult } from "../types";

interface Span { start: number; end: number; category: string; label: string; }

const COLORS: Record<string, string> = {
  vitals: "bg-blue-100 text-blue-900",
  medications: "bg-green-100 text-green-900",
  instructions: "bg-amber-100 text-amber-900",
  metadata: "bg-purple-100 text-purple-900",
};

function collectSpans(extracted: ExtractionResult): Span[] {
  const spans: Span[] = [];
  Object.entries(extracted.vitals).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "vitals", label: k });
  });
  extracted.medications.forEach((m, i) => {
    if (m?.span) spans.push({ start: m.span[0], end: m.span[1], category: "medications", label: m.name });
  });
  Object.entries(extracted.instructions).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "instructions", label: k });
  });
  Object.entries(extracted.metadata).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "metadata", label: k });
  });
  return spans.sort((a, b) => a.start - b.start);
}

export default function NoteViewer({ rawText, extracted }: { rawText: string; extracted: ExtractionResult }) {
  const spans = collectSpans(extracted);
  const parts: JSX.Element[] = [];
  let pos = 0;

  for (const span of spans) {
    if (span.start > pos) {
      parts.push(<span key={`text-${pos}`}>{rawText.slice(pos, span.start)}</span>);
    }
    if (span.end > span.start) {
      const color = COLORS[span.category] || "bg-slate-100";
      parts.push(
        <mark key={`mark-${span.start}`} title={`${span.category}: ${span.label}`}
          className={`rounded px-0.5 ${color} cursor-help`}>
          {rawText.slice(span.start, span.end)}
        </mark>
      );
      pos = span.end;
    }
  }
  if (pos < rawText.length) {
    parts.push(<span key="text-end">{rawText.slice(pos)}</span>);
  }

  return (
    <div className="h-full overflow-y-auto p-4 font-mono text-sm whitespace-pre-wrap leading-relaxed text-slate-700">
      {parts}
    </div>
  );
}
```

- [ ] **Step 2: Create FieldEditor.tsx**

```tsx
// frontend/src/components/FieldEditor.tsx
import { useState } from "react";

export type FieldStatus = "accepted" | "corrected" | "removed" | "pending";

interface Props {
  label: string;
  value: string;
  status: FieldStatus;
  onChange: (value: string, status: FieldStatus) => void;
}

export default function FieldEditor({ label, value, status, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  const statusColors: Record<FieldStatus, string> = {
    accepted: "border-green-300 bg-green-50",
    corrected: "border-amber-300 bg-amber-50",
    removed: "border-red-200 bg-red-50 opacity-60",
    pending: "border-slate-200 bg-white",
  };

  function save() {
    setEditing(false);
    onChange(draft, draft !== value ? "corrected" : "accepted");
  }

  if (status === "removed") {
    return (
      <div className={`rounded border p-2 text-sm ${statusColors.removed}`}>
        <span className="font-medium text-slate-500 text-xs uppercase tracking-wide">{label}</span>
        <span className="ml-2 text-slate-400 line-through">{value}</span>
        <button onClick={() => onChange(value, "accepted")} className="ml-2 text-xs text-blue-500 hover:underline">restore</button>
      </div>
    );
  }

  return (
    <div className={`rounded border p-2 text-sm ${statusColors[status]}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-slate-500 text-xs uppercase tracking-wide">{label}</span>
        <div className="flex gap-1">
          {status !== "accepted" && (
            <button onClick={() => onChange(value, "accepted")}
              className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 hover:bg-green-200">✓</button>
          )}
          <button onClick={() => setEditing(true)}
            className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-slate-200">edit</button>
          <button onClick={() => onChange(value, "removed")}
            className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-600 hover:bg-red-200">✕</button>
        </div>
      </div>
      {editing ? (
        <div className="mt-1 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={save} className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">save</button>
          <button onClick={() => { setEditing(false); setDraft(value); }}
            className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
        </div>
      ) : (
        <p className="mt-1 text-slate-700">{draft}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Implement Review.tsx**

```tsx
// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef } from "react";
import { useLocation, useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult } from "../types";
import NoteViewer from "../components/NoteViewer";
import FieldEditor, { FieldStatus } from "../components/FieldEditor";

type FieldState = { value: string; status: FieldStatus };
type FieldMap = Record<string, FieldState>;

export default function Review() {
  const location = useLocation();
  const { noteId } = useParams();
  const navigate = useNavigate();
  const startTime = useRef(Date.now());

  const [rawText, setRawText] = useState<string>("");
  const [extracted, setExtracted] = useState<ExtractionResult | null>(null);
  const [noteIdState, setNoteIdState] = useState<number | null>(null);
  const [fields, setFields] = useState<FieldMap>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer
  useEffect(() => {
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - startTime.current) / 1000)), 1000);
    return () => clearInterval(interval);
  }, []);

  // Load data from navigation state or fetch
  useEffect(() => {
    const state = location.state as { note_id?: number; extracted_json?: ExtractionResult; raw_text?: string } | null;
    if (state?.extracted_json) {
      setRawText(state.raw_text ?? "");
      setExtracted(state.extracted_json);
      setNoteIdState(state.note_id ?? null);
    } else if (noteId) {
      api.getNoteDetail(Number(noteId)).then((d) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
      });
    }
  }, [noteId, location.state]);

  // Flatten extracted JSON into editable fields
  useEffect(() => {
    if (!extracted) return;
    const m: FieldMap = {};
    Object.entries(extracted.vitals).forEach(([k, v]) => {
      if (v) m[`vitals.${k}`] = { value: v.value, status: "pending" };
    });
    extracted.medications.forEach((med, i) => {
      m[`med.${i}.name`] = { value: med.name, status: "pending" };
      if (med.dose) m[`med.${i}.dose`] = { value: med.dose, status: "pending" };
      if (med.route) m[`med.${i}.route`] = { value: med.route, status: "pending" };
      if (med.frequency) m[`med.${i}.frequency`] = { value: med.frequency, status: "pending" };
    });
    Object.entries(extracted.instructions).forEach(([k, v]) => {
      if (v) m[`instr.${k}`] = { value: v.value, status: "pending" };
    });
    Object.entries(extracted.metadata).forEach(([k, v]) => {
      if (v) m[`meta.${k}`] = { value: v.value, status: "pending" };
    });
    setFields(m);
  }, [extracted]);

  function handleFieldChange(key: string, value: string, status: FieldStatus) {
    setFields((prev) => ({ ...prev, [key]: { value, status } }));
  }

  async function handleSave(overallStatus: "accepted" | "corrected") {
    if (!noteIdState || !extracted) return;
    setSaving(true); setError(null);
    try {
      const validated = JSON.parse(JSON.stringify(extracted));
      // Collect removed medication indices first
      const removedMedIndices = new Set<number>();
      Object.entries(fields).forEach(([key, { status }]) => {
        const parts = key.split(".");
        if (parts[0] === "med" && status === "removed") {
          removedMedIndices.add(parseInt(parts[1]));
        }
      });

      // Apply field edits
      Object.entries(fields).forEach(([key, { value, status }]) => {
        const [section, ...rest] = key.split(".");
        if (status === "removed") {
          if (section === "vitals") delete validated.vitals[rest[0]];
          else if (section === "instr") delete validated.instructions[rest[0]];
          else if (section === "meta") delete validated.metadata[rest[0]];
          // med removals handled by filter below
        } else {
          if (section === "vitals" && validated.vitals[rest[0]]) {
            validated.vitals[rest[0]].value = value;
          } else if (section === "instr" && validated.instructions[rest[0]]) {
            validated.instructions[rest[0]].value = value;
          } else if (section === "meta" && validated.metadata[rest[0]]) {
            validated.metadata[rest[0]].value = value;
          } else if (section === "med") {
            const idx = parseInt(rest[0]);
            const field = rest[1];
            if (!removedMedIndices.has(idx) && validated.medications[idx]) {
              (validated.medications[idx] as any)[field] = value;
            }
          }
        }
      });

      // Remove medications marked for deletion
      validated.medications = validated.medications.filter(
        (_: any, i: number) => !removedMedIndices.has(i)
      );

      await api.validate({
        note_id: noteIdState,
        validated_json: validated,
        status: overallStatus,
        review_duration_ms: Date.now() - startTime.current,
      });
      setSaved(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!extracted) return <div className="p-8 text-slate-400">Loading...</div>;

  const hasCorrected = Object.values(fields).some((f) => f.status === "corrected" || f.status === "removed");

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <a href="/" className="text-slate-400 hover:text-slate-600 text-sm">← Back</a>
          <h1 className="text-lg font-semibold text-slate-800">Reviewer</h1>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-400">Time: {Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,"0")}</span>
          <span className="text-slate-400 text-xs">pipeline v{extracted.pipeline_version}</span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden" style={{ height: "calc(100vh - 57px)" }}>
        {/* Left: note viewer */}
        <div className="w-1/2 border-r border-slate-200 overflow-hidden flex flex-col">
          <div className="px-4 py-2 border-b border-slate-100 flex gap-3 text-xs">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-blue-100 inline-block"/>vitals</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-100 inline-block"/>medications</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-100 inline-block"/>instructions</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-purple-100 inline-block"/>metadata</span>
          </div>
          <NoteViewer rawText={rawText} extracted={extracted} />
        </div>

        {/* Right: editable fields */}
        <div className="w-1/2 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Vitals */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Vitals</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("vitals.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("vitals.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Medications */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Medications</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("med.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace(/^med\.\d+\./, "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Instructions */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Instructions</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("instr.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("instr.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Metadata */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Metadata</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("meta.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("meta.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
          </div>

          {/* Footer actions */}
          <div className="border-t border-slate-200 p-4 flex items-center justify-between bg-white">
            {error && <p className="text-red-500 text-sm">{error}</p>}
            {saved && <p className="text-green-600 text-sm">Saved ✓</p>}
            <div className="flex gap-2 ml-auto">
              <button onClick={() => handleSave("accepted")} disabled={saving}
                className="px-4 py-2 border border-green-300 text-green-700 rounded text-sm hover:bg-green-50 disabled:opacity-50">
                Accept all
              </button>
              <button onClick={() => handleSave("corrected")} disabled={saving || !hasCorrected}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Saving..." : "Save corrections"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Review.tsx frontend/src/components/
git commit -m "feat: Review page with NoteViewer span highlighting and FieldEditor"
```

---

### Task 27: History and Metrics pages

**Files:**
- Create: `frontend/src/pages/History.tsx`
- Create: `frontend/src/pages/Metrics.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`

- [ ] **Step 1: Create StatusBadge.tsx**

```tsx
// frontend/src/components/StatusBadge.tsx
const styles = {
  pending: "bg-slate-100 text-slate-600",
  accepted: "bg-green-100 text-green-700",
  corrected: "bg-amber-100 text-amber-700",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = styles[status as keyof typeof styles] ?? styles.pending;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{status}</span>;
}
```

- [ ] **Step 2: Create History.tsx**

```tsx
// frontend/src/pages/History.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { NoteListItem } from "../types";
import StatusBadge from "../components/StatusBadge";

export default function History() {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<NoteListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getHistory().then((d) => { setNotes(d.notes); setLoading(false); });
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">History</h1>
        <nav className="flex gap-4 text-sm text-slate-600">
          <a href="/" className="hover:text-blue-600">Home</a>
          <a href="/metrics" className="hover:text-blue-600">Metrics</a>
        </nav>
      </header>
      <main className="max-w-5xl mx-auto p-6">
        {loading ? <p className="text-slate-400">Loading...</p> : notes.length === 0 ? (
          <p className="text-slate-400">No notes yet. <a href="/" className="text-blue-600 hover:underline">Extract a note</a> or seed demo data.</p>
        ) : (
          <table className="w-full text-sm bg-white rounded-lg shadow-sm overflow-hidden">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["File", "Source", "Created", "Status", "Corrections"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-slate-500 font-medium text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {notes.map((note) => (
                <tr key={note.id} onClick={() => navigate(`/review/${note.id}`)}
                  className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer">
                  <td className="px-4 py-3 text-slate-700">{note.filename ?? `note #${note.id}`}</td>
                  <td className="px-4 py-3 text-slate-500">{note.source}</td>
                  <td className="px-4 py-3 text-slate-500">{new Date(note.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3"><StatusBadge status={note.status} /></td>
                  <td className="px-4 py-3 text-slate-500">{note.correction_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Create Metrics.tsx**

```tsx
// frontend/src/pages/Metrics.tsx
import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { api } from "../api/client";
import { MetricsResponse } from "../types";

export default function Metrics() {
  const [data, setData] = useState<MetricsResponse | null>(null);

  useEffect(() => { api.getMetrics().then(setData); }, []);

  if (!data) return <div className="p-8 text-slate-400">Loading...</div>;

  const evalData = data.eval;
  const chartData = evalData
    ? Object.entries(evalData.by_category).map(([cat, m]) => ({
        category: cat, precision: m.precision, recall: m.recall, f1: m.f1,
      }))
    : [];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Metrics</h1>
        <nav className="flex gap-4 text-sm text-slate-600">
          <a href="/" className="hover:text-blue-600">Home</a>
          <a href="/history" className="hover:text-blue-600">History</a>
        </nav>
      </header>
      <main className="max-w-5xl mx-auto p-6 space-y-8">
        {!evalData ? (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-amber-700 text-sm">
            Evaluation results not yet available. Run <code className="bg-amber-100 px-1 rounded">python scripts/run_evaluation.py</code> to generate metrics.
          </div>
        ) : (
          <>
            {/* Overall cards */}
            <div className="grid grid-cols-3 gap-4">
              {(["precision", "recall", "f1"] as const).map((metric) => (
                <div key={metric} className="bg-white rounded-lg border border-slate-200 p-4 text-center shadow-sm">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">{metric}</p>
                  <p className="text-3xl font-semibold text-blue-600 mt-1">{(evalData.overall[metric] * 100).toFixed(1)}%</p>
                </div>
              ))}
            </div>

            {/* Per-category chart */}
            <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-600 mb-4">Performance by Category</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="category" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                  <Legend />
                  <Bar dataKey="precision" fill="#93c5fd" name="Precision" />
                  <Bar dataKey="recall" fill="#6ee7b7" name="Recall" />
                  <Bar dataKey="f1" fill="#818cf8" name="F1" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <p className="text-xs text-slate-400">
              Evaluated on 20 hand-written synthetic notes · pipeline v{evalData.pipeline_version} · run at {new Date(evalData.run_at).toLocaleString()}
            </p>
          </>
        )}

        {/* DB correction stats */}
        {data.db_stats.by_status.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-600 mb-3">Review Activity</h2>
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-slate-400">
                <th className="text-left py-1">Status</th>
                <th className="text-right py-1">Count</th>
                <th className="text-right py-1">Avg corrections</th>
                <th className="text-right py-1">Avg review time</th>
              </tr></thead>
              <tbody>
                {data.db_stats.by_status.map((row) => (
                  <tr key={row.status} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-700">{row.status}</td>
                    <td className="py-1.5 text-right text-slate-600">{row.count}</td>
                    <td className="py-1.5 text-right text-slate-600">{row.avg_corrections.toFixed(1)}</td>
                    <td className="py-1.5 text-right text-slate-600">
                      {row.avg_review_ms ? `${Math.round(row.avg_review_ms / 1000)}s` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/History.tsx frontend/src/pages/Metrics.tsx frontend/src/components/StatusBadge.tsx
git commit -m "feat: History and Metrics pages"
```

---

### Task 28: Backend + frontend tests

**Files:**
- Test: `backend/tests/test_corrections.py` (unit tests for the corrections module)
- Test: `frontend/src/FieldEditor.test.tsx`

- [ ] **Step 1: Backend corrections unit test**

```python
# backend/tests/test_corrections.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.corrections import compute_correction_count

def test_no_corrections_when_identical():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, ext) == 0

def test_counts_changed_vital():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"bp": {"value": "130/85"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_counts_added_field():
    ext = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_counts_removed_field():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_medication_dose_change_is_one():
    ext = {"vitals": {}, "medications": [{"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"}], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [{"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"}], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1  # Not 2

def test_medication_added_is_one():
    ext = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [{"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"}], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1
```

- [ ] **Step 2: Run backend correction tests**

```bash
python -m pytest backend/tests/test_corrections.py -v
```

Expected: 6 passed.

- [ ] **Step 3: Frontend FieldEditor test**

```tsx
// frontend/src/FieldEditor.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import FieldEditor from "./components/FieldEditor";

it("renders the field label and value", () => {
  render(<FieldEditor label="blood_pressure" value="120/80" status="pending" onChange={() => {}} />);
  expect(screen.getByText("blood_pressure")).toBeInTheDocument();
  expect(screen.getByText("120/80")).toBeInTheDocument();
});

it("calls onChange with corrected status after edit", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" onChange={onChange} />);
  fireEvent.click(screen.getByText("edit"));
  const input = screen.getByDisplayValue("120/80");
  fireEvent.change(input, { target: { value: "130/85" } });
  fireEvent.click(screen.getByText("save"));
  expect(onChange).toHaveBeenCalledWith("130/85", "corrected");
});

it("calls onChange with removed status on remove", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" onChange={onChange} />);
  fireEvent.click(screen.getByText("✕"));
  expect(onChange).toHaveBeenCalledWith("120/80", "removed");
});
```

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npm test
```

Expected: 3 passed.

- [ ] **Step 5: Run complete backend test suite one final time**

```bash
cd /Users/kanuj/clinical-notes-nlp-assistant
python -m pytest backend/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_corrections.py frontend/src/FieldEditor.test.tsx
git commit -m "test: corrections unit tests and FieldEditor component tests"
```

---

### Task 29: Dockerfile + docker-compose.yml

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile

# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend + serve frontend
FROM python:3.11-slim AS runtime
WORKDIR /app/backend

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

# Copy backend
COPY backend/ .

# Copy built frontend into static/
COPY --from=frontend-build /app/frontend/dist ./static

# Copy data and scripts
WORKDIR /app
COPY data/ data/
COPY scripts/ scripts/

ENV FLASK_ENV=production
ENV PYTHONPATH=/app/backend

EXPOSE 5000
CMD ["gunicorn", "--chdir", "/app/backend", "app:create_app()", "--bind", "0.0.0.0:5000", "--workers", "2"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.8"
services:
  backend:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./backend:/app/backend
      - ./data:/app/data
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
    command: python /app/backend/app.py

  frontend:
    image: node:20-alpine
    working_dir: /app/frontend
    volumes:
      - ./frontend:/app/frontend
    ports:
      - "5173:5173"
    command: sh -c "npm install && npm run dev -- --host"
    depends_on:
      - backend
```

- [ ] **Step 3: Create .dockerignore**

```
.venv/
__pycache__/
*.pyc
.git/
node_modules/
frontend/node_modules/
*.db
backend/evaluation/results.json
```

- [ ] **Step 4: Test Docker build**

```bash
docker build -t clinical-notes-nlp .
```

Expected: successful build in ~3-5 minutes.

- [ ] **Step 5: Test Docker run**

```bash
docker run -p 5000:5000 clinical-notes-nlp
```

Then open `http://localhost:5000` and verify Home page loads.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Dockerfile (multi-stage) and docker-compose"
```

---

### Task 30: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md** (abbreviated structure — fill in each section)

The README must include these sections in order:

1. **Project Overview** — one-paragraph summary, portfolio-context framing
2. **Problem Statement** — why this matters, what the system does
3. **Architecture Overview** — ASCII diagram: `[Note Input] → [Flask API] → [NLP Pipeline (medSpaCy + regex)] → [SQLite] ← [React UI]`
4. **Why medSpaCy + Regex** — explicit rationale: rule-based for interpretability and deterministic evaluation, no API cost, medSpaCy's clinical ConText/Sectionizer are the right tools for structured extraction
5. **Setup** — `git clone`, `python3.11 -m venv .venv`, `pip install -r requirements.txt`, `python -m spacy download en_core_web_sm`, `npm install` in frontend/
6. **Local Development** — two-terminal instructions (Flask + Vite), then `python scripts/seed_demo_data.py`
7. **Docker** — `docker compose up` one-liner
8. **Demo Mode** — step-by-step: load sample note → review → save → check History
9. **Evaluation** — `python scripts/run_evaluation.py`, then open Metrics page
10. **Limitations** — prototype vocabulary, no OCR, no real LLM, no auth, no real PHI, all data synthetic, no RxNorm
11. **Future Improvements** — scispaCy upgrade, LLM fallback, OCR, FHIR output, active learning
12. **Screenshots** — 4 placeholder sections: `[Home page screenshot]`, `[Review page screenshot]`, `[History page screenshot]`, `[Metrics page screenshot]`
13. **Synthetic Data Disclaimer** — explicit notice
14. **How to Demo in an Interview** — 90-second script:
    - (0:00) "Here's the home page — you can paste a note or upload a file."
    - (0:15) Load sample note, click Extract
    - (0:25) Walk through the Review page: left pane shows highlighted spans, right pane shows structured fields
    - (0:45) Correct one field, click Save
    - (0:55) Switch to History, show the corrected note with correction count
    - (1:05) Switch to Metrics, show F1 scores
    - (1:20) "The extraction uses medSpaCy for section detection and negation handling, plus regex patterns for vitals — completely rule-based, no LLM dependency, deterministic and evaluatable."

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add portfolio-ready README"
```

---

### Task 31: End-to-end verification

- [ ] **Step 1: Start app locally**

```bash
# Terminal 1
source .venv/bin/activate
cd backend && python app.py

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173`

- [ ] **Step 2: Verify each verification checklist item from the spec**

```
1. Home page loads and shows synthetic data banner
2. Paste sample note → Extract → Review page shows highlights + fields
3. Upload a .txt file → Review page loads
4. Edit a field → Save → History shows corrected status with correction_count > 0
5. python scripts/seed_demo_data.py → 60 notes in History
6. python scripts/run_evaluation.py → prints summary; Metrics page shows data
7. pytest backend/tests/ -v → all pass
8. cd frontend && npm test → all pass
9. docker build . → succeeds
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and verification"
```

---
