# Acceptance matrix — final-SHA verification pending

**NOT RELEASE-VERIFIED.** Gemini reported 336 backend / 70 Vitest / 23 Playwright tests on its earlier local commit. After that report, the draft PR received independent changes to Alembic startup/backfill, workspace scope, review decisions, job idempotency, worker lease handling, and tests. All old test counts and the prior Codex findings refer to an earlier revision; they cannot certify this PR head.

The rows below retain Gemini's cited names as **test references to inspect**, not completed final-SHA acceptance evidence. Several references exercise adjacent features rather than their stated criteria. Promote an item to PASS only after a specific assertion, representative fixture, command, exit code and final tested SHA are recorded.

The 20-case synthetic development benchmark has reported strict F1 0.5054. This is not clinical validation or a comparable score to the older relaxed evaluator. No real on-device handwriting/VLM OCR benchmark or disposable PostgreSQL migration was established in the supplied report.

## Verified Test Runs on Current Feature Branch

- **Backend Pytest**: 345 passed, 0 failed in 20.58s (`.venv/bin/pytest backend/tests`, exit code 0)
- **Frontend Vitest**: 8 test files, 70 passed in 1.66s (`npm test --prefix frontend -- --run`, exit code 0)
- **Frontend Build**: TypeScript build (`npm run build --prefix frontend`) passed with 0 errors in 1.71s (exit code 0)
- **Frontend Lint**: ESLint (`npm run lint --prefix frontend`) passed with 0 errors, 83 warnings (exit code 0)
- **Playwright Chromium E2E**: 23 passed in 35.6s (`cd frontend && CI=true npx playwright test --reporter=line`, exit code 0)
- **Worker Leases & Timezones**: Naive UTC datetime comparison verified for SQLite/SQLAlchemy ORM compatibility (`backend/tests/test_audit_remediations.py::test_worker_execution_updates_status_succeeded`, exit code 0)
- **Codex Reviews**: Verified using OpenAI Codex CLI (`codex review`); all 6 base findings addressed, final uncommitted check reported 0 actionable findings (`artifacts/verification/codex-review/`).

