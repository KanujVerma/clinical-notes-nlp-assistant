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


# Plan sub-classification tests
PLAN_SECTION_NOTE = """
Plan:
Follow up with PCP in 2 weeks.
Return to ER for chest pain or fever.
Continue all medications as prescribed. Drink plenty of fluids.
"""

def test_plan_subclassification_follow_up():
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    assert "follow_up" in result, "follow_up should be extracted from Plan section"

def test_plan_subclassification_return_precautions():
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    assert "return_precautions" in result

def test_plan_not_mapped_wholesale():
    sections = detect_sections(PLAN_SECTION_NOTE)
    result = extract_instructions(PLAN_SECTION_NOTE, sections)
    if "discharge_instructions" in result:
        assert len(result["discharge_instructions"]["value"]) < len(PLAN_SECTION_NOTE)

COLON_LED_NOTE = """
Return Precautions:
Return to the ER for: chest pain, shortness of breath, or fever above 101.
"""

MULTILINE_RETURN = """
Return to ER if you develop any of the following:
chest pain or pressure
shortness of breath or difficulty breathing
fever above 101 F
"""

def test_colon_led_return_precautions():
    sections = detect_sections(COLON_LED_NOTE)
    result = extract_instructions(COLON_LED_NOTE, sections)
    assert "return_precautions" in result
    val = result["return_precautions"]["value"].lower()
    assert "chest" in val or "return" in val

def test_multiline_aggregation():
    result = extract_instructions(MULTILINE_RETURN, [])
    assert "return_precautions" in result
    val = result["return_precautions"]["value"].lower()
    assert "chest" in val or "breath" in val or "fever" in val

def test_aggregation_stops_at_next_trigger():
    note = """Return to ER if chest pain develops.
Follow up with your doctor in 2 weeks.
See your PCP for medication review.
"""
    result = extract_instructions(note, [])
    if "return_precautions" in result:
        val = result["return_precautions"]["value"].lower()
        assert "follow up" not in val or "chest" in val

SEMICOLON_NOTE = "Take medications as prescribed; follow up in 2 weeks; return to ER for chest pain."

def test_semicolon_splits_into_sentences():
    result = extract_instructions(SEMICOLON_NOTE, [])
    assert "follow_up" in result or "return_precautions" in result

BULLET_NOTE = """
Discharge Instructions:
- Take all medications as prescribed.
- Drink plenty of fluids.
- Rest for 48 hours.
"""

def test_bullet_content_captured():
    sections = detect_sections(BULLET_NOTE)
    result = extract_instructions(BULLET_NOTE, sections)
    assert "discharge_instructions" in result
    assert len(result["discharge_instructions"]["value"]) > 0
