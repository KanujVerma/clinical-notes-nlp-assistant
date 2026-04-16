import re
from typing import Any

_PATTERNS = [
    # patient_name — longer aliases first to avoid partial matches
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
