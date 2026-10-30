"""Offline PR8 comparison-contract tests only: fake model OUTPUTS are never measurements."""
from __future__ import annotations

import copy
import hashlib
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


@pytest.mark.parametrize("metric", ["precision", "recall", "f1"])
def test_derived_aggregate_medication_metric_tampering_fails_replay(
        manifest, mock_reports, tmp_path, metric):
    meta, gold = canonical_manifest(manifest, LOCK)
    def mutate(result):
        aggregate = result["summary"]["qwen3_vl"]["medications"]
        aggregate[metric] = 0.777777
    changed = _tamper(mock_reports["qwen3_vl"], tmp_path, mutate)
    with pytest.raises(ValueError, match="MODEL_AGGREGATE_MISMATCH"):
        verify_single_arm_report(changed, "qwen3_vl", meta, gold)


def test_derived_critical_token_recall_tampering_fails_replay(manifest, mock_reports, tmp_path):
    meta, gold = canonical_manifest(manifest, LOCK)
    def mutate(result):
        result["summary"]["tesseract"]["critical_token_recall"] = 0.777777
    changed = _tamper(mock_reports["tesseract"], tmp_path, mutate)
    with pytest.raises(ValueError, match="OCR_AGGREGATE_MISMATCH"):
        verify_single_arm_report(changed, "tesseract", meta, gold)


def test_live_model_tag_change_mid_run_cannot_produce_completion_receipt(
        manifest, mock_reports, tmp_path, monkeypatch):
    versions = {
        arm: json.loads(path.read_text(encoding="utf-8"))["model_digests"][arm]
        for arm, path in mock_reports.items()
    }
    class NoNetworkSample:
        def __init__(self, arms): self.arms = arms
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def report(self): return {"status": "unmeasured_mock_test"}
    monkeypatch.setattr(runner, "_preflight_models", lambda: versions)
    monkeypatch.setattr(runner, "_swap_used_macos_bytes", lambda: None)
    monkeypatch.setattr(runner, "LocalOllamaResourceSampler", NoNetworkSample)
    monkeypatch.setattr(runner, "run_evaluation",
                        lambda manifest_path, arms, output_dir: mock_reports[arms[0]])
    monkeypatch.setattr(runner.pytesseract, "get_tesseract_version",
                        lambda: versions["tesseract"])
    monkeypatch.setattr(runner, "get_installed_model_digest",
                        lambda model: "replaced-model-digest" if model == runner.MODELS["glm_ocr"]
                        else versions["qwen3_vl"])
    output = tmp_path / "live-tag-change"
    with pytest.raises(ValueError, match="MODEL_DIGEST_CHANGED_DURING_EVALUATION:glm_ocr"):
        runner.execute(manifest, LOCK, output)
    assert (output / "execution_status.json").exists()
    assert not (output / "completion_receipt.json").exists()
    assert not (output / "paired_comparison.json").exists()


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
    # Make the SECOND row duplicate the FIRST: the duplicate-ID guard should
    # run before source SHA validation of the deliberately duplicated record.
    changed = _tamper(qwen, tmp_path, lambda x: x["cases"]["qwen3_vl"][1].update(
        case_id=x["cases"]["qwen3_vl"][0]["case_id"]))
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


@pytest.mark.parametrize("wrong", [
    {"glm_ocr": "qwen3-vl:4b", "qwen3_vl": "qwen3-vl:4b"},
    {"glm_ocr": "glm-ocr:q8_0", "qwen3_vl": "qwen3-vl:8b"},
    {"glm_ocr": "glm-ocr:q4_0", "qwen3_vl": "qwen3-vl:4b"},
])
def test_overridden_local_model_tags_rejected_before_any_endpoint_request(monkeypatch, wrong):
    monkeypatch.setattr(runner, "MODELS", wrong)
    monkeypatch.setattr(runner, "_ensure_local_ollama_endpoint",
                        lambda: (_ for _ in ()).throw(AssertionError("Remote/Ollama request attempted")))
    with pytest.raises(ValueError, match="NONCANONICAL_LOCAL_MODEL_TAGS"):
        runner._preflight_models()


def test_remote_ollama_endpoint_is_rejected_prior_to_execution(monkeypatch):
    monkeypatch.setattr(runner, "_ensure_local_ollama_endpoint",
                        lambda: (_ for _ in ()).throw(ValueError("Remote endpoint refused")))
    with pytest.raises(ValueError, match="Remote endpoint refused"):
        runner._preflight_models()


