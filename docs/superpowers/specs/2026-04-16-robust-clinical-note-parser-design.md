# Robust Clinical Note Parser — Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Approach:** A — Targeted regex hardening

---

## Problem

The current pipeline was designed around a single clean note template. It fails on realistic clinical note variation:

- Medication lines are missed when the drug name is absent from the medSpaCy vocabulary (e.g., Metformin, Albuterol not extracted from a valid discharge summary).
- Dose units like "puffs", "tabs", "capsules" are not recognized.
- Many common section header aliases are not matched (e.g., "Discharge Medications", "Hospital Course", "Impression", "A/P").
- Metadata fields only match one canonical phrasing ("Patient:", "Date of Service:").
- Follow-up and return precaution content embedded in prose is not reliably captured.

---

## Scope

Changes are confined to the backend extractor layer:

- `backend/extractors/sections.py`
- `backend/extractors/vitals.py`
- `backend/extractors/medications.py`
- `backend/extractors/metadata.py`
- `backend/extractors/instructions.py`

No schema changes, no new dependencies, no frontend changes. The pipeline interface (`run_pipeline`) is unchanged. Existing tests continue to pass; new tests are added for each extractor.

---

## Design

### 1. Section Detection (`sections.py`)

Expand `_SECTION_PATTERNS` with all realistic header aliases. Each entry maps one or more regex alternatives to a canonical category name.

| Canonical category | New aliases added |
|---|---|
| `medications` | Discharge Medications, Home Medications, Current Medications, Meds |
| `vitals` | Vital Signs, Objective, Exam, Physical Exam, PE |
| `metadata` | (handled at field level, not section level) |
| `hpi` | Interval History, Hospital Course |
| `chief_complaint` | CC, Reason for Visit |
| `assessment_plan` | Impression, Diagnoses, Problem List, A/P, Assessment and Plan |
| `discharge_instructions` | Plan (when no other plan section found), Discharge Instructions |
| `follow_up` | Follow-up, Follow Up |
| `return_precautions` | Return Precautions, When to Return |

The anchor pattern (`^[ \t]*<header>[ \t]*:?[ \t]*$`) is retained — it requires section headers to appear on their own line, which is consistent with all three note types (discharge summary, SOAP/APSO, H&P). This prevents false section matches inside prose paragraphs.

---

### 2. Vitals (`vitals.py`)

Extend each pattern to cover real-world formatting variants. Units are captured and included in the value string where present.

| Field | New variants |
|---|---|
| `blood_pressure` | `BP 142/88`, `BP: 142/88 mmHg`, `Blood Pressure 142/88` — include `mmHg` in value if present |
| `heart_rate` | `HR 78`, `Pulse 78`, `Pulse: 78 bpm` |
| `temperature` | `T 98.6`, `T: 98.6 F`, `Temp 98.6 F` — include unit (F/C) in value |
| `respiratory_rate` | `RR 18`, `Resp 18`, `Resp Rate 18`, `breaths/min` context |
| `oxygen_saturation` | `SpO2 96%`, `O2 sat 96%`, `O2 Sat 96% on room air`, `Sat 96% RA` — include `%` in value |
| `weight` | `Wt 185 lb`, `Weight 185 lbs`, `Wt: 185 kg` — include unit in value |

---

### 3. Medications (`medications.py`)

This is the most significant change. The current approach (medSpaCy vocabulary matching → window scan for dose/route/freq) fails when drug names are absent from the vocabulary.

**New strategy: structured line parser first, medSpaCy fallback second.**

#### 3a. Structured line parser

When a medications section is detected, parse it line by line. For each non-empty line:

1. Strip leading bullets, numbers, hyphens, and punctuation.
2. Attempt to match the line against the pattern:  
   `<name> <dose> [<route>] [<frequency>] [<qualifier>]`  
   where `<name>` is 1–4 non-numeric words, `<dose>` is a number followed by a unit.
3. If `<dose>` is present, treat the line as a medication candidate.
4. If `<dose>` is absent but `<route>` or `<frequency>` is unambiguously present (e.g., "PO", "IV", "BID"), treat as a candidate.
5. A line that matches none of the above is skipped (avoids capturing section headers, diagnoses, free-text lines).

**Dose units extended:** mg, mcg, g, ml, units, mEq, **puffs, tabs, tablets, capsules, cap, patch, spray, drops**

**Route abbreviations extended:** PO, IV, IM, SQ, subq, subcutaneous, inhaled, inhalation, topical, SL, PR, transdermal, **intranasal, ophthalmic, otic, rectal, oral**

