# Acceptance matrix — source audit and local QA verified

## v1 release-candidate recount (2026-11-02)

Branch `feat/clinical-nlp-v1-release`, base `0dd45ab3c07561b04ac264d5ec8d8f28935d4676`. Command results are in `docs/validation/V1_RELEASE_EVIDENCE.md`.

- **Backend Pytest**: 552 passed, 0 failed in 32.23s (`.venv/bin/python -m pytest backend/tests/ -q`, exit code 0). Pillow 10.4.0 reproduces the frozen image bytes. `requirements.txt` stays hash-frozen at `pillow>=10`, so the pin is installed beside that file.
- **PostgreSQL concurrency**: 3 passed in 1.55s with `REQUIRE_POSTGRES=1` on a disposable cluster (`.venv/bin/python -m pytest backend/tests/test_postgres_concurrency.py -q`, exit code 0). A missing binary fails the run.
- **Frontend Vitest**: 13 files, 101 passed, 0 failed in 1.99s (`npm test --prefix frontend -- --run`, exit code 0).
- **Frontend lint**: 0 errors, 99 warnings (`npm run lint --prefix frontend`, exit code 0). The warnings are pre-existing `any` and hook-dependency findings.
- **Playwright Chromium**: 31 passed, 2 skipped, 0 failed in 40.8s (`cd frontend && CI=true npx playwright test --workers=1`, exit code 0). The skips are `frontend/e2e/hosted-real.spec.ts` because `RUN_REAL_HOSTED_E2E` is unset.
- **Human clinician review**: none. No signoff is claimed.
- **v1 head review**: the GitHub Codex review on the draft PR. The October Codex CLI passes below do not review this head.

The October snapshot under "Executed Local Test Suites" is historical. It is not the v1 recount.

