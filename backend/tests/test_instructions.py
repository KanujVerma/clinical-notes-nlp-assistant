import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.instructions import extract_instructions
from extractors.sections import detect_sections

NOTE_SECTIONED = """
DISCHARGE INSTRUCTIONS:
Take medications as prescribed. Rest for 48 hours.

FOLLOW UP:
See Dr. Smith in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if fever exceeds 101 F or chest pain worsens.
"""

NOTE_NO_SECTIONS = """
Patient should follow up in 2 weeks with their PCP.
Return to ER if shortness of breath develops.
Call the clinic if pain is not improving.
"""

def test_primary_path_discharge():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "discharge_instructions" in result
    assert result["discharge_instructions"]["source"] == "section"
    assert result["discharge_instructions"]["confidence"] == 0.9

def test_primary_path_follow_up():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "follow_up" in result
    assert "smith" in result["follow_up"]["value"].lower()

def test_primary_path_return_precautions():
    sections = detect_sections(NOTE_SECTIONED)
    result = extract_instructions(NOTE_SECTIONED, sections)
    assert "return_precautions" in result
    assert result["return_precautions"]["source"] == "section"

def test_fallback_path_follow_up():
    result = extract_instructions(NOTE_NO_SECTIONS, [])
    assert "follow_up" in result
    assert result["follow_up"]["source"] == "fallback"
    assert result["follow_up"]["confidence"] == 0.6

def test_fallback_path_return():
    result = extract_instructions(NOTE_NO_SECTIONS, [])
    assert "return_precautions" in result

def test_returns_dict():
    result = extract_instructions("No instructions here.", [])
    assert isinstance(result, dict)
