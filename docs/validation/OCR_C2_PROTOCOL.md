# OCR campaign 2 protocol

Campaign ID: `ocr-campaign2-native-regions-v1`.
Machine-readable copy: `docs/validation/ocr_c2_protocol_manifest.json`.
Partition file, unchanged: `docs/validation/pr10_partition_manifest.json`.

This study does not amend campaign 1. `jpeg_ctx8192__spaces` is not a recognition winner and is not eligible for the untouched holdout.

## Question

Does a preregistered native GLM-OCR mode, with optional deterministic page bands or line strips, reduce paired normalized AMR character error by at least 10% relative to the frozen 8,192-context JSON control, without losing a baseline success or adding a critical-token error, at a cold single-page p95 of at most 60 seconds?

A negative or inconclusive result is a complete outcome.

## Controls and candidates

Controls do not consume a candidate slot. They do consume compute.

- `B8192` is the primary comparator. Installed `glm-ocr:q8_0` is passed on every call. Image preparation is the existing `infer_image` JPEG path: longest side at most 3000, at most 14 megapixels, quality 85, subsampling 0. The frozen JSON OCR prompt inside `glm_ocr_infer` is not edited. `num_ctx=8192`, `num_predict=2048`, temperature 0, `keep_alive=0`.
- `Blegacy` is the secondary historical comparator. It uses the same frozen prompt and omits `num_ctx`. The observed server default is recorded when the control runs. It is not assumed to be 4096. Coverage recovery against this control is not a recognition gain.

Native calls are a separate adapter. They do not go through the JSON grammar in `query_ollama_multimodal`.

- Prompt text is exactly `Text Recognition:`.
- No custom system instruction. The installed template is `{{ .Prompt }}`, so a system string is not inherited from the template. `raw` stays off.
- `format` is omitted. The transport JSON is parsed; its `response` string is the transcription and is not decoded as JSON.
- `model=glm-ocr:q8_0`, `num_ctx=8192`, temperature 0, `stream=false`.
- `N1`: whole page, `num_predict=2048`, `keep_alive=0`.
- `N2`: `N1` with `num_predict=4096`. Run only if `N1` truncated on a development input because generation hit the cap. Do not raise `num_ctx`.
- `N3`: deterministic horizontal bands, cap 2048 per region.
- `N4`: deterministic line strips, cap 2048 per strip. Fall back to the `N3` partition when line segmentation is unavailable.
- `N5`: the best safety-qualified native parent (`N1`–`N4`) with that parent's geometry and generation cap, and `keep_alive=5m` during that page's regions, then unload before the next page. Skip if there is no parent. If outputs differ from the parent, it is a different configuration and must pass the accuracy gates.
- `N6`: `microsoft/trocr-base-handwritten` at revision `eaacaf452b06415df8f10bb6fad3a4c11e609406`, only after native routes fail the development gates and `N4` geometry is usable. One `.safetensors` weight file plus the listed processor files. Do not download `pytorch_model.bin`. No `trust_remote_code`. Not downloaded at protocol time.

Two candidate slots remain for a prediction-affecting correctness fix. A changed prompt, decoder, threshold, fallback, or model setting needs a new fingerprint and a slot. Replay of the same configuration does not take another slot. Every model call consumes time.

No contrast, gamma, sharpen, spacing sweep, output rewrite, or ensemble.

## Segmentation

Version `ocr_c2_segments_v2`. Constants are in the manifest. The page is oriented once, and both the cuts and the crops use that image.

Apply EXIF orientation once. Build an Otsu mask only to find whitespace. The recognizer receives RGB crops passed through `infer_image`, not the mask. A low-ink row has at most 0.1% foreground pixels. A usable gap is at least 8 consecutive low-ink rows.

`N3` looks for one usable gap within 10% of page height of the one-third and two-third positions. The gap center nearest the target wins. Ties go upward. At most three bands. No usable cut yields one page and `segmentation_fallback`.

`N4` cuts only at usable gaps that sit between ink bands. Leading and trailing whitespace stay attached to the neighboring text region, so a blank margin is not its own recognition call. Pieces shorter than 16 pixels merge into the nearest neighbor, and every source row stays in exactly one region. More than 24 regions, or a layout the rules do not handle, falls back to the `N3` partition and marks line segmentation unavailable.

