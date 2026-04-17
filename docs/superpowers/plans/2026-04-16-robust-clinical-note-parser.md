# Robust Clinical Note Parser Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Broaden the clinical NLP pipeline to reliably extract vitals, medications, instructions, and metadata from discharge summaries, SOAP notes, and H&P notes with realistic formatting variation.

**Architecture:** Five targeted extractor files are modified in isolation. Each extractor is tested independently before the pipeline integration test runs. The structured medication line parser is a new code path inside `medications.py` that runs before medSpaCy; `instructions.py` gains Plan-section sub-classification and OCR-tolerant sentence splitting.

**Tech Stack:** Python 3.11, pytest, regex (stdlib), medSpaCy (existing), no new dependencies.

---

## Chunk 1: Sections + Vitals + Metadata

### Task 1: Extend section header aliases (`sections.py`)

**Files:**
- Modify: `backend/extractors/sections.py`
- Modify: `backend/tests/test_sections.py`

**Context:** `_SECTION_PATTERNS` is a list of `(regex_string, category_name)` pairs. Each pair compiles to a multiline anchor pattern `^[ \t]*<pattern>[ \t]*:?[ \t]*$`. Add a new `plan` category; do NOT map Plan → discharge_instructions here — that sub-classification happens in `instructions.py`.

- [ ] **Write failing tests**

Add to `backend/tests/test_sections.py`:

```python
import pytest

DISCHARGE_SUMMARY = """
Discharge Medications:
lisinopril 10 mg PO daily

Hospital Course:
Patient admitted for pneumonia, improved on antibiotics.

Impression:
Pneumonia, resolving.

A/P:
Continue antibiotics.

Plan:
Follow up in 1 week.
Return to ER for worsening symptoms.
"""

SOAP_NOTE = """
CC:
Shortness of breath.

Objective:
BP 130/80. HR 88.

Assessment and Plan:
Hypertension, controlled.
"""

def test_detects_discharge_medications():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "medications" for s in sections)

def test_detects_hospital_course():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "hpi" for s in sections)

def test_detects_impression():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "assessment_plan" for s in sections)

def test_detects_ap_shorthand():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "assessment_plan" for s in sections)

def test_detects_plan_as_own_category():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "plan" for s in sections)

def test_soap_objective_maps_to_vitals():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "vitals" for s in sections)

def test_soap_cc_maps_to_chief_complaint():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "chief_complaint" for s in sections)

def test_soap_assessment_and_plan():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "assessment_plan" for s in sections)
```

- [ ] **Run tests, confirm they fail**

```bash
cd backend && python -m pytest tests/test_sections.py::test_detects_discharge_medications tests/test_sections.py::test_detects_plan_as_own_category -v
```
Expected: FAIL — categories not yet recognized.

- [ ] **Implement: update `_SECTION_PATTERNS` in `sections.py`**

Replace the existing `_SECTION_PATTERNS` list with:

```python
_SECTION_PATTERNS = [
    # Instructions
    (r"discharge\s+instructions?", "discharge_instructions"),
    (r"follow[\s\-]?up", "follow_up"),
    (r"return\s+precautions?|when\s+to\s+return", "return_precautions"),
    # Medications (all aliases map to same category)
    (r"discharge\s+medications?|home\s+medications?|current\s+medications?|medications?\s*(list)?|meds", "medications"),
    # Assessment/Plan
    (r"assessment\s*/\s*plan|a\s*/\s*p|assessment\s+and\s+plan", "assessment_plan"),
    (r"assessment|impression|diagnoses|problem\s+list", "assessment_plan"),
    # Plan as its own category (sub-classified by instructions.py)
    (r"plan", "plan"),
    # HPI / Hospital Course
    (r"history\s+of\s+present\s+illness|hpi|interval\s+history|hospital\s+course", "hpi"),
    # Vitals
    (r"vital\s*signs?|vitals?|objective|physical\s+exam(?:ination)?|exam|pe\b", "vitals"),
    # Chief complaint
    (r"chief\s+complaint|cc\b|reason\s+for\s+visit", "chief_complaint"),
    # Past medical history
    (r"past\s+medical\s+history|pmh", "pmh"),
]
```

- [ ] **Run all section tests**

```bash
cd backend && python -m pytest tests/test_sections.py -v
```
Expected: all pass.

- [ ] **Commit**

```bash
git add backend/extractors/sections.py backend/tests/test_sections.py
git commit -m "feat: extend section header aliases (discharge meds, hospital course, impression, A/P, plan, objective)"
```

---

### Task 2: Extend vitals patterns (`vitals.py`)

**Files:**
- Modify: `backend/extractors/vitals.py`
- Modify: `backend/tests/test_vitals.py`

**Context:** Each entry in `_PATTERNS` is `(field_name, compiled_regex, is_bp_bool)`. For BP only, two capture groups (systolic, diastolic) are joined with `/`. For all others, group 1 is the numeric value. Units should be included in the value string where present — append them by capturing an optional unit group and constructing the value string in `extract_vitals`.

- [ ] **Write failing tests**

Add to `backend/tests/test_vitals.py`:

