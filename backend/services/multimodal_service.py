import os
import json
import base64
import re
import urllib.request
import urllib.error
import hashlib
from urllib.parse import urlsplit
from typing import Dict, Any, Optional, List, Tuple
from services.ollama_service import is_ollama_available, detect_discrepancies

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OCR_MODEL = os.environ.get("OLLAMA_OCR_MODEL", "glm-ocr:q8_0")
DEFAULT_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen3-vl:4b")


def _parse_model_json(raw: str) -> Any:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _ensure_local_ollama_endpoint() -> None:
    """Reject accidental remote/cloud model endpoints and URLs with secrets."""
    url = urlsplit(OLLAMA_BASE_URL)
    if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1", "::1")
            or url.username is not None or url.password is not None
            or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("Ollama must use an HTTP loopback endpoint")


def query_ollama_multimodal(
    model: str,
    prompt: str,
    images_b64: List[str],
    system: Optional[str] = None,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """
    Queries local Ollama instance with multimodal inputs (base64 images).
    """
    _ensure_local_ollama_endpoint()
    if model not in (DEFAULT_OCR_MODEL, DEFAULT_VL_MODEL):
        raise ValueError("Model is not in the local vision allowlist")
    if len(images_b64) != 1 or len(images_b64[0]) > 14 * 1024 * 1024:
        raise ValueError("Only one bounded local image is allowed")
    if not isinstance(prompt, str) or len(prompt) > 8192:
        raise ValueError("Invalid bounded model prompt")
    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "format": "json",
        "keep_alive": 0,
        "options": {"temperature": 0, "num_predict": 2048},
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "ClinicalNLP/2.0"},
    )
    with urllib.request.urlopen(req, timeout=max(1.0, min(timeout, 90.0))) as resp:
        response_bytes = resp.read(128 * 1024 + 1)
        if len(response_bytes) > 128 * 1024:
            raise ValueError("Vision model output exceeded the bounded response size")
        response = json.loads(response_bytes.decode("utf-8"))
        if not isinstance(response, dict):
            raise ValueError("Vision model response must be an object")
        return response


