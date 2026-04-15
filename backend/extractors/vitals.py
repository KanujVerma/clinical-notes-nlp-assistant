import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern, bool]] = [
    (
        "blood_pressure",
        re.compile(r"(?i)(?:\bb\.?p\.?\b|blood\s+pressure)\s*:?\s*(\d{2,3})\s*/\s*(\d{2,3})"),
        True,
    ),
    (
        "heart_rate",
        re.compile(r"(?i)(?:\b(?:h\.?r\.?|pulse)\b|heart\s+rate)\s*:?\s*(\d{2,3})\s*(?:bpm)?"),
        False,
    ),
    (
        "temperature",
        re.compile(r"(?i)(?:\btemp(?:erature)?)\s*:?\s*(\d{2,3}(?:\.\d)?)\s*°?\s*[fc]?"),
        False,
    ),
    (
        "respiratory_rate",
        re.compile(r"(?i)(?:\b(?:r\.?r\.?|respirations?)\b|resp(?:iratory)?\s+rate)\s*:?\s*(\d{1,3})"),
        False,
    ),
    (
        "oxygen_saturation",
        re.compile(r"(?i)(?:\bspo2?\b|o2\s+sat(?:uration)?|oxygen\s+sat(?:uration)?)\s*:?\s*(\d{2,3})\s*%?"),
        False,
    ),
    (
        "weight",
        re.compile(r"(?i)(?:\bwt\.?\b|weight)\s*:?\s*(\d{2,4}(?:\.\d)?)\s*(?:lbs?|kg|pounds?|kilograms?)?"),
        False,
    ),
]


def extract_vitals(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, pattern, is_bp in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        value = f"{m.group(1)}/{m.group(2)}" if is_bp else m.group(1)
        results[name] = {
            "value": value,
            "span": [m.start(), m.end()],
            "source": "regex",
            "confidence": 1.0,
        }
    return results
