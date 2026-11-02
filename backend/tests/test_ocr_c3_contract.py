"""Campaign-3 contracts. No Vision framework, Ollama, or private handwriting."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from evaluation.ocr_c2.holdout import sealed_ids
from evaluation.ocr_c2.metrics import normalize_recognition, normalized_errors, occurrence_case, strict_case
from evaluation.ocr_c3.assemble import assemble, reading_order_uncertain
from evaluation.ocr_c3.budget import BudgetExhausted, Ledger
from evaluation.ocr_c3.cohorts import development_ids
from evaluation.ocr_c3.controller import acquire_lock, require_reviewed, step, write_checkpoint
from evaluation.ocr_c3.control_reuse import BaselineRejected, accept_saved_control, select_baseline
from evaluation.ocr_c3.execute import confirmation_fits, run_screen
from evaluation.ocr_c3.gates import compare_dataset, confirmation_outcome, screen_outcome
from evaluation.ocr_c3.geometry import geometry_status, pixel_rectangle
from evaluation.ocr_c3.identity import (
    SCORING_FILES, SCORING_SYMBOLS, inference_hash, request_identity, runtime_matches, scoring_hash,
)
from evaluation.ocr_c3.integrate import enabled, recognize
from evaluation.ocr_c3.protocol import CAMPAIGN_ID, CANDIDATE, ROOT, load_protocol
from evaluation.ocr_c3.replay import document_complete, replay_case
from evaluation.ocr_c3.runner import HelperTimeout, run_helper
from evaluation.ocr_c3.schema import validate_result
from evaluation.pr10_replay import reference_text
from evaluation.public_amr_benchmark import infer_image, sha


def _observation(index, text, x, y, width, height, image_width, image_height, alternate="other"):
    normalized = {
        "x": x / image_width,
        "y": 1 - (y + height) / image_height,
        "width": width / image_width,
        "height": height / image_height,
    }
    pixel = pixel_rectangle(normalized, image_width, image_height)
    return {
        "index": index,
        "candidates": [
            {"text": text, "confidence": 0.4},
            {"text": alternate, "confidence": 0.2},
        ],
        "top_candidate": text,
        "normalized_rectangle": normalized,
        "pixel_rectangle": pixel,
        "geometry_status": geometry_status(pixel, image_width, image_height),
    }


def _result(observations, prepared, transcript, width=100, height=40):
    return {
        "schema_version": "ocr_c3_vision_result_v1",
        "campaign_id": CAMPAIGN_ID,
        "candidate": CANDIDATE,
        "request_id": "req",
        "dataset": "amr",
        "case_id": "AMR_035",
        "page_index": 0,
        "source_sha256": "abc",
        "prepared_image_sha256": sha(prepared),
        "prepared_width": width,
        "prepared_height": height,
        "vision_request_revision": 3,
        "recognition_level": "accurate",
        "recognition_languages": ["en-US"],
        "uses_language_correction": False,
        "status": "completed" if transcript.strip() else "empty_transcription",
        "observations": observations,
        "assembled_transcription": transcript,
        "reading_order": "vision_reading_order_v1",
        "reading_order_uncertain": reading_order_uncertain(observations, width, height),
        "runtime_identity": {
            "os_build": load_protocol()["runtime"]["os_build"],
            "arch": load_protocol()["runtime"]["arch"],
            "vision_revision": load_protocol()["runtime"]["vision_revision"],
            "model_weight_digest": None,
        },
    }


def test_protocol_pins_one_vision_configuration():
    protocol = load_protocol()
    assert protocol["campaign_id"] == CAMPAIGN_ID
    assert protocol["candidate"]["id"] == CANDIDATE
    assert protocol["candidate"]["uses_language_correction"] is False
    assert protocol["candidate"]["recognition_languages"] == ["en-US"]
    assert protocol["candidate"]["custom_words"] == []
    assert protocol["runtime"]["vision_revision"] == 3
    assert protocol["runtime"]["model_weight_digest_available"] is False
    assert protocol["budgets"]["total_seconds"] == 7200
    assert protocol["selection"]["relative_cer_factor"] == 0.9
    source = (ROOT / "backend/evaluation/ocr_c3_swift/main.swift").read_text()
    assert "recognitionLevel = .accurate" in source
    assert "usesLanguageCorrection = false" in source
    assert "en-US" in source
    assert "http://" not in source
    assert inference_hash()
    scored_names = [name for _relative, names in SCORING_SYMBOLS for name in names]
    assert "_word_distance" in scored_names
    assert "backend/evaluation/ocr_c2/metrics.py" in SCORING_FILES
    assert scoring_hash()


def test_pixel_origin_and_corners():
    full = pixel_rectangle({"x": 0, "y": 0, "width": 1, "height": 1}, 200, 100)
    assert full == {"x": 0, "y": 0, "width": 200, "height": 100}
    top_left = pixel_rectangle({"x": 0, "y": 0.9, "width": 0.1, "height": 0.1}, 200, 100)
    assert top_left["x"] == 0
    assert abs(top_left["y"]) < 1e-9
    bottom_left = pixel_rectangle({"x": 0, "y": 0, "width": 0.1, "height": 0.1}, 200, 100)
    assert bottom_left["y"] == 90
    assert geometry_status({"x": 0, "y": 0, "width": 0, "height": 10}, 20, 20) == "invalid"
    assert geometry_status({"x": -1, "y": 0, "width": 4, "height": 4}, 20, 20) == "invalid"


def test_assembly_is_stable_and_keeps_duplicate_lines():
    observations = [
        _observation(1, "second", 0, 20, 40, 10, 100, 40),
        _observation(0, "first", 0, 0, 40, 10, 100, 40),
        _observation(2, "first", 0, 0, 10, 10, 100, 40),
    ]
    assert assemble(observations, 100, 40).splitlines()[0] == "first"
    assert assemble(observations, 100, 40).count("first") == 2
    tied = [
        _observation(1, "right", 50, 0, 10, 10, 100, 40),
        _observation(0, "left", 0, 0, 10, 10, 100, 40),
    ]
    assert assemble(tied, 100, 40) == "left\nright"
    columns = [
        _observation(0, "left", 0, 0, 20, 10, 100, 40),
        _observation(1, "right", 80, 0, 20, 10, 100, 40),
    ]
    assert reading_order_uncertain(columns, 100, 40) is True
    assert assemble(columns, 100, 40) == "left\nright"


def test_top_candidate_is_scored_and_alternates_are_not():
    prepared = b"prepared-jpeg"
    observations = [_observation(0, "5 mg", 0, 0, 40, 10, 100, 40, alternate="50 mg")]
    transcript = assemble(observations, 100, 40)
    result = _result(observations, prepared, transcript)
    checked = validate_result(result, prepared, 3)
    assert checked["transcription"] == "5 mg"
    result["assembled_transcription"] = "50 mg"
    try:
        validate_result(result, prepared, 3)
        raise AssertionError("alternate candidate scored")
    except ValueError as error:
        assert str(error) == "OCR_C3_ASSEMBLY"


def test_empty_page_is_not_a_completed_document():
    assert document_complete([
        {"status": "completed", "assembled_transcription": "5 mg"},
        {"status": "empty_transcription", "assembled_transcription": ""},
    ]) is False
    assert document_complete([{"status": "completed", "assembled_transcription": "5 mg"}]) is True


def test_prepared_jpeg_does_not_keep_a_second_orientation():
    image = Image.new("RGB", (30, 10), "white")
    exif = Image.Exif()
    exif[274] = 6
    raw = BytesIO()
    image.save(raw, format="TIFF", exif=exif)
    prepared = infer_image(raw.getvalue())
    decoded = Image.open(BytesIO(prepared))
    assert decoded.size == (10, 30)
    assert decoded.getexif().get(274, 1) == 1


def test_screen_ids_stay_away_from_sealed_splits():
    sealed = sealed_ids()
    amr = development_ids("screen", "amr")
    rx = development_ids("screen", "rx")
    assert len(amr) == 8
    assert len(rx) == 64
    assert not set(amr) & sealed["amr"]
    assert not set(rx) & sealed["rx"]
    assert len(development_ids("confirm", "amr")) == 20
    assert len(development_ids("confirm", "rx")) == 256
    try:
        development_ids("holdout", "amr")
        raise AssertionError("holdout opened")
    except Exception as error:
        assert "protected" in str(error).lower() or "sealed" in str(error).lower() or "PROTECTED" in str(error)


def test_relative_gate_and_safety_use_paired_cases():
    def case(identifier, prediction, reference):
        text = reference_text(reference)
        aligned = occurrence_case(text, prediction)
        return {
            "id": identifier,
            "status": "scored",
            "prediction": prediction,
            "metrics": strict_case(text, prediction),
            "normalized": normalized_errors(text, prediction),
            "occurrence_hits": aligned["occurrence_hits"],
            "occurrence_total": aligned["occurrence_total"],
            "occurrence_false_positives": aligned["occurrence_false_positives"],
        }

    reference = b"5 mg\n"
    baseline = [case("a", "5 mg", reference)]
    better = [case("a", "5 mg", reference)]
    worse = [case("a", "50 mg", reference)]
    same = compare_dataset(baseline, better)
    assert same["passed"] is False
    assert "relative_cer" in same["reasons"]
    unsafe = compare_dataset(baseline, worse)
    assert unsafe["passed"] is False
    lost = compare_dataset(baseline, [])
    assert "coverage_lost" in lost["reasons"] or "coverage_fell" in lost["reasons"]
    outcome = screen_outcome(same, same, [1, 2, 3, 4, 5, 6, 7, 70])
    assert outcome["outcome"] == "screen_negative"
    assert outcome["latency_p95_seconds"] == 70
    assert outcome["small_sample_p95"] is True
    rx_same = compare_dataset(baseline, better, require_relative=False)
    assert rx_same["passed"] is True
    assert "relative_cer" not in rx_same["reasons"]
    rx_worse = compare_dataset(baseline, worse, require_relative=False)
    assert "normalized_cer_worsened" in rx_worse["reasons"] or "strict_cer_worsened" in rx_worse["reasons"]


def test_confirmation_interval_can_stay_inconclusive():
    groups = [[(100, 80, 100)]]
    result = confirmation_outcome(groups, True, True)
    assert result["outcome"] in {"confirmation_negative", "confirmation_inconclusive", "development_candidate_ready"}
    assert result["bootstrap"]["point"] == 0.2
    weak = confirmation_outcome([[(100, 95, 100)]], True, True)
    assert weak["outcome"] == "confirmation_negative"


def test_replay_rejects_a_changed_transcript():
    prepared = b"page-bytes"
    observations = [_observation(0, "5 mg", 0, 0, 20, 10, 100, 40)]
    transcript = assemble(observations, 100, 40)
    page = _result(observations, prepared, transcript)
    reference = b"5 mg\n"
    text = reference_text(reference)
    aligned = occurrence_case(text, transcript)
    case = {
        "status": "scored",
        "prediction": transcript,
        "reference_sha256": sha(reference),
        "metrics": strict_case(text, transcript),
        "normalized": normalized_errors(text, transcript),
        "normalized_prediction": normalize_recognition(transcript),
        "occurrence_hits": aligned["occurrence_hits"],
        "occurrence_total": aligned["occurrence_total"],
        "occurrence_false_positives": aligned["occurrence_false_positives"],
        "pages": [page],
    }
    expected = request_identity("amr", ["AMR_035"], 3)
    case["identity"] = expected
    assert replay_case(case, reference, [prepared], expected)["classification"] == "verified"
    try:
        replay_case(dict(case, identity={}), reference, [prepared], expected)
        raise AssertionError("case without a Vision identity verified")
    except ValueError as error:
        assert str(error) == "OCR_C3_REPLAY"
    forged = dict(case, prediction="50 mg")
    try:
        replay_case(forged, reference, [prepared], expected)
        raise AssertionError("forged transcript verified")
    except ValueError as error:
        assert str(error) == "OCR_C3_REPLAY"
    empty = _result([], prepared, "")
    incomplete = dict(case, pages=[page, empty])
    incomplete["prediction"] = transcript + "\n"
    try:
        replay_case(incomplete, reference, [prepared, prepared], expected)
        raise AssertionError("empty page verified as scored")
    except ValueError as error:
        assert str(error) == "OCR_C3_REPLAY"
    drifted = dict(page)
    drifted["runtime_identity"] = dict(page["runtime_identity"], os_build="other")
    try:
        validate_result(drifted, prepared, 3)
        raise AssertionError("other OS build accepted")
    except ValueError as error:
        assert str(error) == "OCR_C3_RUNTIME"


def test_stale_control_and_unreviewed_screen_are_refused(tmp_path):
    try:
        accept_saved_control(
            {"status": "incomplete"}, [], b"5 mg\n", [], "digest", "amr", ["AMR_035"],
        )
        raise AssertionError("control without pages accepted")
    except BaselineRejected as error:
        assert str(error) == "baseline_evidence_incomplete"
    called = {"value": False}

    def load():
        called["value"] = True
        return {"loaded": True}

    try:
        run_screen({"state": "review_ready"}, "abc", load)
        raise AssertionError("unreviewed screen loaded a case")
    except RuntimeError as error:
        assert str(error) == "review_blocked"
    assert called["value"] is False
    require_reviewed({"state": "screening", "review_status": "passed", "reviewed_head": "abc"}, "abc")


def test_budget_timeout_and_lock(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", cap_seconds=30)
    assert ledger.begin("one", 120) == 30
    try:
        ledger.begin("two", 1)
        raise AssertionError("budget continued")
    except BudgetExhausted:
        pass
    image = tmp_path / "page.jpg"
    output = tmp_path / "out.json"
    image.write_bytes(b"prepared")

    def explode(argv, allowed, output_path):
        raise HelperTimeout("timeout")

    timed = run_helper(
        Path("binary"), image, output, "page", Path("config.json"), "fp",
        "amr", "AMR_035", 0, "source", b"prepared", Ledger(tmp_path / "time.jsonl", cap_seconds=7200),
        launch=explode,
    )
    assert timed["status"] == "timeout"
    stale = tmp_path / "stale.json"
    stale.write_text('{"status":"completed","assembled_transcription":"old"}')

    def leave_stale(argv, allowed, output_path):
        return {"returncode": 7}

    reused = run_helper(
        Path("binary"), image, stale, "fresh", Path("config.json"), "fp",
        "amr", "AMR_035", 0, "source", b"prepared", Ledger(tmp_path / "stale.jsonl", cap_seconds=7200),
        launch=leave_stale,
    )
    assert reused["status"] == "vision_request_failed"
    assert reused["completed"] is False
    failed = tmp_path / "failed.json"

    def write_failure(argv, allowed, output_path):
        output_path.write_text(json.dumps({
            "schema_version": "ocr_c3_vision_result_v1",
            "campaign_id": CAMPAIGN_ID,
            "request_id": "vision-fail",
            "status": "vision_request_failed",
            "error_code": "vision_request_failed",
            "elapsed_seconds": 0.1,
        }))
        return {"returncode": 3}

    envelope = run_helper(
        Path("binary"), image, failed, "vision-fail", Path("config.json"), "fp",
        "amr", "AMR_035", 0, "source", b"prepared", Ledger(tmp_path / "fail.jsonl", cap_seconds=7200),
        launch=write_failure,
    )
    assert envelope["status"] == "vision_request_failed"
    assert envelope["completed"] is False
    mismatched = tmp_path / "mismatch.json"

    def write_other_request(argv, allowed, output_path):
        output_path.write_text(json.dumps({
            "status": "completed",
            "request_id": "other",
            "dataset": "amr",
            "case_id": "AMR_035",
            "page_index": 0,
            "source_sha256": "source",
            "source_code_fingerprint": "fp",
            "assembled_transcription": "5 mg",
        }))
        return {"returncode": 0}

    foreign = run_helper(
        Path("binary"), image, mismatched, "this-request", Path("config.json"), "fp",
        "amr", "AMR_035", 0, "source", b"prepared", Ledger(tmp_path / "foreign.jsonl", cap_seconds=7200),
        launch=write_other_request,
    )
    assert foreign["status"] == "integrity_blocked"
    first = acquire_lock(tmp_path / "study.lock")
    try:
        acquire_lock(tmp_path / "study.lock")
        raise AssertionError("second lock acquired")
    except RuntimeError as error:
        assert str(error) == "OCR_C3_LOCK"
    first.close()
    assert confirmation_fits(100, 10, 7) is True
    assert confirmation_fits(100, 10, 9) is False
    assert step("review_ready", "review_passed") == "screening"
    try:
        step("screening", "holdout")
        raise AssertionError("holdout transition accepted")
    except ValueError as error:
        assert str(error) == "OCR_C3_PROTECTED_STAGE"
    write_checkpoint(tmp_path / "state.json", {
        "campaign_id": CAMPAIGN_ID,
        "state": "review_ready",
        "reviewed_head": "",
        "review_status": "pending",
        "budget_seconds": 0,
    })


def test_integration_stays_off_and_runtime_identity_is_exact(monkeypatch):
    monkeypatch.delenv("OCR_C3_ENABLED", raising=False)
    assert enabled() is False
    assert recognize(b"image", {"text": "kept"})["status"] == "disabled"
    protocol = load_protocol()
    assert runtime_matches({
        "os_build": protocol["runtime"]["os_build"],
        "arch": protocol["runtime"]["arch"],
        "vision_revision": 3,
        "model_weight_digest": None,
    }) is True
    assert runtime_matches({
        "os_build": "other",
        "arch": "arm64",
        "vision_revision": 3,
        "model_weight_digest": None,
    }) is False
    identity = request_identity("amr", ["AMR_035"], 3)
    assert identity["uses_language_correction"] is False
    assert json.loads(json.dumps(identity))["vision_revision"] == 3


def _jpeg(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _campaign2_control(tmp_path: Path, sources: list[bytes], transcripts: list[str], reference: bytes, digest: str, case_ids: list[str], name: str):
    """Build a case with campaign 2's runner, page writer, and scorer."""
    from evaluation.ocr_c2.budget import Ledger
    from evaluation.ocr_c2.identity import request_identity as control_identity
    from evaluation.ocr_c2.runner import run_page
    from evaluation.ocr_c2.screen_driver import page_artifact, score_document

    identity = control_identity("B8192", "amr", case_ids, digest)
    reference_sha = sha(reference)
    pages = []
    for index, (source, transcript) in enumerate(zip(sources, transcripts)):
        image = Image.open(BytesIO(source))
        image.load()

        def transport(prepared, candidate, allowed, transcript=transcript, digest=digest):
            del prepared, candidate, allowed
            return {
                "model": "glm-ocr:q8_0",
                "response": transcript,
                "done": True,
                "done_reason": "stop",
                "elapsed_seconds": 0.01,
                "model_digest": digest,
            }

        ledger = Ledger(tmp_path / f"{name}-{index}.jsonl", cap_seconds=100)
        result = run_page(image, "B8192", transport, ledger, f"{name}-{index}", digest)
        result["page_seconds"] = 0.01
        pages.append(page_artifact(result, sha(source), reference_sha, identity))
    return score_document(pages, reference_sha, reference, identity), pages


