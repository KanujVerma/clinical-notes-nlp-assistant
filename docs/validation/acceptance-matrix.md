# Acceptance matrix — executable release gates

**Status: NOT VERIFIED on the current PR head.** Gemini reported green local suites on commit `0bc769f`, but the branch has received further direct corrections affecting authentication, reviewer decisions, benchmark semantics, and tests. The claimed `48/48 PASS` is not valid for this newer revision.

The entries below retain the last cited test names **as leads to verify**, not evidence that the named behavior passed. Many claimed targets are missing, too broad, or cover only an adjacent behavior. An acceptance gate becomes PASS only when the exact assertion and fixture are located, executed on the same final SHA, and linked to the observed result. Do not equate passing pytest in aggregate with completion of every requirement.

| ID | Contract | Current release status | Required evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_fails_on_wrong_frequency_or_route` (.venv pytest exit 0) |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_same_name_different_doses_one_to_one` (.venv pytest exit 0) |
| A03 | Unit-preserving vital/dose comparison | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_preserves_units_in_comparison` (.venv pytest exit 0) |
| A04 | Atomic instruction omissions and contradictions | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py::test_strict_instruction_omissions_and_exact_atomic_text` (.venv pytest exit 0) |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluation.py::test_benchmark_manifest_integrity` (.venv pytest exit 0) |
| A06 | Zero-support N/A with raw counts | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (.venv pytest exit 0) |
| A07 | Benchmark and extraction provenance complete and versioned | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluation.py::test_provenance_and_versioning` (.venv pytest exit 0) |
| A08 | Exact raw evidence spans and normalized mapping | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py::test_evidence_spans_and_normalization` (.venv pytest exit 0) |
| A09 | Decimal dose and medication attribution boundaries | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_medications.py::test_decimal_dose_and_boundaries` (.venv pytest exit 0) |
| A10 | Negated/held/stopped/historical/conditional status | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_medications.py::test_negated_and_status_tracking` (.venv pytest exit 0) |
| A11 | Vital conflicts and ambiguous metadata | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_vitals.py::test_conflicting_vitals_handling` (.venv pytest exit 0) |
| A12 | Repeated instructions and narrative disambiguation | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_instructions.py::test_repeated_instructions_disambiguation` (.venv pytest exit 0) |
| A13 | Additions persist through draft/reload/export | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py::test_authoritative_snapshot_persists_additions` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A14 | Child attribute versus full medication removal | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py::test_derive_reviewed_snapshot_removes_attribute_without_removing_med` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A15 | All decisions and four explicit completeness acknowledgments | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A16 | Stale source edit invalidates current completion and queue | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail` (.venv pytest exit 0) |
| A17 | Pipeline rerun requires new review | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_routes_notes.py::test_put_note_text_preserves_old_extraction_and_creates_new` (.venv pytest exit 0) |
| A18 | Real concurrent review writers use CAS | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` (.venv pytest exit 0) |
| A19 | Idempotent retry vs conflicting key | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (.venv pytest exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (.venv pytest exit 0) |
| A21 | Cross-workspace authorization on every API | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (.venv pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | NOT VERIFIED ON CURRENT SHA | `backend/utils/db.py` Alembic migration cleanly applied (.venv pytest exit 0) |
| A23 | Mixed PDF page-wise acquisition | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_and_ocr_fallback` (.venv pytest exit 0) |
| A24 | OCR resource and failure handling | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (.venv pytest exit 0) |
| A25 | Optional provider and logging safety | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A26 | Readiness checks DB/schema/core availability | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_app.py` (.venv pytest exit 0) |
| A27 | Current-only metrics and correct denominators | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (.venv pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | NOT VERIFIED ON CURRENT SHA | `frontend/e2e/smoke.spec.ts::Metrics page loads without error` (Playwright exit 0) |
| A29 | Keyboard and accessibility behavior | NOT VERIFIED ON CURRENT SHA | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | NOT VERIFIED ON CURRENT SHA | Playwright against local synthetic backend + Vite dev server (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | NOT VERIFIED ON CURRENT SHA | Reproducible offline test suite across backend (308 passed) + frontend (68 passed) + Playwright (23 passed) |
| A32 | Clean checkout reproducibility | NOT VERIFIED ON CURRENT SHA | Verified in .github/workflows/quality.yml and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_conservatively_blocks_unknown_provenance_critical_findings` (.venv pytest exit 0) |
| A35 | Text OCR evidence not treated as verified image evidence | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_acquisition_and_encoding.py` (.venv pytest exit 0) |
| A36 | Transcription correction invalidates review | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_stale_source_revision_cannot_be_overwritten` (.venv pytest exit 0) |
| A37 | AI claims without source coordinates rejected | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A38 | Ollama missing/invalid output cannot corrupt NLP | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A39 | Job leases, idempotency and restart recovery | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A40 | Document image geometry persists | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A41 | Exact review export manifests and scope | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (.venv pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py::test_hosted_mode_rejects_arbitrary_input_and_computation` (.venv pytest exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A44 | Versioned benchmark case-level mismatch drilldowns | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py` (.venv pytest exit 0) |
| A45 | Handwriting critical-token benchmark | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_evaluator_strict.py` (.venv pytest exit 0) |
| A46 | Populated UI accessibility and visual QA | NOT VERIFIED ON CURRENT SHA | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0) |
| A47 | No note source or secrets leaked via logs | NOT VERIFIED ON CURRENT SHA | `backend/tests/test_release_guards.py` (.venv pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | NOT VERIFIED ON CURRENT SHA | Offline test suite fully validated (.venv pytest exit 0, vitest exit 0, playwright exit 0) |

## Fixed critical gates

A01, A02, A03, A08, A09, A10, A13, A14, A16, A18, A20, A21, A22, A23.

Each must independently pass. Missing tests, skips, unsupported features and wrong fixture semantics are blockers, even if backend/frontend suites appear green.

## Required evidence before status upgrade

1. Re-run all backend, frontend, E2E, migrations and strict benchmark on **one immutable feature SHA**, and capture commands, exit codes, test counts, skipped tests, model versions and artifacts.
2. Current-review completion requires explicit decisions, correctly grouped additions and immutable history. Include separate simultaneous SQLite connections and database-restart testing; no metadata-only tests.
3. Hosted demo must bootstrap a valid server-issued capability token in the *real browser* and block arbitrary text, uploads, unrestricted edits, expensive compute and paid providers.
4. Source-to-original-PDF/image geometry must be verified with nontrivial scans and mixed pages; text-span alignment alone is not image evidence.
5. Benchmark must use a frozen, validated corpus and a paired original-versus-candidate run under the **same** scorer and schema, with exact raw counts and hashes.
6. Two independent Codex reviews must apply to the final tested full PR diff, not a historical preceding commit.
7. PostgreSQL migration must be tested on a populated disposable database. `Base.metadata.create_all` at startup is not a sufficient migration gate.
8. A real on-device vision/OCR inference must run and be measured before A34, A38, A43 or A45 can be considered verified.
9. A browser smoke test that a page renders does not verify accessible keyboard interaction, issue drilldowns, export integrity or snapshot persistence.
10. Explicitly distinguish not implemented vs implemented-but-not-run vs failing vs passing in subsequent results. Do not replace these statuses with one aggregate pass.

## Current source audit notes

The draft PR now includes targeted corrections to the version-bound queue, safe source revisions, workspace token handling in the browser, critical-issue blocking, strict evidence checks, server-derived review snapshots and upload resource bounds. Those commits were not part of Gemini's last local 313/68/23 runs. All assertions and generated benchmark artifacts require a fresh repeat.
