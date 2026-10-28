# Acceptance matrix — source audit and final-SHA verification pending

**NOT RELEASE-VERIFIED.** Gemini reported local passing test suites on commit `53e9d4b`, but the branch has since received independent fixes to protected source images, model-source requirements, inference validation, hosted cleanup, and provenance terminology. Those earlier counts are historical, not tests of this new HEAD. Unsupported model benchmarks must not be presented as empirical.

- **Feature Branch**: `feat/clinical-validation-workbench`
- **Last Gemini-reported tested commit**: `53e9d4b`; **current HEAD requires a fresh full test/Codex run**.
- **Zero Paid Cloud API Incurred**: $0.00 spent (all local SQLite/PostgreSQL 15, deterministic heuristics, local multimodal Ollama adapters, and ChatGPT-authenticated Codex CLI)

## Historical Gemini-reported local test runs (pre-audit corrections)

- **Backend Pytest**: 363 passed, 0 failed in 18.31s (`.venv/bin/pytest backend/tests`, exit code 0)
- **PostgreSQL 15 Concurrency & Migration Suite**: 3 passed in 1.58s (`.venv/bin/pytest backend/tests/test_postgres_concurrency.py`, exit code 0; tests disposable local PostgreSQL 15 cluster, running full Alembic 001->002->003 migrations, multithreaded review writer barrier with separate connections, and job creation barrier)
- **Frontend Vitest**: 10 test files, 89 passed, 0 failed in 1.68s (`npm test --prefix frontend -- --run`, exit code 0)
- **Frontend TypeScript Build**: `tsc -b && vite build` passed with 0 errors in 1.04s (exit code 0)
- **Frontend Lint**: ESLint (`npm run lint --prefix frontend`) passed with 0 errors, 96 warnings (exit code 0)
- **Playwright Chromium E2E**: 25 passed, 0 failed in 28.0s (`cd frontend && CI=true npx playwright test`, exit code 0)
- **Worker Leases & Timezones**: Naive UTC datetime comparison verified for SQLite/SQLAlchemy ORM compatibility and lease renewal handling in `backend/worker.py`
- **Codex Reviews**: Verified using OpenAI Codex CLI (`codex review --base origin/main`); all findings addressed, and final clean worktree verified with `codex review --uncommitted` (`artifacts/verification/codex-review/`).

---

