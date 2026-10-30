# PR #8: Real local GLM-OCR / Qwen3-VL frozen-holdout comparison

## Meaning of the evaluation

PR #7 froze 24 fictional images: eight clean printed, eight degraded printed, and eight photographed-effect printed. This PR adds strict three-arm execution and independent replay for Tesseract, GLM-OCR and Qwen3-VL, **without changing any of the frozen scoring rules, OCR prompts, extraction code, images or gold annotations**.

**GitHub Actions cannot measure GLM/Qwen unless those actual local models are installed.** CI performs real Tesseract and clearly mocked contract unit tests; their mock outputs are never model-accuracy claims. The user's Mac must complete the real local GLM/Qwen runs before publishing a three-way ranking.

Frozen PR #6 code baseline: b58a65da2b28917aedd5504c4c8b7e5818f03033.

Canonical original PR #7 manifest SHA-256: c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332.

The existing PROSPECTIVE_HOLDOUT_LOCK.json and its documented retrospective dependency amendment remain unchanged. An image whose rendered bytes differ from the original PR7 sources is **not** the same test case.

## Local Mac setup and immutable source acquisition

From the project repository, check out the PR8 branch and make sure the project dependencies are installed with Python 3.11. Install Tesseract/Poppler if needed. No API keys are needed. Never use actual patient notes.

    git switch feat/paired-local-model-comparison
    python3.11 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    brew install tesseract poppler

Get the **actual original 24 images/gold** from GitHub Actions run #41003374761. Do not regenerate the images on the Mac and assume they match:

    gh auth status
    gh run download 41003374761 -n prospective-synthetic-holdout-tesseract-only -D artifacts/pr7-source

These files should include artifacts/pr7-source/dataset/manifest.json plus dataset/images/*.png. The script verifies **every source image hash**, exact gold labels, original manifest SHA and unchanged freeze. Verify without querying models:

    .venv/bin/python backend/evaluation/run_paired_holdout.py --manifest artifacts/pr7-source/dataset/manifest.json --preflight

## Actual local inference

Run all three arms on the **same image bytes**. Default installed tags from the frozen adapters are:

- GLM-OCR: glm-ocr:q8_0
- Qwen3-VL: qwen3-vl:4b
- Tesseract: locally installed system OCR executable

The benchmark **enforces these exact two model tags**. If OLLAMA_OCR_MODEL or OLLAMA_VL_MODEL overrides either one, execution fails with NONCANONICAL_LOCAL_MODEL_TAGS before making any inference or creating results. This prevents accidental comparisons against different architectures or quantizations. The real installed model digest is independently rechecked after each full 24-image arm.

Check the installed tags with ollama list and local service health, and use only the loopback endpoint http://127.0.0.1:11434. The runner never downloads models. If missing, check resource and disk limits and ask the user before pulling any models. Do not switch tags or use a remote API and call it the same experiment.

    export OLLAMA_HOST=http://127.0.0.1:11434
    .venv/bin/python backend/evaluation/run_paired_holdout.py --manifest artifacts/pr7-source/dataset/manifest.json --output artifacts/pr8-real-three-arm --execute

The runner **preflights both installed Ollama digests before creating any result** and processes one arm at a time. On the user's 16-GB Mac, avoid other large local agents running simultaneously. The existing source-bound model adapter already uses keep_alive=0 and temperature=0.

Outputs:
- paired_comparison.json: source-verified strict medication/vital accuracy, per-case errors, same-source comparison, model digests, latency and observed resource samples
- completion_receipt.json: immutable SHA-256 references to all reports, created **only after all three pass**
- single_arm_reports/{arm}/paired_local_*.json: actual unmodified model predictions and scoring
- execution_status.json: an intentionally incomplete initial marker; **not evidence of success**

Incomplete runs must be reported as incomplete, even if one or two arms succeeded. Use a new output directory for each rerun.

## Repeatable independent audit, without model calls

From the original actual single-arm report files, run an offline replay:

    .venv/bin/python backend/evaluation/run_paired_holdout.py --manifest artifacts/pr7-source/dataset/manifest.json --compare-only --tesseract-report TESSERACT_JSON --glm-report GLM_JSON --qwen-report QWEN_JSON --original-paired-report artifacts/pr8-real-three-arm/paired_comparison.json --completion-receipt artifacts/pr8-real-three-arm/completion_receipt.json --output artifacts/pr8-verified-replay

The replay verifies all 24 image SHA values, original text labels and model predictions, recomputes every case score using the same frozen source-order scorer, verifies aggregate TP/FP/FN and text CER/WER, and refuses missing or duplicate cases. It makes **zero model calls**. It additionally requires the original complete execution receipt and its SHA-bound paired result, proves that all three raw arm files match their original hashes, and checks the preregistered model tags and their recorded digests. This guards accidental report/model substitution; JSON hashes alone do **not** provide independently signed proof of the host or hardware.

**Metrics:** strict medication whole-record TP/FP/FN/F1 (annotated name, dose, route, frequency, action), vital TP/FP/FN/F1, per-case wins/losses/ties, critical OCR token misses, OCR CER/WER for Tesseract and GLM ONLY, per-arm latency and actual model versions/digests. Qwen returns direct structured fields; it has **no OCR CER/WER**. Model comparisons are between different architectures but on identical annotated images.

**Memory:** Ollama /api/ps model residency/VRAM and separate observed runner RSS are sampled during each arm, if possible. Missing samples remain unmeasured, never zero. Mac sysctl vm.swapusage snapshots before and after each arm are total-system snapshots, **not** peak or model-attributable memory. Do not add shared/system RAM to VRAM or claim precise model-specific swap peaks.

## Boundaries and failure handling

This is a previously unseen **generator-authored synthetic printed** benchmark, not independent human adjudication, genuine handwriting, clinical validity, or evidence of safe prescribing. Reports retain complete original model text/candidates; no automatic fixes to dose, decimal, unit, frequency or stop/hold status. Cases with zero medications are scored as negatives, not discarded.

Stop on missing local models, mixed or modified source images, changed frozen code, malformed or incomplete output, changed model digests, mismatched scores or unattested memory measurements. Do not alter PR7 gold or parser/scorer to improve scores. Do not deploy production or silently change the routing architecture.

Share the entire original artifacts/pr8-real-three-arm directory as a ZIP, plus terminal output, commit SHA and nonsecret model version listing. The PR will remain draft until authentic Mac-model measurements and final review are available.
