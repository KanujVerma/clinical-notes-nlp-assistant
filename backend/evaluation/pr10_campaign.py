"""Detached PR #10 keep/discard loop. Resumes from case checkpoints."""
from __future__ import annotations

import fcntl
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from evaluation.pr10_autoresearch import (
    MANIFEST, MODEL, PRIVATE, build_identity, reference_bytes_for, run_spec, work_items,
)
from evaluation.pr10_candidate import historical_specs, mutation_queue, resolve_spec
from evaluation.pr10_identity import CheckpointRejected, LegacyCheckpoint
from evaluation.pr10_replay import (
    cohorts_match, decide_screen, has_recognition_change, load_verified_run,
    micro_summary, paired_population,
)

BUDGET_EXPERIMENTS = 30
BUDGET_CONFIGS = 40
BUDGET_MS = 6 * 60 * 60 * 1000
TRACKED = (
    "encode", "contrast", "grayscale", "gamma", "sharpen", "denoise", "trim",
    "longest", "num_ctx", "prompt", "dedupe_lines", "collapse_spaces",
    "second_pass", "segment", "jpeg_quality",
)


def _decisions_path() -> Path:
    return PRIVATE / "decisions.jsonl"


def _best_path() -> Path:
    return PRIVATE / "best.json"


def _state_path() -> Path:
    return PRIVATE / "run_state.json"


def _pending_path() -> Path:
    return PRIVATE / "pending_confirm.json"


