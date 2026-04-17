import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.metadata import extract_metadata

NOTE_WITH_META = """
Patient: John Doe
Date of Service: 2024-01-15
Provider: Dr. Jane Smith

Chief complaint: chest pain.
"""

def test_extracts_patient_name():
    m = extract_metadata(NOTE_WITH_META)
    assert m["patient_name"]["value"] == "John Doe"

def test_extracts_date_of_service():
    m = extract_metadata(NOTE_WITH_META)
    assert m["date_of_service"]["value"] == "2024-01-15"

def test_extracts_provider():
    m = extract_metadata(NOTE_WITH_META)
    assert "Smith" in m["provider_name"]["value"]

def test_no_metadata_returns_empty():
    m = extract_metadata("This note has no metadata headers.")
    assert len(m) == 0

def test_partial_metadata_ok():
    m = extract_metadata("Patient: Jane Doe\nNo other headers.")
    assert "patient_name" in m
    assert "date_of_service" not in m

def test_patient_name_alias():
    m = extract_metadata("Patient Name: Jane Smith\nDate of Service: 2024-01-01")
    assert m["patient_name"]["value"] == "Jane Smith"

def test_pt_abbreviation():
    m = extract_metadata("Pt: Jane Smith")
    assert m["patient_name"]["value"] == "Jane Smith"

def test_date_seen_alias():
    m = extract_metadata("Date Seen: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_visit_date_alias():
    m = extract_metadata("Visit Date: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_dos_alias():
    m = extract_metadata("DOS: 2024-03-15")
    assert m["date_of_service"]["value"] == "2024-03-15"

def test_attending_alias():
    m = extract_metadata("Attending: Dr. Sarah Chen")
    assert "Chen" in m["provider_name"]["value"]

def test_clinician_alias():
    m = extract_metadata("Clinician: Dr. Sarah Chen")
    assert "Chen" in m["provider_name"]["value"]

def test_john_smith_note():
    note = "Patient: John Smith\nDate of Service: 2024-03-15\nProvider: Dr. Sarah Chen"
    m = extract_metadata(note)
    assert m["patient_name"]["value"] == "John Smith"
    assert m["date_of_service"]["value"] == "2024-03-15"
    assert "Chen" in m["provider_name"]["value"]

def test_name_alias():
    m = extract_metadata("Name: Robert Lee\nDate Seen: 2025-01-14")
    assert m["patient_name"]["value"] == "Robert Lee"

def test_physician_alias():
    m = extract_metadata("Physician: Dr. Anita Morris")
    assert "Morris" in m["provider_name"]["value"]