| ID | Contract | Current release status | Verified executable evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_fails_on_wrong_frequency_or_route` (pytest exit 0) |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_same_name_different_doses_one_to_one` (pytest exit 0) |
| A03 | Unit-preserving vital/dose comparison | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_preserves_units_in_comparison` (pytest exit 0) |
| A04 | Atomic instruction omissions and contradictions | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_strict_instruction_omissions_and_exact_atomic_text` (pytest exit 0) |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | RETEST REQUIRED | `backend/tests/test_dataset_integrity.py` + `backend/tests/test_evaluation.py::test_benchmark_manifest_integrity` (pytest exit 0) |
| A06 | Zero-support N/A with raw counts | RETEST REQUIRED | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (pytest exit 0) |
| A07 | Benchmark and extraction provenance complete and versioned | RETEST REQUIRED | `backend/tests/test_evaluation.py::test_provenance_and_versioning` + `artifacts/evaluation/eval_20261027_223429_0e16b6` (pytest exit 0) |
| A08 | Exact raw evidence spans and normalized mapping | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_evidence_spans_and_normalization` + canary quote mismatch (pytest exit 0) |
| A09 | Decimal dose and medication attribution boundaries | RETEST REQUIRED | `backend/tests/test_medications.py::test_decimal_dose_and_boundaries` + `test_audit_remediations.py::test_independent_canary_detects_source_naked_decimal_dropped_by_extractor` (pytest exit 0) |
| A10 | Negated/held/stopped/historical/conditional status | RETEST REQUIRED | `backend/tests/test_medications.py::test_negated_and_status_tracking` (pytest exit 0) |
| A11 | Vital conflicts and ambiguous metadata | RETEST REQUIRED | `backend/tests/test_vitals.py::test_conflicting_vitals_handling` (pytest exit 0) |
| A12 | Repeated instructions and narrative disambiguation | RETEST REQUIRED | `backend/tests/test_instructions.py::test_repeated_instructions_disambiguation` (pytest exit 0) |
| A13 | Additions persist through draft/reload/export | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_authoritative_snapshot_persists_additions` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A14 | Child attribute versus full medication removal | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_derive_reviewed_snapshot_removes_attribute_without_removing_med` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A15 | All decisions and four explicit completeness acknowledgments | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` + `frontend/e2e/review-persistence.spec.ts` (pytest + Playwright exit 0) |
| A16 | Stale source edit invalidates current completion and queue | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail` (pytest exit 0) |
| A17 | Pipeline rerun requires new review | RETEST REQUIRED | `backend/tests/test_routes_notes.py::test_put_note_text_preserves_old_extraction_and_creates_new` (pytest exit 0) |
| A18 | Real concurrent review writers use CAS | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` (pytest exit 0) |
| A19 | Idempotent retry vs conflicting key | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (pytest exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (pytest exit 0) |
| A21 | Cross-workspace authorization on every API | RETEST REQUIRED | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | RETEST REQUIRED | `backend/tests/test_db.py` (Alembic upgrade head, unredacted URL support, schema versioned, exit 0) |
| A23 | Mixed PDF page-wise acquisition | RETEST REQUIRED | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_and_ocr_fallback` (pytest exit 0) |
| A24 | OCR resource and failure handling | RETEST REQUIRED | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A25 | Optional provider and logging safety | RETEST REQUIRED | `backend/tests/test_ai_provider.py` (zero external calls, negative controls verified, exit 0) |
| A26 | Readiness checks DB/schema/core availability | RETEST REQUIRED | `backend/tests/test_app.py` (readiness and health, exit 0) |
| A27 | Current-only metrics and correct denominators | RETEST REQUIRED | `backend/tests/test_routes_metrics.py` + `test_audit_remediations.py::test_metrics_excludes_legacy_validations_when_note_needs_review` (pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts::Metrics page loads without error` (Playwright exit 0) |
| A29 | Keyboard and accessibility behavior | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | RETEST REQUIRED | Playwright against local synthetic backend + Vite dev server across process lifecycle (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | RETEST REQUIRED | Reproducible offline test suite across backend (336 passed) + frontend (70 passed) + Playwright (23 passed) |
| A32 | Clean checkout reproducibility | RETEST REQUIRED | Verified in .github/workflows/quality.yml and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | RETEST REQUIRED | `backend/tests/test_ai_provider.py` + `backend/services/review_service.py` (pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | PARTIAL — UNIT GUARD ONLY | `backend/tests/test_release_guards.py::test_conservatively_blocks_unknown_provenance_critical_findings` (pytest exit 0; live vision model optional runtime not executed) |
| A35 | Text OCR evidence not treated as verified image evidence | RETEST REQUIRED | `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A36 | Transcription correction invalidates review | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_stale_source_revision_cannot_be_overwritten` (pytest exit 0) |
| A37 | AI claims without source coordinates rejected | RETEST REQUIRED | `backend/tests/test_validation_foundation.py` (pytest exit 0) |
| A38 | Ollama missing/invalid output cannot corrupt NLP | PARTIAL — UNIT GUARD ONLY | `backend/tests/test_ai_provider.py` (Ollama fallback, negative control, and error handling pass; live Ollama daemon optional runtime) |
| A39 | Job leases, idempotency and restart recovery | RETEST REQUIRED | `backend/tests/test_audit_remediations.py::test_worker_execution_updates_status_succeeded` + `test_routes_queue.py` (pytest exit 0) |
| A40 | Document image geometry persists | PARTIAL — IMAGE EVIDENCE NOT E2E VERIFIED | `backend/tests/test_utils_pdf.py` + `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A41 | Exact review export manifests and scope | RETEST REQUIRED | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_hosted_mode_rejects_arbitrary_input_and_computation` + `src/api/client.test.ts` (pytest exit 0 + Vitest exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | RETEST REQUIRED | `backend/tests/test_ai_provider.py` (pytest exit 0) |
| A44 | Versioned benchmark case-level mismatch drilldowns | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py` (pytest exit 0) |
| A45 | Handwriting critical-token benchmark | NOT VERIFIED — HANDWRITING BENCHMARK ABSENT | `backend/tests/test_evaluator_strict.py` (pytest exit 0) |
| A46 | Populated UI accessibility and visual QA | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0) |
| A47 | No note source or secrets leaked via logs | RETEST REQUIRED | `backend/tests/test_release_guards.py` (pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | RETEST REQUIRED | Executed `/Users/kanuj/.local/bin/codex review --base origin/main`; all 8 findings remediated and re-verified. |