**Frequency extended:** once daily, twice daily, BID, TID, QID, QHS, QAM, daily, qd, **q4h, q6h, q8h, q12h, q24h,** PRN, as needed, at bedtime, bedtime, weekly, monthly

**Inhaler-style dosing:** Pattern `\d+\s+puffs?\s+(?:q\d+h|BID|TID|daily|PRN)` is matched as a valid dose+frequency combination.

**PRN/as-needed:** Captured in `frequency` field if present on the line (e.g., "q6h PRN wheezing" → frequency = "q6h PRN").

#### 3b. medSpaCy fallback

After structured parsing, run medSpaCy on the full note text to catch medication mentions in prose (e.g., in HPI, assessment). De-duplicate against already-found medications by name (case-insensitive). The fallback result is tagged `"source": "medspacy"` while the line parser results are tagged `"source": "section"`.

#### 3c. Guard against over-greedy matching

A line is rejected as a medication candidate if:
- It contains no dose-like token AND no unambiguous route/frequency token
- It is entirely uppercase (likely a section header)
- It matches a known non-medication pattern: date lines, diagnosis lines (containing ICD-like patterns), instruction sentences (containing "return to", "follow up", "avoid", "drink")

---

### 4. Metadata (`metadata.py`)

Extend field-level patterns to cover common header variants.

| Field | Aliases |
|---|---|
| `patient_name` | `Patient:`, `Patient Name:`, `Name:`, `Pt:` |
| `date_of_service` | `Date of Service:`, `DOS:`, `Date Seen:`, `Date:`, `Visit Date:` |
| `provider_name` | `Provider:`, `Attending:`, `Physician:`, `Clinician:`, `Doctor:`, `Dr:` |

Date field: capture the full value string (date formats are not normalized — left as-is for the reviewer to verify).

---

### 5. Instructions (`instructions.py`)

**Section mapping additions:**  
Map `hospital_course` (from the `hpi` section category) and `plan` (from `assessment_plan`) as additional sources for `discharge_instructions` when no dedicated `discharge_instructions` section is found.

**Sentence-level fallback (enhanced):**  
The existing fallback fires on individual sentences. Extend the trigger patterns:

`follow_up` triggers:
- `follow up with`, `follow-up with`, `see your`, `return to (clinic|office|your doctor|primary care)`, `schedule an appointment`, `call your doctor`

`return_precautions` triggers:
- `return to (the ER|emergency|hospital)`, `call (911|your doctor|if)`, `seek (medical|emergency|immediate)`, `go to the ER`, `if you (develop|experience|notice|have|feel)`, `worsening`, `seek care`

`discharge_instructions` triggers (prose):
- `take your`, `rest`, `avoid`, `do not`, `drink plenty`, `use your`, `continue your`, `apply`

**Multi-sentence aggregation:** When a fallback trigger is found, collect that sentence **and** the following 1–2 sentences (up to the next trigger or section boundary) into the value. This handles cases like "Return to ER for: chest pain, shortness of breath, fever." split across lines.

---

## Testing

New tests added in `backend/tests/`:

- `test_sections.py` — extend with discharge summary and SOAP note fixtures, verify all new aliases are recognized
- `test_vitals.py` — test all new format variants for each vital sign
- `test_medications.py` — test structured line parsing (bullets, numbered, inhaler-style, missing route/freq, prose fallback), test over-greedy guard
- `test_metadata.py` — test all new header variants
- `test_instructions.py` — test section-source mapping from Plan/Hospital Course, test multi-sentence fallback aggregation
- `test_pipeline.py` — end-to-end test using the full discharge summary from the design spec (John Smith note); verify all 3 medications are extracted with correct dose/route/freq

---

## Verification Checklist

1. John Smith discharge summary extracts Lisinopril, Metformin, and Albuterol with correct dose/route/freq
2. Albuterol "2 puffs q6h PRN wheezing" → dose = "2 puffs", frequency = "q6h PRN"
3. All vitals from the note extracted with correct values
4. `follow_up` captured from "Follow Up:" section
5. `return_precautions` captured from "Return Precautions:" section
6. `discharge_instructions` captured from "Discharge Instructions:" section
7. Metadata: patient_name = "John Smith", date_of_service = "2024-03-15", provider_name = "Dr. Sarah Chen"
8. A SOAP note with "A/P" section is correctly mapped to `assessment_plan`
9. A note with no section headers still extracts vitals and at least one instruction via fallback
10. All pre-existing tests continue to pass
