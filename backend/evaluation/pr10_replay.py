"""Recompute PR #10 metrics from saved predictions and source bytes."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

from evaluation.public_amr_benchmark import CRITICAL, score, sha


def cohorts_match(incumbent_ids, candidate_ids) -> bool:
    return set(incumbent_ids) == set(candidate_ids)


def decide_screen(incumbent: dict, candidate: dict) -> dict:
    """Compare one candidate with its incumbent.

    Undefined CER stays undefined. Coverage recovery without a paired CER
    gain is a reliability candidate, not an accuracy win. Equal quality
    rejects the candidate and keeps the incumbent.
    """
    if incumbent.get("rx_cer") is None or candidate.get("rx_cer") is None:
        return {"status": "rejected", "reason": "Rx CER is undefined"}
    if incumbent.get("paired_cer") is None or candidate.get("paired_cer") is None:
        return {"status": "inconclusive", "reason": "no shared scored AMR cases"}
    reasons = []
    if candidate["scored"] < incumbent["scored"]:
        reasons.append("coverage fell")
    inc_rx = incumbent.get("rx_scored")
    cand_rx = candidate.get("rx_scored")
    if inc_rx is not None and cand_rx is not None and cand_rx < inc_rx:
        reasons.append("Rx coverage fell")
    if candidate["paired_cer"] > incumbent["paired_cer"] + 1e-12:
        reasons.append("paired CER rose")
    if candidate["paired_hits"] < incumbent["paired_hits"]:
        reasons.append("paired critical hits fell")
    if candidate["paired_fp"] > incumbent["paired_fp"]:
        reasons.append("paired false positives rose")
    inc_occ = incumbent.get("occurrence_fp")
    cand_occ = candidate.get("occurrence_fp")
    if inc_occ is not None and cand_occ is not None and cand_occ > inc_occ:
        reasons.append("occurrence false positives rose")
    if candidate["scored"] == incumbent["scored"] and candidate["fp"] > incumbent["fp"]:
        reasons.append("false positives rose")
    if candidate["rx_cer"] > incumbent["rx_cer"] + 0.01:
        reasons.append("Rx CER worsened")
    if candidate["paired_p95"] > max(incumbent["paired_p95"] * 2, incumbent["paired_p95"] + 15000):
        reasons.append("paired latency more than doubled")
    if reasons:
        return {"status": "rejected", "reason": "; ".join(reasons)}
    if candidate["paired_cer"] + 1e-12 < incumbent["paired_cer"] or (
        candidate["fp"] < incumbent["fp"] and candidate["paired_cer"] <= incumbent["paired_cer"] + 1e-12
    ):
        return {
            "status": "accuracy_candidate",
            "reason": "paired accuracy improved without a safety regression",
        }
    if candidate["scored"] > incumbent["scored"] or (
        inc_rx is not None and cand_rx is not None and cand_rx > inc_rx
    ):
        return {
            "status": "reliability_candidate",
            "reason": "coverage improved without a paired accuracy gain",
        }
    return {"status": "rejected", "reason": "no measured gain on the same inputs"}


def critical_occurrences(text: str) -> list[str]:
    return [match.group().casefold() for match in CRITICAL.finditer(text or "")]


def align_critical(reference: str, hypothesis: str) -> dict:
    """Occurrence alignment. Repeated or swapped doses stay distinct."""
    ref = critical_occurrences(reference)
    hyp = critical_occurrences(hypothesis)
    hits = 0
    missed: list[str] = []
    extra: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=ref, b=hyp, autojunk=False).get_opcodes():
        if tag == "equal":
            hits += i2 - i1
        elif tag == "delete":
            missed.extend(ref[i1:i2])
        elif tag == "insert":
            extra.extend(hyp[j1:j2])
        else:
            missed.extend(ref[i1:i2])
            extra.extend(hyp[j1:j2])
    return {
        "occurrence_hits": hits,
        "occurrence_total": len(ref),
        "occurrence_false_positives": len(extra),
        "missed_critical_tokens": missed,
        "extra_critical_tokens": extra,
    }


def critical_false_positives(reference: str, hypothesis: str) -> int:
    """Unique unmatched critical strings. This is not an occurrence count."""
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
    def optional(key: str) -> int | None:
        if not scored or any(key not in case for case in scored):
            return None
        return sum(case[key] for case in scored)
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
        "unique_unmatched_critical_tokens": false_positives,
        "occurrence_hits": optional("occurrence_hits"),
        "occurrence_total": optional("occurrence_total"),
        "occurrence_false_positives": optional("occurrence_false_positives"),
        "median_latency_ms": percentile(latencies, 0.5),
        "p95_latency_ms": percentile(latencies, 0.95),
        "reference_chars": chars,
        "reference_words": words,
    }


def reference_text(reference_bytes: bytes) -> str:
    """Score decoded UTF-8 text. A BOM is stripped and CRLF becomes LF."""
    return bytes(reference_bytes).decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def rescore_case(case: dict, reference_bytes: bytes, reference_sha256: str) -> dict:
    if not isinstance(reference_bytes, (bytes, bytearray)) or not reference_bytes:
        raise ValueError("PR10_REFERENCE_MISSING")
    actual = sha(bytes(reference_bytes))
    if actual != reference_sha256 or case.get("reference_sha256") != reference_sha256:
        raise ValueError("PR10_REFERENCE_HASH_MISMATCH")
    if case.get("status") != "scored":
        return case
    prediction = case.get("prediction")
    if not isinstance(prediction, str) or not prediction.strip():
        raise ValueError("PR10_EMPTY_PREDICTION")
    reference = reference_text(reference_bytes)
    metrics = score(reference, prediction)
    false_positives = critical_false_positives(reference, prediction)
    if metrics != case.get("metrics") or false_positives != case.get("critical_false_positives"):
        raise ValueError("PR10_REPLAY_METRICS_MISMATCH")
    verified = dict(case)
    verified["replay_verified"] = True
    return verified


def load_run(path: Path) -> list[dict]:
    cases = []
    for item in sorted(path.glob("*.json")):
        if item.name in {"summary.json", "best.json"}:
            continue
        payload = json.loads(item.read_text())
        if isinstance(payload, dict) and payload.get("id"):
            cases.append(payload)
    seen = set()
    for case in cases:
        if case["id"] in seen:
            raise ValueError("PR10_DUPLICATE_CASE")
        seen.add(case["id"])
    return cases
