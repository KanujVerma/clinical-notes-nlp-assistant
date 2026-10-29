# Medication parsing: development replay and safety boundaries (PR #6)

## What changed

The deterministic extractor now prefers **explicit, anchored medication orders** from each source line before falling back to section parsing and medSpaCy. This is a candidate extraction improvement only. It does not automate approval or assert that an order is clinically appropriate.

- Preserves numeric strings and units including 0.05 vs 0.5 mg, mcg vs mg, 25 mcg/hr, and 250/50 mcg.
- Captures stated actions only: hold/withhold, start/initiate, continue/resume and stop/discontinue. An unspecified action stays empty, not implicitly "start".
- Preserves distinct source occurrences of the same medication across separate lines, including taper and multiple-dose examples. Same-source mentions found by separate parsing strategies are deduplicated by their overlapping source spans, **not** by name.
- Retains exact half-open source spans on the input transcription. Normal workflow remaps them to the acquired raw text.
- Keeps warnings ("Do not dispense ..."), numeric lab values, and general narrative from becoming new medication orders when they are not explicit dose-and-sig prescriptions.
- Does not use Qwen's proposed values as authoritative and does not infer missing doses/routes/actions. Source-linked human review is unchanged.

This parser does not resolve general medication identity aliases, all complex titration instructions, temporality across paragraphs, tables, or ambiguous negation scope. Unknown formulations may still fail. It is an engineering prototype for synthetic notes.

## Fully reproducible replay: no model calls

From the repo root after installing pinned dependencies:

    python -m pytest backend/tests/test_medication_gold_replay.py -q

    python backend/evaluation/replay_medication_parser.py \
      --manifest data/vision_gold_30/manifest.json \
      --report artifacts/evaluation/paired_local_17f5737320b78e10.json \
      --output-dir artifacts/evaluation

This scorer runs the updated deterministic parser against three kinds of text:

1. **Gold text**: the exact generator-supplied reference transcription. This removes image OCR errors to measure parser behavior alone.
2. **Saved GLM-OCR text**: the original on-device predictions recorded in the immutable PR #5 JSON.
3. **Saved Tesseract text**: the same original predictions from the immutable PR #5 JSON.

Every reported case is verified against the source PNG SHA-256 and dataset manifest identity. All medication record matches use the original strict, source-order evaluator with dose, route, frequency and action as annotated. The replay emits a **new file**, preserving the original benchmark and model digests; Qwen predictions are not rerun or rescored here.

The dedicated Local Vision GitHub Actions workflow uploads a separate artifact named **synthetic-medication-parser-development-replay**, allowing exact counts and error inspection at the PR head.

## Evidence and limitations

- The 30 examples were seen during implementation. They are **development examples**, and post-change improvements are **in-sample**. Do not portray the new scores as an independent holdout or clinical accuracy.
- Original GLM-OCR CER ~1.43%, Tesseract CER ~4.60%, and Qwen direct medication F1 ~0.607 remain attached to the original real model run. The new replay only changes deterministic extraction behavior on stored OCR strings.
- Whole-record F1 penalizes any mismatch in annotated dose, route, frequency, or action as one FP and one FN, even when the drug name is correct. The result is a strict engineering benchmark, not a measure of risk-weighted safety.
- No genuine handwriting, independently transcribed physical notes, model RAM measurement, or clinical validation has occurred. The next validation must freeze parser behavior and normalization **before** creating a separate holdout.
- Never use this pipeline with patient information in the hosted demo or as a medication reconciliation/clinical decision system.

## Next evaluation gates

1. Freeze the parser, normalizers, scorer and prompt digests.
2. Generate a previously unseen printed/noisy/photographed holdout with separately audited gold medication attributes and negative controls; avoid any overlap with the seen 30 cases.
3. Collect genuinely handwritten *fictional* notes and independently transcribe/annotate them. Do not label cursive fonts as handwriting.
4. Measure drug identity, dose/unit, route, frequency, stop/hold negation, duplicate occurrences, source-span quality, omissions and false positive medication orders. Analyze high-risk misses individually.
5. Evaluate false confidence and selective fallback only on frozen independent evidence, with human review as the final authority.

No paid inference, public deployment, production migration or clinical release is part of PR #6.