| ID | Contract | Current release status | Verified executable evidence |
|---|---|---|---|
| A01 | Wrong medication route/frequency fail per-attribute and strict record | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_fails_on_wrong_frequency_or_route` (pytest exit 0) |
| A02 | Duplicate-name medication occurrences preserved and paired one-to-one | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_same_name_different_doses_one_to_one` (pytest exit 0) |
| A03 | Unit-preserving vital/dose comparison | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_evaluator_strict_preserves_units_in_comparison` (pytest exit 0) |
| A04 | Atomic instruction omissions and contradictions | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py::test_strict_instruction_omissions_and_exact_atomic_text` (pytest exit 0) |
| A05 | Dataset integrity: hashes, missing/orphan labels, exceptions | RETEST REQUIRED | `backend/tests/test_dataset_integrity.py` + `backend/tests/test_evaluation.py::test_benchmark_manifest_integrity` (pytest exit 0) |
| A06 | Zero-support N/A with raw counts | RETEST REQUIRED | `backend/tests/test_routes_metrics.py::test_metrics_uses_current_completed_head_and_handles_zero_support` (pytest exit 0) |
| A07 | Benchmark and extraction provenance complete and versioned | RETEST REQUIRED | `backend/tests/test_evaluation.py::test_provenance_and_versioning` + `artifacts/evaluation/` (pytest exit 0) |
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
| A18 | Real concurrent review writers use CAS | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` (SQLite barrier) + `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_review_writers_barrier_race` (PostgreSQL 15 barrier, separate connection threads, exactly 1 winner, 1 loser, 1 DB event, exit 0) |
| A19 | Idempotent retry vs conflicting key | RETEST REQUIRED | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (SQLite barrier) + `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_job_creation_idempotency_barrier` (PostgreSQL 15 barrier, exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (pytest exit 0) |
| A21 | Cross-workspace authorization on every API | RETEST REQUIRED | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | RETEST REQUIRED | `backend/tests/test_postgres_concurrency.py::test_postgres_alembic_upgrade_and_schema_verification` (Alembic 001->002->003 executed on real PostgreSQL 15, verified tables, foreign keys, and indexes) + `backend/tests/test_db.py` (exit 0) |
| A23 | Mixed PDF page-wise acquisition | RETEST REQUIRED | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_digital_and_scanned` (pytest exit 0) |
| A24 | OCR resource and failure handling | RETEST REQUIRED | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A25 | Optional provider and logging safety | RETEST REQUIRED | `backend/tests/test_ai_provider.py` (zero external calls, negative controls verified, exit 0) |
| A26 | Readiness checks DB/schema/core availability | RETEST REQUIRED | `backend/tests/test_app.py` (readiness and health, exit 0) |
| A27 | Current-only metrics and correct denominators | RETEST REQUIRED | `backend/tests/test_routes_metrics.py` + `test_audit_remediations.py::test_metrics_excludes_legacy_validations_when_note_needs_review` (pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts::Metrics page loads without error` (Playwright exit 0) |
| A29 | Keyboard and accessibility behavior | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | RETEST REQUIRED | Playwright against local synthetic backend + Vite dev server across process lifecycle (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | RETEST REQUIRED | Reproducible offline test suite across backend (363 passed) + frontend (89 passed) + Playwright (25 passed) |
| A32 | Clean checkout reproducibility | RETEST REQUIRED | Verified in `.github/workflows/quality.yml` and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | RETEST REQUIRED | `backend/tests/test_multimodal_adapters.py::test_multimodal_ai_candidates_api_preserves_authoritative_state` + `backend/services/review_service.py` (pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | PARTIAL — NEGATIVE CONTROLS | Numeric/negation disagreement on OCR tokens is tested; no live vision OCR disagreement benchmark or calibration. |
| A35 | Text OCR evidence not treated as verified image evidence | RETEST REQUIRED | OCR agreement now correctly labeled \`ocr_consistent_unverified\`; source pixels require separate human/independent verification. |
| A36 | Transcription correction invalidates review | RETEST REQUIRED | `backend/tests/test_release_guards.py::test_stale_source_revision_cannot_be_overwritten` (pytest exit 0) |
| A37 | AI claims without source coordinates rejected | PARTIAL — UNVERIFIED MODEL GEOMETRY | Proposed model boxes are not authoritative source evidence; original pixel confirmation is not automated. |
| A38 | Ollama missing/invalid output cannot corrupt NLP | PARTIAL — MOCK/OFFLINE ONLY | Offline and invalid-response tests exist; no verified installed-model run or model digest. |
| A39 | Job leases, idempotency and restart recovery | RETEST REQUIRED | Lease renewal before bounded tasks does not establish heartbeat/recovery through arbitrarily long inference; run local regression. |
| A40 | Document image geometry persists | RETEST REQUIRED | Original PDF/image viewer now uses authenticated blob fetch, replacing bare image URL; browser/unit tests must rerun. |
| A41 | Exact review export manifests and scope | RETEST REQUIRED | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | RETEST REQUIRED | `backend/tests/test_workspace_authorization.py` (sandbox quota, 2h retention, precomputed scenario seed with 0 Spacy calls) + `frontend/e2e/hosted-mode.spec.ts` (Playwright exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | NOT IMPLEMENTED | Precomputed bundle contains deterministic extraction/issues but no versioned recorded AI inference artifacts. |
| A44 | Versioned benchmark case-level mismatch drilldowns | RETEST REQUIRED | `backend/tests/test_evaluator_strict.py` (pytest exit 0) |
| A45 | Handwriting critical-token benchmark | NOT MEASURED — SYNTHETIC EXAMPLE ONLY | Handwritten 'predictions' in the earlier test were manually typed. CER/WER from those strings are a metric-unit-test example, not actual GLM-OCR or Qwen3-VL measurements. |
| A46 | Populated UI accessibility and visual QA | RETEST REQUIRED | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0, screenshots updated in `docs/screenshots/`) |
| A47 | No note source or secrets leaked via logs | RETEST REQUIRED | `backend/tests/test_release_guards.py` (pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | RETEST REQUIRED | Final \`codex review --uncommitted\` reported a clean worktree (nothing to review); run \`codex review --base origin/main\` after final code/test commits. |

## New independent source-audit findings (October 28, 2026)

- Protected page images required browser-side capability headers. The original `<img src="/api/notes/...">` could not send them. The viewer now requests an authenticated blob and revokes its local object URL. Retest actual image loading and page/rotation changes.
- Model-adapter requests for a vision task with only a text source previously fell back silently to text inference. They now fail closed with `IMAGE_SOURCE_REQUIRED`; model names are server allowlisted and the Ollama endpoint is restricted to HTTP loopback.
- The handwriting CER/WER in the prior report came entirely from authored hypothesis strings, not on-device OCR runs. Do not publish these numbers as measured model accuracy.
- Hosted workspace expiry cleanup previously failed to remove dependent `IssueEvent` and `AcquisitionRun` rows before their parents; code/test corrections were added, but PostgreSQL FK behavior must be executed on disposable DB.
- The hosted scenario bundle currently has no versioned AI recordings. A43 requires a separate recorded-run implementation rather than relabeling deterministic fixture output.
- CI status from GitHub Actions and final Codex full-diff review are not confirmed for these new commits. Keep PR draft, do not merge or deploy.