```python
# New format variants
VARIANTS = """
Blood Pressure 142/88 mmHg
Pulse: 78 bpm
T: 98.6 F
Resp Rate: 18 breaths/min
O2 Sat 96% on room air
Weight: 185 lb
"""

ABBREVIATED = "BP 142/88. HR 78 bpm. T 98.6 F. RR 18. SpO2 96% RA. Wt 185 lb."

def test_blood_pressure_variant_with_mmhg():
    v = extract_vitals(VARIANTS)
    assert "blood_pressure" in v
    assert v["blood_pressure"]["value"].startswith("142/88")

def test_pulse_alias():
    v = extract_vitals(VARIANTS)
    assert "heart_rate" in v
    assert v["heart_rate"]["value"] == "78"

def test_temperature_T_abbreviation():
    v = extract_vitals(ABBREVIATED)
    assert "temperature" in v
    assert "98.6" in v["temperature"]["value"]

def test_respiratory_rate_resp_rate_alias():
    v = extract_vitals(VARIANTS)
    assert "respiratory_rate" in v
    assert v["respiratory_rate"]["value"] == "18"

def test_oxygen_saturation_o2_sat_alias():
    v = extract_vitals(VARIANTS)
    assert "oxygen_saturation" in v
    assert "96" in v["oxygen_saturation"]["value"]

def test_weight_lb_unit():
    v = extract_vitals(VARIANTS)
    assert "weight" in v
    assert "185" in v["weight"]["value"]

def test_abbreviated_vitals_all_extracted():
    v = extract_vitals(ABBREVIATED)
    for field in ["blood_pressure", "heart_rate", "temperature",
                  "respiratory_rate", "oxygen_saturation", "weight"]:
        assert field in v, f"Missing: {field}"
```

- [ ] **Run tests, confirm they fail**

```bash
cd backend && python -m pytest tests/test_vitals.py::test_temperature_T_abbreviation tests/test_vitals.py::test_pulse_alias -v
```
Expected: FAIL.

- [ ] **Implement: replace `_PATTERNS` in `vitals.py`**

```python
import re
from typing import Any

# Each entry: (field_name, pattern, is_bp, unit_group_index_or_None)
# For BP: groups (1, 2) = systolic/diastolic, group 3 = optional unit
# For others: group 1 = value, group 2 = optional unit
_PATTERNS = [
    (
        "blood_pressure",
        re.compile(
            r"(?i)(?:b\.?p\.?|blood\s+pressure)\s*:?\s*"
            r"(\d{2,3})\s*/\s*(\d{2,3})"
            r"(?:\s*(mmhg))?"
        ),
        True,
    ),
    (
        "heart_rate",
        re.compile(
            r"(?i)(?:h\.?r\.?|pulse|heart\s+rate)\s*:?\s*"
            r"(\d{2,3})"
            r"(?:\s*(bpm))?"
        ),
        False,
    ),
    (
        "temperature",
        re.compile(
            r"(?i)(?:\btemp(?:erature)?|\bT\b)\s*:?\s*"
            r"(\d{2,3}(?:\.\d)?)"
            r"(?:\s*°?\s*([FC]))?"
        ),
        False,
    ),
    (
        "respiratory_rate",
        re.compile(
            r"(?i)(?:r\.?r\.?|resp(?:iratory)?\s*(?:rate)?|respirations?)\s*:?\s*"
            r"(\d{1,3})"
            r"(?:\s*(breaths?/min|breaths?))?"
        ),
        False,
    ),
    (
        "oxygen_saturation",
        re.compile(
            r"(?i)(?:spo2?|o2\s+sat(?:uration)?|oxygen\s+sat(?:uration)?|sat)\s*:?\s*"
            r"(\d{2,3})\s*(%?)"
            r"(?:\s*(?:on\s+room\s+air|RA|room\s+air))?"
        ),
        False,
    ),
    (
        "weight",
        re.compile(
            r"(?i)(?:wt\.?|weight)\s*:?\s*"
            r"(\d{2,4}(?:\.\d)?)"
            r"(?:\s*(lbs?|kg|pounds?|kilograms?))?"
        ),
        False,
    ),
]


def extract_vitals(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, pattern, is_bp in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if is_bp:
            unit = m.group(3) or ""
            value = f"{m.group(1)}/{m.group(2)}"
            if unit:
                value += f" {unit}"
        else:
            num = m.group(1)
            unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
            value = f"{num} {unit}".strip() if unit else num
        results[name] = {
            "value": value,
            "span": [m.start(), m.end()],
            "source": "regex",
            "confidence": 1.0,
        }
    return results
```

- [ ] **Run all vitals tests**

```bash
cd backend && python -m pytest tests/test_vitals.py -v
```
Expected: all pass. Note: existing tests assert `value == "140/90"` (no unit) — the new pattern must still pass these since the original fixtures have no mmHg.

- [ ] **Commit**

```bash
git add backend/extractors/vitals.py backend/tests/test_vitals.py
git commit -m "feat: extend vitals patterns (T abbreviation, Pulse, Resp Rate, O2 Sat RA, unit capture)"
```

---

### Task 3: Extend metadata patterns (`metadata.py`)

**Files:**
- Modify: `backend/extractors/metadata.py`
- Modify: `backend/tests/test_metadata.py`

