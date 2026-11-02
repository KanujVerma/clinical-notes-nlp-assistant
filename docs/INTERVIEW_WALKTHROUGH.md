# Interview walkthrough

These answers are for a teachback. They are not a claim that a live interview already happened. Personas used while building the workflow: a synthetic reviewer who must see the source before accepting a field, and a manager who needs an issue count to open the exact note. Those are assumptions, not stakeholder interviews.

1. **Trace one synthetic note.** Paste creates a `Note` and `NoteRevision` (`backend/routes/notes.py`). `run_pipeline` (`backend/extractors/pipeline.py`) stores an `Extraction` bound to that revision. `check_extraction` writes `OperationalIssue` rows. `process_review_mutation` (`backend/services/review_service.py`) appends a `ReviewEvent` and updates the note only if the lock version and review head still match.

2. **Why deterministic extraction?** The reviewer has to see why a field exists. An LLM as the authority would hide the rule and make a wrong dose look confident. Optional models stay proposals. They do not complete a review.

3. **How are spans verified?** `verify_evidence` in `backend/validation/checker.py` rejects out-of-bounds spans. If a `raw_quote` is claimed, it must equal `raw_text[start:end]`. A normalized dose is a separate field and does not inherit a fabricated quote.

4. **How are duplicates scored?** `compare_strict_medications` in `backend/evaluation/strict_evaluator.py` pairs shared source-occurrence ids first, then assigns remaining same-name items one-to-one by span overlap. `test_duplicate_pairing_does_not_optimize_correct_dose` locks the failure mode where a scorer would swap doses to inflate F1.

5. **How can a benchmark look too good?** Pooling the 20-note development set with the 24-image run, treating empty support as 100%, or matching duplicate names by the dose that scores best. The showcase keeps those datasets in separate sections.

6. **How does revision binding block a stale review?** A completed event stores `source_revision_id` and `extraction_id`. A transcription edit appends a new revision and clears `review_head_event_id`. Completing or replaying against the old binding raises `StaleReviewError`.

7. **Concurrency and idempotency.** The note update is a conditional `UPDATE` on lock version and head. One writer wins. The same key and body returns the original event only while that event is still the head. The same key with a different body is `IDEMPOTENCY_CONFLICT`.

8. **Dashboard to source.** `/metrics` links to `/metrics/drilldown?kind=issues&severity=warning&state=open`. Each row's label is the issue code and the link carries `note_id`, `source_revision_id`, `extraction_id`, and `issue`. `frontend/e2e/validation-loop.spec.ts` checks the row is the fixture note.

9. **What is validated, and what is not?** The checker, review CAS, workspace isolation, and the frozen archive hash are automated. Clinician review, real patients, and handwriting accuracy are not. The 24-image table is one local synthetic run.

10. **What did the owner do, and what would clinical use require?** The owner set the synthetic-only boundary, the architecture, and the decision not to merge the handwriting research. Agents assisted implementation and review. Clinical use would need a different data policy, clinician adjudication, identity controls, and an owner-approved deployment. This repository does not provide those.

A rejected approach: replacing the scorer with a Hungarian solver so the docs would sound more sophisticated. That would let duplicate doses be matched for a higher score. Another change kept because a counterexample required it: idempotent replay used to return success after the source moved. The regression is `test_idempotent_replay_after_source_change_is_not_current_completion`.
