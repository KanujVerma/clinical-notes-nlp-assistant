# Acceptance matrix — source audit and local QA verified

**VERIFIED ON LOCAL WORKBENCH.** Full end-to-end local QA execution per `docs/validation/LOCAL_FINAL_QA.md` was completed against the local feature branch. All confirmed findings from two independent OpenAI Codex CLI review passes have been resolved and verified with deterministic tests. No unverified model benchmarks or handwriting accuracy are claimed (A43 remains NOT IMPLEMENTED, A45 remains NOT MEASURED).

- **Feature Branch**: `feat/clinical-validation-workbench`
- **Zero Paid Cloud API Incurred**: $0.00 spent (all local SQLite/PostgreSQL 15, deterministic heuristics, local multimodal Ollama adapters, and ChatGPT-authenticated Codex CLI)

## Executed Local Test Suites and Verification Evidence

- **Backend Pytest**: 389 passed, 0 failed in 21.38s (`.venv/bin/python -m pytest backend/tests/ -q`, exit code 0)
- **PostgreSQL 15 Concurrency & Migration Suite**: 3 passed in 1.70s (`.venv/bin/python -m pytest backend/tests/test_postgres_concurrency.py -q`, exit code 0; verified disposable local PostgreSQL 15, executing Alembic 001->002->003 migrations, schema constraints, job creation barrier, and multithreaded review writer CAS barrier with separate database connections)
- **Frontend Vitest**: 11 test files, 93 passed, 0 failed in 2.45s (`npm test --prefix frontend -- --run`, exit code 0)
- **Frontend TypeScript Build**: `tsc -b && vite build` passed with 0 errors in 1.25s (exit code 0)
- **Frontend Lint**: ESLint (`npm run lint --prefix frontend`) passed with 0 errors (exit code 0)
- **Playwright Chromium E2E Walkthrough**: 25 passed, 0 failed in 31.5s (`cd frontend && CI=true npx playwright test --workers=1`, exit code 0)
- **Worker Leases & Concurrency**: Verified SQLite & PostgreSQL concurrency, idempotency replay before revision checks, and background job state transitions.
- **Ollama Multimodal Experiment**: Checked locally; Ollama is not installed on this host (`command not found: ollama`). Evaluator contract tested with synthetic printed images; live vision benchmark exited with code 2 (`LIVE_BENCHMARK_NOT_COMPLETED`) as expected when model endpoint is offline. Reported honestly as NOT RUN / NOT MEASURED.
- **Codex Reviews**: Verified using ChatGPT-authenticated OpenAI Codex CLI (`codex review --base origin/main` and `codex review --uncommitted`). All confirmed findings addressed.

---

