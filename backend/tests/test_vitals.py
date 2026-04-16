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


# New format variants
VARIANTS = """
Blood Pressure 142/88 mmHg
Pulse: 78 bpm
T: 98.6 F
Resp Rate: 18 breaths/min
O2 Sat 96% on room air
Weight: 185 lb
"""

ABBREVIATED = "BP 142/88. HR 78 bpm. T 98.6 F. RR 18. SpO2 96% RA. Wt 185 lb."

def test_blood_pressure_variant_with_mmhg():
    v = extract_vitals(VARIANTS)
    assert "blood_pressure" in v
    assert v["blood_pressure"]["value"].startswith("142/88")

def test_pulse_alias():
    v = extract_vitals(VARIANTS)
    assert "heart_rate" in v
    assert v["heart_rate"]["value"] == "78"

def test_temperature_T_abbreviation():
    v = extract_vitals(ABBREVIATED)
    assert "temperature" in v
    assert "98.6" in v["temperature"]["value"]

def test_respiratory_rate_resp_rate_alias():
    v = extract_vitals(VARIANTS)
    assert "respiratory_rate" in v
    assert v["respiratory_rate"]["value"] == "18"

def test_oxygen_saturation_o2_sat_alias():
    v = extract_vitals(VARIANTS)
    assert "oxygen_saturation" in v
    assert "96" in v["oxygen_saturation"]["value"]

def test_weight_lb_unit():
    v = extract_vitals(VARIANTS)
    assert "weight" in v
    assert "185" in v["weight"]["value"]

def test_abbreviated_vitals_all_extracted():
    v = extract_vitals(ABBREVIATED)
    for field in ["blood_pressure", "heart_rate", "temperature",
                  "respiratory_rate", "oxygen_saturation", "weight"]:
        assert field in v, f"Missing: {field}"

def test_respiratory_rate_breaths_per_min_standalone():
    v = extract_vitals("18 breaths/min")
    assert "respiratory_rate" in v
    assert v["respiratory_rate"]["value"] == "18"
