# V1 release plan

Base SHA verified before this branch: `0dd45ab3c07561b04ac264d5ec8d8f28935d4676` (`origin/main`, merge of PR #8).

Branch: `feat/clinical-nlp-v1-release`, created from that SHA in an isolated worktree. The dirty `feat/handwriting-ocr-accuracy` checkout was not reset. PRs #9–#12 stay open and unmerged. This PR is draft and is not auto-merged.

## Architecture

Upload or paste creates a source asset and an immutable note revision. `run_pipeline` writes an extraction bound to that revision and text hash. `check_extraction` writes operational issues from the candidate and the source, not from the extractor's own score. `process_review_mutation` appends a review event and conditionally updates the note head. A later source edit appends a new revision and extraction and clears the current head. Metrics and the queue treat only the current head as the current review.

## Already implemented

Synthetic paste/TXT/PDF/image ingestion, deterministic extraction, review accept/edit/remove, category acknowledgments, export, workspace isolation, metrics drilldown, validation lab, showcase, and the frozen 24-image evidence archive.

## Confirmed defects fixed on this branch

- P1: an identical idempotency replay after the source or review head moved returned HTTP 200 and a completed outcome. It now returns `STALE_REVIEW` and does not insert a second event.
- P1: a parent medication `edit` with no attribute change could be scored `reviewed_corrected`. It is rejected. An attribute edit counts only when the value changes.
- P1: quality CI push trigger targeted `feat/clinical-validation-workbench` instead of `main`. Postgres tests skipped when Homebrew binaries were absent and the suite still exited 0. CI now has a required disposable Postgres job, and `REQUIRE_POSTGRES=1` fails if binaries are missing.
- P1: user-facing docs described medication matching as the Hungarian algorithm. The implementation is source-occurrence-first with a bounded assignment. The docs now say that.
- P1: the acceptance matrix named tests that do not exist. Rows now point at tests that exist, and A34/A37/A38/A43/A45 stay inside their evidence boundaries.

## Known limits, not new P0s

Native extraction spans are bounds-checked. A fabricated `raw_quote` is a critical mismatch. The checker does not treat a normalized dose as if it were the original source text. Integer extraction ids are not a supported lookup; clients use `public_id`. Handwriting accuracy, clinician signoff, and production deployment are out of scope.

## Release gates

G1–G12 in the v1 goal. Evidence for the final SHA is `docs/validation/V1_RELEASE_EVIDENCE.md`. `make verify-release` is the local offline entrypoint.

`requirements.txt` is hash-frozen by the prospective-holdout amendment, so it still says `pillow>=10`. Pillow 10.4.0 is the renderer that regenerates manifest SHA `c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332`. Pillow 12.2.0 and 13.0.0 both emit `88ca0b0ebe0e7f2fe3f2356aa70a7f9aba1db239ebdeb9fd7e36f6a704214d1a`. CI and `scripts/verify_v1_release.py` install or require 10.4.0 without editing the frozen file. Images, gold, model reports, and scores are unchanged.

## Demo

`data/validation_loop/v1_synthetic_note.txt` is the deterministic note. `v1_injected_counterexample.json` is a planted decimal and quote error, not an extractor output. The browser flow is `frontend/e2e/validation-loop.spec.ts`.

## Review policy

Native GitHub Codex review on the PR head. No fabricated human reviewer. High-risk changes are the review-service replay rule, the correction flag, the evaluator description, and the benchmark aggregate. No schema migration was required.
