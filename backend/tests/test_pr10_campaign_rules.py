"""Promotion rules and candidate diffs. No model calls."""
from __future__ import annotations

import io
import json

from PIL import Image

from evaluation import pr10_autoresearch, pr10_campaign
from evaluation.pr10_campaign import _compare, _metrics, acquire_lock, campaign
from evaluation.pr10_autoresearch import (
    MODEL, build_identity, completed_status, predict_spec, require_frozen_amr_pages, run_spec,
)
from evaluation.pr10_candidate import (
    changed_fields, historical_specs, mutation_queue, render_regions, resolve_spec,
)
from evaluation.pr10_identity import (
    BOUND_FILES, IDENTITY_VERSION, CheckpointRejected, LegacyCheckpoint, assess_reuse,
    fingerprint, implementation_hashes, inference_fingerprint, scoring_fingerprint,
)
from evaluation.pr10_replay import (
    align_critical, audit_saved_runs, classify_saved_run, cohorts_match,
    critical_false_positives, decide_screen, load_run, load_verified_run,
    micro_summary, paired_population, reference_text, rescore_case,
)
from evaluation.public_amr_benchmark import infer_image, score, sha

TRACKED = (
    "encode", "contrast", "grayscale", "gamma", "sharpen", "denoise", "trim",
    "longest", "num_ctx", "prompt", "dedupe_lines", "collapse_spaces",
    "second_pass", "segment", "jpeg_quality",
)


def _view(**overrides):
    base = {
        "scored": 8, "fp": 1, "paired_cer": 0.40, "paired_hits": 7,
        "paired_fp": 1, "paired_p95": 8000, "rx_cer": 0.37,
    }
    base.update(overrides)
    return base


def _scored(case_id: str):
    return {
        "id": case_id,
        "status": "scored",
        "latency_ms": 10,
        "critical_false_positives": 0,
        "metrics": {
            "character_distance": 1,
            "word_distance": 1,
            "ref_chars": 4,
            "ref_words": 1,
            "critical_tokens": [],
        },
    }


def test_coverage_gain_without_paired_gain_is_reliability_only():
    decision = decide_screen(_view(scored=2), _view(scored=8))
    assert decision["status"] == "reliability_candidate"


def test_paired_cer_improvement_is_an_accuracy_candidate():
    decision = decide_screen(_view(), _view(paired_cer=0.30))
    assert decision["status"] == "accuracy_candidate"


def test_paired_error_or_coverage_loss_is_rejected():
    assert decide_screen(_view(), _view(paired_cer=0.50))["status"] == "rejected"
    assert decide_screen(_view(), _view(scored=7))["status"] == "rejected"
    assert decide_screen(_view(rx_scored=64), _view(rx_scored=63))["status"] == "rejected"
    assert decide_screen(_view(), _view(paired_hits=6))["status"] == "rejected"
    assert decide_screen(_view(), _view(paired_fp=2))["status"] == "rejected"
    assert decide_screen(_view(), _view())["status"] == "rejected"
    assert "no measured gain" in decide_screen(_view(), _view())["reason"]


def test_undefined_rx_cer_cannot_win():
    assert decide_screen(_view(), _view(rx_cer=None))["status"] == "inconclusive"
    assert "no shared scored Rx" in decide_screen(_view(rx_cer=None), _view())["reason"]
    failed = {"id": "rx1", "status": "failed"}
    metrics = _metrics([_scored("amr1")], [failed], {"amr1"})
    assert metrics["rx_cer"] is None
    assert metrics["rx_scored"] == 0


def test_zero_shared_amr_successes_are_not_perfect_paired_cer():
    decision = decide_screen(_view(paired_cer=None), _view(paired_cer=None))
    assert decision["status"] == "inconclusive"
    metrics = _metrics(
        [{"id": "amr1", "status": "failed"}, {"id": "amr2", "status": "failed"}],
        [_scored("rx1")],
        set(),
    )
    assert metrics["paired_cer"] is None


def test_different_attempted_ids_are_not_the_same_cohort():
    assert cohorts_match(["a", "b"], ["b", "a"])
    assert not cohorts_match(["a", "b"], ["a"])


def test_each_mutation_changes_one_tracked_field():
    parent = historical_specs()["jpeg_ctx8192"]
    children = mutation_queue(parent)
    assert len(children) >= 15
    families = {child["family"] for child in children}
    assert {"A", "B", "C", "D", "E"} <= families
    for child in children:
        changed = [key for key in TRACKED if child.get(key) != parent.get(key)]
        assert changed, child["name"]
        assert len(changed) == 1, (child["name"], changed)


def test_noop_mutation_is_not_a_new_experiment():
    parent = dict(historical_specs()["jpeg_ctx8192"])
    parent["name"] = "jpeg_ctx8192__no_infer"
    parent["prompt"] = "no_infer"
    children = mutation_queue(parent)
    assert not any(child["name"].endswith("__no_infer") for child in children)
    for child in children:
        assert changed_fields(parent, child) and len(changed_fields(parent, child)) == 1


def _scored_case(reference: str, prediction: str, digest: str) -> dict:
    aligned = align_critical(reference, prediction)
    return {
        "status": "scored",
        "prediction": prediction,
        "reference_sha256": digest,
        "metrics": score(reference, prediction),
        "critical_false_positives": critical_false_positives(reference, prediction),
        "occurrence_hits": aligned["occurrence_hits"],
        "occurrence_total": aligned["occurrence_total"],
        "occurrence_false_positives": aligned["occurrence_false_positives"],
    }


