# Clinical Notes NLP Assistant — Design Spec

**Date:** 2026-04-15
**Status:** Approved

---

## Context

A portfolio-quality full-stack web app that extracts structured information from unstructured clinical notes, lets a reviewer correct the output, persists the corrections, and reports honest evaluation metrics against a labeled synthetic test set.

The goal is a project that supports truthful portfolio claims:
- Built a clinical NLP pipeline using medSpaCy + spaCy + regex
- Built a Flask API and React reviewer UI
- Implemented a human-in-the-loop validation workflow
- Parsed text-based PDFs with PyMuPDF
- Persisted outputs + corrections in SQLite
- Evaluated extraction performance on a labeled synthetic eval set

Constraints: local-first, no LLM, no auth, no OCR, no real PHI, no credentialed datasets (no MIMIC). Must run on first clone with a single command.

---

## Architecture

Monorepo, two processes in dev (Flask :5000 + Vite :5173 with proxy), one container in prod (Flask serves the built React bundle from `backend/static/`).

```
clinical-notes-nlp-assistant/
├── backend/
│   ├── app.py                    # Flask app factory, CORS, blueprint registration
│   ├── config.py                 # SPACY_MODEL flag (web_sm | sci_sm), paths, PIPELINE_VERSION
│   ├── routes/                   # extract, upload, validate, history, metrics, seed
│   ├── extractors/
│   │   ├── pipeline.py           # Orchestrator; stamps pipeline_version on outputs
│   │   ├── preprocess.py         # Whitespace collapse, line rejoining, header normalization
│   │   ├── sections.py           # medSpaCy Sectionizer wrapper
│   │   ├── vitals.py             # Regex + unit normalization
│   │   ├── medications.py        # medSpaCy TargetMatcher + regex dose/route/frequency; ConText for negation
│   │   ├── instructions.py       # Section-scoped PRIMARY + sentence/keyword FALLBACK
│   │   ├── metadata.py           # Optional patient/date/provider
│   │   ├── normalize.py          # Canonical JSON, span preservation, confidence
│   │   └── patterns/             # Regex patterns + TargetMatcher rule files
│   ├── models/                   # SQLAlchemy: Note, Extraction, Validation
│   ├── evaluation/
│   │   ├── metrics.py            # Precision / recall / F1 / exact-match
│   │   ├── compare.py            # Prediction ↔ ground-truth aligner
│   │   └── report.py             # JSON + pretty summary
│   ├── utils/                    # pdf.py (PyMuPDF), io.py, db.py
│   └── tests/                    # pytest: extractors + API
├── frontend/                     # Vite + React + TypeScript + Tailwind
│   ├── src/
│   │   ├── pages/                # Home, Review, History, Metrics
│   │   ├── components/           # NoteViewer (span highlight), FieldEditor, StatusBadge
│   │   ├── api/                  # fetch wrappers
│   │   └── types.ts              # Mirrors backend schema
├── data/
│   ├── dev/notes/*.txt           # 50 programmatically generated
│   ├── eval/notes/*.txt          # 20 hand-written
│   ├── eval/labels/*.json        # 20 ground-truth label files
│   └── showcase/notes/*.txt      # 10 polished for screenshots/demo
├── scripts/
│   ├── generate_dev_notes.py     # Template-based generator (dev notes only)
│   ├── seed_demo_data.py         # Loads dev + showcase notes (60) → extract → persist (eval set held out)
│   └── run_evaluation.py         # CLI: runs eval, writes JSON, prints summary
├── Dockerfile                    # Multi-stage: node build → python runtime
├── docker-compose.yml            # Dev convenience
├── requirements.txt
└── README.md
```

---

## Extraction Pipeline

Orchestrator sequence: `preprocess → sections → [vitals, medications, instructions, metadata] → normalize`.

Every extracted field is emitted as:

```json
{
  "value": "<normalized value>",
  "span": [start, end],
  "source": "regex" | "medspacy" | "section" | "fallback",
  "confidence": 0.0–1.0
}
```

`span` values are **character offsets into `raw_text`** as stored in the DB (pre-preprocessing). `preprocess.py` must either produce character-aligned output (same length as raw) or map preprocessed offsets back to raw offsets before returning. The NoteViewer highlights `raw_text` using these offsets directly.

Top-level output is stamped with `pipeline_version` (string constant in `config.py`, e.g. `"0.1.0"`).

