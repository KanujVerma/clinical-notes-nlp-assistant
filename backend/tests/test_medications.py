import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.medications import extract_medications

NOTE_SIMPLE = "Patient takes lisinopril 10 mg PO daily for hypertension."
NOTE_NEGATED = "Patient is NOT taking metformin. Denies use of atorvastatin."
NOTE_MULTI = "Medications: albuterol 2.5 mg nebulized BID and omeprazole 20 mg PO QHS."

def test_extracts_medication_name():
    meds = extract_medications(NOTE_SIMPLE)
    assert len(meds) >= 1
    names = [m["name"] for m in meds]
    assert "lisinopril" in names

def test_extracts_dose():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["dose"] == "10 mg"

def test_extracts_route():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["route"].upper() == "PO"

def test_extracts_frequency():
    meds = extract_medications(NOTE_SIMPLE)
    lis = next(m for m in meds if m["name"] == "lisinopril")
    assert lis["frequency"].lower() == "daily"

def test_negated_medication_excluded():
    meds = extract_medications(NOTE_NEGATED)
    names = [m["name"] for m in meds]
    assert "metformin" not in names
    assert "atorvastatin" not in names

def test_multiple_medications():
    meds = extract_medications(NOTE_MULTI)
    names = [m["name"] for m in meds]
    assert "albuterol" in names
    assert "omeprazole" in names

def test_returns_list():
    meds = extract_medications("No medications here.")
    assert isinstance(meds, list)
