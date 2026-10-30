"""RxHandBD public test-split CONTRACT tests only, fake images and fake model text."""
from __future__ import annotations

import csv

import pytest
from PIL import Image, ImageDraw
from evaluation import public_rxhandbd_benchmark as rx
from evaluation import public_amr_benchmark as amr


@pytest.fixture
def fake_rx(tmp_path, monkeypatch):
    monkeypatch.setattr(rx, "EXPECTED_TEST", 16)
    root = tmp_path / "mock-rx-not-real-words"
    (root / "test_images").mkdir(parents=True)
    (root / "train_images").mkdir()
    records = []
    for i in range(16):
        name = f"case_{i:03d}.jpg"
        img = Image.new("RGB", (80 + i, 40), (255, 255, 255))
        ImageDraw.Draw(img).rectangle((i, 1, i+5, 10), fill=(i, 0, 130))
        img.save(root / "test_images" / name)
        records.append({"filename": name, "label": f"mock{i} 2.5 mg"})
    Image.new("RGB", (100, 40)).save(root / "train_images" / "train_1.jpg")
    with (root / "test_labels.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("filename", "label"))
        writer.writeheader()
        writer.writerows(records)
    return root


def approve(tmp_path, root):
    study = tmp_path / "review"
    rx.scaffold(root, study, count=12, images_dir=root / "test_images")
    review = amr.load(study / "privacy_review.json")
    review["reviewer_id"] = "MOCK_REVIEWER_NOT_REAL"
    for item in review["cases"]:
        item.update({"image_and_label_inspected": True,
                     "contains_identifiers": False,
                     "contains_real_patient_data": False,
                     "decision": "approved", "exclusion_reason": None})
    (study / "privacy_review.json").write_bytes(amr.raw_json(review))
    return study


def test_only_test_split_is_selected_and_scaffold_does_not_self_approve(fake_rx, tmp_path):
    study = tmp_path / "unapproved"
    result = rx.scaffold(fake_rx, study, count=12, images_dir=fake_rx / "test_images")
    assert result["publisher_test_rows"] == 16
    assert result["selected_words"] == 12
    selection = amr.load(study / "selection.json")
    assert all(r["image_name"].startswith("case_") for r in selection["full_test_ledger"])
    assert not any("train_1" in r["image_name"] for r in selection["full_test_ledger"])
    with pytest.raises(ValueError, match="RX_PRIVACY_REVIEW_REQUIRED"):
        rx.seal(study, tmp_path / "not-created")


def test_rxsafe_seal_and_replay_recomputed_from_fake_predictions(fake_rx, tmp_path,
                                                                monkeypatch):
    study = approve(tmp_path, fake_rx)
    sealed = tmp_path / "sealed"
    assert rx.seal(study, sealed)["scored"] == 12
    lock, manifest = rx.verify(sealed)
    assert lock["selected"] == 12
    assert manifest["word_level_only"] is True
    assert manifest["publisher_gold_not_human_adjudicated"] is True
    monkeypatch.setattr(amr, "preflight",
                        lambda arms: {"tesseract": "tess", "glm_ocr": "glm",
                                      "qwen3_vl_ocr": "qwen"})
    monkeypatch.setattr(rx, "infer_word", lambda arm, raw: "MOCK 2.5 mg")
    monkeypatch.setattr(rx.pytesseract, "get_tesseract_version", lambda: "tess")
    monkeypatch.setattr(rx, "get_installed_model_digest",
                        lambda m: "glm" if m == "glm-ocr:q8_0" else "qwen")
    result_dir = tmp_path / "mock-only"
    assert rx.evaluate(sealed, result_dir)["scored"] == 12
    assert rx.replay(sealed, result_dir)["status"] == "replayed_publisher_word_gold"
    report_path = result_dir / "raw_results.json"
    report = amr.load(report_path)
    report["cases"][0]["results"]["qwen3_vl_ocr"]["transcription"] = "tampered"
    report_path.write_bytes(amr.raw_json(report))
    receipt = amr.load(result_dir / "completion_receipt.json")
    receipt["results_sha256"] = amr.sha(report_path.read_bytes())
    (result_dir / "completion_receipt.json").write_bytes(amr.raw_json(receipt))
    with pytest.raises(ValueError, match="RX_REPLAY_METRICS_CHANGED"):
        rx.replay(sealed, result_dir)


def test_test_label_mutation_disallows_seal(fake_rx, tmp_path):
    study = approve(tmp_path, fake_rx)
    labels = fake_rx / "test_labels.csv"
    labels.write_text(labels.read_text().replace("mock0", "incorrect"))
    with pytest.raises(ValueError, match="RX_PUBLISHER_OR_SELECTION_CHANGED"):
        rx.seal(study, tmp_path / "not-created")


def test_missing_word_image_disallows_scaffold(fake_rx, tmp_path):
    (fake_rx / "test_images/case_000.jpg").unlink()
    with pytest.raises(ValueError, match="RX_MISSING_OR_DUPLICATE_TEST_IMAGE"):
        rx.scaffold(fake_rx, tmp_path / "not-created", count=12,
                    images_dir=fake_rx / "test_images")
