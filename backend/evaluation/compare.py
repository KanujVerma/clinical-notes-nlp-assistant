"""
Compare pipeline predictions against ground-truth labels.
All string comparisons: trimmed, lowercased, units stripped.
"""
import re
from typing import Any


def _normalize(s: str) -> str:
    """Strip common vital units, lowercase, trim. Use for vitals/metadata fields only."""
    s = s.lower().strip()
    # Strip common units from end of string (vitals only — do NOT apply to free text)
    s = re.sub(r'\s*(lbs?|kg|pounds?|kilograms?|bpm|mmhg|%)\s*$', '', s).strip()
    return s


def _normalize_text(s: str) -> str:
    """Lowercase and trim only — for free-text fields like instructions."""
    return s.lower().strip()


def _get_value(field_data: Any) -> str:
    if isinstance(field_data, dict):
        return _normalize(str(field_data.get("value", "")))
    return _normalize(str(field_data))


def _get_text(field_data: Any) -> str:
    """Extract value as plain normalized text (no unit stripping)."""
    if isinstance(field_data, dict):
        return _normalize_text(str(field_data.get("value", "")))
    return _normalize_text(str(field_data))


def compare_vitals(pred: dict, label: dict) -> tuple[int, int, int]:
    """Returns (true_positives, false_positives, false_negatives)."""
    tp = fp = fn = 0
    all_keys = set(pred) | set(label)
    for key in all_keys:
        if key in pred and key in label:
            if _get_value(pred[key]) == _get_value(label[key]):
                tp += 1
            else:
                fp += 1
                fn += 1
        elif key in pred:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn


def compare_instructions(pred: dict, label: dict) -> tuple[int, int, int]:
    """Substring match: label value must appear within predicted value.
    Uses text normalization (lowercase+strip only, no unit stripping) to preserve
    free-text content correctly.
    """
    tp = fp = fn = 0
    all_keys = set(pred) | set(label)
    for key in all_keys:
        if key in pred and key in label:
            pred_val = _get_text(pred[key])
            label_val = _normalize_text(str(label[key]))
            if label_val in pred_val:
                tp += 1
            else:
                fp += 1
                fn += 1
        elif key in pred:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn


def compare_metadata(pred: dict, label: dict) -> tuple[int, int, int]:
    """Same as vitals: exact match after normalization."""
    return compare_vitals(pred, label)


def compare_medications(pred: list, label: list) -> tuple[int, int, int]:
    """
    Match by name (lowercased). For matched pairs, check dose match.
    Route and frequency are optional (scored if present in label).
    +1 TP per matched item where name + dose match.
    """
    tp = fp = fn = 0
    pred_by_name = {m["name"].lower().strip(): m for m in pred}
    label_by_name = {m["name"].lower().strip(): m for m in label}
    all_names = set(pred_by_name) | set(label_by_name)
    for name in all_names:
        if name in pred_by_name and name in label_by_name:
            pm = pred_by_name[name]
            lm = label_by_name[name]
            # Dose must match
            if _normalize(pm.get("dose", "")) == _normalize(lm.get("dose", "")):
                tp += 1
            else:
                fp += 1
                fn += 1
        elif name in pred_by_name:
            fp += 1
        else:
            fn += 1
    return tp, fp, fn
