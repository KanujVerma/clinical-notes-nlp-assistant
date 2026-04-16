"""Section detection using regex header matching."""
import re
from typing import Any

_SECTION_PATTERNS = [
    # Instructions
    (r"discharge\s+instructions?", "discharge_instructions"),
    (r"follow[\s\-]?up", "follow_up"),
    (r"return\s+precautions?|when\s+to\s+return", "return_precautions"),
    # Medications (all aliases map to same category)
    (r"discharge\s+medications?|home\s+medications?|current\s+medications?|medications?\s*(list)?|meds", "medications"),
    # Assessment/Plan — compound forms before single words
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

_COMPILED = [
    (re.compile(rf"(?i)^[ \t]*{pat}[ \t]*:?[ \t]*$", re.MULTILINE), cat)
    for pat, cat in _SECTION_PATTERNS
]


def detect_sections(text: str) -> list[dict[str, Any]]:
    """
    Return a list of detected sections with keys:
        category, header, text, start, end (char offsets in text).
    """
    hits: list[tuple[int, int, str, str]] = []
    for pattern, category in _COMPILED:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), category, m.group().strip()))

    if not hits:
        return []

    hits.sort(key=lambda h: h[0])

    sections = []
    for i, (start, end, category, header) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        section_text = text[end:next_start].strip()
        sections.append({
            "category": category,
            "header": header,
            "text": section_text,
            "start": start,
            "end": next_start,
        })
    return sections