**Vitals** — regex-driven, unit-aware:
- BP: `BP?\s*:?\s*(\d{2,3})/(\d{2,3})`
- HR: `(HR|pulse|heart\s*rate)\s*:?\s*(\d{2,3})`
- Temp, RR, SpO2, weight: analogous patterns
- Confidence: `1.0` for exact match, `0.7` for fuzzy fallback

**Medications** — medSpaCy `TargetMatcher` with a **curated prototype vocabulary** (~50 common outpatient meds: lisinopril, metformin, atorvastatin, albuterol, amoxicillin, etc.). Around each match, regex sweeps for dose (`\d+\s*(mg|mcg|g|ml|units?)`), route (`PO|IV|IM|SQ|subq|inhaled|topical`), frequency (`BID|TID|QID|QHS|daily|q\d+h|PRN|once daily`). medSpaCy `ConText` drops negated mentions. **Explicitly framed as a prototype vocabulary in the README — not a production drug-normalization system.** No RxNorm, no brand/generic resolution, no dose unit conversion.

**Instructions** — two-path strategy. Output shape is a dict keyed by category:

```json
{
  "discharge_instructions": {"value": "...", "source": "section", "confidence": 0.9, "span": [...]},
  "follow_up":              {"value": "...", "source": "fallback", "confidence": 0.6, "span": [...]},
  "return_precautions":     {"value": "...", "source": "section", "confidence": 0.9, "span": [...]}
}
```

1. **Primary: section-scoped.** Sectionizer labels sections `discharge_instructions`, `follow_up`, `return_precautions` → extract span content. `source: "section"`, `confidence: 0.9`.
2. **Fallback: sentence/keyword.** When headers are missing or unrecognized, sentence-split and match triggers (`follow up`, `return if`, `call if`, `come back`, `ER if`) to classify each sentence into the closest category. `source: "fallback"`, `confidence: 0.6`.

Primary results take precedence; fallback fills unpopulated categories only.

**Metadata** — light regex: `Patient:`, `DOS:`/`Date of Service:`, `Provider:`/`Attending:`. Only populated if clearly present.

---

## Data Model (SQLite via SQLAlchemy)

```
notes
  id                INTEGER PK
  filename          TEXT NULL
  raw_text          TEXT NOT NULL
  source            TEXT CHECK(source IN ('paste','txt','pdf','demo'))
  created_at        TIMESTAMP

extractions
  id                INTEGER PK
  note_id           INTEGER FK → notes
  extracted_json    TEXT NOT NULL
  pipeline_version  TEXT NOT NULL         -- e.g. '0.1.0'
  extracted_at      TIMESTAMP

validations
  id                INTEGER PK
  note_id           INTEGER FK → notes
  validated_json    TEXT NOT NULL
  status            TEXT CHECK(status IN ('pending','accepted','corrected'))
  review_duration_ms INTEGER NULL
  correction_count  INTEGER NOT NULL       -- computed vs latest extraction on POST /validate
  validated_at      TIMESTAMP
```

One note → one current extraction → optional validation.

`correction_count` is computed server-side on `POST /validate` by counting the number of leaf-level field values in `validated_json` that differ (by trimmed string comparison) from the corresponding field in `extracted_json`. Fields added in `validated_json` that were absent in `extracted_json` count as +1 each; fields removed count as +1 each.

---

## API (Flask blueprints)

| Endpoint | Behavior |
|---|---|
| `POST /extract` | Body `{text}` → pipeline → returns JSON + spans. **No DB write.** Ephemeral dry-run; used only for preview/testing. |
| `POST /notes` | Body `{text, source:"paste"}` → persists note, runs pipeline, persists extraction → returns `{note_id, extracted_json}`. This is the correct endpoint for pasted text in the Home → Review flow. |
| `POST /upload` | Multipart `.txt`/`.pdf` → PyMuPDF text extraction for PDFs (raises `400 EMPTY_PDF_TEXT` if extracted text < 50 chars) → pipeline → persist note + extraction → `{note_id, extracted_json}`. |
| `POST /validate` | Body `{note_id, validated_json, status, review_duration_ms}` → persists validation, computes `correction_count`. |
| `GET /history` | Paginated list of notes with latest validation status. |
| `GET /history/<id>` | Full note + extraction + validation. |
| `GET /metrics` | Reads `evaluation/results.json` + aggregates DB correction stats. Returns `{eval: null, db_stats: {...}}` if `results.json` is absent. |
| `POST /seed-demo` | Idempotent: loads dev + showcase notes (60 total), extracts, persists. Calls same shared function as `scripts/seed_demo_data.py`. |

