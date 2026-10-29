# Clinical Notes NLP Assistant

A **full-stack, synthetic clinical-note extraction and human-review prototype** built with React, TypeScript, Flask, SQLAlchemy, spaCy/medSpaCy, and deterministic rules. It extracts structured fields, lets a reviewer inspect and correct them against the source, and records reviewer activity.

> **Code and deployment are separate.** The validation workbench, synthetic showcase, and 30-image local vision benchmark are merged on `main`. Production Vercel and Render auto-deploys remain disabled. A passing code gate does not establish that the hosted demo runs this revision.

> **Synthetic engineering demo — not for clinical use.** Do not submit real patient information. This is not clinically validated, does not verify patient identity, and is not an EHR or prescribing tool. Session-based workspace separation is not authentication.

**Hosted demo:** [clinical-nlp.vercel.app](https://clinical-nlp.vercel.app/) (availability and deployment version are not guaranteed by this README). For reproducible behavior, run the checked-out revision locally.

## Product walkthrough

1. Paste a synthetic note, load the built-in sample, seed demo notes, or upload TXT, PDF, or a typed image. OCR uses Tesseract for scanned/printed inputs.
2. The deterministic extractor identifies metadata, vitals, medication mentions and instructions, retaining source-linked field information where available.
3. Review each extracted field, accept/edit/remove it, and save. The keyboard-oriented interface supports repeated inspection and correction.
4. Browse the queue and review history. The Metrics view summarizes reviewer corrections and activity within the current browser workspace.
5. Optionally inspect a local-dictionary explanation of a medication or abbreviation. An external AI terminology explanation is a separate, on-demand feature when configured; it is **not** the extraction engine.

| Upload | Review | Metrics |
|:---:|:---:|:---:|
| ![Upload page](docs/screenshots/upload.png) | ![Review page](docs/screenshots/review.png) | ![Metrics page](docs/screenshots/metrics.png) |

Other interface views: [Queue](docs/screenshots/queue.png), [History](docs/screenshots/history.png), and [Terminology explainer](docs/screenshots/explainer.png). Screenshots may describe the recorded UI state rather than the currently deployed build.

## How it works

```text
Synthetic text / TXT / PDF / typed image
         |
         v
Flask upload/paste API
  |-- PyMuPDF text extraction / Tesseract OCR fallback
  |-- text normalization + custom regex section detection
  |-- deterministic vitals, medication, instruction, metadata extraction
  |      (regex and spaCy/medSpaCy matching/context rules)
         |
         v
SQLAlchemy persistence (SQLite local; configurable PostgreSQL)
         |
         v
React + TypeScript reviewer UI
Upload --> Queue --> Review --> History --> Metrics

Optional, separate path:
dictionary explanation --> configured field-level AI explanation
```

The core NLP pipeline is **rule-based**, not an LLM note extractor. It uses a custom regex section detector, rather than spaCy's Sectionizer. The optional AI explainer is not required to process or review notes and is disabled when no API key is set.

### Engineering tradeoffs

- **Inspectability over black-box output:** structured fields can be compared with the original synthetic source, but a matching span alone does not prove a correct medication interpretation.
- **Human review is explicit:** a correction represents a user's action. A low correction rate does **not** establish high extraction accuracy; unnoticed omissions and reviewer error remain possible.
- **Bounded prototype scope:** the demo deliberately avoids real patient workflows, EHR integration, treatment recommendation, and claims of regulatory or privacy compliance.

## Run locally

Prerequisites: Python 3.11, a compatible Node.js version (Node 20 is a practical default), and Tesseract + Poppler for scanned PDFs/images.

```bash
# macOS OCR dependencies
brew install tesseract poppler

git clone https://github.com/KanujVerma/clinical-notes-nlp-assistant.git
cd clinical-notes-nlp-assistant
git switch main

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

cd frontend
npm ci
cd ..
```

Start the full local workbench (Flask, Vite and **one durable processing worker**) with:

```bash
make dev
# http://127.0.0.1:5173
```

The local AI panel now queues source/extraction-bound jobs and polls the worker. Without a running worker, requests remain queued; Flask itself does **not** run inference. Launch Ollama separately only when testing an installed, free local model. The two vision adapters require an original synthetic PDF/image, and neither their output nor visual-coordinate suggestions can automatically approve review data.

If running services separately, open three terminals:

```bash
.venv/bin/python backend/app.py       # Flask on port 5000
.venv/bin/python backend/worker.py    # one local processing worker
cd frontend && npm run dev            # Vite on port 5173
```

Open <http://localhost:5173>. Vite proxies `/api` to the local Flask backend. Without `DATABASE_URL`, the backend uses a local SQLite database. Seed synthetic notes with the **Seed demo data** button or use **Load sample note**. No API keys are needed.

**Optional AI explainer:** External paid inference is disabled by default. To explicitly enable it locally, set `ENABLE_EXTERNAL_EXPLAINER=true` AND configure `ANTHROPIC_API_KEY`; keep both disabled for offline processing. A pre-existing API key alone cannot enable provider calls. Keep it unset for offline extraction/review testing. Never send actual patient data to this demo or to the optional provider.

**Docker Compose (development):** `docker compose up --build` starts the backend on port **5000** and Vite on **5173**, but the two-service Compose configuration does **not** start the local worker or enable AI inference. Use `make dev` for the complete local workbench.

## Review controls

| Key | Action |
|---|---|
| `A` | Accept focused field |
| `E` | Edit |
| `R` | Remove |
| `Tab` / `Shift+Tab` | Navigate fields |
| `Esc` | Deactivate |
| `⌘S` / `Ctrl+S` | Save |

The reviewer can inspect medications, vitals, instructions, and metadata. Medication mentions without sufficient structured directions require human interpretation rather than assuming they are active treatment instructions.

## Validation Workbench & Verification Architecture

In addition to the baseline pipeline, this repository includes the **Clinical NLP Validation Workbench** (`docs/validation/`), establishing immutable lineage, defensive verification, and statistical evaluation:

- **Immutable Lineage & Append-Only Event Store**: Ingestion hashes source assets into content-addressed storage (SHA-256). Transcription edits create an incremented `NoteRevision` chain. Review events cite parent pointers, lock versions (optimistic concurrency), and idempotency keys.
- **Independent Quality Canaries**: Pure validation rules independently check extracted entities for half-open interval coordinate bounds, exact quote integrity (`A08`), decimal dose formatting risks (`A09`), duplicate medication conflicts (`A02`), missing vital units (`A03`), and contradictory instructions (`A04`).
- **Operational Issues Drawer**: Live slide-out drawer surfacing canaries and critical blockers with explicit reviewer disposition lifecycles.
- **Synthetic Evaluation Lab (`/validation-lab`)**: Deterministic source-occurrence-first medication pairing with a bounded assignment fallback (not the Hungarian algorithm), evaluating annotated medication attributes (`name`, `dose`, `route`, `frequency`, `duration`, `qualifier`) and case-by-case error attribution (TP/FP/FN).
- **Checksummed Export**: Downloadable review ZIPs with structured decisions, source lineage, and a SHA-256 file manifest. Checksums are not clinician signatures or independent proof of correctness.

Comprehensive documentation is available in [`docs/validation/`](docs/validation/):
- [Acceptance Matrix (A01–A48)](docs/validation/acceptance-matrix.md)
- [System Architecture](docs/validation/architecture.md)
- [API Contract](docs/validation/api-contract.md)
- [Requirements & Boundaries](docs/validation/requirements.md)
- [Engineering Demonstration Script](docs/validation/demo-script.md)
- [Contribution Changelog](docs/validation/contribution-changelog.md)
- [30-case Real Vision Benchmark Audit](docs/validation/THIRTY_CASE_BENCHMARK_AUDIT.md)
- [Medication Parser Gold/OCR Replay](docs/validation/MEDICATION_GOLD_REPLAY.md)

## Verification

From the repository root:

```bash
# Backend pytest suite (rerun and record counts for this exact commit)
source .venv/bin/activate
python -m pytest backend/tests/ -q

# Frontend unit tests, linting, and build
cd frontend
npm test
npm run lint
npm run build

# End-to-end browser tests (counts depend on checked-out revision)
# Requires Flask (port 5000) and Vite (port 5173) running:
npx playwright test
```

## Known limitations and operational boundaries

- **Synthetic only:** The system is restricted to synthetic, de-identified clinical scenarios. It is not HIPAA-certified, does not connect to EHRs, does not verify patient identity, and must never be used for real clinical decision-making.
- **Extraction bounds:** Ambiguous clinical phrasing, novel abbreviations, and unformatted narrative text require human verification. The deterministic pipeline flags anomalies via canaries rather than making autonomous clinical decisions.
- **Optional local AI:** On-device GLM-OCR and Qwen3-VL adapters exist. PR #5 records real local inference on 30 hash-pinned generator-derived printed/noisy/photographed-effect synthetic images, **not** handwriting or an independent holdout. Model suggestions remain separate from reviewer-approved state. Vision requests without an original image source fail closed; paid terminology explanation stays opt-in.
- **Real synthetic model benchmark:** Original image/source hashes, saved local predictions, model digests, CER/WER, critical tokens, and strict entity scores are in `artifacts/evaluation/paired_local_17f5737320b78e10.json`. See the [independent source audit](docs/validation/THIRTY_CASE_BENCHMARK_AUDIT.md). The [medication parser replay](docs/validation/MEDICATION_GOLD_REPLAY.md) separately scores the current deterministic extractor against perfect synthetic transcripts and those saved OCR predictions. None of these development scores is a held-out or clinical validation estimate.
- **Evaluation limits:** The historical 20-note synthetic corpus was inspected during development and is not a held-out or clinically adjudicated set. Older saved benchmark artifacts use earlier matching rules and cannot be treated as a comparable strict baseline.
- **Release status:** GitHub Actions verifies synthetic/offline and hosted-mode contracts on each changed PR head. The [acceptance matrix](docs/validation/acceptance-matrix.md) contains historical verification snapshots; production deployment, migrations, EHR integration, and handling actual patient information remain unapproved.

## Project scope and contributions

This repository is an engineering exercise in structured extraction, reviewer UX, deterministic testing, and learning from counterexamples using **synthetic data only**. The original application and any later AI-assisted reliability enhancements should remain distinguishable through commit history and dated implementation evidence. Automated code review is not a substitute for human or clinical review.

See `backend/extractors/`, `backend/evaluation/`, `backend/tests/`, `frontend/src/pages/`, and `frontend/e2e/` for the implementation and test entry points.
