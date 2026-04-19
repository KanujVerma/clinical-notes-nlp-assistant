# Session-Based Workspace Isolation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scope all notes/extractions/validations to a per-browser session ID so every live demo visitor has a private, isolated workspace.

**Architecture:** Add `session_id VARCHAR(36)` to the `notes` table; all child records (`extractions`, `validations`) are already linked via `note_id`, so filtering `notes` by `session_id` is sufficient. Frontend generates a UUID v4 on first visit, persists it under `clinical_nlp_session_id` in `localStorage`, and sends it as `X-Session-ID` on every request. Backend validates presence per-route via a `require_session()` helper.

**Tech Stack:** Flask, SQLAlchemy (SQLite in tests, Supabase Postgres in prod), React/Vite, TypeScript

---

## File Map

| Status | Path | Purpose |
|--------|------|---------|
| Modify | `backend/models/note.py` | Add `session_id` column |
| Modify | `backend/app.py` | Populate `g.session_id` in `before_request` |
| **Create** | `backend/utils/session.py` | `require_session()` helper |
| Modify | `backend/routes/notes.py` | Session guard + set + ownership on PUT |
| Modify | `backend/routes/upload.py` | Session guard + set |
| Modify | `backend/routes/queue.py` | Session guard + filter |
| Modify | `backend/routes/history.py` | Session guard + filter + ownership |
| Modify | `backend/routes/validate.py` | Session guard + ownership + next_pending filter |
| Modify | `backend/routes/metrics.py` | Session guard + join through Note |
| Modify | `backend/routes/seed.py` | Session guard + session-scoped idempotency + set |
| **Create** | `backend/routes/reset.py` | `DELETE /api/reset` — clear session workspace |
| Modify | `backend/app.py` | Register reset blueprint |
| Modify | `frontend/src/api/client.ts` | Generate/persist session ID; inject header |
| Modify | `frontend/src/components/AppShell.tsx` | Add reset workspace button with count confirmation |
| **Create** | `frontend/e2e/session-isolation.spec.ts` | Playwright isolation smoke test against production |
| Modify | `backend/tests/test_routes_history.py` | Add SID + session headers + new guard tests |
| Modify | `backend/tests/test_routes_queue.py` | Add SID + session headers + new guard tests |
| Modify | `backend/tests/test_routes_validate.py` | Add SID + session headers + new guard tests |
| Modify | `backend/tests/test_routes_metrics.py` | Add SID + session headers + new guard tests |
| Modify | `backend/tests/test_routes_upload.py` | Add SID + session headers + new guard tests |
| Modify | `backend/tests/test_routes_notes.py` | Add SID + session headers + new guard tests |
| **Create** | `backend/tests/test_routes_reset.py` | Tests for new reset route |
| No change | `backend/tests/test_routes_extract.py` | Extract is exempt; coverage provided by `test_utils_session.py` |

---

## Chunk 1: Foundation — Migration, Model, Helper, App

### Task 1: Run Supabase Migration

**Files:**
- No code files — SQL run manually against Supabase

- [ ] **Step 1: Get exact FK constraint names from Supabase SQL editor**

```sql
SELECT conname, conrelid::regclass
FROM pg_constraint
WHERE conrelid IN ('extractions'::regclass, 'validations'::regclass)
  AND contype = 'f';
```

Expected output: rows like `extractions_note_id_fkey`, `validations_note_id_fkey` (names may differ — use actual values in next step).

- [ ] **Step 2: Run migration SQL in Supabase SQL editor**

```sql
-- Add session_id column (VARCHAR(36) for UUID values)
ALTER TABLE notes ADD COLUMN session_id VARCHAR(36);

-- Index for fast session-scoped reads
CREATE INDEX idx_notes_session_id ON notes(session_id);

-- Re-add FK constraints with ON DELETE CASCADE
-- Replace constraint names with actual values from Step 1 if different
ALTER TABLE extractions DROP CONSTRAINT extractions_note_id_fkey;
ALTER TABLE extractions ADD CONSTRAINT extractions_note_id_fkey
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE;

ALTER TABLE validations DROP CONSTRAINT validations_note_id_fkey;
ALTER TABLE validations ADD CONSTRAINT validations_note_id_fkey
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE;

-- Delete all existing globally-seeded rows (explicit order — safe regardless of cascade state)
DELETE FROM validations;
DELETE FROM extractions;
DELETE FROM notes;
```

- [ ] **Step 3: Verify migration**

```sql
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'notes' AND column_name = 'session_id';

SELECT COUNT(*) FROM notes;  -- should be 0
```

Expected: `session_id | character varying | 36`, count = 0.

---

### Task 2: Add `session_id` to SQLAlchemy model

**Files:**
- Modify: `backend/models/note.py`

- [ ] **Step 1: Write failing test — model has session_id attribute**

Add to `backend/tests/test_db.py` (or create if not present):

```python
def test_note_has_session_id_column(engine):
    from models.note import Note
    col_names = [c.key for c in Note.__table__.columns]
    assert "session_id" in col_names
```

- [ ] **Step 2: Run test — expect failure**

```bash
cd backend && python -m pytest tests/test_db.py::test_note_has_session_id_column -v
```

Expected: FAIL (AttributeError or assertion error)

- [ ] **Step 3: Update `backend/models/note.py`**

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from models.base import Base

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # paste|txt|pdf|ocr|demo
    ocr_confidence = Column(Float, nullable=True)
    session_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Run test — expect pass**

```bash
cd backend && python -m pytest tests/test_db.py::test_note_has_session_id_column -v
```

Expected: PASS

- [ ] **Step 5: Confirm all existing tests still pass**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: All pass (session_id is nullable, nothing breaks)

- [ ] **Step 6: Commit**

```bash
git add backend/models/note.py backend/tests/test_db.py
git commit -m "feat: add session_id column to Note model"
```

---

### Task 3: Create `utils/session.py` helper

