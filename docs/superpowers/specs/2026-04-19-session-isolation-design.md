# Session-Based Workspace Isolation

**Date:** 2026-04-19
**Status:** Approved

## Problem

The live demo app uses a single shared database with no user scoping. Any visitor's uploads, validations, and seeded demo data are visible to every other visitor. This breaks the demo experience.

## Goal

Each visitor gets an isolated, private workspace — persisted across page refreshes via `localStorage` — with no login required.

## Approach

Add a `session_id` column to the `notes` table. Since `extractions` and `validations` both join through `note_id`, filtering `notes` by `session_id` is sufficient to isolate all data. The frontend generates a UUID v4 on first visit, stores it in `localStorage`, and sends it as `X-Session-ID` on every API request.

## Requirements

1. **No silent fallback.** If `X-Session-ID` is missing, absent, or empty (after `.strip()`) on any session-scoped route, return `400 MISSING_SESSION_ID`. Never fall back to global/shared reads.
2. **Strict read filters.** All reads use `Note.session_id == g.session_id`. Old `NULL` rows are never surfaced, even if they exist in the DB.
3. **Ownership checks.** Before returning or mutating a note, verify `note.session_id == g.session_id`. Return `403 FORBIDDEN` otherwise.
4. **Seed scoping.** `POST /api/seed-demo` seeds notes tagged with the requesting session's ID only. The idempotency check must also be session-scoped (see seed route section).
5. **Reset.** `DELETE /api/reset` deletes all notes for the session (cascade handles extractions/validations). Returns counts (see Reset section).
6. **Stateless extraction unchanged.** `POST /api/extract` is pure NLP with no DB writes — no session header required.
7. **Clean state.** All existing globally-seeded rows are deleted from Supabase before shipping.

## Data Model Change

```sql
-- Step 1: Add session_id (nullable for backward compat with existing NULL rows)
ALTER TABLE notes ADD COLUMN session_id VARCHAR;

-- Step 2: Add ON DELETE CASCADE to child tables.
-- Must drop and re-add the named constraints. Get exact names first:
--   SELECT conname FROM pg_constraint WHERE conrelid = 'extractions'::regclass AND contype = 'f';
--   SELECT conname FROM pg_constraint WHERE conrelid = 'validations'::regclass AND contype = 'f';
-- Then:
ALTER TABLE extractions DROP CONSTRAINT extractions_note_id_fkey;
ALTER TABLE extractions ADD CONSTRAINT extractions_note_id_fkey
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE;

ALTER TABLE validations DROP CONSTRAINT validations_note_id_fkey;
ALTER TABLE validations ADD CONSTRAINT validations_note_id_fkey
  FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE;

-- Step 3: Clean existing globally-seeded data
DELETE FROM validations;
DELETE FROM extractions;
DELETE FROM notes;
```

`nullable=True` in the SQLAlchemy model is a backward-compatibility concession for the schema migration only. It does NOT make `session_id` optional in application code. Every write path (create note, upload, seed) must explicitly pass `session_id=g.session_id`. A `Note` created without `session_id` is a bug.

## Session Guard Helper

A `_require_session()` helper lives in `utils/session.py`:

```python
from flask import g, jsonify

def require_session():
    """Returns session_id string or raises; call at top of each session-scoped route."""
    sid = g.get("session_id", "")
    if not sid:
        from flask import abort, make_response
        abort(make_response(
            jsonify({"error": "X-Session-ID header is required", "code": "MISSING_SESSION_ID"}), 400
        ))
    return sid
```

`before_request` in `app.py` only populates `g.session_id` — it does not validate:

```python
@app.before_request
def open_session():
    g.db = get_session(engine)
    g.session_id = request.headers.get("X-Session-ID", "").strip()
```

Validation happens per-route via `require_session()`. Routes that are exempt (`/api/extract`, `/api/health`) simply never call the helper.

## Backend Changes

