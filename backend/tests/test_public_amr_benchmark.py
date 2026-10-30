"""Public AMR contract tests ONLY: generated pixel patterns + mocked model predictions.

No test fixture is genuine handwriting and none measures model accuracy.
The real AMR dataset is NEVER downloaded or committed in CI.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from evaluation import public_amr_benchmark as amr


@pytest.fixture
def publisher_fixture(tmp_path):
    root = tmp_path / "mock-publisher-dataset-NOT-REAL-HANDWRITING"
    (root / "htr").mkdir(parents=True)
    (root / "truth").mkdir()
    rows = []
    multipage = {2: 3, 13: 2, 18: 3, 45: 2, 52: 3}
    for index in range(1, 63):
        ident = f"AMR_{index:03d}"
        pages = []
        for page in range(1, multipage.get(index, 1) + 1):
            name = f"htr/{ident}_HTR_p{page}.png"
            im = Image.new("RGB", (140 + index, 80 + page), (250, 250, 250))
            # Colored machine-generated marks, not images of handwriting.
            ImageDraw.Draw(im).rectangle((index, page, index + 10, page + 15),
                                         fill=(index, page * 3, 77))
            im.save(root / name)
            pages.append(name)
        truth = f"truth/{ident}.txt"
        (root / truth).write_text(
            f"MOCK GENERATED TEXT {ident}: hold 2.5 mg PRN\n", encoding="utf-8")
        rows.append({
            "pair_id": ident, "htr_file": ";".join(pages), "truth_file": truth,
            "num_pages": str(len(pages)),
            "contributor": f"mock_writer_{(index - 1) % 15:02d}",
        })
    with (root / "metadata.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=(
            "pair_id", "htr_file", "truth_file", "num_pages", "contributor"))
        writer.writeheader()
        writer.writerows(rows)
    return root


def prepare(tmp_path, publisher_fixture, *, exclude=()):
    study = tmp_path / "mock-intake"
    result = amr.scaffold(publisher_fixture, study)
    review_file = study / "privacy_review.json"
    review = amr.load(review_file)
    review["reviewer_id"] = "MOCK_REVIEWER_NOT_HUMAN"
    for record in review["cases"]:
        record["all_pages_and_transcript_reviewed"] = True
        record["contains_real_patient_data"] = False
        record["contains_identifiers"] = False
        if record["id"] in exclude:
            record["decision"] = "exclude"
            record["exclusion_reason"] = "other_concern"
        else:
            record["decision"] = "approved"
            record["exclusion_reason"] = None
    review_file.write_bytes(amr.raw_json(review))
    return study, result


def test_scaffold_is_private_unapproved_and_diverse(tmp_path, publisher_fixture):
    study = tmp_path / "intake"
    result = amr.scaffold(publisher_fixture, study)
    assert result["publisher_records"] == 62
    assert result["selected"] == 24
    record = amr.load(study / "selection.json")
    assert len({r["writer_group"] for r in record["all_records"]}) == 15
    assert amr.load(study / "privacy_review.json")["reviewer_id"] == ""
    assert all(x["decision"] == "unreviewed" for x in
               amr.load(study / "privacy_review.json")["cases"])
    with pytest.raises(ValueError, match="AMR_PRIVACY_REVIEW_NOT_SIGNED"):
        amr.seal(study, tmp_path / "blocked-seal")
    assert not (tmp_path / "blocked-seal").exists()


def test_seal_preserves_original_images_and_multpage_alignment(tmp_path, publisher_fixture):
    study, _ = prepare(tmp_path, publisher_fixture)
    seal_dir = tmp_path / "sealed-private"
    output = amr.seal(study, seal_dir)
    assert output["selected"] == 24 and output["scored"] == 24
    assert output["excluded"] == 0
    seal, scored = amr.verify(seal_dir)
    assert seal["scored"] == 24
    assert len(scored["cases"]) == 24
    first = scored["cases"][0]
    for case in scored["cases"]:
        for page in case["pages"]:
            original = (seal_dir / page["original"]).read_bytes()
            transformed = (seal_dir / page["inference"]).read_bytes()
            assert amr.sha(original) == page["original_sha256"]
            assert amr.sha(transformed) == page["inference_sha256"]
            assert original != transformed
    # If a selected case has three pages, it is still exactly ONE scored record.
    assert all(len(c["pages"]) == len(next(r for r in
               amr.load(study / "selection.json")["all_records"]
               if r["id"] == c["id"])["pages"]) for c in scored["cases"])
    assert first["reference"].endswith(".txt")


def test_seal_disallows_same_image_under_multiple_record_ids(tmp_path, publisher_fixture):
    first = publisher_fixture / "htr/AMR_001_HTR_p1.png"
    second = publisher_fixture / "htr/AMR_002_HTR_p1.png"
    second.write_bytes(first.read_bytes())
    with pytest.raises(ValueError, match="AMR_DUPLICATE_IMAGE_CONTENT"):
        amr.scaffold(publisher_fixture, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_multipage_metadata_mismatch_is_rejected(tmp_path, publisher_fixture):
    metadata = publisher_fixture / "metadata.csv"
    metadata.write_text(metadata.read_text().replace(
        "AMR_002_HTR_p3.png,truth/AMR_002.txt,3,",
        "AMR_002_HTR_p3.png,truth/AMR_002.txt,4,"), encoding="utf-8")
    with pytest.raises(ValueError, match="AMR_INCORRECT_MULTIPAGE_PAIRING"):
        amr.scaffold(publisher_fixture, tmp_path / "not-created")


def test_source_mutation_after_scaffold_blocks_freeze(tmp_path, publisher_fixture):
    study, _ = prepare(tmp_path, publisher_fixture)
    (publisher_fixture / "truth/AMR_001.txt").write_text("Wrong replacement\n")
    with pytest.raises(ValueError, match="AMR_UPSTREAM_BYTES_CHANGED"):
        amr.seal(study, tmp_path / "not-created")


def test_incomplete_review_and_faked_privacy_flags_rejected(tmp_path, publisher_fixture):
    study = tmp_path / "intake"
    amr.scaffold(publisher_fixture, study)
    review = amr.load(study / "privacy_review.json")
    review["reviewer_id"] = "mock_reviewer"
    for case in review["cases"]:
        case["all_pages_and_transcript_reviewed"] = True
        case["decision"] = "approved"
        case["contains_identifiers"] = False
        case["contains_real_patient_data"] = False
    review["cases"][0]["contains_identifiers"] = True
    (study / "privacy_review.json").write_bytes(amr.raw_json(review))
    with pytest.raises(ValueError, match="AMR_PRIVACY_UNSAFE_APPROVAL"):
        amr.seal(study, tmp_path / "not-created")


def test_reviewed_exclusions_retained_in_denominator(tmp_path, publisher_fixture):
    study, result = prepare(tmp_path, publisher_fixture, exclude=("AMR_001",))
    seal_dir = tmp_path / "sealed-private"
    output = amr.seal(study, seal_dir)
    assert output["scored"] == 23
    assert output["excluded"] == 1
    _, record = amr.verify(seal_dir)
    assert record["total_upstream_records"] == 62
    assert record["selected_ids"] == result["selected_ids"]
    assert record["excluded_before_inference"] == [
        {"id": "AMR_001", "reason": "other_concern"}]


def test_tampered_transformed_image_or_reference_invalidates_seal(
        tmp_path, publisher_fixture):
    study, _ = prepare(tmp_path, publisher_fixture)
    sealed = tmp_path / "sealed-private"
    amr.seal(study, sealed)
    _, manifest = amr.verify(sealed)
    image = sealed / manifest["cases"][0]["pages"][0]["inference"]
    image.write_bytes(image.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="AMR_SEALED_SOURCE_MODIFIED"):
        amr.verify(sealed)


def test_unavailable_models_fail_before_creating_results(tmp_path, publisher_fixture, monkeypatch):
    study, _ = prepare(tmp_path, publisher_fixture)
    sealed = tmp_path / "sealed-private"
    amr.seal(study, sealed)
    def offline():
        raise RuntimeError("MODEL_NOT_INSTALLED")
    monkeypatch.setattr(amr, "_preflight_models", offline)
    destination = tmp_path / "no-model-run"
    with pytest.raises(RuntimeError, match="MODEL_NOT_INSTALLED"):
        amr.execute(sealed, destination, ("tesseract", "glm_ocr", "qwen3_vl_ocr"))
    assert not destination.exists()


def test_fake_predictions_replay_and_tamper_detection(
        tmp_path, publisher_fixture, monkeypatch):
    study, _ = prepare(tmp_path, publisher_fixture)
    sealed = tmp_path / "sealed-private"
    amr.seal(study, sealed)
    fake_models = {"tesseract": "mock-tess", "glm_ocr": "mock-glm",
                   "qwen3_vl_ocr": "mock-qwen"}
    monkeypatch.setattr(amr, "preflight", lambda arms: fake_models)
    monkeypatch.setattr(amr, "infer", lambda arm, source: "MOCK 2.5 mg PRN")
    monkeypatch.setattr(amr.pytesseract, "get_tesseract_version", lambda: "mock-tess")
    monkeypatch.setattr(amr, "get_installed_model_digest",
                        lambda model: "mock-glm" if model == "glm-ocr:q8_0"
                        else "mock-qwen")
    run = tmp_path / "fake-model-run-ONLY"
    completed = amr.execute(sealed, run)
    assert completed["scored"] == 24
    assert completed["arms"] == list(amr.ARMS)
    assert amr.replay(sealed, run)["status"] == "replayed_all_saved_predictions"
    report_file = run / "raw_results.json"
    report = amr.load(report_file)
    report["cases"][0]["results"]["glm_ocr"]["metrics"]["cer"] = 0.0
    report_file.write_bytes(amr.raw_json(report))
    # Even a re-signed receipt cannot bypass independent recomputation of metrics.
    receipt = amr.load(run / "completion_receipt.json")
    receipt["result_sha256"] = amr.sha(report_file.read_bytes())
    (run / "completion_receipt.json").write_bytes(amr.raw_json(receipt))
    with pytest.raises(ValueError, match="AMR_REPLAY_PREDICTION_OR_METRICS_TAMPERED"):
        amr.replay(sealed, run)


def test_literal_critical_numbers_and_negation_preserved():
    result = amr.score("Hold warfarin 2.5 mg PRN", "Hold warfarin 25 mg")
    assert {t["token"] for t in result["critical_tokens"]} >= {"2.5 mg", "PRN"}
    assert not next(t for t in result["critical_tokens"]
                    if t["token"] == "2.5 mg")["recognized"]