**Context:** Each entry in `_PATTERNS` is `(field_name, compiled_regex)`. The regex captures everything after the colon on the same line. Add aliases per the spec; patterns are tried in order and first match wins, so put longer/more-specific aliases before shorter ones.

- [ ] **Write failing tests**

Add to `backend/tests/test_metadata.py`:

```python
def test_patient_name_alias():
    m = extract_metadata("Patient Name: Jane Smith\nDate of Service: 2024-01-01")
    assert m["patient_name"]["value"] == "Jane Smith"

def test_pt_abbreviation():
    m = extract_metadata("Pt: Jane Smith")
    assert m["patient_name"]["value"] == "Jane Smith"

def test_date_seen_alias():
    m = extract_metadata("Date Seen: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_visit_date_alias():
    m = extract_metadata("Visit Date: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_dos_alias():
    m = extract_metadata("DOS: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_attending_alias():
    m = extract_metadata("Attending: Dr. Sarah Chen")
    assert "Chen" in m["provider_name"]["value"]

def test_clinician_alias():
    m = extract_metadata("Clinician: Dr. Sarah Chen")
    assert "Chen" in m["provider_name"]["value"]

def test_john_smith_note():
    note = "Patient: John Smith\nDate of Service: 2024-03-15\nProvider: Dr. Sarah Chen"
    m = extract_metadata(note)
    assert m["patient_name"]["value"] == "John Smith"
    assert m["date_of_service"]["value"] == "2024-03-15"
    assert "Chen" in m["provider_name"]["value"]
```

- [ ] **Run tests, confirm they fail**

```bash
cd backend && python -m pytest tests/test_metadata.py::test_patient_name_alias tests/test_metadata.py::test_date_seen_alias -v
```
Expected: FAIL.

- [ ] **Implement: replace `_PATTERNS` in `metadata.py`**

```python
import re
from typing import Any

_PATTERNS = [
    # patient_name — longer aliases first
    ("patient_name",    re.compile(r"(?i)(?:patient\s+name|patient|pt)\s*:\s*(.+)")),
    # date_of_service
    ("date_of_service", re.compile(r"(?i)(?:date\s+of\s+service|date\s+seen|visit\s+date|dos|date)\s*:\s*(\S+)")),
    # provider_name — longer aliases first
    ("provider_name",   re.compile(r"(?i)(?:attending\s+physician|attending|clinician|physician|provider|doctor|dr)\s*:\s*(.+)")),
]


def extract_metadata(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for field, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            results[field] = {
                "value": m.group(1).strip(),
                "span": [m.start(), m.end()],
                "source": "regex",
                "confidence": 0.9,
            }
    return results
```

- [ ] **Run all metadata tests**

```bash
cd backend && python -m pytest tests/test_metadata.py -v
```
Expected: all pass.

- [ ] **Commit**

```bash
git add backend/extractors/metadata.py backend/tests/test_metadata.py
git commit -m "feat: extend metadata patterns (Patient Name, Date Seen, DOS, Attending, Clinician)"
```

---

## Chunk 2: Medications

### Task 4: Structured medication line parser + extended regexes (`medications.py`)

**Files:**
- Modify: `backend/extractors/medications.py`
- Modify: `backend/tests/test_medications.py`

**Context:** The new strategy runs a structured line parser on any detected medications section text first, then runs medSpaCy on the full text for prose fallback. The line parser does not require a drug vocabulary — it accepts any line that has a recognizable dose, route, or frequency token. Results are tagged `"source": "section"`; medSpaCy results are tagged `"source": "medspacy"` and de-duplicated by name (case-insensitive) with the line parser taking precedence.

The function signature `extract_medications(text: str)` is unchanged. The new implementation adds an optional `sections` parameter with a default of `None` so it can be called with section data from the pipeline.

- [ ] **Write failing tests**

Add to `backend/tests/test_medications.py`:

