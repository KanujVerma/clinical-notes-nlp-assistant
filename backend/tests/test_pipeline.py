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


ELEANOR_PRICE = """SOAP NOTE

Name: Eleanor Price
Date: 2025-03-04
Doctor: Dr. Jason Liu

O:
BP 102/64
HR: 96
T 99.3 F
Resp 18
SpO2 97% RA
Wt 146 lb

Current Medications:
1. Albuterol inhaler 2 puffs q6h PRN wheezing
2. Azithromycin 250 mg PO daily for 3 more days
3. Lisinopril 10 mg PO daily
4. Benzonatate 100 mg PO TID as needed for cough

A/P:
Encourage fluids and slow position changes. Continue nitrofurantoin 100 mg BID for 3 more days.
Hold lisinopril tomorrow if systolic BP remains under 100. Continue metformin 500 mg PO BID.
May use ondansetron 4 mg q8h PRN nausea.
RTC with PCP in 2-3 days if not improving.
Go to the ER for fainting, chest pain, worsening weakness, inability to keep fluids down.
"""

def test_eleanor_nitrofurantoin_not_misparsed_as_lisinopril():
    """Continue nitrofurantoin 100 mg BID must NOT bind dose to lisinopril."""
    out = run_pipeline(ELEANOR_PRICE)
    names = [m["name"].lower() for m in out["medications"]]
    # nitrofurantoin should be present
    assert any("nitrofurantoin" in n for n in names)
    # lisinopril should not have dose=100mg (cross-sentence contamination)
    for m in out["medications"]:
        if "lisinopril" in m["name"].lower():
            assert m.get("dose", "") != "100 mg", \
                "lisinopril incorrectly bound to nitrofurantoin's 100 mg dose"

def test_eleanor_ondansetron_extracted():
    """May use ondansetron 4 mg q8h PRN nausea must be captured from A/P prose."""
    out = run_pipeline(ELEANOR_PRICE)
    names = [m["name"].lower() for m in out["medications"]]
    assert any("ondansetron" in n for n in names)
    ond = next((m for m in out["medications"] if "ondansetron" in m["name"].lower()), None)
    assert ond is not None
    assert ond.get("dose") == "4 mg"
    assert "q8h" in ond.get("frequency", "").lower() or "8h" in ond.get("frequency", "").lower()

def test_eleanor_rtc_captured_as_follow_up():
    """RTC with PCP in 2-3 days if not improving should map to follow_up."""
    out = run_pipeline(ELEANOR_PRICE)
    assert "follow_up" in out["instructions"]
    assert "rtc" in out["instructions"]["follow_up"]["value"].lower() \
        or "pcp" in out["instructions"]["follow_up"]["value"].lower() \
        or "improving" in out["instructions"]["follow_up"]["value"].lower()

def test_eleanor_return_precautions_captured():
    """Go to the ER for... should be captured as return_precautions."""
    out = run_pipeline(ELEANOR_PRICE)
    assert "return_precautions" in out["instructions"]

def test_eleanor_patient_name():
    out = run_pipeline(ELEANOR_PRICE)
    assert out["metadata"]["patient_name"]["value"] == "Eleanor Price"

def test_eleanor_provider_name():
    out = run_pipeline(ELEANOR_PRICE)
    assert "Liu" in out["metadata"]["provider_name"]["value"]


HAROLD_BENNETT = """FOLLOW-UP NOTE

Patient: Harold Bennett
Date Seen: 2025-04-02
Provider: Dr. Nina Shah

HPI:
68-year-old male returning for follow-up. Still having burning with urination and fatigue,
though dizziness is better. No CP, no SOB, no syncope. He says he is taking tamsulosin nightly.
Also using zofran as needed for nausea.

Vital Signs
BP 118/70
Pulse 90 bpm
Temp 100.1 F
Resp 19
O2 sat 96% RA
Wt 164 lb

Plan
Continue ciprofloxacin 500 mg PO BID x 2 more days.
Continue tamsulosin 0.4 mg qhs.
May use ondansetron 4 mg q8h PRN nausea.
Push oral fluids and avoid sudden position changes.
See PCP in 3 days if symptoms do not resolve.
Return to ER for fever > 101.5, vomiting, inability to urinate, worsening weakness.
"""

def test_harold_follow_up_not_narrative_hpi():
    """HPI 'returning for follow-up' must NOT be captured as follow-up instruction."""
    out = run_pipeline(HAROLD_BENNETT)
    fu = out["instructions"].get("follow_up", {})
    value = fu.get("value", "")
    assert "returning for follow-up" not in value.lower(), \
        f"Narrative HPI text captured as follow-up: {value!r}"

def test_harold_follow_up_is_plan_instruction():
    """'See PCP in 3 days if symptoms do not resolve' should be the follow-up."""
    out = run_pipeline(HAROLD_BENNETT)
    assert "follow_up" in out["instructions"]
    value = out["instructions"]["follow_up"]["value"]
    assert "pcp" in value.lower() or "3 days" in value.lower() or "resolve" in value.lower()

def test_harold_ciprofloxacin_extracted():
    out = run_pipeline(HAROLD_BENNETT)
    names = [m["name"].lower() for m in out["medications"]]
    assert any("cipro" in n for n in names)

def test_harold_return_precautions():
    out = run_pipeline(HAROLD_BENNETT)
    assert "return_precautions" in out["instructions"]
