"""
Medication extraction.
Strategy: structured line parser on medications sections -> medSpaCy prose fallback.
Prototype vocabulary -- not a production drug-normalization system.
"""
import re
import json
import os
from typing import Any

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "patterns", "medications.json")

# -- Dose -----------------------------------------------------------------------
_DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*"
    r"(?:mg|mcg|g|ml|units?|meq|puffs?|tablets?|tabs?|capsules?|cap|patch|spray|drops))",
    re.IGNORECASE,
)

# -- Route ----------------------------------------------------------------------
_ROUTE_RE = re.compile(
    r"\b(PO|IV|IM|SQ|subq|subcutaneous|inhaled|inhalation|topical|sublingual|SL|PR|"
    r"transdermal|intranasal|ophthalmic|otic|rectal|oral)\b",
    re.IGNORECASE,
)

# -- Frequency ------------------------------------------------------------------
_FREQ_RE = re.compile(
    r"\b(once\s+daily|twice\s+daily|"
    r"every\s+\d+\s+hours?|"
    r"once\s+weekly|twice\s+weekly|"
    r"BID|TID|QID|QHS|QAM|QPM|QD|"
    r"daily|q\.?d\.?|"
    r"q\d+h|"
    r"PRN|as\s+needed|"
    r"at\s+bedtime|bedtime|"
    r"weekly|monthly)\b",
    re.IGNORECASE,
)

# -- Reject patterns (guard 3) --------------------------------------------------
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


def _parse_line(line: str, char_offset: int) -> "dict[str, Any] | None":
    """
    Parse a single medication line into a med dict.
    Returns None if the line is rejected or cannot be parsed.
    """
    # Strip leading bullets, numbers, hyphens, whitespace
    clean = re.sub(r"^[\s\-\u2022*\d.)\]]+", "", line).strip()
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


def _parse_section_lines(section_text: str, section_start: int) -> "list[dict[str, Any]]":
    """Parse a medications section line-by-line."""
    results = []
    offset = section_start
    for line in section_text.splitlines():
        med = _parse_line(line, offset)
        if med:
            results.append(med)
        offset += len(line) + 1  # +1 for newline
    return results


def _scan_window(text: str, start: int, end: int) -> "dict[str, str]":
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


def extract_medications(text: str, sections: "list[dict[str, Any]] | None" = None) -> "list[dict[str, Any]]":
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
            # sec["text"] is the text after the header (already stripped)
            # We reconstruct the offset as: sec["start"] + len(sec["header"]) + 1
            header_end = sec["start"] + len(sec["header"]) + 1  # +1 for the colon/newline
            section_results.extend(_parse_section_lines(sec["text"], header_end))

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
