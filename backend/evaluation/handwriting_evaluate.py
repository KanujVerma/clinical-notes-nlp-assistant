"""PR9: real local evaluation + independent replay on sealed fictional handwriting.

NO handwritten images are bundled. This cannot create real handwriting,
human reviewers, verified clinical annotations, or accuracy claims from CI.
The original PR8 parser/scorer/vision prompts remain unchanged.

python backend/evaluation/handwriting_evaluate.py execute --sealed data/handwriting-private/sealed-v1 --output artifacts/handwriting-private/run1
python backend/evaluation/handwriting_evaluate.py replay --sealed data/handwriting-private/sealed-v1 --run artifacts/handwriting-private/run1 --output artifacts/handwriting-private/replay1
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from evaluation.handwriting_study import MODEL_TAGS, load_object, verify_seal  # noqa: E402
from evaluation.local_vision_eval import (  # noqa: E402
    FIELDS, VITAL_FIELDS, _score_counts, _score_text, run_evaluation, pytesseract,
    score_occurrences,
)
from evaluation.local_ollama_resource_sampler import LocalOllamaResourceSampler  # noqa: E402
from evaluation.paired_holdout_analysis import _deterministic_candidates  # noqa: E402
from evaluation.run_paired_holdout import (  # noqa: E402
    _preflight_models, _swap_used_macos_bytes, _write_json_once,
    _report_source_pointer,
)
from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from services.inference_pipeline import InferenceBindingError, get_installed_model_digest  # noqa: E402

ARMS = ("tesseract", "glm_ocr", "qwen3_vl")
MIN_PILOT_CASES = 12
MIN_PILOT_WRITERS = 3
MIN_TARGET_CASES = 24


def _validate_study_for_run(sealed: Path) -> tuple[dict, dict, dict]:
    seal = verify_seal(sealed)
    if seal["scorable_count"] < MIN_PILOT_CASES:
        raise ValueError("HANDWRITING_INSUFFICIENT_HUMAN_COHORT")
    manifest = load_object(sealed / "scored_manifest.json")
    scored_writers = {
        case["human_provenance"]["writer_pseudonym"]
        for case in manifest["cases"]
    }
    if len(scored_writers) < MIN_PILOT_WRITERS:
        raise ValueError("HANDWRITING_INSUFFICIENT_HUMAN_COHORT")
    _, info = load_gold_manifest(sealed / "scored_manifest.json")
    if (info["annotation_status"] != "independent_human_transcription"
            or info["manifest_sha256"] != seal["scored_manifest_sha256"]
            or len(manifest["cases"]) != seal["scorable_count"]):
        raise ValueError("HANDWRITING_UNSEALED_EVALUATION_INPUT")
    # A pilot with <24 independent source images is always exploratory.
    return seal, manifest, info


def _check_score(expected: list, actual: list, stored: dict,
                 fields: tuple, identity: str) -> None:
    correct = score_occurrences(expected, actual, fields, identity)
    if stored != correct:
        raise ValueError("HANDWRITING_CASE_SCORE_REPLAY_MISMATCH")


def _case_scores(row: dict, arm: str) -> tuple[dict, dict]:
    if arm == "qwen3_vl":
        return row["medications"], row["vitals"]
    det = row.get("deterministic_pipeline")
    if not isinstance(det, dict):
        raise ValueError("HANDWRITING_MISSING_FROZEN_PARSER_SCORE")
    return det["medications"], det["vitals"]


def verify_single_arm_report(path: Path, arm: str, metadata: dict,
                             reference: dict[str, dict]) -> dict:
    """Independently verify every saved prediction and every derived count."""
    if arm not in ARMS:
        raise ValueError("HANDWRITING_UNKNOWN_EVALUATION_ARM")
    report = load_object(path)
    digest = (report.get("model_digests") or {}).get(arm)
    if (report.get("status") != "completed_local_actual_predictions"
            or report.get("synthetic_only") is not True
            or report.get("not_clinical_validation") is not True
            or report.get("dataset") != metadata
            or report.get("arms_run") != [arm]
            or not isinstance(digest, str) or not digest.strip()
            or not isinstance(report.get("cases"), dict)
            or set(report["cases"]) != {arm}
            or not isinstance(report["cases"][arm], list)
            or len(report["cases"][arm]) != len(reference)
            or not isinstance(report.get("summary"), dict)
            or set(report["summary"]) != {arm}):
        raise ValueError("HANDWRITING_INCOMPLETE_UNBOUND_MODEL_REPORT")
    rows = {}
    for row in report["cases"][arm]:
        if not isinstance(row, dict):
            raise ValueError("HANDWRITING_INVALID_MODEL_ROW")
        ident = row.get("case_id")
        if ident in rows or ident not in reference:
            raise ValueError("HANDWRITING_DUPLICATE_MISSING_CASE")
        gold = reference[ident]
        if (row.get("source_sha256") != gold["sha256"]
                or row.get("source_type") != "handwritten"
                or type(row.get("latency_ms")) is not int
                or row["latency_ms"] < 0):
            raise ValueError("HANDWRITING_IMAGE_OR_LATENCY_MISMATCH")
        if arm != "qwen3_vl":
            text = row.get("transcription")
            if not isinstance(text, str) or row.get("text_metrics") != _score_text(
                    gold["reference_text"], text, gold["critical_tokens"]):
                raise ValueError("HANDWRITING_OCR_REPLAY_MISMATCH")
            medications, vitals = _deterministic_candidates(text)
        else:
            if row.get("text_metrics") is not None or "transcription" in row:
                raise ValueError("HANDWRITING_QWEN_IS_NOT_OCR")
            proposal = row.get("structured_candidates")
            if (not isinstance(proposal, dict)
                    or not isinstance(proposal.get("medications"), list)
                    or not isinstance(proposal.get("vitals"), list)):
                raise ValueError("HANDWRITING_QWEN_CANDIDATES_INVALID")
            medications, vitals = proposal["medications"], proposal["vitals"]
        med_score, vit_score = _case_scores(row, arm)
        _check_score(gold["expected_medications"], medications, med_score, FIELDS, "name")
        _check_score(gold["expected_vitals"], vitals, vit_score, VITAL_FIELDS, "vital_type")
        rows[ident] = row
    if set(rows) != set(reference):
        raise ValueError("HANDWRITING_DUPLICATE_MISSING_CASE")

    original = report["summary"][arm]
    if original.get("cases") != len(reference):
        raise ValueError("HANDWRITING_AGGREGATE_CHANGED")
    latencies = sorted(x["latency_ms"] for x in rows.values())
    if (original.get("total_latency_ms") != sum(latencies)
            or original.get("latency_p50_ms") != latencies[len(latencies)//2]
            or original.get("latency_p95_ms") != latencies[int(len(latencies)*.95)]):
        raise ValueError("HANDWRITING_LATENCY_SUMMARY_CHANGED")

    for category, index in (("medications", 0), ("vitals", 1)):
        sc = [_case_scores(row, arm)[index] for row in rows.values()]
        totals = {key: sum(s[key] for s in sc)
                  for key in ("tp", "fp", "fn", "support")}
        derived = _score_counts(totals["tp"], totals["fp"], totals["fn"])
        target = (original.get("deterministic_pipeline") or {}).get(category) \
            if arm != "qwen3_vl" else original.get(category)
        if not isinstance(target, dict) or any(target.get(k) != v for k, v in
                                               {**totals, **derived}.items()):
            raise ValueError("HANDWRITING_AGGREGATE_CHANGED")

    if arm != "qwen3_vl":
        metrics = [x["text_metrics"] for x in rows.values()]
        chars = sum(x["character_distance"] for x in metrics)
        words = sum(x["word_distance"] for x in metrics)
        char_ref = sum(x["ref_chars"] for x in metrics)
        word_ref = sum(x["ref_words"] for x in metrics)
        critical = [c for x in metrics for c in x["critical_tokens"]]
        values = {
            "character_distance": chars,
            "word_distance": words,
            "reference_characters": char_ref,
            "reference_words": word_ref,
            "cer_micro": chars / char_ref if char_ref else None,
            "wer_micro": words / word_ref if word_ref else None,
            "critical_token_hits": sum(int(c["recognized"]) for c in critical),
            "critical_token_total": len(critical),
            "critical_token_recall": (sum(int(c["recognized"]) for c in critical) / len(critical)
                                      if critical else None),
        }
        if any(original.get(k) != v for k, v in values.items()):
            raise ValueError("HANDWRITING_OCR_AGGREGATE_CHANGED")
    return {
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "model_digest_or_version": digest,
        "summary": original,
        "cases": rows,
    }


def compare_reports(sealed: Path, reports: dict[str, Path],
                    resource_reports: dict[str, dict] | None = None) -> dict:
    if set(reports) != set(ARMS):
        raise ValueError("HANDWRITING_ALL_THREE_ARMS_REQUIRED")
    seal, manifest, metadata = _validate_study_for_run(sealed)
    gold = {c["id"]: c for c in manifest["cases"]}
    validated = {
        arm: verify_single_arm_report(reports[arm], arm, metadata, gold)
        for arm in ARMS
    }
    case_details, pairwise = [], {}
    for case in manifest["cases"]:
        ident = case["id"]
        detail = {"case_id": ident, "source_sha256": case["sha256"],
                  "writing_style": case["writing_style"],
                  "capture_quality": case["capture_quality"], "arms": {}}
        for arm in ARMS:
            result = validated[arm]["cases"][ident]
            meds, vitals = _case_scores(result, arm)
            detail["arms"][arm] = {
                "medications": {k: meds[k] for k in ("tp", "fp", "fn", "mismatches")},
                "vitals": {k: vitals[k] for k in ("tp", "fp", "fn", "mismatches")},
                "medication_exact": not meds["fp"] and not meds["fn"],
                "vital_exact": not vitals["fp"] and not vitals["fn"],
                "missed_critical_strings": (
                    [x["token"] for x in result["text_metrics"]["critical_tokens"]
                     if not x["recognized"]] if arm != "qwen3_vl" else None
                ),
                "cer": result["text_metrics"]["cer"] if arm != "qwen3_vl" else None,
                "latency_ms": result["latency_ms"],
            }
        case_details.append(detail)
    for first, second in (("glm_ocr", "tesseract"), ("qwen3_vl", "glm_ocr"),
                          ("qwen3_vl", "tesseract")):
        stats = {}
        for category, label in (("medications", "medication_exact"), ("vitals", "vital_exact")):
            win = loss = tie = 0
            for case in case_details:
                a = case["arms"][first][label]
                b = case["arms"][second][label]
                win += a and not b
                loss += b and not a
                tie += a == b
            stats[category] = {"first_exact_only": win, "second_exact_only": loss, "tie": tie}
        pairwise[first + "_vs_" + second] = stats
    strata: dict[str, dict] = {}
    for dimension in ("writing_style", "capture_quality"):
        groups = {}
        for label in sorted(set(case[dimension] for case in case_details)):
            cases = [c for c in case_details if c[dimension] == label]
            metric = {}
            for arm in ARMS:
                c = [case["arms"][arm]["medications"] for case in cases]
                tp = sum(x["tp"] for x in c)
                fp = sum(x["fp"] for x in c)
                fn = sum(x["fn"] for x in c)
                metric[arm] = {**_score_counts(tp, fp, fn),
                               "case_count": len(cases)}
            groups[label] = metric
        strata[dimension] = groups
    return {
        "status": "completed_sealed_local_handwriting_comparison",
        "annotation_status": "independent_human_transcription_attested_not_proven",
        "synthetic_only": True,
        "genuine_handwriting_attested_not_independently_verified": True,
        "not_clinical_validation": True,
        "not_a_patient_data_benchmark": True,
        "dataset_id": seal["dataset_id"],
        "sealed_manifest_sha256": seal["scored_manifest_sha256"],
        "cohort_seal_sha256": hashlib.sha256(
            (sealed / "study_seal.json").read_bytes()).hexdigest(),
        "all_images_count": seal["case_count"],
        "scored_images_count": seal["scorable_count"],
        "predeclared_unscorable_case_ids": seal["unscorable_case_ids"],
        "cohort_phase": seal["cohort_phase"],
        "meets_minimum_24_case_target": seal["scorable_count"] >= MIN_TARGET_CASES
            and seal["writer_count"] >= MIN_PILOT_WRITERS,
        "model_tags": MODEL_TAGS,
        "arm_summaries": {
            arm: {
                "digest_or_version": validated[arm]["model_digest_or_version"],
                "original_report_sha256": validated[arm]["file_sha256"],
                "summary": validated[arm]["summary"],
                "resource_observation": (resource_reports or {}).get(arm, {
                    "status": "not_measured_in_replay",
                }),
            } for arm in ARMS
        },
        "paired_exact_case_comparisons": pairwise,
        "stratified_medication_metrics": strata,
        "case_details": case_details,
        "limitations": [
            "Human handwriting origin and actor independence are externally attested, not cryptographically proven",
            "All gold is independently transcribed and adjudicated by claimed humans; software cannot establish authenticity",
            "Every predeclared excluded/ambiguous sample remains in dataset denominator",
            "One limited fictional handwriting sample, NOT clinical validation or deployable OCR",
            "No post-hoc prompt, parser, or alias retuning against the sealed cohort",
            "Model self-reported shape and runtime memory observations are not accuracy proof",
        ],
    }


def execute(sealed: Path, output: Path) -> dict:
    seal, _, _ = _validate_study_for_run(sealed)
    installed = _preflight_models()  # exact model tags, only LOCAL Ollama endpoint
    if output.exists():
        raise ValueError("HANDWRITING_RESULT_OUTPUT_EXISTS")
    output.mkdir(parents=True, exist_ok=False)
    _write_json_once(output / "execution_status.json", {
        "status": "not_yet_completed",
        "cohort_seal_sha256": hashlib.sha256(
            (sealed / "study_seal.json").read_bytes()).hexdigest(),
        "note": "Only completion_receipt.json attests all three arms completed",
    })
    reports, observations = {}, {}
    for arm in ARMS:
        # Verify that original annotated gold, images and evaluation source
        # remained unchanged even during long, one-arm-at-a-time inference.
        verify_seal(sealed)
        before = _swap_used_macos_bytes()
        with LocalOllamaResourceSampler((arm,)) as observer:
            report = run_evaluation(sealed / "scored_manifest.json", (arm,),
                                    output / "raw_reports" / arm)
        after = _swap_used_macos_bytes()
        recorded = load_object(report)
        try:
            after_digest = (get_installed_model_digest(MODEL_TAGS[arm])
                            if arm in MODEL_TAGS else
                            str(pytesseract.get_tesseract_version()))
        except (ValueError, OSError, RuntimeError, InferenceBindingError) as exc:
            raise RuntimeError("HANDWRITING_MODEL_DIGEST_UNAVAILABLE_AFTER_RUN") from exc
        if (recorded.get("model_digests", {}).get(arm) != installed[arm]
                or after_digest != installed[arm]):
            raise ValueError("HANDWRITING_MODEL_ID_CHANGED_DURING_RUN")
        reports[arm] = report
        observations[arm] = {
            **observer.report(),
            "system_swap_before_bytes": before,
            "system_swap_after_bytes": after,
            "memory_note": "Total system snapshots, not attributable isolated model RAM/VRAM peak",
        }
        verify_seal(sealed)
        print("HANDWRITING_REAL_ARM_COMPLETED:" + arm, flush=True)
    paired = compare_reports(sealed, reports, observations)
    paired["execution_provenance"] = {
        "execution_kind": "real_local_inference_self_reported",
        "model_tags": MODEL_TAGS,
        "preflight_digests": installed,
        "mac_or_host_system": platform.system(),
        "host_architecture": platform.machine(),
        "utc_completed": datetime.now(timezone.utc).isoformat(),
        "no_model_download_or_remote_api": True,
    }
    _write_json_once(output / "paired_handwriting_results.json", paired)
    _write_json_once(output / "completion_receipt.json", {
        "status": paired["status"],
        "cohort_seal_sha256": paired["cohort_seal_sha256"],
        "paired": _report_source_pointer(output / "paired_handwriting_results.json"),
        "arm_files": {arm: _report_source_pointer(path) for arm, path in reports.items()},
    })
    return paired


def replay(sealed: Path, original_run: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("HANDWRITING_RESULT_OUTPUT_EXISTS")
    receipt = load_object(original_run / "completion_receipt.json")
    original = load_object(original_run / "paired_handwriting_results.json")
    reports = {}
    if receipt.get("status") != "completed_sealed_local_handwriting_comparison":
        raise ValueError("HANDWRITING_COMPLETION_RECEIPT_REQUIRED")
    for arm in ARMS:
        source = original_run / "raw_reports" / arm
        choices = list(source.glob("paired_local_*.json"))
        if len(choices) != 1:
            raise ValueError("HANDWRITING_ORIGINAL_ARM_REPORT_MISSING")
        reports[arm] = choices[0]
    audit = compare_reports(sealed, reports)
    paired_source = original_run / "paired_handwriting_results.json"
    if (not isinstance(receipt.get("paired"), dict)
            or receipt["paired"].get("sha256") != hashlib.sha256(paired_source.read_bytes()).hexdigest()
            or receipt.get("cohort_seal_sha256") != audit["cohort_seal_sha256"]
            or not isinstance(receipt.get("arm_files"), dict)
            or set(receipt["arm_files"]) != set(ARMS)
            or original.get("case_details") != audit["case_details"]
            or original.get("paired_exact_case_comparisons") !=
                audit["paired_exact_case_comparisons"]
            or original.get("stratified_medication_metrics") !=
                audit["stratified_medication_metrics"]):
        raise ValueError("HANDWRITING_ORIGINAL_COMPARISON_RECEIPT_MISMATCH")
    provenance = original.get("execution_provenance")
    if (not isinstance(provenance, dict)
            or provenance.get("model_tags") != MODEL_TAGS
            or provenance.get("execution_kind") != "real_local_inference_self_reported"):
        raise ValueError("HANDWRITING_MODEL_IDENTITY_UNATTESTED")
    before = provenance.get("preflight_digests")
    if not isinstance(before, dict) or set(before) != set(ARMS):
        raise ValueError("HANDWRITING_MODEL_IDENTITY_UNATTESTED")
    summaries = original.get("arm_summaries")
    if not isinstance(summaries, dict) or set(summaries) != set(ARMS):
        raise ValueError("HANDWRITING_MODEL_IDENTITY_UNATTESTED")
    for arm in ARMS:
        att = receipt["arm_files"][arm]
        verified = audit["arm_summaries"][arm]
        orig = summaries[arm]
        if (not isinstance(att, dict) or not isinstance(orig, dict)
                or before[arm] != verified["digest_or_version"]
                or orig.get("digest_or_version") != verified["digest_or_version"]
                or orig.get("original_report_sha256") != verified["original_report_sha256"]
                or orig.get("summary") != verified["summary"]
                or att.get("sha256") != verified["original_report_sha256"]):
            raise ValueError("HANDWRITING_MODEL_OR_SUMMARY_HASH_MISMATCH")
    # Verify ALL raw annotation records remain sealed, not only scored items.
    verify_seal(sealed)
    audit["offline_replay"] = {
        "status": "original_scores_and_identity_receipt_verified",
        "new_model_calls": False,
        "original_paired_sha256": hashlib.sha256(paired_source.read_bytes()).hexdigest(),
        "original_receipt_sha256": hashlib.sha256(
            (original_run / "completion_receipt.json").read_bytes()).hexdigest(),
        "limit": "Self-reported source provenance, not signed proof of actual model hardware",
    }
    output.mkdir(parents=True, exist_ok=False)
    _write_json_once(output / "verified_handwriting_results.json", audit)
    return audit


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    for kind in ("execute", "replay"):
        c = commands.add_parser(kind)
        c.add_argument("--sealed", type=Path, required=True)
        c.add_argument("--output", type=Path, required=True)
        if kind == "replay":
            c.add_argument("--run", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == "execute":
            result = execute(args.sealed, args.output)
        else:
            result = replay(args.sealed, args.run, args.output)
    except (ValueError, KeyError, OSError, RuntimeError, TypeError, InferenceBindingError) as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z0-9_:-]{2,120}", code):
            code = "HANDWRITING_EVALUATION_FAILED"
        print("HANDWRITING_EVALUATION_NOT_COMPLETED:" + code, file=sys.stderr)
        return 2
    print("HANDWRITING_EVALUATION_VERIFIED:" + result["sealed_manifest_sha256"])
    for arm in ARMS:
        summary = result["arm_summaries"][arm]["summary"]
        medications = (summary.get("deterministic_pipeline") or {}).get("medications") \
            if arm != "qwen3_vl" else summary.get("medications")
        print("HANDWRITING_ARM_OBSERVED:" + json.dumps({
            "arm": arm,
            "cases": summary["cases"],
            "medications": {k: medications[k] for k in ("tp", "fp", "fn", "f1")},
            "cer_micro": summary.get("cer_micro") if arm != "qwen3_vl" else None,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