def test_rescore_requires_the_original_reference_bytes():
    body = "5 mg\n".encode()
    digest = sha(body)
    case = _scored_case("5 mg\n", "5 mg", digest)
    verified = rescore_case(case, body, digest)
    assert verified["replay_verified"] is True
    bom = b"\xef\xbb\xbf5 mg\n"
    bom_case = _scored_case("5 mg\n", "5 mg", sha(bom))
    assert rescore_case(bom_case, bom, sha(bom))["replay_verified"] is True
    crlf = b"5 mg\r\n"
    crlf_case = _scored_case("5 mg\n", "5 mg", sha(crlf))
    assert rescore_case(crlf_case, crlf, sha(crlf))["replay_verified"] is True
    try:
        rescore_case(case, b"5 mg\n", "0" * 64)
        raise AssertionError("hash mismatch was accepted")
    except ValueError as error:
        assert str(error) == "PR10_REFERENCE_HASH_MISMATCH"
    try:
        rescore_case(case, b"", digest)
        raise AssertionError("missing reference was accepted")
    except ValueError as error:
        assert str(error) == "PR10_REFERENCE_MISSING"
    changed = dict(case)
    changed["prediction"] = "50 mg"
    try:
        rescore_case(changed, body, digest)
        raise AssertionError("changed prediction was accepted")
    except ValueError as error:
        assert str(error) == "PR10_REPLAY_METRICS_MISMATCH"
    tweaked = dict(case)
    tweaked["metrics"] = dict(case["metrics"])
    tweaked["metrics"]["character_distance"] = 99
    try:
        rescore_case(tweaked, body, digest)
        raise AssertionError("changed metric was accepted")
    except ValueError as error:
        assert str(error) == "PR10_REPLAY_METRICS_MISMATCH"
    lied = dict(case)
    lied["occurrence_hits"] = case["occurrence_hits"] + 1
    try:
        rescore_case(lied, body, digest)
        raise AssertionError("changed occurrence count was accepted")
    except ValueError as error:
        assert str(error) == "PR10_REPLAY_METRICS_MISMATCH"


def test_empty_transcription_is_not_scored():
    assert completed_status("") == "empty_transcription"
    assert completed_status("   ") == "empty_transcription"
    assert completed_status(None) == "empty_transcription"
    assert completed_status("5 mg") == "scored"


def _scripted_ocr(monkeypatch, responses: list[str]):
    pending = iter(responses)

    def fake(image_bytes, page_number=1, model=None, num_ctx=None, system_prompt=None, user_prompt=None):
        return {"status": "completed", "transcribed_text": next(pending), "model": model}

    monkeypatch.setattr(pr10_autoresearch, "glm_ocr_infer", fake)


def test_blank_page_is_an_inference_miss(monkeypatch):
    _scripted_ocr(monkeypatch, ["5 mg", ""])
    text, _latency, status, passes = predict_spec(historical_specs()["jpeg_ctx8192"], [_png(), _png()])
    assert text == ""
    assert status == "empty_transcription"
    assert passes == 1


def test_second_pass_recovers_a_blank_page(monkeypatch):
    _scripted_ocr(monkeypatch, ["5 mg", "   ", "5 mg", "10 mg"])
    spec = dict(historical_specs()["jpeg_ctx8192"])
    spec["second_pass"] = True
    text, _latency, status, passes = predict_spec(spec, [_png(), _png()])
    assert status == "scored"
    assert passes == 2
    assert "5 mg" in text and "10 mg" in text


def test_unrecovered_blank_page_stays_a_miss(monkeypatch):
    _scripted_ocr(monkeypatch, ["5 mg", "", "5 mg", ""])
    spec = dict(historical_specs()["jpeg_ctx8192"])
    spec["second_pass"] = True
    text, _latency, status, passes = predict_spec(spec, [_png(), _png()])
    assert text == ""
    assert status == "empty_transcription"
    assert passes == 2


def test_blank_retry_does_not_erase_a_complete_first_pass(monkeypatch):
    _scripted_ocr(monkeypatch, ["5 mg", ""])
    spec = dict(historical_specs()["jpeg_ctx8192"])
    spec["second_pass"] = True
    text, _latency, status, passes = predict_spec(spec, [_png()])
    assert status == "scored"
    assert passes == 2
    assert text.strip() == "5 mg"


def test_occurrence_alignment_keeps_repeated_and_altered_doses_distinct():
    same = align_critical("5 mg", "5 mg")
    assert same["occurrence_hits"] == 1 and same["occurrence_false_positives"] == 0
    altered = align_critical(".5 mg", "5 mg")
    assert altered["occurrence_hits"] == 0 and altered["occurrence_false_positives"] == 1
    assert align_critical("2.5 mg", "25 mg")["occurrence_hits"] == 0
    assert align_critical("1 mg", "1 g")["occurrence_hits"] == 0
    assert align_critical("25 mcg", "250 mcg")["occurrence_hits"] == 0
    repeated = align_critical("5 mg", "5 mg 5 mg")
    assert repeated["occurrence_hits"] == 1
    assert repeated["occurrence_false_positives"] == 1
    assert align_critical("no 5 mg", "5 mg")["occurrence_hits"] == 1
    assert "no" in align_critical("no 5 mg", "5 mg")["missed_critical_tokens"]
    decision = decide_screen(_view(occurrence_fp=0), _view(occurrence_fp=1))
    assert decision["status"] == "rejected"
    assert "occurrence false positives rose" in decision["reason"]


