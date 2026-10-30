"""Strict, read-only comparison of three REAL single-arm holdout reports.

Uses the unchanged PR7 frozen scorer. This module never performs inference,
retunes a parser, fabricates predictions, or labels Qwen output as OCR text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.holdout_cases_v1 import CASES
from evaluation.local_vision_eval import (
    FIELDS, VITAL_FIELDS, _score_text, _score_counts, score_occurrences,
)
from evaluation.prospective_holdout import validate_freeze, validate_case_partition
from evaluation.vision_benchmark import load_gold_manifest
from extractors.pipeline import run_pipeline

ARMS = ("tesseract", "glm_ocr", "qwen3_vl")
CANONICAL_MANIFEST_SHA256 = "c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332"
CANONICAL_DATASET_ID = "prospective_printed_synthetic_holdout_v1"


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("INVALID_MODEL_REPORT")
    return obj


def canonical_manifest(manifest_path: Path, lock_path: Path) -> tuple[dict, dict[str, dict]]:
    """Verify both frozen source code and exact PR7 image+gold bytes."""
    lock = validate_freeze(lock_path)
    validate_case_partition()
    validated, metadata = load_gold_manifest(manifest_path)
    payload = _read_json(manifest_path)
    if (metadata["manifest_sha256"] != CANONICAL_MANIFEST_SHA256
            or metadata["dataset_id"] != CANONICAL_DATASET_ID
            or metadata["case_count"] != 24
            or payload.get("annotation_status") != "synthetic_generator_ground_truth"
            or payload.get("synthetic_only") is not True
            or payload.get("frozen_baseline_commit") != lock["frozen_baseline_commit"]
            or payload.get("frozen_case_definition_git_blob") != lock["frozen_case_definition_git_blob"]):
        raise ValueError("CANONICAL_HOLDOUT_MANIFEST_MISMATCH")
    gold = payload.get("cases")
    if not isinstance(gold, list) or len(gold) != len(CASES):
        raise ValueError("CANONICAL_HOLDOUT_CASES_MISMATCH")
    for fixture, annotated, source in zip(CASES, gold, validated):
        if (annotated.get("id") != fixture["id"]
                or source["id"] != fixture["id"]
                or annotated.get("source_type") != fixture["type"]
                or annotated.get("reference_text") != "\n".join(fixture["lines"])
                or annotated.get("critical_tokens") != fixture["critical_tokens"]
                or annotated.get("expected_medications") != fixture["expected_medications"]
                or annotated.get("expected_vitals") != fixture["expected_vitals"]
                or annotated.get("sha256") != source["source_sha256"]):
            raise ValueError("CANONICAL_HOLDOUT_CASES_MISMATCH")
    return metadata, {x["id"]: x for x in gold}


def _deterministic_candidates(transcription: str) -> tuple[list[dict], list[dict]]:
    """Same field adapter as the hash-frozen local_vision_eval.py, for auditing."""
    pipeline = run_pipeline(transcription)
    meds = []
    for m in pipeline.get("medications", []):
        frequency = str(m.get("frequency", "")).strip()
        qualifier = str(m.get("qualifier", "")).strip().lower()
        folded = frequency.lower()
        if "as needed" in qualifier and "as needed" not in folded:
            frequency = (frequency + " as needed").strip()
        elif "prn" in qualifier and "prn" not in folded:
            frequency = (frequency + " PRN").strip()
        meds.append({
            "name": m.get("name", ""), "dose": m.get("dose", ""),
            "route": m.get("route", ""), "frequency": frequency,
            "action": m.get("action", ""),
        })
    vitals = []
    for vital_type, item in pipeline.get("vitals", {}).items():
        value = str(item.get("value", "")).strip()
        if value.endswith("%"):
            vitals.append({"vital_type": vital_type, "value": value[:-1].strip(), "unit": "%"})
        else:
            parts = value.split()
            vitals.append({
                "vital_type": vital_type,
                "value": parts[0] if parts else "",
                "unit": parts[1] if len(parts) >= 2 else "",
            })
    return meds, vitals


def _metrics(row: dict, arm: str) -> tuple[dict, dict]:
    if arm in ("tesseract", "glm_ocr"):
        det = row.get("deterministic_pipeline")
        if not isinstance(det, dict):
            raise ValueError("MISSING_DETERMINISTIC_SCORES")
        return det.get("medications"), det.get("vitals")
    return row.get("medications"), row.get("vitals")


def _verify_score(expected: list[dict], predicted: list[dict], stored: dict,
                  fields: tuple[str, ...], identity: str) -> dict:
    calculated = score_occurrences(expected, predicted, fields, identity)
    if not isinstance(stored, dict) or calculated != stored:
        raise ValueError("MODEL_SCORE_REPLAY_MISMATCH")
    if stored["support"] != len(expected):
        raise ValueError("MODEL_GOLD_SUPPORT_MISMATCH")
    return stored


def verify_single_arm_report(path: Path, arm: str, metadata: dict,
                             gold: dict[str, dict]) -> dict[str, Any]:
    """Recompute every case score from retained predictions and frozen rules."""
    if arm not in ARMS:
        raise ValueError("INVALID_ARM")
    report = _read_json(path)
    if (report.get("status") != "completed_local_actual_predictions"
            or report.get("synthetic_only") is not True
            or report.get("not_clinical_validation") is not True
            or report.get("arms_run") != [arm]
            or report.get("dataset") != metadata
            or not isinstance(report.get("model_digests"), dict)
            or set(report["model_digests"]) != {arm}
            or not isinstance(report["model_digests"][arm], str)
            or not report["model_digests"][arm].strip()):
        raise ValueError("INCOMPLETE_OR_MISBOUND_REAL_MODEL_REPORT")
    cases = report.get("cases")
    summary = report.get("summary")
    if (not isinstance(cases, dict) or set(cases) != {arm}
            or not isinstance(cases[arm], list)
            or len(cases[arm]) != len(gold)
            or not isinstance(summary, dict) or set(summary) != {arm}):
        raise ValueError("MISSING_OR_EXTRA_CASES")
    observed = {}
    for row in cases[arm]:
        if not isinstance(row, dict):
            raise ValueError("INVALID_MODEL_CASE")
        case_id = row.get("case_id")
        if case_id not in gold or case_id in observed:
            raise ValueError("MISSING_DUPLICATE_OR_UNKNOWN_CASE")
        expected = gold[case_id]
        if (row.get("source_sha256") != expected["sha256"]
                or row.get("source_type") != expected["source_type"]
                or type(row.get("latency_ms")) is not int
                or row["latency_ms"] < 0):
            raise ValueError("MODEL_SOURCE_OR_LATENCY_MISMATCH")
        if arm in ("tesseract", "glm_ocr"):
            text = row.get("transcription")
            if not isinstance(text, str):
                raise ValueError("MISSING_REAL_OCR_TRANSCRIPTION")
            if row.get("text_metrics") != _score_text(
                expected["reference_text"], text, expected["critical_tokens"],
            ):
                raise ValueError("OCR_TEXT_METRICS_CHANGED")
            pred_meds, pred_vitals = _deterministic_candidates(text)
        else:
            if row.get("text_metrics") is not None or "transcription" in row:
                raise ValueError("QWEN_STRUCTURED_OUTPUT_IS_NOT_OCR")
            candidates = row.get("structured_candidates")
            if (not isinstance(candidates, dict)
                    or not isinstance(candidates.get("medications"), list)
                    or not isinstance(candidates.get("vitals"), list)):
                raise ValueError("MISSING_QWEN_STRUCTURED_CANDIDATES")
            pred_meds, pred_vitals = candidates["medications"], candidates["vitals"]
        ms, vs = _metrics(row, arm)
        _verify_score(expected["expected_medications"], pred_meds, ms, FIELDS, "name")
        _verify_score(expected["expected_vitals"], pred_vitals, vs, VITAL_FIELDS, "vital_type")
        observed[case_id] = row
    if set(observed) != set(gold):
        raise ValueError("MISSING_DUPLICATE_OR_UNKNOWN_CASE")

    reported = summary[arm]
    if not isinstance(reported, dict) or reported.get("cases") != len(gold):
        raise ValueError("MODEL_AGGREGATE_MISMATCH")
    rows = list(observed.values())
    for category in ("medications", "vitals"):
        scores = [_metrics(row, arm)[0 if category == "medications" else 1] for row in rows]
        target = (reported.get("deterministic_pipeline") or {}).get(category) \
            if arm != "qwen3_vl" else reported.get(category)
        if not isinstance(target, dict):
            raise ValueError("MODEL_AGGREGATE_MISMATCH")
        counts = {key: sum(s[key] for s in scores)
                  for key in ("tp", "fp", "fn", "support")}
        derived = _score_counts(counts["tp"], counts["fp"], counts["fn"])
        if (any(counts[key] != target.get(key) for key in counts)
                or any(derived[key] != target.get(key)
                       for key in ("precision", "recall", "f1"))):
            raise ValueError("MODEL_AGGREGATE_MISMATCH")
    times = sorted(row["latency_ms"] for row in rows)
    if (reported.get("total_latency_ms") != sum(times)
            or reported.get("latency_p50_ms") != times[len(times)//2]
            or reported.get("latency_p95_ms") != times[int(len(times)*.95)]):
        raise ValueError("MODEL_LATENCY_AGGREGATE_MISMATCH")
    if arm in ("tesseract", "glm_ocr"):
        texts = [x["text_metrics"] for x in rows]
        chars = sum(x["character_distance"] for x in texts)
        words = sum(x["word_distance"] for x in texts)
        ref_chars = sum(x["ref_chars"] for x in texts)
        ref_words = sum(x["ref_words"] for x in texts)
        checks = [y for x in texts for y in x["critical_tokens"]]
        if (reported.get("character_distance") != chars
                or reported.get("word_distance") != words
                or reported.get("reference_characters") != ref_chars
                or reported.get("reference_words") != ref_words
                or reported.get("cer_micro") != (chars / ref_chars if ref_chars else None)
                or reported.get("wer_micro") != (words / ref_words if ref_words else None)
                or reported.get("critical_token_hits") != sum(bool(x["recognized"]) for x in checks)
                or reported.get("critical_token_total") != len(checks)
                or reported.get("critical_token_recall") != (
                    sum(bool(x["recognized"]) for x in checks) / len(checks)
                    if checks else None
                )):
            raise ValueError("OCR_AGGREGATE_MISMATCH")
    return {
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "model_digest_or_version": report["model_digests"][arm],
        "git_sha_recorded": report.get("git_sha"),
        "summary": reported,
        "cases": observed,
    }


def _is_exact(score: dict) -> bool:
    return score["fp"] == 0 and score["fn"] == 0


def compare_paired_reports(manifest_path: Path, lock_path: Path,
                           model_reports: dict[str, Path],
                           resources: dict[str, dict] | None = None) -> dict[str, Any]:
    """Do not produce paired metrics without all three full REAL arm reports."""
    if set(model_reports) != set(ARMS):
        raise ValueError("THREE_REAL_ARMS_REQUIRED")
    metadata, gold = canonical_manifest(manifest_path, lock_path)
    validated = {
        arm: verify_single_arm_report(model_reports[arm], arm, metadata, gold)
        for arm in ARMS
    }
    resources = resources or {}
    comparisons: dict[str, dict] = {}
    case_details = []
    for case_id, source in gold.items():
        row = {
            "case_id": case_id,
            "source_type": source["source_type"],
            "image_sha256": source["sha256"],
            "gold_medications": len(source["expected_medications"]),
            "gold_vitals": len(source["expected_vitals"]),
            "arms": {},
        }
        for arm in ARMS:
            result = validated[arm]["cases"][case_id]
            meds, vitals = _metrics(result, arm)
            row["arms"][arm] = {
                "medications": {
                    "tp": meds["tp"], "fp": meds["fp"], "fn": meds["fn"],
                    "strict_exact": _is_exact(meds),
                    "mismatches": meds["mismatches"],
                },
                "vitals": {
                    "tp": vitals["tp"], "fp": vitals["fp"], "fn": vitals["fn"],
                    "strict_exact": _is_exact(vitals),
                    "mismatches": vitals["mismatches"],
                },
                "latency_ms": result["latency_ms"],
                "cer": result["text_metrics"]["cer"] if arm != "qwen3_vl" else None,
                "wer": result["text_metrics"]["wer"] if arm != "qwen3_vl" else None,
                "missed_critical_tokens": [
                    item["token"] for item in (result.get("text_metrics") or {}).get("critical_tokens", [])
                    if not item["recognized"]
                ] if arm != "qwen3_vl" else None,
            }
        case_details.append(row)
    for first, second in (("glm_ocr", "tesseract"), ("qwen3_vl", "glm_ocr"),
                          ("qwen3_vl", "tesseract")):
        stats: dict[str, Any] = {}
        for category in ("medications", "vitals"):
            wins = losses = ties = 0
            for row in case_details:
                a = row["arms"][first][category]["strict_exact"]
                b = row["arms"][second][category]["strict_exact"]
                wins += a and not b
                losses += b and not a
                ties += a == b
            stats[category] = {"first_exact_only": wins,
                               "second_exact_only": losses, "tie": ties}
        if first != "qwen3_vl" and second != "qwen3_vl":
            cer = {"glm_lower_cer": 0, "tesseract_lower_cer": 0, "equal": 0}
            for row in case_details:
                a = row["arms"]["glm_ocr"]["cer"]
                b = row["arms"]["tesseract"]["cer"]
                cer["glm_lower_cer" if a < b else
                    "tesseract_lower_cer" if b < a else "equal"] += 1
            stats["paired_ocr_cer"] = cer
        else:
            stats["paired_ocr_cer"] = None
        comparisons[first + "_vs_" + second] = stats

    return {
        "status": "completed_three_arm_local_paired_synthetic_comparison",
        "synthetic_only": True,
        "not_clinical_validation": True,
        "independent_human_gold": False,
        "genuine_handwriting_tested": False,
        "no_automatic_medication_routing_decision": True,
        "frozen_baseline_commit": validate_freeze(lock_path)["frozen_baseline_commit"],
        "dataset_id": metadata["dataset_id"],
        "manifest_sha256": metadata["manifest_sha256"],
        "case_count": 24,
        "arms_run": list(ARMS),
        "scoring": "unchanged_frozen_source_occurrence_strict_medication_fields",
        "arm_summaries": {
            arm: {
                "model_digest_or_version": validated[arm]["model_digest_or_version"],
                "original_report_sha256": validated[arm]["report_sha256"],
                "recorded_git_sha": validated[arm]["git_sha_recorded"],
                "summary": validated[arm]["summary"],
                "out_of_process_resources": resources.get(arm, {
                    "status": "not_measured_in_compare_only",
                }),
            } for arm in ARMS
        },
        "paired_exact_case_comparisons": comparisons,
        "case_details": case_details,
        "limitations": [
            "Only 24 new generator-authored synthetic printed/photographed-effect images",
            "Same case source bytes and annotated gold across all three arms",
            "GLM and Tesseract are OCR plus frozen deterministic parser; Qwen is direct structured output",
            "Qwen has no character/word OCR metrics; never assign a CER or WER",
            "One run per arm, not repeated-seed statistical confidence or calibration",
            "Model self-reported visual boxes are not source-verified image coordinates",
            "Memory polling can miss short model loads; missing measurements remain unmeasured",
            "No patient data, genuine handwriting, autonomous medical decisions, or clinical validation",
        ],
    }