**Files:**
- Create: `backend/utils/session.py`
- Test: `backend/tests/test_utils_session.py` (new)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_utils_session.py`:

```python
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_missing_session_header_on_scoped_route_returns_400(client):
    # /api/notes is session-scoped; no header → 400
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "MISSING_SESSION_ID"

def test_empty_session_header_returns_400(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": "   "})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_valid_session_header_allows_request(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                       headers={"X-Session-ID": "test-session-abc"})
    assert resp.status_code == 201

def test_extract_is_exempt_from_session(client):
    # /api/extract has no DB writes — must remain exempt
    resp = client.post("/api/extract", json={"text": "BP: 120/80."})
    assert resp.status_code == 200

def test_health_is_exempt_from_session(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_utils_session.py -v
```

Expected: `test_missing_session_header_on_scoped_route_returns_400` PASSES (currently notes returns 201, so it FAILs) — all session-guard tests fail or pass wrong.

- [ ] **Step 3: Create `backend/utils/session.py`**

```python
from flask import g, jsonify, make_response, abort


def require_session() -> str:
    """Return session_id from g, or abort with 400 MISSING_SESSION_ID."""
    sid = g.get("session_id", "")
    if not sid:
        abort(make_response(
            jsonify({"error": "X-Session-ID header is required", "code": "MISSING_SESSION_ID"}),
            400,
        ))
    return sid
```

- [ ] **Step 4: Update `backend/app.py` — populate `g.session_id` in `before_request`**

Change the existing `open_session` function:

```python
@app.before_request
def open_session():
    from flask import g, request
    g.db = get_session(engine)
    g.session_id = request.headers.get("X-Session-ID", "").strip()
```

- [ ] **Step 5: Run session helper tests — still expect failure (routes not yet guarded)**

```bash
cd backend && python -m pytest tests/test_utils_session.py -v
```

Expected: `test_missing_session_header_on_scoped_route_returns_400` still FAILS (route has no guard yet). This confirms tests are real.

- [ ] **Step 6: Commit the helper and app change (without route guards yet)**

```bash
git add backend/utils/session.py backend/app.py
git commit -m "feat: add require_session helper and populate g.session_id in before_request"
```

---

## Chunk 2: Write Routes (notes, upload, seed)

> All three routes create `Note` objects. Guard + set `session_id`. Update their existing tests to pass the header.

### Task 4: Update `routes/notes.py`

**Files:**
- Modify: `backend/routes/notes.py`
- Modify: `backend/tests/test_routes_notes.py`

- [ ] **Step 1: Read existing test file**

```bash
cat backend/tests/test_routes_notes.py
```

- [ ] **Step 2: Add session guard tests to `test_routes_notes.py`**

Add `SID = "test-session-abc"` at the top and update all existing route calls to include `headers={"X-Session-ID": SID}`. Add new guard/isolation tests at the bottom:

```python
import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

# --- guard tests (new) ---

def test_create_note_missing_session_returns_400(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80."})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_update_note_text_missing_session_returns_400(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72."})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_update_note_text_wrong_session_returns_403(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72."},
                      headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"

# --- existing tests updated to include session header ---

def test_create_note_returns_201(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."},
                       headers={"X-Session-ID": SID})
    assert resp.status_code == 201
    data = resp.get_json()
    assert "note_id" in data
    assert "extracted_json" in data

def test_update_note_text_returns_200(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.put(f"/api/notes/{note_id}/text", json={"text": "HR: 72."},
                      headers={"X-Session-ID": SID})
    assert resp.status_code == 200
```

(Keep any other assertions from the original file, adding `headers={"X-Session-ID": SID}` to each route call.)

- [ ] **Step 3: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_notes.py -v
```

Expected: guard tests FAIL (no guard implemented yet), existing tests FAIL (guard not there, but also may fail differently).

- [ ] **Step 4: Implement `backend/routes/notes.py`**

```python
import json
from flask import Blueprint, request, jsonify, g
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from config import Config
from utils.session import require_session

bp = Blueprint("notes", __name__)


@bp.post("/api/notes")
def create_note():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required", "code": "MISSING_TEXT"}), 400

    extracted = run_pipeline(text)

    note = Note(raw_text=text, source="paste", session_id=sid)
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


@bp.put("/api/notes/<int:note_id>/text")
def update_note_text(note_id: int):
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required", "code": "TEXT_REQUIRED"}), 400

    note.raw_text = text
    g.db.query(Extraction).filter_by(note_id=note_id).delete()

    extracted = run_pipeline(text)
    extraction = Extraction(
        note_id=note_id,
        extracted_json=json.dumps(extracted),
        pipeline_version=Config.PIPELINE_VERSION,
    )
    g.db.add(extraction)
    g.db.commit()

    return jsonify({"note_id": note_id, "extracted_json": extracted}), 200
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_notes.py -v
```

Expected: All PASS

- [ ] **Step 6: Run full test suite — expect previous tests to fail on unguarded routes (that's fine)**

```bash
cd backend && python -m pytest --tb=line -q
```

Expected: `test_routes_notes.py` all pass; other route tests may now fail because they don't pass session headers yet — this is expected and will be fixed in subsequent tasks.

- [ ] **Step 7: Commit**

```bash
git add backend/routes/notes.py backend/tests/test_routes_notes.py
git commit -m "feat: add session guard to notes routes"
```

---

### Task 5: Update `routes/upload.py`

**Files:**
- Modify: `backend/routes/upload.py`
- Modify: `backend/tests/test_routes_upload.py`

- [ ] **Step 1: Read existing test file**

```bash
cat backend/tests/test_routes_upload.py
```

- [ ] **Step 2: Add SID constant + guard test + update existing calls**

Add at top of `test_routes_upload.py`:
```python
SID = "test-session-abc"
```

Add guard test:
```python
def test_upload_missing_session_returns_400(client):
    import io
    data = {"file": (io.BytesIO(b"BP: 120/80."), "note.txt")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"
```

Update all existing upload calls to include `headers={"X-Session-ID": SID}`.

- [ ] **Step 3: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_upload.py -v
```

- [ ] **Step 4: Update `backend/routes/upload.py`**

Add `from utils.session import require_session` import. At the top of the `upload()` function, before any other logic, add:

```python
@bp.post("/api/upload")
def upload():
    sid = require_session()
    # ... rest of existing code unchanged ...
```

Then change the `Note(...)` construction line to:

```python
note = Note(filename=f.filename, raw_text=text, source=source,
            ocr_confidence=ocr_confidence, session_id=sid)
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_upload.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/routes/upload.py backend/tests/test_routes_upload.py
git commit -m "feat: add session guard to upload route"
```

---

### Task 6: Update `routes/seed.py`

**Files:**
- Modify: `backend/routes/seed.py`
- Test: add to `backend/tests/test_routes_extract.py` or a new `test_routes_seed.py`

- [ ] **Step 1: Write failing tests for seed guard and isolation**

Create `backend/tests/test_routes_seed.py`:

```python
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db"),
        "DATA_DIR": str(tmp_path / "data"),  # no seed files → loaded=0
    })
    with app.test_client() as c:
        yield c

def test_seed_missing_session_returns_400(client):
    resp = client.post("/api/seed-demo")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_seed_with_session_returns_200(client):
    resp = client.post("/api/seed-demo", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "loaded" in data
    assert "skipped" in data
```

- [ ] **Step 2: Run tests — expect failure on guard test**

```bash
cd backend && python -m pytest tests/test_routes_seed.py -v
```

- [ ] **Step 3: Update `backend/routes/seed.py`**

```python
import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from extractors.pipeline import run_pipeline
from config import Config
from utils.session import require_session

bp = Blueprint("seed", __name__)
_SEED_SOURCES = ["dev", "showcase"]


def seed_notes(db_session, session_id: str) -> dict:
    loaded = 0
    skipped = 0
    for source_dir in _SEED_SOURCES:
        notes_dir = os.path.join(Config.DATA_DIR, source_dir, "notes")
        if not os.path.isdir(notes_dir):
            continue
        for fname in sorted(os.listdir(notes_dir)):
            if not fname.endswith(".txt"):
                continue
            # Idempotency scoped to this session
            existing = db_session.execute(
                select(Note).where(Note.filename == fname,
                                   Note.session_id == session_id)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue
            fpath = os.path.join(notes_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
            extracted = run_pipeline(text)
            note = Note(filename=fname, raw_text=text, source="demo",
                        session_id=session_id)
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
    sid = require_session()
    result = seed_notes(g.db, sid)
    return jsonify(result)
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_seed.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/seed.py backend/tests/test_routes_seed.py
git commit -m "feat: add session guard and scoped idempotency to seed route"
```

---

## Chunk 3: Read Routes (queue, history, validate)

### Task 7: Update `routes/queue.py`

**Files:**
- Modify: `backend/routes/queue.py`
- Modify: `backend/tests/test_routes_queue.py`

- [ ] **Step 1: Add SID constant and update `test_routes_queue.py`**

At top of file add:
```python
SID = "test-session-abc"
SID2 = "other-session-xyz"
```

Add guard test:
```python
def test_queue_missing_session_returns_400(client):
    resp = client.get("/api/queue")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"
```

Add isolation test:
```python
def test_queue_isolates_by_session(client):
    # Session 1 creates a note
    client.post("/api/notes", json={"text": "BP: 120/80."},
                headers={"X-Session-ID": SID})
    # Session 2 should see empty queue
    resp = client.get("/api/queue", headers={"X-Session-ID": SID2})
    assert resp.get_json()["count"] == 0
```

Update all existing helper functions and route calls:
```python
def _create_note(client, text="BP: 120/80. HR: 72.", sid=SID):
    resp = client.post("/api/notes", json={"text": text},
                       headers={"X-Session-ID": sid})
    assert resp.status_code == 201
    return resp.get_json()["note_id"]

def _validate_note(client, note_id, sid=SID):
    resp = client.post(
        "/api/validate",
        json={
            "note_id": note_id,
            "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
            "status": "accepted",
            "review_duration_ms": 100,
        },
        headers={"X-Session-ID": sid},
    )
    return resp
```

Add `headers={"X-Session-ID": SID}` to all `client.get("/api/queue")` calls.

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_queue.py -v
```

- [ ] **Step 3: Update `backend/routes/queue.py`**

```python
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("queue", __name__)


@bp.get("/api/queue")
def get_queue():
    sid = require_session()
    stmt = (
        select(Note)
        .join(Extraction, Extraction.note_id == Note.id)
        .outerjoin(Validation, Validation.note_id == Note.id)
        .where(Validation.id == None)  # noqa: E711
        .where(Note.session_id == sid)
        .order_by(Note.created_at.asc())
    )
    notes = g.db.execute(stmt).scalars().all()

    result = [
        {
            "id": note.id,
            "filename": note.filename,
            "source": note.source,
            "created_at": note.created_at.isoformat() if note.created_at else None,
        }
        for note in notes
    ]

    return jsonify({"notes": result, "count": len(result)})
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_queue.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/queue.py backend/tests/test_routes_queue.py
git commit -m "feat: add session guard and isolation filter to queue route"
```

---

### Task 8: Update `routes/history.py`

**Files:**
- Modify: `backend/routes/history.py`
- Modify: `backend/tests/test_routes_history.py`

- [ ] **Step 1: Update `test_routes_history.py`**

Add at top:
```python
SID = "test-session-abc"
SID2 = "other-session-xyz"
```

Update `seeded_client` fixture and all route calls:
```python
@pytest.fixture
def seeded_client(client):
    client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."},
                headers={"X-Session-ID": SID})
    return client
```

Add guard and isolation tests:
```python
def test_history_missing_session_returns_400(client):
    resp = client.get("/api/history")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_history_detail_missing_session_returns_400(client):
    resp = client.get("/api/history/1")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_history_isolates_by_session(client):
    client.post("/api/notes", json={"text": "BP: 120/80."},
                headers={"X-Session-ID": SID})
    resp = client.get("/api/history", headers={"X-Session-ID": SID2})
    assert resp.get_json()["notes"] == []

def test_history_detail_wrong_session_returns_403(client):
    note_id = client.post("/api/notes", json={"text": "BP: 120/80."},
                          headers={"X-Session-ID": SID}).get_json()["note_id"]
    resp = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"
```

Update existing test calls to add `headers={"X-Session-ID": SID}`.

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_history.py -v
```

- [ ] **Step 3: Update `backend/routes/history.py`**

```python
import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select, desc
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("history", __name__)


@bp.get("/api/history")
def list_history():
    sid = require_session()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page

    notes = g.db.execute(
        select(Note)
        .where(Note.session_id == sid)
        .order_by(desc(Note.created_at))
        .limit(per_page)
        .offset(offset)
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
    sid = require_session()
    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

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

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_history.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/history.py backend/tests/test_routes_history.py
git commit -m "feat: add session guard, filter, and ownership check to history routes"
```

---

### Task 9: Update `routes/validate.py`

**Files:**
- Modify: `backend/routes/validate.py`
- Modify: `backend/tests/test_routes_validate.py`

- [ ] **Step 1: Update `test_routes_validate.py`**

Add at top:
```python
SID = "test-session-abc"
SID2 = "other-session-xyz"
```

Update the `note_id` fixture and existing calls:
```python
@pytest.fixture
def note_id(client):
    resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."},
                       headers={"X-Session-ID": SID})
    return resp.get_json()["note_id"]
```

Add guard and cross-session tests:
```python
def test_validate_missing_session_returns_400(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    })
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_validate_wrong_session_returns_403(client, note_id):
    resp = client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID2})
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"

def test_next_pending_id_stays_within_session(client):
    """next_pending_id must not leak note IDs from other sessions."""
    sid_a = "session-a"
    sid_b = "session-b"
    # Session A creates note
    note_a = client.post("/api/notes", json={"text": "BP: 120/80."},
                         headers={"X-Session-ID": sid_a}).get_json()["note_id"]
    # Session B creates note
    note_b = client.post("/api/notes", json={"text": "HR: 72."},
                         headers={"X-Session-ID": sid_b}).get_json()["note_id"]
    # Session A validates its note — next_pending should be None (no more in session A)
    resp = client.post("/api/validate", json={
        "note_id": note_a,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": sid_a})
    assert resp.status_code == 200
    assert resp.get_json()["next_pending_id"] is None  # session B's note must NOT appear
```

Update all existing test calls to include `headers={"X-Session-ID": SID}`. In particular, `test_validate_upserts` calls `client.get(f"/api/history/{note_id}")` — that call must also get the header, since history is session-scoped after Task 8:

```python
def test_validate_upserts(client, note_id):
    payload = {
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
        "review_duration_ms": 3000,
    }
    client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    payload["status"] = "corrected"
    resp = client.post("/api/validate", json=payload, headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    detail = client.get(f"/api/history/{note_id}", headers={"X-Session-ID": SID}).get_json()
    assert detail["validation"]["status"] == "corrected"
```

Also update `test_validate_next_pending_id_returns_unvalidated_note` — every `/api/notes` and `/api/validate` call needs `headers={"X-Session-ID": SID}`.

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_validate.py -v
```

- [ ] **Step 3: Update `backend/routes/validate.py`**

```python
import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.corrections import compute_correction_count
from utils.session import require_session

bp = Blueprint("validate", __name__)


@bp.post("/api/validate")
def validate():
    sid = require_session()
    body = request.get_json(silent=True) or {}
    note_id = body.get("note_id")
    validated_json = body.get("validated_json")
    status = body.get("status")
    if not note_id or validated_json is None or not status:
        return jsonify({"error": "note_id, validated_json, and status are required",
                        "code": "MISSING_FIELDS"}), 400

    note = g.db.get(Note, note_id)
    if not note:
        return jsonify({"error": "Note not found", "code": "NOT_FOUND"}), 404
    if note.session_id != sid:
        return jsonify({"error": "Forbidden", "code": "FORBIDDEN"}), 403

    extraction = g.db.execute(
        select(Extraction).where(Extraction.note_id == note_id)
    ).scalar_one_or_none()
    extracted = json.loads(extraction.extracted_json) if extraction else {}
    correction_count = compute_correction_count(extracted, validated_json)

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

    next_pending = g.db.execute(
        select(Note.id)
        .join(Extraction, Extraction.note_id == Note.id)
        .outerjoin(Validation, Validation.note_id == Note.id)
        .where(Validation.id == None)  # noqa: E711
        .where(Note.id != note_id)
        .where(Note.session_id == sid)
        .order_by(Note.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    return jsonify({"message": "Validation saved", "correction_count": correction_count,
                    "next_pending_id": next_pending})
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_validate.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/validate.py backend/tests/test_routes_validate.py
git commit -m "feat: add session guard, ownership check, and session-scoped next_pending to validate route"
```

---

## Chunk 4: Metrics, Seed Tests, Reset Route

### Task 10: Update `routes/metrics.py`

**Files:**
- Modify: `backend/routes/metrics.py`
- Modify: `backend/tests/test_routes_metrics.py`

- [ ] **Step 1: Update `test_routes_metrics.py`**

Add at top:
```python
SID = "test-session-abc"
SID2 = "other-session-xyz"
```

Add guard and isolation tests:
```python
def test_metrics_missing_session_returns_400(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_metrics_isolates_by_session(client):
    """Session B's validations must not appear in Session A's metrics."""
    # Session B creates and validates a note with corrections
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                            headers={"X-Session-ID": SID2})
    note_id = note_resp.get_json()["note_id"]
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {"blood_pressure": {"value": "999/999"}},
                           "medications": [], "instructions": {}, "metadata": {}},
        "status": "corrected",
    }, headers={"X-Session-ID": SID2})

    # Session A metrics should be empty
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    data = resp.get_json()
    assert data["db_stats"]["by_status"] == []
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert data["db_stats"]["correction_rates"]["by_category"][cat]["reviewed"] == 0
```

The three existing metric tests must be updated to pass session headers on every route call. Replace them with:

```python
def test_metrics_has_correction_rates_key(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "correction_rates" in data["db_stats"]


def test_metrics_correction_rates_shape_when_empty(client):
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    assert "by_category" in rates
    assert "by_field" in rates
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert cat in rates["by_category"]


def test_metrics_correction_rates_after_validation(client):
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80. HR: 72."},
                            headers={"X-Session-ID": SID})
    note_id = note_resp.get_json()["note_id"]
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {
            "vitals": {"blood_pressure": {"value": "130/85"}},
            "medications": [], "instructions": {}, "metadata": {},
        },
        "status": "corrected",
    }, headers={"X-Session-ID": SID})

    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    assert "vitals.blood_pressure" in rates["by_field"]
    assert rates["by_field"]["vitals.blood_pressure"]["reviewed"] >= 1
    assert rates["by_field"]["vitals.blood_pressure"]["corrected"] >= 1
    assert rates["by_category"]["vitals"]["rate"] > 0


def test_metrics_correction_rate_zero_when_no_corrections(client):
    note_resp = client.post("/api/notes", json={"text": "BP: 120/80."},
                            headers={"X-Session-ID": SID})
    note_id = note_resp.get_json()["note_id"]
    history = client.get(f"/api/history/{note_id}",
                         headers={"X-Session-ID": SID}).get_json()
    extracted = history["extracted_json"]
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": extracted,
        "status": "accepted",
    }, headers={"X-Session-ID": SID})
    resp = client.get("/api/metrics", headers={"X-Session-ID": SID})
    rates = resp.get_json()["db_stats"]["correction_rates"]
    for cat in ("vitals", "medications", "instructions", "metadata"):
        assert rates["by_category"][cat]["corrected"] == 0
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd backend && python -m pytest tests/test_routes_metrics.py -v
```

- [ ] **Step 3: Update `backend/routes/metrics.py`**

```python
import json, os
from flask import Blueprint, jsonify, g
from sqlalchemy import select, func
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from config import Config
from utils.session import require_session

bp = Blueprint("metrics", __name__)

_CATEGORIES = ("vitals", "medications", "instructions", "metadata")


def _compute_correction_rates(validations):
    by_category = {cat: {"reviewed": 0, "corrected": 0} for cat in _CATEGORIES}
    by_field = {}

    for ext_json, val_json in validations:
        try:
            extracted = json.loads(ext_json) if isinstance(ext_json, str) else ext_json
            validated = json.loads(val_json) if isinstance(val_json, str) else val_json
        except (json.JSONDecodeError, TypeError):
            continue

        for cat in ("vitals", "instructions", "metadata"):
            ext_sec = extracted.get(cat) or {}
            val_sec = validated.get(cat) or {}
            if not isinstance(ext_sec, dict) or not isinstance(val_sec, dict):
                continue
            all_keys = set(ext_sec) | set(val_sec)
            for key in all_keys:
                field_key = f"{cat}.{key}"
                if field_key not in by_field:
                    by_field[field_key] = {"reviewed": 0, "corrected": 0}
                by_field[field_key]["reviewed"] += 1
                by_category[cat]["reviewed"] += 1
                if key not in ext_sec or key not in val_sec:
                    by_field[field_key]["corrected"] += 1
                    by_category[cat]["corrected"] += 1
                else:
                    ext_val = str(ext_sec[key].get("value", "") if isinstance(ext_sec[key], dict) else ext_sec[key]).strip()
                    val_val = str(val_sec[key].get("value", "") if isinstance(val_sec[key], dict) else val_sec[key]).strip()
                    if ext_val != val_val:
                        by_field[field_key]["corrected"] += 1
                        by_category[cat]["corrected"] += 1

        ext_meds = {m.get("name", "").lower().strip(): m for m in (extracted.get("medications") or [])}
        val_meds = {m.get("name", "").lower().strip(): m for m in (validated.get("medications") or [])}
        for k in set(ext_meds) | set(val_meds):
            by_category["medications"]["reviewed"] += 1
            if k not in ext_meds or k not in val_meds:
                by_category["medications"]["corrected"] += 1
            else:
                e, v = ext_meds[k], val_meds[k]
                for field in ("name", "dose", "route", "frequency"):
                    if e.get(field, "").strip() != v.get(field, "").strip():
                        by_category["medications"]["corrected"] += 1
                        break

    def _with_rate(d):
        reviewed, corrected = d["reviewed"], d["corrected"]
        return {"reviewed": reviewed, "corrected": corrected,
                "rate": round(corrected / reviewed, 4) if reviewed else 0.0}

    return {
        "by_category": {cat: _with_rate(by_category[cat]) for cat in _CATEGORIES},
        "by_field": {k: _with_rate(v) for k, v in by_field.items()},
    }


@bp.get("/api/metrics")
def metrics():
    sid = require_session()
    from flask import current_app
    eval_results_path = current_app.config.get("EVAL_RESULTS_PATH", Config.EVAL_RESULTS_PATH)
    eval_data = None
    if os.path.exists(eval_results_path):
        with open(eval_results_path) as f:
            eval_data = json.load(f)

    # Stats by status — join through Note to scope by session
    rows = g.db.execute(
        select(
            Validation.status,
            func.count().label("count"),
            func.avg(Validation.correction_count).label("avg_corrections"),
            func.avg(Validation.review_duration_ms).label("avg_review_ms"),
        )
        .join(Note, Note.id == Validation.note_id)
        .where(Note.session_id == sid)
        .group_by(Validation.status)
    ).all()

    # Per-category correction rates — join through Note to scope by session
    val_rows = g.db.execute(
        select(Extraction.extracted_json, Validation.validated_json)
        .join(Note, Note.id == Extraction.note_id)
        .join(Validation, Validation.note_id == Extraction.note_id)
        .where(Note.session_id == sid)
    ).all()
    correction_rates = _compute_correction_rates(
        [(r.extracted_json, r.validated_json) for r in val_rows]
    )

    db_stats = {
        "by_status": [
            {
                "status": r.status,
                "count": r.count,
                "avg_corrections": round(r.avg_corrections or 0, 2),
                "avg_review_ms": round(r.avg_review_ms or 0),
            }
            for r in rows
        ],
        "correction_rates": correction_rates,
    }

    return jsonify({"eval": eval_data, "db_stats": db_stats})
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_metrics.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/metrics.py backend/tests/test_routes_metrics.py
git commit -m "feat: add session guard and session-scoped joins to metrics route"
```

---

### Task 11: Create `routes/reset.py`

**Files:**
- Create: `backend/routes/reset.py`
- Modify: `backend/app.py` (register blueprint)
- Create: `backend/tests/test_routes_reset.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_routes_reset.py`:

```python
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

SID = "test-session-abc"
SID2 = "other-session-xyz"

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///" + str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def _seed(client, text="BP: 120/80.", sid=SID):
    return client.post("/api/notes", json={"text": text},
                       headers={"X-Session-ID": sid}).get_json()["note_id"]

def test_reset_missing_session_returns_400(client):
    resp = client.delete("/api/reset")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_SESSION_ID"

def test_reset_empty_workspace_returns_zero_counts(client):
    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"deleted_notes": 0, "deleted_extractions": 0, "deleted_validations": 0}

def test_reset_deletes_only_current_session(client):
    _seed(client, sid=SID)
    _seed(client, sid=SID2)

    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert resp.status_code == 200
    assert resp.get_json()["deleted_notes"] == 1

    # SID2's note should still be visible
    queue = client.get("/api/queue", headers={"X-Session-ID": SID2})
    assert queue.get_json()["count"] == 1

def test_reset_returns_correct_counts(client):
    note_id = _seed(client)
    # Also create a validation for it
    client.post("/api/validate", json={
        "note_id": note_id,
        "validated_json": {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}},
        "status": "accepted",
    }, headers={"X-Session-ID": SID})

    resp = client.delete("/api/reset", headers={"X-Session-ID": SID})
    data = resp.get_json()
    assert data["deleted_notes"] == 1
    assert data["deleted_extractions"] == 1
    assert data["deleted_validations"] == 1

def test_reset_clears_queue_and_history(client):
    _seed(client)
    _seed(client)
    client.delete("/api/reset", headers={"X-Session-ID": SID})
    assert client.get("/api/queue", headers={"X-Session-ID": SID}).get_json()["count"] == 0
    assert client.get("/api/history", headers={"X-Session-ID": SID}).get_json()["notes"] == []
```

- [ ] **Step 2: Run tests — expect failures (route doesn't exist)**

```bash
cd backend && python -m pytest tests/test_routes_reset.py -v
```

Expected: All fail with 404 or similar.

- [ ] **Step 3: Create `backend/routes/reset.py`**

```python
from flask import Blueprint, jsonify, g
from sqlalchemy import select
from models.note import Note
from models.extraction import Extraction
from models.validation import Validation
from utils.session import require_session

bp = Blueprint("reset", __name__)


@bp.delete("/api/reset")
def reset_workspace():
    sid = require_session()

    note_ids = list(g.db.execute(
        select(Note.id).where(Note.session_id == sid)
    ).scalars())

    if not note_ids:
        return jsonify({"deleted_notes": 0, "deleted_extractions": 0, "deleted_validations": 0})

    # Count before deleting (counts become unavailable after delete)
    deleted_extractions = g.db.query(Extraction).filter(
        Extraction.note_id.in_(note_ids)
    ).count()
    deleted_validations = g.db.query(Validation).filter(
        Validation.note_id.in_(note_ids)
    ).count()

    # Explicit child deletes — SQLite does not enforce FK cascade by default
    g.db.query(Validation).filter(Validation.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Extraction).filter(Extraction.note_id.in_(note_ids)).delete(synchronize_session=False)
    g.db.query(Note).filter(Note.session_id == sid).delete(synchronize_session=False)
    g.db.commit()

    return jsonify({
        "deleted_notes": len(note_ids),
        "deleted_extractions": deleted_extractions,
        "deleted_validations": deleted_validations,
    })
```

- [ ] **Step 4: Register blueprint in `backend/app.py`**

In the blueprints section, add:
```python
from routes.reset import bp as reset_bp
app.register_blueprint(reset_bp)
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
cd backend && python -m pytest tests/test_routes_reset.py -v
```

- [ ] **Step 6: Run full backend test suite**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add backend/routes/reset.py backend/app.py backend/tests/test_routes_reset.py
git commit -m "feat: add DELETE /api/reset route for session workspace cleanup"
```

---

## Chunk 5: Frontend

### Task 12: Update `frontend/src/api/client.ts`

**Files:**
- Modify: `frontend/src/api/client.ts`

> The frontend has no server-side test runner; verify by running the dev server and inspecting browser DevTools (Network tab and Application > localStorage).

- [ ] **Step 1: Update `frontend/src/api/client.ts`**

```typescript
// frontend/src/api/client.ts
import { QueueResponse } from "../types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api";

const SESSION_KEY = "clinical_nlp_session_id";

function getOrCreateSessionId(): string {
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

const SESSION_ID = getOrCreateSessionId();

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Session-ID": SESSION_ID,
      ...(options?.headers ?? {}),
    },
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
    return fetch(`${BASE}/upload`, {
      method: "POST",
      headers: { "X-Session-ID": SESSION_ID },
      body: form,
    }).then(async (r) => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({ error: r.statusText }));
        throw new Error(err.error || "Upload failed");
      }
      return r.json() as Promise<{
        note_id: number;
        extracted_json: any;
        raw_text: string;
        ocr_confidence: number | null;
        source: string;
      }>;
    });
  },

  validate: (payload: {
    note_id: number;
    validated_json: any;
    status: string;
    review_duration_ms: number;
  }) =>
    request<{ ok: boolean; correction_count: number; next_pending_id: number | null }>("/validate", {
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

  getQueue: () => request<QueueResponse>("/queue"),

  updateNoteText: (noteId: number, text: string) =>
    request<{ note_id: number; extracted_json: any }>(`/notes/${noteId}/text`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),

  resetWorkspace: () =>
    request<{ deleted_notes: number; deleted_extractions: number; deleted_validations: number }>(
      "/reset",
      { method: "DELETE" }
    ),
};
```

Note: `options` is spread first, then `headers` is built last so `X-Session-ID` is always present even if a caller passes custom headers in `options.headers`. The header is intentionally sent on all routes including `/api/extract` — extract ignores it (it's stateless), but sending it is harmless and keeps the client logic uniform.

- [ ] **Step 2: Verify session ID is generated**

Start dev servers and open browser DevTools → Application → Local Storage → `localhost:5173`:
- Key `clinical_nlp_session_id` should appear with a UUID value on first load
- Refresh — same UUID should persist

- [ ] **Step 3: Verify header is sent on requests**

DevTools → Network tab → click any API call → Headers → Request Headers:
- `X-Session-ID: <uuid>` should appear on every `/api/*` request except `/api/extract`

- [ ] **Step 4: Verify two sessions are isolated**

Open a normal window and an incognito window. In each:
1. Open the site
2. Upload a note or use "Seed demo data"
3. Both windows should have different data in History and Queue

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: generate persistent session ID and inject X-Session-ID header on all API calls"
```

---

---

## Chunk 6: Frontend Reset UI + Playwright Smoke Test

### Task 13: Add reset button to AppShell sidebar

**Files:**
- Modify: `frontend/src/components/AppShell.tsx`

The reset button lives at the bottom of the sidebar. On click it calls `api.resetWorkspace()` and shows a `window.alert` confirmation with the delete counts (no new UI component required — keeps it minimal).

- [ ] **Step 1: Update `frontend/src/components/AppShell.tsx`**

Add a "Workspace" section at the bottom of `<nav>`, after the Pending Review section, and wire up the reset action:

```tsx
// frontend/src/components/AppShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useMatch } from "react-router-dom";
import { api } from "../api/client";
import { QueueNote } from "../types";
import { useQueue } from "../context/QueueContext";

function NavItem({
  to,
  label,
  badge,
}: {
  to: string;
  label: string;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `flex items-center justify-between px-3 py-1.5 rounded-md text-sm transition-colors ${
          isActive
            ? "bg-slate-700 text-slate-100"
            : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        }`
      }
    >
      <span>{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="ml-2 inline-flex items-center justify-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500 text-slate-900 min-w-[18px]">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

export default function AppShell() {
  const reviewMatch = useMatch("/review/:noteId");
  const activeNoteId = reviewMatch?.params.noteId;
  const { queueVersion } = useQueue();
  const [pendingNotes, setPendingNotes] = useState<QueueNote[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    api.getQueue().then((data) => {
      setPendingCount(data.count);
      setPendingNotes(data.notes.slice(0, 8));
    }).catch(() => {});
  }, [queueVersion]);

  async function handleReset() {
    if (!window.confirm("Reset your workspace? This deletes all your notes and validations.")) return;
    setResetting(true);
    try {
      const result = await api.resetWorkspace();
      window.alert(
        `Workspace cleared — ${result.deleted_notes} note(s), ` +
        `${result.deleted_extractions} extraction(s), ` +
        `${result.deleted_validations} validation(s) deleted.`
      );
      window.location.href = "/";
    } catch {
      window.alert("Reset failed — please try again.");
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="flex h-screen bg-slate-900 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[220px] flex-shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-slate-700">
          <span className="text-slate-100 font-semibold text-sm tracking-wide">Clinical NLP</span>
          <p className="text-slate-500 text-[10px] mt-0.5">Demo mode — synthetic data</p>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
          {/* Pipeline group */}
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              Pipeline
            </p>
            <div className="space-y-0.5">
              <NavItem to="/" label="Upload" />
              <NavItem to="/queue" label="Queue" badge={pendingCount} />
            </div>
          </div>

          {/* Data group */}
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              Data
            </p>
            <div className="space-y-0.5">
              <NavItem to="/history" label="History" />
              <NavItem to="/metrics" label="Metrics" />
            </div>
          </div>

          {/* Pending Review section */}
          {pendingNotes.length > 0 && (
            <div>
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Pending Review
              </p>
              <div className="space-y-0.5">
                {pendingNotes.map((note) => (
                  <NavLink
                    key={note.id}
                    to={`/review/${note.id}`}
                    className={`block px-3 py-1.5 rounded-md text-xs transition-colors truncate ${
                      activeNoteId === String(note.id)
                        ? "bg-cyan-900 text-cyan-300 border border-cyan-700"
                        : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    }`}
                    title={note.filename ?? `Note #${note.id}`}
                  >
                    {note.filename ?? `Note #${note.id}`}
                  </NavLink>
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* Workspace reset — bottom of sidebar */}
        <div className="px-2 py-3 border-t border-slate-700">
          <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Workspace
          </p>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="w-full text-left px-3 py-1.5 rounded-md text-xs text-slate-400 hover:bg-slate-800 hover:text-red-400 transition-colors disabled:opacity-50"
          >
            {resetting ? "Resetting…" : "Reset workspace"}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify reset button renders**

Start the dev server and open the app. The sidebar should show "Workspace / Reset workspace" at the bottom. Clicking it shows a confirmation dialog; confirming calls the API and shows an alert with counts.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppShell.tsx
git commit -m "feat: add reset workspace button to sidebar with delete count confirmation"
```

---

### Task 14: Playwright session isolation smoke test

**Files:**
- Create: `frontend/e2e/session-isolation.spec.ts`

This test runs against the **production** URL. Both servers must NOT be required locally — the test hits production directly. The Playwright config's `baseURL` is ignored in favour of the hardcoded URL below.

- [ ] **Step 1: Create `frontend/e2e/session-isolation.spec.ts`**

```typescript
/**
 * Session isolation smoke test — production.
 * Verifies that two independent browser contexts have isolated workspaces.
 *
 * Target: https://clinical-nlp.vercel.app
 * Run: npx playwright test e2e/session-isolation.spec.ts --headed
 *
 * Both sessions seed demo data. Isolation is confirmed by comparing
 * the session IDs stored in localStorage — they must differ.
 * Each session's history is only populated after seeding in that context.
 */
import { test, expect, Browser, BrowserContext, Page } from "@playwright/test";

const PROD = "https://clinical-nlp.vercel.app";
const SESSION_KEY = "clinical_nlp_session_id";

async function getSessionId(page: Page): Promise<string> {
  return page.evaluate(
    (key) => localStorage.getItem(key) ?? "",
    SESSION_KEY
  );
}

async function seedAndWait(page: Page) {
  page.on("dialog", (d) => d.accept());
  await page.getByRole("button", { name: /Seed demo data/i }).click();
  await expect(page.getByText(/Seeded|already exist/i)).toBeVisible({ timeout: 15_000 });
}

async function getHistoryCount(page: Page): Promise<number> {
  await page.goto(`${PROD}/history`);
  const rows = page.locator("table tbody tr");
  await rows.first().waitFor({ state: "attached", timeout: 10_000 }).catch(() => {});
  return rows.count();
}

test.describe("Session isolation — production", () => {
  let browser: Browser;
  let ctx1: BrowserContext;
  let ctx2: BrowserContext;
  let page1: Page;
  let page2: Page;

  test.beforeAll(async ({ browser: b }) => {
    browser = b;
    // ctx1 = normal window; ctx2 = fresh incognito-equivalent context
    ctx1 = await browser.newContext();
    ctx2 = await browser.newContext();
    page1 = await ctx1.newPage();
    page2 = await ctx2.newPage();
  });

  test.afterAll(async () => {
    await ctx1.close();
    await ctx2.close();
  });

  test("each context gets a unique session ID", async () => {
    await page1.goto(PROD);
    await page2.goto(PROD);

    const sid1 = await getSessionId(page1);
    const sid2 = await getSessionId(page2);

    expect(sid1).toBeTruthy();
    expect(sid2).toBeTruthy();
    expect(sid1).not.toEqual(sid2);
  });

  test("seeding in one context does not populate the other", async () => {
    // Seed in context 1
    await page1.goto(PROD);
    await seedAndWait(page1);

    // Context 2 should still have empty history
    const count2 = await getHistoryCount(page2);
    expect(count2).toBe(0);
  });

  test("seeding in context 2 gives it its own workspace", async () => {
    await page2.goto(PROD);
    await seedAndWait(page2);

    const count2 = await getHistoryCount(page2);
    expect(count2).toBeGreaterThan(0);
  });

  test("context 1 history is unaffected by context 2 seeding", async () => {
    const count1Before = await getHistoryCount(page1);
    // Seed again in ctx2 — ctx1 count must not change
    await page2.goto(PROD);
    await seedAndWait(page2);
    const count1After = await getHistoryCount(page1);
    expect(count1After).toEqual(count1Before);
  });

  test("session ID persists across refresh in context 1", async () => {
    await page1.goto(PROD);
    const sidBefore = await getSessionId(page1);

    await page1.reload();
    const sidAfter = await getSessionId(page1);

    expect(sidAfter).toEqual(sidBefore);
  });

  test("history persists after refresh in context 1", async () => {
    const countBefore = await getHistoryCount(page1);
    await page1.reload();
    const countAfter = await getHistoryCount(page1);
    expect(countAfter).toEqual(countBefore);
  });
});
```

- [ ] **Step 2: Run the smoke test against production**

Make sure both backends are deployed first (Task 15). Then run:

```bash
cd frontend && npx playwright test e2e/session-isolation.spec.ts --headed --project=chromium
```

Expected: All 6 tests pass. Two windows open in Chrome — each shows its own isolated workspace.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/session-isolation.spec.ts
git commit -m "test: add Playwright session isolation smoke test against production"
```

---

## Chunk 7: Integration Verification + Deploy

### Task 15: Full test suite + deploy

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && python -m pytest --tb=short -q
```

Expected: All pass, no failures.

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npm run build
```

Expected: Zero type errors, build succeeds.

- [ ] **Step 3: Deploy backend (Render)**

Push to main or trigger deploy from Render dashboard. Confirm the new `session_id` column is present in Supabase (migration was run in Task 1). Confirm health endpoint responds: `GET /api/health`.

- [ ] **Step 4: Deploy frontend**

```bash
cd frontend && vercel --prod
```

- [ ] **Step 5: Smoke test on production**

1. Open `https://clinical-nlp.vercel.app` in a fresh incognito window
2. Check DevTools → Application → Local Storage → key `clinical_nlp_session_id` exists
3. Click "Seed demo data" — notes should appear in Queue and History
4. Open a second incognito window — History and Queue should be empty
5. The two windows should have completely independent workspaces
6. Refresh window 1 — data should persist (same session ID)

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: verify session isolation — all tests pass, prod deployed"
```
