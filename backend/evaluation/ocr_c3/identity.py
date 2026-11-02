"""Campaign-3 fingerprints. Scoring stays the existing campaign-2 scorer."""
from __future__ import annotations

import json

from evaluation.ocr_c2.identity import symbol_source
from evaluation.ocr_c3.protocol import MANIFEST_PATH, ROOT, load_protocol
from evaluation.public_amr_benchmark import sha

INFERENCE_FILES = (
    "backend/evaluation/ocr_c3_swift/main.swift",
    "backend/evaluation/ocr_c3/assemble.py",
    "backend/evaluation/ocr_c3/geometry.py",
    "backend/evaluation/ocr_c3/runner.py",
    "backend/evaluation/ocr_c3/budget.py",
)
INFERENCE_SYMBOLS = (
    ("backend/evaluation/public_amr_benchmark.py", ("MAX_INPUT_BYTES", "check", "infer_image")),
)
SCORING_SYMBOLS = (
    ("backend/evaluation/ocr_c2/metrics.py", (
        "normalize_recognition", "normalized_errors", "strict_case", "occurrence_case",
        "micro_rate", "nearest_rank_p95", "meets_relative_reduction", "whitespace_only",
        "preserves_successes", "safety_ok", "bootstrap_relative",
    )),
    ("backend/evaluation/pr10_replay.py", ("critical_occurrences", "align_critical", "reference_text")),
    ("backend/evaluation/public_amr_benchmark.py", ("CRITICAL", "score")),
    ("backend/evaluation/local_vision_eval.py", ("exact_critical_tokens", "_score_text")),
    ("backend/services/multimodal_service.py", ("_levenshtein_distance", "calculate_cer_wer")),
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def _bundle(parts: list[str]) -> str:
    return sha("\n".join(parts).encode())


def inference_hash() -> str:
    parts = [relative + "\n" + sha(_read(relative).encode()) for relative in INFERENCE_FILES]
    for relative, names in INFERENCE_SYMBOLS:
        parts.append(relative + ":" + ",".join(names) + "\n" + symbol_source(_read(relative), names))
    return _bundle(parts)


def scoring_hash() -> str:
    parts = []
    for relative, names in SCORING_SYMBOLS:
        parts.append(relative + ":" + ",".join(names) + "\n" + symbol_source(_read(relative), names))
    return _bundle(parts)


def swift_source_sha256() -> str:
    return sha((ROOT / "backend/evaluation/ocr_c3_swift/main.swift").read_bytes())


def request_identity(dataset: str, ids: list[str], revision: int) -> dict:
    protocol = load_protocol()
    manifest = MANIFEST_PATH.read_bytes()
    return {
        "campaign_id": protocol["campaign_id"],
        "candidate": protocol["candidate"]["id"],
        "dataset": dataset,
        "ids": list(ids),
        "vision_revision": revision,
        "protocol_sha256": sha(manifest),
        "partition_sha256": sha((ROOT / protocol["partition_manifest"]).read_bytes()),
        "inference_sha256": inference_hash(),
        "scoring_sha256": scoring_hash(),
        "swift_source_sha256": swift_source_sha256(),
        "reading_order": protocol["reading_order"],
        "uses_language_correction": False,
    }


def runtime_matches(observed: dict, protocol: dict | None = None) -> bool:
    protocol = protocol or load_protocol()
    runtime = protocol["runtime"]
    if observed.get("os_build") != runtime["os_build"]:
        return False
    if observed.get("arch") != runtime["arch"]:
        return False
    if observed.get("vision_revision") != runtime["vision_revision"]:
        return False
    if observed.get("model_weight_digest") not in (None,):
        return False
    return True


def dumps(identity: dict) -> str:
    return json.dumps(identity, sort_keys=True)
