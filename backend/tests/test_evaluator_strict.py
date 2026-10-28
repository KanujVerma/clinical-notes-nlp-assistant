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


def test_duplicate_pairing_does_not_optimize_correct_dose():
    # Without source occurrence IDs/evidence, pair by occurrence order. The
    # old comparator matched exact attributes first and falsely reported 2 TP.
    preds = [
        {"name": "Lisinopril", "dose": "20 mg", "route": "PO"},
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO"},
    ]
    gold = [
        {"name": "Lisinopril", "dose": "10 mg", "route": "PO"},
        {"name": "Lisinopril", "dose": "20 mg", "route": "PO"},
    ]
    r = compare_strict_medications(preds, gold)
    assert (r["tp"], r["fp"], r["fn"]) == (0, 2, 2)
    assert [(p["pred_idx"], p["label_idx"]) for p in r["pairs"]] == [(0, 0), (1, 1)]
    assert r["matching_ambiguities"]


def test_explicit_occurrence_identity_beats_array_order():
    preds = [
        {"name": "Lisinopril", "dose": "20 mg", "source_occurrence_id": "second"},
        {"name": "Lisinopril", "dose": "10 mg", "source_occurrence_id": "first"},
    ]
    gold = [
        {"name": "Lisinopril", "dose": "10 mg", "source_occurrence_id": "first"},
        {"name": "Lisinopril", "dose": "20 mg", "source_occurrence_id": "second"},
    ]
    r = compare_strict_medications(preds, gold)
    assert (r["tp"], r["fp"], r["fn"]) == (2, 0, 0)
    assert [(p["pred_idx"], p["label_idx"]) for p in r["pairs"]] == [(1, 0), (0, 1)]


def test_strict_record_rejects_wrong_route_with_same_name_and_dose():
    r = compare_strict_medications(
        [{"name": "Drug A", "dose": "5 mg", "route": "IV"}],
        [{"name": "Drug A", "dose": "5 mg", "route": "PO"}],
    )
    assert (r["tp"], r["fp"], r["fn"]) == (0, 1, 1)
    assert r["attribute_counts"]["route"] == {
        "tp": 0, "fp": 1, "fn": 1, "excluded_unannotated": 0,
    }


def test_missing_annotation_does_not_count_as_gold_correctness():
    r = compare_strict_medications(
        [{"name": "Drug A", "dose": "5 mg", "route": "PO"}],
        [{"name": "Drug A", "dose": "5 mg"}],
    )
    assert r["attribute_counts"]["route"]["excluded_unannotated"] == 1
    assert r["contract"] == "strict_annotated_record_source_first_v3"
