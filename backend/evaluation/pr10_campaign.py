"""Detached PR #10 keep/discard loop. Resumes from case checkpoints."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from evaluation.pr10_autoresearch import PRIVATE, run_spec
from evaluation.pr10_candidate import historical_specs, mutation_queue
from evaluation.pr10_replay import decide_screen, micro_summary

DECISIONS = PRIVATE / "decisions.jsonl"
BEST = PRIVATE / "best.json"
STATE = PRIVATE / "run_state.json"
PENDING = PRIVATE / "pending_confirm.json"
RECEIPT = PRIVATE / "batch_receipt.json"
BUDGET_EXPERIMENTS = 30
BUDGET_CONFIGS = 40
BUDGET_MS = 6 * 60 * 60 * 1000
TRACKED = (
    "encode", "contrast", "grayscale", "gamma", "sharpen", "denoise", "trim",
    "longest", "num_ctx", "prompt", "dedupe_lines", "collapse_spaces",
    "second_pass", "segment", "jpeg_quality",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _cases(stage: str, name: str, dataset: str) -> list[dict]:
    folder = PRIVATE / stage / name / dataset
    summary_path = folder / "summary.json"
    if not summary_path.exists():
        raise ValueError(f"PR10_MISSING_SUMMARY {stage} {name} {dataset}")
    cases = []
    for path in sorted(folder.glob("*.json")):
        if path.name == "summary.json":
            continue
        cases.append(json.loads(path.read_text()))
    summary = json.loads(summary_path.read_text())
    recomputed = micro_summary(cases)
    compared = ("attempted", "scored", "failed", "cer_micro", "wer_micro",
                "critical_recall", "critical_false_positives")
    if any(summary.get(key) != recomputed.get(key) for key in compared):
        raise ValueError(f"PR10_RECEIPT_MISMATCH {stage} {name} {dataset}")
    return cases


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
    _write(RECEIPT, receipt)
    if not ok:
        raise ValueError("PR10_BATCH_NOT_VERIFIED")
    return receipt


def _seed_decisions() -> None:
    if DECISIONS.exists():
        return
    for name, reason in (
        ("png_lossless", "Same 2/8 coverage as the default-context baseline and no meaningful CER change."),
        ("contrast_autocontrast", "Same 2/8 coverage and a higher CER than the default-context baseline."),
    ):
        _append(DECISIONS, {
            "utc": _now(), "candidate": name, "stage": "screen", "status": "discard",
            "family": "A", "reason": reason,
        })


def _decisions() -> list[dict]:
    _seed_decisions()
    return _read_jsonl(DECISIONS)


def _best_spec() -> dict:
    if BEST.exists():
        return json.loads(BEST.read_text())["spec"]
    return historical_specs()["jpeg_baseline"]


def _save_best(spec: dict, reason: str) -> None:
    _write(BEST, {"candidate": spec["name"], "spec": spec, "reason": reason, "utc": _now()})


def _ready(stage: str, name: str, dataset: str) -> bool:
    return (PRIVATE / stage / name / dataset / "summary.json").exists()


def _view(stage: str, name: str) -> dict:
    amr = _cases(stage, name, "amr")
    rx = _cases(stage, name, "rx")
    return amr, rx


def _metrics(amr_cases: list[dict], rx_cases: list[dict], paired_ids: set[str]) -> dict:
    amr = micro_summary(amr_cases)
    rx = micro_summary(rx_cases)
    paired = micro_summary([case for case in amr_cases if case["id"] in paired_ids and case["status"] == "scored"])
    return {
        "scored": amr["scored"],
        "fp": amr["critical_false_positives"],
        "paired_cer": 0.0 if paired["cer_micro"] is None else paired["cer_micro"],
        "paired_hits": paired["critical_hit"],
        "paired_fp": paired["critical_false_positives"],
        "paired_p95": paired["p95_latency_ms"] or 0,
        "rx_cer": 0.0 if rx["cer_micro"] is None else rx["cer_micro"],
    }


def _compare(stage: str, incumbent: str, candidate: str) -> dict:
    inc_amr, inc_rx = _view(stage, incumbent)
    cand_amr, cand_rx = _view(stage, candidate)
    paired_ids = {
        case["id"] for case in inc_amr if case["status"] == "scored"
    } & {
        case["id"] for case in cand_amr if case["status"] == "scored"
    }
    decision = decide_screen(
        _metrics(inc_amr, inc_rx, paired_ids),
        _metrics(cand_amr, cand_rx, paired_ids),
    )
    decision.update({"candidate": candidate, "incumbent": incumbent, "stage": stage, "utc": _now()})
    return decision


def _latest(decisions: list[dict]) -> list[dict]:
    ordered = []
    index = {}
    for row in decisions:
        if row["status"] not in {"keep", "discard"}:
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
        if row["status"] != "discard":
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
    _append(DECISIONS, decision)
    print(f"PR10_DECISION {decision['candidate']} {decision['stage']} {decision['status']} {decision['reason']}", flush=True)


def campaign() -> int:
    try:
        verify_finished_batch()
    except Exception:
        traceback.print_exc()
        _write(STATE, {"status": "integrity", "utc": _now()})
        print("PR10_STOP integrity", flush=True)
        return 0
    try:
        return _run()
    except Exception:
        traceback.print_exc()
        _write(STATE, {"status": "crashed", "utc": _now(), "elapsed_ms": elapsed_ms()})
        print("PR10_CRASH restart", flush=True)
        return 1


def _run() -> int:
    _seed_decisions()
    while True:
        decisions = _decisions()
        reason = _stopping(decisions)
        if reason:
            _write(STATE, {"status": "stopped", "reason": reason, "utc": _now(),
                           "elapsed_ms": elapsed_ms(), "experiments": len(decisions)})
            print(f"PR10_STOP {reason}", flush=True)
            return 0
        best = _best_spec()
        pending = json.loads(PENDING.read_text()) if PENDING.exists() else None
        if pending is None and not any(
            row["candidate"] == "jpeg_ctx8192" and row["stage"] == "screen" for row in decisions
        ):
            if _ready("screen", "jpeg_ctx8192", "amr") and _ready("screen", "jpeg_ctx8192", "rx"):
                decision = _compare("screen", "jpeg_baseline", "jpeg_ctx8192")
                _record(historical_specs()["jpeg_ctx8192"], decision)
                if decision["status"] == "keep":
                    _write(PENDING, historical_specs()["jpeg_ctx8192"])
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
            if decision["status"] == "keep":
                _save_best(pending, decision["reason"])
            PENDING.unlink(missing_ok=True)
            continue
        child = _next_child(best, decisions)
        if child is None:
            _write(STATE, {"status": "stopped", "reason": "queue_exhausted", "utc": _now(),
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
        if decision["status"] == "keep":
            _write(PENDING, child)
    return 0


def _missing_confirm(incumbent: str, candidate: str) -> tuple[str, str] | None:
    for name, dataset in (
        (incumbent, "amr"), (candidate, "amr"), (incumbent, "rx"), (candidate, "rx"),
    ):
        if not _ready("confirm", name, dataset):
            return name, dataset
    return None


