# PR #10 review rules

These apply to handwritten OCR experiments.

**Immutable evidence.** Reject changes that reuse, overwrite, or relabel predictions unless the source, model, code, prompt, scorer, cohort, and configuration fingerprints match. A saved prediction must replay to its stored scores, including occurrence counts, using the same reference text as the original score. Files that are not `pr10_run_identity_v4` stay legacy and are not rewritten. Inference identity and scoring identity are separate, so a scorer change must not be described as a new model run.

**Coverage and paired evaluation.** Reject comparisons that hide inference failures, turn undefined CER into zero, treat different successful populations as paired, or call a coverage-only gain an accuracy win. An empty transcription is a miss, including one blank page in a multi-page document.

**Holdout and safety.** Reject changes that tune on untouched holdouts, fill in medication values from clinical plausibility, invent human review, leak private data, or claim clinical validation. Unique unmatched critical strings are not occurrence-level dose errors.

**Campaign 2.** `ocr-campaign2-native-regions-v1` is a separate study. Do not restart campaign 1, relabel its checkpoints, or weaken `pr10_run_identity_v4`. Campaign 2 has its own protocol, identity, and private directory. Screening and confirmation must not read the sealed holdout.
