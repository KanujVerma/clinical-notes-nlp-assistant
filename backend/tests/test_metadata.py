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
