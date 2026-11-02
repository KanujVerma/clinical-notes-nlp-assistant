"""Normalized recognition metrics and the preregistered selection rule."""
from __future__ import annotations

import math
import random

from evaluation.ocr_c2.protocol import load_protocol
from evaluation.pr10_replay import align_critical, reference_text
from evaluation.public_amr_benchmark import score
from services.multimodal_service import _levenshtein_distance


def normalize_recognition(text: str) -> str:
    decoded = reference_text(text.encode("utf-8")) if ("\r" in text or text.startswith("\ufeff")) else text
    return " ".join(decoded.split())


def normalized_errors(reference: str, hypothesis: str) -> dict:
    left = normalize_recognition(reference)
    right = normalize_recognition(hypothesis)
    ref_chars = len(left)
    ref_words = left.split()
    if ref_chars == 0:
        return {"char_distance": None, "word_distance": None, "ref_chars": 0, "ref_words": 0}
    return {
        "char_distance": _levenshtein_distance(left, right),
        "word_distance": _word_distance(ref_words, right.split()),
        "ref_chars": ref_chars,
        "ref_words": len(ref_words),
    }


def _word_distance(left: list[str], right: list[str]) -> int:
    rows = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(len(left) + 1):
        rows[i][0] = i
    for j in range(len(right) + 1):
        rows[0][j] = j
    for i, token in enumerate(left, start=1):
        for j, other in enumerate(right, start=1):
            cost = 0 if token == other else 1
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
    return rows[-1][-1]


def micro_rate(distances: list[int], totals: list[int]) -> float | None:
    denominator = sum(totals)
    if denominator == 0:
        return None
    return sum(distances) / denominator


def strict_case(reference: str, hypothesis: str) -> dict:
    return score(reference, hypothesis)


def occurrence_case(reference: str, hypothesis: str) -> dict:
    return align_critical(reference, hypothesis)


def preserves_successes(baseline_ids: set[str], candidate_ids: set[str]) -> bool:
    return set(baseline_ids) <= set(candidate_ids)


def safety_ok(baseline: dict, candidate: dict) -> bool:
    if candidate["occurrence_hits"] < baseline["occurrence_hits"]:
        return False
    if candidate["occurrence_false_positives"] > baseline["occurrence_false_positives"]:
        return False
    return True


def whitespace_only(left: str, right: str) -> bool:
    return left != right and normalize_recognition(left) == normalize_recognition(right)


def nearest_rank_p95(samples: list[float]) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def meets_relative_reduction(candidate_cer: float | None, baseline_cer: float | None) -> bool:
    if candidate_cer is None or baseline_cer is None or baseline_cer == 0:
        return False
    return candidate_cer <= 0.90 * baseline_cer


def bootstrap_relative(
    groups: list[list[tuple[int, int, int]]], replicates: int | None = None, seed: int | None = None,
) -> dict:
    """Writer-group bootstrap of the paired relative CER reduction.

    Each observation is (baseline_distance, candidate_distance, ref_chars).
    A draw resamples whole writer groups, so the baseline and candidate stay paired.
    The statistic is (baseline CER - candidate CER) / baseline CER.
    """
    rule = load_protocol()["budgets"]
    replicates = rule["bootstrap_replicates"] if replicates is None else replicates
    seed = rule["bootstrap_seed"] if seed is None else seed
    rng = random.Random(seed)
    if not groups:
        return {"point": None, "low": None, "high": None, "relative": None}

    def reduction(sample: list[list[tuple[int, int, int]]]) -> float | None:
        baseline = sum(item[0] for group in sample for item in group)
        candidate = sum(item[1] for group in sample for item in group)
        total = sum(item[2] for group in sample for item in group)
        if total == 0 or baseline == 0:
            return None
        return (baseline - candidate) / baseline

    point = reduction(groups)
    draws = []
    undefined = 0
    for _ in range(replicates):
        sample = [groups[rng.randrange(len(groups))] for _ in groups]
        value = reduction(sample)
        if value is None:
            undefined += 1
        else:
            draws.append(value)
    if point is None or undefined or len(draws) != replicates:
        return {
            "point": point, "low": None, "high": None, "relative": point,
            "groups": len(groups), "undefined_draws": undefined,
        }
    draws.sort()
    low = draws[max(0, math.ceil(0.025 * len(draws)) - 1)]
    high = draws[min(len(draws) - 1, math.ceil(0.975 * len(draws)) - 1)]
    return {
        "point": point, "low": low, "high": high, "relative": point,
        "groups": len(groups), "undefined_draws": 0,
    }


def select_finalist(rows: list[dict]) -> dict:
    """Apply the protocol order. Rows already carry paired metrics against B8192."""
    rule = load_protocol()["selection"]
    product_p95 = load_protocol()["budgets"]["product_p95_seconds"]
    eligible = []
    rejected = []
    for row in rows:
        reasons = []
        if row.get("provenance_ok") is not True or row.get("confirmation_complete") is not True:
            reasons.append("invalid")
        if not row.get("preserves_successes", False):
            reasons.append("lost_success")
        if not row.get("safety_ok", False):
            reasons.append("safety")
        if not meets_relative_reduction(row.get("paired_norm_cer"), row.get("baseline_norm_cer")):
            reasons.append("relative_cer")
        if row.get("strict_worse") or row.get("norm_wer_worse") or row.get("rx_worse") or row.get("full_cohort_worse"):
            reasons.append("secondary_metric")
        if not row.get("recognition_change", False):
            reasons.append("whitespace_only")
        if reasons:
            rejected.append({**row, "reasons": reasons})
            continue
        latency = nearest_rank_p95(row.get("cold_page_seconds") or [])
        product = latency is not None and latency <= product_p95
        eligible.append({**row, "p95": latency, "product_eligible": product})
    product_rows = [row for row in eligible if row["product_eligible"]]
    if not product_rows:
        return {"status": "latency_blocker" if eligible else "no_candidate", "eligible": eligible, "rejected": rejected}
    best = min(row["paired_norm_cer"] for row in product_rows)
    near = [
        row for row in product_rows
        if row["paired_norm_cer"] <= rule["near_best_relative"] * best
        and row["paired_norm_cer"] <= best + rule["near_best_absolute"]
    ]
    near.sort(key=lambda row: (row["p95"], row["paired_norm_cer"], row.get("calls", 0), row["candidate"]))
    return {"status": "selected", "candidate": near[0]["candidate"], "near_best": [row["candidate"] for row in near], "rejected": rejected}
