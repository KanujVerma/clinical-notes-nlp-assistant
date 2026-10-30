"""PR9 contract tests: ALL images and local model responses are mocked.

White/color PNGs are generated only to test admission checks, hashes, independent
human roles and scorer replay. These tests have NEVER measured handwriting or
any GLM/Qwen model. No fabricated measurements may be published as results.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest
from PIL import Image

from evaluation import handwriting_study as study
from evaluation import handwriting_evaluate as evaluation
from evaluation import local_vision_eval as vision


def put(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_input(tmp_path, count=12, excluded=False):
    source = tmp_path / "fake-input-NOT-real-handwriting"
    (source / "images").mkdir(parents=True)
    collection = {
        "schema_version": study.VERSION,
        "dataset_id": "fictional_handwriting_mock_contract",
        "synthetic_only": True,
        "contains_actual_patient_data": False,
        "attestation_verified_outside_software": True,
        "cases": [],
    }
    trans = []
    for actor in ("annotator_alpha", "annotator_beta"):
        trans.append({
            "schema_version": study.VERSION, "dataset_id": collection["dataset_id"],
            "transcriber_pseudonym": actor,
            "independent_transcription_attested": True,
            "blind_to_models_and_writer_prompts": True,
            "cases": [],
        })
    adjud = {
        "schema_version": study.VERSION,
        "dataset_id": collection["dataset_id"],
        "adjudicator_pseudonym": "adjudicator_independent",
        "blinded_to_models": True,
        "independent_review_attested": True,
        "reviewed_both_transcripts": True,
        "cases": [],
    }
    for i in range(count):
        ident = f"hw{i+1:03d}"
        image = source / "images" / f"{ident}.png"
        # 100% synthetic BLANK image; not one byte represents handwriting.
        Image.new("RGB", (50 + i, 28 + i), (220-i, 240-i, 240-i)).save(image)
        sha = hashlib.sha256(image.read_bytes()).hexdigest()
        text = ("SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE\n"
                "Start Bisoprolol 2.5 mg PO QAM.\nPulse 58 bpm."
                if i % 3 == 0
                else "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE\nNo aspirin currently taken.")
        gold_med = ([{"name": "Bisoprolol", "dose": "2.5 mg", "route": "PO",
                      "frequency": "QAM", "action": "start"}] if i % 3 == 0 else [])
        gold_vital = ([{"vital_type": "heart_rate", "value": "58", "unit": "bpm"}]
                      if i % 3 == 0 else [])
        source_case = {
            "id": ident,
            "image": f"images/{ident}.png",
            "sha256": sha,
            "writer_pseudonym": f"writer_{i % 3 + 1:02d}",
            "generation_method": "freehand",
            "capture_method": "pen_on_paper_scan",
            "writing_style": ("block_print", "cursive", "mixed")[i % 3],
            "capture_quality": "clean" if i < count // 2 else "challenging",
            "genuine_handwriting_attested": True,
            "fictional_content_attested": True,
            "source_image_reviewed_for_identifiers": True,
            "writer_consent_attested": True,
        }
        collection["cases"].append(source_case)
        for doc in trans:
            doc["cases"].append({"id": ident, "sha256": sha, "reference_text": text})
        final = {
            "id": ident,
            "sha256": sha,
            "reference_text": text,
            "resolution": "agreed",
            "reviewed_original_image": True,
            "adjudication_record_id": f"fictional_audit_{i:03d}",
            "expected_medications": gold_med,
            "expected_vitals": gold_vital,
            "critical_tokens": ["2.5 mg"] if i % 3 == 0 else ["No aspirin"],
        }
        if excluded and i == count-1:
            final.update({
                "resolution": "unscorable",
                "exclusion_reason": "irreducibly_ambiguous",
                "resolution_notes": "Independent readers could not resolve the source",
                "reference_text": "",
                "expected_medications": [],
                "expected_vitals": [],
                "critical_tokens": [],
            })
        adjud["cases"].append(final)
    put(source / "collection.json", collection)
    for i, name in enumerate(("transcriber_a", "transcriber_b")):
        put(source / (name + ".json"), trans[i])
    put(source / "adjudication.json", adjud)
    return source


def read_source(source, name):
    return json.loads((source / (name + ".json")).read_text(encoding="utf-8"))


def patch_source(source, name, change):
    obj = read_source(source, name)
    change(obj)
    put(source / (name + ".json"), obj)


@pytest.fixture
def intake(tmp_path):
    return make_input(tmp_path)


def test_independent_human_roles_and_matching_12_case_gold_are_only_attestations(intake):
    manifest, originals = study.validate_collection(intake)
    assert len(originals) == 12
    assert manifest["annotation_status"] == "independent_human_transcription"
    assert all(x["source_type"] == "handwritten" for x in manifest["cases"])
    # The sources are actually test-generated blank images, NOT genuine notes.
    assert manifest["attestation_verified_outside_software"] is True


def test_make_seal_and_reverify_gold_and_original_image_bytes(intake, tmp_path):
    out = tmp_path / "sealed-private-mock"
    sealed = study.prepare(intake, out)
    assert sealed["case_count"] == 12
    assert sealed["writer_count"] == 3
    assert sealed["scorable_count"] == 12
    assert sealed["cohort_phase"] == "pilot_or_insufficient_sample"
    assert len(sealed["scored_manifest_sha256"]) == 64
    assert study.verify_seal(out) == sealed
    assert set(sealed["annotation_file_sha256"]) == {
        "collection", "transcriber_a", "transcriber_b", "adjudication"
    }
    with pytest.raises(ValueError, match="HANDWRITING_SEAL_DESTINATION_EXISTS"):
        study.prepare(intake, out)


@pytest.mark.parametrize("field", [
    "genuine_handwriting_attested", "fictional_content_attested",
    "source_image_reviewed_for_identifiers", "writer_consent_attested",
])
def test_reject_missing_truthful_source_attestations(intake, field):
    patch_source(intake, "collection", lambda x: x["cases"][0].update({field: False}))
    with pytest.raises(ValueError, match="HANDWRITING_HUMAN_CAPTURE_ATTESTATIONS_REQUIRED"):
        study.validate_collection(intake)


def test_fonts_or_ai_generated_images_cannot_claim_genuine_handwriting(intake):
    patch_source(intake, "collection",
                 lambda x: x["cases"][0].update(generation_method="cursive_font"))
    with pytest.raises(ValueError, match="HANDWRITING_HUMAN_CAPTURE_ATTESTATIONS_REQUIRED"):
        study.validate_collection(intake)


def test_transcriber_writer_and_adjudicator_separation(intake):
    patch_source(intake, "transcriber_b",
                 lambda x: x.update(transcriber_pseudonym="annotator_alpha"))
    with pytest.raises(ValueError, match="HANDWRITING_TRANSCRIBERS_NOT_INDEPENDENT"):
        study.validate_collection(intake)


def test_reject_writer_is_transcriber_or_adjudicator(intake):
    patch_source(intake, "collection",
                 lambda x: x["cases"][0].update(writer_pseudonym="annotator_alpha"))
    with pytest.raises(ValueError, match="HANDWRITING_WRITER_REVIEWER_OVERLAP"):
        study.validate_collection(intake)


def test_reject_transcriber_not_blind_to_model_or_writer_original(intake):
    patch_source(intake, "transcriber_a",
                 lambda x: x.update(blind_to_models_and_writer_prompts=False))
    with pytest.raises(ValueError, match="HANDWRITING_BLIND_TRANSCRIBER_REQUIRED"):
        study.validate_collection(intake)


def test_reject_adjudicator_not_independent_of_annotators(intake):
    patch_source(intake, "adjudication",
                 lambda x: x.update(adjudicator_pseudonym="annotator_beta"))
    with pytest.raises(ValueError, match="HANDWRITING_ADJUDICATOR_REQUIRED"):
        study.validate_collection(intake)


def test_frozen_all_cases_must_be_transcribed_not_posthoc_selected(intake):
    patch_source(intake, "transcriber_a", lambda x: x["cases"].pop())
    with pytest.raises(ValueError, match="HANDWRITING_PARTITION_CASES_MISMATCH"):
        study.validate_collection(intake)


def test_disagreements_must_be_explicitly_human_adjudicated(intake):
    patch_source(intake, "transcriber_b",
                 lambda x: x["cases"][0].update(reference_text="A radically different text"))
    with pytest.raises(ValueError, match="HANDWRITING_DISAGREEMENT_MUST_BE_RESOLVED"):
        study.validate_collection(intake)
    patch_source(intake, "adjudication",
                 lambda x: x["cases"][0].update(
                     resolution="adjudicated", resolution_notes="Reviewed numeric dose from original pixels"))
    study.validate_collection(intake)


def test_reject_transcriber_on_wrong_source_image(intake):
    patch_source(intake, "transcriber_a",
                 lambda x: x["cases"][0].update(sha256="0" * 64))
    with pytest.raises(ValueError, match="HANDWRITING_ANNOTATION_IMAGE_MISMATCH"):
        study.validate_collection(intake)


def test_renamed_or_mutated_source_bytes_rejected(intake):
    file = intake / "images/hw001.png"
    file.write_bytes(file.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="HANDWRITING_IMAGE_SHA_CHANGED"):
        study.validate_collection(intake)


def test_annotator_file_changed_between_intake_validation_and_copy_fails_closed(
        intake, tmp_path, monkeypatch):
    original = study.validate_collection
    def modify_during_validation(root):
        result = original(root)
        annotator = root / "transcriber_a.json"
        annotator.write_bytes(annotator.read_bytes() + b" ")
        return result
    monkeypatch.setattr(study, "validate_collection", modify_during_validation)
    target = tmp_path / "should-not-seal-changing-annotations"
    with pytest.raises(ValueError, match="HANDWRITING_ANNOTATIONS_CHANGED_DURING_INTAKE"):
        study.prepare(intake, target)
    assert not target.exists()


def test_full_cohort_requires_24_adjudicated_scorable_not_24_just_submitted(tmp_path):
    inp = make_input(tmp_path, count=24, excluded=True)
    sealed = tmp_path / "sealed"
    freeze = study.prepare(inp, sealed)
    assert freeze["case_count"] == 24
    assert freeze["scorable_count"] == 23
    assert freeze["cohort_phase"] == "pilot_or_insufficient_sample"
    assert freeze["unscorable_case_ids"] == ["hw024"]


def test_missing_patient_protection_attestation_and_no_shared_private_identifiers(intake):
    patch_source(intake, "collection",
                 lambda x: x.update(contains_actual_patient_data=True))
    with pytest.raises(ValueError, match="HANDWRITING_COLLECTION_ATTESTATION_REQUIRED"):
        study.validate_collection(intake)


def test_out_of_folder_images_cannot_be_injected(intake):
    patch_source(intake, "collection",
                 lambda x: x["cases"][0].update(image="../../elsewhere.png"))
    with pytest.raises(ValueError, match="HANDWRITING_UNSAFE_OR_MISSING_IMAGE"):
        study.validate_collection(intake)


def test_unscorable_cases_are_precommitted_not_silently_dropped(tmp_path):
    inp = make_input(tmp_path, excluded=True)
    out = tmp_path / "sealed"
    seal = study.prepare(inp, out)
    assert seal["case_count"] == 12
    assert seal["scorable_count"] == 11
    assert seal["unscorable_case_ids"] == ["hw012"]
    assert study.verify_seal(out)["unscorable_case_ids"] == ["hw012"]


def test_12_total_but_11_scorable_is_not_a_valid_pilot(tmp_path):
    inp = make_input(tmp_path, excluded=True)
    sealed = tmp_path / "sealed"
    study.prepare(inp, sealed)
    with pytest.raises(ValueError, match="HANDWRITING_INSUFFICIENT_HUMAN_COHORT"):
        evaluation._validate_study_for_run(sealed)


def test_seal_blocks_retrospective_changes_to_gold_and_original_annotation(intake, tmp_path):
    out = tmp_path / "sealed"
    study.prepare(intake, out)
    manifest_path = out / "scored_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_medications"][0]["dose"] = "25 mg"
    put(manifest_path, payload)
    with pytest.raises(ValueError, match="HANDWRITING_SEALED_GOLD_CHANGED"):
        study.verify_seal(out)
    # Restore the exact original serialized gold from the unmodified collection.
    out2 = tmp_path / "sealed-second"
    study.prepare(intake, out2)
    transcripts = out2 / "annotations/transcriber_a.json"
    transcripts.write_bytes(transcripts.read_bytes() + b" ")
    with pytest.raises(ValueError, match="HANDWRITING_INDEPENDENT_ANNOTATIONS_CHANGED"):
        study.verify_seal(out2)


def test_no_12_case_or_three_writer_cohort_produces_model_claims(tmp_path):
    inp = make_input(tmp_path, count=3)
    out = tmp_path / "sealed"
    study.prepare(inp, out)
    with pytest.raises(ValueError, match="HANDWRITING_INSUFFICIENT_HUMAN_COHORT"):
        evaluation._validate_study_for_run(out)


def make_mock_reports(monkeypatch, sealed, tmp_path):
    """No real vision/Ollama models. We never publish test outputs."""
    monkeypatch.setattr(vision, "get_installed_model_digest",
                        lambda model: "TEST_ONLY_NOT_A_MODEL_SHA256_" + model)
    monkeypatch.setattr(vision.pytesseract, "get_tesseract_version",
                        lambda: "TEST_ONLY_NOT_REAL_TESSERACT")
    monkeypatch.setattr(vision.pytesseract, "image_to_string",
                        lambda *args, **kwargs: "No aspirin currently taken.")
    monkeypatch.setattr(vision, "glm_ocr_infer",
                        lambda *args, **kwargs: {
                            "status": "completed", "transcribed_text": "No aspirin currently taken.",
                        })
    monkeypatch.setattr(vision, "qwen3_vl_infer",
                        lambda *args, **kwargs: {
                            "status": "completed",
                            "candidates": {"medications": [], "vitals": [], "visual_evidence": []},
                        })
    return {
        arm: vision.run_evaluation(sealed / "scored_manifest.json",
                                   (arm,), tmp_path / "fake-reports" / arm)
        for arm in evaluation.ARMS
    }


def test_mocked_contract_comparison_replays_all_scored_cases_without_claiming_accuracy(
        intake, tmp_path, monkeypatch):
    sealed = tmp_path / "sealed"
    study.prepare(intake, sealed)
    reports = make_mock_reports(monkeypatch, sealed, tmp_path)
    compared = evaluation.compare_reports(sealed, reports)
    assert compared["all_images_count"] == 12
    assert compared["scored_images_count"] == 12
    assert compared["cohort_phase"] == "pilot_or_insufficient_sample"
    assert compared["meets_minimum_24_case_target"] is False
    assert len(compared["case_details"]) == 12
    assert set(compared["stratified_medication_metrics"]["writing_style"]) == {
        "block_print", "cursive", "mixed"
    }
    assert compared["arm_summaries"]["qwen3_vl"]["summary"].get("cer_micro") is None
    for values in compared["paired_exact_case_comparisons"].values():
        assert sum(values["medications"].values()) == 12
    assert compared["not_clinical_validation"] is True


def test_raw_predicted_medication_f1_cannot_be_faked_before_audit(intake, tmp_path, monkeypatch):
    sealed = tmp_path / "sealed"
    study.prepare(intake, sealed)
    reports = make_mock_reports(monkeypatch, sealed, tmp_path)
    original = json.loads(reports["qwen3_vl"].read_text(encoding="utf-8"))
    original["summary"]["qwen3_vl"]["medications"]["f1"] = 1.0
    changed = tmp_path / "tampered.json"
    put(changed, original)
    with pytest.raises(ValueError, match="HANDWRITING_AGGREGATE_CHANGED"):
        evaluation.verify_single_arm_report(
            changed, "qwen3_vl",
            vision.load_gold_manifest(sealed / "scored_manifest.json")[1],
            {x["id"]: x for x in json.loads(
                (sealed / "scored_manifest.json").read_text())["cases"]},
        )


def test_execute_preflight_stops_if_models_absent_without_inference(
        intake, tmp_path, monkeypatch):
    sealed = tmp_path / "sealed"
    study.prepare(intake, sealed)
    monkeypatch.setattr(evaluation, "_preflight_models",
                        lambda: (_ for _ in ()).throw(ValueError("NONCANONICAL_LOCAL_MODEL_TAGS")))
    monkeypatch.setattr(evaluation, "run_evaluation",
                        lambda *args, **kw: (_ for _ in ()).throw(
                            AssertionError("Inference must not happen")))
    output = tmp_path / "none"
    with pytest.raises(ValueError, match="NONCANONICAL_LOCAL_MODEL_TAGS"):
        evaluation.execute(sealed, output)
    assert not output.exists()


def test_real_run_receipt_and_offline_replay_are_consistent_when_models_are_mocked(
        intake, tmp_path, monkeypatch):
    sealed = tmp_path / "sealed"
    study.prepare(intake, sealed)
    fake_digests = {
        "tesseract": "TEST_ONLY_NOT_REAL_TESSERACT",
        "glm_ocr": "TEST_ONLY_NOT_A_MODEL_SHA256_glm-ocr:q8_0",
        "qwen3_vl": "TEST_ONLY_NOT_A_MODEL_SHA256_qwen3-vl:4b",
    }
    class FakeSampler:
        def __init__(self, arms): self.arms = arms
        def __enter__(self): return self
        def __exit__(self, typ, val, tb): return False
        def report(self): return {"status": "fake_sampler_not_empirical"}
    monkeypatch.setattr(evaluation, "_preflight_models", lambda: fake_digests)
    monkeypatch.setattr(evaluation, "LocalOllamaResourceSampler", FakeSampler)
    monkeypatch.setattr(evaluation, "_swap_used_macos_bytes", lambda: None)
    monkeypatch.setattr(evaluation, "get_installed_model_digest",
                        lambda model: fake_digests["glm_ocr"] if "glm" in model else fake_digests["qwen3_vl"])
    monkeypatch.setattr(evaluation.pytesseract, "get_tesseract_version",
                        lambda: fake_digests["tesseract"])
    # This mock adapter calls the same real frozen scoring engine but NEVER Ollama.
    monkeypatch.setattr(vision, "get_installed_model_digest",
                        lambda model: fake_digests["glm_ocr"] if "glm" in model else fake_digests["qwen3_vl"])
    monkeypatch.setattr(vision, "pytesseract", evaluation.pytesseract)
    monkeypatch.setattr(vision.pytesseract, "image_to_string",
                        lambda *a, **k: "No aspirin currently taken.")
    monkeypatch.setattr(vision, "glm_ocr_infer",
                        lambda *a, **k: {"status": "completed", "transcribed_text": "No aspirin currently taken."})
    monkeypatch.setattr(vision, "qwen3_vl_infer",
                        lambda *a, **k: {
                            "status": "completed",
                            "candidates": {"medications": [], "vitals": [], "visual_evidence": []},
                        })
    run_dir = tmp_path / "fake-run"
    compared = evaluation.execute(sealed, run_dir)
    assert compared["scored_images_count"] == 12
    assert (run_dir / "completion_receipt.json").exists()
    replay = evaluation.replay(sealed, run_dir, tmp_path / "offline-replay")
    assert replay["offline_replay"]["new_model_calls"] is False
    assert replay["case_details"] == compared["case_details"]
    assert replay["arm_summaries"]["glm_ocr"]["summary"]["cases"] == 12
    receipt = json.loads((run_dir / "completion_receipt.json").read_text())
    receipt["arm_files"]["glm_ocr"]["sha256"] = "0" * 64
    put(run_dir / "completion_receipt.json", receipt)
    with pytest.raises(ValueError, match="HANDWRITING_MODEL_OR_SUMMARY_HASH_MISMATCH"):
        evaluation.replay(sealed, run_dir, tmp_path / "bad-replay")
