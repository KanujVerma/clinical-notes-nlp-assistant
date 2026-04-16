# Clinical Notes NLP Assistant

A portfolio-quality full-stack web application that extracts structured information from unstructured clinical notes, lets a human reviewer correct the output, persists corrections in SQLite, and reports honest evaluation metrics against a labeled synthetic test set.

> **All data is entirely synthetic.** No real patient information is used anywhere in this project.

---

## Problem Statement

Unstructured clinical notes contain vital clinical information — vitals, medications, follow-up instructions — buried in free text, abbreviations, inconsistent formatting, and prose. Extracting this information reliably is a core challenge in clinical NLP.

This project builds a practical extraction pipeline that:
1. Parses a clinical note into structured fields (vitals, medications, instructions, metadata)
2. Presents the output in a reviewer UI with span highlighting for verification
3. Allows the reviewer to accept, correct, or remove any field
4. Tracks corrections and computes evaluation metrics against ground-truth labels

---

## Architecture Overview

```
[Note Input]
  (paste text / upload .txt / upload .pdf)
        │
        ▼
[Flask API :5000]
  POST /api/notes    POST /api/upload
        │
        ▼
[NLP Pipeline]
  preprocess → sections → [vitals, medications, instructions, metadata] → normalize
  (medSpaCy TargetMatcher + ConText + Sectionizer) + (regex)
        │
        ▼
[SQLite via SQLAlchemy]
  notes ← extractions ← validations
        ▲
        │
[React UI :5173]
  Home → Review (span highlights + field editor) → History → Metrics
```

---

## Why medSpaCy + Regex

**Rule-based extraction for interpretability and deterministic evaluation.**

- **medSpaCy** provides clinical-domain components: `Sectionizer` (section header detection), `ConText` (negation/uncertainty), and `TargetMatcher` (vocabulary-driven entity matching). These map directly to the clinical extraction task.
- **Regex** handles the structured, predictable patterns of vitals (e.g. `BP 120/80`, `HR 72 bpm`) with high precision and no hallucination risk.
- **No LLM dependency**: extraction is deterministic — run the same note twice, get the same output. This makes evaluation meaningful: F1 scores reflect real system behavior.
- **No API cost**: the full pipeline runs locally with no external calls.
- **Honest limitations**: the medication vocabulary is a curated prototype (~50 drugs). This is explicitly documented. Production deployment would require RxNorm integration and a full drug database.

---

## Setup

```bash
git clone <repo>
cd clinical-notes-nlp-assistant

# Backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# Frontend
cd frontend
npm install
cd ..
```

---

## Local Development

**Terminal 1 — Backend:**
```bash
source .venv/bin/activate
cd backend
python app.py
# Flask running on http://localhost:5000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
# Vite running on http://localhost:5173
```

**Seed demo data (optional):**
```bash
source .venv/bin/activate
python scripts/seed_demo_data.py
# Seeded: 60 loaded, 0 already existed.
```

Open `http://localhost:5173` in your browser.

---

## Docker

```bash
docker compose up
```

App runs at `http://localhost:5000` (Flask serves the built React bundle).

To build only:
```bash
docker build -t clinical-notes-nlp .
```

---

## Demo Mode

1. Open the Home page
2. Click **Load sample note** to populate the text area
3. Click **Extract →** — the Review page opens
4. Left pane: raw note text with color-coded span highlights (blue = vitals, green = medications, amber = instructions, purple = metadata)
5. Right pane: editable structured fields. Try editing a field, then clicking **Save corrections**
6. Navigate to **History** — the note appears with status `corrected` and a non-zero correction count
7. Navigate to **Metrics** to see F1 scores (requires running the evaluation script first)

Alternatively, click **Seed demo data** on the Home page to load 60 synthetic notes, then browse History.

---

## Evaluation

```bash
source .venv/bin/activate
python scripts/run_evaluation.py
```

