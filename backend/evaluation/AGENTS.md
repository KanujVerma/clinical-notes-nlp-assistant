# PR #10 review rules

These apply to handwritten OCR experiments.

**Immutable evidence.** Reject changes that reuse, overwrite, or relabel predictions unless the source, model, code, prompt, scorer, cohort, and configuration fingerprints match. Files that are not `pr10_run_identity_v4` stay legacy and are not rewritten. Inference identity and scoring identity are separate, so a scorer change must not be described as a new model run.

**Coverage and paired evaluation.** Reject comparisons that hide inference failures, turn undefined CER into zero, treat different successful populations as paired, or call a coverage-only gain an accuracy win. An empty transcription is a miss.

**Holdout and safety.** Reject changes that tune on untouched holdouts, fill in medication values from clinical plausibility, invent human review, leak private data, or claim clinical validation. Unique unmatched critical strings are not occurrence-level dose errors.
