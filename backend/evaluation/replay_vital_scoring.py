"""Replay stored Qwen3-VL vital predictions under a post-hoc alias scorer.

Does NOT contact Ollama or change any original report. It verifies the frozen
source images, image hashes, case IDs and manifest first, then writes a new
immutable diagnostic artifact with an explicit "posthoc" evidence tier.

Usage:
  python backend/evaluation/replay_vital_scoring.py \
    --manifest data/vision_gold_30/manifest.json \
    --report artifacts/evaluation/paired_local_17f5737320b78e10.json \
    --output-dir artifacts/evaluation
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import os

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from evaluation.local_vision_eval import (  # noqa: E402
    VITAL_FIELDS, _score_counts, score_occurrences,
)
from evaluation.vision_benchmark import load_gold_manifest  # noqa: E402
from evaluation.vision_vital_aliases import (  # noqa: E402
    ALIAS_VERSION, normalized_vitals,
)


def _read_dict(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 10_000_000:
        raise ValueError("INVALID_BENCHMARK_REPORT")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_BENCHMARK_REPORT") from exc
    if not isinstance(result, dict):
        raise ValueError("INVALID_BENCHMARK_REPORT")
    return result


def _head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, check=True, text=True, capture_output=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def replay(manifest_file: Path, report_file: Path, output_dir: Path) -> Path:
    images, metadata = load_gold_manifest(manifest_file)
    gold = _read_dict(manifest_file)
    report_bytes = report_file.read_bytes()
    original = _read_dict(report_file)
    if (original.get("status") != "completed_local_actual_predictions"
            or original.get("synthetic_only") is not True
            or original.get("not_clinical_validation") is not True
            or "qwen3_vl" not in original.get("arms_run", [])
            or not isinstance(original.get("model_digests", {}).get("qwen3_vl"), str)
            or original.get("dataset", {}).get("manifest_sha256") != metadata["manifest_sha256"]):
        raise ValueError("EVALUATION_PROVENANCE_MISMATCH")

    recorded_cases = (original.get("cases") or {}).get("qwen3_vl")
    manifest_cases = gold.get("cases")
    if (not isinstance(recorded_cases, list)
            or not isinstance(manifest_cases, list)
            or len(recorded_cases) != len(images)
            or len(manifest_cases) != len(images)):
        raise ValueError("EVALUATION_CASE_SET_MISMATCH")
    source_lookup = {x["id"]: x["source_sha256"] for x in images}
    labels = {x["id"]: x.get("expected_vitals", []) for x in manifest_cases}
    if len(labels) != len(images):
        raise ValueError("EVALUATION_CASE_SET_MISMATCH")

    original_raw_predictions = []
    per_case = []
    seen = set()
    for record in recorded_cases:
        if not isinstance(record, dict):
            raise ValueError("INVALID_RECORDED_PREDICTION")
        case_id = record.get("case_id")
        if (not isinstance(case_id, str)
                or case_id not in source_lookup or case_id in seen
                or record.get("source_sha256") != source_lookup[case_id]):
            raise ValueError("EVALUATION_SOURCE_MISMATCH")
        seen.add(case_id)
        candidates = record.get("structured_candidates")
        if not isinstance(candidates, dict):
            raise ValueError("INVALID_RECORDED_PREDICTION")
        vitals = candidates.get("vitals")
        expected = labels[case_id]
        if not isinstance(vitals, list) or not isinstance(expected, list):
            raise ValueError("INVALID_RECORDED_PREDICTION")

        # Reuse the strict source-occurrence scorer. Only the *explicit*
        # vital identity aliases and redundant saturation percent sign
        # are normalized. Do not coerce BP numeric values, doses or units.
        scored = score_occurrences(
            normalized_vitals(expected),
            normalized_vitals(vitals),
            VITAL_FIELDS, "vital_type",
        )
        per_case.append({
            "case_id": case_id,
            "source_sha256": record["source_sha256"],
            "posthoc_vitals": scored,
        })
        original_raw_predictions.append({
            "case_id": case_id,
            "vitals": vitals,
        })

    if seen != set(source_lookup):
        raise ValueError("EVALUATION_CASE_SET_MISMATCH")

    tp = sum(x["posthoc_vitals"]["tp"] for x in per_case)
    fp = sum(x["posthoc_vitals"]["fp"] for x in per_case)
    fn = sum(x["posthoc_vitals"]["fn"] for x in per_case)
    original_score = original.get("summary", {}).get("qwen3_vl", {}).get("vitals")
    if not isinstance(original_score, dict):
        raise ValueError("EVALUATION_ORIGINAL_SCORE_MISSING")

    result = {
        "status": "completed_posthoc_reanalysis_from_saved_predictions",
        "evidence_tier": "exploratory_after_inspecting_model_outputs",
        "is_new_model_run": False,
        "synthetic_only": True,
        "not_clinical_validation": True,
        "normalization_version": ALIAS_VERSION,
        "reference_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "reference_model_git_sha": original.get("git_sha"),
        "reanalysis_git_sha": _head(),
        "model_digest": original["model_digests"]["qwen3_vl"],
        "dataset": metadata,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "original_exact_vitals": original_score,
        "posthoc_alias_normalized_vitals": {
            **_score_counts(tp, fp, fn),
            "support": sum(len(labels[c["case_id"]]) for c in per_case),
        },
        "cases": per_case,
        "limitations": [
            "Aliases were selected after inspecting the original predictions; result is exploratory",
            "No model was rerun or retrained in this replay",
            "Only vital identity and duplicate SpO2 percent symbol normalized; numeric values and units remain strict",
            "Handwriting remains unmeasured",
            "Source images are synthetic and generator-derived, not clinically validated",
            "Qwen3-VL output remains non-authoritative until independently reviewed",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    name = "posthoc_vitals_" + hashlib.sha256(raw).hexdigest()[:16] + ".json"
    target = output_dir / name
    if target.exists():
        raise FileExistsError("REPLAY_REPORT_ALREADY_EXISTS")
    with tempfile.NamedTemporaryFile(
        dir=output_dir, prefix=".posthoc_", suffix=".tmp", delete=False
    ) as file:
        file.write(raw)
        temp = Path(file.name)
    try:
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/evaluation")
    opts = parser.parse_args()
    try:
        result = replay(opts.manifest, opts.report, opts.output_dir)
    except (OSError, ValueError, FileExistsError) as exc:
        code = str(exc)
        if not code.replace("_", "").isupper():
            code = "POSTHOC_REANALYSIS_FAILED"
        print("POSTHOC_REANALYSIS_NOT_COMPLETED: " + code, file=sys.stderr)
        return 2
    print("POSTHOC_REANALYSIS_COMPLETED: " + str(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
