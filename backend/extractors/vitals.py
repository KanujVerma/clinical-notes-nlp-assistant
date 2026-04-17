import re
from typing import Any

# Each entry: (field_name, pattern, mode)
# mode "bp"       — groups (sys, dia, unit?)
# mode "num_unit" — groups (num, unit?)
# mode "rr"       — groups (num_abbrev, unit_abbrev?, num_standalone, unit_standalone)
_PATTERNS = [
    (
        "blood_pressure",
        re.compile(
            r"(?i)(?:b\.?p\.?|blood\s+pressure)\s*:?\s*"
            r"(\d{2,3})\s*/\s*(\d{2,3})"
            r"(?:\s*(mmhg))?"
        ),
        "bp",
    ),
    (
        "heart_rate",
        re.compile(
            r"(?i)(?:h\.?r\.?|pulse|heart\s+rate)\s*:?\s*"
            r"(\d{2,3})"
            r"(?:\s*(bpm))?"
        ),
        "num_unit",
    ),
    (
        "temperature",
        re.compile(
            r"(?i)(?:\btemp(?:erature)?|\bT\b)\s*:?\s*"
            r"(\d{2,3}(?:\.\d)?)"
            r"(?:\s*°?\s*([FC]))?"
        ),
        "num_unit",
    ),
    (
        "respiratory_rate",
        re.compile(
            r"(?i)(?:"
            r"(?:r\.?r\.?|resp(?:iratory)?\s*(?:rate)?|respirations?)\s*:?\s*(\d{1,3})(?:\s*(breaths?/min))?"
            r"|(\d{1,3})\s+(breaths?/min)"
            r")"
        ),
        "rr",
    ),
    (
        "oxygen_saturation",
        re.compile(
            r"(?i)(?:spo2?|o2\s+sat(?:uration)?|oxygen\s+sat(?:uration)?|sat)\s*:?\s*"
            r"(\d{2,3})"
            r"\s*(%)"
            r"(?:\s*(?:on\s+room\s+air|RA|room\s+air))?"
        ),
        "num_unit",
    ),
    (
        "weight",
        re.compile(
            r"(?i)(?:wt\.?|weight)\s*:?\s*"
            r"(\d{2,4}(?:\.\d)?)"
            r"(?:\s*(lbs?|kg|pounds?|kilograms?))?"
        ),
        "num_unit",
    ),
]


def _join(num: str, unit: str) -> str:
    """Join a numeric value and its unit with appropriate spacing."""
    if not unit:
        return num
    # Symbols like % attach directly; alphabetic units get a space
    sep = "" if unit.startswith("%") else " "
    return f"{num}{sep}{unit}"


def extract_vitals(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, pattern, mode in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if mode == "bp":
            unit = m.group(3) or ""
            value = f"{m.group(1)}/{m.group(2)}"
            if unit:
                value += f" {unit}"
        elif mode == "rr":
            # groups: (num_abbrev, unit_abbrev?, num_standalone, unit_standalone)
            num = m.group(1) or m.group(3) or ""
            unit = m.group(2) or m.group(4) or ""
            value = _join(num, unit)
        else:  # num_unit
            num = m.group(1) or ""
            unit = m.group(2) or ""
            value = _join(num, unit)
        results[name] = {
            "value": value,
            "span": [m.start(), m.end()],
            "source": "regex",
            "confidence": 1.0,
        }
    return results