A gutter at least 3% of page width inside the central 20–80%, with low ink on at least 80% of nonblank rows, marks `reading_order_uncertain`. That page is one whole-page region. No text is dropped because it is small. Regions join with one newline. An empty or failed region on a crop that contains ink makes the page incomplete. An empty transcription of a page with no ink is also incomplete. An empty result on a blank margin does not fail a page that still has a scored ink region. A failed page makes the AMR document incomplete. Rx crops stay one region and are not pooled with AMR.

## Data

Screening reuses `screening_selection`: one lowest AMR id per development writer group (8 documents, all pages) and the first 64 hash-ranked development Rx crops. Confirmation uses all 20 AMR development documents and the first 256 development Rx crops. The 892-crop `internal_validation` role was defined in the frozen partition. Campaign 1's closeout did not establish a completed evaluation of it. Campaign 2 may read it once, after the finalist is frozen, and will not call it untouched. The 18 AMR holdout documents and 1,015 untouched Rx test crops stay sealed until the holdout state of a frozen finalist. Screening and confirmation refuse those ids.

## Metrics and selection

Strict micro CER/WER uses the existing `score` function. Normalized text decodes UTF-8, strips a BOM, turns CR/LF into LF, collapses each whitespace run to one space, and strips the ends. Case, digits, punctuation, and order stay. Normalized micro CER is total character edits over total reference characters. An empty reference denominator is undefined, not zero and not a win.

Comparisons require the candidate's complete successes to include every baseline complete success. Occurrence-level critical hits must not fall and occurrence false positives must not rise on matched successes. Full-cohort critical recall must not fall for final eligibility. No critical tokens means N/A with denominator zero. Medication-dose association is not established.

Selection order, before internal validation:

1. Drop invalid provenance, incomplete confirmation, lost successes, and safety regressions.
2. Require paired normalized AMR CER `<= 0.90` times `B8192`. If the baseline CER is 0, no relative gain is claimable. Strict AMR CER/WER, normalized WER, paired Rx normalized CER/WER, and full-cohort normalized AMR CER must not worsen.
3. At least one paired prediction must differ after whitespace normalization.
4. Product eligibility needs cold single-page p95 `<= 60` seconds. Rank is `ceil(0.95 * n)` on the sorted sample, 1-based.
5. Among eligible rows, `E_min` is the best paired normalized AMR CER. The near-best set satisfies both `E <= 1.05 * E_min` and `E <= E_min + 0.005`.
6. Choose the smallest p95 in that set, then lower CER, then fewer recognition calls, then lexical id.
7. A slower candidate can remain an accuracy-only research result. An extra 20% relative CER reduction with unchanged safety is reported separately. It does not open the holdout and does not relax the 60-second product target.

## Budget and provenance

Global model-operation cap: 21,600 seconds, including controls, smoke, retries, warmup, confirmation, validation, and final evaluation. Exploration stops at 7,200 seconds. Cumulative time must be at most 10,800 seconds before holdout. The rest is reserved for the frozen three-arm evaluation. Remaining time is checked before every model call. Per-call cap is 90 seconds. Per-page cap is 120 seconds. A crash charges the attempt's deadline. An unfinished cohort does not get a summary. One machine-level lock lives under the original checkout's private campaign directory.

Identity version `ocr_c2_identity_v3` binds the protocol manifest, partition, ids, source and reference hashes, crop geometry, model id, and request options. Inference identity hashes the native adapter, segmentation, runner, and the `infer_image` implementation (`infer_image`, its size check, and `MAX_INPUT_BYTES`). Scoring identity hashes the normalized metrics, `score`, `CRITICAL`, `_score_text`, occurrence alignment, reference decoding, and the Levenshtein implementation. A change to `score` does not change the inference fingerprint. A scorer change is not a new model run. Consumers recompute metrics from saved predictions and reference bytes. Holdout analysis, if reached, uses 10,000 writer-group bootstrap replicates for AMR and paired-crop replicates for Rx, seed `20261101`. An interval that includes no improvement is inconclusive.

## Integration and states

`OCR_C2_ENABLED=1` is required for the experimental entrypoint. The default is off. Accepted text can be passed to the existing extractor. The raw transcript and any reviewed state stay distinct. The controller states are `preflight`, `review_ready`, `screening`, `confirming`, `optional_model`, `selecting`, `internal_validation`, `final_freeze`, `holdout`, `replay`, `report`, and `stopped`. A missing qualification, a budget block, an integrity failure, or a missing review stops or pauses. Code existing is not a completed phase.

Development inference waits until this protocol and the runner are committed, offline tests and the campaign CI job pass, and a native Codex review of that head is done.
