"""Validate a Vision result without trusting its assembled transcript."""
from __future__ import annotations

from evaluation.ocr_c3.assemble import assemble, reading_order_uncertain
from evaluation.ocr_c3.geometry import geometry_status, pixel_rectangle
from evaluation.ocr_c3.identity import runtime_matches
from evaluation.ocr_c3.protocol import CAMPAIGN_ID, CANDIDATE, READING_ORDER
from evaluation.public_amr_benchmark import sha


REQUIRED = (
    "schema_version", "campaign_id", "candidate", "request_id", "dataset", "case_id",
    "page_index", "source_sha256", "prepared_image_sha256", "prepared_width",
    "prepared_height", "vision_request_revision", "recognition_level",
    "recognition_languages", "uses_language_correction", "status", "observations",
    "assembled_transcription", "reading_order", "runtime_identity",
)


def validate_result(result: dict, prepared: bytes, revision: int) -> dict:
    if not isinstance(result, dict) or any(key not in result for key in REQUIRED):
        raise ValueError("OCR_C3_MALFORMED_RESULT")
    if result["schema_version"] != "ocr_c3_vision_result_v1":
        raise ValueError("OCR_C3_MALFORMED_RESULT")
    if result["campaign_id"] != CAMPAIGN_ID or result["candidate"] != CANDIDATE:
        raise ValueError("OCR_C3_MALFORMED_RESULT")
    if result["recognition_level"] != "accurate" or result["uses_language_correction"] is not False:
        raise ValueError("OCR_C3_CONFIG_DRIFT")
    if result["recognition_languages"] != ["en-US"] or result["reading_order"] != READING_ORDER:
        raise ValueError("OCR_C3_CONFIG_DRIFT")
    if result["vision_request_revision"] != revision:
        raise ValueError("OCR_C3_REVISION")
    if not isinstance(result.get("runtime_identity"), dict) or not runtime_matches(result["runtime_identity"]):
        raise ValueError("OCR_C3_RUNTIME")
    if sha(prepared) != result["prepared_image_sha256"]:
        raise ValueError("OCR_C3_PREPARED_HASH")
    width = int(result["prepared_width"])
    height = int(result["prepared_height"])
    observations = result["observations"]
    if not isinstance(observations, list):
        raise ValueError("OCR_C3_MALFORMED_RESULT")
    for observation in observations:
        normalized = observation.get("normalized_rectangle")
        if not isinstance(normalized, dict):
            raise ValueError("OCR_C3_GEOMETRY")
        expected = pixel_rectangle(normalized, width, height)
        actual = observation.get("pixel_rectangle")
        if not isinstance(actual, dict):
            raise ValueError("OCR_C3_GEOMETRY")
        for key, value in expected.items():
            if abs(float(actual[key]) - value) > 1e-6:
                raise ValueError("OCR_C3_GEOMETRY")
        if observation.get("geometry_status") != geometry_status(expected, width, height):
            raise ValueError("OCR_C3_GEOMETRY")
        candidates = observation.get("candidates") or []
        if len(candidates) > 3:
            raise ValueError("OCR_C3_CANDIDATES")
        if candidates and observation.get("top_candidate") != candidates[0].get("text"):
            raise ValueError("OCR_C3_TOP_CANDIDATE")
    transcript = assemble(observations, width, height)
    if result.get("assembled_transcription") != transcript:
        raise ValueError("OCR_C3_ASSEMBLY")
    uncertain = reading_order_uncertain(observations, width, height)
    if bool(result.get("reading_order_uncertain")) != uncertain:
        raise ValueError("OCR_C3_READING_ORDER")
    stripped = transcript.strip()
    expected_status = "completed" if stripped else "empty_transcription"
    if result["status"] != expected_status:
        raise ValueError("OCR_C3_STATUS")
    return {"transcription": transcript, "reading_order_uncertain": uncertain, "status": result["status"]}
