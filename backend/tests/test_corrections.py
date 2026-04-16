import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.corrections import compute_correction_count

def test_no_corrections_when_identical():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, ext) == 0

def test_counts_changed_vital():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"bp": {"value": "130/85"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_counts_added_field():
    ext = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_counts_removed_field():
    ext = {"vitals": {"bp": {"value": "120/80"}}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1

def test_medication_dose_change_is_one():
    ext = {"vitals": {}, "medications": [{"name": "metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"}], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [{"name": "metformin", "dose": "1000 mg", "route": "PO", "frequency": "BID"}], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1  # Not 2

def test_medication_added_is_one():
    ext = {"vitals": {}, "medications": [], "instructions": {}, "metadata": {}}
    val = {"vitals": {}, "medications": [{"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily"}], "instructions": {}, "metadata": {}}
    assert compute_correction_count(ext, val) == 1
