"""Optional local entrypoint. Off unless OCR_C2_ENABLED=1."""
from __future__ import annotations

import os


def enabled() -> bool:
    return os.environ.get("OCR_C2_ENABLED") == "1"


def recognize(image_bytes: bytes, reviewed: dict | None = None) -> dict:
    """Return a disabled result by default and never replace reviewed fields."""
    if not enabled():
        return {
            "status": "disabled",
            "transcription": None,
            "reviewed": dict(reviewed or {}),
            "reason": "OCR_C2_DISABLED",
        }
    return {
        "status": "experimental",
        "transcription": None,
        "reviewed": dict(reviewed or {}),
        "reason": "no_frozen_finalist",
    }
