"""Native GLM request builder. No JSON grammar and no network at import."""
from __future__ import annotations

import base64

from evaluation.ocr_c2.protocol import load_protocol

NATIVE_PROMPT = "Text Recognition:"
CONTROL_MODEL = "glm-ocr:q8_0"


def control_call(kind: str, image_bytes: bytes, page_number: int, infer, timeout: float | None = None) -> dict:
    """Call the frozen JSON adapter without changing its prompt defaults."""
    extra = {} if timeout is None else {"timeout": timeout}
    if kind == "B8192":
        return infer(image_bytes, page_number=page_number, model=CONTROL_MODEL, num_ctx=8192, **extra)
    if kind == "Blegacy":
        return infer(image_bytes, page_number=page_number, model=CONTROL_MODEL, num_ctx=None, **extra)
    raise ValueError("OCR_C2_CONTROL")


class ModelMismatch(ValueError):
    pass


class DigestDrift(ValueError):
    pass


def resolved_spec(candidate: str, parent: str | None = None) -> dict:
    """N5 keeps its parent's geometry and decoder and changes only keep_alive."""
    spec = dict(load_protocol()["candidates"][candidate])
    if candidate != "N5":
        return spec
    if parent not in {"N1", "N2", "N3", "N4"}:
        raise ValueError("OCR_C2_N5_PARENT")
    base = dict(load_protocol()["candidates"][parent])
    base.update({"role": "runtime", "keep_alive": "5m", "parent": parent})
    return base


def build_native_payload(image_bytes: bytes, candidate: str, keep_alive=None, parent: str | None = None) -> dict:
    spec = resolved_spec(candidate, parent)
    model = load_protocol()["model"]
    if spec["role"] not in {"native", "runtime"}:
        raise ValueError("OCR_C2_NOT_NATIVE")
    num_predict = spec.get("num_predict", 2048)
    payload = {
        "model": model["tag"],
        "prompt": NATIVE_PROMPT,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False,
        "keep_alive": spec.get("keep_alive", 0) if keep_alive is None else keep_alive,
        "options": {
            "temperature": 0,
            "num_predict": num_predict,
            "num_ctx": spec.get("num_ctx", 8192),
        },
    }
    if "format" in payload or "raw" in payload or "system" in payload:
        raise ValueError("OCR_C2_NATIVE_CONTRACT")
    if payload["prompt"] != NATIVE_PROMPT:
        raise ValueError("OCR_C2_NATIVE_PROMPT")
    return payload


def interpret_native_response(response: dict, requested_model: str, expected_digest: str | None = None) -> dict:
    if not isinstance(response, dict):
        return {"status": "malformed_transport", "transcription": "", "scored": False}
    observed = response.get("model")
    if observed != requested_model:
        raise ModelMismatch("model_mismatch")
    if expected_digest is not None and response.get("model_digest") != expected_digest:
        raise DigestDrift("model_digest_mismatch")
    text = response.get("response")
    meta = {
        "done": response.get("done"),
        "done_reason": response.get("done_reason"),
        "prompt_eval_count": response.get("prompt_eval_count"),
        "eval_count": response.get("eval_count"),
        "load_duration": response.get("load_duration"),
        "eval_duration": response.get("eval_duration"),
    }
    if not isinstance(text, str) or response.get("done") is not True:
        return {"status": "malformed_transport", "transcription": "", "scored": False, **meta}
    if response.get("done_reason") == "length":
        return {"status": "generation_limit", "transcription": text, "scored": False, **meta}
    if not text.strip():
        return {"status": "empty_transcription", "transcription": text, "scored": False, **meta}
    return {"status": "scored", "transcription": text, "scored": True, **meta}