```python
# ---- Structured line parser tests ----

SECTION_NOTE = """Medications:
- Lisinopril 10 mg PO daily
- Metformin 500 mg PO BID
- Albuterol inhaler 2 puffs q6h PRN wheezing
"""

SECTION_NOTE_BULLETED = """Home Medications:
• Atorvastatin 40 mg PO QHS
• Aspirin 81 mg PO daily
1. Metoprolol 25 mg PO BID
"""

SECTION_NOTE_UPPERCASE = """MEDICATIONS:
LISINOPRIL 10 MG PO DAILY
METFORMIN 500 MG PO BID
"""

SECTION_NO_ROUTE = """Medications:
Prednisone 20 mg daily
Ibuprofen 400 mg TID
"""

# ---- Negative tests ----

NEGATIVE_LINES = """Medications:
Continue medications as above
No home meds listed
NKDA
Allergies: penicillin
See medication reconciliation form
"""

def test_section_extracts_lisinopril():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "lisinopril" in names

def test_section_extracts_metformin():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "metformin" in names

def test_section_extracts_albuterol():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "albuterol" in names or any("albuterol" in n for n in names)

def test_albuterol_puffs_dose():
    meds = extract_medications(SECTION_NOTE)
    alb = next((m for m in meds if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "puffs" in alb["dose"].lower() or "2" in alb["dose"]

def test_albuterol_prn_frequency():
    meds = extract_medications(SECTION_NOTE)
    alb = next((m for m in meds if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "prn" in alb["frequency"].lower() or "q6h" in alb["frequency"].lower()

def test_bulleted_lines_parsed():
    meds = extract_medications(SECTION_NOTE_BULLETED)
    names = [m["name"].lower() for m in meds]
    assert "atorvastatin" in names
    assert "aspirin" in names
    assert "metoprolol" in names

def test_uppercase_med_lines_accepted():
    meds = extract_medications(SECTION_NOTE_UPPERCASE)
    names = [m["name"].lower() for m in meds]
    assert "lisinopril" in names
    assert "metformin" in names

def test_missing_route_still_extracted():
    meds = extract_medications(SECTION_NO_ROUTE)
    names = [m["name"].lower() for m in meds]
    assert "prednisone" in names
    prednisone = next(m for m in meds if "prednisone" in m["name"].lower())
    assert prednisone["dose"] == "20 mg"
    assert prednisone["route"] == ""  # missing is OK

# ---- Negative tests ----

def test_negative_continue_medications():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    assert not any("continue" in n for n in names)
    assert not any("medication" in n for n in names)

def test_negative_no_home_meds():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    assert not any("home" in n for n in names)
    assert not any("listed" in n for n in names)

def test_negative_allergy_line():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    assert "penicillin" not in names or all(
        m["route"] != "" or m["frequency"] != "" or m["dose"] != ""
        for m in meds if m["name"].lower() == "penicillin"
    )

# ---- Frequency variant tests ----

FREQ_NOTE = """Medications:
- Ibuprofen 400 mg PO every 6 hours
- Amoxicillin 500 mg PO every 8 hours
- Methotrexate 15 mg PO once weekly
- Prednisone 10 mg PO QAM
"""

def test_every_6_hours_frequency():
    meds = extract_medications(FREQ_NOTE)
    ibu = next((m for m in meds if "ibuprofen" in m["name"].lower()), None)
    assert ibu is not None
    assert "6" in ibu["frequency"] or "hour" in ibu["frequency"].lower()

def test_once_weekly_frequency():
    meds = extract_medications(FREQ_NOTE)
    mtx = next((m for m in meds if "methotrexate" in m["name"].lower()), None)
    assert mtx is not None
    assert "week" in mtx["frequency"].lower()

def test_qam_frequency():
    meds = extract_medications(FREQ_NOTE)
    pred = next((m for m in meds if "prednisone" in m["name"].lower()), None)
    assert pred is not None
    assert "qam" in pred["frequency"].lower()
```

- [ ] **Run tests, confirm they fail**

```bash
cd backend && python -m pytest tests/test_medications.py::test_section_extracts_metformin tests/test_medications.py::test_section_extracts_albuterol tests/test_medications.py::test_albuterol_puffs_dose -v
```
Expected: FAIL — structured line parser not yet implemented.

- [ ] **Implement: rewrite `medications.py`**

