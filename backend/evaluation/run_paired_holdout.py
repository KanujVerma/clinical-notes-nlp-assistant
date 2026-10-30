"""Run three ACTUAL local model arms on the exact PR7 24-image frozen holdout.

The PR8 scoring wrapper never changes the locked extraction/parser/scorer/gold.
By default, execute all three arms sequentially to limit RAM on a 16-GB Mac.
A missing model or non-loopback Ollama endpoint fails BEFORE writing results.
No Ollama downloads, remote APIs, EHR integration, or patient data.

Use the complete, original dataset/ directory in GitHub run #41003374761:
    gh run download 41003374761 -n prospective-synthetic-holdout-tesseract-only -D artifacts/pr7-source
    python backend/evaluation/run_paired_holdout.py --manifest artifacts/pr7-source/dataset/manifest.json --preflight
    python backend/evaluation/run_paired_holdout.py --manifest artifacts/pr7-source/dataset/manifest.json --output artifacts/pr8-local --execute

For independent verification of already recorded full-arm outputs (no models):
    python backend/evaluation/run_paired_holdout.py --manifest ... --output artifacts/pr8-replay --compare-only --tesseract-report FILE --glm-report FILE --qwen-report FILE
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from evaluation.local_vision_eval import run_evaluation, pytesseract  # noqa: E402
from evaluation.local_ollama_resource_sampler import LocalOllamaResourceSampler  # noqa: E402
from evaluation.paired_holdout_analysis import (  # noqa: E402
    ARMS, canonical_manifest, compare_paired_reports,
)
from services.inference_pipeline import get_installed_model_digest, InferenceBindingError  # noqa: E402
from services.multimodal_service import (  # noqa: E402
    DEFAULT_OCR_MODEL, DEFAULT_VL_MODEL, _ensure_local_ollama_endpoint,
)

DEFAULT_LOCK = ROOT / "docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json"
MODELS = {"glm_ocr": DEFAULT_OCR_MODEL, "qwen3_vl": DEFAULT_VL_MODEL}
REQUIRED_MODEL_TAGS = {"glm_ocr": "glm-ocr:q8_0", "qwen3_vl": "qwen3-vl:4b"}


def _swap_used_macos_bytes() -> int | None:
    """A single OS snapshot, NEVER a peak or attributable model-memory measure."""
    if platform.system() != "Darwin":
        return None
    try:
        raw = subprocess.run(
            ["sysctl", "-n", "vm.swapusage"], check=True,
            capture_output=True, text=True, timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\bused\s*=\s*(\d+(?:\.\d+)?)\s*([KMGT])", raw, re.I)
    if not match:
        return None
    return int(float(match.group(1)) * 1024 ** ("KMGT".index(match.group(2).upper()) + 1))


def _preflight_models() -> dict[str, str]:
    """Verify frozen model IDs, and exact installed tags before inference."""
    # The frozen visual adapters read OLLAMA_OCR_MODEL/OLLAMA_VL_MODEL from the
    # environment. An overridden tag could label Qwen outputs as GLM results,
    # so do not allow any alternate model identity in this pre-registered test.
    if MODELS != REQUIRED_MODEL_TAGS:
        raise ValueError("NONCANONICAL_LOCAL_MODEL_TAGS")
    _ensure_local_ollama_endpoint()
    versions = {"tesseract": str(pytesseract.get_tesseract_version())}
    for arm in ("glm_ocr", "qwen3_vl"):
        try:
            digest = get_installed_model_digest(MODELS[arm])
        except (OSError, InferenceBindingError, ValueError, RuntimeError) as exc:
            raise RuntimeError("LOCAL_MODEL_NOT_INSTALLED_OR_UNREACHABLE:" + arm) from exc
        if not isinstance(digest, str) or not digest.strip():
            raise RuntimeError("LOCAL_MODEL_DIGEST_NOT_AVAILABLE:" + arm)
        versions[arm] = digest
    return versions


def _write_json_once(path: Path, payload: dict) -> None:
    if path.exists():
        raise ValueError("IMMUTABLE_REPORT_ALREADY_EXISTS")
    raw = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(raw)


def _report_source_pointer(path: Path) -> dict:
    return {
        "file_name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def execute(manifest_path: Path, lock_path: Path, output_dir: Path) -> dict:
    metadata, _ = canonical_manifest(manifest_path, lock_path)
    installed = _preflight_models()  # No output or inference on missing models.
    if output_dir.exists():
        raise ValueError("PAIRED_OUTPUT_DIRECTORY_EXISTS")
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json_once(output_dir / "execution_status.json", {
        "status": "not_yet_completed", "arms_required": list(ARMS),
        "canonical_manifest_sha256": metadata["manifest_sha256"],
        "note": "Partial artifacts are not a successful paired comparison.",
    })
    reports = {}
    resource_reports = {}
    for arm in ARMS:
        print("ACTUAL_LOCAL_ARM_START:" + arm, flush=True)
        swap_before = _swap_used_macos_bytes()
        with LocalOllamaResourceSampler((arm,)) as sampler:
            report = run_evaluation(manifest_path, (arm,), output_dir / "single_arm_reports" / arm)
        swap_after = _swap_used_macos_bytes()
        reports[arm] = report
        resource_reports[arm] = {
            **sampler.report(),
            "system_swap_used_before_bytes": swap_before,
            "system_swap_used_after_bytes": swap_after,
            "swap_measurement_note": (
                "Two point-in-time global swap snapshots, not peak swap, "
                "not attributable solely to this model or to Ollama."
            ),
        }
        # A model tag may change WHILE its 24 images are being processed.
        # The original report records only its pre-inference digest, so
        # independently re-query the installed tag now, after inference.
        try:
            live_digest = (get_installed_model_digest(MODELS[arm])
                           if arm in MODELS
                           else str(pytesseract.get_tesseract_version()))
        except (OSError, InferenceBindingError, ValueError, RuntimeError) as exc:
            raise RuntimeError("MODEL_DIGEST_UNAVAILABLE_AFTER_RUN:" + arm) from exc
        recorded = json.loads(report.read_text(encoding="utf-8"))
        if (recorded.get("model_digests", {}).get(arm) != installed[arm]
                or live_digest != installed[arm]):
            raise ValueError("MODEL_DIGEST_CHANGED_DURING_EVALUATION:" + arm)
        print("ACTUAL_LOCAL_ARM_COMPLETED:" + arm, flush=True)

    paired = compare_paired_reports(manifest_path, lock_path, reports, resource_reports)
    paired["run_provenance"] = {
        "execution_type": "real_local_inference_not_mocked",
        "source_manifest_sha256": metadata["manifest_sha256"],
        "utc_completed": datetime.now(timezone.utc).isoformat(),
        "os_system": platform.system(),
        "os_machine": platform.machine(),
        "python_version": platform.python_version(),
        "model_tags": MODELS,
        "model_digests_or_version_preflight": installed,
        "original_arm_report_locations": {
            arm: str(reports[arm].relative_to(output_dir)) for arm in ARMS
        },
        "no_external_apis_or_model_downloads": True,
        "all_three_arms_required": True,
    }
    _write_json_once(output_dir / "paired_comparison.json", paired)
    # Do not overwrite the initial status file; instead create a final
    # completion receipt whose existence requires all 3 arms to validate.
    _write_json_once(output_dir / "completion_receipt.json", {
        "status": "completed_three_arm_local_paired_synthetic_comparison",
        "paired_report": _report_source_pointer(output_dir / "paired_comparison.json"),
        "source_manifest_sha256": metadata["manifest_sha256"],
        "arm_files": {
            arm: _report_source_pointer(reports[arm]) for arm in ARMS
        },
    })
    return paired


def compare_only(manifest_path: Path, lock_path: Path, output_dir: Path,
                 reports: dict[str, Path]) -> dict:
    if output_dir.exists():
        raise ValueError("PAIRED_OUTPUT_DIRECTORY_EXISTS")
    # No model endpoints or downloads are accessed in this branch.
    paired = compare_paired_reports(manifest_path, lock_path, reports)
    output_dir.mkdir(parents=True, exist_ok=False)
    paired["run_provenance"] = {
        "execution_type": "offline_replay_of_submitted_single_arm_reports",
        "new_model_calls": False,
        "original_arm_files": {arm: _report_source_pointer(path)
                               for arm, path in reports.items()},
    }
    _write_json_once(output_dir / "paired_comparison.json", paired)
    return paired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true",
                      help="Validate frozen source/image/gold only; NO model inference")
    mode.add_argument("--execute", action="store_true",
                      help="Run ALL three real local model arms sequentially")
    mode.add_argument("--compare-only", action="store_true",
                      help="Audit all three already captured model reports, NO inference")
    parser.add_argument("--tesseract-report", type=Path)
    parser.add_argument("--glm-report", type=Path)
    parser.add_argument("--qwen-report", type=Path)
    args = parser.parse_args()

    try:
        meta, _ = canonical_manifest(args.manifest, args.lock)
        if args.preflight:
            if args.output or args.tesseract_report or args.glm_report or args.qwen_report:
                raise ValueError("PREFLIGHT_ACCEPTS_NO_OUTPUT_OR_REPORTS")
            print("PAIRED_PREFLIGHT_VERIFIED_CANONICAL_24_CASES:" + meta["manifest_sha256"])
            return 0
        if args.output is None:
            raise ValueError("OUTPUT_DIRECTORY_REQUIRED")
        if args.execute:
            if args.tesseract_report or args.glm_report or args.qwen_report:
                raise ValueError("EXECUTE_DOES_NOT_CONSUME_PRIOR_REPORTS")
            paired = execute(args.manifest, args.lock, args.output)
        else:
            reports = {
                "tesseract": args.tesseract_report,
                "glm_ocr": args.glm_report,
                "qwen3_vl": args.qwen_report,
            }
            if any(path is None for path in reports.values()):
                raise ValueError("THREE_ORIGINAL_MODEL_REPORT_PATHS_REQUIRED")
            paired = compare_only(args.manifest, args.lock, args.output, reports)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError,
            InferenceBindingError) as exc:
        # No uploaded patient text or model source document is printed.
        code = str(exc)
        if not re.fullmatch(r"[A-Z0-9_:-]{2,120}", code):
            code = "PAIRED_COMPARISON_FAILED"
        print("PAIRED_COMPARISON_NOT_COMPLETED:" + code, file=sys.stderr)
        return 2

    print("PAIRED_COMPARISON_COMPLETED:" + paired["manifest_sha256"])
    for arm in ARMS:
        stats = paired["arm_summaries"][arm]["summary"]
        category = (stats.get("deterministic_pipeline") or {}).get("medications") \
            if arm != "qwen3_vl" else stats.get("medications")
        print("REAL_PAIRED_ARM_SUMMARY:" + json.dumps({
            "arm": arm, "cases": stats["cases"],
            "medications": {k: category[k] for k in ("tp", "fp", "fn", "f1", "support")},
            "cer_micro": stats.get("cer_micro") if arm != "qwen3_vl" else None,
            "latency_p50_ms": stats["latency_p50_ms"],
            "model_digest_or_version": paired["arm_summaries"][arm]["model_digest_or_version"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
