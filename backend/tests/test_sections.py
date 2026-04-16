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


DISCHARGE_SUMMARY = """
Discharge Medications:
lisinopril 10 mg PO daily

Hospital Course:
Patient admitted for pneumonia, improved on antibiotics.

Impression:
Pneumonia, resolving.

A/P:
Continue antibiotics.

Plan:
Follow up in 1 week.
Return to ER for worsening symptoms.
"""

SOAP_NOTE = """
CC:
Shortness of breath.

Objective:
BP 130/80. HR 88.

Assessment and Plan:
Hypertension, controlled.
"""

def test_detects_discharge_medications():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "medications" for s in sections)

def test_detects_hospital_course():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "hpi" for s in sections)

def test_detects_impression():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "assessment_plan" for s in sections)

def test_detects_ap_shorthand():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "assessment_plan" for s in sections)

def test_detects_plan_as_own_category():
    sections = detect_sections(DISCHARGE_SUMMARY)
    assert any(s["category"] == "plan" for s in sections)

def test_soap_objective_maps_to_vitals():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "vitals" for s in sections)

def test_soap_cc_maps_to_chief_complaint():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "chief_complaint" for s in sections)

def test_soap_assessment_and_plan():
    sections = detect_sections(SOAP_NOTE)
    assert any(s["category"] == "assessment_plan" for s in sections)


# --- Additional alias coverage tests ---

def test_home_medications_alias():
    sections = detect_sections("Home Medications:\nlisinopril 10 mg PO daily")
    assert any(s["category"] == "medications" for s in sections)

def test_current_medications_alias():
    sections = detect_sections("Current Medications:\nlisinopril 10 mg PO daily")
    assert any(s["category"] == "medications" for s in sections)

def test_meds_alias():
    sections = detect_sections("Meds:\nlisinopril 10 mg PO daily")
    assert any(s["category"] == "medications" for s in sections)

def test_interval_history_alias():
    sections = detect_sections("Interval History:\nPatient improved.")
    assert any(s["category"] == "hpi" for s in sections)

def test_reason_for_visit_alias():
    sections = detect_sections("Reason for Visit:\nChest pain.")
    assert any(s["category"] == "chief_complaint" for s in sections)

def test_physical_exam_alias():
    sections = detect_sections("Physical Exam:\nBP 130/80.")
    assert any(s["category"] == "vitals" for s in sections)

def test_vital_signs_alias():
    sections = detect_sections("Vital Signs:\nBP 130/80.")
    assert any(s["category"] == "vitals" for s in sections)

def test_when_to_return_alias():
    sections = detect_sections("When to Return:\nReturn if fever develops.")
    assert any(s["category"] == "return_precautions" for s in sections)

def test_follow_up_hyphen_alias():
    sections = detect_sections("Follow-up:\nSee your doctor in 2 weeks.")
    assert any(s["category"] == "follow_up" for s in sections)

def test_problem_list_alias():
    sections = detect_sections("Problem List:\n1. Hypertension")
    assert any(s["category"] == "assessment_plan" for s in sections)
