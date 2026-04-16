import re
from typing import Any

# Each entry: (field_name, pattern, is_bp)
# For BP: groups (1, 2) = systolic/diastolic, group 3 = optional unit (mmHg)
# For others: group 1 = value, group 2 = optional unit (may be None)
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
            r"(?:\s*bpm)?"
        ),
        False,
    ),
    (
        "temperature",
        re.compile(
            r"(?i)(?:\btemp(?:erature)?|\bT\b)\s*:?\s*"
            r"(\d{2,3}(?:\.\d)?)"
            r"(?:\s*°?\s*[FC])?"
        ),
        False,
    ),
    (
        "respiratory_rate",
        re.compile(
            r"(?i)(?:(?:r\.?r\.?|resp(?:iratory)?\s*(?:rate)?|respirations?)\s*:?\s*(\d{1,3})"
            r"|(\d{1,3})\s+breaths?/min)"
        ),
        False,
    ),
    (
        "oxygen_saturation",
        re.compile(
            r"(?i)(?:spo2?|o2\s+sat(?:uration)?|oxygen\s+sat(?:uration)?|sat)\s*:?\s*"
            r"(\d{2,3})"
            r"\s*%?"
            r"(?:\s*(?:on\s+room\s+air|RA|room\s+air))?"
        ),
        False,
    ),
    (
        "weight",
        re.compile(
            r"(?i)(?:wt\.?|weight)\s*:?\s*"
            r"(\d{2,4}(?:\.\d)?)"
            r"(?:\s*(?:lbs?|kg|pounds?|kilograms?))?"
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
            # First non-None group is the numeric value
            num = next((g for g in m.groups() if g is not None), "")
            value = num
        results[name] = {
            "value": value,
            "span": [m.start(), m.end()],
            "source": "regex",
            "confidence": 1.0,
        }
    return results