def _identity(**overrides):
    parts = {
        "identity_version": IDENTITY_VERSION,
        "manifest_sha256": "a" * 64,
        "dataset": "amr",
        "stage": "screen",
        "selection_policy": "screen",
        "case_ids_sha256": "b" * 64,
        "candidate": "jpeg_ctx8192",
        "parent": "jpeg_baseline",
        "model": "glm-ocr:q8_0",
        "model_digest": "c" * 64,
        "num_ctx": 8192,
        "prompt_sha256": "d" * 64,
        "spec_sha256": "e" * 64,
        "temperature": 0,
        "num_predict": 2048,
        "timeout_s": 90,
        "keep_alive": 0,
        "inference_sha256": "1" * 64,
        "transform_sha256": "2" * 64,
        "scoring_sha256": "3" * 64,
        "identity_sha256": "4" * 64,
        "reference_sha256": "5" * 64,
    }
    parts.update(overrides)
    parts["inference_fingerprint"] = inference_fingerprint(parts)
    parts["scoring_fingerprint"] = scoring_fingerprint(parts)
    return parts


def test_legacy_checkpoints_are_not_reused_or_rewritten():
    current = fingerprint(_identity())
    other = fingerprint(_identity(spec_sha256="f" * 64))
    assert current != other
    legacy = {"id": "AMR_035", "status": "scored", "prediction": "5 mg"}
    assert assess_reuse({"AMR_035": legacy}, ["AMR_035"], current) == "legacy_unverified"
    partial = {
        "AMR_035": {
            "identity_version": IDENTITY_VERSION,
            "experiment_fingerprint": current,
            "status": "scored",
            "prediction": "5 mg",
        }
    }
    assert assess_reuse(partial, ["AMR_035", "AMR_039"], current) == "incomplete"
    assert assess_reuse(partial, ["AMR_035"], other) == "fingerprint_mismatch"
    empty = dict(partial["AMR_035"], prediction="")
    assert assess_reuse({"AMR_035": empty}, ["AMR_035"], current) == "invalid"
    assert assess_reuse(partial, ["AMR_035"], current) == "reusable"
    assert assess_reuse({"AMR_099": partial["AMR_035"]}, ["AMR_035"], current) == "extra_case"


def test_second_campaign_lock_fails_without_starting_work(tmp_path):
    first = acquire_lock(tmp_path / "campaign.lock")
    try:
        acquire_lock(tmp_path / "campaign.lock")
        raise AssertionError("second lock was granted")
    except RuntimeError as error:
        assert str(error) == "already_running"
    finally:
        first.close()


def test_duplicate_case_ids_are_rejected(tmp_path):
    payload = {"id": "AMR_001", "status": "failed"}
    (tmp_path / "a.json").write_text(json.dumps(payload))
    (tmp_path / "b.json").write_text(json.dumps(payload))
    try:
        load_run(tmp_path)
        raise AssertionError("duplicate case was accepted")
    except ValueError as error:
        assert str(error) == "PR10_DUPLICATE_CASE"


def _population_case(case_id, distance, chars, status="scored", prediction="5 mg"):
    if status != "scored":
        return {"id": case_id, "status": status, "latency_ms": 5, "prediction": ""}
    return {
        "id": case_id,
        "status": "scored",
        "latency_ms": 5,
        "prediction": prediction,
        "critical_false_positives": 0,
        "metrics": {
            "character_distance": distance,
            "word_distance": 0,
            "ref_chars": chars,
            "ref_words": 1,
            "critical_tokens": [],
        },
    }


def _promotion(inc_rx, cand_rx):
    amr = [_population_case("A", 1, 4, prediction="dose")]
    stats = paired_population(inc_rx, cand_rx)
    assert stats["status"] == "ok"
    shared = set(stats["shared_ids"])
    decision = decide_screen(
        _metrics(amr, inc_rx, {"A"}, shared),
        _metrics(amr, cand_rx, {"A"}, shared),
    )
    decision.update({key: value for key, value in stats.items() if key != "status"})
    return decision


def test_component_hashes_bind_adapter_transform_and_scorer():
    base = implementation_hashes()
    again = implementation_hashes()
    assert base == again
    assert not any(path.endswith(".md") for path in BOUND_FILES)
    adapter = (
        b'"temperature": 0\n"num_predict": 2048\n"keep_alive": 0\n'
        b"timeout: float = 90.0\n# adapter\n"
    )
    changed_adapter = implementation_hashes({
        "backend/services/multimodal_service.py": adapter + b"changed\n",
    })
    assert changed_adapter["inference_sha256"] != base["inference_sha256"]
    assert changed_adapter["scoring_sha256"] == base["scoring_sha256"]
    changed_transform = implementation_hashes({
        "backend/evaluation/pr10_candidate.py": b"transform-v2",
    })
    assert changed_transform["transform_sha256"] != base["transform_sha256"]
    assert changed_transform["scoring_sha256"] == base["scoring_sha256"]
    changed_scorer = implementation_hashes({
        "backend/evaluation/pr10_replay.py": b"scorer-v2",
    })
    assert changed_scorer["scoring_sha256"] != base["scoring_sha256"]
    assert changed_scorer["inference_sha256"] == base["inference_sha256"]
    prompt_changed = _identity(prompt_sha256="f" * 64)
    assert inference_fingerprint(prompt_changed) != inference_fingerprint(_identity())
    assert scoring_fingerprint(prompt_changed) == scoring_fingerprint(_identity())
    digest_changed = fingerprint(_identity(model_digest="9" * 64))
    assert assess_reuse(
        {"AMR_035": {
            "identity_version": IDENTITY_VERSION,
            "experiment_fingerprint": digest_changed,
            "status": "scored",
            "prediction": "5 mg",
        }},
        ["AMR_035"],
        fingerprint(_identity()),
    ) == "fingerprint_mismatch"
    assert fingerprint(_identity(num_ctx=8192)) != fingerprint(_identity(num_ctx=16384))
    assert fingerprint(_identity()) == fingerprint(_identity())


