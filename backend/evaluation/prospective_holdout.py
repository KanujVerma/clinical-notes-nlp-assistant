"""Generate and evaluate a pre-committed synthetic printed-image holdout.

The baseline parser/scorer file blobs and case-definition blob are sealed in
a reviewed lock. Scores are NOT tuning criteria; modifying the parser or gold
after seeing these predictions invalidates the prospective designation.

This is not independently human-annotated data, genuine handwriting, or
clinical validation. No remote models or automatic downloads are permitted.

Examples:
  python backend/evaluation/prospective_holdout.py --lock docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json --output artifacts/holdout --arms tesseract
  python backend/evaluation/prospective_holdout.py --lock docs/validation/PROSPECTIVE_HOLDOUT_LOCK.json --output artifacts/holdout-local --arms tesseract,glm_ocr,qwen3_vl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from evaluation.generate_synthetic_visual_cases import make_image_for_case  # noqa: E402
from evaluation.local_vision_eval import parse_arms, run_evaluation  # noqa: E402
from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from evaluation.holdout_cases_v1 import CASES  # noqa: E402
from evaluation.local_ollama_resource_sampler import LocalOllamaResourceSampler  # noqa: E402

CATEGORIES = ("printed_clean", "printed_degraded", "photographed")
FROZEN_SOURCE_PATHS = (
    "backend/extractors/medication_orders.py",
    "backend/extractors/medications.py",
    "backend/extractors/patterns/medications.json",
    "backend/extractors/pipeline.py",
    "backend/extractors/sections.py",
    "backend/extractors/preprocess.py",
    "backend/extractors/normalize.py",
    "backend/evaluation/local_vision_eval.py",
    "backend/evaluation/vision_benchmark.py",
    "backend/evaluation/vision_vital_aliases.py",
    "backend/evaluation/generate_synthetic_visual_cases.py",
    "backend/services/inference_pipeline.py",
    "backend/services/multimodal_service.py",
)
OLD_DEV_MANIFEST = ROOT / "data/vision_gold_30/manifest.json"


def _blob_sha(content: bytes) -> str:
    """Git SHA-1 blob hash, not a plain file digest."""
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def _read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("INVALID_HOLDOUT_JSON")
    return obj


def validate_freeze(lock_path: Path) -> dict:
    """Fail closed if scorer, parser, prompt, renderer, or case gold changed."""
    lock = _read_json(lock_path)
    if (lock.get("lock_version") != "prospective_synthetic_v1"
            or lock.get("synthetic_only") is not True
            or lock.get("annotation_status") != "synthetic_generator_ground_truth"
            or not re.fullmatch(r"[0-9a-f]{40}", str(lock.get("frozen_baseline_commit", "")))
            or lock.get("previous_development_cases") != 30):
        raise ValueError("UNFROZEN_EVALUATION_CONTRACT")
    versions = lock.get("frozen_file_git_blobs")
    if not isinstance(versions, dict) or set(versions) != set(FROZEN_SOURCE_PATHS):
        raise ValueError("UNFROZEN_EVALUATION_CONTRACT")
    for relative, expected in versions.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{40}", expected):
            raise ValueError("UNFROZEN_EVALUATION_CONTRACT")
        if _blob_sha((ROOT / relative).read_bytes()) != expected:
            raise ValueError("FROZEN_EVALUATION_SOURCE_CHANGED:" + relative)
    case_file = BACKEND / "evaluation/holdout_cases_v1.py"
    if _blob_sha(case_file.read_bytes()) != lock.get("frozen_case_definition_git_blob"):
        raise ValueError("FROZEN_HOLDOUT_CASES_CHANGED")
    return lock


def _gold_records(case: dict) -> None:
    meds, vitals = case.get("expected_medications"), case.get("expected_vitals")
    if not isinstance(meds, list) or not isinstance(vitals, list):
        raise ValueError("UNANNOTATED_HOLDOUT_CASE")
    for item in meds:
        if (not isinstance(item, dict) or
                not isinstance(item.get("name"), str) or not item["name"].strip()
                or not isinstance(item.get("dose"), str)):
            # Empty *explicitly annotated* dose is allowed in a dose-free
            # medication mention; missing dose annotation is not.

            raise ValueError("UNANNOTATED_HOLDOUT_MEDICATION")
        for optional in ("route", "frequency", "action"):
            if optional in item and not isinstance(item[optional], str):
                raise ValueError("UNANNOTATED_HOLDOUT_MEDICATION")
    for item in vitals:
        if (not isinstance(item, dict)
                or not all(k in item for k in ("vital_type", "value", "unit"))):
            raise ValueError("UNANNOTATED_HOLDOUT_VITALS")


def validate_case_partition(cases: list[dict] = CASES) -> dict:
    """Check generator fixtures do not reuse the 30 observed source documents."""
    old = _read_json(OLD_DEV_MANIFEST).get("cases", [])
    old_ids = {row["id"] for row in old}
    old_text = {
        hashlib.sha256(row["reference_text"].encode()).hexdigest()
        for row in old
    }
    # Exact medical-order line reuse from the observed corpus is prohibited.
    old_lines = {
        line.strip().casefold()
        for row in old for line in row["reference_text"].splitlines()
        if len(line.strip()) >= 25 and not line.startswith("SYNTHETIC DOCUMENT")
    }
    ids, payload_hashes, kinds = set(), set(), {kind: 0 for kind in CATEGORIES}
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("EXPECTED_24_FROZEN_HOLDOUT_CASES")
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("INVALID_HOLDOUT_CASE")
        ident, kind, lines = item.get("id"), item.get("type"), item.get("lines")
        if (not isinstance(ident, str) or not re.fullmatch(r"h[0-9]{2}_[a-z0-9_]{4,60}", ident)
                or ident in ids or ident in old_ids or kind not in CATEGORIES
                or not isinstance(lines, list) or len(lines) < 2
                or any(not isinstance(s, str) or not s for s in lines)
                or lines[0] != "SYNTHETIC DOCUMENT - NOT FOR CLINICAL USE"):
            raise ValueError("INVALID_HOLDOUT_CASE")
        if any(line.strip().casefold() in old_lines for line in lines[1:]):
            raise ValueError("DEVELOPMENT_LINE_REUSED")
        ids.add(ident)
        kinds[kind] += 1
        text = "\n".join(lines)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h in old_text or h in payload_hashes:
            raise ValueError("DEVELOPMENT_DOCUMENT_REUSED")
        payload_hashes.add(h)
        tokens = item.get("critical_tokens")
        if (not isinstance(tokens, list) or not tokens or
                any(not isinstance(t, str) or t not in text for t in tokens)):
            raise ValueError("INVALID_HOLDOUT_CRITICAL_TOKENS")
        _gold_records(item)
    if set(kinds.values()) != {8}:
        raise ValueError("UNBALANCED_HOLDOUT_IMAGE_CATEGORIES")
    return {"case_count": len(cases), "groups": kinds}


def generate_holdout(lock_path: Path, destination: Path) -> Path:
    """Write hash-pinned images/gold only to a new, nonexisting directory."""
    lock = validate_freeze(lock_path)
    validate_case_partition()
    if destination.exists():
        raise ValueError("HOLDOUT_DESTINATION_EXISTS")
    destination.mkdir(parents=True, exist_ok=False)
    image_dir = destination / "images"
    image_dir.mkdir()
    items = []
    for item in CASES:
        ident = item["id"]
        image = make_image_for_case(item["lines"], item["type"], ident)
        file = image_dir / (ident + ".png")
        image.save(file, "PNG", optimize=False)
        items.append({
            "id": ident,
            "image": "images/" + file.name,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "reference_text": "\n".join(item["lines"]),
            "source_type": item["type"],
            "critical_tokens": item["critical_tokens"],
            "expected_medications": item["expected_medications"],
            "expected_vitals": item["expected_vitals"],
        })
    manifest = {
        "dataset_id": "prospective_printed_synthetic_holdout_v1",
        "synthetic_only": True,
        "annotation_status": "synthetic_generator_ground_truth",
        "validation_role": "parser_frozen_before_corpus_authored",
        "frozen_baseline_commit": lock["frozen_baseline_commit"],
        "frozen_case_definition_git_blob": lock["frozen_case_definition_git_blob"],
        "cases": items,
        "limitations": [
            "Generator-authored fictional images/gold, NOT independent human annotation",
            "Eight printed clean, eight degraded and eight photographed-effect, NOT genuine handwriting",
            "Prospective only relative to pre-committed parser/scorer. No clinical validity",
        ],
    }
    path = destination / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validated, meta = load_gold_manifest(path)
    if len(validated) != 24 or meta["case_count"] != 24:
        raise ValueError("HOLDOUT_GENERATION_INTEGRITY_FAILURE")
    return path


def evaluate(lock_path: Path, destination: Path, arms: tuple[str, ...]) -> dict:
    """Capture real outputs; never tune or modify baseline based on results."""
    lock = validate_freeze(lock_path)
    manifest = generate_holdout(lock_path, destination / "dataset")
    with LocalOllamaResourceSampler(arms) as resources:
        record_path = run_evaluation(manifest, arms, destination / "model_results")
    run = _read_json(record_path)
    # Low-level local_vision_eval retains its original generic description;
    # this wrapper gives the correct dataset-specific interpretation.
    summary = {
        "status": "completed_prospective_synthetic_holdout",
        "synthetic_only": True,
        "not_clinical_validation": True,
        "not_independently_human_annotated": True,
        "genuine_handwriting_tested": False,
        "dataset_role": "unseen_synthetic_relative_to_frozen_parser",
        "frozen_baseline_commit": lock["frozen_baseline_commit"],
        "frozen_file_git_blobs": lock["frozen_file_git_blobs"],
        "frozen_case_definition_git_blob": lock["frozen_case_definition_git_blob"],
        "manifest_sha256": run["dataset"]["manifest_sha256"],
        "raw_result_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "model_digests": run["model_digests"],
        "out_of_process_model_resource_observations": resources.report(),
        "arms_run": run["arms_run"],
        "actual_results": run["summary"],
        "limitations": [
            "24 generated fictional printed/photographed-effect samples only",
            "No genuine handwriting; no clinical data or validation",
            "Results are from these exact unseen synthetic cases, not a production accuracy claim",
            "Original development report and model predictions remain unmodified",
            "Any later parser/scorer/prompt or gold edits invalidate the prospective designation",
        ],
    }
    out = destination / "holdout_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arms", default="tesseract")
    parser.add_argument("--integrity-only", action="store_true")
    args = parser.parse_args()
    try:
        validate_freeze(args.lock)
        validate_case_partition()
        if args.integrity_only:
            print("PROSPECTIVE_HOLDOUT_FREEZE_VALID: 24 cases; no inference")
            return 0
        result = evaluate(args.lock, args.output, parse_arms(args.arms))
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        print("PROSPECTIVE_HOLDOUT_NOT_COMPLETED: " + str(exc), file=sys.stderr)
        return 2
    print("PROSPECTIVE_HOLDOUT_COMPLETED: " + ",".join(result["arms_run"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
