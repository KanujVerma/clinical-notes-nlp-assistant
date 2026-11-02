"""Fixed screen and confirmation gates. Thresholds are not adjusted after results."""
from __future__ import annotations

from evaluation.ocr_c2.metrics import (
    bootstrap_relative, meets_relative_reduction, micro_rate, nearest_rank_p95,
    normalize_recognition, preserves_successes, whitespace_only,
)
from evaluation.ocr_c3.protocol import load_protocol


def _scored(cases: list[dict]) -> dict[str, dict]:
    return {case["id"]: case for case in cases if case.get("status") == "scored" and case.get("metrics")}


def _rate(cases: dict[str, dict], ids: list[str], distance: str, total: str, section: str) -> float | None:
    return micro_rate(
        [cases[item][section][distance] for item in ids],
        [cases[item][section][total] for item in ids],
    )


def _recognition_changed(baseline: dict[str, dict], candidate: dict[str, dict], ids: list[str]) -> bool:
    for item in ids:
        left = baseline[item]["prediction"]
        right = candidate[item]["prediction"]
        if normalize_recognition(left) != normalize_recognition(right) and not whitespace_only(left, right):
            return True
    return False


def compare_dataset(baseline_cases: list[dict], candidate_cases: list[dict]) -> dict:
    baseline = _scored(baseline_cases)
    candidate = _scored(candidate_cases)
    paired = sorted(set(baseline) & set(candidate))
    attempted = max(len(baseline_cases), len(candidate_cases))
    reasons = []
    if not preserves_successes(set(baseline), set(candidate)):
        reasons.append("coverage_lost")
    if len(candidate) < len(baseline):
        reasons.append("coverage_fell")
    view = {
        "attempted": attempted,
        "baseline_scored": len(baseline),
        "candidate_scored": len(candidate),
        "paired": len(paired),
        "strict_cer": _rate(candidate, paired, "character_distance", "ref_chars", "metrics"),
        "baseline_strict_cer": _rate(baseline, paired, "character_distance", "ref_chars", "metrics"),
        "strict_wer": _rate(candidate, paired, "word_distance", "ref_words", "metrics"),
        "baseline_strict_wer": _rate(baseline, paired, "word_distance", "ref_words", "metrics"),
        "normalized_cer": _rate(candidate, paired, "char_distance", "ref_chars", "normalized"),
        "baseline_normalized_cer": _rate(baseline, paired, "char_distance", "ref_chars", "normalized"),
        "normalized_wer": _rate(candidate, paired, "word_distance", "ref_words", "normalized"),
        "baseline_normalized_wer": _rate(baseline, paired, "word_distance", "ref_words", "normalized"),
        "occurrence_hits": sum(candidate[item]["occurrence_hits"] for item in paired),
        "baseline_occurrence_hits": sum(baseline[item]["occurrence_hits"] for item in paired),
        "occurrence_total": sum(candidate[item]["occurrence_total"] for item in paired),
        "baseline_occurrence_total": sum(baseline[item]["occurrence_total"] for item in paired),
        "occurrence_false_positives": sum(candidate[item]["occurrence_false_positives"] for item in paired),
        "baseline_occurrence_false_positives": sum(baseline[item]["occurrence_false_positives"] for item in paired),
    }
    if None in (view["normalized_cer"], view["baseline_normalized_cer"], view["strict_cer"], view["baseline_strict_cer"]):
        reasons.append("undefined_cer")
    elif view["strict_cer"] > view["baseline_strict_cer"] + 1e-12:
        reasons.append("strict_cer_worsened")
    if view["strict_wer"] is not None and view["baseline_strict_wer"] is not None:
        if view["strict_wer"] > view["baseline_strict_wer"] + 1e-12:
            reasons.append("strict_wer_worsened")
    if view["normalized_wer"] is not None and view["baseline_normalized_wer"] is not None:
        if view["normalized_wer"] > view["baseline_normalized_wer"] + 1e-12:
            reasons.append("normalized_wer_worsened")
    if view["occurrence_hits"] < view["baseline_occurrence_hits"]:
        reasons.append("critical_hits_fell")
    base_total = view["baseline_occurrence_total"]
    cand_total = view["occurrence_total"]
    if base_total and cand_total:
        if view["occurrence_hits"] / cand_total + 1e-12 < view["baseline_occurrence_hits"] / base_total:
            reasons.append("critical_recall_fell")
    elif base_total and not cand_total:
        reasons.append("critical_recall_fell")
    if view["occurrence_false_positives"] > view["baseline_occurrence_false_positives"]:
        reasons.append("critical_false_positives_rose")
    if not meets_relative_reduction(view["normalized_cer"], view["baseline_normalized_cer"]):
        reasons.append("relative_cer")
    elif not _recognition_changed(baseline, candidate, paired):
        reasons.append("whitespace_only")
    view["reasons"] = reasons
    view["passed"] = not reasons
    return view


def screen_outcome(amr: dict, rx: dict, latencies: list[float]) -> dict:
    protocol = load_protocol()
    p95 = nearest_rank_p95(latencies)
    reasons = list(amr["reasons"]) + [f"rx_{reason}" for reason in rx["reasons"]]
    latency_blocker = p95 is None or p95 > protocol["budgets"]["product_p95_seconds"]
    if reasons:
        outcome = "screen_negative"
    else:
        outcome = "screen_passed"
    return {
        "outcome": outcome,
        "reasons": reasons,
        "latency_p95_seconds": p95,
        "latency_blocker": latency_blocker,
        "small_sample_p95": len(latencies) < 20,
        "amr_normalized_cer": amr["normalized_cer"],
        "baseline_normalized_cer": amr["baseline_normalized_cer"],
    }


def confirmation_outcome(amr_groups: list[list[tuple[int, int, int]]], screen_passed: bool, safety_passed: bool) -> dict:
    protocol = load_protocol()["budgets"]
    interval = bootstrap_relative(
        amr_groups,
        replicates=protocol["bootstrap_replicates"],
        seed=protocol["bootstrap_seed"],
    )
    point = interval.get("point")
    low = interval.get("low")
    if not screen_passed or not safety_passed or point is None or point < 0.10:
        outcome = "confirmation_negative"
    elif low is None or low < 0.10:
        outcome = "confirmation_inconclusive"
    else:
        outcome = "development_candidate_ready"
    return {"outcome": outcome, "bootstrap": interval, "writer_groups": len(amr_groups)}
