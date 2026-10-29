"""Offline tests for the paired LOCAL evaluation contract.

Mocked model predictions here verify scores/controls, never claim empirical
GLM-OCR or Qwen3-VL performance. Actual local runs are a separate CLI gate.
"""
import json

import pytest

from evaluation import local_vision_eval as vision
from evaluation.generate_synthetic_visual_cases import generate


def test_duplicate_occurrences_paired_by_order_not_best_dose():
    expected = [
        {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
        {"name": "Metformin", "dose": "1000 mg", "route": "PO", "frequency": "nightly"},
    ]
    predicted = [
        {"name": "Metformin", "dose": "1000 mg", "route": "PO", "frequency": "nightly"},
        {"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"},
    ]
    scored = vision.score_occurrences(expected, predicted, vision.FIELDS, "name")
    assert (scored["tp"], scored["fp"], scored["fn"]) == (0, 2, 2)
    assert scored["pairing_policy"] == "name_then_source_occurrence_order"


def test_wrong_dose_unit_and_decimal_fail_strict_occurrence():
    gold = [{"name": "Warfarin", "dose": "2.5 mg", "route": "PO", "frequency": "daily"}]
    bad = [{"name": "Warfarin", "dose": "25 mg", "route": "PO", "frequency": "daily"}]
    scored = vision.score_occurrences(gold, bad, vision.FIELDS, "name")
    assert (scored["tp"], scored["fp"], scored["fn"]) == (0, 1, 1)
    assert scored["f1"] == 0.0
    assert scored["mismatches"][0]["attributes"]["dose"]["expected"] == "2.5 mg"

    # Missing predictions with gold support must report 0.0 F1, not null
    omitted = vision.score_occurrences(gold, [], vision.FIELDS, "name")
    assert (omitted["tp"], omitted["fp"], omitted["fn"]) == (0, 0, 1)
    assert omitted["f1"] == 0.0

    bad[0]["dose"] = "2.5 g"
    assert vision.score_occurrences(gold, bad, vision.FIELDS, "name")["tp"] == 0


def test_explicit_hold_stop_actions_are_strict_but_unannotated_are_excluded():
    held = [{"name": "Warfarin", "dose": "2.5 mg", "action": "hold"}]
    proposed = [{"name": "Warfarin", "dose": "2.5 mg", "action": "start"}]
    incorrect = vision.score_occurrences(held, proposed, vision.FIELDS, "name")
    assert (incorrect["tp"], incorrect["fp"], incorrect["fn"]) == (0, 1, 1)
    assert "action" in incorrect["mismatches"][0]["attributes"]

    proposed[0]["action"] = "hold"
    assert vision.score_occurrences(held, proposed, vision.FIELDS, "name")["tp"] == 1

    unannotated = [{"name": "Warfarin", "dose": "2.5 mg"}]
    # A missing gold action is not automatically a true negative or a
    # confirmed hallucination; mark this dimension unannotated.
    assert vision.score_occurrences(unannotated, proposed, vision.FIELDS, "name")["tp"] == 1


def test_critical_numeric_tokens_and_uncapped_error_rates():
    ref = "Take 2.5 mg"
    wrong = "Take 25 mg"
    tokens = vision.exact_critical_tokens(ref, wrong, ["2.5 mg"])
    assert tokens == [{"token": "2.5 mg", "recognized": False}]
    assert vision._score_text("A", "A " * 15, [])["cer"] > 1


def test_arms_reject_unknown_and_duplicate_values():
    assert vision.parse_arms("tesseract,glm_ocr") == ("tesseract", "glm_ocr")
    for invalid in ("", "tesseract,tesseract", "qwen3_vl,remote_api", "glm_ocr,"):
        with pytest.raises(ValueError, match="INVALID_EVALUATION_ARMS"):
            vision.parse_arms(invalid)


def test_local_tesseract_only_baseline_without_ollama(tmp_path, monkeypatch):
    manifest = generate(tmp_path / "dataset")
    monkeypatch.setattr(vision.pytesseract, "get_tesseract_version", lambda: "test-tesseract")
    monkeypatch.setattr(
        vision.pytesseract, "image_to_string",
        lambda image, config: "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE",
    )
    # Prove this baseline does NOT query Ollama.
    monkeypatch.setattr(
        vision, "get_installed_model_digest",
        lambda model: (_ for _ in ()).throw(AssertionError("Ollama not allowed")),
    )
    result_path = vision.run_evaluation(
        manifest, ("tesseract",), tmp_path / "reports",
    )
    report = json.loads(result_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed_local_actual_predictions"
    assert report["arms_run"] == ["tesseract"]
    assert report["model_digests"]["tesseract"] == "test-tesseract"
    assert report["summary"]["tesseract"]["cases"] == 3
    assert report["summary"]["tesseract"]["critical_token_total"] > 0
    assert report["paired_tesseract_glm"] is None
    assert report["not_clinical_validation"] is True


def test_full_paired_adapter_scoring_and_manifest_digest(tmp_path, monkeypatch):
    manifest = generate(tmp_path / "dataset")
    monkeypatch.setattr(vision.pytesseract, "get_tesseract_version", lambda: "test-tesseract")
    monkeypatch.setattr(vision.pytesseract, "image_to_string", lambda img, config: "Test")
    monkeypatch.setattr(vision, "get_installed_model_digest",
                        lambda name: "local-model-sha256-digest-" + name)
    monkeypatch.setattr(vision, "glm_ocr_infer",
                        lambda image: {"status": "completed", "transcribed_text": "Test"})
    monkeypatch.setattr(vision, "qwen3_vl_infer",
                        lambda image: {"status": "completed", "candidates": {
                            "medications": [{"name": "Metformin", "dose": "500 mg", "route": "PO", "frequency": "BID"}],
                            "vitals": [],
                        }})
    path = vision.run_evaluation(
        manifest, ("tesseract", "glm_ocr", "qwen3_vl"), tmp_path / "reports",
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["arms_run"] == ["tesseract", "glm_ocr", "qwen3_vl"]
    assert len(report["paired_tesseract_glm"]) == 3
    assert len(report["cases"]["qwen3_vl"]) == 3
    assert report["cases"]["qwen3_vl"][0]["text_metrics"] is None
    assert report["summary"]["qwen3_vl"]["medications"]["support"] > 0
    assert len(report["dataset"]["manifest_sha256"]) == 64


def test_model_unavailable_fails_without_publishing_claims(tmp_path, monkeypatch, capsys):
    import sys
    manifest = generate(tmp_path / "dataset")
    monkeypatch.setattr(vision, "get_installed_model_digest",
                        lambda model: (_ for _ in ()).throw(vision.InferenceBindingError("MODEL_NOT_INSTALLED")))
    destination = tmp_path / "output"
    with pytest.raises(vision.InferenceBindingError, match="MODEL_NOT_INSTALLED"):
        vision.run_evaluation(manifest, ("glm_ocr",), destination)
    assert not destination.exists()

    monkeypatch.setattr(sys, "argv", ["local_vision_eval", "--manifest", str(manifest), "--arms", "glm_ocr", "--output-dir", str(destination)])
    ret = vision.main()
    assert ret == 2
    captured = capsys.readouterr()
    assert "EVALUATION_NOT_COMPLETED: MODEL_NOT_INSTALLED" in captured.err


def test_handwriting_rejected_without_independent_gold(tmp_path):
    manifest = generate(tmp_path / "dataset")
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["cases"][0]["source_type"] = "handwritten"
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    cases, _ = vision.load_gold_manifest(manifest)
    with pytest.raises(ValueError, match="HANDWRITING_GOLD_MUST_BE_INDEPENDENT"):
        vision._validate_structured_gold(raw, cases)


def test_rss_memory_marks_unloaded_model_as_unmeasured():
    mem = vision._get_rss_bytes()
    assert "runner_peak_rss_bytes" in mem
    assert isinstance(mem["runner_peak_rss_bytes"], int)
    assert mem["runner_peak_rss_bytes"] > 0
    assert mem["ollama_inference_rss_bytes"] is None
    assert mem["ollama_memory_status"] == "unmeasured_out_of_process_runner"
