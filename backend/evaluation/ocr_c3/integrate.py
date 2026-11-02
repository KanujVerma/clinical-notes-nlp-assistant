"""Optional local entrypoint. Off unless OCR_C3_ENABLED=1."""
from __future__ import annotations

import os


def enabled() -> bool:
    return os.environ.get("OCR_C3_ENABLED") == "1"


def recognize(image_bytes: bytes, reviewed: dict | None = None) -> dict:
    """Disabled by default. A confidence value never bypasses review."""
    del image_bytes
    if not enabled():
        return {
            "status": "disabled",
            "transcription": None,
            "reviewed": dict(reviewed or {}),
            "reason": "OCR_C3_DISABLED",
        }
    return {
        "status": "experimental",
        "transcription": None,
        "reviewed": dict(reviewed or {}),
        "reason": "no_development_candidate",
    }
