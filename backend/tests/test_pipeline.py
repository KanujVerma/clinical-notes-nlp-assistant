import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.pipeline import run_pipeline

NOTE = """Patient: Jane Doe
Date of Service: 2024-03-10



Vitals: BP 132/84. HR: 80. Temp 98.4F. RR 14. SpO2: 97%. Wt 160 lbs.

Medications:
- lisinopril 10 mg PO daily
- metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take all medications as prescribed. Avoid strenuous activity for 1 week.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain, shortness of breath, or fever > 101F.
"""

def test_pipeline_returns_dict():
    out = run_pipeline(NOTE)
    assert isinstance(out, dict)

def test_pipeline_has_version():
    out = run_pipeline(NOTE)
    assert "pipeline_version" in out

def test_pipeline_extracts_bp():
    out = run_pipeline(NOTE)
    assert "blood_pressure" in out["vitals"]

def test_pipeline_extracts_medications():
    out = run_pipeline(NOTE)
    names = [m["name"] for m in out["medications"]]
    assert "lisinopril" in names

def test_pipeline_extracts_follow_up():
    out = run_pipeline(NOTE)
    assert "follow_up" in out["instructions"]

def test_pipeline_extracts_metadata():
    out = run_pipeline(NOTE)
    assert "patient_name" in out["metadata"]

def test_spans_are_raw_offsets():
    out = run_pipeline(NOTE)
    bp = out["vitals"]["blood_pressure"]
    start, end = bp["span"]
    assert "132" in NOTE[start:end] or "84" in NOTE[start:end]

JOHN_SMITH = """DISCHARGE SUMMARY

Patient: John Smith
Date of Service: 2024-03-15
Provider: Dr. Sarah Chen

Vitals:
BP: 142/88 mmHg
HR: 78 bpm
Temp: 98.6 F
RR: 18 breaths/min
SpO2: 96% on room air
Weight: 185 lb

Medications:
Lisinopril 10 mg PO daily
Metformin 500 mg PO BID
Albuterol inhaler 2 puffs q6h PRN wheezing

Discharge Instructions:
Drink plenty of fluids and rest as needed.
Use albuterol inhaler as directed for wheezing or shortness of breath.
Continue home medications as listed above.

Follow Up:
Follow up with primary care physician in 2 weeks.

Return Precautions:
Return to the ER for chest pain, worsening shortness of breath, persistent fever, or inability to tolerate fluids.
"""

HEADERLESS = """Patient feels better after treatment.
Take ibuprofen 400 mg every 8 hours as needed for pain.
Follow up with your doctor in one week.
Return to the ER if symptoms worsen or fever develops.
"""

def test_john_smith_extracts_lisinopril():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert "lisinopril" in names

def test_john_smith_extracts_metformin():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert "metformin" in names

def test_john_smith_extracts_albuterol():
    out = run_pipeline(JOHN_SMITH)
    names = [m["name"].lower() for m in out["medications"]]
    assert any("albuterol" in n for n in names)

def test_john_smith_albuterol_dose():
    out = run_pipeline(JOHN_SMITH)
    alb = next((m for m in out["medications"] if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "puffs" in alb["dose"].lower() or "2" in alb["dose"]

def test_john_smith_albuterol_prn():
    out = run_pipeline(JOHN_SMITH)
    alb = next((m for m in out["medications"] if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "prn" in alb["frequency"].lower() or "q6h" in alb["frequency"].lower()

def test_john_smith_all_vitals():
    out = run_pipeline(JOHN_SMITH)
    for field in ["blood_pressure", "heart_rate", "temperature",
                  "respiratory_rate", "oxygen_saturation", "weight"]:
        assert field in out["vitals"], f"Missing vital: {field}"

def test_john_smith_metadata():
    out = run_pipeline(JOHN_SMITH)
    assert out["metadata"]["patient_name"]["value"] == "John Smith"
    assert out["metadata"]["date_of_service"]["value"] == "2024-03-15"
    assert "Chen" in out["metadata"]["provider_name"]["value"]

def test_john_smith_all_instructions():
    out = run_pipeline(JOHN_SMITH)
    for cat in ["discharge_instructions", "follow_up", "return_precautions"]:
        assert cat in out["instructions"], f"Missing instruction: {cat}"

def test_headerless_fallback_follow_up():
    out = run_pipeline(HEADERLESS)
    assert "follow_up" in out["instructions"]

def test_headerless_fallback_return_precautions():
    out = run_pipeline(HEADERLESS)
    assert "return_precautions" in out["instructions"]