def test_historical_b8192_reuse_reads_the_campaign2_schema(tmp_path, monkeypatch):
    import evaluation.ocr_c3.control_reuse as control_reuse

    digest = "a" * 64
    other_digest = "b" * 64
    reference = b"5 mg\n"
    source = _jpeg((20, 40, 60))
    second = _jpeg((9, 8, 7))
    case, pages = _campaign2_control(tmp_path, [source], ["5 mg"], reference, digest, ["DOC_A"], "valid")
    assert "model_digest" not in case
    assert case["identity"]["model_digest"] == digest
    assert "prepared_image_sha256" not in case
    assert pages[0]["source_sha256"] == sha(source)
    assert pages[0]["source_sha256"] != pages[0]["regions"][0]["crop_sha256"]
    assert pages[0]["regions"][0]["crop_sha256"] == sha(infer_image(source))
    accept_saved_control(case, pages, reference, [source], digest, "amr", ["DOC_A"])
    reused = select_baseline(
        {"DOC_A": (case, pages)}, {"DOC_A": reference}, {"DOC_A": [source]},
        digest, "amr", ["DOC_A"],
    )
    assert reused == {"decision": "reuse"}

    blank, blank_pages = _campaign2_control(tmp_path, [source], [""], reference, digest, ["DOC_A"], "blank")
    assert blank["status"] == "incomplete"
    accept_saved_control(blank, blank_pages, reference, [source], digest, "amr", ["DOC_A"])
    assert blank["status"] == "incomplete"
    assert blank["metrics"] is None

    def refuse(reason: str, saved=case, saved_pages=pages, sources=None, digest_value=digest, ids=None):
        try:
            accept_saved_control(
                saved, saved_pages, reference, [source] if sources is None else sources,
                digest_value, "amr", ["DOC_A"] if ids is None else ids,
            )
            raise AssertionError(reason)
        except BaselineRejected as error:
            assert str(error) == reason

    from evaluation.ocr_c2.identity import request_identity as control_identity
    legacy = control_identity("Blegacy", "amr", ["DOC_A"], digest)
    legacy_case = dict(case, identity=legacy)
    refuse("baseline_model_drift", legacy_case)
    refuse("baseline_model_drift", json.loads(json.dumps(case)) | {"identity": dict(case["identity"], num_ctx=1024)})
    refuse("baseline_model_drift", json.loads(json.dumps(case)) | {"identity": dict(case["identity"], prompt="Text Recognition:")})
    refuse("baseline_model_drift", json.loads(json.dumps(case)) | {"identity": dict(case["identity"], num_predict=4096)})
    drifted = _campaign2_control(tmp_path, [source], ["5 mg"], reference, other_digest, ["DOC_A"], "drift")
    refuse("baseline_model_drift", drifted[0], drifted[1], digest_value=digest)
    for field in ("protocol_sha256", "partition_sha256", "scoring_sha256", "inference_sha256", "control_sha256"):
        mutated = json.loads(json.dumps(case))
        mutated["identity"][field] = "0" * 64
        refuse("baseline_code_drift", mutated)
    wrong_source = json.loads(json.dumps(pages))
    wrong_source[0]["source_sha256"] = "0" * 64
    refuse("baseline_source_mismatch", case, wrong_source)
    wrong_crop = json.loads(json.dumps(pages))
    wrong_crop[0]["regions"][0]["crop_sha256"] = sha(b"different-jpeg")
    refuse("baseline_prepared_bytes_mismatch", case, wrong_crop)
    wrong_reference = dict(case, reference_sha256="0" * 64)
    refuse("baseline_reference_mismatch", wrong_reference)
    wrong_metrics = json.loads(json.dumps(case))
    wrong_metrics["metrics"] = dict(case["metrics"], cer=1)
    refuse("baseline_reference_mismatch", wrong_metrics)
    refuse("baseline_evidence_incomplete", {"status": "scored"})
    refuse("baseline_evidence_incomplete", case, [])
    paired, paired_pages = _campaign2_control(
        tmp_path, [source, second], ["5 mg", "10 mg"], reference, digest, ["DOC_A"], "pair",
    )
    refuse("baseline_evidence_incomplete", paired, paired_pages[:1], [source, second])
    refuse("baseline_evidence_incomplete", paired, paired_pages + paired_pages[:1], [source, second])
    refuse("baseline_source_mismatch", paired, list(reversed(paired_pages)), [source, second])

    cohort = ["DOC_A", "DOC_B"]
    kept, kept_pages = _campaign2_control(tmp_path, [source], ["5 mg"], reference, digest, cohort, "kept")
    rejected, rejected_pages = _campaign2_control(
        tmp_path, [second], ["10 mg"], reference, other_digest, cohort, "rejected",
    )
    snapshot = json.dumps({"kept": kept, "rejected": rejected})
    fresh = select_baseline(
        {"DOC_A": (kept, kept_pages), "DOC_B": (rejected, rejected_pages)},
        {"DOC_A": reference, "DOC_B": reference},
        {"DOC_A": [source], "DOC_B": [second]},
        digest, "amr", cohort,
    )
    assert fresh == {"decision": "fresh", "reason": "baseline_model_drift", "case_id": "DOC_B"}
    assert json.dumps({"kept": kept, "rejected": rejected}) == snapshot
    missing = select_baseline(
        {"DOC_A": (case, pages)}, {"DOC_A": reference}, {"DOC_A": [source]},
        digest, "amr", cohort,
    )
    assert missing == {"decision": "fresh", "reason": "baseline_evidence_incomplete"}
    duplicate = select_baseline(
        {"DOC_A": (case, pages)}, {"DOC_A": reference}, {"DOC_A": [source]},
        digest, "amr", ["DOC_A", "DOC_A"],
    )
    assert duplicate == {"decision": "fresh", "reason": "baseline_evidence_incomplete"}
    monkeypatch.setattr(control_reuse, "infer_image", lambda raw: b"not-the-historical-jpeg")
    refuse("baseline_prepared_bytes_mismatch")
