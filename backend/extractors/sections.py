"""Section detection using regex header matching."""
import re
from typing import Any

_SECTION_PATTERNS = [
    (r"discharge\s+instructions?", "discharge_instructions"),
    (r"follow[\s\-]?up", "follow_up"),
    (r"return\s+precautions?", "return_precautions"),
    (r"medications?(\s+list)?", "medications"),
    (r"assessment\s*/\s*plan|a\s*/\s*p", "assessment_plan"),
    (r"(assessment|plan)", "assessment_plan"),
    (r"history\s+of\s+present\s+illness|hpi", "hpi"),
    (r"(physical\s+exam|pe|examination)", "physical_exam"),
    (r"vital\s*signs?|vitals?", "vitals"),
    (r"(past\s+medical\s+history|pmh)", "pmh"),
    (r"(chief\s+complaint|cc)", "chief_complaint"),
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
