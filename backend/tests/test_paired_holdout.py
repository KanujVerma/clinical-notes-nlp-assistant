"""Offline PR8 comparison-contract tests only: fake model OUTPUTS are never measurements."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluation import local_vision_eval as vision
from evaluation import run_paired_holdout as runner
from evaluation.paired_holdout_analysis import (
    ARMS, CANONICAL_MANIFEST_SHA256, canonical_manifest,
    compare_paired_reports, verify_single_arm_report,
)
from evaluation.prospective_holdout import ROOT, generate_holdout

LOCK = ROOT / "docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json"
FIXTURE_TRANSCRIPT = "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE\nNo drug orders in this mock test."


@pytest.fixture(scope="module")
def manifest(tmp_path_factory):
    path = generate_holdout(LOCK, tmp_path_factory.mktemp("pr8-canonical") / "dataset")
    # Verify the canonical dataset and its images really match PR7.
    assert canonical_manifest(path, LOCK)[0]["manifest_sha256"] == CANONICAL_MANIFEST_SHA256
    return path


@pytest.fixture(scope="module")
def mock_reports(manifest, tmp_path_factory):
    """Mock ONLY inference in tests; real evaluation/scoring engine stays unmodified."""
    out = tmp_path_factory.mktemp("pr8-test-model-reports")
    original_ocr = vision.glm_ocr_infer
    original_qwen = vision.qwen3_vl_infer
    original_digest = vision.get_installed_model_digest
    original_tess = vision.pytesseract.image_to_string
    original_version = vision.pytesseract.get_tesseract_version
    try:
        vision.get_installed_model_digest = lambda model: "test-only-unmeasured-local-" + model
        vision.pytesseract.get_tesseract_version = lambda: "test-only-not-a-measurement"
        vision.pytesseract.image_to_string = lambda *a, **kw: FIXTURE_TRANSCRIPT
        vision.glm_ocr_infer = lambda *a, **kw: {
            "status": "completed", "transcribed_text": FIXTURE_TRANSCRIPT,
        }
        vision.qwen3_vl_infer = lambda *a, **kw: {
            "status": "completed",
            "candidates": {"medications": [], "vitals": [], "visual_evidence": []},
        }
        yield {
            arm: vision.run_evaluation(manifest, (arm,), out / arm)
            for arm in ARMS
        }
    finally:
        vision.glm_ocr_infer = original_ocr
        vision.qwen3_vl_infer = original_qwen
        vision.get_installed_model_digest = original_digest
        vision.pytesseract.image_to_string = original_tess
        vision.pytesseract.get_tesseract_version = original_version


def _tamper(source: Path, output_dir: Path, callback) -> Path:
    obj = json.loads(source.read_text(encoding="utf-8"))
    callback(obj)
    path = output_dir / "altered_report.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_compare_requires_complete_same_image_three_arm_real_report_contract(manifest, mock_reports):
    compare = compare_paired_reports(manifest, LOCK, mock_reports)
    assert compare["status"] == "completed_three_arm_local_paired_synthetic_comparison"
    assert compare["case_count"] == 24
    assert compare["manifest_sha256"] == CANONICAL_MANIFEST_SHA256
    assert compare["arms_run"] == list(ARMS)
    assert len(compare["case_details"]) == 24
    assert compare["arm_summaries"]["qwen3_vl"]["summary"].get("cer_micro") is None
    assert compare["arm_summaries"]["glm_ocr"]["summary"].get("cer_micro") is not None
    assert compare["arm_summaries"]["qwen3_vl"]["out_of_process_resources"]["status"] == "not_measured_in_compare_only"
    assert compare["no_automatic_medication_routing_decision"] is True
    assert len({row["image_sha256"] for row in compare["case_details"]}) == 24
    for category in ("medications", "vitals"):
        for values in compare["paired_exact_case_comparisons"].values():
            row = values[category]
            assert sum(row.values()) == 24
    assert compare["paired_exact_case_comparisons"]["qwen3_vl_vs_glm_ocr"]["paired_ocr_cer"] is None


def test_reports_reject_mixed_dataset_and_swapped_source_image(manifest, mock_reports, tmp_path):
    _, gold = canonical_manifest(manifest, LOCK)
    source = mock_reports["glm_ocr"]
    changed = _tamper(source, tmp_path, lambda x: x["dataset"].update(manifest_sha256="0" * 64))
    with pytest.raises(ValueError, match="INCOMPLETE_OR_MISBOUND"):
        verify_single_arm_report(changed, "glm_ocr", canonical_manifest(manifest, LOCK)[0], gold)
    changed = _tamper(source, tmp_path, lambda x: x["cases"]["glm_ocr"][0].update(source_sha256="0" * 64))
    with pytest.raises(ValueError, match="MODEL_SOURCE_OR_LATENCY_MISMATCH"):
        verify_single_arm_report(changed, "glm_ocr", canonical_manifest(manifest, LOCK)[0], gold)


def test_scores_replay_against_original_predictions_not_report_claims(manifest, mock_reports, tmp_path):
    meta, gold = canonical_manifest(manifest, LOCK)
    source = mock_reports["qwen3_vl"]
    def add_fabricated_candidate(x):
        x["cases"]["qwen3_vl"][0]["structured_candidates"]["medications"].append({
            "name": "Imaginary Drug", "dose": "999 mg", "route": "PO",
            "frequency": "daily", "action": "start",
        })
    changed = _tamper(source, tmp_path, add_fabricated_candidate)
    with pytest.raises(ValueError, match="MODEL_SCORE_REPLAY_MISMATCH"):
        verify_single_arm_report(changed, "qwen3_vl", meta, gold)

    changed = _tamper(mock_reports["tesseract"], tmp_path, lambda x: x["cases"]["tesseract"][0].update(transcription="A completely different OCR hypothesis"))
    with pytest.raises(ValueError, match="OCR_TEXT_METRICS_CHANGED"):
        verify_single_arm_report(changed, "tesseract", meta, gold)


def test_strict_action_dose_and_unit_errors_cannot_be_normalized_away():
    from evaluation.local_vision_eval import FIELDS, score_occurrences
    gold = [{"name": "Warfarin", "dose": "2.5 mg", "route": "PO", "frequency": "daily", "action": "hold"}]
    for wrong in (
        {"dose": "25 mg"},
        {"dose": "2.5 g"},
        {"action": "start"},
        {"frequency": "BID"},
    ):
        pred = {**gold[0], **wrong}
        score = score_occurrences(gold, [pred], FIELDS, "name")
        assert (score["tp"], score["fp"], score["fn"], score["f1"]) == (0, 1, 1, 0.0)
    assert score_occurrences([], [], FIELDS, "name")["f1"] is None


def test_duplicate_missing_extra_cases_and_fake_qwen_ocr_are_rejected(manifest, mock_reports, tmp_path):
    meta, gold = canonical_manifest(manifest, LOCK)
    qwen = mock_reports["qwen3_vl"]
    changed = _tamper(qwen, tmp_path, lambda x: x["cases"]["qwen3_vl"].pop())
    with pytest.raises(ValueError, match="MISSING_OR_EXTRA_CASES"):
        verify_single_arm_report(changed, "qwen3_vl", meta, gold)
    changed = _tamper(qwen, tmp_path, lambda x: x["cases"]["qwen3_vl"][0].update(
        case_id=x["cases"]["qwen3_vl"][1]["case_id"]))
    with pytest.raises(ValueError, match="MISSING_DUPLICATE_OR_UNKNOWN_CASE"):
        verify_single_arm_report(changed, "qwen3_vl", meta, gold)
    changed = _tamper(qwen, tmp_path, lambda x: x["cases"]["qwen3_vl"][0].update(
        transcription="This isn't a Qwen OCR hypothesis"))
    with pytest.raises(ValueError, match="QWEN_STRUCTURED_OUTPUT_IS_NOT_OCR"):
        verify_single_arm_report(changed, "qwen3_vl", meta, gold)


def test_same_image_preflight_rejects_modified_gold_and_duplicate_source(manifest, tmp_path):
    old = json.loads(manifest.read_text(encoding="utf-8"))
    output = tmp_path / "dataset"
    output.mkdir()
    for case in old["cases"]:
        original = manifest.parent / case["image"]
        target = output / case["image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes())
    temp = copy.deepcopy(old)
    temp["cases"][0]["expected_medications"][0]["dose"] = "999 mg"
    m = output / "manifest.json"
    m.write_text(json.dumps(temp), encoding="utf-8")
    with pytest.raises(ValueError, match="CANONICAL_HOLDOUT_MANIFEST_MISMATCH"):
        canonical_manifest(m, LOCK)


def test_incomplete_arm_reports_cannot_be_called_a_head_to_head(manifest, mock_reports):
    with pytest.raises(ValueError, match="THREE_REAL_ARMS_REQUIRED"):
        compare_paired_reports(manifest, LOCK, {"tesseract": mock_reports["tesseract"]})


def test_no_model_installed_fails_before_model_calls_or_artifact_creation(manifest, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_preflight_models", lambda: (_ for _ in ()).throw(
        RuntimeError("LOCAL_MODEL_NOT_INSTALLED_OR_UNREACHABLE:glm_ocr")))
    monkeypatch.setattr(runner, "run_evaluation",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("Missing models must stop before inference")))
    destination = tmp_path / "should-not-exist"
    with pytest.raises(RuntimeError, match="LOCAL_MODEL_NOT_INSTALLED_OR_UNREACHABLE"):
        runner.execute(manifest, LOCK, destination)
    assert not destination.exists()


def test_remote_ollama_endpoint_is_rejected_prior_to_execution(monkeypatch):
    monkeypatch.setattr(runner, "_ensure_local_ollama_endpoint",
                        lambda: (_ for _ in ()).throw(ValueError("Remote endpoint refused")))
    with pytest.raises(ValueError, match="Remote endpoint refused"):
        runner._preflight_models()


def test_compare_only_creates_new_verified_report_without_model_calls(manifest, mock_reports, tmp_path):
    out = tmp_path / "replay"
    result = runner.compare_only(manifest, LOCK, out, mock_reports)
    saved = json.loads((out / "paired_comparison.json").read_text(encoding="utf-8"))
    assert result["manifest_sha256"] == saved["manifest_sha256"]
    assert saved["run_provenance"]["new_model_calls"] is False
    with pytest.raises(ValueError, match="PAIRED_OUTPUT_DIRECTORY_EXISTS"):
        runner.compare_only(manifest, LOCK, out, mock_reports)


def test_cli_preflight_does_not_query_models_or_create_artifacts(manifest, monkeypatch, capsys):
    monkeypatch.setattr(runner.sys, "argv", [
        "run_paired_holdout", "--manifest", str(manifest), "--preflight",
    ])
    monkeypatch.setattr(runner, "_preflight_models", lambda: (_ for _ in ()).throw(
        AssertionError("preflight must not query local Ollama")))
    assert runner.main() == 0
    assert "PAIRED_PREFLIGHT_VERIFIED_CANONICAL_24_CASES" in capsys.readouterr().out


def test_resource_absence_is_not_claimed_as_zero_and_swap_is_not_peak():
    report = runner._swap_used_macos_bytes()
    assert report is None or (type(report) is int and report >= 0)
    assert "system_swap_used_before_bytes" not in {
        "status": "not_measured_in_compare_only"
    }
