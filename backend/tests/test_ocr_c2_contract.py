"""Synthetic campaign-2 contract. No Ollama and no private handwriting."""
from __future__ import annotations

import ast
import io
import time
from pathlib import Path

from PIL import Image

from evaluation.ocr_c2.budget import BudgetExhausted, Ledger
from evaluation.ocr_c2.controller import (
    TransitionRejected, acquire_lock, assess_optional, step, write_checkpoint,
)
from evaluation.ocr_c2.downloads import DownloadRefused, authorize
from evaluation.ocr_c2.holdout import HoldoutSealed, cohort_for, refuse_tuning_ids, sealed_ids
from evaluation.ocr_c2.identity import (
    INFERENCE_FILES, INFERENCE_SYMBOLS, SCORING_FILES, SCORING_SYMBOLS,
    control_hash, inference_hash, request_identity, scoring_hash,
)
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
from evaluation.ocr_c2.screen_driver import (
    accept_saved_case, accept_saved_page, control_response, next_request_prefix, score_document,
)
from evaluation.ocr_c2.segment import orient_page, segment_page
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


def test_exploration_allowance_is_checked_before_every_region(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger._append({"request_id": "seed", "event": "finish", "charged_seconds": 7190})
    calls = []

    def transport(prepared, candidate, allowed):
        calls.append(allowed)
        return {
            "model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "done_reason": "stop",
            "elapsed_seconds": 30, "model_digest": "aa",
        }

    image = _page(40, 100, _rows(0, 20, 40) + _rows(40, 60, 40) + _rows(80, 100, 40))
    result = run_page(image, "N3", transport, ledger, "explore", "aa", phase="exploration")
    assert calls == [10]
    assert result["status"] == "budget_blocked"
    assert ledger.exploration_blocked() is True


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
    omitted = {key: value for key, value in common.items() if key not in {"provenance_ok", "confirmation_complete"}}
    hidden = select_finalist([{**omitted, "candidate": "N1", "paired_norm_cer": 0.30, "cold_page_seconds": [10, 10, 10, 10]}])
    assert hidden["status"] == "no_candidate"
    assert hidden["rejected"][0]["reasons"] == ["invalid"]


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
    overrun = Ledger(tmp_path / "overrun.jsonl", cap_seconds=100)
    assert overrun.begin("over", 90) == 90
    overrun.finish("over", 95)
    assert overrun.charged() == 95
    assert overrun.begin("next", 10) == 5
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


def test_failed_native_screen_reaches_optional_eligibility():
    assert step("screening", "nonqualifying") == "optional_model"
    assert step("screening", "budget_blocked") == "stopped"
    assert step("screening", "integrity_blocked") == "stopped"
    eligible = {
        "native_routes_failed": True,
        "page_count": 8,
        "full_page_layouts": 2,
        "split_line_pages": 6,
        "download_compatible": True,
        "budget_sufficient": True,
        "review_and_ci_complete": True,
    }
    assert assess_optional(eligible) == "prerequisites_met"
    assert step("optional_model", "prerequisites_met") == "optional_model"


def test_optional_phase_stays_closed_when_a_prerequisite_fails():
    observed = {
        "native_routes_failed": True,
        "page_count": 8,
        "full_page_layouts": 7,
        "split_line_pages": 1,
        "download_compatible": True,
        "budget_sufficient": True,
        "review_and_ci_complete": True,
    }
    assert assess_optional(observed) == "geometry_blocked"
    assert step("optional_model", "geometry_blocked") == "stopped"
    blocked = dict(observed, page_count=8, full_page_layouts=2, split_line_pages=6)
    assert assess_optional(dict(blocked, download_compatible=False)) == "download_blocked"
    assert assess_optional(dict(blocked, budget_sufficient=False)) == "budget_blocked"
    assert assess_optional(dict(blocked, review_and_ci_complete=False)) == "review_blocked"
    assert assess_optional(dict(blocked, integrity_blocked=True)) == "integrity_blocked"
    assert assess_optional(dict(blocked, budget_exhausted=True)) == "budget_blocked"
    assert step("optional_model", "download_blocked") == "stopped"
    assert step("optional_model", "review_blocked") == "stopped"


def test_control_termination_is_not_rewritten_as_a_stop(tmp_path):
    limited = control_response({
        "status": "completed",
        "transcribed_text": "5 mg",
        "done": True,
        "done_reason": "length",
    }, "aa")
    assert limited["done_reason"] == "length"
    assert limited["response"] == "5 mg"
    missing = control_response({"status": "completed", "transcribed_text": "5 mg"}, "aa")
    assert missing["done"] is False
    assert missing["done_reason"] is None
    image = _page(20, 20, _rows(0, 10, 20))
    ledger = Ledger(tmp_path / "ledger.jsonl", cap_seconds=100)
    result = run_page(image, "B8192", lambda *_args: limited, ledger, "control", "aa")
    assert result["completed"] is False
    assert result["regions"][0]["status"] == "generation_limit"


def test_saved_screen_evidence_must_match_before_reuse():
    identity = request_identity("N1", "amr", ["A"], "abc")
    reference = b"a"
    case = score_document(
        [{"completed": True, "prediction": "a", "regions": [], "page_seconds": 1}],
        sha(reference),
        reference,
        identity,
    )
    accept_saved_case(case, identity, sha(reference), reference)
    other = request_identity("N1", "amr", ["B"], "abc")
    try:
        accept_saved_case(case, other, sha(reference), reference)
        raise AssertionError("stale case was reused")
    except ValueError as error:
        assert str(error) == "OCR_C2_STALE_EVIDENCE"
    page = {
        "status": "scored",
        "source_sha256": "source",
        "reference_sha256": "reference",
        "experiment_fingerprint": identity["experiment_fingerprint"],
        "scoring_sha256": identity["scoring_sha256"],
        "regions": [{"order": 0, "status": "scored"}],
    }
    try:
        accept_saved_page(page, identity, "source", "reference")
        raise AssertionError("page without a crop hash was reused")
    except ValueError as error:
        assert str(error) == "OCR_C2_STALE_EVIDENCE"
    page["regions"][0]["crop_sha256"] = "crop"
    accept_saved_page(page, identity, "source", "reference")


def test_sanitized_driver_keeps_private_paths_out():
    source = Path(__file__).parents[1].joinpath("evaluation/ocr_c2/screen_driver.py").read_text()
    assert "/Users/" not in source
    assert "handwriting-private" not in source
    assert next_request_prefix("N1-amr-doc-p0", set()) == "N1-amr-doc-p0"
    assert next_request_prefix("N1-amr-doc-p0", {"N1-amr-doc-p0-0"}) == "N1-amr-doc-p0-r2"


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
    assert first["identity_version"] == "ocr_c2_identity_v5"
    assert "control_sha256" not in first
    assert first["inference_sha256"] != first["scoring_sha256"]


def test_bootstrap_is_undefined_when_the_denominator_is_zero():
    empty = bootstrap_relative([[(0, 0, 0)]], replicates=20, seed=20261101)
    assert empty["point"] is None
    assert bootstrap_relative([[(0, 5, 100)]], replicates=10, seed=1)["point"] is None
    stable_a = bootstrap_relative([[(4, 1, 10)], [(8, 2, 10)]], replicates=30, seed=20261101)
    stable_b = bootstrap_relative([[(4, 1, 10)], [(8, 2, 10)]], replicates=30, seed=20261101)
    assert stable_a == stable_b
    assert load_protocol()["budgets"]["bootstrap_replicates"] == 10000
    improved = bootstrap_relative([[(40, 20, 100)], [(40, 20, 100)]], replicates=40, seed=20261101)
    regressed = bootstrap_relative([[(10, 20, 100)], [(10, 20, 100)]], replicates=40, seed=20261101)
    assert improved["point"] == 0.5 and improved["low"] > 0
    assert regressed["point"] == -1.0 and regressed["high"] < 0
    mixed = bootstrap_relative(
        [[(40, 20, 100)], [(10, 20, 100)]], replicates=200, seed=20261101,
    )
    assert mixed["low"] <= 0 <= mixed["high"]
    hidden = bootstrap_relative([[(10, 0, 100)], [(0, 1, 100)]], replicates=40, seed=20261101)
    assert hidden["point"] == 0.9
    assert hidden["undefined_draws"] > 0
    assert hidden["low"] is None and hidden["high"] is None


def test_keep_alive_variant_is_labeled_separately():
    resident = build_native_payload(b"image", "N5", parent="N1")
    assert resident["keep_alive"] == "5m"
    assert resident["prompt"] == NATIVE_PROMPT
    assert "format" not in resident


def test_crops_follow_exif_orientation():
    raw = Image.new("RGB", (12, 36), "white")
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    raw.save(buffer, format="JPEG", exif=exif)
    buffer.seek(0)
    stored = Image.open(buffer)
    stored.load()
    oriented = orient_page(stored)
    assert oriented.size != stored.size
    layout = segment_page(stored, "page")
    assert (layout["width"], layout["height"]) == oriented.size
    assert stored.size[0] < layout["width"] or stored.size[1] < layout["height"]


def test_outer_whitespace_stays_with_the_text_band():
    ink = _rows(100, 120, 40) + _rows(200, 220, 40) + _rows(300, 320, 40)
    page = _page(40, 400, ink)
    layout = segment_page(page, "lines")
    ink_rows = set(range(100, 120)) | set(range(200, 220)) | set(range(300, 320))
    assert layout["regions"][0]["y0"] == 0
    assert layout["regions"][-1]["y1"] == 400
    assert all(region["has_ink"] for region in layout["regions"])
    assert all(any(row in ink_rows for row in range(region["y0"], region["y1"])) for region in layout["regions"])
    assert len(layout["regions"]) == 3


def test_n5_inherits_its_parent_geometry_and_cap(tmp_path):
    longer = build_native_payload(b"image", "N5", parent="N2")
    assert longer["options"]["num_predict"] == 4096
    assert longer["options"]["num_ctx"] == 8192
    assert longer["keep_alive"] == "5m"
    try:
        build_native_payload(b"image", "N5")
        raise AssertionError("N5 ran without a parent")
    except ValueError as error:
        assert str(error) == "OCR_C2_N5_PARENT"
    image = _page(40, 100, _rows(0, 20, 40) + _rows(40, 60, 40) + _rows(80, 100, 40))

    def transport(prepared, candidate, allowed):
        return {
            "model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "done_reason": "stop",
            "elapsed_seconds": 1, "model_digest": "aa",
        }

    lines = run_page(image, "N5", transport, Ledger(tmp_path / "lines.jsonl", cap_seconds=100), "lines", "aa", parent="N4")
    whole = run_page(image, "N5", transport, Ledger(tmp_path / "page.jsonl", cap_seconds=100), "page", "aa", parent="N1")
    assert len(lines["regions"]) > 1
    assert len(whole["regions"]) == 1
    by_lines = request_identity("N5", "amr", ["A"], "abc", parent="N4")
    by_cap = request_identity("N5", "amr", ["A"], "abc", parent="N2")
    assert by_lines["geometry"] == "lines"
    assert by_cap["num_predict"] == 4096
    assert by_lines["experiment_fingerprint"] != by_cap["experiment_fingerprint"]


def test_scoring_hash_is_not_the_inference_hash():
    inference_names = {name for _path, names in INFERENCE_SYMBOLS for name in names}
    scoring_names = {name for _path, names in SCORING_SYMBOLS for name in names}
    assert "infer_image" in inference_names
    assert "score" in scoring_names
    assert "infer_image" not in scoring_names
    assert "score" not in inference_names
    assert "backend/evaluation/ocr_c2/segment.py" in INFERENCE_FILES
    assert "backend/evaluation/ocr_c2/segment.py" not in SCORING_FILES
    assert "backend/services/multimodal_service.py" not in INFERENCE_FILES
    assert inference_hash() != scoring_hash()
    ident = request_identity("N1", "amr", ["A"], "abc")
    assert ident["inference_sha256"] == inference_hash()
    assert ident["scoring_sha256"] == scoring_hash()


def test_scorer_edit_does_not_change_the_inference_fingerprint(monkeypatch):
    from evaluation.ocr_c2 import identity

    before_inference = identity.inference_hash()
    before_scoring = identity.scoring_hash()
    before_control = identity.control_hash()
    original = identity._read

    def revised(relative: str) -> str:
        text = original(relative)
        if relative == "backend/evaluation/public_amr_benchmark.py":
            return text.replace(
                "def score(reference: str, hypothesis: str) -> dict:",
                "def score(reference: str, hypothesis: str) -> dict:\n    \"scorer-only revision\"",
                1,
            )
        return text

    monkeypatch.setattr(identity, "_read", revised)
    assert identity.inference_hash() == before_inference
    assert identity.scoring_hash() != before_scoring
    assert identity.control_hash() == before_control


def test_control_prompt_edit_changes_only_the_control_fingerprint(monkeypatch):
    from evaluation.ocr_c2 import identity

    before_native = request_identity("N1", "amr", ["A"], "abc")
    before_control = request_identity("B8192", "amr", ["A"], "abc")
    assert before_control["control_sha256"] == control_hash()
    original = identity._read

    def revised(relative: str) -> str:
        text = original(relative)
        if relative == "backend/services/multimodal_service.py":
            return text.replace(
                '"num_predict": 2048',
                '"num_predict": 2049',
                1,
            )
        return text

    monkeypatch.setattr(identity, "_read", revised)
    native = request_identity("N1", "amr", ["A"], "abc")
    control = request_identity("B8192", "amr", ["A"], "abc")
    assert native["experiment_fingerprint"] == before_native["experiment_fingerprint"]
    assert native["inference_sha256"] == before_native["inference_sha256"]
    assert control["control_sha256"] != before_control["control_sha256"]
    assert control["experiment_fingerprint"] != before_control["experiment_fingerprint"]


def _stopped(text: str) -> dict:
    return {
        "model": "glm-ocr:q8_0", "response": text, "done": True, "done_reason": "stop",
        "elapsed_seconds": 1, "model_digest": "aa",
    }


def test_empty_blank_page_stays_incomplete(tmp_path):
    image = _page(40, 80, [])

    def transport(prepared, candidate, allowed):
        return _stopped("  ")

    result = run_page(image, "N1", transport, Ledger(tmp_path / "blank.jsonl", cap_seconds=100), "blank", "aa")
    assert result["layout"]["regions"][0]["has_ink"] is False
    assert result["prediction"].strip() == ""
    assert result["status"] == "incomplete"
    assert result["completed"] is False


def test_blank_margin_does_not_fail_a_scored_ink_region(tmp_path):
    image = _page(40, 300, _rows(150, 170, 40))
    layout = segment_page(image, "bands")
    assert layout["regions"][0]["has_ink"] is False
    assert any(region["has_ink"] for region in layout["regions"])
    calls = {"n": 0}

    def transport(prepared, candidate, allowed):
        calls["n"] += 1
        text = "" if calls["n"] == 1 else "5 mg"
        return _stopped(text)

    result = run_page(image, "N3", transport, Ledger(tmp_path / "margin.jsonl", cap_seconds=100), "margin", "aa")
    assert result["status"] == "scored"
    assert result["completed"] is True
    assert "5 mg" in result["prediction"]


def test_non_object_transport_is_recorded_as_malformed(tmp_path):
    image = _page(40, 40, _rows(10, 20, 40))
    for index, payload in enumerate((None, [])):
        def transport(prepared, candidate, allowed, payload=payload):
            time.sleep(0.05)
            return payload

        ledger = Ledger(tmp_path / f"bad-{index}.jsonl", cap_seconds=100)
        result = run_page(image, "N1", transport, ledger, f"bad-{index}", "aa")
        assert result["status"] == "incomplete"
        assert result["completed"] is False
        assert result["regions"][0]["status"] == "malformed_transport"
        assert [row["event"] for row in ledger.rows()] == ["begin", "finish"]
        assert ledger.charged() >= 0.04
    listed = {
        "model": "glm-ocr:q8_0", "response": ["5 mg"], "done": True, "done_reason": "stop",
        "model_digest": "aa",
    }
    ledger = Ledger(tmp_path / "listed.jsonl", cap_seconds=100)
    result = run_page(image, "N1", lambda prepared, candidate, allowed: listed, ledger, "listed", "aa")
    assert result["status"] == "incomplete"
    assert result["regions"][0]["status"] == "malformed_transport"
    assert result["regions"][0]["transcription"] == ""
    assert result["regions"][0]["raw_response"] == ["5 mg"]
    assert result["prediction"] == ""

    def untimed(prepared, candidate, allowed):
        time.sleep(0.05)
        return {
            "model": "glm-ocr:q8_0", "response": "5 mg", "done": True, "done_reason": "stop",
            "model_digest": "aa",
        }

    missing = Ledger(tmp_path / "untimed.jsonl", cap_seconds=100)
    scored = run_page(image, "N1", untimed, missing, "untimed", "aa")
    assert scored["completed"] is True
    assert missing.charged() >= 0.04


def test_generation_limit_on_a_blank_margin_keeps_the_page_incomplete(tmp_path):
    image = _page(40, 300, _rows(150, 170, 40))
    calls = {"n": 0}

    def transport(prepared, candidate, allowed):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "model": "glm-ocr:q8_0", "response": "50 mg", "done": True, "done_reason": "length",
                "elapsed_seconds": 1, "model_digest": "aa",
            }
        return _stopped("5 mg")

    result = run_page(image, "N3", transport, Ledger(tmp_path / "limit.jsonl", cap_seconds=100), "limit", "aa")
    assert result["regions"][0]["status"] == "generation_limit"
    assert result["status"] == "incomplete"
    assert result["completed"] is False