def _receipt_path() -> Path:
    return PRIVATE / "batch_receipt.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def acquire_lock(path: Path):
    """One campaign owner. A second launch fails without starting inference."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as blocked:
        handle.close()
        raise RuntimeError("already_running") from blocked
    return handle


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def _append(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def elapsed_ms() -> int:
    total = 0
    if not PRIVATE.exists():
        return 0
    for path in PRIVATE.rglob("*.json"):
        if path.name in {"summary.json", "best.json", "run_state.json", "batch_receipt.json"}:
            continue
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and "latency_ms" in payload:
            total += int(payload["latency_ms"])
    return total


def _installed_digest() -> str:
    from services.inference_pipeline import get_installed_model_digest
    return get_installed_model_digest(MODEL)


def _expected(stage: str, name: str, dataset: str, identifiers: list[str]) -> dict:
    try:
        spec = resolve_spec(name)
    except KeyError as missing:
        raise CheckpointRejected("unknown_spec") from missing
    return build_identity(spec, stage, dataset, _installed_digest(), identifiers)


def _cases(stage: str, name: str, dataset: str) -> list[dict]:
    """Load one run only after its identity, cohort, and receipt match."""
    manifest = json.loads(MANIFEST.read_bytes())
    identifiers = work_items(manifest, stage, dataset)
    folder = PRIVATE / stage / name / dataset
    sources = reference_bytes_for(dataset, identifiers)
    return load_verified_run(
        folder, _expected(stage, name, dataset, identifiers), identifiers, sources,
    )


def verify_finished_batch() -> dict:
    """The shell did not record Python exit codes. Trust a matching recompute."""
    expected = (
        ("jpeg_ctx8192", "amr", 8),
        ("jpeg_baseline", "rx", 64),
        ("jpeg_ctx8192", "rx", 64),
    )
    commands = []
    for name, dataset, count in expected:
        cases = _cases("screen", name, dataset)
        commands.append({
            "candidate": name, "dataset": dataset, "expected_cases": count,
            "case_files": len(cases), "recompute_matches": len(cases) == count,
        })
    log = (PRIVATE / "controller.log").read_text() if (PRIVATE / "controller.log").exists() else ""
    head = log.split("CAMPAIGN_START", 1)[0]
    receipt = {
        "verified_utc": _now(),
        "shell_exit_status": "not_recorded",
        "python_exit_status": "not_recorded",
        "completion_rule": "summary_recompute_matches_and_case_count",
        "log_has_traceback": "Traceback" in head,
        "log_done_markers": {
            "amr_ctx8192": "AMR_CTX8192_DONE" in head,
            "rx_baseline": "RX_BASELINE_DONE" in head,
            "rx_ctx8192": "RX_CTX8192_DONE" in head,
        },
        "commands": commands,
    }
    ok = (
        all(item["recompute_matches"] for item in commands)
        and not receipt["log_has_traceback"]
        and all(receipt["log_done_markers"].values())
    )
    receipt["verified"] = ok
    if not ok:
        raise CheckpointRejected("batch_unverified")
    if not _receipt_path().exists():
        _write(_receipt_path(), receipt)
    return receipt


def _seed_decisions() -> None:
    if _decisions_path().exists():
        return
    for name, reason in (
        ("png_lossless", "Same 2/8 coverage as the default-context baseline and no meaningful CER change."),
        ("contrast_autocontrast", "Same 2/8 coverage and a higher CER than the default-context baseline."),
    ):
        _append(_decisions_path(), {
            "utc": _now(), "candidate": name, "stage": "screen", "status": "discard",
            "family": "A", "reason": reason,
        })


def _decisions() -> list[dict]:
    _seed_decisions()
    return _read_jsonl(_decisions_path())


def _best_spec() -> dict:
    if _best_path().exists():
        return json.loads(_best_path().read_text())["spec"]
    return historical_specs()["jpeg_baseline"]


def _save_best(spec: dict, reason: str) -> None:
    _write(_best_path(), {"candidate": spec["name"], "spec": spec, "reason": reason, "utc": _now()})


def _ready(stage: str, name: str, dataset: str) -> bool:
    """A summary file is not evidence. The saved cases must verify."""
    if not (PRIVATE / stage / name / dataset / "summary.json").exists():
        return False
    _cases(stage, name, dataset)
    return True


def _view(stage: str, name: str) -> dict:
    amr = _cases(stage, name, "amr")
    rx = _cases(stage, name, "rx")
    return amr, rx


def _metrics(
    amr_cases: list[dict],
    rx_cases: list[dict],
    paired_ids: set[str],
    paired_rx_ids: set[str] | None = None,
) -> dict:
    amr = micro_summary(amr_cases)
    if paired_rx_ids is None:
        paired_rx_ids = {case["id"] for case in rx_cases if case.get("status") == "scored"}
    rx_paired = micro_summary([
        case for case in rx_cases
        if case.get("id") in paired_rx_ids and case.get("status") == "scored"
    ])
    rx_all = micro_summary(rx_cases)
    paired = micro_summary([
        case for case in amr_cases if case["id"] in paired_ids and case["status"] == "scored"
    ])
    return {
        "scored": amr["scored"],
        "fp": amr["critical_false_positives"],
        "paired_cer": paired["cer_micro"],
        "paired_hits": paired["critical_hit"],
        "paired_occurrence_hits": paired["occurrence_hits"],
        "paired_fp": paired["critical_false_positives"],
        "paired_p95": paired["p95_latency_ms"] or 0,
        "rx_cer": rx_paired["cer_micro"],
        "rx_wer": rx_paired["wer_micro"],
        "rx_cer_all_scored": rx_all["cer_micro"],
        "rx_scored": rx_all["scored"],
        "rx_paired_n": len(paired_rx_ids),
        "rx_occurrence_hits": rx_paired["occurrence_hits"],
        "rx_occurrence_fp": rx_paired["occurrence_false_positives"],
        "occurrence_fp": paired["occurrence_false_positives"],
    }


def _compare(stage: str, incumbent: str, candidate: str) -> dict:
    inc_amr, inc_rx = _view(stage, incumbent)
    cand_amr, cand_rx = _view(stage, candidate)
    if not cohorts_match(
        (case["id"] for case in inc_amr), (case["id"] for case in cand_amr)
    ) or not cohorts_match(
        (case["id"] for case in inc_rx), (case["id"] for case in cand_rx)
    ):
        return {
            "status": "inconclusive",
            "reason": "attempted cohorts differ",
            "candidate": candidate,
            "incumbent": incumbent,
            "stage": stage,
            "utc": _now(),
        }
    rx = paired_population(inc_rx, cand_rx)
    if rx["status"] != "ok":
        return {
            "status": "inconclusive",
            "reason": rx["status"].replace("_", " "),
            "candidate": candidate,
            "incumbent": incumbent,
            "stage": stage,
            "utc": _now(),
        }
    paired_ids = {
        case["id"] for case in inc_amr if case["status"] == "scored"
    } & {
        case["id"] for case in cand_amr if case["status"] == "scored"
    }
    paired_rx_ids = set(rx["shared_ids"])
    decision = decide_screen(
        _metrics(inc_amr, inc_rx, paired_ids, paired_rx_ids),
        _metrics(cand_amr, cand_rx, paired_ids, paired_rx_ids),
    )
    token_change = has_recognition_change(inc_amr, cand_amr) or has_recognition_change(inc_rx, cand_rx)
    if decision["status"] == "accuracy_candidate" and not token_change:
        decision = {
            "status": "rejected",
            "reason": "formatting change is not a recognition gain",
        }
    decision.update({
        "candidate": candidate,
        "incumbent": incumbent,
        "stage": stage,
        "utc": _now(),
        "rx_paired_cer_incumbent": rx["incumbent_paired_cer"],
        "rx_paired_cer_candidate": rx["candidate_paired_cer"],
        "rx_all_scored_cer_incumbent": rx["incumbent_all_scored_cer"],
        "rx_all_scored_cer_candidate": rx["candidate_all_scored_cer"],
        "rx_paired_n": len(paired_rx_ids),
        "rx_paired_wer_incumbent": rx["incumbent_paired_wer"],
        "rx_paired_wer_candidate": rx["candidate_paired_wer"],
    })
    return decision


def _latest(decisions: list[dict]) -> list[dict]:
    ordered = []
    index = {}
    for row in decisions:
        if row["status"] not in {
            "keep", "discard", "rejected", "reliability_candidate",
            "accuracy_candidate", "inconclusive",
        }:
            continue
        name = row["candidate"]
        if name in index:
            ordered[index[name]] = row
        else:
            index[name] = len(ordered)
            ordered.append(row)
    return ordered


def _stopping(decisions: list[dict]) -> str | None:
    finished = _latest(decisions)
    if len(finished) >= BUDGET_EXPERIMENTS:
        return "experiment_budget"
    names = {row["candidate"] for row in finished}
    names.update(path.parent.parent.name for path in PRIVATE.glob("*/*/*/summary.json"))
    if len(names) >= BUDGET_CONFIGS:
        return "configuration_budget"
    if elapsed_ms() >= BUDGET_MS:
        return "compute_budget"
    families = {row.get("family") for row in finished}
    tail = 0
    for row in reversed(finished):
        if row["status"] not in {"discard", "rejected"}:
            break
        tail += 1
    if len(finished) >= 20 and tail >= 10 and {"A", "B", "C", "D", "E"} <= families:
        return "no_remaining_gain"
    return None


def _next_child(spec: dict, decisions: list[dict]) -> dict | None:
    done = {row["candidate"] for row in decisions if row["stage"] == "screen"}
    for child in mutation_queue(spec):
        if child["name"] not in done:
            return child
    return None


def _record(spec: dict, decision: dict) -> None:
    decision["family"] = spec.get("family")
    decision["hypothesis"] = spec.get("hypothesis")
    decision["spec_name"] = spec.get("name")
    _append(_decisions_path(), decision)
    print(f"PR10_DECISION {decision['candidate']} {decision['stage']} {decision['status']} {decision['reason']}", flush=True)


def campaign() -> int:
    try:
        campaign.lock_handle = acquire_lock(PRIVATE / "campaign.lock")
    except RuntimeError as blocked:
        if str(blocked) != "already_running":
            raise
        print("PR10_STOP already_running", flush=True)
        return 0
    reason = _stopping(_decisions())
    if reason:
        _stop_without_clobber(reason, len(_decisions()))
        return 0
    try:
        verify_finished_batch()
    except Exception:
        traceback.print_exc()
        _write(_state_path(), {"status": "integrity", "utc": _now()})
        print("PR10_STOP integrity", flush=True)
        return 0
    try:
        return _run()
    except (LegacyCheckpoint, CheckpointRejected) as blocked:
        _write(_state_path(), {"status": "stopped", "reason": str(blocked), "utc": _now(),
                       "elapsed_ms": elapsed_ms()})
        print(f"PR10_STOP {blocked}", flush=True)
        return 0
    except Exception:
        traceback.print_exc()
        _write(_state_path(), {"status": "crashed", "utc": _now(), "elapsed_ms": elapsed_ms()})
        print("PR10_CRASH restart", flush=True)
        return 1


def _run() -> int:
    _seed_decisions()
    decisions = _decisions()
    reason = _stopping(decisions)
    if reason:
        _stop_without_clobber(reason, len(decisions))
        return 0
    verify_finished_batch()
    while True:
        decisions = _decisions()
        reason = _stopping(decisions)
        if reason:
            _stop_without_clobber(reason, len(decisions))
            return 0
        best = _best_spec()
        pending = json.loads(_pending_path().read_text()) if _pending_path().exists() else None
        if pending is None and not any(
            row["candidate"] == "jpeg_ctx8192" and row["stage"] == "screen" for row in decisions
        ):
            if _ready("screen", "jpeg_ctx8192", "amr") and _ready("screen", "jpeg_ctx8192", "rx"):
                decision = _compare("screen", "jpeg_baseline", "jpeg_ctx8192")
                _record(historical_specs()["jpeg_ctx8192"], decision)
                if decision["status"] in {"keep", "accuracy_candidate"}:
                    _write(_pending_path(), historical_specs()["jpeg_ctx8192"])
                continue
        if pending:
            missing = _missing_confirm(best["name"], pending["name"])
            if missing:
                name, dataset = missing
                spec = pending if name == pending["name"] else historical_specs().get(name, best)
                print(f"PR10_NEXT confirm {name} {dataset} {spec.get('hypothesis')}", flush=True)
                run_spec(spec, "confirm", dataset, None)
                continue
            decision = _compare("confirm", best["name"], pending["name"])
            _record(pending, decision)
            if decision["status"] in {"keep", "accuracy_candidate"}:
                _save_best(pending, decision["reason"])
            _pending_path().unlink(missing_ok=True)
            continue
        child = _next_child(best, decisions)
        if child is None:
            _write(_state_path(), {"status": "stopped", "reason": "queue_exhausted", "utc": _now(),
                           "elapsed_ms": elapsed_ms()})
            print("PR10_STOP queue_exhausted", flush=True)
            return 0
        if not _ready("screen", child["name"], "amr"):
            print(f"PR10_NEXT screen {child['name']} amr {child['hypothesis']}", flush=True)
            run_spec(child, "screen", "amr", None)
            continue
        if not _ready("screen", child["name"], "rx"):
            print(f"PR10_NEXT screen {child['name']} rx {child['hypothesis']}", flush=True)
            run_spec(child, "screen", "rx", None)
            continue
        decision = _compare("screen", best["name"], child["name"])
        _record(child, decision)
        if decision["status"] in {"keep", "accuracy_candidate"}:
            _write(_pending_path(), child)
    return 0


def _stop_without_clobber(reason: str, experiments: int) -> None:
    """Record a new stop. Leave an already recorded stop and its artifacts alone."""
    current = json.loads(_state_path().read_text()) if _state_path().exists() else None
    if not current or current.get("status") != "stopped" or current.get("reason") != reason:
        _write(_state_path(), {"status": "stopped", "reason": reason, "utc": _now(),
                       "elapsed_ms": elapsed_ms(), "experiments": experiments})
    print(f"PR10_STOP {reason}", flush=True)


def _missing_confirm(incumbent: str, candidate: str) -> tuple[str, str] | None:
    for name, dataset in (
        (incumbent, "amr"), (candidate, "amr"), (incumbent, "rx"), (candidate, "rx"),
    ):
        if not _ready("confirm", name, dataset):
            return name, dataset
    return None


