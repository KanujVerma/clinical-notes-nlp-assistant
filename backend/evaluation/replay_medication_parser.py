"""Replay the deterministic medication parser on gold and saved OCR transcripts.

Development-only diagnostic. Never contacts Ollama, modifies original scores,
or claims an independent holdout evaluation. Original source PNG hashes and
all model-prediction source bindings are checked before scoring.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from evaluation.local_vision_eval import FIELDS, _score_counts, score_occurrences  # noqa: E402
from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from extractors.pipeline import run_pipeline  # noqa: E402


def _json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise ValueError("INVALID_MEDICATION_REPLAY_INPUT")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("INVALID_MEDICATION_REPLAY_INPUT") from exc
    if not isinstance(value, dict):
        raise ValueError("INVALID_MEDICATION_REPLAY_INPUT")
    return value


def score_frozen_transcriptions(manifest_path: Path, report_path: Path) -> dict:
    """Return case-level and aggregate strict record scores with source checks."""
    images, metadata = load_gold_manifest(manifest_path)
    manifest = _json(manifest_path)
    report = _json(report_path)
    if (manifest.get("annotation_status") != "synthetic_generator_ground_truth"
            or report.get("status") != "completed_local_actual_predictions"
            or report.get("synthetic_only") is not True
            or report.get("not_clinical_validation") is not True
            or report.get("dataset", {}).get("manifest_sha256") != metadata["manifest_sha256"]):
        raise ValueError("MEDICATION_REPLAY_PROVENANCE_MISMATCH")

    if set(report.get("arms_run", [])) != {"tesseract", "glm_ocr", "qwen3_vl"}:
        raise ValueError("MEDICATION_REPLAY_ARMS_MISMATCH")

    gold_cases = manifest.get("cases")
    if not isinstance(gold_cases, list) or len(gold_cases) != len(images):
        raise ValueError("MEDICATION_REPLAY_GOLD_MISMATCH")
    gold_by_id = {case["id"]: case for case in gold_cases}
    image_by_id = {image["id"]: image["source_sha256"] for image in images}
    if len(gold_by_id) != len(images) or set(gold_by_id) != set(image_by_id):
        raise ValueError("MEDICATION_REPLAY_GOLD_MISMATCH")

    transcripts: dict[str, dict[str, str]] = {
        "gold_text": {case["id"]: case["reference_text"] for case in gold_cases}
    }
    for arm in ("glm_ocr", "tesseract"):
        recorded = report.get("cases", {}).get(arm)
        if not isinstance(recorded, list) or len(recorded) != len(images):
            raise ValueError("MEDICATION_REPLAY_CASE_MISMATCH")
        arm_text: dict[str, str] = {}
        for row in recorded:
            if not isinstance(row, dict):
                raise ValueError("MEDICATION_REPLAY_CASE_MISMATCH")
            case_id = row.get("case_id")
            if (case_id not in image_by_id or case_id in arm_text
                    or row.get("source_sha256") != image_by_id[case_id]
                    or not isinstance(row.get("transcription"), str)):
                raise ValueError("MEDICATION_REPLAY_SOURCE_MISMATCH")
            arm_text[case_id] = row["transcription"]
        if set(arm_text) != set(image_by_id):
            raise ValueError("MEDICATION_REPLAY_CASE_MISMATCH")
        transcripts[arm] = arm_text

    results: dict[str, dict] = {}
    for arm, text_by_id in transcripts.items():
        cases: list[dict] = []
        tp = fp = fn = 0
        for case in gold_cases:
            case_id = case["id"]
            expected = case.get("expected_medications")
            if not isinstance(expected, list):
                raise ValueError("MEDICATION_REPLAY_GOLD_MISMATCH")
            parsed = run_pipeline(text_by_id[case_id])["medications"]
            score = score_occurrences(expected, parsed, FIELDS, "name")
            tp += score["tp"]
            fp += score["fp"]
            fn += score["fn"]
            cases.append({
                "case_id": case_id,
                "source_sha256": image_by_id[case_id],
                "counts": {k: score[k] for k in ("tp", "fp", "fn", "support")},
                "mismatches": score["mismatches"],
                "predictions": [
                    {k: med.get(k, "") for k in ("name", "dose", "route", "frequency", "action", "span", "source")}
                    for med in parsed
                ],
            })
        results[arm] = {
            **_score_counts(tp, fp, fn),
            "support": sum(len(c.get("expected_medications", [])) for c in gold_cases),
            "cases": cases,
        }

    return {
        "status": "completed_frozen_development_medication_parser_replay",
        "evidence_tier": "posthoc_development_corpus",
        "is_new_model_run": False,
        "synthetic_only": True,
        "not_clinical_validation": True,
        "corpus_role": "seen_development_cases_not_independent_holdout",
        "source_manifest_sha256": metadata["manifest_sha256"],
        "source_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "original_model_digests": report.get("model_digests"),
        "original_model_run_git_sha": report.get("git_sha"),
        "original_model_scores_unchanged": {
            arm: report["summary"][arm]["deterministic_pipeline"]["medications"]
            for arm in ("tesseract", "glm_ocr")
        },
        "results": results,
        "limitations": [
            "The parser was developed after inspecting these 30 cases; scores are in-sample",
            "Gold text isolates parsing from OCR; saved GLM and Tesseract outputs reuse existing model predictions",
            "No human handwriting, independent holdout, real patient data, or clinical validation",
            "Only fields explicitly annotated in the synthetic gold are scored",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/evaluation")
    opts = parser.parse_args()
    try:
        result = score_frozen_transcriptions(opts.manifest, opts.report)
        result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(result, indent=2, sort_keys=True).encode("utf-8")
        output = opts.output_dir / (
            "medication_parser_replay_" + hashlib.sha256(encoded).hexdigest()[:16] + ".json"
        )
        opts.output_dir.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError("MEDICATION_REPLAY_OUTPUT_EXISTS")
        output.write_bytes(encoded)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("MEDICATION_REPLAY_NOT_COMPLETED: " + type(exc).__name__, file=sys.stderr)
        return 2
    for arm, scored in result["results"].items():
        print(
            f"{arm}: TP={scored['tp']} FP={scored['fp']} FN={scored['fn']} "
            f"strict F1={scored['f1']:.4f}"
        )
    print("MEDICATION_REPLAY_COMPLETED: " + str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