All errors: `{error: string, code: string}` with appropriate HTTP status.

### Frontend navigation contract

`POST /notes` and `POST /upload` both return `{note_id, extracted_json}`. The frontend passes this payload via React Router `location.state` to the Review page. The Review page reads from `location.state` on first render; if absent (direct URL access or refresh), it falls back to `GET /history/<id>`.

### Flask SPA route

`app.py` includes a catch-all route (`@app.route("/", defaults={"path": ""})`) that serves `backend/static/index.html` for all non-API paths, enabling client-side routing.

---

## Frontend (4 pages)

Vite + React + TypeScript + Tailwind. Slate/white/accent-blue palette. "Reviewer" wording throughout.

1. **Home** — Textarea paste + drag-drop upload (`.txt`/`.pdf`) + "Load sample note" + "Seed demo data" button. Submit → Review.
2. **Review** *(merged Results + Review)* — Two-pane:
   - Left: raw note text with `<mark>` highlights, color-coded by category. Hover shows source + confidence.
   - Right: editable structured fields by category. Per-field Accept / Correct / Remove toggles. Footer: elapsed timer (starts on page load, feeds `review_duration_ms`) + "Save as validated" CTA → `POST /validate`.
   - Works for fresh extractions (paste path) and re-opened history notes.
3. **History** — Table: filename / created_at / status badge / correction count. Row → Review.
4. **Metrics** — Cards (precision / recall / F1) + per-category bar chart (Recharts) + correction rate + avg review time.

---

## Synthetic Data

- **50 dev notes** — `scripts/generate_dev_notes.py` template-based generator, randomized vitals/meds/headers/abbreviations/negations.
- **20 eval notes + labels** — hand-written with deliberate variation the generator doesn't know about (inconsistent headers, abbreviations, negations, meds in prose, missing fields). Labels at `data/eval/labels/<name>.json`.
- **10 showcase notes** — hand-polished, each exercising a different UI state.

`scripts/seed_demo_data.py` and `POST /seed-demo` load **dev + showcase notes only (60 total)**. Eval notes are not seeded into the reviewer DB — they remain a held-out set used only by `run_evaluation.py`. This keeps the portfolio claim honest: eval set is never touched by the reviewer workflow.

Marked synthetic in README and in a Home page banner.

---

## Ground-Truth Label Schema

Each eval note has a corresponding `data/eval/labels/<name>.json` with this structure:

```json
{
  "vitals": {
    "blood_pressure": "140/90",
    "heart_rate": "78",
    "temperature": "98.6",
    "respiratory_rate": "16",
    "oxygen_saturation": "98",
    "weight": "185 lbs"
  },
  "medications": [
    { "name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily" }
  ],
  "instructions": {
    "discharge_instructions": "Take medications as prescribed.",
    "follow_up": "Follow up in 2 weeks.",
    "return_precautions": "Return to ER if chest pain worsens."
  },
  "metadata": {
    "patient_name": "John Doe",
    "date_of_service": "2024-01-15",
    "provider_name": "Dr. Smith"
  }
}
```

Rules:
- Absent vitals fields → key omitted (not null).
- Instructions values are the extracted text verbatim (trimmed).
- Metadata keys are omitted if not clearly present in the note.
- Medication list order does not matter for matching.

---

## Evaluation

`scripts/run_evaluation.py`:
1. Iterates `data/eval/notes/*.txt`
2. Runs pipeline
3. Compares to `data/eval/labels/<name>.json`:
   - Vitals / metadata: field-level exact match (trimmed, lowercased)
   - Instructions: substring match — prediction is correct if the label value appears within the predicted string (trimmed, lowercased), accommodating minor prefix/suffix variation
   - Medications: per-item set match — name required (trimmed, lowercased); dose required (trimmed, lowercased); route + frequency optional (correct if present in both and matching)
4. Computes precision / recall / F1 per category + overall
5. Writes `backend/evaluation/results.json` (schema below)
6. Prints formatted summary table

### `evaluation/results.json` schema