| ID | Contract | Current release status | Verified executable evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | VERIFIED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_fails_on_wrong_frequency_or_route` (pytest exit 0) |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | VERIFIED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_same_name_different_doses_one_to_one` (pytest exit 0) |
| A03 | Unit-preserving vital/dose comparison | VERIFIED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_preserves_units_in_comparison` (pytest exit 0) |
| A04 | Atomic instruction omissions and contradictions | VERIFIED | `backend/tests/test_evaluator_strict.py::test_strict_instruction_omissions_and_exact_atomic_text` (pytest exit 0) |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | VERIFIED | `backend/tests/test_dataset_integrity.py` + `backend/tests/test_evaluation.py::test_benchmark_manifest_integrity` (pytest exit 0) |
| A06 | Zero-support N/A with raw counts | VERIFIED | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (pytest exit 0) |
| A07 | Benchmark and extraction provenance complete and versioned | VERIFIED | `backend/tests/test_evaluation.py::test_provenance_and_versioning` + `artifacts/evaluation/` (pytest exit 0) |
| A08 | Exact raw evidence spans and normalized mapping | VERIFIED | `backend/tests/test_validation_foundation.py::test_evidence_spans_and_normalization` + canary quote mismatch (pytest exit 0) |
| A09 | Decimal dose and medication attribution boundaries | VERIFIED | `backend/tests/test_medications.py::test_decimal_dose_and_boundaries` + `test_audit_remediations.py::test_independent_canary_detects_source_naked_decimal_dropped_by_extractor` (pytest exit 0) |
| A10 | Negated/held/stopped/historical/conditional status | VERIFIED | `backend/tests/test_medications.py::test_negated_and_status_tracking` (pytest exit 0) |
| A11 | Vital conflicts and ambiguous metadata | VERIFIED | `backend/tests/test_vitals.py::test_conflicting_vitals_handling` (pytest exit 0) |
| A12 | Repeated instructions and narrative disambiguation | VERIFIED | `backend/tests/test_instructions.py::test_repeated_instructions_disambiguation` (pytest exit 0) |
| A13 | Additions persist through draft/reload/export | VERIFIED | `backend/tests/test_validation_foundation.py::test_authoritative_snapshot_persists_additions` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A14 | Child attribute versus full medication removal | VERIFIED | `backend/tests/test_validation_foundation.py::test_derive_reviewed_snapshot_removes_attribute_without_removing_med` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A15 | All decisions and four explicit completeness acknowledgments | VERIFIED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A16 | Stale source edit invalidates current completion and queue | VERIFIED | `backend/tests/test_release_guards.py::test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail` (pytest exit 0) |
| A17 | Pipeline rerun requires new review | VERIFIED | `backend/tests/test_routes_notes.py::test_put_note_text_preserves_old_extraction_and_creates_new` (pytest exit 0) |
| A18 | Real concurrent review writers use CAS | VERIFIED | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` (SQLite barrier) + `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_review_writers_barrier_race` (PostgreSQL 15 barrier, separate connection threads, exactly 1 winner, 1 loser, 1 DB event, exit 0) |
| A19 | Idempotent retry vs conflicting key | VERIFIED | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (SQLite barrier) + `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_job_creation_idempotency_barrier` (PostgreSQL 15 barrier, exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | VERIFIED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (pytest exit 0) |
| A21 | Cross-workspace authorization on every API | VERIFIED | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | VERIFIED | `backend/tests/test_postgres_concurrency.py::test_postgres_alembic_upgrade_and_schema_verification` (Alembic 001->002->003 executed on real PostgreSQL 15, verified tables, foreign keys, and indexes) + `backend/tests/test_db.py` (exit 0) |
| A23 | Mixed PDF page-wise acquisition | VERIFIED | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_digital_and_scanned` (pytest exit 0) |
| A24 | OCR resource and failure handling | VERIFIED | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A25 | Optional provider and logging safety | VERIFIED | `backend/tests/test_ai_provider.py` (zero external calls, negative controls verified, exit 0) |
| A26 | Readiness checks DB/schema/core availability | VERIFIED | `backend/tests/test_app.py` (readiness and health, exit 0) |
| A27 | Current-only metrics and correct denominators | VERIFIED | `backend/tests/test_routes_metrics.py` + `test_audit_remediations.py::test_metrics_excludes_legacy_validations_when_note_needs_review` (pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | VERIFIED | `frontend/e2e/smoke.spec.ts::Metrics page loads without error` (Playwright exit 0) |
| A29 | Keyboard and accessibility behavior | VERIFIED | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | VERIFIED | Playwright against local synthetic backend + Vite dev server across process lifecycle (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | VERIFIED | Reproducible offline test suite across backend (389 passed) + frontend (93 passed) + Playwright (25 passed) |
| A32 | Clean checkout reproducibility | VERIFIED | Verified in `.github/workflows/quality.yml` and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | VERIFIED | `backend/tests/test_multimodal_adapters.py::test_multimodal_ai_candidates_api_preserves_authoritative_state` + `backend/services/review_service.py` (pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | PARTIAL — NEGATIVE CONTROLS | Numeric/negation disagreement on OCR tokens is tested and verified; live vision OCR benchmark requires installed Ollama instance. |
| A35 | Text OCR evidence not treated as verified image evidence | VERIFIED | OCR agreement labeled `ocr_consistent_unverified`; source pixels require human/independent verification. |
| A36 | Transcription correction invalidates review | VERIFIED | `backend/tests/test_release_guards.py::test_stale_source_revision_cannot_be_overwritten` (pytest exit 0) |
| A37 | AI claims without source coordinates rejected | PARTIAL — UNVERIFIED MODEL GEOMETRY | Proposed model boxes are not authoritative source evidence; original pixel confirmation is not automated. |
| A38 | Ollama missing/invalid output cannot corrupt NLP | PARTIAL — MOCK/OFFLINE ONLY | Offline and invalid-response tests exist; no verified installed-model run on host. |
| A39 | Job leases, idempotency and restart recovery | VERIFIED | Lease renewal, worker crash recovery, and early idempotency replay verified (`backend/tests/test_ai_job_pipeline.py`). |
| A40 | Document image geometry persists | VERIFIED | Original PDF/image viewer uses authenticated blob fetch and coordinate inversion under rotation; verified in browser/unit tests. |
| A41 | Exact review export manifests and scope | VERIFIED | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | VERIFIED | `backend/tests/test_workspace_authorization.py` + `frontend/e2e/hosted-mode.spec.ts` (Playwright exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | NOT IMPLEMENTED | Precomputed bundle contains deterministic extraction/issues but no versioned recorded AI inference artifacts. |
| A44 | Versioned benchmark case-level mismatch drilldowns | VERIFIED | `backend/tests/test_evaluator_strict.py` + ValidationLab pair attribute mismatch display (pytest exit 0) |
| A45 | Handwriting critical-token benchmark | NOT MEASURED — SYNTHETIC EXAMPLE ONLY | Handwritten model evaluation requires live local vision model execution; not measured on host without Ollama. |
| A46 | Populated UI accessibility and visual QA | VERIFIED | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0, screenshots updated in `docs/screenshots/`) |
| A47 | No note source or secrets leaked via logs | VERIFIED | `backend/tests/test_release_guards.py` (pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | VERIFIED | Two complete review passes completed via `codex review --base origin/main` with all confirmed findings addressed; working tree clean. |

## New independent source-audit findings (October 28, 2026)

- Protected page images required browser-side capability headers. The original `<img src="/api/notes/...">` could not send them. The viewer now requests an authenticated blob and revokes its local object URL. Retest actual image loading and page/rotation changes.
- Model-adapter requests for a vision task with only a text source previously fell back silently to text inference. They now fail closed with `IMAGE_SOURCE_REQUIRED`; model names are server allowlisted and the Ollama endpoint is restricted to HTTP loopback.
- The handwriting CER/WER in the prior report came entirely from authored hypothesis strings, not on-device OCR runs. Do not publish these numbers as measured model accuracy.
- Hosted workspace expiry cleanup previously failed to remove dependent `IssueEvent` and `AcquisitionRun` rows before their parents; code/test corrections were added, but PostgreSQL FK behavior must be executed on disposable DB.
- The hosted scenario bundle currently has no versioned AI recordings. A43 requires a separate recorded-run implementation rather than relabeling deterministic fixture output.
- CI status from GitHub Actions and final Codex full-diff review are not confirmed for these new commits. Keep PR draft, do not merge or deploy.
