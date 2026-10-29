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
from validation.checker import check_extraction


MANIFEST = ROOT / "data/vision_gold_30/manifest.json"
REPORT = ROOT / "artifacts/evaluation/paired_local_17f5737320b78e10.json"


@pytest.mark.parametrize(
    "line,name,dose,route,freq,action",
    [
        ("Continue to hold Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "PO", "daily", "hold"),
        ("Stop taking Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "PO", "daily", "stop"),
        ("Continue taking Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "PO", "daily", "continue"),
        ("Hold Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "PO", "daily", "hold"),
        ("Do not continue Aspirin 81 mg.", "aspirin", "81 mg", "", "", "stop"),
        ("Start Amlodipine 5 mg PO daily tomorrow.", "amlodipine", "5 mg", "PO", "daily", "start"),
        ("Administer Haloperidol 0.5 mg PO BID PRN agitation.", "haloperidol", "0.5 mg", "PO", "BID PRN", ""),
        ("Fentanyl 25 mcg/hr transdermal patch every 72 hours.", "fentanyl", "25 mcg/hr", "transdermal", "every 72 hours", ""),
        ("Fluticasone/Salmeterol 250/50 mcg inhaled 1 puff BID.", "fluticasone/salmeterol", "250/50 mcg", "inhaled", "BID", ""),
        ("Insulin glargine 20 units SubQ at bedtime.", "insulin glargine", "20 units", "SubQ", "at bedtime", ""),
        ("Lorazepam 0.5 mg PO nightly at bedtime.", "lorazepam", "0.5 mg", "PO", "nightly", ""),
        ("Discharge Meds: Metoprolol Succinate 50 mg PO daily.", "metoprolol succinate", "50 mg", "PO", "daily", ""),
        ("Metformin BID 500 mg PO.", "metformin", "500 mg", "PO", "BID", ""),
        ("Metformin PO BID 500 mg.", "metformin", "500 mg", "PO", "BID", ""),
        ("Insulin glargine 20 units SQ bedtime.", "insulin glargine", "20 units", "SQ", "bedtime", ""),
        ("Metformin PO 500 mg BID.", "metformin", "500 mg", "PO", "BID", ""),
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
        "Weight gain 20 g daily.",
        "Weight increased 5 g daily.",
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
    # Verify that the older section-line fallback cannot reintroduce a
    # negated order after the explicit parser correctly rejects it.
    assert run_pipeline("Medications:\n" + negative_line)["medications"] == []


@pytest.mark.parametrize(
    "source,name,dose,action",
    [
        ("Medications:\nContinue to hold Warfarin 2.5 mg PO daily.", "warfarin", "2.5 mg", "hold"),
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


def test_unrecognized_compound_action_is_not_attributed_as_medication_name():
    assert parse_order_lines("Continue to start Warfarin 2.5 mg PO daily.") == []
    assert parse_order_lines("Start to discontinue Aspirin 81 mg PO daily.") == []


def test_compound_order_in_plan_cannot_be_reintroduced_by_prose_or_medspacy():
    source = "Plan:\nContinue to hold Warfarin 2.5 mg PO daily."
    meds = run_pipeline(source)["medications"]
    assert [(m["name"], m["action"]) for m in meds] == [("warfarin", "hold")]

    # Unsupported mixed directives must not reappear as an actionless order
    # via the legacy section/prose parser or medSpaCy fallback.
    for section in ("Medications:\n", "Plan:\n", ""):
        assert run_pipeline(
            section + "Continue to start Warfarin 2.5 mg PO daily."
        )["medications"] == []


def test_indented_legacy_medication_and_prose_sections_keep_exact_offsets():
    source = "Medications:\n" + " " * 30 + "Hold Aspirin 81 mg PO daily.\n"
    meds = run_pipeline(source)["medications"]
    assert len(meds) == 1
    assert (meds[0]["name"], meds[0]["action"]) == ("aspirin", "hold")
    start, end = meds[0]["span"]
    assert source[start:end] == "Aspirin 81 mg PO daily"
    assert start == source.index("Aspirin")

    source = "Plan:\n" + " " * 28 + "Continue Metformin 500 mg PO BID.\n"
    meds = run_pipeline(source)["medications"]
    assert len(meds) == 1
    assert (meds[0]["name"], meds[0]["action"]) == ("metformin", "continue")
    start, end = meds[0]["span"]
    assert source[start:end] == "Metformin 500 mg PO BID"


def test_prn_indication_whitespace_preserves_original_evidence_coordinates():
    for whitespace in ("  ", "\t", " \t "):
        source = (
            "Medications:\n"
            "Albuterol inhaler 2 puffs q6h PRN chest"
            + whitespace + "tightness."
        )
        meds = run_pipeline(source)["medications"]
        assert len(meds) == 1
        assert meds[0]["qualifier"] == "PRN chest tightness"
        start, end = meds[0]["span"]
        assert source[start:end].endswith("PRN chest" + whitespace + "tightness")
        assert end == source.index("tightness") + len("tightness")


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


def test_stop_continue_taking_never_becomes_part_of_drug_identity():
    for verb, action in (("Stop taking", "stop"), ("Continue taking", "continue")):
        line = verb + " Warfarin 2.5 mg PO daily."
        for source in (line, "Medications:\n" + line):
            meds = run_pipeline(source)["medications"]
            assert len(meds) == 1, (source, meds)
            assert meds[0]["name"] == "warfarin"
            assert meds[0]["action"] == action
            start, end = meds[0]["span"]
            assert source[start:end].startswith("Warfarin")


def test_second_medication_instruction_never_leaks_prn_into_first_drug():
    source = "Start Lisinopril 10 mg PO daily and use albuterol PRN wheezing."
    assert parse_order_line(source) is None
    orders = parse_order_lines(source)
    lis = [m for m in orders if m["name"] == "lisinopril"]
    assert len(lis) == 1
    assert lis[0]["frequency"].casefold() == "daily"
    assert lis[0]["qualifier"] == ""
    assert lis[0]["action"] == "start"

    extracted = run_pipeline(source)["medications"]
    lis = [m for m in extracted if m["name"] == "lisinopril"]
    assert len(lis) == 1
    assert lis[0]["frequency"].casefold() == "daily"
    assert "prn" not in lis[0].get("qualifier", "").casefold()


def test_dose_free_take_aspirin_daily_keeps_canonical_entity():
    for source in ("Take aspirin daily.", "Medications:\nTake aspirin daily."):
        meds = run_pipeline(source)["medications"]
        assert len(meds) >= 1
        assert any(m["name"] == "aspirin" and m["frequency"].casefold() == "daily" for m in meds)
        assert all(m["name"] != "take aspirin" for m in meds)


def test_current_use_narrative_must_not_corrupt_drug_identity():
    for text in (
        "Currently taking Warfarin 2.5 mg PO daily.",
        "Medications:\nCurrently taking Warfarin 2.5 mg PO daily.",
    ):
        # The old medSpaCy fallback may recognize Warfarin as a medication
        # mention; it must not become "currently taking warfarin" or create
        # an authoritative new medication order.
        meds = run_pipeline(text)["medications"]
        assert len(meds) <= 1
        assert all(m["name"] == "warfarin" for m in meds)


def test_as_needed_and_prn_long_indications_survive_precedence_and_spans():
    cases = [
        (
            "Medications:\nBenzonatate 100 mg PO TID as needed for cough or shortness of breath.",
            "as needed for cough or shortness of breath",
        ),
        (
            "Medications:\nAlbuterol 2 puffs q6h PRN cough or shortness of breath.",
            "PRN cough or shortness of breath",
        ),
    ]
    for text, qualifier in cases:
        meds = run_pipeline(text)["medications"]
        assert len(meds) == 1
        assert meds[0]["qualifier"] == qualifier
        start, end = meds[0]["span"]
        assert text[start:end].endswith(qualifier)


def test_weight_gain_cannot_be_extracted_as_new_medication():
    for narrative in ("Weight gain 20 g daily.", "Weight increased 5 g daily."):
        for source in (narrative, "Medications:\n" + narrative):
            assert run_pipeline(source)["medications"] == []


def test_legacy_pre_dose_schedules_and_bedtime_remain_reviewable():
    cases = [
        ("Medications:\nMetformin BID 500 mg PO.", ("metformin", "PO", "BID")),
        ("Medications:\nMetformin PO BID 500 mg.", ("metformin", "PO", "BID")),
        ("Medications:\nInsulin glargine 20 units SQ bedtime.", ("insulin glargine", "SQ", "bedtime")),
    ]
    for source, expected in cases:
        medications = run_pipeline(source)["medications"]
        assert len(medications) == 1, source
        med = medications[0]
        assert (med["name"], med["route"], med["frequency"]) == expected
        start, end = med["span"]
        assert source[start:end].casefold().startswith(expected[0])

    # Competing schedules must not be merged or silently normalized.
    assert parse_order_lines("Metformin BID 500 mg PO TID.") == []


def test_pre_dose_route_not_misclassified_as_medication_identity():
    for source in (
        "Metformin PO 500 mg BID.",
        "Medications:\nMetformin PO 500 mg BID.",
    ):
        meds = run_pipeline(source)["medications"]
        assert len(meds) == 1
        assert (meds[0]["name"], meds[0]["dose"], meds[0]["route"], meds[0]["frequency"]) == (
            "metformin", "500 mg", "PO", "BID"
        )
        start, end = meds[0]["span"]
        assert source[start:end].startswith("Metformin PO 500 mg")

    # Do not guess which of two contradictory routes applies.
    assert parse_order_lines("Metformin IV 500 mg PO BID.") == []


def test_remaining_course_duration_and_original_span_survive_section_precedence():
    source = "Medications:\nPrednisone 20 mg PO daily for 5 more days."
    meds = run_pipeline(source)["medications"]
    assert len(meds) == 1
    assert meds[0]["name"] == "prednisone"
    assert meds[0]["duration"] == "for 5 more days"
    start, end = meds[0]["span"]
    assert source[start:end].endswith("for 5 more days")


def test_real_extraction_hold_stop_trigger_validation_non_active_canary():
    text = (
        "Hold Warfarin 2.5 mg PO daily.\n"
        "Discontinue Aspirin 81 mg PO daily.\n"
        "Start Lisinopril 10 mg PO daily.\n"
    )
    extracted = run_pipeline(text)
    meds = extracted["medications"]
    assert [(x["name"], x.get("action")) for x in meds] == [
        ("warfarin", "hold"), ("aspirin", "stop"), ("lisinopril", "start")
    ]
    issues = check_extraction(
        {"raw_text": text},
        {"extracted_json": extracted},
    )
    non_active = [i for i in issues if i.issue_code == "A10_NON_ACTIVE_MEDICATION"]
    assert len(non_active) == 2
    descriptions = " ".join(i.safe_explanation.lower() for i in non_active)
    assert "warfarin" in descriptions and "aspirin" in descriptions
    assert "lisinopril" not in descriptions


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
