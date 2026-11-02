"""Recompute a saved prediction before a comparison trusts it."""
from __future__ import annotations

from evaluation.ocr_c2.metrics import normalize_recognition, occurrence_case, strict_case
from evaluation.pr10_replay import reference_text
from evaluation.public_amr_benchmark import sha


def replay_case(case: dict, reference_bytes: bytes) -> dict:
    if sha(bytes(reference_bytes)) != case.get("reference_sha256"):
        raise ValueError("reference_hash_mismatch")
    if case.get("status") != "scored":
        return {"classification": "not_scored", "case": case}
    prediction = case.get("prediction")
    if not isinstance(prediction, str) or not prediction.strip():
        raise ValueError("empty_prediction")
    reference = reference_text(reference_bytes)
    fresh = strict_case(reference, prediction)
    aligned = occurrence_case(reference, prediction)
    if fresh != case.get("metrics"):
        raise ValueError("replay_mismatch")
    for key in ("occurrence_hits", "occurrence_total", "occurrence_false_positives"):
        if case.get(key) != aligned[key]:
            raise ValueError("replay_mismatch")
    if case.get("normalized_prediction") != normalize_recognition(prediction):
        raise ValueError("replay_mismatch")
    return {"classification": "verified", "case": case}
