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


# ---- Structured line parser tests ----

SECTION_NOTE = """Medications:
- Lisinopril 10 mg PO daily
- Metformin 500 mg PO BID
- Albuterol inhaler 2 puffs q6h PRN wheezing
"""

SECTION_NOTE_BULLETED = """Home Medications:
\u2022 Atorvastatin 40 mg PO QHS
\u2022 Aspirin 81 mg PO daily
1. Metoprolol 25 mg PO BID
"""

SECTION_NOTE_UPPERCASE = """MEDICATIONS:
LISINOPRIL 10 MG PO DAILY
METFORMIN 500 MG PO BID
"""

SECTION_NO_ROUTE = """Medications:
Prednisone 20 mg daily
Ibuprofen 400 mg TID
"""

# ---- Negative tests ----

NEGATIVE_LINES = """Medications:
Continue medications as above
No home meds listed
NKDA
Allergies: penicillin
See medication reconciliation form
"""

def test_section_extracts_lisinopril():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "lisinopril" in names

def test_section_extracts_metformin():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "metformin" in names

def test_section_extracts_albuterol():
    meds = extract_medications(SECTION_NOTE)
    names = [m["name"].lower() for m in meds]
    assert "albuterol" in names or any("albuterol" in n for n in names)

def test_albuterol_puffs_dose():
    meds = extract_medications(SECTION_NOTE)
    alb = next((m for m in meds if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "puffs" in alb["dose"].lower() or "2" in alb["dose"]

def test_albuterol_prn_frequency():
    meds = extract_medications(SECTION_NOTE)
    alb = next((m for m in meds if "albuterol" in m["name"].lower()), None)
    assert alb is not None
    assert "prn" in alb["frequency"].lower() or "q6h" in alb["frequency"].lower()

def test_bulleted_lines_parsed():
    meds = extract_medications(SECTION_NOTE_BULLETED)
    names = [m["name"].lower() for m in meds]
    assert "atorvastatin" in names
    assert "aspirin" in names
    assert "metoprolol" in names

def test_uppercase_med_lines_accepted():
    meds = extract_medications(SECTION_NOTE_UPPERCASE)
    names = [m["name"].lower() for m in meds]
    assert "lisinopril" in names
    assert "metformin" in names

def test_missing_route_still_extracted():
    meds = extract_medications(SECTION_NO_ROUTE)
    names = [m["name"].lower() for m in meds]
    assert "prednisone" in names
    prednisone = next(m for m in meds if "prednisone" in m["name"].lower())
    assert prednisone["dose"] == "20 mg"
    assert prednisone["route"] == ""  # missing is OK

# ---- Negative tests ----

def test_negative_continue_medications():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    assert not any("continue" in n for n in names)
    assert not any("medication" in n for n in names)

def test_negative_no_home_meds():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    assert not any("home" in n for n in names)
    assert not any("listed" in n for n in names)

def test_negative_allergy_line():
    meds = extract_medications(NEGATIVE_LINES)
    names = [m["name"].lower() for m in meds]
    # "penicillin" should not appear as a medication without dose/route/freq
    if "penicillin" in names:
        penicillin = next(m for m in meds if m["name"].lower() == "penicillin")
        # It must have at least one of dose, route, frequency to be a valid med
        assert penicillin["route"] != "" or penicillin["frequency"] != "" or penicillin["dose"] != ""

# ---- Frequency variant tests ----

FREQ_NOTE = """Medications:
- Ibuprofen 400 mg PO every 6 hours
- Amoxicillin 500 mg PO every 8 hours
- Methotrexate 15 mg PO once weekly
- Prednisone 10 mg PO QAM
"""

def test_every_6_hours_frequency():
    meds = extract_medications(FREQ_NOTE)
    ibu = next((m for m in meds if "ibuprofen" in m["name"].lower()), None)
    assert ibu is not None
    assert "6" in ibu["frequency"] or "hour" in ibu["frequency"].lower()

def test_once_weekly_frequency():
    meds = extract_medications(FREQ_NOTE)
    mtx = next((m for m in meds if "methotrexate" in m["name"].lower()), None)
    assert mtx is not None
    assert "week" in mtx["frequency"].lower()

def test_qam_frequency():
    meds = extract_medications(FREQ_NOTE)
    pred = next((m for m in meds if "prednisone" in m["name"].lower()), None)
    assert pred is not None
    assert "qam" in pred["frequency"].lower()
