"""Recompute PR #10 metrics from saved predictions and source bytes."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

from evaluation.pr10_identity import (
    IDENTITY_VERSION, CheckpointRejected, LegacyCheckpoint, mismatch_code,
)
from evaluation.public_amr_benchmark import CRITICAL, score, sha


def cohorts_match(incumbent_ids, candidate_ids) -> bool:
    return set(incumbent_ids) == set(candidate_ids)


def decide_screen(incumbent: dict, candidate: dict) -> dict:
    """Compare one candidate with its incumbent.

    Undefined CER stays undefined. Coverage recovery without a paired CER
    gain is a reliability candidate, not an accuracy win. Equal quality
    rejects the candidate and keeps the incumbent.
    """
    def paired_rx(view: dict) -> int:
        if "rx_paired_n" in view:
            return view["rx_paired_n"]
        return 0 if view.get("rx_cer") is None else 1

    if paired_rx(incumbent) == 0 or paired_rx(candidate) == 0 or (
        incumbent.get("rx_cer") is None or candidate.get("rx_cer") is None
    ):
        return {"status": "inconclusive", "reason": "no shared scored Rx cases"}
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
    inc_rx_occ = incumbent.get("rx_occurrence_fp")
    cand_rx_occ = candidate.get("rx_occurrence_fp")
    if inc_rx_occ is not None and cand_rx_occ is not None and cand_rx_occ > inc_rx_occ:
        reasons.append("Rx occurrence false positives rose")
    if candidate["paired_p95"] > max(incumbent["paired_p95"] * 2, incumbent["paired_p95"] + 15000):
        reasons.append("paired latency more than doubled")
    if reasons:
        return {"status": "rejected", "reason": "; ".join(reasons)}
    rx_improved = candidate["rx_cer"] + 1e-12 < incumbent["rx_cer"]
    if candidate["paired_cer"] + 1e-12 < incumbent["paired_cer"] or rx_improved or (
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


def _normalize_whitespace(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in (text or "").splitlines())


def has_recognition_change(incumbent: list[dict], candidate: list[dict]) -> bool:
    """True when a shared success changes a token, not only spaces or line breaks."""
    inc = {case["id"]: case for case in incumbent}
    for case in candidate:
        other = inc.get(case.get("id"))
        if other is None or case.get("status") != "scored" or other.get("status") != "scored":
            continue
        if _normalize_whitespace(case.get("prediction") or "") != _normalize_whitespace(other.get("prediction") or ""):
            return True
    return False


def predictions_differ_only_by_whitespace(incumbent: list[dict], candidate: list[dict]) -> bool:
    """True when shared successes differ only by space or line-break collapsing."""
    inc = {case["id"]: case for case in incumbent}
    cand = {case["id"]: case for case in candidate}
    shared = [
        case_id for case_id in inc
        if case_id in cand
        and inc[case_id].get("status") == "scored"
        and cand[case_id].get("status") == "scored"
    ]
    if not shared:
        return False
    changed = False
    for case_id in shared:
        left = inc[case_id].get("prediction") or ""
        right = cand[case_id].get("prediction") or ""
        if left != right:
            changed = True
        if _normalize_whitespace(left) != _normalize_whitespace(right):
            return False
    return changed


def paired_population(incumbent: list[dict], candidate: list[dict]) -> dict:
    """Paired and all-scored micro scores. Does not treat a different success set as paired."""
    inc_ids = [case.get("id") for case in incumbent]
    cand_ids = [case.get("id") for case in candidate]
    if any(case_id in (None, "") for case_id in inc_ids + cand_ids):
        return {"status": "duplicate_case"}
    if len(inc_ids) != len(set(inc_ids)) or len(cand_ids) != len(set(cand_ids)):
        return {"status": "duplicate_case"}
    if set(inc_ids) != set(cand_ids):
        return {"status": "attempted_cohorts_differ"}
    shared = {
        case["id"] for case in incumbent if case.get("status") == "scored"
    } & {
        case["id"] for case in candidate if case.get("status") == "scored"
    }

    def pack(cases: list[dict], selected: set) -> dict:
        chosen = [case for case in cases if case.get("id") in selected and case.get("status") == "scored"]
        summary = micro_summary(chosen if selected is not None else cases)
        return summary

    inc_paired = pack(incumbent, shared)
    cand_paired = pack(candidate, shared)
    inc_all = micro_summary(incumbent)
    cand_all = micro_summary(candidate)
    return {
        "status": "ok",
        "shared_ids": sorted(shared),
        "incumbent_paired_cer": inc_paired["cer_micro"],
        "candidate_paired_cer": cand_paired["cer_micro"],
        "incumbent_paired_wer": inc_paired["wer_micro"],
        "candidate_paired_wer": cand_paired["wer_micro"],
        "incumbent_all_scored_cer": inc_all["cer_micro"],
        "candidate_all_scored_cer": cand_all["cer_micro"],
        "incumbent_scored": inc_all["scored"],
        "candidate_scored": cand_all["scored"],
        "incumbent_failed": inc_all["failed"],
        "candidate_failed": cand_all["failed"],
        "attempted": inc_all["attempted"],
        "incumbent_occurrence_fp": inc_paired["occurrence_false_positives"],
        "candidate_occurrence_fp": cand_paired["occurrence_false_positives"],
        "incumbent_critical_fp": inc_paired["critical_false_positives"],
        "candidate_critical_fp": cand_paired["critical_false_positives"],
        "paired_reference_chars": inc_paired["reference_chars"],
    }


SUMMARY_METRIC_KEYS = (
    "attempted", "scored", "failed", "cer_micro", "wer_micro",
    "critical_recall", "critical_false_positives",
)


def _read_cases(folder: Path) -> tuple[dict[str, dict], dict | None]:
    cases: dict[str, dict] = {}
    summary = None
    if not folder.exists():
        return cases, None
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_text())
        if path.name == "summary.json":
            summary = payload
            continue
        if path.stem in cases or payload.get("id") in cases:
            raise CheckpointRejected("duplicate_case")
        cases[path.stem] = payload
    return cases, summary


def classify_saved_run(
    folder: Path,
    expected: dict,
    identifiers: list[str],
    sources: dict[str, bytes] | None = None,
) -> dict:
    """Read one saved run and classify it. Never writes."""
    if len(identifiers) != len(set(identifiers)):
        return {"classification": "duplicate_case", "cases": []}
    cases_by_stem, summary = _read_cases(folder)
    if any(case.get("id") != stem for stem, case in cases_by_stem.items()):
        return {"classification": "duplicate_case", "cases": []}
    if any(case.get("identity_version") != IDENTITY_VERSION for case in cases_by_stem.values()):
        return {"classification": "legacy_unverified", "cases": list(cases_by_stem.values())}
    extra = set(cases_by_stem) - set(identifiers)
    if extra:
        return {"classification": "extra_case", "cases": list(cases_by_stem.values())}
    missing = [item for item in identifiers if item not in cases_by_stem]
    present = [cases_by_stem[item] for item in identifiers if item in cases_by_stem]
    for case in present:
        code = mismatch_code(case, expected)
        if code:
            return {"classification": code, "cases": present}
        if sources and case["id"] in sources:
            if sha(sources[case["id"]]) != case.get("reference_sha256"):
                return {"classification": "reference_hash_mismatch", "cases": present}
        elif case.get("status") == "scored" and not _sha256_hex(case.get("reference_sha256")):
            return {"classification": "reference_hash_missing", "cases": present}
    if missing:
        return {"classification": "incomplete", "cases": present}
    ordered = [cases_by_stem[item] for item in identifiers]
    recomputed = micro_summary(ordered)
    if summary is None:
        return {"classification": "summary_missing", "cases": ordered, "recomputed": recomputed}
    if any(summary.get(key) != recomputed.get(key) for key in SUMMARY_METRIC_KEYS):
        return {"classification": "summary_mismatch", "cases": ordered, "recomputed": recomputed}
    if summary.get("experiment_fingerprint") != expected["experiment_fingerprint"]:
        return {"classification": "fingerprint_mismatch", "cases": ordered, "recomputed": recomputed}
    if summary.get("identity_version") != IDENTITY_VERSION:
        return {"classification": "legacy_unverified", "cases": ordered}
    return {"classification": "verified", "cases": ordered, "recomputed": recomputed, "summary": summary}


def load_verified_run(
    folder: Path,
    expected: dict,
    identifiers: list[str],
    sources: dict[str, bytes] | None = None,
) -> list[dict]:
    """Return cases only when the saved run matches the expected identity."""
    before = _snapshot(folder)
    result = classify_saved_run(folder, expected, identifiers, sources)
    if _snapshot(folder) != before:
        raise CheckpointRejected("artifact_mutated")
    code = result["classification"]
    if code == "legacy_unverified":
        raise LegacyCheckpoint("legacy_unverified")
    if code != "verified":
        raise CheckpointRejected(code)
    return result["cases"]


def _sha256_hex(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _snapshot(folder: Path) -> list[tuple[str, bytes]]:
    if not folder.exists():
        return []
    return [(path.name, path.read_bytes()) for path in sorted(folder.glob("*.json"))]


def audit_saved_runs(root: Path) -> dict:
    """Count saved runs by identity class. Does not read prediction text aloud or write."""
    legacy = 0
    verified = 0
    other = 0
    runs = 0
    if not root.exists():
        return {"runs": 0, "legacy_unverified": 0, "verified": 0, "other": 0}
    for summary_path in sorted(root.glob("*/*/*/summary.json")):
        runs += 1
        folder = summary_path.parent
        versions = set()
        for path in folder.glob("*.json"):
            if path.name == "summary.json":
                continue
            payload = json.loads(path.read_text())
            versions.add(payload.get("identity_version"))
        if versions <= {None} or versions == set():
            legacy += 1
        elif versions == {IDENTITY_VERSION}:
            verified += 1
        else:
            other += 1
    return {
        "runs": runs,
        "legacy_unverified": legacy,
        "verified": verified,
        "other": other,
    }
