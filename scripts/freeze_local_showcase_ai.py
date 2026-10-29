"""Freeze actual completed LOCAL synthetic vision predictions for PR #4.

This script never runs models or publishes to the web. It requires the owner
to separately inspect the raw local evaluation file before approving its
publication in the curated synthetic-only repository. If the file contains
only Tesseract results or mocked unit-test digests, it fails closed.

Example:
  python scripts/freeze_local_showcase_ai.py \
    --evaluation artifacts/evaluation/paired_local_<actual>.json \
    --approve-reviewed

Do NOT use the manually authored handwriting CER test or model mocks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.showcase_evidence import (  # noqa: E402
    BASELINE_FILE, RECORDED_FILE, ShowcaseEvidenceError,
    verified_tesseract_baseline, verified_recorded_ai,
)


def freeze(evaluation_file: Path, target: Path, *, reviewed: bool) -> Path:
    if not reviewed:
        raise ShowcaseEvidenceError("CURATOR_APPROVAL_REQUIRED")
    if not evaluation_file.is_file() or evaluation_file.stat().st_size > 400_000:
        raise ShowcaseEvidenceError("LOCAL_MODEL_EVALUATION_UNAVAILABLE")

    original = evaluation_file.read_bytes()
    try:
        report = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ShowcaseEvidenceError("LOCAL_MODEL_EVALUATION_INVALID") from exc
    baseline = verified_tesseract_baseline(BASELINE_FILE)
    expected_by_id = {x["case_id"]: x["source_sha256"] for x in baseline["cases"]}

    dataset = report.get("dataset", {})
    digests = report.get("model_digests", {})
    arms = report.get("arms_run", [])
    rows = report.get("cases", {})
    git_sha = report.get("git_sha")
    if (report.get("status") != "completed_local_actual_predictions"
            or report.get("synthetic_only") is not True
            or report.get("not_clinical_validation") is not True
            or dataset.get("annotation_status") != "synthetic_generator_ground_truth"
            or dataset.get("manifest_sha256") != baseline["manifest_sha256"]
            or not isinstance(git_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", git_sha)
            or not isinstance(digests, dict) or not isinstance(rows, dict)
            or not isinstance(arms, list)):
        raise ShowcaseEvidenceError("LOCAL_MODEL_EVALUATION_INVALID")

    freeze_runs = []
    for adapter in ("glm_ocr", "qwen3_vl"):
        if adapter not in arms:
            continue
        digest = digests.get(adapter)
        cases = rows.get(adapter)
        if (not isinstance(digest, str)
                or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest)
                or not isinstance(cases, list)
                or len(cases) != len(expected_by_id)):
            raise ShowcaseEvidenceError("MODEL_DIGEST_OR_CASES_INVALID")
        recorded = []
        seen = set()
        for item in cases:
            case_id = item.get("case_id") if isinstance(item, dict) else None
            if (not isinstance(case_id, str) or case_id not in expected_by_id
                    or case_id in seen
                    or item.get("source_sha256") != expected_by_id[case_id]):
                raise ShowcaseEvidenceError("LOCAL_MODEL_SOURCE_MISMATCH")
            seen.add(case_id)
            result = {
                "case_id": case_id,
                "source_sha256": item["source_sha256"],
            }
            if adapter == "glm_ocr":
                transcript = item.get("transcription")
                if not isinstance(transcript, str) or not transcript.strip():
                    raise ShowcaseEvidenceError("INVALID_LOCAL_TRANSCRIPTION")
                result["transcription"] = transcript
            else:
                candidates = item.get("structured_candidates")
                if not isinstance(candidates, dict):
                    raise ShowcaseEvidenceError("INVALID_LOCAL_CANDIDATES")
                result["structured_candidates"] = candidates
            recorded.append(result)
        if seen != set(expected_by_id):
            raise ShowcaseEvidenceError("LOCAL_MODEL_SOURCE_MISMATCH")
        freeze_runs.append({
            "adapter": adapter, "model_digest": digest, "cases": recorded,
        })

    if not freeze_runs:
        raise ShowcaseEvidenceError("NO_REAL_LOCAL_AI_MODEL_ARMS")

    fixture = {
        "schema_version": "1",
        "synthetic_only": True,
        "independently_reviewed": True,
        "review_scope": "synthetic_examples_only_not_clinically_adjudicated",
        "source_manifest_sha256": baseline["manifest_sha256"],
        "local_evaluation_git_sha": git_sha,
        "source_report_sha256": hashlib.sha256(original).hexdigest(),
        "model_runs": freeze_runs,
    }

    # Validate its exact serialization via the same code serving public
    # responses. A missing/forged source binding cannot be promoted.
    target.parent.mkdir(parents=True, exist_ok=True)
    draft = target.with_name(target.name + ".pending")
    draft.write_text(json.dumps(fixture, indent=2, sort_keys=True), encoding="utf-8")
    try:
        verified_recorded_ai(baseline, draft)
        if target.exists():
            raise ShowcaseEvidenceError("RECORDED_AI_ALREADY_EXISTS")
        draft.replace(target)
    finally:
        draft.unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=RECORDED_FILE)
    parser.add_argument("--approve-reviewed", action="store_true")
    args = parser.parse_args()
    try:
        result = freeze(args.evaluation, args.output, reviewed=args.approve_reviewed)
    except (OSError, ValueError, ShowcaseEvidenceError) as exc:
        code = exc.code if isinstance(exc, ShowcaseEvidenceError) else "RECORDING_NOT_PUBLISHED"
        print("SHOWCASE_RECORDING_REJECTED: " + code, file=sys.stderr)
        return 2
    print("LOCAL_SYNTHETIC_RECORDING_FROZEN: " + str(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
