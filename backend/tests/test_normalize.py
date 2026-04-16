import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.normalize import normalize_output

RAW_VITALS = {
    "blood_pressure": {"value": "140/90", "span": [10, 20], "source": "regex", "confidence": 1.0},
}
RAW_MEDS = [{"name": "lisinopril", "dose": "10 mg", "route": "PO", "frequency": "daily",
              "span": [30, 40], "source": "medspacy", "confidence": 0.9}]
RAW_INSTR = {
    "follow_up": {"value": "See Dr. Smith in 2 weeks.", "span": [50, 75], "source": "section", "confidence": 0.9}
}
RAW_META = {"patient_name": {"value": "John Doe", "span": [0, 8], "source": "regex", "confidence": 0.9}}

def test_output_has_required_keys():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert "pipeline_version" in out
    assert "vitals" in out
    assert "medications" in out
    assert "instructions" in out
    assert "metadata" in out

def test_pipeline_version_stamped():
    out = normalize_output("0.2.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert out["pipeline_version"] == "0.2.0"

def test_vitals_preserved():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert out["vitals"]["blood_pressure"]["value"] == "140/90"

def test_medications_list():
    out = normalize_output("0.1.0", RAW_VITALS, RAW_MEDS, RAW_INSTR, RAW_META)
    assert isinstance(out["medications"], list)
    assert out["medications"][0]["name"] == "lisinopril"
