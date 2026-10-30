# Prospective synthetic visual holdout protocol (pre-registered)

## Scope and freeze

This protocol is written before the new 24-case corpus is authored or evaluated. Freeze the medication parser, section/medSpaCy fallback, extraction pipeline, scorer, prompt, normalizer, and image renderer on the final merged PR #6 before cases are defined. A lock file records Git blob hashes of all frozen files, baseline commit SHA, and separate case-definition blob. The tool refuses to run if any locked file changes.

No parser or scoring-normalization change is permitted in this evaluation PR after the new predictions are inspected. Record failures as failures; improvements require a new development PR and separately registered future holdout. Never regenerate gold, reselect cases, discard failures, or re-label a development evaluation as prospective.

## Independent of the 30-case development set, not human annotated

- Exactly **24** new fictional notes: eight printed_clean, eight printed_degraded, and eight photographed using the same deterministic renderer. These are printed-font images with photographic effects, not handwriting.
- Case IDs, complete transcripts, and exact medication instruction lines must not repeat the earlier 30-case development corpus. Every generated image and manifest is SHA-256 verified.
- Gold is manually specified **before** model runs. It is prospective relative to frozen parser code, but is **generator-authored, not independently transcribed or clinically adjudicated**.
- Include positive orders, stop/hold, repeats, decimals and unit traps, distractors, follow-ups, and medication-free negatives. Do not select cases based on predictions.
- Report all cases including failures. Record drug occurrence TP/FP/FN, strict record F1 (annotated name/dose/route/frequency/action), per-case mismatch data, CER/WER, critical tokens, true latency and exactly which local models were actually run.
- Treat wrong decimals, units and action polarity as individual safety-sensitive error cases, not just aggregate F1.

## Execution and evidence tiers

Once the finalized lock is committed, run:

    python backend/evaluation/prospective_holdout.py --lock docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json --output artifacts/prospective-holdout --arms tesseract

GitHub Actions measures **real Tesseract** on the new generated images, never mock metrics, and uploads a distinct labeled synthetic holdout artifact. It cannot run GLM-OCR or Qwen3-VL unless the exact local Ollama models are installed on an authorized machine. To measure those locally with already installed models, use --arms tesseract,glm_ocr,qwen3_vl. Missing models imply **not measured**, never simulated results.

The existing paired runner includes generic historical development warnings; the wrapper specifies the accurate data role. New Tesseract scores on the 24 cases cannot be numerically compared directly with GLM/Qwen scores obtained on the earlier 30 cases.

## Genuine handwriting is separate

Volunteers must physically handwrite entirely **fictional** notes using a pen or freehand stylus. Obtain separately produced and reconciled reference transcriptions from at least two independent transcribers, with a separate adjudicator and pseudonymized writer. Record capture method, ambiguous letter/number resolution, and confirmation that images contain no real patient data or identifying information.

    python backend/evaluation/handwriting_intake.py --manifest /private/fictional-handwriting/manifest.json

This validator checks submitted hashes and provenance attestations but cannot prove the attested handwriting or annotator independence. A human must inspect the original source and written records. **No real human handwriting samples have been supplied or measured.** Cursive fonts or model-generated imitation handwriting must never be reported as genuine samples.

## Claim constraints

A synthetic printed holdout offers narrow evidence about unseen artificial case patterns only. It cannot establish clinical validity, actual handwriting accuracy, medication reconciliation safety, HIPAA compliance, or real-patient performance. Models and parsers generate untrusted proposals, with source-bound human review as the authority.

No hosted deployment, database migration, EHR connection, new automatic model decision route or paid API inference is included. Select model routing and performance thresholds only after analyzing frozen prospective evidence in a separate PR.
