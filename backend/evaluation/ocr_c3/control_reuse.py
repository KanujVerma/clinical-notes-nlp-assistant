"""Historical B8192 evidence is reusable only when every fingerprint still matches."""
from __future__ import annotations

from evaluation.ocr_c2.identity import control_hash, inference_hash, scoring_hash
from evaluation.ocr_c2.replay import replay_case
from evaluation.public_amr_benchmark import sha


def accept_saved_control(saved: dict, reference_bytes: bytes, prepared_sha256: str, model_digest: str) -> None:
    stored = saved.get("identity") if isinstance(saved.get("identity"), dict) else {}
    if stored.get("inference_sha256") != inference_hash():
        raise ValueError("OCR_C3_CONTROL_STALE")
    if stored.get("control_sha256") != control_hash():
        raise ValueError("OCR_C3_CONTROL_STALE")
    if stored.get("scoring_sha256") != scoring_hash():
        raise ValueError("OCR_C3_CONTROL_STALE")
    if saved.get("prepared_image_sha256") != prepared_sha256:
        raise ValueError("OCR_C3_CONTROL_STALE")
    if saved.get("model_digest") != model_digest:
        raise ValueError("OCR_C3_CONTROL_STALE")
    if sha(reference_bytes) != saved.get("reference_sha256"):
        raise ValueError("OCR_C3_CONTROL_STALE")
    if saved.get("status") == "scored":
        replay_case(saved, reference_bytes)
    elif saved.get("status") != "incomplete":
        raise ValueError("OCR_C3_CONTROL_STALE")
