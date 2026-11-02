"""Historical B8192 evidence is reusable only when every fingerprint still matches."""
from __future__ import annotations

from evaluation.ocr_c2.identity import request_identity
from evaluation.ocr_c2.replay import replay_case
from evaluation.public_amr_benchmark import sha

_B8192_FIELDS = (
    "campaign_id", "candidate", "dataset", "case_ids_sha256",
    "protocol_sha256", "partition_sha256", "model", "model_digest",
    "num_ctx", "num_predict", "keep_alive", "prompt", "geometry",
    "inference_sha256", "scoring_sha256", "control_sha256",
    "experiment_fingerprint",
)


def accept_saved_control(
    saved: dict, reference_bytes: bytes, prepared_sha256: str, model_digest: str,
    dataset: str, case_ids: list[str],
) -> None:
    expected = request_identity("B8192", dataset, case_ids, model_digest)
    stored = saved.get("identity") if isinstance(saved.get("identity"), dict) else {}
    if expected["candidate"] != "B8192" or expected["num_ctx"] != 8192:
        raise ValueError("OCR_C3_CONTROL_STALE")
    for key in _B8192_FIELDS:
        if stored.get(key) != expected[key]:
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