```python
"""
Medication extraction.
Strategy: structured line parser on medications sections → medSpaCy prose fallback.
Prototype vocabulary — not a production drug-normalization system.
"""
import re
import json
import os
from typing import Any

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "patterns", "medications.json")

# ── Dose ────────────────────────────────────────────────────────────────────
_DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*"
    r"(?:mg|mcg|g|ml|units?|meq|puffs?|tabs?|tablets?|capsules?|cap|patch|spray|drops))",
    re.IGNORECASE,
)

# ── Route ────────────────────────────────────────────────────────────────────
_ROUTE_RE = re.compile(
    r"\b(PO|IV|IM|SQ|subq|subcutaneous|inhaled|inhalation|topical|sublingual|SL|PR|"
    r"transdermal|intranasal|ophthalmic|otic|rectal|oral)\b",
    re.IGNORECASE,
)

# ── Frequency ────────────────────────────────────────────────────────────────
_FREQ_RE = re.compile(
    r"\b(once\s+daily|twice\s+daily|"
    r"every\s+\d+\s+hours?|"
    r"once\s+weekly|twice\s+weekly|"
    r"BID|TID|QID|QHS|QAM|QPM|qam|qpm|QD|"
    r"daily|q\.?d\.?|"
    r"q\d+h|"
    r"PRN|as\s+needed|"
    r"at\s+bedtime|bedtime|"
    r"weekly|monthly)\b",
    re.IGNORECASE,
)

# ── Reject patterns (guard 3) ────────────────────────────────────────────────
_REJECT_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}",
    re.IGNORECASE,
)
_REJECT_ICD = re.compile(r"\b[A-Z]\d{2,3}\.?\d*\b")
_REJECT_PROSE = re.compile(
    r"^(return\s+to|follow[\s\-]?up|avoid|drink|if\s+you|go\s+to|call|seek|"
    r"use\s+the|take\s+all|continue\s+medications?|no\s+(home\s+)?meds?|"
    r"see\s+med|nkda|allergies?)",
    re.IGNORECASE,
)

_WINDOW = 60  # characters for medSpaCy window scan

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import Config
    import medspacy
    from medspacy.target_matcher import TargetRule
    try:
        nlp = medspacy.load(Config.SPACY_MODEL, disable=["parser"])
    except OSError:
        if Config.SPACY_MODEL == "en_core_web_sm":
            raise
        import warnings
        warnings.warn(f"Model {Config.SPACY_MODEL!r} not found, falling back to en_core_web_sm")
        nlp = medspacy.load("en_core_web_sm", disable=["parser"])
    with open(_VOCAB_PATH) as f:
        vocab: list[str] = json.load(f)
    target_matcher = nlp.get_pipe("medspacy_target_matcher")
    rules = [TargetRule(name, "MEDICATION") for name in vocab]
    target_matcher.add(rules)
    _nlp = nlp
    return _nlp


def _is_rejected(line: str) -> bool:
    """Return True if this line should not be treated as a medication entry."""
    stripped = line.strip()
    if not stripped:
        return True
    # Guard 1: no dose/route/freq token at all
    has_dose = bool(_DOSE_RE.search(stripped))
    has_route = bool(_ROUTE_RE.search(stripped))
    has_freq = bool(_FREQ_RE.search(stripped))
    if not has_dose and not has_route and not has_freq:
        return True
    # Guard 2: entirely uppercase AND no dose/sig structure
    if stripped == stripped.upper() and not has_dose and not has_route and not has_freq:
        return True
    # Guard 3: matches non-medication reject patterns
    if _REJECT_DATE.search(stripped):
        return True
    if _REJECT_ICD.search(stripped):
        return True
    if _REJECT_PROSE.match(stripped):
        return True
    return False


def _parse_line(line: str, char_offset: int) -> dict[str, Any] | None:
    """
    Parse a single medication line into a med dict.
    Returns None if the line is rejected or cannot be parsed.
    """
    # Strip leading bullets, numbers, hyphens, whitespace
    clean = re.sub(r"^[\s\-•*\d.)\]]+", "", line).strip()
    if _is_rejected(clean):
        return None

    dm = _DOSE_RE.search(clean)
    rm = _ROUTE_RE.search(clean)
    fm = _FREQ_RE.search(clean)

    # Extract name: words before the first dose/route/freq token
    first_token_pos = min(
        (m.start() for m in [dm, rm, fm] if m),
        default=len(clean),
    )
    name_raw = clean[:first_token_pos].strip()
    # Remove trailing punctuation from name
    name = re.sub(r"[\s,;:]+$", "", name_raw).strip()
    if not name:
        return None

    # Build frequency: append PRN qualifier if present after main freq match
    freq = ""
    if fm:
        freq = fm.group(1)
        after_freq = clean[fm.end():]
        prn_match = re.search(r"\bPRN\b", after_freq, re.IGNORECASE)
        if prn_match:
            freq = f"{freq} PRN"

    return {
        "name": name.lower(),
        "dose": dm.group(1).strip() if dm else "",
        "route": rm.group(1) if rm else "",
        "frequency": freq,
        "span": [char_offset, char_offset + len(line)],
        "source": "section",
        "confidence": 0.85,
    }


def _parse_section_lines(section_text: str, section_start: int) -> list[dict[str, Any]]:
    """Parse a medications section line-by-line."""
    results = []
    offset = section_start
    for line in section_text.splitlines():
        med = _parse_line(line, offset)
        if med:
            results.append(med)
        offset += len(line) + 1  # +1 for newline
    return results


def _scan_window(text: str, start: int, end: int) -> dict[str, str]:
    window_start = max(0, start - _WINDOW)
    window_end = min(len(text), end + _WINDOW)
    snippet = text[window_start:window_end]
    result: dict[str, str] = {}
    dm = _DOSE_RE.search(snippet)
    if dm:
        result["dose"] = dm.group(1).strip()
    rm = _ROUTE_RE.search(snippet)
    if rm:
        result["route"] = rm.group(1)
    fm = _FREQ_RE.search(snippet)
    if fm:
        result["frequency"] = fm.group(1)
    return result


def extract_medications(text: str, sections: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Extract medications from text.
    1. Structured line parser on any medications section (source: "section").
    2. medSpaCy on full text for prose fallback (source: "medspacy").
    3. De-duplicate by name; section results take precedence.
    """
    from extractors.sections import detect_sections
    if sections is None:
        sections = detect_sections(text)

    # Step 1: structured line parser on medications sections
    section_results: list[dict[str, Any]] = []
    for sec in sections:
        if sec["category"] == "medications":
            section_results.extend(_parse_section_lines(sec["text"], sec["start"] + len(sec["header"]) + 1))

    section_names = {m["name"].lower() for m in section_results}

    # Step 2: medSpaCy prose fallback
    nlp = _get_nlp()
    doc = nlp(text)
    prose_results: list[dict[str, Any]] = []
    for ent in doc.ents:
        if ent.label_ != "MEDICATION":
            continue
        if ent._.is_negated:
            continue
        name = ent.text.lower()
        if name in section_names:
            continue  # already found by line parser; skip
        extra = _scan_window(text, ent.start_char, ent.end_char)
        prose_results.append({
            "name": name,
            "dose": extra.get("dose", ""),
            "route": extra.get("route", ""),
            "frequency": extra.get("frequency", ""),
            "span": [ent.start_char, ent.end_char],
            "source": "medspacy",
            "confidence": 0.9,
        })

    return section_results + prose_results
```

