"""Conservative, versioned post-hoc normalizers for synthetic vital scoring.

Aliases describe *identical measurement identities*, not inferred values.
Do not turn partial readings (e.g. a lone systolic BP) into full BP or
rewrite decimals, units, route, medication status, or numeric comparisons.

This table was selected after inspecting the 30-case synthetic model outputs,
so any alias-based replay result is an EXPLORATORY ANALYSIS, never a frozen
prospective score or independent clinical validation.
"""
from __future__ import annotations

import re
from typing import Any

ALIAS_VERSION = "vital_identity_aliases_posthoc_v1"

_VITAL_ALIASES = {
    "bp": "blood_pressure",
    "blood pressure": "blood_pressure",
    "blood_pressure": "blood_pressure",
    "hr": "heart_rate",
    "heart rate": "heart_rate",
    "heart_rate": "heart_rate",
    "pulse": "heart_rate",
    "rr": "respiratory_rate",
    "respiratory rate": "respiratory_rate",
    "respiratory_rate": "respiratory_rate",
    "spo2": "oxygen_saturation",
    "spo₂": "oxygen_saturation",
    "oxygen sat": "oxygen_saturation",
    "oxygen saturation": "oxygen_saturation",
    "oxygen_saturation": "oxygen_saturation",
    "temp": "temperature",
    "temperature": "temperature",
    "glucose": "blood_glucose",
    "blood glucose": "blood_glucose",
    "blood_glucose": "blood_glucose",
    "fasting blood glucose": "blood_glucose",
}


def _text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").strip().casefold().split())


def canonical_vital_type(raw: Any) -> str:
    text = _text(raw)
    key = re.sub(r"[\s_-]+", " ", text)
    # Unknown fields must stay distinct; do not invent synonym matches.
    return _VITAL_ALIASES.get(text, _VITAL_ALIASES.get(key, key.replace(" ", "_")))


def normalized_vitals(records: list[dict]) -> list[dict]:
    """Copy records for scoring without altering original captured predictions."""
    if not isinstance(records, list):
        raise ValueError("INVALID_VITAL_ALIAS_INPUT")
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("INVALID_VITAL_ALIAS_INPUT")
        item = dict(record)
        kind = canonical_vital_type(record.get("vital_type"))
        if not kind:
            raise ValueError("INVALID_VITAL_ALIAS_INPUT")
        item["vital_type"] = kind
        value = _text(item.get("value"))
        unit = _text(item.get("unit"))
        # SpO2 sometimes duplicates its "%" unit inside the value: 98% / %.
        # Removing this *redundancy only* does not change the measurement.
        if kind == "oxygen_saturation" and unit == "%" and re.fullmatch(r"\d+(?:\.\d+)?%", value):
            value = value[:-1]
        item["value"] = value
        item["unit"] = unit
        normalized.append(item)
    return normalized