def test_saved_run_validation_rejects_incomplete_or_forged_identity(tmp_path):
    spec = historical_specs()["jpeg_ctx8192"]
    identifiers = ["A", "B"]
    identity = build_identity(
        spec, "screen", "amr", "c" * 64, identifiers,
        reference_hashes={item: "ab" * 32 for item in identifiers},
    )
    cases = [
        _stamp(_population_case(case_id, 1, 4), identity)
        for case_id in identifiers
    ]
    folder = tmp_path / "run"
    _write_verified(folder, identity, cases)
    assert [case["id"] for case in load_verified_run(folder, identity, identifiers)] == identifiers
    before = (folder / "A.json").read_bytes()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "A.json").write_text(json.dumps({"id": "A", "status": "scored", "prediction": "5 mg"}))
    (legacy / "summary.json").write_text(json.dumps(micro_summary([
        _population_case("A", 1, 4),
    ])))
    legacy_before = (legacy / "A.json").read_bytes()
    try:
        load_verified_run(legacy, identity, ["A"])
        raise AssertionError("legacy checkpoint was accepted")
    except LegacyCheckpoint as error:
        assert str(error) == "legacy_unverified"
    assert (legacy / "A.json").read_bytes() == legacy_before
    assert b"identity_version" not in (legacy / "A.json").read_bytes()
    assert (folder / "A.json").read_bytes() == before
    assert classify_saved_run(folder, identity, ["A"])["classification"] == "extra_case"
    assert classify_saved_run(folder, identity, ["A", "B", "A"])["classification"] == "duplicate_case"
    missing = tmp_path / "missing"
    _write_verified(missing, identity, cases[:1])
    assert classify_saved_run(missing, identity, identifiers)["classification"] == "incomplete"
    forged = tmp_path / "forged"
    _write_verified(forged, identity, cases)
    summary = json.loads((forged / "summary.json").read_text())
    summary["experiment_fingerprint"] = "0" * 64
    (forged / "summary.json").write_text(json.dumps(summary))
    assert classify_saved_run(forged, identity, identifiers)["classification"] == "fingerprint_mismatch"
    digest = tmp_path / "digest"
    stamped = [_stamp(_population_case(case_id, 1, 4), identity) for case_id in identifiers]
    for case in stamped:
        case["model_digest"] = "d" * 64
    _write_verified(digest, identity, stamped)
    assert classify_saved_run(digest, identity, identifiers)["classification"] == "model_digest_mismatch"
    prompt = tmp_path / "prompt"
    stamped = [_stamp(_population_case(case_id, 1, 4), identity) for case_id in identifiers]
    for case in stamped:
        case["prompt_sha256"] = "e" * 64
    _write_verified(prompt, identity, stamped)
    assert classify_saved_run(prompt, identity, identifiers)["classification"] == "prompt_mismatch"
    code = tmp_path / "code"
    stamped = [_stamp(_population_case(case_id, 1, 4), identity) for case_id in identifiers]
    for case in stamped:
        case["inference_sha256"] = "f" * 64
        case["inference_fingerprint"] = "f" * 64
    _write_verified(code, identity, stamped)
    assert classify_saved_run(code, identity, identifiers)["classification"] == "implementation_mismatch"


def test_inference_passes_the_frozen_model_on_every_call(monkeypatch):
    monkeypatch.setenv("OLLAMA_OCR_MODEL", "other-ocr:latest")
    seen = []

    def fake(image_bytes, page_number=1, model=None, num_ctx=None, system_prompt=None, user_prompt=None):
        seen.append(model)
        return {"status": "completed", "transcribed_text": "5 mg", "model": model}

    monkeypatch.setattr(pr10_autoresearch, "glm_ocr_infer", fake)
    spec = dict(historical_specs()["jpeg_ctx8192"])
    spec["second_pass"] = True
    text, _latency, status, passes = predict_spec(spec, [_png()])
    assert text.strip()
    assert status == "scored"
    assert passes == 2
    assert seen == [MODEL, MODEL]


def test_wrong_model_result_blocks_the_run(monkeypatch):
    def fake(image_bytes, page_number=1, model=None, num_ctx=None, system_prompt=None, user_prompt=None):
        return {"status": "completed", "transcribed_text": "5 mg", "model": "other-ocr:latest"}

    monkeypatch.setattr(pr10_autoresearch, "glm_ocr_infer", fake)
    try:
        predict_spec(historical_specs()["jpeg_ctx8192"], [_png()])
        raise AssertionError("foreign model was accepted")
    except CheckpointRejected as error:
        assert str(error) == "model_mismatch"


