import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from extractors.vitals import extract_vitals

SIMPLE = "BP: 140/90. HR 78. Temp 98.6F. RR: 16. SpO2 98%. Wt 185 lbs."

def test_extracts_blood_pressure():
    v = extract_vitals(SIMPLE)
    assert v["blood_pressure"]["value"] == "140/90"

def test_extracts_heart_rate():
    v = extract_vitals(SIMPLE)
    assert v["heart_rate"]["value"] == "78"

def test_extracts_temperature():
    v = extract_vitals(SIMPLE)
    assert v["temperature"]["value"] == "98.6"

def test_extracts_respiratory_rate():
    v = extract_vitals(SIMPLE)
    assert v["respiratory_rate"]["value"] == "16"

def test_extracts_oxygen_saturation():
    v = extract_vitals(SIMPLE)
    assert v["oxygen_saturation"]["value"] == "98"

def test_extracts_weight():
    v = extract_vitals(SIMPLE)
    assert v["weight"]["value"] == "185"

def test_missing_vital_not_in_output():
    v = extract_vitals("No vitals here.")
    assert len(v) == 0

def test_confidence_is_float():
    v = extract_vitals(SIMPLE)
    for field in v.values():
        assert isinstance(field["confidence"], float)

def test_span_is_tuple():
    v = extract_vitals(SIMPLE)
    for field in v.values():
        assert isinstance(field["span"], list)
        assert len(field["span"]) == 2
