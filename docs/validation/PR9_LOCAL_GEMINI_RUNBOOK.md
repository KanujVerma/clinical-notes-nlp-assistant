# PR9 local execution handoff for Gemini / a Mac terminal agent

**Purpose:** carry out the approved **AMR document** and **RxHandBD word** public handwriting evaluation under PR #9. This runbook **does not authorize** deploying the app, merging PR9, modifying frozen PR7/8 logic, publishing source images or patient identifiers, downloading new Ollama models, or using cloud vision/LLM APIs on images. PR9 original six-person study remains a separate, optional stronger research protocol. Publisher text is **not** independently adjudicated gold.

## Goal and success conditions

- Checkout PR9 branch `feat/genuine-handwriting-validation` into a clean working tree. Confirm latest PR/branch and read `docs/validation/PR9_PUBLIC_HANDWRITING_DATASET_PROPOSAL.md`.
- Source AMR from **Hugging Face dataset revision `fa27d29dae4128ac45f035fd580928c84bec4e98`** (62 source records, 15 publisher contributors, 5 multi-page). Source RxHandBD from **Mendeley v3 DOI `10.17632/dsb5r6vskg.3`**, use `RxHandBD-ML.zip` publisher test split only (1,115 labeled words). Do not fetch a moving revision or include training images in the test.
- Before local inference, confirm no real patient data/identifiers in selected images or publisher labels. Generate and facilitate a real local review without fabricating a human signature or using the benchmark models to decide if their own predicted text is accurate.
- Verify original source bytes and published labels, freeze selected sources/transformations/reviewer decisions/implementation, and independently timestamp the SHA-256 of each study seal.
- Run actual local Tesseract, GLM-OCR `glm-ocr:q8_0`, and **Qwen3-VL with a separate frozen OCR transcription prompt** `qwen3-vl:4b` sequentially on precisely the same AMR pages and Rx test crops. Do not confuse Qwen structured extraction with transcription. No model downloads or external inference.
- Independently replay saved predictions against exactly the frozen publisher reference, and write **privacy-safe aggregate** CER/WER/critical-token-recall/latency results with provenance, denominators and limitations. Do not report numeric accuracy from test mocks or partial runs. Keep PR9 draft until full evidence review.

## AMR workflow

1. First check Python 3.11 environment, `tesseract --version`, `ollama list`, installed local model digests, and working branch. Honor resource limits of a 16 GB Apple Silicon Mac: one arm at a time; scripts use keep_alive=0 for local Ollama.
2. Install only necessary Python packages in the local virtual environment, preferably from the repository's pinned `requirements.txt`; if `hf` CLI is unavailable, use `pip install huggingface_hub` in that venv, without modifying project requirements to introduce production dependencies.
3. Fetch the pinned upstream:
   ```bash
   hf download Nigeria-Health-data-OCR-pipeline/African-Medical-Records --repo-type dataset --revision fa27d29dae4128ac45f035fd580928c84bec4e98 --local-dir data/handwriting-private/amr-upstream
   python backend/evaluation/public_amr_benchmark.py scaffold --dataset-root data/handwriting-private/amr-upstream --study data/handwriting-private/amr-intake
   ```
