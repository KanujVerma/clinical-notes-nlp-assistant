"""Recompute a saved Vision case from its observations and reference bytes."""
from __future__ import annotations

from evaluation.ocr_c2.metrics import normalize_recognition, normalized_errors, occurrence_case, strict_case
from evaluation.ocr_c3.schema import validate_result
from evaluation.pr10_replay import reference_text
from evaluation.public_amr_benchmark import sha


def document_complete(pages: list[dict]) -> bool:
    if not pages:
        return False
    return all(
        page.get("status") == "completed" and str(page.get("assembled_transcription") or "").strip()
        for page in pages
    )


def replay_case(case: dict, reference_bytes: bytes, prepared_pages: list[bytes]) -> dict:
    if sha(bytes(reference_bytes)) != case.get("reference_sha256"):
        raise ValueError("OCR_C3_REPLAY")
    if case.get("status") != "scored":
        return {"classification": "not_scored", "case": case}
    pages = case.get("pages")
    if not isinstance(pages, list) or len(pages) != len(prepared_pages):
        raise ValueError("OCR_C3_REPLAY")
    transcripts = []
    for page, prepared in zip(pages, prepared_pages):
        checked = validate_result(page, prepared, page["vision_request_revision"])
        if checked["transcription"] != page.get("assembled_transcription"):
            raise ValueError("OCR_C3_REPLAY")
        transcripts.append(checked["transcription"])
    prediction = "\n".join(transcripts)
    if prediction != case.get("prediction"):
        raise ValueError("OCR_C3_REPLAY")
    reference = reference_text(reference_bytes)
    if strict_case(reference, prediction) != case.get("metrics"):
        raise ValueError("OCR_C3_REPLAY")
    aligned = occurrence_case(reference, prediction)
    for key in ("occurrence_hits", "occurrence_total", "occurrence_false_positives"):
        if case.get(key) != aligned[key]:
            raise ValueError("OCR_C3_REPLAY")
    if case.get("normalized") != normalized_errors(reference, prediction):
        raise ValueError("OCR_C3_REPLAY")
    if case.get("normalized_prediction") != normalize_recognition(prediction):
        raise ValueError("OCR_C3_REPLAY")
    return {"classification": "verified", "case": case}
