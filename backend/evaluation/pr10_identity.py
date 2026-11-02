"""Fingerprint for one PR #10 run. Old files without it stay untouched."""
from __future__ import annotations

import json
from pathlib import Path

from evaluation.public_amr_benchmark import sha

IDENTITY_VERSION = "pr10_run_identity_v4"
ROOT = Path(__file__).resolve().parents[2]
DECODING = {
    "temperature": 0,
    "num_predict": 2048,
    "timeout_s": 90,
    "keep_alive": 0,
}
INFERENCE_FILES = (
    "backend/evaluation/pr10_autoresearch.py",
    "backend/services/multimodal_service.py",
)
TRANSFORM_FILES = (
    "backend/evaluation/pr10_candidate.py",
    "backend/evaluation/public_amr_benchmark.py",
)
SCORING_FILES = (
    "backend/evaluation/pr10_replay.py",
    "backend/evaluation/public_amr_benchmark.py",
)
IDENTITY_FILES = ("backend/evaluation/pr10_identity.py",)
BOUND_FILES = INFERENCE_FILES + TRANSFORM_FILES + SCORING_FILES + IDENTITY_FILES
INFERENCE_FIELDS = (
    "model", "model_digest", "num_ctx", "prompt_sha256", "spec_sha256",
    "temperature", "num_predict", "timeout_s", "keep_alive",
    "inference_sha256", "transform_sha256",
)
SCORING_FIELDS = ("scoring_sha256",)
REQUIRED = (
    "identity_version",
    "manifest_sha256",
    "dataset",
    "stage",
    "selection_policy",
    "case_ids_sha256",
    "candidate",
    "parent",
    "model",
    "model_digest",
    "num_ctx",
    "prompt_sha256",
    "spec_sha256",
    "temperature",
    "num_predict",
    "timeout_s",
    "keep_alive",
    "inference_sha256",
    "transform_sha256",
    "scoring_sha256",
    "identity_sha256",
    "inference_fingerprint",
    "scoring_fingerprint",
    "reference_sha256",
)
DECODING_LITERALS = (
    '"temperature": 0',
    '"num_predict": 2048',
    '"keep_alive": 0',
    "timeout: float = 90.0",
)


class LegacyCheckpoint(ValueError):
    """Saved cases predate the fingerprint. Do not overwrite them."""


class CheckpointRejected(ValueError):
    """Saved cases do not match this experiment. Do not overwrite them."""


def canonical(body: dict) -> bytes:
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return raw.encode("utf-8")


def fingerprint(parts: dict) -> str:
    missing = [key for key in REQUIRED if key not in parts]
    if missing:
        raise ValueError("PR10_IDENTITY_INCOMPLETE " + ",".join(missing))
    body = {key: parts[key] for key in REQUIRED}
    return sha(canonical(body))


def inference_fingerprint(parts: dict) -> str:
    return sha(canonical({key: parts[key] for key in INFERENCE_FIELDS}))


def scoring_fingerprint(parts: dict) -> str:
    return sha(canonical({key: parts[key] for key in SCORING_FIELDS}))


def _bundle(paths: tuple[str, ...], overrides: dict[str, bytes] | None) -> str:
    payload = b""
    for relative in paths:
        if overrides and relative in overrides:
            body = overrides[relative]
        else:
            body = (ROOT / relative).read_bytes()
        if relative == "backend/services/multimodal_service.py":
            text = body.decode("utf-8", errors="replace")
            if any(literal not in text for literal in DECODING_LITERALS):
                raise ValueError("PR10_DECODING_DRIFT")
        payload += relative.encode("utf-8") + b"\0" + body
    return sha(payload)


def implementation_hashes(overrides: dict[str, bytes] | None = None) -> dict[str, str]:
    """Hash the source bytes that can change inputs, outputs, or scores."""
    return {
        "inference_sha256": _bundle(INFERENCE_FILES, overrides),
        "transform_sha256": _bundle(TRANSFORM_FILES, overrides),
        "scoring_sha256": _bundle(SCORING_FILES, overrides),
        "identity_sha256": _bundle(IDENTITY_FILES, overrides),
    }


def assess_reuse(cases_by_id: dict[str, dict], identifiers: list[str], experiment_fingerprint: str) -> str:
    """Say whether existing case files may be reused. Never rewrites them."""
    expected = list(identifiers)
    if len(expected) != len(set(expected)):
        return "duplicate_case"
    extra = set(cases_by_id) - set(expected)
    if extra:
        return "extra_case"
    present = [cases_by_id[item] for item in expected if item in cases_by_id]
    if any(case.get("identity_version") != IDENTITY_VERSION for case in present):
        return "legacy_unverified"
    if any(case.get("experiment_fingerprint") != experiment_fingerprint for case in present):
        return "fingerprint_mismatch"
    if any(
        case.get("status") == "scored" and not str(case.get("prediction") or "").strip()
        for case in present
    ):
        return "invalid"
    if len(present) < len(expected):
        return "incomplete"
    return "reusable"


def mismatch_code(case: dict, expected: dict) -> str | None:
    """Machine-readable provenance failure. None means this case matches."""
    if case.get("identity_version") != IDENTITY_VERSION:
        return "legacy_unverified"
    if case.get("model") != expected["model"]:
        return "model_mismatch"
    if case.get("model_digest") != expected["model_digest"]:
        return "model_digest_mismatch"
    if case.get("prompt_sha256") != expected["prompt_sha256"]:
        return "prompt_mismatch"
    if case.get("inference_fingerprint") != expected["inference_fingerprint"]:
        return "implementation_mismatch"
    if case.get("scoring_fingerprint") != expected["scoring_fingerprint"]:
        return "scoring_drift"
    for key in ("inference_sha256", "transform_sha256", "scoring_sha256", "identity_sha256"):
        if case.get(key) != expected[key]:
            return "implementation_mismatch"
    if case.get("experiment_fingerprint") != expected["experiment_fingerprint"]:
        return "fingerprint_mismatch"
    if case.get("status") == "scored" and not str(case.get("prediction") or "").strip():
        return "invalid"
    if case.get("candidate") != expected["candidate"]:
        return "fingerprint_mismatch"
    return None
