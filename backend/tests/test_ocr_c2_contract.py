"""Synthetic campaign-2 contract. No Ollama and no private handwriting."""
from __future__ import annotations

import ast

from PIL import Image

from evaluation.ocr_c2.budget import BudgetExhausted, Ledger
from evaluation.ocr_c2.controller import TransitionRejected, acquire_lock, step, write_checkpoint
from evaluation.ocr_c2.downloads import DownloadRefused, authorize
from evaluation.ocr_c2.holdout import HoldoutSealed, cohort_for, refuse_tuning_ids, sealed_ids
from evaluation.ocr_c2.identity import request_identity
from evaluation.ocr_c2.integrate import enabled, recognize
from evaluation.ocr_c2.metrics import (
    bootstrap_relative, meets_relative_reduction, micro_rate, nearest_rank_p95,
    normalize_recognition, occurrence_case, preserves_successes, safety_ok, select_finalist,
    whitespace_only,
)
from evaluation.ocr_c2.native import (
    NATIVE_PROMPT, build_native_payload, control_call, interpret_native_response,
)
from evaluation.ocr_c2.protocol import CAMPAIGN_ID, load_protocol
from evaluation.ocr_c2.replay import replay_case
from evaluation.ocr_c2.runner import run_page
from evaluation.ocr_c2.segment import segment_page
from evaluation.public_amr_benchmark import score, sha


def _page(width, height, ink):
    image = Image.new("RGB", (width, height), "white")
    draw = image.load()
    for y, xs in ink:
        for x in xs:
            draw[x, y] = (0, 0, 0)
    return image


def _rows(start, end, width):
    return [(y, range(width)) for y in range(start, end)]


def test_protocol_identity_is_campaign_2():
    protocol = load_protocol()
    assert protocol["campaign_id"] == CAMPAIGN_ID
    assert protocol["base_commit"] == "bdbf5f8360344c6ae1fdad716de142f85b169042"
    assert protocol["budgets"]["global_model_seconds"] == 21600
    assert protocol["budgets"]["candidate_slots"] == 8
    assert set(protocol["candidates"]) == {"B8192", "Blegacy", "N1", "N2", "N3", "N4", "N5", "N6"}


def test_native_request_omits_json_grammar_and_names_the_model():
    payload = build_native_payload(b"image", "N1")
    assert payload["prompt"] == NATIVE_PROMPT
    assert payload["model"] == "glm-ocr:q8_0"
    assert payload["stream"] is False
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_ctx"] == 8192
    assert payload["options"]["num_predict"] == 2048
    assert payload["keep_alive"] == 0
    assert "format" not in payload
    assert "system" not in payload
    assert "raw" not in payload
    longer = build_native_payload(b"image", "N2")
    assert longer["options"]["num_predict"] == 4096
    assert longer["options"]["num_ctx"] == 8192


def test_controls_pass_the_explicit_model(monkeypatch):
    seen = []

    def infer(image_bytes, page_number=1, model=None, num_ctx=None, system_prompt=None, user_prompt=None):
        seen.append((model, num_ctx, system_prompt, user_prompt))
        return {"status": "completed", "model": model}

    control_call("B8192", b"img", 1, infer)
    control_call("Blegacy", b"img", 1, infer)
    assert seen == [("glm-ocr:q8_0", 8192, None, None), ("glm-ocr:q8_0", None, None, None)]