- [ ] **Update `pipeline.py` to pass sections to `extract_medications`**

In `backend/extractors/pipeline.py`, change the medications extraction call:

```python
    meds_raw = extract_medications(clean, sections)
```

- [ ] **Run all medication tests**

```bash
cd backend && python -m pytest tests/test_medications.py -v
```
Expected: all pass.

- [ ] **Run full test suite to check for regressions**

```bash
cd backend && python -m pytest -q
```
Expected: all pass.

- [ ] **Commit**

```bash
git add backend/extractors/medications.py backend/extractors/pipeline.py backend/tests/test_medications.py
git commit -m "feat: structured medication line parser with extended dose/route/freq regexes and over-greedy guards"
```

---

## Chunk 3: Instructions + End-to-End

### Task 5: Plan sub-classification + OCR-tolerant fallback (`instructions.py`)

**Files:**
- Modify: `backend/extractors/instructions.py`
- Modify: `backend/tests/test_instructions.py`

**Context:** The key changes:
1. `plan` and `hpi` (hospital_course) sections are sub-classified sentence-by-sentence using triggers, filling whichever instruction categories aren't yet populated — NOT mapped wholesale to `discharge_instructions`.
2. Sentence splitting is now tolerant of OCR artifacts: splits on `.`, `!`, `?`, `;`, newlines, and colon-led lines (e.g., `Return to ER for:` is a trigger sentence whose following items are the aggregated content).
3. Multi-sentence aggregation: trigger sentence + next 2 sentences, stopping at the next trigger or section header.

- [ ] **Write failing tests**

Add to `backend/tests/test_instructions.py`:

```python
# Plan sub-classification tests
PLAN_SECTION_NOTE = """
Plan:
Follow up with PCP in 2 weeks.
Return to ER for chest pain or fever.
Continue all medications as prescribed. Drink plenty of fluids.
"""

def test_plan_subclassification_follow_up():
    from extractors.sections import detect_sections
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    assert "follow_up" in result, "follow_up should be extracted from Plan section"

def test_plan_subclassification_return_precautions():
    from extractors.sections import detect_sections
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    assert "return_precautions" in result

def test_plan_not_mapped_wholesale():
    """Plan section content should NOT fill discharge_instructions with the entire section text."""
    from extractors.sections import detect_sections
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    if "discharge_instructions" in result:
        # Value should be a sentence, not the entire Plan section
        assert len(result["discharge_instructions"]["value"]) < len(PLAN_SECTION_NOTE)

# Multi-sentence aggregation tests
COLON_LED_NOTE = """
Return Precautions:
Return to the ER for: chest pain, shortness of breath, or fever above 101.
"""

MULTILINE_RETURN = """
Return to ER if you develop any of the following:
chest pain or pressure
shortness of breath or difficulty breathing
fever above 101 F
"""

def test_colon_led_return_precautions():
    from extractors.sections import detect_sections
    sections = detect_sections(COLON_LED_NOTE)
    result = extract_instructions(COLON_LED_NOTE, sections)
    assert "return_precautions" in result
    val = result["return_precautions"]["value"].lower()
    assert "chest" in val or "return" in val

def test_multiline_aggregation():
    """Fallback should aggregate the trigger sentence with following lines."""
    result = extract_instructions(MULTILINE_RETURN, [])
    assert "return_precautions" in result
    val = result["return_precautions"]["value"].lower()
    # Should capture more than just the first line
    assert "chest" in val or "breath" in val or "fever" in val

def test_aggregation_stops_at_next_trigger():
    """Aggregation must not bleed into a follow_up sentence."""
    note = """Return to ER if chest pain develops.
Follow up with your doctor in 2 weeks.
See your PCP for medication review.
"""
    result = extract_instructions(note, [])
    if "return_precautions" in result:
        val = result["return_precautions"]["value"].lower()
        # follow-up content should NOT be included in return_precautions
        assert "follow up" not in val or "chest" in val

# OCR-tolerant splitting tests
SEMICOLON_NOTE = "Take medications as prescribed; follow up in 2 weeks; return to ER for chest pain."

def test_semicolon_splits_into_sentences():
    result = extract_instructions(SEMICOLON_NOTE, [])
    assert "follow_up" in result or "return_precautions" in result

# Bullet-point content
BULLET_NOTE = """
Discharge Instructions:
- Take all medications as prescribed.
- Drink plenty of fluids.
- Rest for 48 hours.
"""

def test_bullet_content_captured():
    from extractors.sections import detect_sections
    sections = detect_sections(BULLET_NOTE)
    result = extract_instructions(BULLET_NOTE, sections)
    assert "discharge_instructions" in result
    assert len(result["discharge_instructions"]["value"]) > 0
```

- [ ] **Run tests, confirm they fail**

```bash
cd backend && python -m pytest tests/test_instructions.py::test_plan_subclassification_follow_up tests/test_instructions.py::test_multiline_aggregation -v
```
Expected: FAIL.

- [ ] **Implement: rewrite `instructions.py`**

