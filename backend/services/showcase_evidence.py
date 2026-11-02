"""Read-only, source-hash-checked synthetic evidence for the public showcase.

Never infer model accuracy from unit mocks. The committed Tesseract baseline is
an actually executed development OCR run; GLM/Qwen examples appear only after
an explicit local capture + human-reviewed commit of a compatible recording.
This service never invokes Ollama, paid APIs, DB writes or untrusted paths.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE_FILE = ROOT / "artifacts" / "evaluation" / "paired_local_030d0865b198675a.json"
RECORDED_FILE = ROOT / "data" / "showcase" / "recorded_ai.json"
FROZEN_BENCHMARK_FILE = ROOT / "data" / "showcase" / "frozen_24_image_benchmark.json"

# Counts copied from docs/validation/PR8_REAL_THREE_ARM_RESULTS.md.
# They describe one frozen Mac run. They are not a new measurement.
_FROZEN_ARM_COUNTS = {
    "tesseract": {
        "medication_tp": 11, "medication_fp": 3, "medication_fn": 12,
        "vital_tp": 4, "vital_fp": 0, "vital_fn": 1,
        "cer_errors": 124, "cer_chars": 2896, "wer_errors": 164, "wer_words": 494,
        "critical_hits": 42, "critical_total": 55, "ocr_available": True,
    },
    "glm_ocr": {
        "medication_tp": 23, "medication_fp": 0, "medication_fn": 0,
        "vital_tp": 5, "vital_fp": 0, "vital_fn": 0,
        "cer_errors": 17, "cer_chars": 2896, "wer_errors": 13, "wer_words": 494,
        "critical_hits": 55, "critical_total": 55, "ocr_available": True,
    },
    "qwen3_vl": {
        "medication_tp": 15, "medication_fp": 8, "medication_fn": 8,
        "vital_tp": 0, "vital_fp": 7, "vital_fn": 5,
        "cer_errors": None, "cer_chars": None, "wer_errors": None, "wer_words": None,
        "critical_hits": None, "critical_total": None, "ocr_available": False,
    },
}
MAX_BYTES = 400_000
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


class ShowcaseEvidenceError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _read_json(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ShowcaseEvidenceError("SHOWCASE_EVIDENCE_MISSING")
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, ShowcaseEvidenceError):
            raise
        raise ShowcaseEvidenceError("SHOWCASE_EVIDENCE_INVALID") from exc
    if not isinstance(obj, dict):
        raise ShowcaseEvidenceError("SHOWCASE_EVIDENCE_INVALID")
    return obj


def verified_tesseract_baseline(path: Path = BASELINE_FILE) -> dict:
    data = _read_json(path)
    arms = data.get("arms_run")
    entries = data.get("cases")
    dataset = data.get("dataset") or {}
    summary = (data.get("summary") or {}).get("tesseract") or {}
    digest = (data.get("model_digests") or {}).get("tesseract")
    if (data.get("status") != "completed_local_actual_predictions"
            or data.get("synthetic_only") is not True
            or data.get("not_clinical_validation") is not True
            or arms != ["tesseract"]
            or not isinstance(entries, dict)
            or not isinstance(entries.get("tesseract"), list)
            or not isinstance(dataset, dict)
            or not isinstance(dataset.get("manifest_sha256"), str)
            or not _SHA.fullmatch(dataset["manifest_sha256"])
            or dataset.get("annotation_status") != "synthetic_generator_ground_truth"
            or not isinstance(digest, str) or len(digest) > 60):
        raise ShowcaseEvidenceError("BASELINE_INVALID")

    samples = []
    counts = {"ref_chars": 0, "ref_words": 0, "char_distance": 0,
              "word_distance": 0, "critical_hits": 0, "critical_total": 0}
    seen = set()
    for entry in entries["tesseract"]:
        if not isinstance(entry, dict):
            raise ShowcaseEvidenceError("BASELINE_INVALID")
        case_id = entry.get("case_id")
        source_sha = entry.get("source_sha256")
        transcription = entry.get("transcription")
        metrics = entry.get("text_metrics")
        if (not isinstance(case_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", case_id)
                or case_id in seen or not isinstance(source_sha, str)
                or not _SHA.fullmatch(source_sha) or not isinstance(transcription, str)
                or len(transcription) > 20_000 or not isinstance(metrics, dict)):
            raise ShowcaseEvidenceError("BASELINE_INVALID")
        seen.add(case_id)
        critical = metrics.get("critical_tokens")
        if not isinstance(critical, list):
            raise ShowcaseEvidenceError("BASELINE_INVALID")
        for m, source in (("ref_chars", "ref_chars"), ("ref_words", "ref_words"),
                          ("char_distance", "character_distance"), ("word_distance", "word_distance")):
            number = metrics.get(source)
            if type(number) is not int or number < 0:
                raise ShowcaseEvidenceError("BASELINE_INVALID")
            counts[m] += number
        for token in critical:
            if (not isinstance(token, dict) or not isinstance(token.get("token"), str)
                    or type(token.get("recognized")) is not bool):
                raise ShowcaseEvidenceError("BASELINE_INVALID")
            counts["critical_total"] += 1
            counts["critical_hits"] += int(token["recognized"])
        samples.append({
            "case_id": case_id,
            "source_sha256": source_sha,
            "source_type": entry.get("source_type", "synthetic_printed"),
            "transcription": transcription,
            "cer": counts_safe_rate(metrics["character_distance"], metrics["ref_chars"]),
            "wer": counts_safe_rate(metrics["word_distance"], metrics["ref_words"]),
            "critical_tokens": critical,
        })

    if (not 1 <= len(samples) <= 100
            or len(samples) != dataset.get("case_count")
            or summary.get("critical_token_hits") != counts["critical_hits"]
            or summary.get("critical_token_total") != counts["critical_total"]
            or summary.get("character_distance") != counts["char_distance"]
            or summary.get("word_distance") != counts["word_distance"]):
        raise ShowcaseEvidenceError("BASELINE_SUMMARY_MISMATCH")

    return {
        "status": "recorded_real_tesseract",
        "model": "Tesseract",
        "engine_version": digest,
        "dataset_id": dataset.get("dataset_id", "synthetic_development"),
        "annotation_status": dataset["annotation_status"],
        "manifest_sha256": dataset["manifest_sha256"],
        "case_count": len(samples),
        "cer_micro": counts_safe_rate(counts["char_distance"], counts["ref_chars"]),
        "wer_micro": counts_safe_rate(counts["word_distance"], counts["ref_words"]),
        "critical_token_hits": counts["critical_hits"],
        "critical_token_total": counts["critical_total"],
        "cases": samples,
        "source": "committed_local_tesseract_run",
        "limitations": "Three generator-produced printed development cases; not handwriting or clinical validation.",
    }


def counts_safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def verified_recorded_ai(
    baseline: dict, path: Path = RECORDED_FILE,
) -> dict:
    """Require a vetted, versioned model-result fixture with exact source hashes."""
    if not path.exists():
        return {
            "status": "not_recorded",
            "models": [],
            "message": "No reviewed GLM-OCR or Qwen3-VL recording has been committed.",
        }
    data = _read_json(path)
    if (data.get("schema_version") != "1"
            or data.get("synthetic_only") is not True
            or data.get("independently_reviewed") is not True
            or data.get("source_manifest_sha256") != baseline["manifest_sha256"]
            or not isinstance(data.get("model_runs"), list)
            or not 1 <= len(data["model_runs"]) <= 2):
        raise ShowcaseEvidenceError("RECORDED_AI_INVALID")

    source_map = {item["case_id"]: item["source_sha256"] for item in baseline["cases"]}
    recorded = []
    unique = set()
    for run in data["model_runs"]:
        if not isinstance(run, dict):
            raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
        model = run.get("adapter")
        digest = run.get("model_digest")
        cases = run.get("cases")
        if (model not in ("glm_ocr", "qwen3_vl") or model in unique
                or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
                or not isinstance(cases, list) or len(cases) != len(source_map)):
            raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
        unique.add(model)
        valid_cases = []
        seen = set()
        for item in cases:
            if not isinstance(item, dict):
                raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
            case_id = item.get("case_id")
            if (not isinstance(case_id, str) or case_id in seen or case_id not in source_map
                    or item.get("source_sha256") != source_map[case_id]):
                raise ShowcaseEvidenceError("RECORDED_AI_SOURCE_MISMATCH")
            seen.add(case_id)
            if model == "glm_ocr":
                prediction = item.get("transcription")
                if not isinstance(prediction, str) or not prediction.strip() or len(prediction) > 20_000:
                    raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
                safe_result: dict[str, Any] = {"transcription": prediction}
            else:
                candidates = item.get("structured_candidates")
                if not isinstance(candidates, dict):
                    raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
                meds = candidates.get("medications")
                vitals = candidates.get("vitals")
                if (not isinstance(meds, list) or len(meds) > 50
                        or not isinstance(vitals, list) or len(vitals) > 50
                        or any(not isinstance(x, dict) for x in meds + vitals)):
                    raise ShowcaseEvidenceError("RECORDED_AI_INVALID")
                safe_result = {"structured_candidates": {
                    "medications": meds, "vitals": vitals,
                }}
            valid_cases.append({"case_id": case_id, "source_sha256": item["source_sha256"], **safe_result})
        if seen != set(source_map):
            raise ShowcaseEvidenceError("RECORDED_AI_SOURCE_MISMATCH")
        recorded.append({
            "adapter": model,
            "model_digest": digest,
            "cases": valid_cases,
            "source": "curator_reviewed_local_recording",
            "not_clinical_validation": True,
        })
    return {
        "status": "recorded_model_proposals_unverified",
        "models": recorded,
        "message": "Model proposals were recorded locally; visual claims still require human source verification.",
    }


def _rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _f1(tp: int, fp: int, fn: int) -> float | None:
    denom = (2 * tp) + fp + fn
    if denom == 0:
        return None
    return (2 * tp) / denom


def verified_frozen_benchmark(path: Path = FROZEN_BENCHMARK_FILE) -> dict:
    """Published aggregate for the frozen 24-image run. No raw transcripts."""
    data = _read_json(path)
    if (data.get("schema_version") != "1"
            or data.get("dataset_role") != "frozen_printed_synthetic_image_benchmark"
            or data.get("synthetic_only") is not True
            or data.get("not_clinical_validation") is not True
            or data.get("raw_recordings_published") is not False
            or data.get("case_count") != 24
            or data.get("attempted_cases") != 24
            or data.get("exclusions") != 0
            or data.get("medication_support") != 23
            or data.get("vital_support") != 5
            or data.get("manifest_sha256") != "c30cfdd3ce457b157d1ee89a7859dfbe137c71e17990e84dcab49a74c6e6c332"
            or data.get("evidence_zip_sha256") != "d073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d"
            or data.get("source_document") != "docs/validation/PR8_REAL_THREE_ARM_RESULTS.md"):
        raise ShowcaseEvidenceError("FROZEN_BENCHMARK_INVALID")
    arms_in = data.get("arms")
    if not isinstance(arms_in, list) or [a.get("id") for a in arms_in] != list(_FROZEN_ARM_COUNTS):
        raise ShowcaseEvidenceError("FROZEN_BENCHMARK_INVALID")
    published = []
    for arm in arms_in:
        expected = _FROZEN_ARM_COUNTS[arm["id"]]
        if any(arm.get(key) != value for key, value in expected.items()):
            raise ShowcaseEvidenceError("FROZEN_BENCHMARK_COUNT_MISMATCH")
        if arm.get("cases") or arm.get("transcription") or arm.get("raw_transcript"):
            raise ShowcaseEvidenceError("FROZEN_BENCHMARK_RAW_RECORDING")
        med_f1 = _f1(arm["medication_tp"], arm["medication_fp"], arm["medication_fn"])
        vital_f1 = _f1(arm["vital_tp"], arm["vital_fp"], arm["vital_fn"])
        published.append({
            "id": arm["id"],
            "label": arm.get("label") or arm["id"],
            "medication_tp": arm["medication_tp"],
            "medication_fp": arm["medication_fp"],
            "medication_fn": arm["medication_fn"],
            "medication_precision": _rate(arm["medication_tp"], arm["medication_tp"] + arm["medication_fp"]),
            "medication_recall": _rate(arm["medication_tp"], arm["medication_tp"] + arm["medication_fn"]),
            "medication_f1": med_f1,
            "vital_tp": arm["vital_tp"],
            "vital_fp": arm["vital_fp"],
            "vital_fn": arm["vital_fn"],
            "vital_f1": vital_f1,
            "ocr_cer": _rate(arm["cer_errors"], arm["cer_chars"]),
            "ocr_wer": _rate(arm["wer_errors"], arm["wer_words"]),
            "ocr_available": arm["ocr_available"],
            "critical_hits": arm["critical_hits"],
            "critical_total": arm["critical_total"],
        })
    examples = data.get("documented_failure_examples")
    if not isinstance(examples, list) or not examples or len(examples) > 8:
        raise ShowcaseEvidenceError("FROZEN_BENCHMARK_INVALID")
    for example in examples:
        if not isinstance(example, dict) or example.get("raw_transcript"):
            raise ShowcaseEvidenceError("FROZEN_BENCHMARK_RAW_RECORDING")
        summary = example.get("summary")
        if not isinstance(summary, str) or len(summary) > 240:
            raise ShowcaseEvidenceError("FROZEN_BENCHMARK_INVALID")
    return {
        "dataset_role": data["dataset_role"],
        "case_count": 24,
        "attempted_cases": 24,
        "valid_predictions": 24,
        "exclusions": 0,
        "medication_support": 23,
        "vital_support": 5,
        "manifest_sha256": data["manifest_sha256"],
        "evidence_zip_sha256": data["evidence_zip_sha256"],
        "source_document": data["source_document"],
        "matcher": "source_occurrence_first_bounded_assignment",
        "raw_recordings_published": False,
        "not_clinical_validation": True,
        "separate_from": [
            "synthetic_development_20_note_corpus",
            "tesseract_development_recording_3_case",
        ],
        "arms": published,
        "documented_failure_examples": examples,
        "limitations": (
            "One frozen 24-image printed-synthetic run. Scores are not paired with the "
            "3-case Tesseract development recording or the 20-note text corpus, and they "
            "are not a clinical or handwriting result. Raw model transcripts are not published here."
        ),
    }


def public_showcase(
    path: Path = BASELINE_FILE,
    recordings: Path = RECORDED_FILE,
    frozen_benchmark: Path = FROZEN_BENCHMARK_FILE,
) -> dict:
    baseline = verified_tesseract_baseline(path)
    ai = verified_recorded_ai(baseline, recordings)
    frozen = verified_frozen_benchmark(frozen_benchmark)
    return {
        "schema_version": "1",
        "synthetic_only": True,
        "ready_for_clinical_use": False,
        "baseline": baseline,
        "recorded_ai": ai,
        "frozen_benchmark": frozen,
        "notice": "Source-image and medication truth are not inferred from model agreement.",
    }
