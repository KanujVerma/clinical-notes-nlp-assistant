"""Run a REAL local GLM-OCR benchmark against hash-pinned synthetic images.

This command does not create test images, fake transcriptions, use paid APIs or
infer gold labels. A real labeled synthetic-image manifest is required.
Do not cite output from calculate_cer_wer unit tests as model measurements.

Usage:
  python backend/evaluation/vision_benchmark.py \
    --manifest data/vision_gold/manifest.json

Manifest example (replace hashes/images/references with real synthetic data):
{
  "dataset_id": "synthetic_visual_ocr_v1",
  "synthetic_only": true,
  "annotation_status": "synthetic_generator_ground_truth",
  "cases": [
    {
      "id": "case001",
      "image": "images/case001.png",
      "sha256": "<64-hex SHA-256 of original image bytes>",
      "reference_text": "Warfarin 2.5 mg PO daily",
      "critical_tokens": ["2.5 mg"]
    }
  ]
}

An independently human-transcribed reference may instead use the explicit
annotation_status value "independent_human_transcription" only when true.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image  # noqa: E402
from services.multimodal_service import (  # noqa: E402
    DEFAULT_OCR_MODEL, OLLAMA_BASE_URL,
    _ensure_local_ollama_endpoint, glm_ocr_infer, calculate_cer_wer,
)

DATASET_ANNOTATION_STATUSES = {
    "synthetic_generator_ground_truth",
    "independent_human_transcription",
    "developer_transcribed_development",
}
MAX_CASES = 100
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000


def load_gold_manifest(path: Path) -> tuple[list[dict], dict]:
    """Validate each synthetic image, case reference, and SHA-256 before inference."""
    path = path.resolve()
    payload_bytes = path.read_bytes()
    manifest = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("synthetic_only") is not True:
        raise ValueError("Benchmark requires an explicit synthetic_only=true manifest")
    status = manifest.get("annotation_status")
    if status not in DATASET_ANNOTATION_STATUSES:
        raise ValueError("Explicit honest annotation_status is required")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("Benchmark must contain 1-100 labeled image cases")

    validated = []
    seen = set()
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("Invalid benchmark case")
        case_id = item["id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", case_id) or case_id in seen:
            raise ValueError("Invalid or duplicate case identifier")
        seen.add(case_id)

        image_rel = item.get("image")
        sha = item.get("sha256")
        reference = item.get("reference_text")
        critical = item.get("critical_tokens", [])
        if (not isinstance(image_rel, str) or not image_rel
                or not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", sha)
                or not isinstance(reference, str) or not reference.strip()
                or not isinstance(critical, list)
                or any(not isinstance(t, str) or not t.strip() for t in critical)):
            raise ValueError(f"Incomplete labeled case: {case_id}")

        image_path = (path.parent / image_rel).resolve()
        if (not image_path.is_relative_to(path.parent)
                or image_path.suffix.lower() not in (".png", ".jpg", ".jpeg")
                or not image_path.is_file()):
            raise ValueError(f"Invalid image path for {case_id}")
        if image_path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError(f"Oversized source image for {case_id}")

        image_bytes = image_path.read_bytes()
        if hashlib.sha256(image_bytes).hexdigest().lower() != sha.lower():
            raise ValueError(f"Image SHA-256 mismatch for {case_id}")
        with Image.open(image_path) as img:
            if img.width * img.height > MAX_PIXELS:
                raise ValueError(f"Excessive image pixels for {case_id}")
            img.verify()
        validated.append({
            "id": case_id, "image_bytes": image_bytes,
            "source_sha256": sha.lower(),
            "reference_text": reference,
            "critical_tokens": critical,
        })

    return validated, {
        "dataset_id": manifest.get("dataset_id") or "unlabeled_synthetic_visual",
        "annotation_status": status,
        "manifest_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "case_count": len(cases),
    }


def installed_model_digest() -> str:
    """Fetch the actual installed Ollama model digest, never infer it from a tag."""
    _ensure_local_ollama_endpoint()
    request = Request(f"{OLLAMA_BASE_URL}/api/tags", headers={"User-Agent": "ClinicalNLP-Eval/1.0"})
    with urlopen(request, timeout=5) as response:
        data = response.read(256 * 1024 + 1)
    if len(data) > 256 * 1024:
        raise RuntimeError("Model list exceeds metadata limit")
    registry = json.loads(data.decode("utf-8"))
    for model in registry.get("models", []):
        if model.get("name") == DEFAULT_OCR_MODEL and isinstance(model.get("digest"), str):
            digest = model["digest"]
            if digest:
                return digest
    raise RuntimeError(f"Required local OCR model not installed: {DEFAULT_OCR_MODEL}")


def run_benchmark(manifest_path: Path, output_root: Path) -> Path:
    cases, metadata = load_gold_manifest(manifest_path)
    digest = installed_model_digest()  # Offline/missing model fails before any metrics.
    predictions = []
    distance_chars = 0
    distance_words = 0
    ref_chars = 0
    ref_words = 0
    critical_failures = 0

    for case in cases:
        output = glm_ocr_infer(case["image_bytes"], model=DEFAULT_OCR_MODEL)
        if output.get("status") != "completed":
            raise RuntimeError(
                f"Real local OCR inference did not complete: {case['id']}: "
                f"{output.get('error_code', 'UNKNOWN')}"
            )
        actual = output.get("transcribed_text")
        if not isinstance(actual, str) or not actual.strip():
            raise RuntimeError(f"Model returned empty transcription: {case['id']}")

        metrics = calculate_cer_wer(case["reference_text"], actual)
        distance_chars += metrics["char_distance"]
        distance_words += metrics["word_distance"]
        ref_chars += metrics["ref_chars"]
        ref_words += metrics["ref_words"]
        # Exact bounded token checks flag critical substitutions. The reference
        # text must independently support all user-authored critical tokens.
        token_checks = []
        for token in case["critical_tokens"]:
            if token not in case["reference_text"]:
                raise ValueError(f"Critical token absent from gold reference: {case['id']}")
            lead_bound = r"(?<![0-9.])" if (token and (token[0].isdigit() or token[0] == ".")) else r"(?<!\w)"
            trail_bound = r"(?![0-9.])" if (token and (token[-1].isdigit() or token[-1] == ".")) else r"(?!\w)"
            present = re.search(
                lead_bound + re.escape(token).replace(r"\ ", r"\s+") + trail_bound,
                actual,
            ) is not None
            critical_failures += int(not present)
            token_checks.append({"token": token, "recognized": present})

        predictions.append({
            "case_id": case["id"],
            "source_sha256": case["source_sha256"],
            "reference_text": case["reference_text"],
            "model_transcription": actual,
            "cer": metrics["cer"], "wer": metrics["wer"],
            "character_distance": metrics["char_distance"],
            "word_distance": metrics["word_distance"],
            "critical_tokens": token_checks,
        })

    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_sha = "unknown"

    report = {
        "status": "completed_live_local_model",
        "synthetic_only": True,
        "dataset": metadata,
        "model": DEFAULT_OCR_MODEL,
        "model_digest": digest,
        "git_sha": git_sha,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(cases),
        "character_error_rate_micro": distance_chars / max(1, ref_chars),
        "word_error_rate_micro": distance_words / max(1, ref_words),
        "critical_token_failures": critical_failures,
        "cases": predictions,
        "limitations": [
            "Synthetic data; not clinical validation",
            "OCR agreement does not prove original pixels are read correctly",
            "No calibration of model-reported confidence",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        json.dumps(report, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    output = output_root / f"vision_{fingerprint}.json"
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "artifacts" / "evaluation",
    )
    args = parser.parse_args()
    try:
        report = run_benchmark(args.manifest, args.output_dir)
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"LIVE_BENCHMARK_NOT_COMPLETED: {exc}", file=sys.stderr)
        return 2
    print(f"LIVE_BENCHMARK_COMPLETED: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