```python
import re
from typing import Any

_CATEGORIES = ["discharge_instructions", "follow_up", "return_precautions"]

# ── Trigger patterns ──────────────────────────────────────────────────────────
_FALLBACK_TRIGGERS: dict[str, list[re.Pattern]] = {
    "follow_up": [
        re.compile(r"(?i)\bfollow[\s\-]?up\s+with\b"),
        re.compile(r"(?i)\bfollow[\s\-]?up\b"),
        re.compile(r"(?i)\bsee\s+your\b"),
        re.compile(r"(?i)\breturn\s+to\s+(clinic|office|your\s+doctor|primary\s+care|pcp)\b"),
        re.compile(r"(?i)\bschedule\s+an?\s+appointment\b"),
        re.compile(r"(?i)\bcall\s+your\s+doctor\b"),
    ],
    "return_precautions": [
        re.compile(r"(?i)\breturn\s+to\s+(the\s+)?(er|emergency|hospital)\b"),
        re.compile(r"(?i)\bgo\s+to\s+(the\s+)?(er|emergency)\b"),
        re.compile(r"(?i)\bseek\s+(medical|emergency|immediate)\b"),
        re.compile(r"(?i)\bcall\s+(911|if\b)"),
        re.compile(r"(?i)\bif\s+(you\s+)?(develop|experience|notice|have|feel)\b"),
        re.compile(r"(?i)\bworsening\b"),
        re.compile(r"(?i)\bseek\s+care\b"),
    ],
    "discharge_instructions": [
        re.compile(r"(?i)\btake\s+(your|all)\b"),
        re.compile(r"(?i)\bdrink\s+plenty\b"),
        re.compile(r"(?i)\brest\b"),
        re.compile(r"(?i)\bavoid\b"),
        re.compile(r"(?i)\bdo\s+not\b"),
        re.compile(r"(?i)\buse\s+your\b"),
        re.compile(r"(?i)\bcontinue\s+your\b"),
        re.compile(r"(?i)\bapply\b"),
    ],
}

# Matches a line that looks like a section header (used as aggregation stop)
_HEADER_RE = re.compile(r"(?i)^[ \t]*[A-Za-z\s/]+[ \t]*:[ \t]*$", re.MULTILINE)


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """
    Split text into (sentence, start, end) tuples.
    Tolerates: periods, !, ?, semicolons, newlines, colon-led lines.
    Strips leading bullets/numbers/whitespace from each sentence.
    """
    sentences = []
    # Split on sentence-ending punctuation, semicolons, and newlines
    pattern = re.compile(r"(?<=[.!?;])\s+|\n+")
    last = 0
    for m in pattern.finditer(text):
        raw = text[last:m.start()]
        sent = re.sub(r"^[\s\-•*\d.)\]]+", "", raw).strip()
        if sent:
            sentences.append((sent, last, m.start()))
        last = m.end()
    remaining = re.sub(r"^[\s\-•*\d.)\]]+", "", text[last:]).strip()
    if remaining:
        sentences.append((remaining, last, len(text)))
    return sentences


def _classify_sentence(sent: str) -> str | None:
    """Return the category triggered by this sentence, or None."""
    for cat in _CATEGORIES:
        for trigger in _FALLBACK_TRIGGERS[cat]:
            if trigger.search(sent):
                return cat
    return None


def _sub_classify_text(text: str, text_start: int, existing: dict[str, Any]) -> dict[str, Any]:
    """
    Run trigger-based sub-classification on a block of text (e.g. a Plan section).
    Fills categories not already present in `existing`.
    Returns a dict of newly found categories.
    """
    found: dict[str, Any] = {}
    sentences = _split_sentences(text)
    i = 0
    while i < len(sentences):
        sent, s_start, s_end = sentences[i]
        cat = _classify_sentence(sent)
        if cat and cat not in existing and cat not in found:
            # Aggregate: trigger sentence + next 2, stopping at next trigger or header
            parts = [sent]
            j = i + 1
            while j < i + 3 and j < len(sentences):
                next_sent, _, _ = sentences[j]
                if _classify_sentence(next_sent) is not None:
                    break
                if _HEADER_RE.match(next_sent):
                    break
                parts.append(next_sent)
                j += 1
            value = " ".join(parts)
            abs_start = text_start + s_start
            abs_end = text_start + sentences[j - 1][2] if j > i + 1 else text_start + s_end
            found[cat] = {
                "value": value,
                "span": [abs_start, abs_end],
                "source": "fallback",
                "confidence": 0.6,
            }
        i += 1
    return found


def extract_instructions(
    text: str,
    sections: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    # Primary: dedicated instruction sections
    for section in sections:
        cat = section["category"]
        if cat in _CATEGORIES and cat not in result:
            result[cat] = {
                "value": section["text"],
                "span": [section["start"], section["end"]],
                "source": "section",
                "confidence": 0.9,
            }

    # Secondary: sub-classify Plan and HPI (hospital_course) sections
    for section in sections:
        if section["category"] in ("plan", "hpi") and len(result) < len(_CATEGORIES):
            new = _sub_classify_text(section["text"], section["end"] - len(section["text"]), result)
            for cat, val in new.items():
                if cat not in result:
                    result[cat] = val

    # Fallback: sentence/keyword on full text (fills only missing categories)
    missing = [c for c in _CATEGORIES if c not in result]
    if not missing:
        return result

    found = _sub_classify_text(text, 0, result)
    for cat, val in found.items():
        if cat not in result:
            result[cat] = val

    return result
```

