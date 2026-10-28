# Local visual evaluation — PR #3

## Goal

Compare **real** local image-to-text OCR from Tesseract and GLM-OCR using
identical original synthetic images, then separately evaluate Qwen3-VL's
structured medications/vitals. No generated test string may be reported as
an observed model transcription. The comparator and corpus are pinned by
hashes, model names and actual installed model digests.

This is a synthetic **development benchmark**, not a clinical adjudication,
generalization estimate, or proof that model output can be used for care.

## Full workflow

Create the printed, degraded and critical-token development images:

    .venv/bin/python backend/evaluation/generate_synthetic_visual_cases.py \
      --output data/vision_gold

Run real Tesseract only, even with Ollama absent:

    .venv/bin/python backend/evaluation/local_vision_eval.py \
      --manifest data/vision_gold/manifest.json --arms tesseract

If the free local models are installed, run one complete paired evaluation:

    ollama --version
    ollama list
    .venv/bin/python backend/evaluation/local_vision_eval.py \
      --manifest data/vision_gold/manifest.json \
      --arms tesseract,glm_ocr,qwen3_vl

There are **no model pulls** in this code, no remote providers, and no
separately billed API requests. The installed Ollama endpoint must be a local
HTTP loopback address. Do not attempt all models simultaneously on the
16 GB Apple Silicon machine. The adapter unloads after each request with
keep_alive=0. If RAM or disk is insufficient, record NOT RUN rather than
substituting a remote model.

Run first:

    .venv/bin/python -m pytest backend/tests/test_local_vision_eval.py \
      backend/tests/test_vision_benchmark_contract.py -q
    .venv/bin/python -m pytest backend/tests/ -q

## Scoring contract

- **Tesseract**: image-to-text OCR; report case-level and micro
  character error rate (CER), word error rate (WER), exact critical-token
  hits/misses, runtime latency and Tesseract version.
- **GLM-OCR**: same original image bytes, same human/generator gold
  reference, same CER/WER/critical-token scorer, runtime latency and
  installed Ollama model SHA/digest. Must have a real successful model
  response to appear in a completed report.
- **Paired comparison**: one row per case with Tesseract and GLM errors
  measured on the same frozen image and reference. No comparison of
  incompatible legacy F1 scores.
- **Qwen3-VL**: extracts structured medication and vital fields, NOT a
  transcript. Report exact per-attribute/source-order whole-record
  precision/recall/F1 and raw TP/FP/FN against explicit synthetic gold.
  It has **NO CER/WER** column because it was never asked to transcribe
  an entire note. Unit and decimal values must be retained exactly.
- Duplicate-name medications pair by source occurrence/order, not by
  whichever dose happens to be correct. A wrong attribute counts one FP
  plus one FN for that record. Absent gold support returns N/A, not 100%.
- Critical-token hit counts are string-detection diagnostics, not proof
  of medication attribution, negation understanding or clinical safety.
- Reports include exact source image hashes, manifest SHA, Git SHA,
  installed model digests, per-case raw predictions and time spent.
  A model failure blocks publication of a completed all-model report.

## Evidence tiers

1. **Unit test only** — mocked predictions, validates the measurement
   code but never establishes AI performance.
2. **Printed synthetic images with Tesseract** — real offline OCR
   baseline; no Ollama claims.
3. **Paired printed GLM-OCR and Qwen3-VL runs** — real local inference on
   generator-derived development images, not a held-out corpus.
4. **Independently transcribed synthetic handwriting** — A45 can only
   advance when genuinely handwritten synthetic images, independently
   specified gold transcription and a real installed model are measured.
   A generated cursive-like font is not independent handwriting.

## Local Mac-only verification for Gemini

Check installed models and machine resources before pulling anything.
Do not change Vercel, Render, Supabase or billing. Execute the fast tests
and baseline first, then real models if available and affordable in RAM.
Save the raw generated JSON and a short note listing the exact Git commit,
model digest, real critical-token misses, latency and what was NOT RUN.

Run free Codex review using the owner's existing ChatGPT-authenticated
CLI against the entire committed PR #3 diff. No Vercel review bot or
API-key billing. Fix confirmed code bugs and rerun actual affected tests.
Keep PR as draft until reviewed. PR #4 will later use legitimately
measured, versioned results in the public synthetic showcase.
