# 30-case local vision benchmark: source audit

This audit distinguishes the ORIGINAL, actual on-device model predictions
from Gemini's narrative and a separate POST-HOC alias reanalysis.
The data are synthetic generator-derived images, not held-out clinical
validation or genuine handwriting.

## Immutable recorded inputs and outputs

- Original results: artifacts/evaluation/paired_local_17f5737320b78e10.json
- Dataset: data/vision_gold_30/manifest.json
- Dataset SHA-256: 219f4425cb9a2d786c389fc1cb82427ff4a6dce15429fe12c58b96bd4f9a8e1b
- Thirty images: 10 printed clean, 10 printed degraded, 10 photographed-effect
- Tesseract 5.5.2, GLM-OCR:q8_0, Qwen3-VL:4b on-device
- GLM digest: 6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f
- Qwen digest: a1b29c246319cdcb1f3842f36d29f198f737c0cf516ba1bcba34b1b974e87980
- Artifact evaluated Git SHA: 22f38cc8a4feabb3f9ddddd77539dfcdad6d0d4e
- Final submitted branch SHA: f2dbf1d66b7f2665d35c5bb7ccc6c6a8e9a64e36
- The model runner RSS of about 224.5 MiB is NOT out-of-process Ollama
  model RAM. Actual model memory remains unmeasured.

## Correct summary from saved JSON (not the prose)

| Arm | CER | WER | Literal critical-token hits | Medication F1 and counts | Vital F1 and counts |
| --- | ---: | ---: | ---: | --- | --- |
| Tesseract + rules | 4.60% | 31.23% | 100/119 | 0.0000, TP0 FP6 FN46 | 0.7273, TP16 FP4 FN8 |
| GLM-OCR + rules | 1.43% | 4.20% | 119/119 | 0.1905, TP6 FP11 FN40 | 0.8511, TP20 FP3 FN4 |
| Qwen3-VL direct | N/A | N/A | N/A | 0.6067, TP27 FP16 FN19 | 0.0377, TP1 FP28 FN23 |

The pasted narrative reported Tesseract vitals F1 as 0.6818,
GLM medications as TP8 FP4 FN38, and a different Qwen model digest.
These differ from the committed artifact. Use the saved JSON and
validate scorer/provenance differences before a public claim.

## Critical case-level corrections

- clean_02_decimal_warfarin: the actual saved Qwen response contains
  ZERO medications, not the claimed correctly extracted Warfarin 2.5 mg.
  GLM transcribed the hold and Do not dispense sentences accurately, but
  the deterministic pipeline did not reconstruct a correct medication.
- clean_05_decimal_haloperidol: GLM correctly transcribes 0.5 mg;
  deterministic rules still omit this medication. Qwen finds it but uses
  an unannotated indication in the action field.
- photo_04_microgram_nitrostat: GLM transcribes 400 mcg; deterministic
  rules miss the drug. Qwen detects it but places PRN in the action
  text instead of the annotated frequency.
- photo_06_continue_discontinue_anticoagulation: actual synthetic source
  says Continue Apixaban and Discontinue Aspirin. The prose describes
  a different Warfarin-to-Apixaban scenario.
- clean_07_multiple_vitals_panel: Qwen predicted BP 118/78, but
  frozen gold is 118/76. Alias normalization must never hide this.

## Major vital-sign scoring artifact

The original strict scorer treated BP versus blood_pressure, HR versus
heart_rate, RR versus respiratory_rate, SpO2 versus oxygen_saturation,
and Temp versus temperature as unrelated entities. This artificially
lowers the ORIGINAL Qwen vitals F1 of 0.0377.

The new versioned replay tool reads the same saved Qwen candidates,
verifies ALL source image SHA-256 bindings and manifest identity,
and adds a separate POST-HOC score without calling Ollama:

    python backend/evaluation/replay_vital_scoring.py \
      --manifest data/vision_gold_30/manifest.json \
      --report artifacts/evaluation/paired_local_17f5737320b78e10.json

Expected exploratory result from independent replay calculation:
TP23 FP6 FN1, F1 about 0.8679, requiring CI confirmation.
The alias table was chosen AFTER inspecting outputs; this is NOT
prospective evaluation. A new frozen holdout is required before
treating it as validated comparable model performance.

## Architecture justified so far

1. GLM-OCR is the strongest transcription candidate on these generated
   printed/noisy/photo images. Literal critical-token hits are not
   medication association, action polarity or negation correctness.
2. Qwen is an independent structured-candidate source, not an
   authoritative review system. It omitted critical Warfarin 2.5 mg
   despite a good aggregate medication F1 and sometimes confuses
   temporal action fields with indications and frequency.
3. The deterministic medication parser is the main bottleneck:
   medication F1 only 0.1905 on GLM transcripts with examples of
   exactly correct OCR followed by failed extraction. Fix semantic
   parser normalization and associations, then evaluate with gold.
4. Keep Tesseract as a fast baseline/fallback (~0.21 s/case versus
   GLM ~8.9 s) until threshold/selection policies are calibrated.
5. Preserve source -> immutable proposals -> deterministic
   discrepancy checks -> human-authorized review.

Still needed: prospective held-out printed corpus with frozen
normalization; separately handwritten and independently transcribed
fictional notes; case-level dose/unit/action error audits; true
Ollama model RAM/swap measurement; final Codex PR review and CI.

No hosted deployment, production migrations, cloud inference, patient
identifiers, clinical accuracy or handwriting claims are authorized.
