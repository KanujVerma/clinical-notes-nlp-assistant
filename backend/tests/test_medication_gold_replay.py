"""In-sample medication parser regression and frozen inference-replay gates.

These are synthetic development examples, not clinical validation or a
prospectively frozen generalization estimate.
"""
import json
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from evaluation.replay_medication_parser import score_frozen_transcriptions
from extractors.medication_orders import parse_order_line, parse_order_lines
from extractors.pipeline import run_pipeline


MANIFEST = ROOT / "data/vision_gold_30/manifest.json"
REPORT = ROOT / "artifacts/evaluation/paired_local_17f5737320b78e10.json"


@pytest.mark.parametrize(
    "line,name,dose,route,freq,action",
    [
        ("Hold Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "PO", "daily", "hold"),
        ("Do not continue Aspirin 81 mg.", "aspirin", "81 mg", "", "", "stop"),
        ("Start Amlodipine 5 mg PO daily tomorrow.", "amlodipine", "5 mg", "PO", "daily", "start"),
        ("Administer Haloperidol 0.5 mg PO BID PRN agitation.", "haloperidol", "0.5 mg", "PO", "BID PRN", ""),
        ("Fentanyl 25 mcg/hr transdermal patch every 72 hours.", "fentanyl", "25 mcg/hr", "transdermal", "every 72 hours", ""),
        ("Fluticasone/Salmeterol 250/50 mcg inhaled 1 puff BID.", "fluticasone/salmeterol", "250/50 mcg", "inhaled", "BID", ""),
        ("Insulin glargine 20 units SubQ at bedtime.", "insulin glargine", "20 units", "SubQ", "at bedtime", ""),
        ("Lorazepam 0.5 mg PO nightly at bedtime.", "lorazepam", "0.5 mg", "PO", "nightly", ""),
        ("Discharge Meds: Metoprolol Succinate 50 mg PO daily.", "metoprolol succinate", "50 mg", "PO", "daily", ""),
        ("Benzonatate 100 mg PO TID as needed for cough.", "benzonatate", "100 mg", "PO", "TID as needed", ""),
        ("Nitroglycerin 400 mcg SL every 5 minutes PRN chest pain.", "nitroglycerin", "400 mcg", "SL", "every 5 minutes PRN", ""),
        ("Discharge Meds Pantoprazole 40 mg PO daily.", "pantoprazole", "40 mg", "PO", "daily", ""),
        ("Ceftriaxone 1 g IV daily for 7 days.", "ceftriaxone", "1 g", "IV", "daily", ""),
        ("Administer Labetalol 20 mg IV push STAT.", "labetalol", "20 mg", "IV", "STAT", ""),
    ],
)
def test_explicit_orders_keep_exact_fields(line, name, dose, route, freq, action):
    meds = parse_order_lines(line)
    assert len(meds) == 1
    med = meds[0]
    assert (med["name"], med["dose"], med["route"], med["frequency"], med["action"]) == (
        name, dose, route, freq, action
    )
    start, end = med["span"]
    assert 0 <= start < end <= len(line)
    assert line[start:end].casefold().startswith(name)


@pytest.mark.parametrize(
    "line",
    [
        "Do not dispense Warfarin 25 mg.",
        "Caution: do not dispense 0.25 mg.",
        "Verify label says 0.05 mg, never 0.5 mg.",
        "Warning: high risk if taken at 2.5 mg.",
        "Maximum daily dose 2 mg.",
        "Fasting blood glucose 118 mg/dL.",
        "Hemoglobin 13.8 g/dL.",
        "Taper by 5 mg weekly.",
        "Patient takes lisinopril 10 mg PO daily for hypertension.",
        "Hold if excessively sedated.",
        "Do not order 25 mg.",
    ],
)
def test_cautions_labs_and_unanchored_prose_not_new_orders(line):
    assert parse_order_lines(line) == []


def test_multiple_dose_clauses_do_not_cross_bind_route_or_frequency():
    ambiguous = "Metformin 500 mg and Lisinopril 10 mg PO daily."
    assert parse_order_lines(ambiguous) == []
    assert parse_order_lines("Metformin 500 mg PO and Aspirin 1 tablet daily.") == []

    separated = "Metformin 500 mg. Start Lisinopril 10 mg PO daily."
    meds = parse_order_lines(separated)
    assert len(meds) == 1
    assert (meds[0]["name"], meds[0]["dose"], meds[0]["action"]) == (
        "lisinopril", "10 mg", "start"
    )

    two_orders = "Hold Warfarin 2.5 mg PO daily; Start Aspirin 81 mg PO daily."
    meds = parse_order_lines(two_orders)
    assert [(m["name"], m["dose"], m["action"]) for m in meds] == [
        ("warfarin", "2.5 mg", "hold"),
        ("aspirin", "81 mg", "start"),
    ]
    for med in meds:
        start, end = med["span"]
        assert two_orders[start:end].casefold().startswith(med["name"])


def test_ambiguous_ocr_frequency_is_not_silently_corrected():
    # O6H could mean a corrupted Q6H, but the model did not actually
    # transcribe Q; do not invent that high-risk medication schedule.
    med = parse_order_line("Acetaminophen 650 mg PO O6H PRN fever.")
    assert med is not None
    assert med["frequency"] == "PRN"


@pytest.mark.parametrize(
    "negative_line",
    [
        "No metformin 500 mg PO BID.",
        "Not taking warfarin 5 mg PO daily.",
        "Denies aspirin 81 mg PO daily.",
        "Never used lisinopril 10 mg PO daily.",
    ],
)
def test_explicit_and_full_pipeline_reject_negated_medication_histories(negative_line):
    assert parse_order_lines(negative_line) == []
    assert run_pipeline(negative_line)["medications"] == []


@pytest.mark.parametrize(
    "source,name,dose,action",
    [
        ("Medications:\nHold Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "hold"),
        ("Medications:\nDo not continue Aspirin 81 mg.", "aspirin", "81 mg", "stop"),
        ("Medications:\nStart Lisinopril 10 mg PO daily.", "lisinopril", "10 mg", "start"),
    ],
)
def test_action_prefixed_section_same_source_produces_one_record(source, name, dose, action):
    meds = run_pipeline(source)["medications"]
    assert [(m["name"], m["dose"], m.get("action", "")) for m in meds] == [
        (name, dose, action)
    ]


def test_explicit_prn_indication_and_evidence_span_are_preserved():
    text = "Medications:\nAlbuterol inhaler 2 puffs q6h PRN wheezing."
    meds = run_pipeline(text)["medications"]
    assert len(meds) == 1
    med = meds[0]
    assert med["frequency"].casefold() == "q6h prn"
    assert med["qualifier"] == "PRN wheezing"
    a, b = med["span"]
    assert text[a:b].endswith("PRN wheezing")
    assert a < b <= len(text)

    other = run_pipeline("Medications:\nBenzonatate 100 mg PO TID as needed for cough.")["medications"]
    assert len(other) == 1
    assert other[0]["qualifier"] == "as needed for cough"


def test_discrete_occurrence_spans_and_action_scope():
    text = (
        "Hold Warfarin 2.5 mg PO daily.\n"
        "Do not dispense Warfarin 25 mg.\n"
        "Start Amlodipine 5 mg PO daily.\n"
    )
    meds = run_pipeline(text)["medications"]
    assert [(m["name"], m["dose"], m.get("action")) for m in meds] == [
        ("warfarin", "2.5 mg", "hold"),
        ("amlodipine", "5 mg", "start"),
    ]
    for med in meds:
        start, end = med["span"]
        assert med["name"] in text[start:end].casefold()


def test_duplicate_drug_names_remain_separate_with_correct_doses():
    text = (
        "Prednisone 20 mg PO QAM.\n"
        "Prednisone 10 mg PO QPM with dinner.\n"
        "Taper by 5 mg weekly.\n"
    )
    meds = run_pipeline(text)["medications"]
    assert [(m["name"], m["dose"], m["frequency"]) for m in meds] == [
        ("prednisone", "20 mg", "QAM"),
        ("prednisone", "10 mg", "QPM"),
    ]
    assert meds[0]["span"][1] < meds[1]["span"][0]


def test_two_medications_on_one_line_remain_distinct():
    meds = run_pipeline(
        "Medications: albuterol 2.5 mg nebulized BID and omeprazole 20 mg PO QHS."
    )["medications"]
    assert "albuterol" in {m["name"] for m in meds}
    assert "omeprazole" in {m["name"] for m in meds}


def test_gold_vs_saved_ocr_replay_is_real_and_improves_legacy_parser():
    result = score_frozen_transcriptions(MANIFEST, REPORT)
    assert result["is_new_model_run"] is False
    assert result["corpus_role"] == "seen_development_cases_not_independent_holdout"
    assert result["original_model_scores_unchanged"]["glm_ocr"]["tp"] == 6
    assert result["original_model_scores_unchanged"]["tesseract"]["tp"] == 0
    expected_support = 46
    gold = result["results"]["gold_text"]
    glm = result["results"]["glm_ocr"]
    tesseract = result["results"]["tesseract"]
    assert (gold["support"], glm["support"], tesseract["support"]) == (46, 46, 46)
    # Explicit quality gate for gold text. We do not count this as independent
    # validation and must not use it to choose clinical automation thresholds.
    assert gold["f1"] >= 0.80
    assert glm["f1"] > result["original_model_scores_unchanged"]["glm_ocr"]["f1"]
    assert tesseract["f1"] > result["original_model_scores_unchanged"]["tesseract"]["f1"]


def test_replay_fails_closed_on_tampered_source_binding(tmp_path):
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["cases"]["glm_ocr"][0]["source_sha256"] = "0" * 64
    tampered = tmp_path / "altered_results.json"
    tampered.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="MEDICATION_REPLAY_SOURCE_MISMATCH"):
        score_frozen_transcriptions(MANIFEST, tampered)


def test_replay_fails_closed_if_frozen_manifest_is_modified(tmp_path):
    report = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report["cases"][0]["expected_medications"][0]["dose"] = "1000 mg"
    tampered = tmp_path / "altered_manifest.json"
    tampered.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        score_frozen_transcriptions(tampered, REPORT)