def test_digest_change_blocks_before_a_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(pr10_autoresearch, "PRIVATE", tmp_path)
    monkeypatch.setattr(pr10_autoresearch, "work_items", lambda manifest, stage, dataset: ["A"])
    intake = tmp_path / "selection.json"
    intake.write_text("{}")
    monkeypatch.setattr(pr10_autoresearch, "AMR_INTAKE", intake)
    monkeypatch.setattr(
        pr10_autoresearch, "_amr_case", lambda selection, ident: ([_png()], "5 mg\n", "ab" * 32),
    )
    digests = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(
        pr10_autoresearch, "get_installed_model_digest", lambda model: next(digests),
    )
    monkeypatch.setattr(
        pr10_autoresearch, "reference_hashes_for",
        lambda dataset, identifiers: {item: "ab" * 32 for item in identifiers},
    )
    seen = []

    def fake(image_bytes, page_number=1, model=None, num_ctx=None, system_prompt=None, user_prompt=None):
        seen.append(model)
        return {"status": "completed", "transcribed_text": "5 mg", "model": model}

    monkeypatch.setattr(pr10_autoresearch, "glm_ocr_infer", fake)
    try:
        run_spec(historical_specs()["jpeg_ctx8192"], "screen", "amr", None)
        raise AssertionError("changed digest was accepted")
    except CheckpointRejected as error:
        assert str(error) == "model_digest_mismatch"
    assert seen == [MODEL]
    assert not (tmp_path / "screen" / "jpeg_ctx8192" / "amr" / "summary.json").exists()


def test_paired_rx_gate_ignores_recovered_crops():
    incumbent = [
        _population_case("R1", 1, 10, prediction="10 mg"),
        _population_case("R2", 0, 100, status="failed"),
    ]
    candidate = [
        _population_case("R1", 3, 10, prediction="30 mg"),
        _population_case("R2", 1, 100, prediction="ok"),
    ]
    decision = _promotion(incumbent, candidate)
    assert decision["candidate_all_scored_cer"] < decision["incumbent_all_scored_cer"]
    assert decision["candidate_paired_cer"] > decision["incumbent_paired_cer"]
    assert decision["status"] == "rejected"
    assert "Rx CER worsened" in decision["reason"]
    identical = [
        _population_case("R1", 1, 10),
        _population_case("R2", 1, 40),
    ]
    assert _promotion(identical, identical)["status"] == "rejected"
    disjoint = [
        _population_case("R1", 1, 10, status="failed"),
        _population_case("R2", 0, 40, prediction="ok"),
    ]
    stats = paired_population(incumbent, disjoint)
    assert stats["shared_ids"] == []
    assert decide_screen(
        _metrics([_population_case("A", 1, 4)], incumbent, {"A"}, set()),
        _metrics([_population_case("A", 1, 4)], disjoint, {"A"}, set()),
    )["status"] == "inconclusive"
    lost = [
        _population_case("R1", 1, 10),
        _population_case("R2", 0, 40, status="failed"),
    ]
    assert "Rx coverage fell" in _promotion(identical, lost)["reason"]
    recovered = [
        _population_case("R1", 1, 10, prediction="10 mg"),
        _population_case("R2", 0, 40, prediction="same"),
    ]
    base = [
        _population_case("R1", 1, 10, prediction="10 mg"),
        _population_case("R2", 0, 40, status="failed"),
    ]
    assert _promotion(base, recovered)["status"] == "reliability_candidate"
    better = [
        _population_case("R1", 0, 10, prediction="better"),
        _population_case("R2", 0, 40, prediction="better"),
    ]
    assert _promotion(identical, better)["status"] == "accuracy_candidate"
    assert paired_population(identical, identical[:1])["status"] == "attempted_cohorts_differ"
    assert paired_population(
        [_population_case("R1", 1, 10), _population_case("R1", 1, 10)],
        identical,
    )["status"] == "duplicate_case"


def _patch_references(monkeypatch, reference: bytes = b"5 mg\n") -> None:
    digest = sha(reference)
    monkeypatch.setattr(
        pr10_autoresearch, "reference_hashes_for",
        lambda dataset, identifiers: {item: digest for item in identifiers},
    )
    monkeypatch.setattr(
        pr10_campaign, "reference_bytes_for",
        lambda dataset, identifiers: {item: reference for item in identifiers},
    )


def test_compare_rejects_whitespace_only_cer_drop(monkeypatch, tmp_path):
    monkeypatch.setattr(pr10_campaign, "PRIVATE", tmp_path)
    monkeypatch.setattr(pr10_campaign, "_installed_digest", lambda: "c" * 64)
    _patch_references(monkeypatch)
    monkeypatch.setattr(
        pr10_campaign, "work_items",
        lambda manifest, stage, dataset: ["A"] if dataset == "amr" else ["R1"],
    )
    digest = "c" * 64
    for spec, distance, text in (
        (historical_specs()["jpeg_baseline"], 2, "5  mg"),
        (historical_specs()["jpeg_ctx8192"], 1, "5 mg"),
    ):
        for dataset, cases in (
            ("amr", [_population_case("A", distance, 10, prediction=text)]),
            ("rx", [_population_case("R1", 1, 10, prediction="10 mg")]),
        ):
            identity = build_identity(spec, "screen", dataset, digest, [case["id"] for case in cases])
            folder = tmp_path / "screen" / spec["name"] / dataset
            _write_verified(folder, identity, [_stamp(case, identity) for case in cases])
    decision = _compare("screen", "jpeg_baseline", "jpeg_ctx8192")
    assert decision["status"] == "rejected"
    assert decision["reason"] == "formatting change is not a recognition gain"


