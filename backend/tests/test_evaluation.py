import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from evaluation.compare import compare_vitals, compare_medications, compare_instructions
from evaluation.metrics import compute_metrics

# ------- compare_vitals -------
PRED_VITALS = {
    "blood_pressure": {"value": "138/88", "source": "regex", "confidence": 1.0, "span": [0, 10]},
    "heart_rate":     {"value": "82",      "source": "regex", "confidence": 1.0, "span": [11, 20]},
    "weight":         {"value": "172 lbs", "source": "regex", "confidence": 1.0, "span": [21, 30]},
}
LABEL_VITALS = {
    "blood_pressure": "138/88",
    "heart_rate": "82",
    "temperature": "98.8",   # in label but not in pred
    "weight": "172 lbs",
}

def test_compare_vitals_correct_match():
    tp, fp, fn = compare_vitals(PRED_VITALS, LABEL_VITALS)
    assert tp == 3  # bp, hr, weight all match
    assert fp == 0
    assert fn == 1  # temperature in label but not in pred

def test_compare_vitals_unit_stripping():
    pred = {"weight": {"value": "185 lbs"}}
    label = {"weight": "185 lbs"}
    tp, fp, fn = compare_vitals(pred, label)
    assert tp == 1
    assert fn == 0

def test_compare_vitals_no_predictions():
    tp, fp, fn = compare_vitals({}, {"blood_pressure": "120/80"})
    assert tp == 0
    assert fn == 1

# ------- compare_medications -------
PRED_MEDS = [
    {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    {"name": "metformin",  "dose": "500 mg", "route": "PO", "frequency": "BID"},
]
LABEL_MEDS = [
    {"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"},
    {"name": "metformin",  "dose": "500 mg", "route": "PO", "frequency": "BID"},
    {"name": "atorvastatin", "dose": "20 mg", "route": "PO", "frequency": "daily"},
]

def test_compare_medications_correct():
    tp, fp, fn = compare_medications(PRED_MEDS, LABEL_MEDS)
    assert tp == 2
    assert fn == 1  # atorvastatin missing from pred

def test_compare_medications_empty_pred():
    tp, fp, fn = compare_medications([], LABEL_MEDS)
    assert tp == 0
    assert fn == 3

# ------- compute_metrics -------
def test_compute_metrics_perfect():
    m = compute_metrics(tp=5, fp=0, fn=0)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0

def test_compute_metrics_no_predictions():
    m = compute_metrics(tp=0, fp=0, fn=5)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0
