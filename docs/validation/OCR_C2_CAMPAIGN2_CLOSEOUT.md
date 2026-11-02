# OCR campaign 2 closeout

Campaign ID: `ocr-campaign2-native-regions-v1`.
Reporting date: 2026-11-02, America/Chicago (CST, UTC-06:00).
Measured head: `7ea3a70ea54b9322b86181a9231e6440e44e74b7`.

## Final disposition

**Campaign 2 is stopped after screening. No native configuration qualifies for confirmation, internal validation, or the untouched holdout.**

The study question was whether a preregistered native GLM-OCR mode reduces paired normalized AMR character error by at least 10% relative to `B8192`, without losing a baseline success or adding a critical-token error, at a cold single-page p95 of at most 60 seconds. On the fixed screen, the best native arm, `N4`, reduced that error by 6.5%. Every native arm also added occurrence-level critical false positives. Stage C confirms only configurations that preserve coverage and safety. None did, so there is no native candidate and no cosmetic winner.

This is a negative screen, not a claim that another recognizer cannot do better.

## What ran

Screen cohort: 8 development AMR documents (one page each) and the first 64 hash-ranked development Rx crops. The same ids were attempted for every finished arm. Holdout ids were not read. The 892-crop internal-validation set was not opened.

| Arm | AMR scored | Rx scored | Paired normalized AMR CER | Relative to B8192 | AMR occurrence hits | AMR occurrence false positives | AMR page p95 (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B8192 | 8/8 | 64/64 | 0.3551 | baseline | 29 | 13 |  |
| N1 | 8/8 | 64/64 | 0.3520 | 0.87% | 29 | 14 | 27.5 |
| N3 | 8/8 | 64/64 | 0.3520 | 0.87% | 29 | 14 | 25.7 |
| N4 | 8/8 | 64/64 | 0.3319 | 6.53% | 29 | 15 | 28.8 |
| Blegacy | 2/8 | 64/64 | not paired | lost 6 AMR successes |  |  |  |

The 10% gate requires paired normalized AMR CER at or below `0.90 * 0.3551 = 0.3196`. None of `N1`, `N3`, or `N4` meet it. Strict AMR CER/WER and normalized WER did not worsen. Paired Rx normalized CER moved from 0.3721 to 0.3605 and did not worsen. Rx occurrence counts were zero on both sides. One AMR comparison per native arm differed only by whitespace; seven differed after normalization, so the change is not whitespace-only. Page p95 on the eight AMR screen pages is under 60 seconds. Latency is not the stop reason.

`Blegacy` is the secondary control, not the primary comparator. Six of its eight AMR documents returned an empty transcription and are incomplete. Its 64 Rx predictions match `B8192` byte for byte. The omitted-context AMR failures are a coverage failure, not a recognition gain.

## Skipped configurations

- `N2`: not run. `N1` had no generation-limit stop, which is the only condition that authorizes the larger cap.
- `N5`: not run. It requires a safety-qualified native parent. The screen has none.
- `N6`: not run. The measured head authorizes the TrOCR file list and does not contain a TrOCR recognizer. Adding one would be a new code head after these measurements. No weights were downloaded.

Candidate slots used: 3 (`N1`, `N3`, `N4`). Controls do not consume a slot.

## Provenance

- Codex review of `7ea3a70` found no issues: https://github.com/KanujVerma/clinical-notes-nlp-assistant/pull/11#issuecomment-6571307796. The review state records `has_any_findings: false`.
- All six PR checks passed on that commit before any development model call.
- Installed model `glm-ocr:q8_0`, Ollama `0.40.12`, digest `6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f`. No weight download and no tag update.
- Private driver called the reviewed `run_page` and frozen `glm_ocr_infer`. It is not in git. Predictions stay under the original checkout's `artifacts/handwriting-private/ocr-campaign2-native-regions-v1/`.
- Replay recomputed all 354 scored screen cases from saved predictions and reference bytes. All 354 verified. The 6 unscored `Blegacy` AMR documents were not treated as successes.
- Model time charged: 1,225.7 seconds, including a 3.52-second diagnostic call and the deadline charge for one interrupted `Blegacy` attempt. Exploration cap is 7,200 seconds. Campaign cap is 21,600 seconds. No reset.
- `OCR_C2_ENABLED` remains off. No product profile was enabled. PR #11 stays unmerged.

## Process state

Stopped. Checkpoint `stop_reason` is `no_safety_qualified_native`. Confirmation, internal validation, holdout, and a finalist replay were not opened because the screen produced no safety-qualified native configuration.

## Clarification, 2026-11-02

The disposition above remains the native-screen result. It is not a finding that every approved route was exhausted.

Native screening is complete and negative. `N1`, `N3`, and `N4` did not meet the 10% paired normalized-CER reduction, and each added critical false positives. The optional recognizer was not evaluated. At the measured head `7ea3a70` its implementation was missing. That absence was an implementation gap, not a scientific exclusion. The campaign stayed implementation-blocked until the authorized geometry check below.

The historical private driver is preserved and was not rewritten. Its sha256 is `486e15ea2bb9824cf821215e79ea42991384ae246a0a270e1a9ab608a61d3167`. A later parameterized executor is `backend/evaluation/ocr_c2/screen_driver.py`. That file is not the source that produced the saved predictions. Replay of the 354 scored cases still does not prove the historical driver's provenance.

Saved page files record region counts and call outcomes. They do not record crop hashes, boxes, or fallback flags. Those flags were recomputed locally with the frozen segmenter on the same development images. Aggregates are in `docs/validation/ocr_c2_screen_geometry.json`.

`N1` and `N3` each made one recognition call on every development page and crop. Recomputed band geometry is one full-page region on all 8 development pages: 5 pages were column-uncertain, and 3 fell back because no usable band cut existed. `N3` did not produce different image regions from `N1`. The identical aggregate CER follows from identical whole-page inputs.

`N4` made one call on 7 development pages and two calls on 1 page. Five pages were column-uncertain whole pages. Two more remained a single region under the line rule. One page was split. The median region covers the full page, and the median ink span is 2,250 px. All 64 development Rx crops stayed one region because the column check was uncertain. Usable single-line geometry is not established. The optional phase stops for `geometry_blocked`. No recognizer weights were downloaded.

The controller now sends a nonqualifying screen to optional-model eligibility. Integrity failures and exhausted budgets during screening still stop immediately. The eligibility check does not start TrOCR when geometry, download compatibility, budget, or review is missing. Confirmation, internal validation, and holdout stay closed. `B8192` evidence is the screen already charged against digest `6e5935a916fc8d6878a67c60c2b99648f54e10b4a4af4cbbfb2c308953000e5f` at head `7ea3a70`; it was not rerun. The live ledger still charges 1,225.7 seconds. The earlier checkpoint is preserved beside the private campaign directory as `checkpoint-native-screen.json`. The current checkpoint stop reason is `geometry_blocked`, with `previous_stop_reason` `no_safety_qualified_native`.
