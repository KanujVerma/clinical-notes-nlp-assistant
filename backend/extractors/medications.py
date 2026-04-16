"""
Medication extraction using medSpaCy TargetMatcher + regex.
Prototype vocabulary — not a production drug-normalization system.
No RxNorm, no brand/generic resolution, no dose unit conversion.
"""
import re
import json
import os
from typing import Any

_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "patterns", "medications.json")
_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|mEq))", re.IGNORECASE)
_ROUTE_RE = re.compile(
    r"\b(PO|IV|IM|SQ|subq|subcutaneous|inhaled|inhalation|topical|sublingual|SL|PR|transdermal)\b",
    re.IGNORECASE,
)
_FREQ_RE = re.compile(
    r"\b(once\s+daily|twice\s+daily|BID|TID|QID|QHS|QAM|daily|q\.?d\.?|q\d+h|PRN|as\s+needed|at\s+bedtime|bedtime|weekly|monthly)\b",
    re.IGNORECASE,
)

_WINDOW = 60  # characters to scan around each medication match

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

    # Disable the dependency parser to avoid conflict with medSpaCy's PyRuSH sentencizer
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


def extract_medications(text: str) -> list[dict[str, Any]]:
    nlp = _get_nlp()
    doc = nlp(text)
    results: list[dict[str, Any]] = []

    for ent in doc.ents:
        if ent.label_ != "MEDICATION":
            continue
        if ent._.is_negated:
            continue

        extra = _scan_window(text, ent.start_char, ent.end_char)
        med: dict[str, Any] = {
            "name": ent.text.lower(),
            "dose": extra.get("dose", ""),
            "route": extra.get("route", ""),
            "frequency": extra.get("frequency", ""),
            "span": [ent.start_char, ent.end_char],
            "source": "medspacy",
            "confidence": 0.9,
        }
        results.append(med)

    return results