This evaluates the pipeline against 20 hand-written synthetic notes with ground-truth labels in `data/eval/labels/`. It prints a summary table and writes `backend/evaluation/results.json`, which the Metrics page reads.

Sample output:
```
============================================================
  Clinical NLP Evaluation — pipeline v0.1.0
============================================================
  Category              Precision     Recall         F1
  vitals                    1.000      0.652      0.790
  medications               0.238      0.222      0.230
  instructions              0.696      0.327      0.444
  metadata                  0.897      0.531      0.667
  OVERALL                   0.754      0.494      0.597
============================================================
  Notes evaluated: 20
```

Vitals precision is high (exact pattern match). Medication recall is lower because the vocabulary covers ~50 prototype drugs — many eval notes include drugs outside this set. This is expected and documented.

---

## Limitations

- **Medication vocabulary is a prototype.** ~50 common outpatient drugs. No RxNorm, no brand/generic resolution, no dose unit conversion. Many real-world medications will not be extracted.
- **No OCR.** PDF support uses PyMuPDF text layer extraction only. Scanned PDFs are not supported.
- **No LLM.** All extraction is rule-based. Ambiguous phrasings may fail.
- **No authentication.** Single-user local tool.
- **No real PHI.** All notes are synthetic. Do not use with real patient data.
- **spaCy model: en_core_web_sm.** A general-purpose model. The scispaCy `en_core_sci_sm` model (set `SPACY_MODEL=en_core_sci_sm`) improves clinical text handling if installed, but is not required.
- **All data is synthetic.** Evaluation metrics reflect performance on deliberately varied synthetic notes, not real clinical data.

---

## Future Improvements

- Upgrade to `en_core_sci_sm` (scispaCy) for better clinical tokenization
- Add RxNorm integration for medication normalization
- Add LLM fallback for ambiguous extractions
- OCR support for scanned PDFs (Tesseract)
- FHIR output format
- Active learning loop: use reviewer corrections to improve extraction over time
- Multi-user review with authentication

---

## Screenshots

**Home page**
```
[Home page screenshot — paste textarea, drag-drop zone, Extract button]
```

**Review page**
```
[Review page screenshot — left: note with colored span highlights; right: editable fields]
```

**History page**
```
[History page screenshot — table of notes with status badges and correction counts]
```

**Metrics page**
```
[Metrics page screenshot — precision/recall/F1 cards and per-category bar chart]
```

---

## Synthetic Data Disclaimer

All clinical notes in this project (`data/dev/`, `data/eval/`, `data/showcase/`) are **entirely synthetic** and were generated programmatically or hand-authored for demonstration purposes. They contain no real patient information, no real provider names, and no real medical records. Any resemblance to real individuals is coincidental.

---

## How to Demo in an Interview

**90-second walkthrough:**

- **(0:00)** "This is the Clinical Notes NLP Assistant. The Home page lets you paste a note or upload a .txt or .pdf file. All data is synthetic — you can see the banner."
- **(0:15)** Click **Load sample note**, then **Extract →**. "The note goes through a Flask API to the NLP pipeline."
- **(0:25)** "Here's the Review page. The left pane shows the original note text with color-coded highlights — blue for vitals, green for medications, amber for instructions. The right pane shows the structured output."
- **(0:45)** Click **edit** on a vital field, change the value, click **save**. Then click **Save corrections**.
- **(0:55)** Navigate to **History**. "You can see the note was marked 'corrected' with the correction count."
- **(1:05)** Navigate to **Metrics**. "These are the F1 scores against a labeled eval set. Vitals are high-precision — the regex is tight. Medication recall is lower because I'm using a prototype vocabulary of ~50 drugs, which I'm transparent about in the README."
- **(1:20)** "The pipeline uses medSpaCy for section detection and negation handling — ConText drops negated medication mentions — plus regex patterns for vitals. Completely rule-based, no LLM dependency, deterministic and evaluatable."
