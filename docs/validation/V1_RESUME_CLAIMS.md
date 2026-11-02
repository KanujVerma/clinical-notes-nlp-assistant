# Resume claim candidates

These are evidence notes for the owner. They are not an edited resume. Do not describe this branch as already merged, and do not describe agent-assisted commits as if they were written without assistance. The dated history is `docs/validation/contribution-changelog.md`.

## Candidate 1

Built a synthetic clinical-note review workbench in which a completed review is valid only for the source revision and extraction it cites, using conditional updates and idempotency keys so a retried or stale client cannot silently replace another decision.

- Code: `backend/services/review_service.py`, `backend/routes/reviews.py`, `backend/routes/revisions.py`
- Tests: `test_idempotent_replay_after_source_change_is_not_current_completion`, `test_concurrent_review_writer_race_detected_and_rejected`, `test_postgres_concurrent_review_writer_barrier`
- Behavior: one writer wins; an identical replay after a source change returns 409 and leaves the original event in history.

## Candidate 2

Separated extraction proposals from independent checks and from human corrections, and showed the loop on a versioned synthetic note with two doses of the same drug, a decimal dose, a held medication, a vital, and a follow-up.

- Code: `backend/validation/checker.py`, `data/validation_loop/`, `frontend/e2e/validation-loop.spec.ts`
- Tests: `backend/tests/test_v1_validation_loop.py`
- Behavior: the real extraction raises duplicate-dose and hold warnings. A planted `.5 mg` quote mismatch is labeled as a counterexample and is not described as model output. The original extraction row stays unchanged when the reviewer edits a dose.

## Candidate 3

Published evaluation results as separate evidence tiers and corrected the medication matcher description to the source-occurrence-first assignment that the code actually runs.

- Code: `backend/evaluation/strict_evaluator.py`, `backend/services/showcase_evidence.py`, `data/showcase/frozen_24_image_benchmark.json`
- Tests: `backend/tests/test_evaluator_strict.py::test_duplicate_pairing_does_not_optimize_correct_dose`, `backend/tests/test_showcase_evidence.py`
- Record: `docs/validation/PR8_REAL_THREE_ARM_RESULTS.md`, archive SHA-256 `d073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d`
- Boundary: 24 fictional printed images. Not clinical validation and not a handwriting score. GLM/Qwen raw transcripts are not on the public showcase.

## What not to claim

HIPAA compliance, clinician validation, production deployment, handwriting accuracy, or that a Vercel URL is running this commit.
