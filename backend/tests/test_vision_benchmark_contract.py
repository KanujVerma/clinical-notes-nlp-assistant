"""Manifest-contract tests; these do NOT invoke Ollama or measure OCR accuracy."""
import hashlib
import json

import pytest
from PIL import Image

from evaluation.vision_benchmark import load_gold_manifest


def _case(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "case001.png"
    Image.new("RGB", (128, 64), color="white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    data = {
        "dataset_id": "synthetic_test",
        "synthetic_only": True,
        "annotation_status": "synthetic_generator_ground_truth",
        "cases": [{
            "id": "case001", "image": "images/case001.png",
            "sha256": digest, "reference_text": "Warfarin 2.5 mg",
            "critical_tokens": ["2.5 mg"],
        }],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return manifest, image_path, data


def test_manifest_with_real_hashed_synthetic_image_is_accepted(tmp_path):
    manifest, image_path, data = _case(tmp_path)
    cases, metadata = load_gold_manifest(manifest)
    assert len(cases) == 1
    assert metadata["case_count"] == 1
    assert metadata["annotation_status"] == "synthetic_generator_ground_truth"
    assert cases[0]["source_sha256"] == hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert len(metadata["manifest_sha256"]) == 64


def test_manifest_rejects_changed_image_bytes(tmp_path):
    manifest, image_path, data = _case(tmp_path)
    Image.new("RGB", (128, 64), color="black").save(image_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_gold_manifest(manifest)


def test_manifest_rejects_unlabeled_or_non_synthetic_input(tmp_path):
    manifest, image_path, data = _case(tmp_path)
    data["synthetic_only"] = False
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic_only"):
        load_gold_manifest(manifest)

    data["synthetic_only"] = True
    data["annotation_status"] = "clinically_validated_by_model"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="annotation_status"):
        load_gold_manifest(manifest)


def test_manifest_rejects_duplicate_ids_and_path_traversal(tmp_path):
    manifest, image_path, data = _case(tmp_path)
    data["cases"].append(dict(data["cases"][0]))
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate case"):
        load_gold_manifest(manifest)

    data["cases"].pop()
    data["cases"][0]["image"] = "../outside.png"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid image path"):
        load_gold_manifest(manifest)


def test_generated_printed_fixtures_have_authentic_image_hashes(tmp_path):
    from evaluation.generate_synthetic_visual_cases import generate
    manifest = generate(tmp_path / "vision")
    cases, metadata = load_gold_manifest(manifest)
    assert metadata["case_count"] == 3
    assert metadata["annotation_status"] == "synthetic_generator_ground_truth"
    assert all(case["image_bytes"].startswith(b"\\x89PNG") for case in cases)
    assert any("2.5 mg" in case["critical_tokens"] for case in cases)
    assert all("source_sha256" in case for case in cases)
