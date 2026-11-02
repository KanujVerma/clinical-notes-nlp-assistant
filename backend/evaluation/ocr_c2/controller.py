"""Campaign state machine. Entering a state does not complete its measurement."""
from __future__ import annotations

import fcntl
import json
from pathlib import Path

STATES = (
    "preflight",
    "review_ready",
    "screening",
    "confirming",
    "optional_model",
    "selecting",
    "internal_validation",
    "final_freeze",
    "holdout",
    "replay",
    "report",
    "stopped",
)

_NEXT = {
    ("preflight", "preflight_ok"): "review_ready",
    ("review_ready", "review_passed"): "screening",
    ("review_ready", "review_blocked"): "stopped",
    ("screening", "screen_done"): "confirming",
    ("screening", "nonqualifying"): "optional_model",
    ("screening", "budget_blocked"): "stopped",
    ("screening", "integrity_blocked"): "stopped",
    ("confirming", "confirm_done"): "selecting",
    ("confirming", "needs_speed"): "selecting",
    ("confirming", "needs_optional"): "optional_model",
    ("confirming", "nonqualifying"): "stopped",
    ("confirming", "budget_blocked"): "stopped",
    ("optional_model", "prerequisites_met"): "optional_model",
    ("optional_model", "optional_done"): "selecting",
    ("optional_model", "optional_skipped"): "selecting",
    ("optional_model", "geometry_blocked"): "stopped",
    ("optional_model", "download_blocked"): "stopped",
    ("optional_model", "budget_blocked"): "stopped",
    ("optional_model", "review_blocked"): "stopped",
    ("optional_model", "integrity_blocked"): "stopped",
    ("selecting", "selected"): "internal_validation",
    ("selecting", "no_candidate"): "stopped",
    ("selecting", "latency_blocker"): "stopped",
    ("internal_validation", "validation_passed"): "final_freeze",
    ("internal_validation", "validation_failed"): "stopped",
    ("internal_validation", "budget_blocked"): "stopped",
    ("final_freeze", "freeze_ok"): "holdout",
    ("final_freeze", "review_blocked"): "stopped",
    ("holdout", "holdout_done"): "replay",
    ("holdout", "budget_blocked"): "stopped",
    ("replay", "replay_ok"): "report",
    ("replay", "integrity_blocked"): "stopped",
    ("report", "report_done"): "stopped",
}


class TransitionRejected(ValueError):
    pass


def assess_optional(findings: dict) -> str:
    """Return the event after native routes fail.

    ``prerequisites_met`` stays in ``optional_model``. It does not download
    weights or run a recognizer. A majority of the development pages must be
    split into more than one line region before that event is allowed.
    """
    if findings.get("integrity_blocked"):
        return "integrity_blocked"
    if findings.get("budget_exhausted"):
        return "budget_blocked"
    if not findings.get("native_routes_failed"):
        return "optional_skipped"
    pages = int(findings.get("page_count") or 0)
    full_page = int(findings.get("full_page_layouts") or 0)
    split = int(findings.get("split_line_pages") or 0)
    if pages == 0 or full_page * 2 >= pages or split * 2 < pages:
        return "geometry_blocked"
    if not findings.get("download_compatible"):
        return "download_blocked"
    if not findings.get("budget_sufficient"):
        return "budget_blocked"
    if not findings.get("review_and_ci_complete"):
        return "review_blocked"
    return "prerequisites_met"


def step(state: str, event: str) -> str:
    if state not in STATES:
        raise TransitionRejected("OCR_C2_STATE")
    nxt = _NEXT.get((state, event))
    if nxt is None:
        raise TransitionRejected("OCR_C2_TRANSITION")
    return nxt


def acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as blocked:
        handle.close()
        raise RuntimeError("already_running") from blocked
    return handle


def write_checkpoint(path: Path, payload: dict) -> None:
    required = {
        "campaign_id", "state", "config_fingerprint", "budget_seconds",
        "stop_reason", "process_started",
    }
    if not required <= set(payload):
        raise ValueError("OCR_C2_CHECKPOINT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)
