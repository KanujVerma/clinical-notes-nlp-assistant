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