def _test_only_mock_execution_receipt(manifest, mock_reports, tmp_path):
    """Construct ONLY in-memory/test-directory attestation for mock-test verification."""
    from evaluation.paired_holdout_analysis import compare_paired_reports
    base = compare_paired_reports(manifest, LOCK, mock_reports)
    versions = {
        arm: base["arm_summaries"][arm]["model_digest_or_version"]
        for arm in ARMS
    }
    base["run_provenance"] = {
        "execution_type": "real_local_inference_not_mocked",
        "all_three_arms_required": True,
        "source_manifest_sha256": base["manifest_sha256"],
        "model_tags": dict(runner.REQUIRED_MODEL_TAGS),
        "model_digests_or_version_preflight": versions,
        "test_only_caution": "FAKE MODEL OUTPUTS USED ONLY TO TEST PROVENANCE VERIFICATION",
    }
    original_path = tmp_path / "mock-original-paired.json"
    original_path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    receipt = {
        "status": base["status"],
        "source_manifest_sha256": base["manifest_sha256"],
        "paired_report": {
            "sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
        },
        "arm_files": {
            arm: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for arm, path in mock_reports.items()
        },
    }
    receipt_path = tmp_path / "mock-execution-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return original_path, receipt_path


def test_compare_only_creates_new_verified_report_without_model_calls(manifest, mock_reports, tmp_path):
    original, receipt = _test_only_mock_execution_receipt(manifest, mock_reports, tmp_path)
    out = tmp_path / "replay"
    result = runner.compare_only(manifest, LOCK, out, mock_reports, original, receipt)
    saved = json.loads((out / "paired_comparison.json").read_text(encoding="utf-8"))
    assert result["manifest_sha256"] == saved["manifest_sha256"]
    assert saved["run_provenance"]["new_model_calls"] is False
    assert saved["run_provenance"]["identity_receipt"]["recorded_model_tags"] == runner.REQUIRED_MODEL_TAGS
    with pytest.raises(ValueError, match="PAIRED_OUTPUT_DIRECTORY_EXISTS"):
        runner.compare_only(manifest, LOCK, out, mock_reports, original, receipt)


def test_offline_replay_needs_original_completed_identity_receipt(manifest, mock_reports, tmp_path):
    out = tmp_path / "no-proof"
    with pytest.raises(ValueError, match="MODEL_IDENTITY_PROVENANCE_REQUIRED"):
        runner.compare_only(
            manifest, LOCK, out, mock_reports,
            tmp_path / "absent-original.json", tmp_path / "absent-receipt.json",
        )
    assert not out.exists()


def test_replay_rejects_relabelled_qwen_as_glm_even_if_receipt_hash_is_updated(
        manifest, mock_reports, tmp_path):
    original, receipt = _test_only_mock_execution_receipt(manifest, mock_reports, tmp_path)
    obj = json.loads(original.read_text())
    obj["run_provenance"]["model_tags"]["glm_ocr"] = "qwen3-vl:4b"
    original.write_text(json.dumps(obj), encoding="utf-8")
    ref = json.loads(receipt.read_text())
    ref["paired_report"]["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(ref), encoding="utf-8")
    out = tmp_path / "wrong-model-replay"
    with pytest.raises(ValueError, match="INVALID_CANONICAL_MODEL_IDENTITY_RECEIPT"):
        runner.compare_only(manifest, LOCK, out, mock_reports, original, receipt)
    assert not out.exists()


def test_replay_rejects_attested_digest_not_matching_source_report(
        manifest, mock_reports, tmp_path):
    original, receipt = _test_only_mock_execution_receipt(manifest, mock_reports, tmp_path)
    obj = json.loads(original.read_text())
    obj["run_provenance"]["model_digests_or_version_preflight"]["glm_ocr"] = "changed-digest"
    original.write_text(json.dumps(obj), encoding="utf-8")
    ref = json.loads(receipt.read_text())
    ref["paired_report"]["sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(ref), encoding="utf-8")
    out = tmp_path / "wrong-digest-replay"
    with pytest.raises(ValueError, match="MODEL_REPORT_NOT_BOUND_TO_ORIGINAL_RECEIPT"):
        runner.compare_only(manifest, LOCK, out, mock_reports, original, receipt)
    assert not out.exists()


@pytest.mark.parametrize("malformed", [
    {"paired_report": None},
    {"arm_files": []},
    {"arm_files": {"tesseract": None}},
])
def test_malformed_original_execution_receipt_fails_closed(
        manifest, mock_reports, tmp_path, malformed):
    original, receipt_path = _test_only_mock_execution_receipt(manifest, mock_reports, tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.update(malformed)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    out = tmp_path / "malformed-receipt-result"
    with pytest.raises(ValueError, match="INVALID_CANONICAL_MODEL_IDENTITY_RECEIPT"):
        runner.compare_only(manifest, LOCK, out, mock_reports, original, receipt_path)
    assert not out.exists()


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
