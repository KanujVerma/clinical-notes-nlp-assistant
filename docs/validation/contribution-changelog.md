# Contribution Changelog & Authorship Lineage

This document truthfully delineates the original resume-time engineering work from the subsequent AI-assisted Validation Workbench implementation.

---

## 1. Original Project Foundation (Resume-Time Work)

The original repository was conceived and built as a full-stack clinical notes NLP demo showcasing:
- **Frontend**: React 18, TypeScript, Tailwind CSS, Vite.
  - Review queue and split-screen note viewer.
  - Rapid keyboard shortcuts (`A` Accept, `E` Edit, `R` Remove, `Tab` Navigate).
  - Inline dictionary explainer popover for medications and clinical abbreviations.
  - Basic Metrics dashboard and History view.
- **Backend**: Flask application running with SQLAlchemy and SQLite.
  - Deterministic clinical entity extraction using spaCy and medSpaCy target matcher.
  - Ingestion pipeline for text notes and PDF/image uploads (PyMuPDF, Tesseract).
  - Synthetic test fixtures and 20 ground-truth reference notes.
- **Test Baseline**: Original unit test suite covering basic parsing rules and route behavior.

---

## 2. Validation Workbench Enhancements (AI-Assisted Pair-Programming)

The Validation Workbench overhaul introduced enterprise-grade provenance, defensive verification, and statistical evaluation:

### Architecture & Database (Alembic & Models)
- **Database Migrations**: Introduced Alembic migration framework (`backend/migrations/`) with backward-compatible schema upgrades.
- **Immutable Provenance Models**:
  - `Workspace`: UUID tenant isolation authenticated via SHA-256 hashed capability tokens.
  - `SourceAsset`: Content-addressed document storage keyed by SHA-256 digest.
  - `AcquisitionRun`: Pagewise OCR coordinate capture and text extraction logs.
  - `NoteRevision`: Immutable source text snapshot chain with audit rationale.
  - `Extraction`: Cryptographically bound to source revision ID and rules hash.
  - `ReviewEvent`: Append-only review event store with parent pointers, optimistic concurrency (`lock_version`), and unique idempotency keys.
  - `OperationalIssue` & `IssueEvent`: Validation canaries with complete lifecycle tracking (`open` → `acknowledged` / `dismissed`).
  - `InferenceRun`: Local AI proposal candidates and discrepancy detection.
  - `Job`: Durable background queue with transactional leasing.

### Independent Verification Engine
- **Pure Validation Checker (`backend/validation/checker.py`)**:
  - Half-open coordinate interval verification (`0 <= start < end <= len(text)`).
  - Exact quote match verification against source text.
  - Decimal dose safety canary (`A09` unanchored `.5 mg` / `5.0 mg`).
  - Duplicate medication conflict canary (`A02`).
  - Missing vital sign unit canary (`A03`).
  - Contradictory instruction canary (`A04`).
  - Non-active medication action canary (`A10`).
- **Atomic Review Service (`backend/services/review_service.py`)**:
  - Optimistic concurrency control via atomic conditional update on `lock_version`.
  - Idempotency verification preventing duplicate review events.
  - Category completeness check enforcing affirmative signoff.
  - Critical blocker enforcement preventing signoff with open blockers.
  - Server-derived disposition (`reviewed_unchanged` vs `reviewed_corrected`).

### Strict Statistical Evaluator (`backend/evaluation/strict_evaluator.py`)
- **Source-occurrence-first pairing**: Same-name medications pair by source occurrence, then by a bounded span-overlap assignment. This is not the Hungarian algorithm. The bound stops a scorer from awarding a true positive by swapping duplicate doses.
- **Attribute-Level Scoring**: Discrete evaluation of medication name, dose, route, frequency, duration, qualifier.
- **Zero-Support Rule**: Strict `N/A` handling when ground truth and predictions are absent.
- **Immutable Artifact Bundles**: Generation of `run_metadata.json`, `summary_metrics.json`, `case_results.json`, and `manifest.json`.

### User Interface Overhaul
- **Validation Lab (`frontend/src/pages/ValidationLab.tsx`)**: Interactive dashboard displaying benchmark results, category breakdowns, and case-by-case error attribution (TP/FP/FN).
- **Operational Issues Drawer (`frontend/src/components/OperationalIssuesDrawer.tsx`)**: Slide-out drawer displaying live canaries, severities, and acknowledgment actions.
- **Transcription Edit Modal (`frontend/src/components/TranscriptionEditModal.tsx`)**: Source text editor triggering immutable `NoteRevision` creation.
- **Cryptographic Export**: Client integration downloading signed ZIP bundle (`manifest.json`, decisions, HTML report).

### Quality Assurance & Test Verification
- **Pytest Test Suite**: Expanded from 277 tests to **295 passed** tests.
- **Vitest Test Suite**: **68 passed** tests.
- **Playwright Chromium Suite**: **21 passed** end-to-end browser tests.
- **ESLint & TypeScript**: Zero compiler errors, zero ESLint errors.

## 2026-11-02 — v1 release candidate packaging

AI-assisted implementation on `feat/clinical-nlp-v1-release`, based on `0dd45ab`. The owner did not merge this branch in the same change. Handwriting PRs #9–#12 were left untouched.

- Rejected an idempotent replay that still looked like the current completion after the source moved.
- Rejected a parent medication edit that scored a correction without changing an attribute.
- Pointed quality CI at `main` and required a disposable PostgreSQL job.
- Replaced user-facing Hungarian-algorithm wording with the source-occurrence-first matcher the code runs.
- Added the versioned validation-loop fixture and showed the frozen 24-image aggregate separately from the 3-case Tesseract recording.

Counts for this commit belong in `docs/validation/V1_RELEASE_EVIDENCE.md`, not in the historical numbers above.