| File | Change |
|------|--------|
| `models/note.py` | Add `session_id = Column(String, nullable=True)` |
| `app.py` | `before_request`: populate `g.session_id` from header (no validation here) |
| `utils/session.py` (new) | `require_session()` helper — 400 on missing/empty |
| `routes/notes.py` | `POST`: `require_session()` guard, set `session_id=g.session_id` on `Note`; `PUT /api/notes/<id>/text`: `require_session()` guard + ownership check before update |
| `routes/upload.py` | `require_session()` guard, set `session_id=g.session_id` on `Note` |
| `routes/queue.py` | `require_session()` guard, filter `.where(Note.session_id == g.session_id)` |
| `routes/history.py` | `require_session()` guard, filter `.where(Note.session_id == g.session_id)` on list; ownership check on detail |
| `routes/validate.py` | `require_session()` guard; ownership check on note lookup; add `.where(Note.session_id == g.session_id)` to `next_pending_id` query (see below) |
| `routes/metrics.py` | `require_session()` guard; both queries join through `Note` filtered by `session_id` (see below) |
| `routes/seed.py` | `require_session()` guard; idempotency check scoped to session: `.where(Note.filename == fname, Note.session_id == g.session_id)`; set `session_id=g.session_id` on seeded notes |
| `routes/reset.py` (new) | `DELETE /api/reset` — delete session's notes + return counts |

### Metrics queries (corrected)

**Cardinality assumption:** `validations.note_id` has a `unique=True` constraint (one validation per note). `extractions` has no DB-level unique constraint, but the upload/notes routes always delete the existing extraction before inserting a new one — so at most one extraction per note exists at runtime. The joins below are safe under this invariant; if multi-extraction support is ever added, the correction-rates query will need a `DISTINCT` or subquery.

Both queries in `metrics()` must join through `Note`:

```python
# Stats by status
rows = g.db.execute(
    select(Validation.status, func.count()..., ...)
    .join(Note, Note.id == Validation.note_id)
    .where(Note.session_id == g.session_id)
    .group_by(Validation.status)
).all()

# Per-category correction rates
val_rows = g.db.execute(
    select(Extraction.extracted_json, Validation.validated_json)
    .join(Note, Note.id == Extraction.note_id)
    .join(Validation, Validation.note_id == Extraction.note_id)
    .where(Note.session_id == g.session_id)
).all()
```

### Validate: next_pending_id query (corrected)

```python
next_pending = g.db.execute(
    select(Note.id)
    .join(Extraction, Extraction.note_id == Note.id)
    .outerjoin(Validation, Validation.note_id == Note.id)
    .where(Validation.id == None)
    .where(Note.id != note_id)
    .where(Note.session_id == g.session_id)   # ← required
    .order_by(Note.created_at.asc())
    .limit(1)
).scalar_one_or_none()
```

## Reset Route

`DELETE /api/reset` — query and capture counts before deleting, then delete notes (cascade removes children):

```python
note_ids = [r.id for r in g.db.execute(select(Note.id).where(Note.session_id == sid)).scalars()]
deleted_extractions = g.db.query(Extraction).filter(Extraction.note_id.in_(note_ids)).count()
deleted_validations = g.db.query(Validation).filter(Validation.note_id.in_(note_ids)).count()
g.db.query(Note).filter(Note.session_id == sid).delete(synchronize_session=False)
g.db.commit()
return jsonify({"deleted_notes": len(note_ids), "deleted_extractions": ..., "deleted_validations": ...})
```

Response shape:
```json
{ "deleted_notes": 3, "deleted_extractions": 3, "deleted_validations": 2 }
```

## Frontend Changes

| File | Change |
|------|--------|
| `src/api/client.ts` | On module load: read `session_id` from `localStorage`; if absent generate with `crypto.randomUUID()` and persist; inject `X-Session-ID` on every `request()` call and the `uploadFile` fetch |

`crypto.randomUUID()` requires a secure context (HTTPS or `localhost`). Local dev via `vite dev` runs on `localhost` — this is fine. In production on Vercel (HTTPS), this is also fine.

No other frontend files change.

## Error Codes

| Condition | Status | Code |
|-----------|--------|------|
| Missing, absent, or empty `X-Session-ID` | 400 | `MISSING_SESSION_ID` |
| Note not found | 404 | `NOT_FOUND` |
| Note belongs to different session | 403 | `FORBIDDEN` |

## What Does NOT Change

- `POST /api/extract` — stateless, no DB, no session header needed
- `GET /api/health` — health check, exempt
- Test suite: tests that create notes must pass `X-Session-ID: test-session` (or a fixed test session ID via `test_config`) to satisfy the guard

## Deployment Steps

1. Run the migration SQL above against Supabase (add column, fix cascade constraints, delete old rows)
2. Deploy backend + frontend
3. Verify: open two browser tabs in incognito — each should have independent history/queue/metrics