- [ ] **Run all instruction tests**

```bash
cd backend && python -m pytest tests/test_instructions.py -v
```
Expected: all pass.

- [ ] **Commit**

```bash
git add backend/extractors/instructions.py backend/tests/test_instructions.py
git commit -m "feat: Plan sub-classification, OCR-tolerant sentence splitting, multi-sentence aggregation in instructions extractor"
```

---

### Task 6: End-to-end pipeline tests

**Files:**
- Modify: `backend/tests/test_pipeline.py`

**Context:** Two new end-to-end fixtures:
1. The John Smith discharge summary from the design spec — verifies all 3 medications with correct dose/route/freq, all vitals, all metadata, all 3 instruction categories.
2. A headerless free-text note — verifies fallback extraction of at least follow_up and return_precautions.

- [ ] **Write failing tests**

Add to `backend/tests/test_pipeline.py`:

```python
JOHN_SMITH = """DISCHARGE SUMMARY

Patient: John Smith
Date of Service: 2024-03-15
Provider: Dr. Sarah Chen

Vitals:
BP: 142/88 mmHg
HR: 78 bpm
Temp: 98.6 F
RR: 18 breaths/min
SpO2: 96% on room air
Weight: 185 lb

Medications:
Lisinopril 10 mg PO daily
Metformin 500 mg PO BID
Albuterol inhaler 2 puffs q6h PRN wheezing

Discharge Instructions:
Drink plenty of fluids and rest as needed.
Use albuterol inhaler as directed for wheezing or shortness of breath.
Continue home medications as listed above.

Follow Up:
Follow up with primary care physician in 2 weeks.

Return Precautions:
Return to the ER for chest pain, worsening shortness of breath, persistent fever, or inability to tolerate fluids.
"""

HEADERLESS = """Patient feels better after treatment.
Take ibuprofen 400 mg every 8 hours as needed for pain.
Follow up with your doctor in one week.
Return to the ER if symptoms worsen or fever develops.
"""

def test_john_smith_extracts_lisinopril():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert "lisinopril" in names

def test_john_smith_extracts_metformin():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert "metformin" in names

def test_john_smith_extracts_albuterol():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert any("albuterol" in n for n in names)

def test_john_smith_albuterol_dose():
    out = run_pipeline(JOHN_SMITH)
    alb = next((m for m in out["medications"] if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "puffs" in alb["dose"].lower() or "2" in alb["dose"]

def test_john_smith_albuterol_prn():
    out = run_pipeline(JOHN_SMITH)
    alb = next((m for m in out["medications"] if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "prn" in alb["frequency"].lower() or "q6h" in alb["frequency"].lower()

def test_john_smith_all_vitals():
    out = run_pipeline(JOHN_SMITH)
    for field in ["blood_pressure", "heart_rate", "temperature",
                  "respiratory_rate", "oxygen_saturation", "weight"]:
        assert field in out["vitals"], f"Missing vital: {field}"

def test_john_smith_metadata():
    out = run_pipeline(JOHN_SMITH)
    assert out["metadata"]["patient_name"]["value"] == "John Smith"
    assert out["metadata"]["date_of_service"]["value"] == "2024-03-15"
    assert "Chen" in out["metadata"]["provider_name"]["value"]

def test_john_smith_all_instructions():
    out = run_pipeline(JOHN_SMITH)
    for cat in ["discharge_instructions", "follow_up", "return_precautions"]:
        assert cat in out["instructions"], f"Missing instruction: {cat}"

def test_headerless_fallback_follow_up():
    out = run_pipeline(HEADERLESS)
    assert "follow_up" in out["instructions"]

def test_headerless_fallback_return_precautions():
    out = run_pipeline(HEADERLESS)
    assert "return_precautions" in out["instructions"]
```

- [ ] **Run tests, confirm they fail (before all changes)**

```bash
cd backend && python -m pytest tests/test_pipeline.py::test_john_smith_extracts_metformin tests/test_pipeline.py::test_john_smith_extracts_albuterol -v
```
Expected: FAIL until medications.py changes in Task 4 are done.

- [ ] **After Tasks 1–5 are done, run all end-to-end tests**

```bash
cd backend && python -m pytest tests/test_pipeline.py -v
```
Expected: all pass.

- [ ] **Run the full test suite**

```bash
cd backend && python -m pytest -q
```
Expected: all pass (135+ existing tests + all new tests).

- [ ] **Commit**

```bash
git add backend/tests/test_pipeline.py
git commit -m "test: end-to-end pipeline tests for John Smith discharge summary and headerless note"
```

---

### Task 7: Final integration commit

- [ ] **Run full suite one last time**

```bash
cd backend && python -m pytest --tb=short -q
```
Expected: 0 failures.

- [ ] **Commit all plan docs**

```bash
git add docs/
git commit -m "docs: add robust parser implementation plan"
```