def test_line_wrap_only_change_is_not_a_recognition_gain(monkeypatch, tmp_path):
    from evaluation.pr10_replay import has_recognition_change, predictions_differ_only_by_whitespace

    wrapped = [_population_case("A", 2, 24, prediction="take one\ntablet daily")]
    unwrapped = [_population_case("A", 1, 24, prediction="take one tablet daily")]
    changed = [_population_case("A", 1, 24, prediction="take two tablet daily")]
    assert not has_recognition_change(wrapped, unwrapped)
    assert predictions_differ_only_by_whitespace(wrapped, unwrapped)
    assert has_recognition_change(wrapped, changed)

    monkeypatch.setattr(pr10_campaign, "PRIVATE", tmp_path)
    monkeypatch.setattr(pr10_campaign, "_installed_digest", lambda: "c" * 64)
    reference = b"take one tablet daily\n"
    _patch_references(monkeypatch, reference)
    monkeypatch.setattr(
        pr10_campaign, "work_items",
        lambda manifest, stage, dataset: ["A"] if dataset == "amr" else ["R1"],
    )
    digest = "c" * 64
    for spec, distance, text in (
        (historical_specs()["jpeg_baseline"], 2, "take one\ntablet daily"),
        (historical_specs()["jpeg_ctx8192"], 1, "take one tablet daily"),
    ):
        for dataset, cases in (
            ("amr", [_population_case("A", distance, 24, prediction=text)]),
            ("rx", [_population_case("R1", 1, 10, prediction="10 mg")]),
        ):
            identity = build_identity(spec, "screen", dataset, digest, [case["id"] for case in cases])
            folder = tmp_path / "screen" / spec["name"] / dataset
            _write_verified(folder, identity, [_stamp(case, identity, reference) for case in cases])
    decision = _compare("screen", "jpeg_baseline", "jpeg_ctx8192")
    assert decision["status"] == "rejected"
    assert decision["reason"] == "formatting change is not a recognition gain"


def test_compare_refuses_legacy_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(pr10_campaign, "PRIVATE", tmp_path)
    monkeypatch.setattr(pr10_campaign, "_installed_digest", lambda: "c" * 64)
    _patch_references(monkeypatch)
    folder = tmp_path / "screen" / "jpeg_baseline" / "amr"
    folder.mkdir(parents=True)
    case = _population_case("AMR_035", 1, 4)
    (folder / "AMR_035.json").write_text(json.dumps(case))
    summary = micro_summary([case])
    (folder / "summary.json").write_text(json.dumps(summary))
    original = (folder / "AMR_035.json").read_bytes()
    try:
        _compare("screen", "jpeg_baseline", "jpeg_ctx8192")
        raise AssertionError("legacy evidence was compared")
    except LegacyCheckpoint as error:
        assert str(error) == "legacy_unverified"
    assert (folder / "AMR_035.json").read_bytes() == original


