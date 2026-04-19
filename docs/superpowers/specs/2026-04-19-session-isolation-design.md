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

1. **No silent fallback.** If `X-Session-ID` is missing or empty on any session-scoped route, return `400 MISSING_SESSION_ID`. Never fall back to global/shared reads.
2. **Strict read filters.** All reads use `Note.session_id == g.session_id`. Old `NULL` rows are never surfaced, even if they exist in the DB.
3. **Ownership checks.** Before returning or mutating a note, verify `note.session_id == g.session_id`. Return `403 FORBIDDEN` otherwise.
4. **Seed scoping.** `POST /api/seed-demo` seeds notes tagged with the requesting session's ID only.
5. **Reset.** `DELETE /api/reset` deletes all notes for the session (cascade handles extractions/validations). Returns `{ deleted_notes, deleted_extractions, deleted_validations }`.
6. **Stateless extraction unchanged.** `POST /api/extract` is pure NLP with no DB writes — no session header required.
7. **Clean state.** All existing globally-seeded rows are deleted from Supabase before shipping.

## Data Model Change

```sql
ALTER TABLE notes ADD COLUMN session_id VARCHAR;
-- No default; all new rows set it explicitly from the request header.
-- Old NULL rows remain in DB but are never returned by any read path.
```

ON DELETE CASCADE must exist on `extractions.note_id` and `validations.note_id` for the reset route to work without manual child deletion. Add if missing.

## Backend Changes

| File | Change |
|------|--------|
| `models/note.py` | Add `session_id = Column(String, nullable=True)` |
| `app.py` | `before_request`: read `X-Session-ID` header → `g.session_id`; return 400 if missing on session-scoped routes (handled per-route, not globally, since `/api/extract` and `/api/health` are exempt) |
| `routes/notes.py` | Set `session_id=g.session_id` on `Note`; guard header presence |
| `routes/upload.py` | Set `session_id=g.session_id` on `Note`; guard header presence |
| `routes/queue.py` | Filter `Note.session_id == g.session_id`; guard header |
| `routes/history.py` | Filter `Note.session_id == g.session_id`; ownership check on detail; guard header |
| `routes/validate.py` | Ownership check (`note.session_id == g.session_id`); guard header |
| `routes/metrics.py` | Join through `Note` filtered by `session_id`; guard header |
| `routes/seed.py` | Set `session_id=g.session_id` on seeded notes; guard header |
| `routes/reset.py` (new) | `DELETE /api/reset`: delete session's notes + return counts |

## Frontend Changes

| File | Change |
|------|--------|
| `src/api/client.ts` | On module load: read `session_id` from `localStorage`, generate UUID v4 if absent, write back. Inject `X-Session-ID` header on every `request()` call and the `uploadFile` fetch. |

No other frontend files change.

## Helper: Session Guard

A shared helper `_require_session()` (in `app.py` or a `utils/session.py`) returns `(g.session_id, None)` when the header is present, or `(None, error_response)` when not — so each route can do a one-liner guard at the top.

## Reset Response Shape

```json
{ "deleted_notes": 3, "deleted_extractions": 3, "deleted_validations": 2 }
```

## Error Codes

| Condition | Status | Code |
|-----------|--------|------|
| Missing/empty `X-Session-ID` | 400 | `MISSING_SESSION_ID` |
| Note not found | 404 | `NOT_FOUND` |
| Note belongs to different session | 403 | `FORBIDDEN` |

## What Does NOT Change

- `POST /api/extract` — stateless, no DB, no session header needed
- `GET /api/health` — health check, exempt
- Test suite uses `test_config` overrides; tests that create notes must now pass a session header or be updated to supply one

## Cleanup

Before deploying: run `DELETE FROM validations; DELETE FROM extractions; DELETE FROM notes;` against Supabase production to remove all globally-seeded rows.
