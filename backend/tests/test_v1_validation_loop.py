"""Deterministic failure-to-correction loop for the v1 synthetic fixture.

The injected decimal/quote error is a controlled counterexample. It is not
an extractor prediction.
"""
import copy
import json
from pathlib import Path

from extractors.pipeline import run_pipeline
from validation.checker import check_extraction

ROOT = Path(__file__).resolve().parents[2]
NOTE_PATH = ROOT / "data" / "validation_loop" / "v1_synthetic_note.txt"
INJECTION_PATH = ROOT / "data" / "validation_loop" / "v1_injected_counterexample.json"


def _note() -> str:
    return NOTE_PATH.read_text(encoding="utf-8")


def _issues(text: str, payload: dict) -> set[str]:
    import hashlib
    revision = {"raw_text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    return {issue.issue_code for issue in check_extraction(revision, {"structured_data": payload})}


def test_fixture_extracts_distinct_occurrences_and_checker_flags_real_conflicts():
    text = _note()
    extracted = run_pipeline(text)
    meds = extracted["medications"]
    metformin = [med for med in meds if med["name"] == "metformin"]
    assert [med["dose"] for med in metformin] == ["500 mg", "1000 mg"]
    assert [med["frequency"] for med in metformin] == ["BID", "nightly"]
    warfarin = next(med for med in meds if med["name"] == "warfarin")
    assert warfarin["dose"] == "2.5 mg"
    held = next(med for med in meds if med["name"] == "lisinopril")
    assert held["action"] == "hold"
    assert extracted["vitals"]["blood_pressure"]["value"] == "128/76"
    assert "Follow up" in extracted["instructions"]["follow_up"]["value"]

    codes = _issues(text, extracted)
    assert "A02_DUPLICATE_MEDICATION_CONFLICT" in codes
    assert "A10_NON_ACTIVE_MEDICATION" in codes
    assert "A09_DECIMAL_DOSE_LEADING_ZERO_MISSING" not in codes
    assert "A08_EVIDENCE_QUOTE_MISMATCH" not in codes


def test_injected_counterexample_is_labeled_and_independently_detected():
    spec = json.loads(INJECTION_PATH.read_text(encoding="utf-8"))
    assert spec["not_an_extractor_output"] is True
    assert spec["label"] == "controlled_engineering_counterexample"
    text = _note()
    original = run_pipeline(text)
    planted = copy.deepcopy(original)
    warfarin = next(med for med in planted["medications"] if med["name"] == "warfarin")
    start, end = warfarin["span"]
    assert text[start:end] == "warfarin 2.5 mg PO daily"
    warfarin["dose"] = ".5 mg"
    warfarin["evidence"] = {"start": start, "end": end, "raw_quote": "25 mg"}

    codes = _issues(text, planted)
    assert set(spec["expected_issue_codes"]) <= codes
    assert _issues(text, original).isdisjoint({"A08_EVIDENCE_QUOTE_MISMATCH", "A09_DECIMAL_DOSE_LEADING_ZERO_MISSING"})
