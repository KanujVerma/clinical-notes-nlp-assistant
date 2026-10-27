# Clinical Notes NLP Assistant

A **full-stack, synthetic clinical-note extraction and human-review prototype** built with React, TypeScript, Flask, SQLAlchemy, spaCy/medSpaCy, and deterministic rules. It extracts structured fields, lets a reviewer inspect and correct them against the source, and records reviewer activity.

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

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

cd frontend
npm ci
cd ..
```

Open two terminals from the repository root:

```bash
# Terminal 1 — Flask
source .venv/bin/activate
cd backend
python app.py
# http://localhost:5000
```

```bash
# Terminal 2 — Vite
cd frontend
npm run dev
# http://localhost:5173
```

Open <http://localhost:5173>. Vite proxies `/api` to the local Flask backend. Without `DATABASE_URL`, the backend uses a local SQLite database. Seed synthetic notes with the **Seed demo data** button or use **Load sample note**. No API keys are needed.

**Optional AI explainer:** Set `ANTHROPIC_API_KEY` only if deliberately testing that external feature. Keep it unset for offline extraction/review testing. Never send actual patient data to this demo or to the optional provider.

**Docker Compose (development):** `docker compose up --build` starts the backend on port **5000** and the Vite frontend on port **5173**. The Compose configuration is a two-service development environment; it does not serve the whole application solely at port 5000.

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

## Verification

From the repository root:

```bash
source .venv/bin/activate
python -m pytest backend/tests/ -q

cd frontend
npm test
npm run lint
npm run build
# Requires both servers running and a local Chromium setup:
npx playwright test
```

Tests must be rerun for the exact checked-out commit and environment. This README does not use a historical test count as proof that current checks passed.

### Offline evaluation: what the scores mean

The legacy `data/eval/` corpus contains 20 synthetic labeled development notes. `python scripts/run_evaluation.py` writes `backend/evaluation/results.json`. The committed April 17, 2026 result recorded overall F1 **0.6549** under pipeline `0.1.0`, but **that is a historical development result, not a verified current score or clinical accuracy claim**.

The original comparator has important limitations: medication matching uses name/dose without strict route/frequency scoring, duplicate-name instances can collapse, vital normalization strips some units without conversion, and instruction substring matching can accept contradictory extra text. Do not compare the legacy result directly with a stricter evaluator or present it as a reliable whole-record medication metric. Review correction rates on the Metrics page are a separate type of measurement.

## Known limitations and next engineering priorities

- **Review provenance:** this `main` revision stores mutable, note-linked validation records. It does not yet enforce immutable source/extraction/review version binding or optimistic concurrency. A review may become stale after source edits. Do not describe it as tamper-proof or audit-grade.
- **Extraction:** ambiguous medication actions, duplicated occurrences, temporal context, decimal doses, incomplete instructions, and mixed-format sources can be misread or missed.
- **OCR:** the current PDF path chooses OCR fallback using a document-level text threshold, so scanned pages mixed with text pages may not be fully acquired; handwriting is unsupported.
- **Measurement:** the legacy benchmark is a synthetic development diagnostic with permissive comparison rules, not independent, clinically adjudicated validation.
- **Privacy and identity:** no clinical-grade authentication, authorization, identity verification, or real-PHI controls are provided. Browser workspace UUIDs are demo scoping only.
- **Optional AI:** explanations can be incomplete or wrong and do not validate extracted facts.

A separate validation/reliability workstream proposes immutable review events, stricter evaluation, independent consistency checks, page-level acquisition, and actionable issue drilldowns. **Those additions are not part of the `main` revision described here until its code and tests are integrated and verified.** Do not claim them on a portfolio or demo without checking the branch and evidence.

## Project scope and contributions

This repository is an engineering exercise in structured extraction, reviewer UX, deterministic testing, and learning from counterexamples using **synthetic data only**. The original application and any later AI-assisted reliability enhancements should remain distinguishable through commit history and dated implementation evidence. Automated code review is not a substitute for human or clinical review.

See `backend/extractors/`, `backend/evaluation/`, `backend/tests/`, `frontend/src/pages/`, and `frontend/e2e/` for the implementation and test entry points.
