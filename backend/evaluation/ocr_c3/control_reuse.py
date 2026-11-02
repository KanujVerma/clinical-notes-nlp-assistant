"""Historical B8192 evidence is reusable only when the campaign-2 artifacts still match.

Campaign 2 stores ``model_digest`` inside ``identity`` and the prepared JPEG
hash on each page region. It does not write a top-level prepared-image hash.
A matching source hash is not evidence that the JPEG sent to GLM is the JPEG
Apple Vision will receive.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from evaluation.ocr_c2.identity import request_identity
from evaluation.ocr_c2.native import resolved_spec
from evaluation.ocr_c2.replay import replay_case
from evaluation.ocr_c2.runner import _crop_bytes
from evaluation.ocr_c2.segment import orient_page, segment_page
from evaluation.public_amr_benchmark import infer_image, sha

_MODEL_FIELDS = (
    "candidate", "parent", "model", "model_digest", "geometry",
    "num_ctx", "num_predict", "keep_alive", "prompt",
)
_CODE_FIELDS = (
    "identity_version", "campaign_id", "dataset", "case_ids_sha256",
    "protocol_sha256", "partition_sha256", "inference_sha256",
    "scoring_sha256", "control_sha256", "experiment_fingerprint",
)
_IDENTITY_FIELDS = _MODEL_FIELDS + _CODE_FIELDS


class BaselineRejected(ValueError):
    """The saved control cannot be compared with the Vision inputs."""


def _reject(reason: str) -> None:
    raise BaselineRejected(reason)


def _historical_crops(source: bytes) -> list[bytes]:
    """Prepared bytes campaign 2 would send for one B8192 page."""
    with Image.open(BytesIO(source)) as image:
        image.load()
        oriented = orient_page(image)
    geometry = resolved_spec("B8192").get("geometry") or "page"
    layout = segment_page(oriented, geometry)
    return [_crop_bytes(oriented, region) for region in layout["regions"]]


def _stored_identity(saved: dict) -> dict:
    stored = saved.get("identity")
    if not isinstance(stored, dict) or any(key not in stored for key in _IDENTITY_FIELDS):
        _reject("baseline_evidence_incomplete")
    return stored


def _pages_agree(saved: dict, pages: list[dict]) -> None:
    joined = "\n".join(page.get("prediction") or "" for page in pages)
    completed = all(page.get("completed") is True for page in pages)
    expected_status = "scored" if completed and joined.strip() else "incomplete"
    generation_limit = any(
        isinstance(region, dict) and region.get("status") == "generation_limit"
        for page in pages
        for region in page.get("regions") or []
    )
    if saved.get("status") != expected_status or saved.get("prediction") != joined:
        _reject("baseline_evidence_incomplete")
    if saved.get("page_seconds") != [page.get("page_seconds") for page in pages]:
        _reject("baseline_evidence_incomplete")
    if bool(saved.get("generation_limit")) != generation_limit:
        _reject("baseline_evidence_incomplete")


def accept_saved_control(
    saved: dict,
    pages: list[dict],
    reference_bytes: bytes,
    sources: list[bytes],
    model_digest: str,
    dataset: str,
    case_ids: list[str],
) -> None:
    """Raise ``BaselineRejected`` unless this case and its pages are a real B8192 control."""
    if not isinstance(saved, dict) or not isinstance(pages, list) or not isinstance(sources, list):
        _reject("baseline_evidence_incomplete")
    if not sources or len(pages) != len(sources) or any(not isinstance(page, dict) for page in pages):
        _reject("baseline_evidence_incomplete")
    expected = request_identity("B8192", dataset, case_ids, model_digest)
    if expected["candidate"] != "B8192" or expected["num_ctx"] != 8192:
        _reject("baseline_model_drift")
    stored = _stored_identity(saved)
    for key in _MODEL_FIELDS:
        if stored.get(key) != expected[key]:
            _reject("baseline_model_drift")
    for key in _CODE_FIELDS:
        if stored.get(key) != expected[key]:
            _reject("baseline_code_drift")
    reference_sha = sha(reference_bytes)
    if saved.get("reference_sha256") != reference_sha:
        _reject("baseline_reference_mismatch")
    for page, source in zip(pages, sources):
        if page.get("source_sha256") != sha(source):
            _reject("baseline_source_mismatch")
        if page.get("reference_sha256") != reference_sha:
            _reject("baseline_reference_mismatch")
        if page.get("experiment_fingerprint") != expected["experiment_fingerprint"]:
            _reject("baseline_code_drift")
        if page.get("scoring_sha256") != expected["scoring_sha256"]:
            _reject("baseline_code_drift")
        if page.get("status") not in {"scored", "incomplete"} or page.get("completed") is not (page.get("status") == "scored"):
            _reject("baseline_evidence_incomplete")
        regions = page.get("regions")
        crops = _historical_crops(source)
        vision = infer_image(source)
        if crops != [vision]:
            _reject("baseline_prepared_bytes_mismatch")
        if not isinstance(regions, list) or len(regions) != len(crops):
            _reject("baseline_evidence_incomplete")
        for index, (region, crop) in enumerate(zip(regions, crops)):
            if not isinstance(region, dict) or "crop_sha256" not in region or region.get("order") != index:
                _reject("baseline_evidence_incomplete")
            if region.get("crop_sha256") != sha(crop):
                _reject("baseline_prepared_bytes_mismatch")
    _pages_agree(saved, pages)
    if saved.get("status") == "scored":
        try:
            replay_case(saved, reference_bytes)
        except ValueError as error:
            raise BaselineRejected("baseline_reference_mismatch") from error
    elif saved.get("status") != "incomplete":
        _reject("baseline_evidence_incomplete")


def select_baseline(
    records: dict[str, tuple[dict, list[dict]]],
    references: dict[str, bytes],
    sources: dict[str, list[bytes]],
    model_digest: str,
    dataset: str,
    case_ids: list[str],
) -> dict:
    """Reuse the saved control, or select a fresh B8192 run without scoring the rejection."""
    expected_ids = list(case_ids)
    if (
        len(expected_ids) != len(set(expected_ids))
        or set(records) != set(expected_ids)
        or set(references) != set(expected_ids)
        or set(sources) != set(expected_ids)
    ):
        return {"decision": "fresh", "reason": "baseline_evidence_incomplete"}
    for case_id in expected_ids:
        case, pages = records[case_id]
        try:
            accept_saved_control(
                case, pages, references[case_id], sources[case_id],
                model_digest, dataset, expected_ids,
            )
        except BaselineRejected as error:
            return {"decision": "fresh", "reason": str(error), "case_id": case_id}
    return {"decision": "reuse"}
