"""Campaign-2 fingerprints. Inference and scoring identities are separate."""
from __future__ import annotations

import json

from evaluation.ocr_c2.protocol import IDENTITY_VERSION, MANIFEST_PATH, PARTITION_PATH, ROOT, load_protocol
from evaluation.public_amr_benchmark import sha

INFERENCE_FILES = (
    "backend/evaluation/ocr_c2/native.py",
    "backend/evaluation/ocr_c2/segment.py",
    "backend/evaluation/ocr_c2/runner.py",
    "backend/evaluation/public_amr_benchmark.py",
)
SCORING_FILES = (
    "backend/evaluation/ocr_c2/metrics.py",
    "backend/evaluation/pr10_replay.py",
    "backend/evaluation/public_amr_benchmark.py",
    "backend/services/multimodal_service.py",
)


def _bundle(files: tuple[str, ...]) -> str:
    parts = []
    for relative in files:
        parts.append(relative + "\n" + sha((ROOT / relative).read_bytes()))
    return sha("\n".join(parts).encode())


def inference_hash() -> str:
    return _bundle(INFERENCE_FILES)


def scoring_hash() -> str:
    return _bundle(SCORING_FILES)


def request_identity(
    candidate: str, dataset: str, case_ids: list[str], model_digest: str, parent: str | None = None,
) -> dict:
    from evaluation.ocr_c2.native import resolved_spec
    protocol = load_protocol()
    spec = resolved_spec(candidate, parent)
    body = {
        "identity_version": IDENTITY_VERSION,
        "campaign_id": protocol["campaign_id"],
        "candidate": candidate,
        "parent": spec.get("parent"),
        "dataset": dataset,
        "case_ids_sha256": sha("\n".join(case_ids).encode()),
        "protocol_sha256": sha(MANIFEST_PATH.read_bytes()),
        "partition_sha256": sha(PARTITION_PATH.read_bytes()),
        "model": protocol["model"]["tag"],
        "model_digest": model_digest,
        "geometry": spec.get("geometry"),
        "num_ctx": spec.get("num_ctx"),
        "num_predict": spec.get("num_predict"),
        "keep_alive": spec.get("keep_alive"),
        "prompt": protocol["model"]["native_prompt"] if spec["role"] != "control" else spec["prompt"],
        "inference_sha256": inference_hash(),
        "scoring_sha256": scoring_hash(),
    }
    body["experiment_fingerprint"] = sha(json.dumps(body, sort_keys=True).encode())
    return body
