"""Campaign-2 fingerprints. PR #10 identity files are not rewritten."""
from __future__ import annotations

import json

from evaluation.ocr_c2.protocol import IDENTITY_VERSION, MANIFEST_PATH, PARTITION_PATH, load_protocol
from evaluation.public_amr_benchmark import sha

BOUND = (
    "backend/evaluation/ocr_c2/native.py",
    "backend/evaluation/ocr_c2/segment.py",
    "backend/evaluation/ocr_c2/metrics.py",
    "backend/evaluation/ocr_c2/runner.py",
)


def code_hash() -> str:
    from evaluation.ocr_c2.protocol import ROOT
    parts = []
    for relative in BOUND:
        parts.append(relative + "\n" + sha((ROOT / relative).read_bytes()))
    return sha("\n".join(parts).encode())


def request_identity(candidate: str, dataset: str, case_ids: list[str], model_digest: str) -> dict:
    protocol = load_protocol()
    spec = protocol["candidates"][candidate]
    body = {
        "identity_version": IDENTITY_VERSION,
        "campaign_id": protocol["campaign_id"],
        "candidate": candidate,
        "dataset": dataset,
        "case_ids_sha256": sha("\n".join(case_ids).encode()),
        "protocol_sha256": sha(MANIFEST_PATH.read_bytes()),
        "partition_sha256": sha(PARTITION_PATH.read_bytes()),
        "model": protocol["model"]["tag"],
        "model_digest": model_digest,
        "num_ctx": spec.get("num_ctx"),
        "num_predict": spec.get("num_predict"),
        "keep_alive": spec.get("keep_alive"),
        "prompt": protocol["model"]["native_prompt"] if spec["role"] != "control" else spec["prompt"],
        "code_sha256": code_hash(),
    }
    body["experiment_fingerprint"] = sha(json.dumps(body, sort_keys=True).encode())
    return body
