# PR #10 accuracy plan

Parent: PR #9 `feat/genuine-handwriting-validation` at `b972d5b229986f52f5ec442688b8812c65a1769a`.
Branch: `feat/handwriting-ocr-accuracy`.
This plan is the preregistration for optimization. It is not a claim that accuracy has improved.

## What this study is

PR #9 froze a public-handwriting measurement path. PR #10 uses that path's unchanged GLM-OCR baseline and asks whether inference-level changes reduce character and word errors on publisher handwriting, especially doses, units, and negations.

Publisher transcriptions are not dual-blind clinical gold. Results are not clinical validation, not prescribing safety, and not a reason to process real patient records.

Historical AMR figures (GLM-OCR CER 37.3%, WER 40.3%, critical-token recall 75.8% on 23 documents) and RxHandBD figures (CER 37.0%, WER 77.3% on 100 crops) stay historical. They are not recomputed here and they are not the untouched holdout.

## Architecture

The candidate pipeline is a separate module from the frozen PR #9 runners:

`original bytes → versioned transform → GLM-OCR transcription → parse and validation → optional bounded second pass → source-linked text`

The baseline transform stays the PR #9 function: longest side at most 3000 pixels, at most 14 megapixels, JPEG quality 85, subsampling 0. Any other transform gets its own version id and is scored as a different candidate.

Tesseract 5.5.2 remains an independent baseline. Its text is not mixed into GLM output unless a later, preregistered selection rule wins on development data only.

`qwen3-vl:4b` stays a separate arm. The installed build is the thinking renderer. PR #10 does not change the frozen PR #9 Qwen prompt or token budget, and it does not download a replacement model. A failed or empty Qwen run is reported as incomplete.

No weight fine-tuning. No cloud OCR.

## Partitions

The assignment is `docs/validation/pr10_partition_manifest.json`, schema `pr10_partition_v1`. It stores ids, writer-group codes, and SHA-256 values. It does not store publisher transcriptions.

AMR revision `fa27d29dae4128ac45f035fd580928c84bec4e98`, 62 records, 15 writer groups.

| Role | Documents | Rule |
|---|---:|---|
| Historical regression | 24, of which `AMR_041` stays unscored | The existing PR #9 pilot. Not used for tuning. |
| Development | 20 | Whole writer groups that did not fit in the holdout. |
| Untouched holdout | 18 | `writer_group_greedy_holdout_v1` |

The holdout rule sorts remaining writer groups by name and assigns each whole group to holdout while the holdout count plus that group size is at most 18. That yields holdout groups 01–07 (18 documents) and development groups 08–15 (20 documents). Groups are not split. Every writer group already appears in the historical 24, so the holdout is not contributor-disjoint from the historical cohort. Development and holdout are contributor-disjoint from each other.

RxHandBD v3, DOI `10.17632/dsb5r6vskg.3`.

| Role | Crops | Rule |
|---|---:|---|
| Train development | 3,571 | SHA-256 of the image file name, all but the last fifth. |
| Train internal validation | 892 | Last `floor(4463/5)` names in that rank. |
| Historical test regression | 100 | The existing PR #9 pilot. Not used for tuning. |
| Untouched official test | 1,015 | Every other publisher test crop. |

Official test labels are not used to choose prompts, transforms, or the train split. Writer identity inside RxHandBD is unknown, so writer-disjoint Rx splits are not claimed.

Holdout predictions, gold-based error slices, and holdout metrics stay unread until one candidate is frozen from development and Rx internal validation.

Privacy status for every PR #10 partition: public publisher data, automated screening only, no human privacy attestation, publisher reference text, not adjudicated. PR #9's manual-review seal is not weakened and is not reused to authorize this study. No `reviewer_id` is written for PR #10.

## Metrics

Scored separately for AMR documents and Rx words. No pooled CER.

- Micro CER and micro WER, same character and word distances as the current public scorer.
- Critical-token recall for doses, units, negations, PRN, and hold/stop language, including a leading decimal such as `.5 mg`. A prediction of `5 mg` is not a hit for `.5 mg`.
- Critical-token false positives: numeric or unit tokens emitted by the model that contradict the reference, counted explicitly rather than absorbed into CER.
- Coverage: cases that return a non-empty transcription versus timeouts, parse failures, and model errors.
- Latency: median and p95 per case. A macOS memory snapshot is not model peak RAM.

## Candidates, in order

Each candidate is one change from the baseline, measured on AMR development and Rx train-internal-validation only.

1. Baseline: current GLM-OCR prompt and the 3000-pixel JPEG transform.
2. Contrast and stroke-preserving preprocessing, versioned, without changing the prompt.
3. Line or region crops fed to the same GLM prompt, documents kept intact for scoring.
4. A new transcription prompt. This is a PR #10 prompt, not an edit of the frozen PR #9 prompt.
5. Decoding limits that still fit a 16 GB machine, recorded as their own configuration.
6. Output checks that reject empty text and refuse to invent a dose when the transcription has no numeral.
7. A second GLM pass only when the first pass fails a preregistered coverage check.

A candidate is eligible to freeze only if, on development data, it reduces CER by at least 5% relative to the paired baseline, does not lower critical-token recall, and does not raise critical number or unit false positives. Rx internal validation must not reverse that CER direction. Latency above 2× baseline p95 keeps the candidate experimental even if accuracy improves.

If no candidate meets that bar, the study reports a negative result and does not promote a pipeline.

## Acceptance on the untouched holdout

After the candidate and its code fingerprint are frozen:

1. At least 5% relative CER reduction against the unchanged GLM baseline on the same holdout ids.
2. No decrease in critical-token recall.
3. No increase in critical number or unit false positives.
4. No drop in successful coverage.
5. p95 latency no worse than 2× baseline, unless the result is labeled experimental-only.
6. Independent replay of saved predictions against the frozen references.
7. AMR document scores and Rx word scores reported separately.

Bootstrap intervals are reported with the point estimates. A small point-estimate gain without a stable paired direction is not described as reliable improvement.

## Execution constraints

One model at a time on the 16 GB M2 Pro. The runner writes one case checkpoint at a time and can resume. It does not rerun a checkpoint whose model digest, prompt, transform, or source hash differs. A receipt exists only when every required case is accounted for.

PR #9 seals, raw predictions, and the PR #7/8 scorer stay untouched. PR #10 stays a draft until Codex has reviewed the exact head and substantive findings are fixed. Neither PR is merged or deployed from this work.
