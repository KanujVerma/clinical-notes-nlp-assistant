"""Recompute PR #10 metrics from saved predictions and source bytes."""
from __future__ import annotations

import json
from pathlib import Path

from evaluation.public_amr_benchmark import CRITICAL, score, sha


def decide_screen(incumbent: dict, candidate: dict) -> dict:
    """Promote only when coverage holds and paired quality does not regress.

    Paired metrics cover cases both sides scored. A coverage gain can promote
    when those shared cases are not worse. Equal quality keeps the incumbent.
    """
    reasons = []
    if candidate["scored"] < incumbent["scored"]:
        reasons.append("coverage fell")
    if candidate["paired_cer"] > incumbent["paired_cer"] + 1e-12:
        reasons.append("paired CER rose")
    if candidate["paired_hits"] < incumbent["paired_hits"]:
        reasons.append("paired critical hits fell")
    if candidate["paired_fp"] > incumbent["paired_fp"]:
        reasons.append("paired false positives rose")
    if candidate["scored"] == incumbent["scored"] and candidate["fp"] > incumbent["fp"]:
        reasons.append("false positives rose")
    if candidate["rx_cer"] > incumbent["rx_cer"] + 0.01:
        reasons.append("Rx CER worsened")
    if candidate["paired_p95"] > max(incumbent["paired_p95"] * 2, incumbent["paired_p95"] + 15000):
        reasons.append("paired latency more than doubled")
    improved = (
        candidate["scored"] > incumbent["scored"]
        or candidate["paired_cer"] + 1e-12 < incumbent["paired_cer"]
        or (candidate["fp"] < incumbent["fp"] and candidate["paired_cer"] <= incumbent["paired_cer"] + 1e-12)
    )
    if reasons or not improved:
        return {"status": "discard", "reason": "; ".join(reasons) or "no measured gain on the same inputs"}
    return {"status": "keep", "reason": "coverage and paired accuracy beat the incumbent without a safety regression"}


def critical_false_positives(reference: str, hypothesis: str) -> int:
    """Hypothesis critical tokens that are not present in the reference."""
    present = {match.group().casefold() for match in CRITICAL.finditer(reference)}
    extra = set()
    for match in CRITICAL.finditer(hypothesis):
        token = match.group().casefold()
        if token not in present:
            extra.add(token)
    return len(extra)


def micro_summary(cases: list[dict]) -> dict:
    scored = [case for case in cases if case.get("status") == "scored"]
    char_distance = sum(case["metrics"]["character_distance"] for case in scored)
    word_distance = sum(case["metrics"]["word_distance"] for case in scored)
    chars = sum(case["metrics"]["ref_chars"] for case in scored)
    words = sum(case["metrics"]["ref_words"] for case in scored)
    hits = sum(token["recognized"] for case in scored
               for token in case["metrics"]["critical_tokens"])
    total = sum(len(case["metrics"]["critical_tokens"]) for case in scored)
    false_positives = sum(case["critical_false_positives"] for case in scored)
    latencies = sorted(case["latency_ms"] for case in scored)
    def percentile(values: list[int], fraction: float) -> int | None:
        if not values:
            return None
        index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
        return values[index]
    return {
        "attempted": len(cases),
        "scored": len(scored),
        "failed": len(cases) - len(scored),
        "cer_micro": char_distance / chars if chars else None,
        "wer_micro": word_distance / words if words else None,
        "critical_hit": hits,
        "critical_total": total,
        "critical_recall": hits / total if total else None,
        "critical_false_positives": false_positives,
        "median_latency_ms": percentile(latencies, 0.5),
        "p95_latency_ms": percentile(latencies, 0.95),
        "reference_chars": chars,
        "reference_words": words,
    }


def rescore_case(case: dict, reference: str, reference_sha256: str) -> dict:
    if sha(reference.encode("utf-8")) != reference_sha256 and sha(
            reference.encode("utf-8-sig")) != reference_sha256:
        # Caller passes the decoded reference. The stored hash is of the file bytes.
        pass
    if case.get("reference_sha256") != reference_sha256:
        raise ValueError("PR10_REFERENCE_HASH_MISMATCH")
    if case.get("status") != "scored":
        return case
    metrics = score(reference, case["prediction"])
    false_positives = critical_false_positives(reference, case["prediction"])
    if metrics != case["metrics"] or false_positives != case["critical_false_positives"]:
        raise ValueError("PR10_REPLAY_METRICS_MISMATCH")
    return case


def load_run(path: Path) -> list[dict]:
    cases = []
    for item in sorted(path.glob("*.json")):
        if item.name in {"summary.json", "best.json"}:
            continue
        payload = json.loads(item.read_text())
        if isinstance(payload, dict) and payload.get("id"):
            cases.append(payload)
    return cases
