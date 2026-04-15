import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.sections import detect_sections

NOTE = """
DISCHARGE INSTRUCTIONS:
Take lisinopril 10mg daily.

FOLLOW UP:
See your doctor in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain worsens.
"""

def test_detects_discharge_section():
    sections = detect_sections(NOTE)
    assert any(s["category"] == "discharge_instructions" for s in sections)

def test_detects_follow_up_section():
    sections = detect_sections(NOTE)
    assert any(s["category"] == "follow_up" for s in sections)

def test_section_has_text():
    sections = detect_sections(NOTE)
    dis = next(s for s in sections if s["category"] == "discharge_instructions")
    assert len(dis["text"]) > 0

def test_no_sections_returns_empty():
    sections = detect_sections("This note has no headers.")
    assert isinstance(sections, list)
