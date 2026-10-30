# Prospective synthetic holdout v1: measured Tesseract baseline

## Evidence record

- **CI run:** [GitHub Actions #41002641807](https://github.com/KanujVerma/clinical-notes-nlp-assistant/actions/runs/41002641807), completed successfully; 24 actual on-runner image-to-text Tesseract predictions, not mocks
- **Runner Tesseract version:** `5.3.4`
- **Frozen merged parser/scorer baseline:** `b58a65da2b28917aedd5504c4c8b7e5818f03033`
- **Case-definition Git blob:** `e2f76eb94688e610bbde27a76781d47bb7744a2d`; authored after pre-case source seal
- **Full generated manifest SHA-256:** `c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332`
- **Original real model results SHA-256:** `af910b4d12211b784d03b5962cdede048231d5bb04510f33844e2ab83c01217b`
- **Dataset:** 24 **new, fictional, generator-authored** printed-font images; eight clean, eight degraded, eight photographed-effect
- **Annotations:** 23 medication occurrences and 5 vitals; synthetic generator-authored gold, **not independent human annotation**
- **Omitted-dependency audit:** added after images were authored and first actual run, but before examining numeric results. Pinned five additional original PR6 blobs (vitals, metadata, instructions, config, requirements) and preserved the original pre-case seal unchanged. See `FROZEN_DEPENDENCY_AMENDMENT.json`.

## Real measured results

| Metric | Tesseract + frozen deterministic rules |
| --- | ---: |
| Character error rate (micro) | 0.041782, **4.18%** |
| Word error rate (micro) | 0.317814, **31.78%** |
| Critical text token hits | **41 / 55** |
| Strict medication-record TP / FP / FN | **12 / 2 / 11** |
| Medication precision / recall / F1 | **0.857 / 0.522 / 0.649** |
| Strict vital-record TP / FP / FN | **4 / 0 / 1** |
| Vital precision / recall / F1 | **1.000 / 0.800 / 0.889** |
| Runner p50 latency | ~270 ms per image (run-specific; later CI measurements may vary) |

These are original strict name/dose/route/frequency/action occurrence metrics on explicitly annotated synthetic fields; no medical safety claims follow from F1. Exact reported latency depends on runner resources.

## Case-level error attribution

All 24 sources and every prediction are retained in the downloadable Actions artifact. Selected observed errors illustrate the problem:

- **h01:** `Bisoprolol` was transcribed as `Bisoprolal`; `PO QAM` merged into `POGAM`. Wrong drug identity, not a source-grounded medication match.
- **h04:** `Baclofen 5 mg PO QAM` became `POQAM`, and `Baclofen 10 mg PO QHS` became `POOHS`. Both occurrence matches were missed.
- **h07:** `Tiotropium 18 mcg` became `18 meg`. This is a high-risk unit corruption and was **not** silently normalized.
- **h12:** `Budesonide 90 mcg` became `90 meg`; `SpO2 97%` became `5p02 97%`. A medication and vital were missed.
- **h17:** The second `Levetiracetam` order was transcribed as `POat bedtime`; route/frequency association differed from gold, generating an FP and FN under strict whole-record scoring.
- **h18:** `Aztreonam 1 g IV` became `Aztreonam 1 IV`, dropping the gram unit.
- **h21:** `Hydroxyzine 10 mg PO every 8 hours` became `10 ma PO every hours`, losing a dose unit and interval number.
- **h06, h14, h22:** Medication-free source examples did not produce a predicted medication record.

No hand-edited repair of these OCR errors was included in the scored predictions. Apparent names, doses and unit strings require review against the source, not automatic completion.

## What is still NOT measured

**GLM-OCR and Qwen3-VL on these 24 images:** not run in this workflow, so their out-of-sample metrics and comparable ranking are **unavailable**. Their earlier 30-case development results do not substitute for same-image testing.

**Genuine handwriting:** not tested. The human-writing provenance intake is ready, but no independently transcribed, genuinely hand-produced fictional notes were provided.

**Ollama model memory:** not measured by this Tesseract-only job. Its report marks out-of-process model memory not applicable, not zero.

## Follow-on architecture gate

Before choosing GLM-OCR as default or Qwen as an additional candidate, run both against these **identical frozen images** using locally installed model digests. Preserve Tesseract's predictions and full mistake list, report paired per-case wins/losses for drug/dose/action fields, and measure actual Ollama residency and latency. Avoid deploying an automatic medication router or prescribing logic. A human reviewer remains the sole authority.

**Scope:** Synthetic engineering benchmark only. Not clinical validation, not HIPAA compliance, not an EHR or prescribing system, no production release.
