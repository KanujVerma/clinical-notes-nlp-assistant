"""Synthetic prospective evaluation integrity tests, NOT model accuracy tests."""
import copy
import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from evaluation.prospective_holdout import (
    CASES, CATEGORIES, ROOT, validate_case_partition,
    validate_freeze, generate_holdout, _blob_sha,
)
from evaluation.handwriting_intake import validate_handwriting_manifest
from evaluation.local_ollama_resource_sampler import LocalOllamaResourceSampler, _parse_running_models
from evaluation.vision_benchmark import load_gold_manifest

LOCK = ROOT / "docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json"


def test_frozen_holdout_has_new_gold_and_balanced_image_categories():
    state = validate_case_partition()
    assert state["case_count"] == 24
    assert state["groups"] == {kind: 8 for kind in CATEGORIES}
    assert all(case["lines"][0] == "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE" for case in CASES)
    assert all(case["type"] != "handwritten" for case in CASES)


def test_case_identity_and_development_reuse_are_rejected():
    cases = copy.deepcopy(CASES)
    cases[1]["id"] = cases[0]["id"]
    with pytest.raises(ValueError, match="INVALID_HOLDOUT_CASE"):
        validate_case_partition(cases)

    cases = copy.deepcopy(CASES)
    cases[1]["lines"] = cases[0]["lines"]
    with pytest.raises(ValueError, match="DEVELOPMENT_DOCUMENT_REUSED"):
        validate_case_partition(cases)


def test_freeze_catches_source_tampering_and_fails_without_a_lock(tmp_path):
    assert validate_freeze(LOCK)["lock_version"] == "prospective_synthetic_v1"
    altered = json.loads(LOCK.read_text())
    altered["frozen_file_git_blobs"]["backend/extractors/medication_orders.py"] = "0" * 40
    path = tmp_path / "altered-lock.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="PRE_CASE_FREEZE_SEAL_MISMATCH"):
        validate_freeze(path)

    altered = json.loads(LOCK.read_text())
    altered["frozen_case_definition_git_blob"] = "f" * 40
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError, match="FROZEN_HOLDOUT_CASES_CHANGED"):
        validate_freeze(path)


def test_hashes_of_generated_images_are_verified_and_cannot_be_overwritten(tmp_path):
    dataset = generate_holdout(LOCK, tmp_path / "set")
    images, info = load_gold_manifest(dataset)
    assert len(images) == 24
    assert info["annotation_status"] == "synthetic_generator_ground_truth"
    manifest = json.loads(dataset.read_text())
    assert manifest["frozen_case_definition_git_blob"] == validate_freeze(LOCK)["frozen_case_definition_git_blob"]
    assert all(case["source_type"] != "handwritten" for case in manifest["cases"])
    with pytest.raises(ValueError, match="HOLDOUT_DESTINATION_EXISTS"):
        generate_holdout(LOCK, tmp_path / "set")
    image = tmp_path / "set" / manifest["cases"][0]["image"]
    image.write_bytes(image.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_gold_manifest(dataset)


def _handwriting_fixture(tmp_path):
    folder = tmp_path / "samples"
    folder.mkdir()
    image = folder / "case01.png"
    Image.new("RGB", (100, 60), "white").save(image)
    fixture = {
        "dataset_id": "fictional_handwriting_test_fixture",
        "synthetic_only": True,
        "annotation_status": "independent_human_transcription",
        "contains_actual_patient_data": False,
        "intended_use": "fictional_handwriting_evaluation_only",
        "attestation_verified_outside_software": True,
        "cases": [{
            "id": "case01",
            "image": "case01.png",
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "reference_text": "Fictional note. Ibuprofen 200 mg PO daily.",
            "critical_tokens": ["200 mg"],
            "source_type": "handwritten",
            "expected_medications": [{"name": "Ibuprofen", "dose": "200 mg", "route": "PO", "frequency": "daily"}],
            "expected_vitals": [],
            "human_provenance": {
                "writer_pseudonym": "writer-001",
                "independent_transcriber_pseudonyms": ["annotator-a", "annotator-b"],
                "adjudicator_pseudonym": "adjudicator-001",
                "capture_method": "pen_on_paper_scan",
                "generation_method": "freehand",
                "genuine_handwriting_attested": True,
                "fictional_content_attested": True,
                "source_image_reviewed_for_identifiers": True,
                "adjudication_record_id": "fictional-review-0001",
            },
        }],
    }
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps(fixture), encoding="utf-8")
    return manifest, fixture


def test_handwriting_contract_requires_separate_transcriber_and_no_font_claims(tmp_path):
    manifest, data = _handwriting_fixture(tmp_path)
    info = validate_handwriting_manifest(manifest)
    assert info["case_count"] == 1
    assert info["annotation_status"] == "independent_human_transcription"
    # The dummy white image is not actually handwritten; the validator only
    # checks attestations. This test must NEVER be cited as handwriting proof.
    assert info["cannot_verify"]

    bad = copy.deepcopy(data)
    bad["cases"][0]["human_provenance"]["generation_method"] = "cursive_font"
    manifest.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="FONTS_OR_AI_NOT_HANDWRITING"):
        validate_handwriting_manifest(manifest)

    bad = copy.deepcopy(data)
    bad["cases"][0]["human_provenance"]["writer_pseudonym"] = "annotator-a"
    manifest.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="HANDWRITING_INDEPENDENT_REVIEW_REQUIRED"):
        validate_handwriting_manifest(manifest)

    bad = copy.deepcopy(data)
    bad["annotation_status"] = "synthetic_generator_ground_truth"
    manifest.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="HANDWRITING_INDEPENDENT_GOLD_REQUIRED"):
        validate_handwriting_manifest(manifest)


def test_git_blob_sha_matches_git_file_object_format():
    content = b"test\n"
    assert _blob_sha(content) == hashlib.sha1(b"blob 5\x00test\n").hexdigest()


def test_ollama_resource_report_does_not_invent_model_memory():
    only_ocr = LocalOllamaResourceSampler(("tesseract",))
    with only_ocr:
        pass
    report = only_ocr.report()
    assert report["status"] == "not_applicable_tesseract_only"
    assert report["peak_reported_model_residency_bytes"] is None
    assert report["peak_reported_model_vram_bytes"] is None

    wanted = LocalOllamaResourceSampler(("glm_ocr",))
    report = wanted.report()
    assert report["status"] == "unmeasured_no_matching_loaded_model_sample"
    assert report["peak_unattributed_ollama_runner_rss_bytes"] is None


def test_ollama_ps_observations_are_model_filtered_not_zero_filled():
    sample = json.dumps({
        "models": [
            {"name": "glm-ocr:q8_0", "size": 1000000, "size_vram": 250000},
            {"name": "unrelated-model:latest", "size": 99999999, "size_vram": 99999999},
            {"name": "corrupt-model", "size": "not-int", "size_vram": 0},
        ]
    }).encode()
    rows = _parse_running_models(sample, {"glm-ocr:q8_0"})
    assert rows == [{
        "model": "glm-ocr:q8_0",
        "model_residency_bytes": 1000000,
        "model_vram_bytes": 250000,
    }]
    assert _parse_running_models(b'{"models":[]}', {"glm-ocr:q8_0"}) == []
    with pytest.raises(ValueError, match="OLLAMA_PS_INVALID"):
        _parse_running_models(b'{"models":{}}', {"glm-ocr:q8_0"})