4. Validate the private `selection.json` against 62 original records, source image hashes and publisher references. Exactly 24 selected in a preregistered round-robin source-contributor pilot. Multipage must stay **one document per transcript**, never multiply its gold across pages.
5. **Privacy review gate:** `privacy_review.json` is deliberately blank. Locally generate a Finder/open-image or contact-sheet review queue, with individual original pages and publisher transcripts visible offline. Never upload these scans or their contents to Gemini/other cloud services. The agent may identify candidate concerns from filenames, local regex or local tools, but cannot falsify a human's completed review or assert consent. If a real reviewer is not available, stop before sealing and report this exact blocker. The publisher's statement of synthesized/volunteer data is not independent proof of zero identifiers. User has approved use of datasets but not fabricated review attestations.
6. After the actual reviewer fills all chosen cases (approved or pre-inference excluded with reason) and the reviewer ID, seal and run:
   ```bash
   python backend/evaluation/public_amr_benchmark.py seal --study data/handwriting-private/amr-intake --out data/handwriting-private/amr-sealed
   shasum -a 256 data/handwriting-private/amr-sealed/study_seal.json
   python backend/evaluation/public_amr_benchmark.py verify --sealed data/handwriting-private/amr-sealed
   python backend/evaluation/public_amr_benchmark.py execute --sealed data/handwriting-private/amr-sealed --out artifacts/handwriting-private/amr-real
   python backend/evaluation/public_amr_benchmark.py replay --sealed data/handwriting-private/amr-sealed --run artifacts/handwriting-private/amr-real
   ```
7. If local GLM/Qwen are missing, **do not download/retag models without permission**. You may use `--arms tesseract` for a clearly labeled **partial baseline**, and report that two other arms remain unmeasured; this does not complete the three-arm study.

## RxHandBD supplemental workflow

1. Obtain `RxHandBD-ML.zip` from official version 3 of https://data.mendeley.com/datasets/dsb5r6vskg/3, and record the archive SHA locally. Extract into `data/handwriting-private/rxhandbd-v3`, not public git.
2. Locate `test_labels.csv` and corresponding 1,115 test images. Resolve ZIP-specific column/folder naming via CLI options, never by silently joining the wrong images or substituting train crops:
   ```bash
   python backend/evaluation/public_rxhandbd_benchmark.py scaffold --dataset-root data/handwriting-private/rxhandbd-v3 --study data/handwriting-private/rx-intake --count 100
   ```
   If ambiguous filename collisions occur, pass `--images-dir` for **test images only**. If the labels use nonstandard columns, specify `--image-column` and `--text-column` after verifying the actual headings.
3. Review all selected image/label pairs offline for privacy. Do not fabricate reviewer identity or claim independent adjudication. On actual approval, seal and timestamp independently, then:
   ```bash
   python backend/evaluation/public_rxhandbd_benchmark.py seal --study data/handwriting-private/rx-intake --out data/handwriting-private/rx-sealed
   shasum -a 256 data/handwriting-private/rx-sealed/study_seal.json
   python backend/evaluation/public_rxhandbd_benchmark.py verify --sealed data/handwriting-private/rx-sealed
   python backend/evaluation/public_rxhandbd_benchmark.py execute --sealed data/handwriting-private/rx-sealed --out artifacts/handwriting-private/rx-real
   python backend/evaluation/public_rxhandbd_benchmark.py replay --sealed data/handwriting-private/rx-sealed --run artifacts/handwriting-private/rx-real
   ```

## Reporting gate

- Run `python -m pytest backend/tests/test_handwriting_study.py backend/tests/test_public_amr_benchmark.py backend/tests/test_public_rxhandbd_benchmark.py -q` locally.
- Check that source freeze, independent replay, exact model tags and digests, complete three-arm completion receipts and all original annotation/source hashes pass. Keep originals/gold and predictions in ignored private paths; **never `git add` these artifacts**.
- PR update should contain only publisher name/version/license, record/pilot/excluded numbers, source/replay *opaque checksums* when safe, exact model identities, per-arm aggregated CER/WER/critical-token recall and latency, test scope and explicit limitations. No scans, raw text or identifiable snippets.
- State **publisher-provided references, not dual-blind human transcription**, **real publisher-described handwriting, not necessarily real patient records**, **not clinical validation**, and **not full medication/vital field F1** (structured gold unavailable). AMR document and Rx word results must be separate.
- Ask Codex for an exact-head review if any changes are required. Do not merge/deploy without approved evidence and user direction. If blocked, return the concrete failed command/condition and whatever independent gates passed, without inventing accuracy.
