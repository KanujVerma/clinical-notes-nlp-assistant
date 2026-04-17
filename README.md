# Clinical Notes NLP Assistant

A full-stack web app that extracts structured data from unstructured clinical notes, presents it in a keyboard-driven reviewer UI, and tracks correction rates and evaluation metrics over time.

> **All data is entirely synthetic.** No real patient information is used anywhere in this project.

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

## What it does

A clinical note comes in as pasted text, a `.txt` file, a text-based PDF, a scanned printed document, or a typed image. The pipeline breaks it into sections and extracts:

- **Vitals** — BP, HR, temperature, RR, SpO2, weight, with units preserved
- **Medications** — name, dose, route, frequency, duration, PRN qualifier
- **Instructions** — discharge instructions, follow-up plan, return precautions
- **Metadata** — patient name, date of service, provider

The extracted fields go into a reviewer UI where each one can be accepted, edited, or removed. Corrections are saved back to the database and surface in a Metrics page alongside F1 scores from an offline evaluation run.

---

## Demo flow

1. Paste a note or upload a file, or click **Seed demo data** to load a set of synthetic notes
2. Open the Queue — pending notes waiting for review are listed there
3. Click a note to open it in the Review page
4. Accept, edit, or remove fields using the keyboard or mouse
5. Save — the UI auto-advances to the next pending note
6. Check the Metrics page to see correction rates by category and field

---

## Architecture

```
[Input]
  paste text / .txt / .pdf (text layer) / .pdf (OCR) / image (.png, .jpg, .tiff)
        │
        ▼
[Flask API — port 5000]
        │
        ▼
[NLP Pipeline]
    section detection → vitals → medications → instructions → metadata
        │
        ▼
[SQLite via SQLAlchemy]
  notes → extractions → validations
        ▲
        │
[React UI — port 5173 (dev) / 5000 (Docker)]
  Upload → Queue → Review → History → Metrics
```

The pipeline is entirely rule-based — no LLM calls, no API keys, and deterministic output for the same input note. Section detection uses medSpaCy's Sectionizer plus header regex patterns. Vitals use unit-preserving regex. The medication extractor combines structured line parsing, prose extraction from Plan/A&P sections, and a medSpaCy TargetMatcher with ConText for negation handling. Instructions use a three-tier approach: dedicated sections first, then sub-classification of Plan/HPI text, then a keyword fallback.

The deterministic design makes evaluation honest — the F1 scores in the Metrics page reflect real system behavior.

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

The reviewer UI is keyboard-driven. Hover over any field card to activate it, then:

| Key | Action |
|-----|--------|
| `A` | Accept |
| `E` | Edit |
| `R` | Remove |
| `Tab` / `Shift+Tab` | Cycle through fields |
| `Esc` | Deactivate |
| `⌘S` / `Ctrl+S` | Save |

A progress bar in the top bar tracks how many fields have been reviewed. After saving, the app auto-advances to the next pending note. Navigating away with unsaved changes triggers a confirmation prompt.

Medication cards group dose, route, frequency, and duration under the drug name with a visual indent so it is clear which sig belongs to which drug. Medications captured from prose with no sig information get a **mention only** label — the reviewer decides whether to keep or remove them.

Re-opening a previously reviewed note reconstructs the prior field statuses from the diff of extracted vs. validated data, shows a banner, and carries the review timer forward.

---

## Evaluation

The Metrics page shows F1 scores from an offline evaluation run against 20 hand-labeled synthetic notes, plus reviewer correction rates by category and field from all validated notes in the database.

To generate the evaluation results:

```bash
source .venv/bin/activate
python scripts/run_evaluation.py
```

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

Vitals precision is high because the regex patterns are tight. Medication recall is lower — the eval set includes drugs outside the curated vocabulary, some medications appear only as prose mentions without the action-verb patterns the extractor looks for, and a handful of note formats fall outside the supported section header patterns. These are the clearest paths to improvement.

---

## Limitations

- **Medication extraction is a prototype.** Structured medication lines with dose/sig usually parse correctly even for drugs outside the curated vocabulary. Prose-only mentions in HPI narrative are more dependent on the curated vocabulary and action-verb sentence patterns. No RxNorm, no brand/generic normalization, no dose unit conversion.
- **Handwritten notes are not supported.** OCR works for clean printed and typed scans. Handwriting degrades Tesseract output significantly and is out of scope for this version.
- **OCR quality depends on scan quality.** Poor contrast, unusual fonts, or heavy artifacts may produce garbled text the extractor can't recover from.
- **Coverage is bounded by the implemented rules.** Unusual phrasings, heavy abbreviations, or note formats outside the supported section/header patterns will reduce extraction quality.
- **No authentication.** Single-user local tool.
- **No real PHI.** Do not use with real patient data.

---

## Potential next steps

- RxNorm integration for drug normalization and broader vocabulary coverage
- scispaCy (`en_core_sci_sm`) for better clinical tokenization
- LLM fallback for fields the rule-based extractors miss consistently
- FHIR-structured output
- Active learning: surface low-confidence extractions and use reviewer corrections to extend the rules

---

## Development

**Backend tests** (118 unit + integration, includes a four-note regression pack):
```bash
source .venv/bin/activate
pytest backend/tests/ -v
```

**End-to-end smoke tests** (Playwright, requires both servers running):
```bash
cd frontend
npx playwright test
```

---

## Synthetic data disclaimer

All clinical notes in this project (`data/dev/`, `data/eval/`, `data/showcase/`) are entirely synthetic, generated programmatically or hand-authored for demonstration purposes. They contain no real patient information, no real provider names, and no real medical records. Any resemblance to real individuals is coincidental.
