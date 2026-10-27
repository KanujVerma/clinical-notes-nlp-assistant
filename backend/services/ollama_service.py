import os
import json
import urllib.request
import urllib.error
import hashlib
from typing import Dict, Any, Optional, List
from schemas.extracted_entities import StructuredExtraction
from models import OperationalIssue, InferenceRun


OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OCR_MODEL = os.environ.get("OLLAMA_OCR_MODEL", "glm-ocr:q8_0")
DEFAULT_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen3-vl:4b")


def is_ollama_available() -> bool:
    """Checks if Ollama daemon is reachable."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", headers={"User-Agent": "ClinicalNLP/2.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_ollama(model: str, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Queries Ollama generate endpoint synchronously."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res


def extract_candidates_with_local_ai(
    raw_text: str,
    model: str = DEFAULT_VL_MODEL,
) -> Dict[str, Any]:
    """
    Requests semantic candidate proposals from local Ollama model.
    Falls back gracefully if unavailable.
    """
    if not is_ollama_available():
        return {
            "status": "disabled",
            "error_code": "OLLAMA_OFFLINE",
            "message": "Local Ollama service not reachable.",
            "candidates": None,
        }

    system_prompt = (
        "You are a clinical document parser. Extract medications and vitals into strict JSON format with keys: "
        "'medications' (list of {name, dose, route, frequency, action}) and "
        "'vitals' (list of {vital_type, value, unit}). Do not provide any conversational text."
    )

    prompt = f"Clinical Note:\n```\n{raw_text}\n```"

    try:
        res = query_ollama(model=model, prompt=prompt, system=system_prompt)
        raw_output = res.get("response", "{}")
        parsed = json.loads(raw_output)
        return {
            "status": "completed",
            "model": model,
            "candidates": parsed,
        }
    except Exception as e:
        return {
            "status": "failed",
            "error_code": "INFERENCE_ERROR",
            "message": str(e),
            "candidates": None,
        }


def detect_discrepancies(
    rule_extraction: Dict[str, Any],
    ai_candidate: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Compares deterministic rule extraction with local AI proposals.
    Flags discrepancies in dose, route, frequency, or omission.
    """
    discrepancies = []
    rule_meds = {m.get("name", "").lower().strip(): m for m in rule_extraction.get("medications", []) if m.get("name")}
    ai_meds = {m.get("name", "").lower().strip(): m for m in ai_candidate.get("medications", []) if m.get("name")}

    # Check medications found by AI but missed by rules
    for name, a_med in ai_meds.items():
        if name not in rule_meds:
            discrepancies.append({
                "type": "omitted_medication",
                "medication": name,
                "detail": f"AI model proposed medication '{name}' which was not extracted by deterministic pipeline.",
                "ai_candidate": a_med,
            })
        else:
            r_med = rule_meds[name]
            # Check dose discrepancy
            r_dose = (r_med.get("dose") or "").strip().lower()
            a_dose = (a_med.get("dose") or "").strip().lower()
            if r_dose and a_dose and r_dose != a_dose:
                discrepancies.append({
                    "type": "dose_discrepancy",
                    "medication": name,
                    "detail": f"Dose discrepancy for '{name}': Rules extracted '{r_dose}', but AI proposed '{a_dose}'.",
                    "rule_value": r_dose,
                    "ai_value": a_dose,
                })

    return discrepancies
