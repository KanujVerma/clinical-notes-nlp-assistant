"""Paired local-only visual evaluation: Tesseract, GLM-OCR and Qwen3-VL.

No remote or paid model endpoints, no model download, no fabricated predictions.
Tesseract/GLM are scored on exact image-to-text CER/WER. Qwen3-VL is scored
separately on structured medication/vital fields, *not* text OCR metrics.
Synthetic development data does not establish clinical performance.

Example:
    python backend/evaluation/generate_synthetic_visual_cases.py --output data/vision_gold
    python backend/evaluation/local_vision_eval.py --manifest data/vision_gold/manifest.json --arms tesseract
    python backend/evaluation/local_vision_eval.py --manifest data/vision_gold/manifest.json --arms tesseract,glm_ocr,qwen3_vl

The second command works without Ollama if Tesseract is installed. The third
fails closed unless both configured local Ollama models are installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from PIL import Image  # noqa: E402
import pytesseract  # noqa: E402

from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from services.inference_pipeline import get_installed_model_digest  # noqa: E402
from services.multimodal_service import glm_ocr_infer, qwen3_vl_infer, calculate_cer_wer  # noqa: E402


ARMS = ("tesseract", "glm_ocr", "qwen3_vl")
FIELDS = ("name", "dose", "route", "frequency", "action")
VITAL_FIELDS = ("vital_type", "value", "unit")


def parse_arms(value: str) -> tuple[str, ...]:
    arms = tuple(piece.strip() for piece in value.split(","))
    if not arms or any(a not in ARMS for a in arms) or len(set(arms)) != len(arms):
        raise ValueError("INVALID_EVALUATION_ARMS")
    return arms


def _normalize(value: Any) -> str:
    """Transparent whitespace/case normalization only; preserves units/decimals."""
    return " ".join(str(value if value is not None else "").strip().casefold().split())


def _score_counts(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def score_occurrences(
    expected: list[dict], predicted: list[dict], fields: tuple[str, ...],
    identity_field: str,
) -> dict:
    """Source-order pairing for duplicate names, independent from field correctness.

    This comparator does NOT use a Hungarian solver that could pick the
    most accurate dose/route match to improve measured performance. A wrong
    attribute gives one FP and one FN for that occurrence.
    """
    if not isinstance(expected, list) or not isinstance(predicted, list):
        raise ValueError("INVALID_STRUCTURED_LABELS")
    if not all(isinstance(item, dict) and _normalize(item.get(identity_field))
               for item in expected + predicted):
        raise ValueError("INVALID_STRUCTURED_LABELS")

    groups_exp: dict[str, list[dict]] = {}
    groups_pred: dict[str, list[dict]] = {}
    for item in expected:
        groups_exp.setdefault(_normalize(item[identity_field]), []).append(item)
    for item in predicted:
        groups_pred.setdefault(_normalize(item[identity_field]), []).append(item)

    tp = fp = fn = 0
    mismatches: list[dict] = []
    for name in sorted(set(groups_exp) | set(groups_pred)):
        gold = groups_exp.get(name, [])
        suggestions = groups_pred.get(name, [])
        common = min(len(gold), len(suggestions))
        for occurrence in range(common):
            exp, pred = gold[occurrence], suggestions[occurrence]
            diffs = {
                field: {"expected": exp.get(field), "predicted": pred.get(field)}
                for field in fields
                if field in exp and _normalize(exp.get(field)) != _normalize(pred.get(field))
            }
            if diffs:
                fp += 1
                fn += 1
                mismatches.append({
                    "name": name, "occurrence_index": occurrence,
                    "type": "wrong_attributes", "attributes": diffs,
                })
            else:
                tp += 1
        fp += len(suggestions) - common
        fn += len(gold) - common
        if len(gold) != len(suggestions):
            mismatches.append({
                "name": name, "type": "occurrence_count_mismatch",
                "expected": len(gold), "predicted": len(suggestions),
            })
    return {
        **_score_counts(tp, fp, fn),
        "support": len(expected),
        "mismatches": mismatches,
        "pairing_policy": "name_then_source_occurrence_order",
    }


def exact_critical_tokens(reference: str, hypothesis: str, tokens: list[str]) -> list[dict]:
    """Dose-aware exact substring checks; do not normalize away the decimal."""
    results = []
    for token in tokens:
        if token not in reference:
            raise ValueError("CRITICAL_TOKEN_NOT_IN_GOLD")
        lead = r"(?<![0-9.])" if token[0].isdigit() or token[0] == "." else r"(?<!\w)"
        tail = r"(?![0-9.])" if token[-1].isdigit() or token[-1] == "." else r"(?!\w)"
        pattern = lead + re.escape(token).replace(r"\ ", r"\s+") + tail
        results.append({"token": token, "recognized": bool(re.search(pattern, hypothesis, flags=re.I))})
    return results


def _score_text(reference: str, prediction: str, critical: list[str]) -> dict:
    errors = calculate_cer_wer(reference, prediction)
    # Unlike old clipped per-case display scores, strict CER/WER can exceed 1
    # for hallucinated insertion-heavy outputs. Never hide that with min(1).
    char_ref = errors["ref_chars"]
    word_ref = errors["ref_words"]
    return {
        "character_distance": errors["char_distance"],
        "word_distance": errors["word_distance"],
        "ref_chars": char_ref,
        "ref_words": word_ref,
        "cer": errors["char_distance"] / char_ref if char_ref else None,
        "wer": errors["word_distance"] / word_ref if word_ref else None,
        "critical_tokens": exact_critical_tokens(reference, prediction, critical),
    }


def _validate_structured_gold(manifest: dict, cases: list[dict]) -> dict:
    raw = manifest.get("cases")
    if not isinstance(raw, list) or len(raw) != len(cases):
        raise ValueError("UNMATCHED_STRUCTURED_GOLD")
    by_id = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("id") in by_id:
            raise ValueError("DUPLICATE_STRUCTURED_CASE")
        kind = item.get("source_type", "unknown")
        if kind == "handwritten" and manifest.get("annotation_status") != "independent_human_transcription":
            raise ValueError("HANDWRITING_GOLD_MUST_BE_INDEPENDENT")
        meds = item.get("expected_medications")
        vitals = item.get("expected_vitals")
        if (meds is not None and (not isinstance(meds, list) or
                any(not isinstance(x, dict) for x in meds))):
            raise ValueError("INVALID_MEDICATION_GOLD")
        if (vitals is not None and (not isinstance(vitals, list) or
                any(not isinstance(x, dict) for x in vitals))):
            raise ValueError("INVALID_VITAL_GOLD")
        by_id[item["id"]] = {
            "source_type": kind,
            "medications": meds,
            "vitals": vitals,
        }
    if set(by_id) != {c["id"] for c in cases}:
        raise ValueError("UNMATCHED_STRUCTURED_GOLD")
    return by_id


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=5,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def run_evaluation(manifest_path: Path, arms: tuple[str, ...], output_dir: Path) -> Path:
    if not arms or any(x not in ARMS for x in arms):
        raise ValueError("INVALID_EVALUATION_ARMS")
    cases, metadata = load_gold_manifest(manifest_path)
    gold_data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    gold = _validate_structured_gold(gold_data, cases)

    model_digests: dict[str, str] = {}
    if "glm_ocr" in arms:
        from services.multimodal_service import DEFAULT_OCR_MODEL
        model_digests["glm_ocr"] = get_installed_model_digest(DEFAULT_OCR_MODEL)
    if "qwen3_vl" in arms:
        from services.multimodal_service import DEFAULT_VL_MODEL
        model_digests["qwen3_vl"] = get_installed_model_digest(DEFAULT_VL_MODEL)
    if "tesseract" in arms:
        model_digests["tesseract"] = str(pytesseract.get_tesseract_version())

    outputs: dict[str, list[dict]] = {arm: [] for arm in arms}
    for case in cases:
        reference, source_image = case["reference_text"], case["image_bytes"]
        labeled = gold[case["id"]]
        for arm in arms:
            started = time.perf_counter()
            if arm == "tesseract":
                with Image.open(io.BytesIO(source_image)) as img:
                    prediction = pytesseract.image_to_string(img.convert("RGB"), config="--psm 6")
                text_metrics = _score_text(reference, prediction, case["critical_tokens"])
                record = {"transcription": prediction, "text_metrics": text_metrics}
            elif arm == "glm_ocr":
                outcome = glm_ocr_infer(source_image)
                if outcome.get("status") != "completed":
                    raise RuntimeError("LOCAL_GLM_OCR_INFERENCE_FAILED")
                prediction = outcome.get("transcribed_text")
                if not isinstance(prediction, str):
                    raise RuntimeError("INVALID_GLM_TRANSCRIPTION")
                record = {
                    "transcription": prediction,
                    "text_metrics": _score_text(reference, prediction, case["critical_tokens"]),
                }
            else:
                outcome = qwen3_vl_infer(source_image)
                if outcome.get("status") != "completed":
                    raise RuntimeError("LOCAL_QWEN_VL_INFERENCE_FAILED")
                candidate = outcome.get("candidates") or {}
                if not isinstance(candidate, dict):
                    raise RuntimeError("INVALID_QWEN_CANDIDATES")
                predicted_meds = candidate.get("medications", [])
                predicted_vitals = candidate.get("vitals", [])
                record = {
                    "structured_candidates": candidate,
                    "medications": (
                        score_occurrences(labeled["medications"], predicted_meds, FIELDS, "name")
                        if labeled["medications"] is not None else None
                    ),
                    "vitals": (
                        score_occurrences(labeled["vitals"], predicted_vitals, VITAL_FIELDS, "vital_type")
                        if labeled["vitals"] is not None else None
                    ),
                    "text_metrics": None,  # Qwen candidates are NOT OCR transcriptions.
                }
            outputs[arm].append({
                "case_id": case["id"],
                "source_sha256": case["source_sha256"],
                "source_type": labeled["source_type"],
                "latency_ms": int((time.perf_counter() - started) * 1000),
                **record,
            })

    summaries: dict[str, dict] = {}
    for arm, rows in outputs.items():
        summary = {"cases": len(rows), "total_latency_ms": sum(r["latency_ms"] for r in rows)}
        if arm in ("tesseract", "glm_ocr"):
            metrics = [r["text_metrics"] for r in rows]
            char_errors = sum(m["character_distance"] for m in metrics)
            word_errors = sum(m["word_distance"] for m in metrics)
            ref_chars = sum(m["ref_chars"] for m in metrics)
            ref_words = sum(m["ref_words"] for m in metrics)
            critical = [check for m in metrics for check in m["critical_tokens"]]
            summary.update({
                "character_distance": char_errors,
                "word_distance": word_errors,
                "reference_characters": ref_chars,
                "reference_words": ref_words,
                "cer_micro": char_errors / ref_chars if ref_chars else None,
                "wer_micro": word_errors / ref_words if ref_words else None,
                "critical_token_hits": sum(1 for x in critical if x["recognized"]),
                "critical_token_total": len(critical),
                "critical_token_recall": (
                    sum(1 for x in critical if x["recognized"]) / len(critical)
                    if critical else None
                ),
            })
        else:
            for category in ("medications", "vitals"):
                values = [r[category] for r in rows if r[category] is not None]
                if not values:
                    summary[category] = None
                else:
                    tp = sum(v["tp"] for v in values)
                    fp = sum(v["fp"] for v in values)
                    fn = sum(v["fn"] for v in values)
                    summary[category] = {
                        **_score_counts(tp, fp, fn),
                        "support": sum(v["support"] for v in values),
                    }
        summaries[arm] = summary

    paired = None
    if "tesseract" in arms and "glm_ocr" in arms:
        tes = {r["case_id"]: r for r in outputs["tesseract"]}
        glm = {r["case_id"]: r for r in outputs["glm_ocr"]}
        paired = [{
            "case_id": ident,
            "tesseract_cer": tes[ident]["text_metrics"]["cer"],
            "glm_ocr_cer": glm[ident]["text_metrics"]["cer"],
            "tesseract_wer": tes[ident]["text_metrics"]["wer"],
            "glm_ocr_wer": glm[ident]["text_metrics"]["wer"],
        } for ident in sorted(tes)]

    report = {
        "status": "completed_local_actual_predictions",
        "synthetic_only": True,
        "not_clinical_validation": True,
        "dataset": metadata,
        "git_sha": _git_sha(),
        "model_digests": model_digests,
        "arms_run": list(arms),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summaries,
        "paired_tesseract_glm": paired,
        "cases": outputs,
        "limitations": [
            "Development synthetic printed images are generator-derived, not a held-out dataset",
            "Qwen3-VL structured entity F1 is not character/word OCR accuracy",
            "No handwritten clinical accuracy unless independently transcribed real handwriting cases were run",
            "Local model runtime memory is not estimated from the Python runner's RSS",
            "Critical token presence is not negation or medication-status comprehension",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_bytes = json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
    name = "paired_local_" + hashlib.sha256(report_bytes).hexdigest()[:16] + ".json"
    final = output_dir / name
    with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".local_eval_", suffix=".tmp", delete=False) as file:
        file.write(report_bytes)
        intermediate = Path(file.name)
    try:
        if final.exists():
            raise FileExistsError("EVALUATION_REPORT_ALREADY_EXISTS")
        os.replace(intermediate, final)
    finally:
        intermediate.unlink(missing_ok=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--arms", default="tesseract,glm_ocr,qwen3_vl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "evaluation")
    args = parser.parse_args()
    try:
        result = run_evaluation(args.manifest, parse_arms(args.arms), args.output_dir)
    except (ValueError, RuntimeError, OSError, FileExistsError) as exc:
        code = str(exc) if str(exc).isupper() and "_" in str(exc) else "LOCAL_EVALUATION_FAILED"
        print("EVALUATION_NOT_COMPLETED: " + code, file=sys.stderr)
        return 2
    print("LOCAL_EVALUATION_COMPLETED: " + str(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
