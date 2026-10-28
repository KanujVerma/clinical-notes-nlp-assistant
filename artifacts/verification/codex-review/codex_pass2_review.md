# OpenAI Codex Independent Review — Pass 2 Audit Report

**Date:** October 27, 2026
**Command:** `codex review --uncommitted`
**Model:** `gpt-6.1-sol`
**Harness / Authentication:** ChatGPT Plan Authentication (non-metered CLI)

---

## 1. Summary of Pass 2 Audit Findings & Resolutions

All findings surfaced by the independent OpenAI Codex auditor during Pass 2 have been strictly resolved and verified in both unit and integration tests:

| ID | Severity | Finding | Resolution Status |
|---|---|---|---|
| C2-01 | P2 | Update pending-note readers for the new persistence model (`backend/routes/revisions.py`, `backend/routes/queue.py`) | **RESOLVED**: Updated `/api/queue` to filter by `(Note.workspace_id == sid \| Note.session_id == sid)`, `Validation.id.is_(None)`, and `Note.review_head_event_id.is_(None)` with `distinct()`. |
| C2-02 | P2 | Load history detail through the current extraction pointer (`backend/routes/history.py`) | **RESOLVED**: Updated `/api/history/<id>` to resolve `note.current_extraction_id` first before falling back to ID-ordered lookups. |
| C2-03 | P2 | Download footer exports with workspace headers (`frontend/src/pages/Review.tsx`) | **RESOLVED**: Replaced static `<a>` links with `api.downloadExport(reviewEventId)` which injects authenticated `X-Session-ID` and `X-Workspace-ID` headers. |
| C2-04 | P2 | Adapt production extraction fields before evidence validation (`backend/validation/checker.py`) | **RESOLVED**: Extended `verify_evidence` to support native pipeline entity `span: [start, end]` tuples, validating boundary constraints without generating false quote mismatches. |
| C2-05 | P2 | Recompute route and frequency for each medication pair (`backend/evaluation/strict_evaluator.py`) | **RESOLVED**: Assigned `p_route`, `p_freq`, `l_route`, and `l_freq` inside the pairing loop for each candidate prediction and label. |
| C2-06 | P2 | Include medication action in strict matching (`backend/evaluation/strict_evaluator.py`) | **RESOLVED**: Enforced exact `p_action == l_action` match requirement in the primary pairing condition. |
| C2-07 | P2 | Unwrap instruction values before comparing them (`backend/evaluation/strict_evaluator.py`) | **RESOLVED**: Added `extract_inst_text` recursive unwrapper to extract normalized text from nested dictionaries. |
| C2-08 | P2 | Reject clinically different instructions despite token overlap (`backend/evaluation/strict_evaluator.py`) | **RESOLVED**: Added explicit checks for numbers (`\b\d+\b`), negation words (`not, no, never, without`), and stop words before allowing token-overlap matches. |
| C2-09 | P2 | Calculate actual correction counts for ReviewEvent metrics (`backend/routes/metrics.py`) | **RESOLVED**: Parsed `item_decisions_json` to compute actual edit/remove/add correction counts and average them per outcome category. |

---

## 2. Verification Evidence

- **Backend Pytest:** 295 passed in 13.05s across 30 modules.
- **Frontend Vitest:** 68 passed in 1.14s.
- **Frontend TypeScript/Vite Build:** Clean production build with 0 errors.
- **Frontend ESLint:** 0 errors.
- **Playwright Chromium E2E:** 21 passed in 40.6s.
