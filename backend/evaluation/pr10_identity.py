"""Fingerprint for one PR #10 run. Old files without it stay untouched."""
from __future__ import annotations

import json

from evaluation.public_amr_benchmark import sha

IDENTITY_VERSION = "pr10_run_identity_v2"
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
)


class LegacyCheckpoint(ValueError):
    """Saved cases predate the fingerprint. Do not overwrite them."""


class CheckpointRejected(ValueError):
    """Saved cases do not match this experiment. Do not overwrite them."""


def fingerprint(parts: dict) -> str:
    missing = [key for key in REQUIRED if key not in parts]
    if missing:
        raise ValueError("PR10_IDENTITY_INCOMPLETE " + ",".join(missing))
    body = {key: parts[key] for key in REQUIRED}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha(raw.encode("utf-8"))


def assess_reuse(cases_by_id: dict[str, dict], identifiers: list[str], experiment_fingerprint: str) -> str:
    """Say whether existing case files may be reused. Never rewrites them."""
    expected = list(identifiers)
    if len(expected) != len(set(expected)):
        return "duplicate_expected"
    extra = set(cases_by_id) - set(expected)
    if extra:
        return "extra"
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