def test_digest_drift_and_generation_limit_are_not_scored():
    try:
        interpret_native_response(
            {"model": "other", "response": "5 mg", "done": True, "model_digest": "aa"},
            "glm-ocr:q8_0", "aa",
        )
        raise AssertionError("foreign model accepted")
    except ValueError as error:
        assert "model_mismatch" in str(error)
    limited = interpret_native_response(
        {"model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "done_reason": "length", "model_digest": "aa"},
        "glm-ocr:q8_0", "aa",
    )
    assert limited["scored"] is False and limited["status"] == "generation_limit"
    empty = interpret_native_response(
        {"model": "glm-ocr:q8_0", "response": "  ", "done": True, "done_reason": "stop", "model_digest": "aa"},
        "glm-ocr:q8_0", "aa",
    )
    assert empty["status"] == "empty_transcription"
    try:
        interpret_native_response(
            {"model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "model_digest": "bb"},
            "glm-ocr:q8_0", "aa",
        )
        raise AssertionError("digest drift accepted")
    except ValueError as error:
        assert "model_digest_mismatch" in str(error)


def test_blank_region_makes_the_page_incomplete(tmp_path):
    image = _page(40, 100, _rows(0, 20, 40) + _rows(40, 60, 40) + _rows(80, 100, 40))
    calls = {"n": 0}

    def transport(prepared, candidate, allowed):
        calls["n"] += 1
        text = "5 mg" if calls["n"] == 1 else ""
        return {
            "model": "glm-ocr:q8_0", "response": text, "done": True, "done_reason": "stop",
            "elapsed_seconds": 1, "model_digest": "aa",
        }

    ledger = Ledger(tmp_path / "ledger.jsonl", cap_seconds=100)
    result = run_page(image, "N3", transport, ledger, "page", "aa")
    assert result["completed"] is False
    assert result["status"] == "incomplete"
    assert len(result["regions"]) >= 2


def test_segmentation_conserves_rows_and_flags_columns():
    bands = _page(40, 90, _rows(0, 20, 40) + _rows(30, 50, 40) + _rows(60, 80, 40))
    layout = segment_page(bands, "bands")
    assert layout["regions"][0]["y0"] == 0
    assert layout["regions"][-1]["y1"] == 90
    assert [item["y0"] for item in layout["regions"][1:]] == [item["y1"] for item in layout["regions"][:-1]]
    lines = segment_page(bands, "lines")
    assert lines["line_segmentation_unavailable"] is False
    assert lines["regions"][0]["y0"] == 0 and lines["regions"][-1]["y1"] == 90
    solid = _page(30, 40, _rows(0, 40, 30))
    fallback = segment_page(solid, "bands")
    assert fallback["segmentation_fallback"] is True
    assert len(fallback["regions"]) == 1
    columns = _page(100, 40, [(y, list(range(0, 16)) + list(range(84, 100))) for y in range(40)])
    uncertain = segment_page(columns, "lines")
    assert uncertain["reading_order_uncertain"] is True
    assert len(uncertain["regions"]) == 1
    short = _page(40, 50, _rows(0, 20, 40) + _rows(28, 32, 40) + _rows(40, 50, 40))
    merged = segment_page(short, "lines")
    assert all(item["y1"] - item["y0"] >= 16 or len(merged["regions"]) == 1 for item in merged["regions"])


def test_whitespace_cannot_win_and_dose_changes_stay_visible():
    assert whitespace_only("5 mg", "5  mg")
    assert normalize_recognition("5 mg\r\n") == "5 mg"
    assert not meets_relative_reduction(0.10, 0.10)
    assert meets_relative_reduction(0.09, 0.10)
    assert not meets_relative_reduction(0.091, 0.10)
    assert not meets_relative_reduction(0.0, 0.0)
    assert occurrence_case("5 mg\n5 mg", "5 mg")["occurrence_hits"] == 1
    assert occurrence_case(".5 mg", "5 mg")["occurrence_hits"] == 0
    assert occurrence_case("5 mg", "50 mg")["occurrence_hits"] == 0
    assert micro_rate([], []) is None
    assert not preserves_successes({"A", "B"}, {"A"})
    assert not safety_ok(
        {"occurrence_hits": 2, "occurrence_false_positives": 0},
        {"occurrence_hits": 1, "occurrence_false_positives": 0},
    )


def test_selection_rule_uses_the_near_best_set():
    assert nearest_rank_p95([10, 20, 30, 40]) == 40
    common = {
        "provenance_ok": True, "confirmation_complete": True, "preserves_successes": True,
        "safety_ok": True, "baseline_norm_cer": 0.40, "strict_worse": False,
        "norm_wer_worse": False, "rx_worse": False, "full_cohort_worse": False,
        "recognition_change": True, "calls": 1,
    }
    rows = [
        {**common, "candidate": "N3", "paired_norm_cer": 0.30, "cold_page_seconds": [50, 55, 70, 80]},
        {**common, "candidate": "N1", "paired_norm_cer": 0.305, "cold_page_seconds": [20, 22, 24, 30]},
        {**common, "candidate": "N4", "paired_norm_cer": 0.20, "cold_page_seconds": [90, 90, 90, 90]},
        {**common, "candidate": "spaces", "paired_norm_cer": 0.30, "recognition_change": False, "cold_page_seconds": [10]},
    ]
    decision = select_finalist(rows)
    assert decision["status"] == "selected"
    assert decision["candidate"] == "N1"
    assert "N4" not in decision["near_best"]
    blocked = select_finalist([{**common, "candidate": "slow", "paired_norm_cer": 0.30, "cold_page_seconds": [61, 61, 61, 90]}])
    assert blocked["status"] == "latency_blocker"


def test_budget_stops_inside_the_call_loop_and_charges_crashes(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", cap_seconds=10)
    assert ledger.begin("a", 90) == 10
    ledger.finish("a", 10)
    try:
        ledger.begin("b", 90)
        raise AssertionError("budget continued")
    except BudgetExhausted:
        pass
    crashed = Ledger(tmp_path / "crash.jsonl", cap_seconds=30)
    crashed.begin("c", 12)
    crashed.recover_crashes()
    assert crashed.charged() == 12
    image = _page(20, 20, _rows(0, 20, 20))

    def transport(prepared, candidate, allowed):
        return {
            "model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "done_reason": "stop",
            "elapsed_seconds": 1, "model_digest": "aa",
        }

    stopped = run_page(image, "N1", transport, ledger, "again", "aa")
    assert stopped["status"] == "budget_blocked"
    assert stopped["completed"] is False


def test_replay_rejects_a_changed_prediction():
    reference = b"5 mg\n"
    prediction = "5 mg"
    aligned = occurrence_case(reference_text(reference), prediction)
    case = {
        "status": "scored",
        "prediction": prediction,
        "reference_sha256": sha(reference),
        "metrics": score(reference_text(reference), prediction),
        "occurrence_hits": aligned["occurrence_hits"],
        "occurrence_total": aligned["occurrence_total"],
        "occurrence_false_positives": aligned["occurrence_false_positives"],
        "normalized_prediction": normalize_recognition(prediction),
    }
    assert replay_case(case, reference)["classification"] == "verified"
    forged = dict(case)
    forged["prediction"] = "50 mg"
    try:
        replay_case(forged, reference)
        raise AssertionError("forged prediction verified")
    except ValueError as error:
        assert str(error) == "replay_mismatch"


def reference_text(raw: bytes) -> str:
    from evaluation.pr10_replay import reference_text as decode
    return decode(raw)


def test_holdout_ids_are_refused_before_freeze():
    screen = cohort_for("screen", "amr")
    sealed = sealed_ids()
    assert not set(screen) & sealed["amr"]
    assert len(screen) == 8
    try:
        refuse_tuning_ids(list(sealed["amr"])[:1])
        raise AssertionError("holdout id was tunable")
    except HoldoutSealed:
        pass
    try:
        cohort_for("holdout", "amr", freeze={"state": "screening", "finalist": "N1"})
        raise AssertionError("unfrozen holdout opened")
    except HoldoutSealed:
        pass
    opened = cohort_for("holdout", "amr", freeze={"state": "holdout", "finalist": "N1"})
    assert set(opened) == sealed["amr"]


def test_second_controller_does_not_start(tmp_path):
    first = acquire_lock(tmp_path / "campaign.lock")
    try:
        acquire_lock(tmp_path / "campaign.lock")
        raise AssertionError("second controller started")
    except RuntimeError as error:
        assert str(error) == "already_running"
    finally:
        first.close()


def test_controller_rejects_a_skipped_review():
    assert step("preflight", "preflight_ok") == "review_ready"
    try:
        step("preflight", "review_passed")
        raise AssertionError("review was skipped")
    except TransitionRejected:
        pass
    assert step("selecting", "no_candidate") == "stopped"


def test_checkpoint_requires_its_fields(tmp_path):
    try:
        write_checkpoint(tmp_path / "state.json", {"state": "preflight"})
        raise AssertionError("thin checkpoint accepted")
    except ValueError as error:
        assert str(error) == "OCR_C2_CHECKPOINT"


def test_download_cap_refuses_bin_and_network_is_not_imported_for_execution():
    protocol = load_protocol()["trocr_authorized_files"]["files"]
    files = [{"name": name, "size": size} for name, size in protocol.items()]
    decision = authorize(files)
    assert decision["downloaded"] is False
    assert decision["bytes"] < 5_000_000_000
    try:
        authorize(files + [{"name": "pytorch_model.bin", "size": 10}])
        raise AssertionError("bin weight authorized")
    except DownloadRefused:
        pass
    source = open("backend/evaluation/ocr_c2/downloads.py").read()
    tree = ast.parse(source)
    imported = [node.names[0].name for node in tree.body if isinstance(node, ast.Import)]
    imported += [node.module for node in tree.body if isinstance(node, ast.ImportFrom)]
    assert "transformers" not in imported
    assert "urllib" not in imported


def test_default_integration_preserves_reviewed_state(monkeypatch):
    monkeypatch.delenv("OCR_C2_ENABLED", raising=False)
    reviewed = {"dose": "5 mg", "reviewed": True}
    result = recognize(b"img", reviewed)
    assert enabled() is False
    assert result["status"] == "disabled"
    assert result["reviewed"] == reviewed
    assert result["transcription"] is None


def test_fingerprints_change_with_the_candidate_not_the_partition_bytes_alone():
    first = request_identity("N1", "amr", ["AMR_001"], "abc")
    second = request_identity("N2", "amr", ["AMR_001"], "abc")
    assert first["experiment_fingerprint"] != second["experiment_fingerprint"]
    assert first["identity_version"] == "ocr_c2_identity_v1"


def test_bootstrap_is_undefined_when_the_denominator_is_zero():
    empty = bootstrap_relative([[(0, 0)]], replicates=20, seed=20261101)
    assert empty["point"] is None
    stable_a = bootstrap_relative([[(1, 10)], [(2, 10)]], replicates=30, seed=20261101)
    stable_b = bootstrap_relative([[(1, 10)], [(2, 10)]], replicates=30, seed=20261101)
    assert stable_a == stable_b
    assert load_protocol()["budgets"]["bootstrap_replicates"] == 10000


def test_keep_alive_variant_is_labeled_separately():
    resident = build_native_payload(b"image", "N5", keep_alive="5m")
    assert resident["keep_alive"] == "5m"
    assert resident["prompt"] == NATIVE_PROMPT
    assert "format" not in resident
