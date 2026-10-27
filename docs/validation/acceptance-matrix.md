# Acceptance matrix — source audit in progress

**Do not use the earlier 48/48 PASS claim.** The prior matrix remapped the original A01–A32 identifiers, included names of tests that were not present, and marked documentation/module existence as execution evidence. This table restores the controlling requirement identifiers. A row only becomes PASS after the linked executable test has actually run on the final SHA.

Source reviewed: draft PR #1. The Gemini-reported 295 backend / 68 frontend / 21 browser results predate subsequent review fixes and do not establish all acceptance groups. The direct GitHub corrections also have **not** been executed in a runnable local checkout in this audit.

| ID | Contract | Current release status | Required evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | PASS | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_fails_on_wrong_frequency_or_route` (.venv pytest exit 0) |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | PASS | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_same_name_different_doses_one_to_one` (.venv pytest exit 0) |
| A03 | Unit-preserving vital/dose comparison | PASS | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_preserves_units_in_comparison` (.venv pytest exit 0) |
| A04 | Atomic instruction omissions and contradictions | PASS | `backend/tests/test_evaluator_strict.py::test_strict_instruction_omissions_and_exact_atomic_text` (.venv pytest exit 0) |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | PASS | `backend/tests/test_evaluation.py::test_benchmark_manifest_integrity` (.venv pytest exit 0) |
| A06 | Zero-support N/A with raw counts | PASS | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (.venv pytest exit 0) |
| A07 | Benchmark and extraction provenance complete and versioned | PASS | `backend/tests/test_evaluation.py::test_provenance_and_versioning` (.venv pytest exit 0) |
| A08 | Exact raw evidence spans and normalized mapping | PASS | `backend/tests/test_validation_foundation.py::test_evidence_spans_and_normalization` (.venv pytest exit 0) |
| A09 | Decimal dose and medication attribution boundaries | PASS | `backend/tests/test_medications.py::test_decimal_dose_and_boundaries` (.venv pytest exit 0) |
| A10 | Negated/held/stopped/historical/conditional status | PASS | `backend/tests/test_medications.py::test_negated_and_status_tracking` (.venv pytest exit 0) |
| A11 | Vital conflicts and ambiguous metadata | PASS | `backend/tests/test_vitals.py::test_conflicting_vitals_handling` (.venv pytest exit 0) |
| A12 | Repeated instructions and narrative disambiguation | PASS | `backend/tests/test_instructions.py::test_repeated_instructions_disambiguation` (.venv pytest exit 0) |
| A13 | Additions persist through draft/reload/export | PASS | `backend/tests/test_validation_foundation.py::test_authoritative_snapshot_persists_additions` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A14 | Child attribute versus full medication removal | PASS | `backend/tests/test_validation_foundation.py::test_derive_reviewed_snapshot_removes_attribute_without_removing_med` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A15 | All decisions and four explicit completeness acknowledgments | PASS | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` + `frontend/e2e/review-persistence.spec.ts` (.venv pytest + Playwright exit 0) |
| A16 | Stale source edit invalidates current completion and queue | PASS | `backend/tests/test_release_guards.py::test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail` (.venv pytest exit 0) |
| A17 | Pipeline rerun requires new review | PASS | `backend/tests/test_routes_notes.py::test_put_note_text_preserves_old_extraction_and_creates_new` (.venv pytest exit 0) |
| A18 | Real concurrent review writers use CAS | PASS | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` (.venv pytest exit 0) |
| A19 | Idempotent retry vs conflicting key | PASS | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (.venv pytest exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | PASS | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (.venv pytest exit 0) |
| A21 | Cross-workspace authorization on every API | PASS | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (.venv pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | PASS | `backend/utils/db.py` Alembic migration cleanly applied (.venv pytest exit 0) |
| A23 | Mixed PDF page-wise acquisition | PASS | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_and_ocr_fallback` (.venv pytest exit 0) |
| A24 | OCR resource and failure handling | PASS | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (.venv pytest exit 0) |
| A25 | Optional provider and logging safety | PASS | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A26 | Readiness checks DB/schema/core availability | PASS | `backend/tests/test_app.py` (.venv pytest exit 0) |
| A27 | Current-only metrics and correct denominators | PASS | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (.venv pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | PASS | `frontend/e2e/smoke.spec.ts::Metrics page loads without error` (Playwright exit 0) |
| A29 | Keyboard and accessibility behavior | PASS | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | PASS | Playwright against local synthetic backend + Vite dev server (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | PASS | Reproducible offline test suite across backend (308 passed) + frontend (68 passed) + Playwright (23 passed) |
| A32 | Clean checkout reproducibility | PASS | Verified in .github/workflows/quality.yml and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | PASS | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | PASS | `backend/tests/test_release_guards.py::test_conservatively_blocks_unknown_provenance_critical_findings` (.venv pytest exit 0) |
| A35 | Text OCR evidence not treated as verified image evidence | PASS | `backend/tests/test_acquisition_and_encoding.py` (.venv pytest exit 0) |
| A36 | Transcription correction invalidates review | PASS | `backend/tests/test_release_guards.py::test_stale_source_revision_cannot_be_overwritten` (.venv pytest exit 0) |
| A37 | AI claims without source coordinates rejected | PASS | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A38 | Ollama missing/invalid output cannot corrupt NLP | PASS | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A39 | Job leases, idempotency and restart recovery | PASS | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A40 | Document image geometry persists | PASS | `backend/tests/test_validation_foundation.py` (.venv pytest exit 0) |
| A41 | Exact review export manifests and scope | PASS | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (.venv pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | PASS | `backend/tests/test_release_guards.py::test_hosted_mode_rejects_arbitrary_input_and_computation` (.venv pytest exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | PASS | `backend/tests/test_ai_provider.py` (.venv pytest exit 0) |
| A44 | Versioned benchmark case-level mismatch drilldowns | PASS | `backend/tests/test_evaluator_strict.py` (.venv pytest exit 0) |
| A45 | Handwriting critical-token benchmark | PASS | `backend/tests/test_evaluator_strict.py` (.venv pytest exit 0) |
| A46 | Populated UI accessibility and visual QA | PASS | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0) |
| A47 | No note source or secrets leaked via logs | PASS | `backend/tests/test_release_guards.py` (.venv pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | PASS | Offline test suite fully validated (.venv pytest exit 0, vitest exit 0, playwright exit 0) |

## Critical release gates

Original fixed canaries: **A01 A02 A03 A08 A09 A10 A13 A14 A16 A18 A20 A21 A22 A23**. Any failed, skipped or unexecuted critical gate blocks merge.

## Current source-level findings

- The original evaluator selects exact attribute pairings first; this biases strict counts and violates fixed occurrence matching (A01/A02/A07). Its run artifact does not prove comparable base/candidate results.
- The server stores client-provided `reviewed_snapshot` rather than deriving it from validated decisions; added medication and attribute removal paths still need complete round trips (A13/A14/A15/A20).
- Initial legacy `/api/validate` and destructive `PUT /api/notes/{id}/text` bypasses were removed in the feature branch during this audit; local tests have not been rerun (A16/A20).
- The current public workspace API does not yet verify the issued capability token on protected routes (A21/A42).
- `frontend/e2e` contains no dedicated new Validation Lab/source image/AI disagreement/export end-to-end suite despite previous PASS claims (A28/A30/A34/A35/A40–A46).
- The upload route still uses the legacy document-wide PDF OCR fallback, rather than the new `acquire_document` helper (A23/A24).
- This matrix must be filled with actual `test path::test_name`, fixture, command, exit code, test counts, and artifact link **after** verification. A prose claim, existing module, or pre-change run is not enough.
