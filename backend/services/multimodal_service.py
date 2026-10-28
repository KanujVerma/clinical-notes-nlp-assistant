import os
import json
import base64
import urllib.request
import urllib.error
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from services.ollama_service import is_ollama_available, detect_discrepancies

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OCR_MODEL = os.environ.get("OLLAMA_OCR_MODEL", "glm-ocr:q8_0")
DEFAULT_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen3-vl:4b")


def query_ollama_multimodal(
    model: str,
    prompt: str,
    images_b64: List[str],
    system: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Queries local Ollama instance with multimodal inputs (base64 images).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "format": "json",
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "ClinicalNLP/2.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        "You are an accurate visual OCR document parser (GLM-OCR). "
        "Extract text and spatial layout from the image into strict JSON format with keys: "
        "'text' (full transcribed text string), "
        "'boxes' (list of {text, bbox: [x0, y0, x1, y1]}), and "
        "'confidence' (number between 0 and 1)."
    )
    prompt = f"Perform OCR layout analysis on page {page_number}."

    try:
        res = query_ollama_multimodal(
            model=active_model,
            prompt=prompt,
            images_b64=[b64_img],
            system=system_prompt,
        )
        raw_output = res.get("response", "{}")
        parsed = json.loads(raw_output)
        if not isinstance(parsed, dict):
            parsed = {"text": str(raw_output), "boxes": []}

        return {
            "status": "completed",
            "model": active_model,
            "page_number": page_number,
            "transcribed_text": str(parsed.get("text", "")).strip(),
            "boxes": parsed.get("boxes", []) if isinstance(parsed.get("boxes"), list) else [],
            "confidence": float(parsed.get("confidence", 0.9)),
        }
    except Exception as e:
        return {
            "status": "failed",
            "model": active_model,
            "error_code": "INFERENCE_ERROR",
            "message": str(e),
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
        "Extract all medications and vitals visible in this clinical note image into strict JSON: "
        "'medications' (list of {name, dose, route, frequency}), "
        "'vitals' (list of {vital_type, value, unit}), and "
        "'visual_evidence' (list of {entity, bbox: [x0, y0, x1, y1]})."
    )
    prompt = "Extract clinical entities from the document image."

    try:
        res = query_ollama_multimodal(
            model=active_model,
            prompt=prompt,
            images_b64=[b64_img],
            system=system_prompt,
        )
        raw_output = res.get("response", "{}")
        parsed = json.loads(raw_output)
        if not isinstance(parsed, dict):
            parsed = {"medications": [], "vitals": []}

        # Normalize medications
        meds = []
        for m in parsed.get("medications", []):
            if isinstance(m, dict) and m.get("name"):
                meds.append({
                    "name": str(m["name"]).strip(),
                    "dose": str(m.get("dose", "")).strip(),
                    "route": str(m.get("route", "")).strip(),
                    "frequency": str(m.get("frequency", "")).strip(),
                })
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
            "message": str(e),
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
    cer = round(min(1.0, char_dist / ref_len), 4)

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
    wer = round(min(1.0, dp[len(ref_words)][len(hyp_words)] / word_len), 4)

    return {
        "cer": cer,
        "wer": wer,
        "char_distance": char_dist,
        "word_distance": dp[len(ref_words)][len(hyp_words)],
        "ref_chars": len(ref_clean),
        "ref_words": len(ref_words),
    }
