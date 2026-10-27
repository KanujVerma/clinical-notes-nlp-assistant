import pytest
from evaluation.strict_evaluator import (
    compare_strict_medications,
    compare_strict_vitals,
    compare_strict_instructions,
    calculate_metrics,
)


def test_strict_medications_preserves_duplicates():
    # Two instances of Lisinopril with different doses
    preds = [
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "morning"},
        {"name": "Lisinopril", "dose": "20 mg", "route": "PO", "frequency": "evening"},
    ]
    labels = [
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "morning"},
        {"name": "Lisinopril", "dose": "20 mg", "route": "PO", "frequency": "evening"},
    ]
    res = compare_strict_medications(preds, labels)
    assert res["tp"] == 2
    assert res["fp"] == 0
    assert res["fn"] == 0


def test_strict_medications_detects_missing_duplicate():
    # Only 1 extracted, but label had 2
    preds = [
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "morning"},
    ]
    labels = [
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO", "frequency": "morning"},
        {"name": "Lisinopril", "dose": "20 mg", "route": "PO", "frequency": "evening"},
    ]
    res = compare_strict_medications(preds, labels)
    assert res["tp"] == 1
    assert res["fp"] == 0
    assert res["fn"] == 1


def test_strict_vitals_unit_preservation():
    # 70 kg vs 70 lbs must fail
    pred = {"weight": {"value": "70", "unit": "kg"}}
    label = {"weight": {"value": "70", "unit": "lbs"}}
    res = compare_strict_vitals(pred, label)
    assert res["tp"] == 0
    assert res["fp"] == 1
    assert res["fn"] == 1


def test_strict_vitals_matching_units():
    pred = {"weight": {"value": "70", "unit": "kg"}}
    label = {"weight": {"value": "70", "unit": "kg"}}
    res = compare_strict_vitals(pred, label)
    assert res["tp"] == 1
    assert res["fp"] == 0
    assert res["fn"] == 0


def test_zero_support_behavior():
    metrics = calculate_metrics(0, 0, 0)
    assert metrics["support"] == 0
    assert not metrics["has_support"]
    assert metrics["precision"] is None
    assert metrics["recall"] is None
    assert metrics["f1"] is None