**VERIFIED ON LOCAL WORKBENCH.** Full end-to-end local QA execution per `docs/validation/LOCAL_FINAL_QA.md` was completed against the earlier local feature branch. Confirmed findings from two independent OpenAI Codex CLI review passes on that earlier diff were resolved and verified with deterministic tests. No unverified model benchmarks or handwriting accuracy are claimed (A43 stays inside the published evidence boundary, A45 remains deferred).

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
| A08 | Exact raw evidence spans and normalized mapping | VERIFIED within quote and bounds checks | `backend/tests/test_validation_foundation.py::test_independent_checker_detects_evidence_quote_mismatch` and `backend/tests/test_v1_validation_loop.py::test_injected_counterexample_is_labeled_and_independently_detected`. Native pipeline spans are bounds-checked. A claimed `raw_quote` must equal the source slice. |
| A09 | Decimal dose and medication attribution boundaries | VERIFIED for the planted leading-zero canary | `test_independent_checker_detects_decimal_dose_canary` and `test_audit_remediations.py::test_independent_canary_detects_source_naked_decimal_dropped_by_extractor` |
| A10 | Negated/held/stopped/historical/conditional status | VERIFIED for hold/stop on the v1 fixture and gold replay | `backend/tests/test_v1_validation_loop.py` and `backend/tests/test_medication_gold_replay.py::test_real_extraction_hold_stop_trigger_validation_non_active_canary`. Historical and conditional phrasing is not fully covered. |
| A11 | Vital conflicts and ambiguous metadata | VERIFIED | `backend/tests/test_vitals.py::test_conflicting_vitals_handling` (pytest exit 0) |
| A12 | Repeated instructions and narrative disambiguation | VERIFIED | `backend/tests/test_instructions.py::test_repeated_instructions_disambiguation` (pytest exit 0) |
| A13 | Additions persist through draft/reload/export | VERIFIED for server-derived additions | `backend/tests/test_review_coverage.py::test_new_medication_child_fields_form_one_occurrence`. Browser reload of an addition is not a separate e2e. |
| A14 | Child attribute versus full medication removal | VERIFIED | `backend/tests/test_review_coverage.py::test_child_frequency_removal_preserves_medication` and `frontend/e2e/review-persistence.spec.ts` |
| A15 | All decisions and four explicit completeness acknowledgments | VERIFIED | `backend/tests/test_validation_foundation.py::test_review_service_rejects_incomplete_acknowledgments` and `frontend/e2e/review-persistence.spec.ts` |
| A16 | Stale source edit invalidates current completion and queue | VERIFIED | `backend/tests/test_release_guards.py::test_exact_bound_source_edit_preserves_old_extraction_and_stale_edits_fail` (pytest exit 0) |
| A17 | Pipeline rerun requires new review | VERIFIED | `backend/tests/test_routes_notes.py::test_put_note_text_preserves_old_extraction_and_creates_new` (pytest exit 0) |
| A18 | Real concurrent review writers use CAS | VERIFIED when the disposable PostgreSQL job runs | `backend/tests/test_validation_foundation.py::test_concurrent_review_writer_race_detected_and_rejected` and `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_review_writer_barrier`. A skip is not a pass under `REQUIRE_POSTGRES=1`. |
| A19 | Idempotent retry vs conflicting key | VERIFIED | `backend/tests/test_validation_foundation.py::test_idempotent_retry_and_conflicting_idempotency_key` (SQLite barrier) + `backend/tests/test_postgres_concurrency.py::test_postgres_concurrent_job_creation_idempotency_barrier` (PostgreSQL 15 barrier, exit 0) |
| A20 | Strict schema, decision-derived snapshot and spoof prevention | VERIFIED | `backend/tests/test_release_guards.py::test_client_snapshot_cannot_invent_medication_without_matching_decisions` (pytest exit 0) |
| A21 | Cross-workspace authorization on every API | VERIFIED | `backend/tests/test_workspace_authorization.py::test_cross_workspace_isolation_reads_writes_exports_reset_metrics` (pytest exit 0) |
| A22 | Preserving SQLite and PostgreSQL migration | VERIFIED | `backend/tests/test_postgres_concurrency.py::test_postgres_alembic_upgrade_and_schema_verification` (Alembic 001->002->003 executed on real PostgreSQL 15, verified tables, foreign keys, and indexes) + `backend/tests/test_db.py` (exit 0) |
| A23 | Mixed PDF page-wise acquisition | VERIFIED | `backend/tests/test_acquisition_and_encoding.py::test_mixed_pdf_pagewise_acquisition_digital_and_scanned` (pytest exit 0) |
| A24 | OCR resource and failure handling | VERIFIED | `backend/tests/test_ocr.py` + `backend/tests/test_acquisition_and_encoding.py` (pytest exit 0) |
| A25 | Optional provider and logging safety | VERIFIED | `backend/tests/test_ai_provider.py` (zero external calls, negative controls verified, exit 0) |
| A26 | Readiness checks DB/schema/core availability | VERIFIED | `backend/tests/test_app.py` (readiness and health, exit 0) |
| A27 | Current-only metrics and correct denominators | VERIFIED | `backend/tests/test_routes_metrics.py` + `test_audit_remediations.py::test_metrics_excludes_legacy_validations_when_note_needs_review` (pytest exit 0) |
| A28 | Actionable dashboard URL drilldowns | VERIFIED when browser tests pass | `frontend/e2e/validation-loop.spec.ts` asserts the warning row belongs to the fixture note. A generic Metrics smoke load is not this proof. |
| A29 | Keyboard and accessibility behavior | VERIFIED | `frontend/e2e/smoke.spec.ts::Review page — keyboard shortcut Tab activates field, A accepts it` (Playwright exit 0) |
| A30 | Real offline workflow including backend restart | VERIFIED | Playwright against local synthetic backend + Vite dev server across process lifecycle (Playwright exit 0) |
| A31 | Independent failure/mitigation/regression loop | VERIFIED | v1 recount: backend 552 passed, frontend Vitest and Playwright recorded in `docs/validation/V1_RELEASE_EVIDENCE.md`. The October snapshot was 389 / 93 / 25. |
| A32 | Clean checkout reproducibility | VERIFIED | Verified in `.github/workflows/quality.yml` and local virtualenv |
| A33 | AI proposal cannot mutate reviewed state | VERIFIED | `backend/tests/test_multimodal_adapters.py::test_multimodal_ai_candidates_api_preserves_authoritative_state` + `backend/services/review_service.py` (pytest exit 0) |
| A34 | AI/OCR disagreement preserves exact critical tokens | Completed within the cases actually tested | Numeric and negation disagreement tests exist. This is not a claim that every OCR runtime was executed for v1. |
| A35 | Text OCR evidence not treated as verified image evidence | VERIFIED | OCR agreement labeled `ocr_consistent_unverified`; source pixels require human/independent verification. |
| A36 | Transcription correction invalidates review | VERIFIED | `backend/tests/test_validation_foundation.py::test_idempotent_replay_after_source_change_is_not_current_completion` and the revision CAS tests in `backend/tests/test_validation_routes.py` |
| A37 | AI claims without source coordinates rejected | Deferred as independent image evidence | Model-proposed coordinates are not independent image evidence. v1 does not treat them as verified pixels. |
| A38 | Ollama missing/invalid output cannot corrupt NLP | Completed within offline and mocked paths | Those paths do not prove every installed model runtime. |
| A39 | Job leases, idempotency and restart recovery | VERIFIED for enqueue, idempotency, and exhausted-lease finalization | `backend/tests/test_ai_job_pipeline.py` and `backend/tests/test_migration_job_integrity.py::test_worker_finalizes_exhausted_lease_even_with_empty_queue`. This row does not claim a live crash-and-resume drill. |
| A40 | Document image geometry persists | VERIFIED | Original PDF/image viewer uses authenticated blob fetch and coordinate inversion under rotation; verified in browser/unit tests. |
| A41 | Exact review export manifests and scope | VERIFIED | `backend/tests/test_validation_routes.py::test_note_lifecycle_revisions_and_review_export` (pytest exit 0) |
| A42 | Hosted APIs reject free-text/upload/live inference | VERIFIED | `backend/tests/test_workspace_authorization.py` + `frontend/e2e/hosted-mode.spec.ts` (Playwright exit 0) |
| A43 | Recorded public-demo AI results labeled correctly | Completed within the published evidence boundary | `/showcase` publishes the 3-case Tesseract recording and the frozen 24-image aggregate. GLM/Qwen raw transcripts are not published. |
| A44 | Versioned benchmark case-level mismatch drilldowns | VERIFIED | `backend/tests/test_evaluator_strict.py` + ValidationLab pair attribute mismatch display (pytest exit 0) |
| A45 | Handwriting critical-token benchmark | Deferred, out of v1 scope | Genuine handwriting accuracy is not a v1 requirement and remains unvalidated. |
| A46 | Populated UI accessibility and visual QA | VERIFIED | `frontend/e2e/smoke.spec.ts` + `frontend/e2e/screenshots.spec.ts` (Playwright exit 0, screenshots updated in `docs/screenshots/`) |
| A47 | No note source or secrets leaked via logs | VERIFIED | `backend/tests/test_release_guards.py` (pytest exit 0) |
| A48 | Final independent Codex review applied to full final diff | Pending the v1 PR review | Two earlier `codex review --base origin/main` passes covered the workbench diff before this branch. They do not review `feat/clinical-nlp-v1-release`. The v1 review is the GitHub Codex comment on that draft PR. |

## New independent source-audit findings (October 28, 2026)

- Protected page images required browser-side capability headers. The original `<img src="/api/notes/...">` could not send them. The viewer now requests an authenticated blob and revokes its local object URL. Retest actual image loading and page/rotation changes.
- Model-adapter requests for a vision task with only a text source previously fell back silently to text inference. They now fail closed with `IMAGE_SOURCE_REQUIRED`; model names are server allowlisted and the Ollama endpoint is restricted to HTTP loopback.
- The handwriting CER/WER in the prior report came entirely from authored hypothesis strings, not on-device OCR runs. Do not publish these numbers as measured model accuracy.
- Hosted workspace expiry cleanup previously failed to remove dependent `IssueEvent` and `AcquisitionRun` rows before their parents; code/test corrections were added, but PostgreSQL FK behavior must be executed on disposable DB.
- The hosted scenario bundle currently has no versioned AI recordings. A43 requires a separate recorded-run implementation rather than relabeling deterministic fixture output.
- CI status from GitHub Actions and final Codex full-diff review are not confirmed for these new commits. Keep PR draft, do not merge or deploy.
