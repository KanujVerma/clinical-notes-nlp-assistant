"""
Compute correction_count between extracted and validated JSON.

Rules:
- Vitals/metadata/instructions: compare `.value` of each field dict (trimmed string).
  +1 per changed/added/removed field. Does NOT compare span/source/confidence.
- Medications: match by name (only), then check if any visible field changed.
  +1 per added, removed, or changed item. No sub-field breakdown within an item.
"""
from typing import Any


def _get_value(field_data: Any) -> str:
    """Extract the .value string from a field dict, or stringify the whole thing."""
    if isinstance(field_data, dict):
        return str(field_data.get("value", "")).strip()
    return str(field_data).strip()


def _leaf_diff(extracted: dict, validated: dict) -> int:
    """Compare two section dicts (e.g. vitals, instructions, metadata) by .value only."""
    count = 0
    all_keys = set(extracted) | set(validated)
    for key in all_keys:
        if key not in extracted:
            count += 1  # field added by reviewer
        elif key not in validated:
            count += 1  # field removed by reviewer
        else:
            if _get_value(extracted[key]) != _get_value(validated[key]):
                count += 1
    return count


def _med_name_key(med: dict) -> str:
    """Match medications by name only — dose changes are corrections, not new items."""
    return med.get("name", "").lower().strip()


def compute_correction_count(extracted: dict[str, Any], validated: dict[str, Any]) -> int:
    count = 0

    # Scalar sections: compare .value of each field
    for section in ("vitals", "instructions", "metadata"):
        ext_sec = extracted.get(section, {})
        val_sec = validated.get(section, {})
        if isinstance(ext_sec, dict) and isinstance(val_sec, dict):
            count += _leaf_diff(ext_sec, val_sec)

    # Medications: match by name, count adds/removes/changes as +1 each
    ext_meds = {_med_name_key(m): m for m in (extracted.get("medications") or [])}
    val_meds = {_med_name_key(m): m for m in (validated.get("medications") or [])}
    all_keys = set(ext_meds) | set(val_meds)
    for k in all_keys:
        if k not in ext_meds or k not in val_meds:
            count += 1  # added or removed
        else:
            # Check if any visible field changed (excluding span/source/confidence)
            e, v = ext_meds[k], val_meds[k]
            for field in ("name", "dose", "route", "frequency"):
                if e.get(field, "").strip() != v.get(field, "").strip():
                    count += 1
                    break

    return count
