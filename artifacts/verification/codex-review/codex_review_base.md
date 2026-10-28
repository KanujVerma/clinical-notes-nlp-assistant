# Codex Review Summary — Base Review (against origin/main)

- **Date:** 2026-10-27
- **Base Commit:** `origin/main` (`596493e97f52c6ff6073828dc89ad7e84658f1ae`)
- **Reviewed Head Commit:** `561009d`
- **Command:** `codex review --base origin/main`
- **Model:** `gpt-6.1-sol` (via ChatGPT subscription, no API-key billing)

## Findings and Remediations

### 1. [P1] Serialize the legacy revision backfill across startup workers
- **File:** `backend/utils/db.py:52-56`
- **Finding:** Concurrent startup workers could both query the same unbacked legacy notes and create duplicate `NoteRevision` records, leaving inconsistent revision pointers.
- **Remediation:** Added an atomic transactional claim (`update(Note).where(Note.id == note.id, Note.current_source_revision_id.is_(None)).update({"current_source_revision_id": rev_id})`) committed per note. Only the claiming worker synthesizes the revision; concurrent workers skip claimed notes.

### 2. [P1] Escape URL interpolation before configuring Alembic
- **File:** `backend/utils/db.py:40-42`
- **Finding:** PostgreSQL URLs containing percent-encoded characters (such as `%40` for `@` in passwords) cause `ConfigParser` in Alembic's `set_main_option` to raise `ValueError: invalid interpolation syntax`.
- **Remediation:** Escaped percent signs using `raw_url.replace("%", "%%")` before passing to `cfg.set_main_option("sqlalchemy.url", ...)`.

### 3. [P2] Preserve restored drafts when flattening extraction fields
- **File:** `frontend/src/pages/Review.tsx:333-337`
- **Finding:** Restoring a saved draft left `reReviewBanner` as `false`, causing the subsequent flattening `useEffect([extracted, reReviewBanner])` to overwrite restored draft decisions and edits with fresh extraction values.
- **Remediation:** Added `hasLoadedReviewRef` to track whether fields were initialized from a review snapshot (draft or re-review). Guarded the flattening effect with `if (!extracted || reReviewBanner || hasLoadedReviewRef.current) return;`.

### 4. [P2] Replay concurrent reviews after uniqueness conflicts
- **File:** `backend/services/review_service.py:700-701`
- **Finding:** Concurrent review requests with the same idempotency key could both pass the initial lookup. The second request raised unhandled `IntegrityError` at `session.flush()`, returning HTTP 500 instead of a clean replay.
- **Remediation:** Caught `IntegrityError` on `session.flush()`, rolled back the session, queried the committed event by `(workspace_id, idempotency_key)`, verified `request_hash == req_hash`, and returned `(existing, True)` as an idempotent replay.

### 5. [P2] Enforce job idempotency with a database constraint
- **File:** `backend/models/job.py`, `backend/routes/jobs.py`
- **Finding:** `Job` table lacked a unique constraint on `(workspace_id, idempotency_key)`, allowing concurrent job posts with the same key to create duplicate jobs.
- **Remediation:** Added `UniqueConstraint("workspace_id", "idempotency_key", name="uq_jobs_workspace_idempotency_key")` to `Job` and migration `001`. Caught `IntegrityError` in `backend/routes/jobs.py` on commit and returned the existing job with HTTP 200.

### 6. [P2] Unwrap vital field objects in the HTML export
- **File:** `backend/routes/export.py:105-107`
- **Finding:** Vitals structured as dictionary field objects (`{"value": "120/80", "unit": "mmHg"}`) were placed directly into the HTML export table value column as raw dict strings.
- **Remediation:** Unwrapped `v.get("value")` and `v.get("unit")` when vital entries are dictionary objects, rendering clean measurement and unit values.
