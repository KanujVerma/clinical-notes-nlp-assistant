# Clinical Notes NLP Assistant

Extracts structured information from unstructured clinical notes, presents it in a reviewer UI for correction, persists everything in SQLite, and evaluates pipeline quality against a labeled synthetic test set.

> **All data is entirely synthetic.** No real patient information is used anywhere in this project.

---

## What it does

A clinical note comes in as pasted text, a `.txt` file, a text-based PDF, a scanned printed document, or a typed image file. The NLP pipeline breaks it into sections, then runs parallel extractors over those sections to produce structured output:

- **Vitals** — BP, HR, temperature, RR, SpO2, weight — with units preserved
- **Medications** — name, dose, route, frequency, duration, PRN qualifier; combines structured line parsing, prose extraction from Plan/A&P sections, and a curated vocabulary with medSpaCy fallback. Still a prototype, not a production-grade medication normalizer.
- **Instructions** — discharge instructions, follow-up plan, return precautions
- **Metadata** — patient name, date of service, provider

That output goes into a review UI where a reviewer can accept, edit, or remove individual fields. Corrections are stored and surfaced in a metrics dashboard alongside F1 scores from an offline evaluation run.

---

## Demo flow

1. Upload or paste a synthetic clinical note
2. Review extracted vitals, medications, instructions, and metadata
3. Accept, edit, or remove fields using the keyboard-driven review UI
4. Save and auto-advance to the next pending note
5. Inspect correction rates and evaluation results in the Metrics page

---

## Architecture

```
[Input]
  paste text / .txt / .pdf (text layer) / .pdf (OCR) / image (.png, .jpg, .tiff)
        │
        ▼
[Flask API — port 5000]
  POST /api/notes    (text)
  POST /api/upload   (file)
        │
        ▼
[NLP Pipeline]
  preprocess
    → section detection   (medSpaCy Sectionizer + header regex)
    → vitals extractor    (regex, unit-preserving)
    → medication extractor (structured line parsing → prose A/P → medSpaCy TargetMatcher + ConText)
    → instruction extractor (dedicated sections → sub-classification → keyword fallback)
    → metadata extractor  (header patterns)
        │
        ▼
[SQLite via SQLAlchemy]
  notes  →  extractions  →  validations
        ▲
        │
[React UI — port 5173 (dev) / 5000 (Docker)]
  Upload → Queue → Review → History → Metrics
```

The pipeline is entirely rule-based — no LLM calls, no API keys, and deterministic output for the same input note.

---

## Why rule-based