def test_budget_stop_does_not_resume_or_rewrite(monkeypatch, tmp_path):
    monkeypatch.setattr(pr10_campaign, "PRIVATE", tmp_path)
    calls = []
    monkeypatch.setattr(pr10_campaign, "run_spec", lambda *args, **kwargs: calls.append(args))
    rows = [
        {"candidate": f"candidate-{index}", "stage": "screen", "status": "discard", "family": "A"}
        for index in range(30)
    ]
    (tmp_path / "decisions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    state = {"status": "stopped", "reason": "experiment_budget", "experiments": 30}
    (tmp_path / "run_state.json").write_text(json.dumps(state))
    legacy = tmp_path / "screen" / "jpeg_ctx8192" / "amr"
    legacy.mkdir(parents=True)
    (legacy / "case.json").write_text(json.dumps({"id": "A", "prediction": "do not touch"}))
    before = (legacy / "case.json").read_bytes()
    state_before = (tmp_path / "run_state.json").read_bytes()
    assert campaign() == 0
    assert calls == []
    assert (legacy / "case.json").read_bytes() == before
    assert (tmp_path / "run_state.json").read_bytes() == state_before


def test_whitespace_only_change_is_not_an_accuracy_win():
    incumbent = [_population_case("R1", 2, 10, prediction="5  mg")]
    candidate = [_population_case("R1", 1, 10, prediction="5 mg")]
    decision = _promotion(incumbent, candidate)
    assert decision["candidate_paired_cer"] < decision["incumbent_paired_cer"]
    assert decision["status"] == "accuracy_candidate"
    from evaluation.pr10_replay import has_recognition_change
    assert not has_recognition_change(incumbent, candidate)


def test_reference_hash_is_part_of_run_identity():
    spec = historical_specs()["jpeg_ctx8192"]
    identifiers = ["R1", "R2"]
    first = build_identity(
        spec, "screen", "rx", "c" * 64, identifiers,
        reference_hashes={item: "a" * 64 for item in identifiers},
    )
    second = build_identity(
        spec, "screen", "rx", "c" * 64, identifiers,
        reference_hashes={"R1": "a" * 64, "R2": "b" * 64},
    )
    assert first["reference_sha256"] != second["reference_sha256"]
    assert first["experiment_fingerprint"] != second["experiment_fingerprint"]
    assert first["inference_fingerprint"] == second["inference_fingerprint"]
    case = _stamp(_population_case("R1", 1, 4), first)
    assert assess_reuse(
        {"R1": {
            "identity_version": IDENTITY_VERSION,
            "experiment_fingerprint": first["experiment_fingerprint"],
            "status": "scored",
            "prediction": "5 mg",
        }},
        ["R1"],
        second["experiment_fingerprint"],
    ) == "fingerprint_mismatch"
    assert case["reference_sha256"] == sha(b"5 mg\n")


def test_changed_reference_bytes_are_not_reused(tmp_path):
    spec = historical_specs()["jpeg_ctx8192"]
    identifiers = ["A"]
    identity = build_identity(
        spec, "screen", "amr", "c" * 64, identifiers,
        reference_hashes={"A": sha(b"5 mg\n")},
    )
    folder = tmp_path / "run"
    _write_verified(folder, identity, [_stamp(_population_case("A", 1, 4), identity)])
    before = (folder / "A.json").read_bytes()
    assert classify_saved_run(
        folder, identity, identifiers, {"A": b"5 mg\n"},
    )["classification"] == "verified"
    assert classify_saved_run(
        folder, identity, identifiers, {"A": b"50 mg\n"},
    )["classification"] == "reference_hash_mismatch"
    assert (folder / "A.json").read_bytes() == before


def test_changed_prediction_is_not_verified_evidence(tmp_path):
    reference = b"5mg"
    spec = historical_specs()["jpeg_ctx8192"]
    identity = build_identity(
        spec, "screen", "amr", "c" * 64, ["A"],
        reference_hashes={"A": sha(reference)},
    )
    stamped = _stamp(_population_case("A", 0, 3, prediction="5mg"), identity, reference)
    folder = tmp_path / "run"
    _write_verified(folder, identity, [stamped])
    assert classify_saved_run(folder, identity, ["A"], {"A": reference})["classification"] == "verified"
    forged = json.loads((folder / "A.json").read_text())
    forged["prediction"] = "50mg"
    (folder / "A.json").write_text(json.dumps(forged))
    cached = (folder / "A.json").read_bytes()
    assert classify_saved_run(folder, identity, ["A"], {"A": reference})["classification"] == "replay_mismatch"
    assert (folder / "A.json").read_bytes() == cached
    consistent = json.loads(cached)
    consistent["metrics"] = score("5mg", "50mg")
    consistent["critical_false_positives"] = critical_false_positives("5mg", "50mg")
    consistent["occurrence_hits"] = 1
    (folder / "A.json").write_text(json.dumps(consistent))
    lied = (folder / "A.json").read_bytes()
    assert classify_saved_run(folder, identity, ["A"], {"A": reference})["classification"] == "replay_mismatch"
    assert (folder / "A.json").read_bytes() == lied


def test_dropped_repeated_dose_is_not_an_accuracy_win():
    reference = "5 mg\n5 mg\nsafe"
    kept = "5 mg\n5 mg\nxxxxxxxxxxxxxxxx"
    dropped = "5 mg\nsafe"

    def case(prediction: str) -> dict:
        aligned = align_critical(reference, prediction)
        return {
            "id": "A",
            "status": "scored",
            "latency_ms": 5,
            "prediction": prediction,
            "critical_false_positives": critical_false_positives(reference, prediction),
            "occurrence_hits": aligned["occurrence_hits"],
            "occurrence_total": aligned["occurrence_total"],
            "occurrence_false_positives": aligned["occurrence_false_positives"],
            "metrics": score(reference, prediction),
        }

    incumbent = case(kept)
    candidate = case(dropped)
    assert incumbent["occurrence_hits"] == 2
    assert candidate["occurrence_hits"] == 1
    rx = [_population_case("R1", 1, 10)]
    inc = _metrics([incumbent], rx, {"A"}, {"R1"})
    cand = _metrics([candidate], rx, {"A"}, {"R1"})
    assert cand["paired_cer"] < inc["paired_cer"]
    assert cand["paired_hits"] == inc["paired_hits"]
    decision = decide_screen(inc, cand)
    assert decision["status"] == "rejected"
    assert "paired occurrence hits fell" in decision["reason"]


def test_dropped_rx_critical_token_is_not_an_accuracy_win():
    reference = "5mg"

    def rx_case(prediction: str) -> dict:
        aligned = align_critical(reference, prediction)
        return {
            "id": "R1",
            "status": "scored",
            "latency_ms": 5,
            "prediction": prediction,
            "critical_false_positives": critical_false_positives(reference, prediction),
            "occurrence_hits": aligned["occurrence_hits"],
            "occurrence_total": aligned["occurrence_total"],
            "occurrence_false_positives": aligned["occurrence_false_positives"],
            "metrics": score(reference, prediction),
        }

    incumbent = rx_case("5mg xxxxxxxxxxxx")
    candidate = rx_case("mg")
    assert incumbent["occurrence_hits"] == 1
    assert candidate["occurrence_hits"] == 0
    assert candidate["occurrence_false_positives"] == 0
    amr = [_population_case("A", 1, 10)]
    inc = _metrics(amr, [incumbent], {"A"}, {"R1"})
    cand = _metrics(amr, [candidate], {"A"}, {"R1"})
    assert cand["rx_cer"] < inc["rx_cer"]
    assert cand["rx_occurrence_fp"] == inc["rx_occurrence_fp"]
    decision = decide_screen(inc, cand)
    assert decision["status"] == "rejected"
    assert "Rx occurrence hits fell" in decision["reason"]


def test_resolve_spec_follows_a_fourth_generation_name():
    name = "jpeg_ctx8192__no_infer__png__contrast__grayscale"
    spec = resolve_spec(name)
    assert spec["name"] == name
    assert spec["prompt"] == "no_infer"
    assert spec["encode"] == "png"
    assert spec["contrast"] == "autocontrast"
    assert spec["grayscale"] is True
    try:
        resolve_spec(name + "__not-a-mutation")
        raise AssertionError("unknown mutation was resolved")
    except KeyError:
        pass


def test_unpaired_false_positive_drop_is_not_an_accuracy_win():
    swapped = decide_screen(_view(fp=2, paired_fp=1), _view(fp=0, paired_fp=1))
    assert swapped["status"] == "rejected"
    assert "no measured gain" in swapped["reason"]
    assert decide_screen(_view(paired_fp=2), _view(paired_fp=1))["status"] == "accuracy_candidate"


def test_amr_pages_must_match_the_frozen_partition(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"page-v1")
    digest = sha(b"page-v1")
    other = sha(b"page-v2")
    manifest = {
        "amr": {
            "development": [{"id": "AMR_035", "page_sha256": [digest]}],
            "untouched_holdout": [{"id": "AMR_099", "page_sha256": [other]}],
        }
    }
    selection = {
        "source_root": str(tmp_path),
        "all_records": [
            {"id": "AMR_035", "pages": [{"path": "page.png", "sha256": digest}]},
            {"id": "AMR_099", "pages": [{"path": "holdout.png", "sha256": other}]},
        ],
    }
    read = []

    def read_page(path):
        read.append(path.name)
        return path.read_bytes()

    require_frozen_amr_pages(["AMR_035"], manifest, selection, read_page)
    assert read == ["page.png"]
    changed = {
        "source_root": str(tmp_path),
        "all_records": [
            {"id": "AMR_035", "pages": [{"path": "page.png", "sha256": other}]},
        ],
    }
    try:
        require_frozen_amr_pages(["AMR_035"], manifest, changed, read_page)
        raise AssertionError("changed intake hash was accepted")
    except CheckpointRejected as error:
        assert str(error) == "source_hash_mismatch"
    page.write_bytes(b"page-v2")
    try:
        require_frozen_amr_pages(["AMR_035"], manifest, selection, read_page)
        raise AssertionError("changed page bytes were accepted")
    except CheckpointRejected as error:
        assert str(error) == "source_hash_mismatch"


def test_historical_audit_counts_legacy_without_writing(tmp_path):
    run = tmp_path / "screen" / "old" / "amr"
    run.mkdir(parents=True)
    (run / "A.json").write_text(json.dumps({"id": "A", "status": "failed"}))
    (run / "summary.json").write_text("{}")
    before = (run / "A.json").read_bytes()
    assert audit_saved_runs(tmp_path) == {
        "runs": 1, "legacy_unverified": 1, "verified": 0, "other": 0,
    }
    assert (run / "A.json").read_bytes() == before


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _stamp(case: dict, identity: dict, reference: bytes = b"5 mg\n") -> dict:
    stamped = dict(case)
    stamped.update({
        "identity_version": IDENTITY_VERSION,
        "model": identity["model"],
        "model_digest": identity["model_digest"],
        "prompt_sha256": identity["prompt_sha256"],
        "candidate": identity["candidate"],
        "experiment_fingerprint": identity["experiment_fingerprint"],
        "inference_fingerprint": identity["inference_fingerprint"],
        "scoring_fingerprint": identity["scoring_fingerprint"],
        "inference_sha256": identity["inference_sha256"],
        "transform_sha256": identity["transform_sha256"],
        "scoring_sha256": identity["scoring_sha256"],
        "identity_sha256": identity["identity_sha256"],
        "reference_sha256": sha(reference),
    })
    prediction = stamped.get("prediction")
    if stamped.get("status") == "scored" and isinstance(prediction, str) and prediction.strip():
        text = reference_text(reference)
        aligned = align_critical(text, prediction)
        stamped["metrics"] = score(text, prediction)
        stamped["critical_false_positives"] = critical_false_positives(text, prediction)
        stamped["occurrence_hits"] = aligned["occurrence_hits"]
        stamped["occurrence_total"] = aligned["occurrence_total"]
        stamped["occurrence_false_positives"] = aligned["occurrence_false_positives"]
    return stamped


def _write_verified(folder, identity: dict, cases: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for case in cases:
        (folder / f"{case['id']}.json").write_text(json.dumps(case))
    summary = micro_summary(cases)
    summary["experiment_fingerprint"] = identity["experiment_fingerprint"]
    summary["identity_version"] = IDENTITY_VERSION
    (folder / "summary.json").write_text(json.dumps(summary))


def test_untouched_jpeg_matches_the_frozen_encoder():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    original = buffer.getvalue()
    assert render_regions(historical_specs()["jpeg_baseline"], original) == [infer_image(original)]
    assert render_regions(historical_specs()["jpeg_ctx8192"], original) == [infer_image(original)]