```json
{
  "run_at": "2026-04-15T12:00:00Z",
  "pipeline_version": "0.1.0",
  "overall": { "precision": 0.82, "recall": 0.79, "f1": 0.80 },
  "by_category": {
    "vitals":       { "precision": 0.90, "recall": 0.85, "f1": 0.87 },
    "medications":  { "precision": 0.78, "recall": 0.72, "f1": 0.75 },
    "instructions": { "precision": 0.80, "recall": 0.77, "f1": 0.78 },
    "metadata":     { "precision": 0.88, "recall": 0.83, "f1": 0.85 }
  },
  "per_note": [
    { "note": "eval_001.txt", "vitals_f1": 0.9, "medications_f1": 0.7, "instructions_f1": 0.8 }
  ]
}
```

The Metrics page reads this file; if absent, `GET /metrics` returns `{eval: null}` and the page shows a "Run evaluation script first" prompt.

---

## Testing

- **Backend (pytest):** golden-fixture tests per extractor; Flask test-client API smoke tests; eval pipeline smoke test on 2-note fixture.
- **Frontend (Vitest):** ~3 component tests (FieldEditor, NoteViewer, ReviewPage save flow). Intentionally minimal.

---

## Configuration

`backend/config.py`:
- `SPACY_MODEL = "en_core_web_sm"` — default, installed via `python -m spacy download en_core_web_sm`
- `PIPELINE_VERSION = "0.1.0"` — stamped on every extraction
- `DB_PATH`, `DATA_DIR`, `EVAL_RESULTS_PATH`

**scispaCy upgrade path (optional, documented in README):** Install via `pip install scispacy` plus the wheel URL `https://s3-us-west-2.amazonaws.com/ai2-s3-public/scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz`. Set `SPACY_MODEL = "en_core_sci_sm"`. `config.py` wraps model loading in a `try/except` — if the model is unavailable it logs a warning and falls back to `en_core_web_sm`. Intentionally not in `requirements.txt` to avoid breaking clone-and-run for reviewers without the wheel.

---

## Docker

Multi-stage `Dockerfile`:
1. **Node stage:** `npm ci && npm run build` → `dist/`
2. **Python stage:** `pip install -r requirements.txt`, `spacy download en_core_web_sm`, copy `dist/` → `backend/static/`, `CMD gunicorn`

`docker-compose.yml` adds volume mounts + `FLASK_ENV=development`.

---

## README Sections

Overview · Problem statement · Architecture diagram · Why medSpaCy + regex (rule-based = interpretable, deterministic, no API cost; ConText/Sectionizer are the right tools for this task) · Setup · Local run · Docker run · Demo-mode walkthrough · Evaluation instructions · Limitations (prototype med vocab, no OCR, no LLM, no auth, all data synthetic) · Future improvements (scispacy, RxNorm, LLM fallback, OCR, FHIR) · Screenshot placeholders · Synthetic data disclaimer · "How to demo in an interview" (90-second walkthrough script)

---

## Deferred

No auth, no OCR, no LLM, no FHIR/RxNorm, no real PHI, no deployed hosting, no multi-user review, no active learning loop.

---

## Verification Checklist

1. `docker compose up` → `localhost:5000` loads Home page
2. Paste sample note → Review renders with highlights + structured fields
3. Upload `.txt` and `.pdf` → both succeed; PDF text extracted
4. Edit fields → Save → History row shows `corrected` + non-zero correction count
5. `python scripts/seed_demo_data.py` → 60 dev+showcase notes in History (eval notes are held out)
6. `python scripts/run_evaluation.py` → summary table; Metrics page populated
7. `pytest backend/tests/` → all pass
8. `npm test` in `frontend/` → all pass
9. `docker build .` succeeds on clean checkout

---

## Critical Files

- `backend/extractors/pipeline.py` — orchestrator + pipeline_version stamping
- `backend/extractors/instructions.py` — dual-path (section-scoped + keyword fallback)
- `backend/extractors/medications.py` — TargetMatcher + regex + ConText
- `backend/models/` — SQLAlchemy with pipeline_version on Extraction
- `backend/evaluation/compare.py` + `metrics.py`
- `scripts/generate_dev_notes.py` + `run_evaluation.py`
- `frontend/src/pages/Review.tsx` — merged Results + Review
- `data/eval/notes/*.txt` + `data/eval/labels/*.json` — the honesty-critical artifact
- `Dockerfile` + `README.md`
