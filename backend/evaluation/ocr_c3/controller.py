"""Campaign-3 states. There is no transition into a holdout."""
from __future__ import annotations

import fcntl
import json
from pathlib import Path

STATES = (
    "preflight",
    "implementation",
    "review_ready",
    "screening",
    "confirming",
    "replay",
    "report",
    "stopped",
)

_NEXT = {
    ("preflight", "protocol_frozen"): "implementation",
    ("implementation", "tests_passed"): "review_ready",
    ("review_ready", "review_passed"): "screening",
    ("review_ready", "review_blocked"): "stopped",
    ("screening", "screen_passed"): "confirming",
    ("screening", "screen_negative"): "stopped",
    ("screening", "budget_blocked"): "stopped",
    ("screening", "integrity_blocked"): "stopped",
    ("screening", "runtime_blocked"): "stopped",
    ("confirming", "confirmation_negative"): "stopped",
    ("confirming", "confirmation_inconclusive"): "stopped",
    ("confirming", "development_candidate_ready"): "replay",
    ("confirming", "confirmation_budget_blocked"): "stopped",
    ("replay", "replay_verified"): "report",
    ("report", "reported"): "stopped",
}


def step(state: str, event: str) -> str:
    if event in {"holdout", "internal_validation"}:
        raise ValueError("OCR_C3_PROTECTED_STAGE")
    try:
        return _NEXT[(state, event)]
    except KeyError as error:
        raise ValueError("OCR_C3_TRANSITION") from error


def require_reviewed(checkpoint: dict, head: str) -> None:
    if checkpoint.get("state") != "screening":
        raise RuntimeError("review_blocked")
    if checkpoint.get("review_status") != "passed" or checkpoint.get("reviewed_head") != head:
        raise RuntimeError("review_blocked")


def acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError("OCR_C3_LOCK") from error
    return handle


def write_checkpoint(path: Path, payload: dict) -> None:
    required = {"campaign_id", "state", "reviewed_head", "review_status", "budget_seconds"}
    if not required <= set(payload):
        raise ValueError("OCR_C3_CHECKPOINT")
    if payload["state"] not in STATES:
        raise ValueError("OCR_C3_CHECKPOINT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
