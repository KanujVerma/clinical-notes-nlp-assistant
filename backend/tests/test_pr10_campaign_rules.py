"""Promotion rules and candidate diffs. No model calls."""
from __future__ import annotations

import io
import json

from PIL import Image

from evaluation.pr10_campaign import _metrics
from evaluation.pr10_autoresearch import completed_status
from evaluation.pr10_campaign import acquire_lock
from evaluation.pr10_candidate import changed_fields, historical_specs, mutation_queue, render_regions
from evaluation.pr10_identity import IDENTITY_VERSION, assess_reuse, fingerprint
from evaluation.pr10_replay import align_critical, cohorts_match, decide_screen, load_run, rescore_case
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
    assert decide_screen(_view(), _view(rx_cer=None))["status"] == "rejected"
    assert decide_screen(_view(rx_cer=None), _view())["reason"] == "Rx CER is undefined"
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
    return {
        "status": "scored",
        "prediction": prediction,
        "reference_sha256": digest,
        "metrics": score(reference, prediction),
        "critical_false_positives": 0,
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


def test_empty_transcription_is_not_scored():
    assert completed_status("") == "empty_transcription"
    assert completed_status("   ") == "empty_transcription"
    assert completed_status(None) == "empty_transcription"
    assert completed_status("5 mg") == "scored"


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
    }
    parts.update(overrides)
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
    assert assess_reuse({"AMR_099": partial["AMR_035"]}, ["AMR_035"], current) == "extra"


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


def test_untouched_jpeg_matches_the_frozen_encoder():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    original = buffer.getvalue()
    assert render_regions(historical_specs()["jpeg_baseline"], original) == [infer_image(original)]
    assert render_regions(historical_specs()["jpeg_ctx8192"], original) == [infer_image(original)]