This was a deliberate choice rather than a limitation. Rule-based extraction is deterministic, which makes evaluation honest: the F1 scores in the Metrics page reflect real system behavior, not sampling variance. ConText handles negation (so "no chest pain" doesn't produce a finding), and the sentence-local medication scanner prevents cross-sentence dose binding without needing a dependency parser.

The trade-off is that coverage is bounded by the implemented rules and patterns rather than learned from data. The medication extractor is the clearest example of this — see Limitations below.

---

## Setup

Requires Python 3.11, Node 18+, and Tesseract (for OCR on images/scanned PDFs).

```bash
# macOS
brew install tesseract poppler

# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr poppler-utils
```

```bash
git clone <repo>
cd clinical-notes-nlp-assistant

# Python environment
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

## Running locally

**Terminal 1 — backend:**
```bash
source .venv/bin/activate
cd backend
python app.py
# Flask on http://localhost:5000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm run dev
# Vite on http://localhost:5173
```

Open `http://localhost:5173`.

**Seed demo data (optional):**
```bash
source .venv/bin/activate
python scripts/seed_demo_data.py
```

---

## Docker

```bash
docker compose up
# App at http://localhost:5000
```

---

## Review workflow

The review UI is designed to be keyboard-driven:

| Key | Action |
|-----|--------|
| `A` | Accept active field |
| `E` | Open edit on active field |
| `R` | Remove active field |
| `Tab` / `Shift+Tab` | Cycle through fields |
| `Esc` | Deactivate |
| `⌘S` / `Ctrl+S` | Save |

The top bar shows a progress bar ("X of Y fields reviewed") and a timer. After saving, the UI auto-advances to the next pending note. If you re-open a previously reviewed note, it reconstructs the prior field statuses from the diff of extracted vs. validated JSON, and carries the timer forward.

Medication cards group dose/route/frequency/duration under the drug name with a visual indent. Medications extracted with no sig (pure name mentions from HPI prose) get a "mention only" label so the reviewer knows to confirm or discard them.

---

## Evaluation

```bash
source .venv/bin/activate
python scripts/run_evaluation.py
```

Evaluates the pipeline against 20 hand-labeled synthetic notes in `data/eval/labels/`. Results are written to `backend/evaluation/results.json`, which the Metrics page reads.

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

Vitals precision is high — the regex patterns are tight and unit-preserving. Medication recall is lower for a few reasons: the eval set includes drugs outside the curated vocabulary, some medications only appear as prose mentions without the action-verb patterns the extractor looks for, and a handful of note formats fall outside the implemented section/header patterns. Expanding vocabulary coverage and broadening the prose extraction rules are the clearest paths to improvement.

The Metrics page also shows reviewer correction rates by category and by field, computed from all validated notes in the database. This tells you where the pipeline is least reliable in practice.

---

## Limitations

- **Medication extraction is a prototype.** Structured medication lines (with dose/sig) usually parse correctly even for drugs outside the curated vocabulary. Prose-only mentions — drugs referenced in HPI narrative without a standard sig format — are more dependent on the curated vocabulary and the action-verb sentence patterns. No RxNorm, no brand/generic normalization, no dose unit conversion.
- **Handwritten notes are not supported.** OCR is implemented for clean printed documents and typed scans. Handwriting degrades Tesseract output significantly and is out of scope for this version.
- **OCR quality depends on image quality.** Clean typed scans work well. Degraded images, unusual fonts, or poor contrast may produce garbled text the extractor can't recover from.
- **Coverage is bounded by the implemented rules.** Unusual phrasings, heavy abbreviations, or note formats outside the supported section/header patterns will reduce extraction quality.
- **No authentication.** Single-user local tool.
- **No real PHI.** Do not use with real patient data.
- **spaCy model: `en_core_web_sm`.** A general-purpose model. The scispaCy `en_core_sci_sm` model (set `SPACY_MODEL=en_core_sci_sm` in config) would improve clinical tokenization but isn't required.

---

## Tests

118 unit and integration tests covering each extractor independently and end-to-end pipeline behavior across four realistic note types (discharge summary, SOAP note, follow-up note, headerless text):

```bash
source .venv/bin/activate
pytest backend/tests/ -v
```

The four full-note fixtures in `test_pipeline.py` act as a regression pack. They cover structured medication sections, prose extraction from A&P, sentence-local dose binding, follow-up disambiguation from HPI narrative, and unit preservation in vitals.

An 11-test Playwright smoke suite covers the end-to-end browser flow:

```bash
cd frontend
npx playwright test
```

---

## Screenshots

**Upload / Queue**

*[screenshot]*

**Review workflow**

*[screenshot]*

**History**

*[screenshot]*

**Metrics**

*[screenshot]*

---

## Potential next steps

- RxNorm integration for drug normalization and vocabulary expansion
- scispaCy (`en_core_sci_sm`) for better clinical tokenization
- LLM fallback for fields the rule-based extractors miss consistently
- FHIR-structured output
- Active learning loop: surface low-confidence extractions for review and use corrections to retrain or extend the rules

---

## Synthetic data disclaimer

All clinical notes in this project (`data/dev/`, `data/eval/`, `data/showcase/`) are entirely synthetic, generated programmatically or hand-authored for demonstration purposes. They contain no real patient information, no real provider names, and no real medical records. Any resemblance to real individuals is coincidental.
