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


def public_showcase(path: Path = BASELINE_FILE, recordings: Path = RECORDED_FILE) -> dict:
    baseline = verified_tesseract_baseline(path)
    ai = verified_recorded_ai(baseline, recordings)
    return {
        "schema_version": "1",
        "synthetic_only": True,
        "ready_for_clinical_use": False,
        "baseline": baseline,
        "recorded_ai": ai,
        "notice": "Source-image and medication truth are not inferred from model agreement.",
    }
