"""Source-bound local inference processing; called only from the durable worker.

No Flask request, arbitrary provider URL, paid API, or review-state mutation.
All image data is derived from an immutable, checksum-verified source asset.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import time
from typing import Any
from urllib.request import Request, urlopen

import fitz
from PIL import Image
from sqlalchemy.orm import Session

from models import Extraction, Job, Note, NoteRevision, SourceAsset
from services import multimodal_service as vision
from services import ollama_service as text_model

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_TEXT_BYTES = 2 * 1024 * 1024
SUPPORTED_ADAPTERS = ("text", "glm_ocr", "qwen3_vl")
PROMPT_VERSIONS = {
    "text": "semantic_candidates_v1",
    "glm_ocr": "glm_ocr_visual_v1",
    "qwen3_vl": "qwen3_vl_visual_v1",
}


class InferenceBindingError(Exception):
    """A safe, stable error code, without source text or machine paths."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def model_for(adapter: str) -> str:
    if adapter == "glm_ocr":
        return vision.DEFAULT_OCR_MODEL
    if adapter in ("text", "qwen3_vl"):
        return vision.DEFAULT_VL_MODEL
    raise InferenceBindingError("INVALID_ADAPTER")


def check_binding(
    session: Session, workspace_id: str, note_id: int,
    source_revision_id: str, extraction_id: str, source_hash: str,
    adapter: str, page_number: int,
) -> tuple[NoteRevision, Extraction, SourceAsset | None]:
    """Reject all stale, cross-workspace and unverifiable inference sources."""
    if adapter not in SUPPORTED_ADAPTERS or type(page_number) is not int:
        raise InferenceBindingError("INVALID_ADAPTER")
    if not (1 <= page_number <= 20):
        raise InferenceBindingError("INVALID_IMAGE_PAGE")

    note = session.query(Note).filter(
        Note.id == note_id, Note.workspace_id == workspace_id,
    ).first()
    if not note:
        raise InferenceBindingError("NOTE_NOT_FOUND")
    if (note.current_source_revision_id != source_revision_id or
            note.current_extraction_id != extraction_id):
        raise InferenceBindingError("AI_STALE_SOURCE")

    revision = session.query(NoteRevision).filter(
        NoteRevision.id == source_revision_id,
        NoteRevision.note_id == note_id,
        NoteRevision.workspace_id == workspace_id,
    ).first()
    if not revision or revision.sha256 != source_hash:
        raise InferenceBindingError("AI_STALE_SOURCE")
    if sha256_bytes(revision.raw_text.encode("utf-8")) != revision.sha256:
        raise InferenceBindingError("SOURCE_INTEGRITY_FAILURE")
    if len(revision.raw_text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise InferenceBindingError("SOURCE_TOO_LARGE")

    extraction = session.query(Extraction).filter(
        Extraction.public_id == extraction_id,
        Extraction.note_id == note_id,
        Extraction.workspace_id == workspace_id,
        Extraction.source_revision_id == source_revision_id,
        Extraction.source_text_hash == source_hash,
        Extraction.status == "completed",
    ).first()
    if not extraction:
        raise InferenceBindingError("EXTRACTION_BINDING_REQUIRED")

    asset = None
    if adapter != "text":
        if not revision.source_asset_id:
            raise InferenceBindingError("IMAGE_SOURCE_REQUIRED")
        asset = session.query(SourceAsset).filter(
            SourceAsset.id == revision.source_asset_id,
            SourceAsset.workspace_id == workspace_id,
        ).first()
        if not asset or asset.mime_type not in (
            "application/pdf", "image/png", "image/jpeg", "image/tiff",
        ):
            raise InferenceBindingError("IMAGE_SOURCE_REQUIRED")
        if page_number > (asset.page_count or 1):
            raise InferenceBindingError("INVALID_IMAGE_PAGE")
    return revision, extraction, asset


def _read_verified_image(asset: SourceAsset, page_number: int) -> bytes:
    path = Path(asset.storage_key)
    try:
        if not path.is_file():
            raise InferenceBindingError("SOURCE_ASSET_UNAVAILABLE")
        if path.stat().st_size != asset.byte_size:
            raise InferenceBindingError("SOURCE_ASSET_INTEGRITY_FAILURE")
        if asset.byte_size <= 0 or asset.byte_size > MAX_SOURCE_BYTES:
            raise InferenceBindingError("SOURCE_ASSET_TOO_LARGE")
        original = path.read_bytes()
    except OSError as exc:
        raise InferenceBindingError("SOURCE_ASSET_UNAVAILABLE") from exc
    if sha256_bytes(original) != asset.sha256:
        raise InferenceBindingError("SOURCE_ASSET_INTEGRITY_FAILURE")

    if asset.mime_type == "application/pdf":
        try:
            with fitz.open(stream=original, filetype="pdf") as doc:
                if (doc.needs_pass or len(doc) > 20 or
                        not 1 <= page_number <= len(doc)):
                    raise InferenceBindingError("INVALID_IMAGE_PAGE")
                page = doc[page_number - 1]
                scale = 150.0 / 72.0
                if page.rect.width * page.rect.height * scale * scale > MAX_IMAGE_PIXELS:
                    raise InferenceBindingError("IMAGE_TOO_LARGE")
                encoded = page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
        except InferenceBindingError:
            raise
        except Exception as exc:
            raise InferenceBindingError("INVALID_SOURCE_PDF") from exc
    else:
        if page_number != 1:
            raise InferenceBindingError("INVALID_IMAGE_PAGE")
        try:
            with Image.open(io.BytesIO(original)) as img:
                if img.width * img.height > MAX_IMAGE_PIXELS or getattr(img, "n_frames", 1) != 1:
                    raise InferenceBindingError("IMAGE_TOO_LARGE")
                if img.format not in ("PNG", "JPEG", "TIFF"):
                    raise InferenceBindingError("INVALID_SOURCE_IMAGE")
                normalized = img.convert("RGB")
                out = io.BytesIO()
                normalized.save(out, format="PNG")
                encoded = out.getvalue()
        except InferenceBindingError:
            raise
        except Exception as exc:
            raise InferenceBindingError("INVALID_SOURCE_IMAGE") from exc

    if len(encoded) > MAX_SOURCE_BYTES:
        raise InferenceBindingError("IMAGE_TOO_LARGE")
    return encoded


def prepare_inference(session: Session, job: Job) -> dict[str, Any]:
    """Load an immutable input snapshot, without making a model call."""
    if job.kind != "ai_inference" or job.note_id is None:
        raise InferenceBindingError("INVALID_JOB_KIND")
    try:
        payload = json.loads(job.payload_json or "{}")
    except (TypeError, ValueError) as exc:
        raise InferenceBindingError("INVALID_JOB_PAYLOAD") from exc
    adapter = payload.get("adapter")
    page_number = payload.get("page_number")
    source_revision_id = payload.get("source_revision_id")
    extraction_id = payload.get("extraction_id")
    source_hash = payload.get("source_hash")
    model = payload.get("model")
    if (not isinstance(source_revision_id, str) or
            not isinstance(extraction_id, str) or
            not isinstance(source_hash, str) or
            model != model_for(adapter)):
        raise InferenceBindingError("INVALID_JOB_PAYLOAD")
    if job.source_revision_id != source_revision_id:
        raise InferenceBindingError("INVALID_JOB_BINDING")

    rev, ext, asset = check_binding(
        session, job.workspace_id, job.note_id, source_revision_id,
        extraction_id, source_hash, adapter, page_number,
    )
    if adapter == "text":
        source = rev.raw_text.encode("utf-8")
        image = None
    else:
        source = _read_verified_image(asset, page_number)
        image = source
    try:
        rules = json.loads(ext.extracted_json or "{}")
    except (TypeError, ValueError) as exc:
        raise InferenceBindingError("INVALID_EXTRACTION_DATA") from exc
    if not isinstance(rules, dict):
        raise InferenceBindingError("INVALID_EXTRACTION_DATA")
    return {
        "workspace_id": job.workspace_id,
        "note_id": job.note_id,
        "source_revision_id": source_revision_id,
        "source_hash": source_hash,
        "extraction_id": extraction_id,
        "adapter": adapter,
        "page_number": page_number,
        "model": model,
        "image": image,
        "raw_text": rev.raw_text if adapter == "text" else None,
        "rule_data": rules,
        "input_hash": sha256_bytes(source),
        "prompt_template_hash": sha256_bytes(PROMPT_VERSIONS[adapter].encode("utf-8")),
    }


def get_installed_model_digest(model_name: str) -> str:
    """Record the digest actually installed on this local Ollama daemon."""
    vision._ensure_local_ollama_endpoint()
    request = Request(
        f"{vision.OLLAMA_BASE_URL}/api/tags",
        headers={"User-Agent": "ClinicalNLP/2.0"},
    )
    try:
        with urlopen(request, timeout=5.0) as response:
            metadata = response.read(256 * 1024 + 1)
        if len(metadata) > 256 * 1024:
            raise InferenceBindingError("MODEL_REGISTRY_TOO_LARGE")
        models = json.loads(metadata.decode("utf-8")).get("models", [])
        for item in models:
            if item.get("name") == model_name and isinstance(item.get("digest"), str):
                if item["digest"]:
                    return item["digest"]
    except InferenceBindingError:
        raise
    except Exception as exc:
        raise InferenceBindingError("LOCAL_MODEL_UNAVAILABLE") from exc
    raise InferenceBindingError("MODEL_NOT_INSTALLED")


def run_local_inference(input_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Call only the configured local model; never alter authoritative state."""
    adapter = input_snapshot["adapter"]
    digest = get_installed_model_digest(input_snapshot["model"])
    start = time.monotonic()
    if adapter == "glm_ocr":
        output = vision.glm_ocr_infer(
            input_snapshot["image"],
            page_number=input_snapshot["page_number"],
            model=input_snapshot["model"],
        )
        candidates = {
            "transcribed_text": output.get("transcribed_text", ""),
            "boxes": output.get("boxes") or [],
        }
        discrepancies = []
        task_type = "multimodal_ocr"
    elif adapter == "qwen3_vl":
        output = vision.qwen3_vl_infer(
            input_snapshot["image"],
            rule_extraction=input_snapshot["rule_data"],
            model=input_snapshot["model"],
        )
        candidates = output.get("candidates") or {}
        discrepancies = output.get("discrepancies") or []
        task_type = "multimodal_vl"
    else:
        output = text_model.extract_candidates_with_local_ai(
            input_snapshot["raw_text"], model=input_snapshot["model"],
        )
        candidates = output.get("candidates") or {}
        discrepancies = text_model.detect_discrepancies(
            input_snapshot["rule_data"], candidates,
        ) if candidates else []
        task_type = "semantic_candidates"

    if output.get("status") != "completed":
        raise InferenceBindingError(output.get("error_code") or "LOCAL_INFERENCE_FAILED")
    return {
        "task_type": task_type,
        "model": input_snapshot["model"],
        "model_digest": digest,
        "candidates": candidates,
        "discrepancies": discrepancies,
        "duration_ms": max(0, int((time.monotonic() - start) * 1000)),
        "input_hash": input_snapshot["input_hash"],
        "prompt_template_hash": input_snapshot["prompt_template_hash"],
    }