def glm_ocr_infer(
    image_bytes: bytes,
    page_number: int = 1,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    GLM-OCR multimodal adapter: transcribes document layout and text
    directly from original image bytes.
    Keeps inference optional and isolated from authoritative state.
    """
    active_model = model or DEFAULT_OCR_MODEL
    if not is_ollama_available():
        return {
            "status": "disabled",
            "model": active_model,
            "error_code": "OLLAMA_OFFLINE",
            "message": "Local Ollama service not reachable for GLM-OCR.",
            "transcribed_text": "",
            "boxes": [],
            "page_number": page_number,
        }

    b64_img = base64.b64encode(image_bytes).decode("ascii")
    system_prompt = (
        "You are an accurate visual OCR document transcription model (GLM-OCR). "
        "Transcribe all text from the image accurately into JSON format with keys: "
        "'text' (full transcribed text string of all lines), "
        "'boxes' (list of {text, bbox: [x0, y0, x1, y1]}), and "
        "'confidence' (number between 0 and 1). "
        "Ensure all document lines are included in the 'text' field."
    )
    prompt = f"Transcribe all visible text from page {page_number} into JSON now."

    try:
        res = query_ollama_multimodal(
            model=active_model,
            prompt=prompt,
            images_b64=[b64_img],
            system=system_prompt,
        )
        raw_output = res.get("response", "{}")
        parsed = _parse_model_json(raw_output)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("text"), str):
            raise ValueError("Malformed visual transcription response")
        transcript = parsed["text"].strip()
        if len(transcript) > 32768:
            raise ValueError("Vision transcription exceeds output limit")
        raw_boxes = parsed.get("boxes", [])
        if not isinstance(raw_boxes, list) or len(raw_boxes) > 1000:
            raise ValueError("Unbounded visual evidence boxes")
        valid_boxes = []
        for box in raw_boxes:
            if not isinstance(box, dict) or not isinstance(box.get("text"), str):
                continue
            geometry = box.get("bbox")
            if isinstance(geometry, list) and len(geometry) == 1 and isinstance(geometry[0], dict):
                d = geometry[0]
                geometry = [d.get("x0", 0), d.get("y0", 0), d.get("x1", 0), d.get("y1", 0)]
            elif isinstance(geometry, dict):
                geometry = [geometry.get("x0", 0), geometry.get("y0", 0), geometry.get("x1", 0), geometry.get("y1", 0)]
            if (isinstance(geometry, list) and len(geometry) == 4 and
                    all(type(v) in (int, float) for v in geometry) and
                    (0 <= geometry[0] < geometry[2] and 0 <= geometry[1] < geometry[3])):
                valid_boxes.append({
                    "text": box["text"][:256],
                    "bbox": geometry,
                    "source_verification": "model_proposed_unverified",
                })
        # If model returned no text in the main field, assemble from boxes
        if not transcript and raw_boxes:
            box_lines = [b.get("text", "").strip() for b in raw_boxes if isinstance(b, dict) and b.get("text")]
            transcript = "\n".join(b for b in box_lines if b)
            if len(transcript) > 32768:
                raise ValueError("Vision transcription exceeds output limit")

        return {
            "status": "completed",
            "model": active_model,
            "page_number": page_number,
            "transcribed_text": transcript,
            "boxes": valid_boxes,
            "confidence": None,  # Never treat model self-report as calibrated accuracy
            "source_verification": "model_proposed_unverified",
        }
    except Exception as e:
        return {
            "status": "failed",
            "model": active_model,
            "error_code": "INFERENCE_ERROR",
            "message": "Local vision inference failed validation or execution",
            "transcribed_text": "",
            "boxes": [],
            "page_number": page_number,
        }


def qwen3_vl_infer(
    image_bytes: bytes,
    rule_extraction: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Qwen3-VL vision-language adapter: extracts structured clinical entities
    (medications, vitals) directly from visual document image.
    Does NOT overwrite reviewed state; produces candidate proposals only.
    """
    active_model = model or DEFAULT_VL_MODEL
    if not is_ollama_available():
        return {
            "status": "disabled",
            "model": active_model,
            "error_code": "OLLAMA_OFFLINE",
            "message": "Local Ollama service not reachable for Qwen3-VL.",
            "candidates": None,
            "discrepancies": [],
        }

    b64_img = base64.b64encode(image_bytes).decode("ascii")
    system_prompt = (
        "You are a clinical vision-language model (Qwen3-VL). "
        "Keep your thinking very brief (under 5 sentences), then output JSON: "
        "{\"medications\": [{\"name\": \"...\", \"dose\": \"...\", \"route\": \"...\", \"frequency\": \"...\", \"action\": \"...\"}], "
        "\"vitals\": [{\"vital_type\": \"...\", \"value\": \"...\", \"unit\": \"...\"}]}. "
        "If an attribute like action is not explicitly stated, use empty string. Use exact names, numbers and units as shown."
    )
    prompt = "Extract clinical entities from the document image into JSON now. Keep thinking brief."

    try:
        res = query_ollama_multimodal(
            model=active_model,
            prompt=prompt,
            images_b64=[b64_img],
            system=system_prompt,
        )
        raw_output = res.get("response", "{}")
        parsed = _parse_model_json(raw_output)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("medications"), list):
            raise ValueError("Malformed structured vision candidates")
        if len(parsed["medications"]) > 100:
            raise ValueError("Too many model-proposed medications")
        if not isinstance(parsed.get("vitals", []), list) or len(parsed.get("vitals", [])) > 100:
            raise ValueError("Malformed or unbounded model-proposed vitals")
        evidence = parsed.get("visual_evidence", [])
        if not isinstance(evidence, list) or len(evidence) > 100:
            raise ValueError("Unbounded proposed visual evidence")
        parsed["visual_evidence"] = []  # Unverified model geometry is not exact source evidence.

        # Normalize medications
        meds = []
        for m in parsed.get("medications", []):
            if isinstance(m, dict) and m.get("name"):
                candidate = {
                    "name": str(m["name"]).strip(),
                    "dose": str(m.get("dose", "")).strip(),
                    "route": str(m.get("route", "")).strip(),
                    "frequency": str(m.get("frequency", "")).strip(),
                    "action": str(m.get("action", "")).strip(),
                }
                if any(len(v) > 160 for v in candidate.values()) or not candidate["name"]:
                    raise ValueError("Malformed or oversized model medication field")
                meds.append(candidate)
        parsed["medications"] = meds

        # Detect discrepancies against deterministic rule extraction
        discrepancies = []
        if rule_extraction:
            discrepancies = detect_discrepancies(rule_extraction, parsed)

        return {
            "status": "completed",
            "model": active_model,
            "candidates": parsed,
            "discrepancies": discrepancies,
            "visual_evidence": parsed.get("visual_evidence", []),
        }
    except Exception as e:
        return {
            "status": "failed",
            "model": active_model,
            "error_code": "INFERENCE_ERROR",
            "message": "Local vision inference failed validation or execution",
            "candidates": None,
            "discrepancies": [],
        }


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def calculate_cer_wer(reference: str, hypothesis: str) -> Dict[str, float]:
    """
    Calculates Character Error Rate (CER) and Word Error Rate (WER)
    between ground-truth reference and model hypothesis.
    """
    ref_clean = reference.strip()
    hyp_clean = hypothesis.strip()

    # CER
    ref_len = len(ref_clean) or 1
    char_dist = _levenshtein_distance(ref_clean, hyp_clean)
    cer = round(char_dist / ref_len, 4)

    # WER
    ref_words = ref_clean.split()
    hyp_words = hyp_clean.split()
    word_len = len(ref_words) or 1

    # Word distance
    word_dist = 0
    dp = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i - 1].lower() == hyp_words[j - 1].lower():
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    wer = round(dp[len(ref_words)][len(hyp_words)] / word_len, 4)

    return {
        "cer": cer,
        "wer": wer,
        "char_distance": char_dist,
        "word_distance": dp[len(ref_words)][len(hyp_words)],
        "ref_chars": len(ref_clean),
        "ref_words": len(ref_words),
    }
