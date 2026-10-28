import os
import json
import urllib.request
import urllib.error
import hashlib
from collections import defaultdict
from urllib.parse import urlsplit
from typing import Dict, Any, Optional, List
from schemas.extracted_entities import StructuredExtraction
from models import OperationalIssue, InferenceRun


OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OCR_MODEL = os.environ.get("OLLAMA_OCR_MODEL", "glm-ocr:q8_0")
DEFAULT_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen3-vl:4b")


def _local_ollama_only() -> bool:
    url = urlsplit(OLLAMA_BASE_URL)
    return (
        url.scheme == "http"
        and url.hostname in ("localhost", "127.0.0.1", "::1")
        and url.username is None and url.password is None
        and url.path in ("", "/") and not url.query and not url.fragment
    )


def is_ollama_available() -> bool:
    """Checks if Ollama daemon is reachable."""
    if not _local_ollama_only():
        return False
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", headers={"User-Agent": "ClinicalNLP/2.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_ollama(model: str, prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Queries Ollama generate endpoint synchronously."""
    if not _local_ollama_only():
        raise ValueError("Ollama must use a local loopback endpoint")
    if model != DEFAULT_VL_MODEL:
        raise ValueError("Text proposals must use the configured local model")
    if not isinstance(prompt, str) or len(prompt) > 32768:
        raise ValueError("Text prompt exceeds the configured model budget")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": 0,
        "options": {"temperature": 0, "num_predict": 1024},
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
        if not isinstance(parsed, dict):
            raise ValueError("Candidate response must be a JSON object")

        # Normalize and validate candidate fields
        if "medications" in parsed:
            if not isinstance(parsed["medications"], list):
                raise ValueError("Medications must be a list")
            cleaned_meds = []
            for item in parsed["medications"]:
                if not isinstance(item, dict):
                    continue
                cleaned_item = {str(k): str(v) for k, v in item.items() if v is not None}
                if cleaned_item.get("name"):
                    cleaned_meds.append(cleaned_item)
            parsed["medications"] = cleaned_meds
        else:
            parsed["medications"] = []

        if "vitals" in parsed and not isinstance(parsed["vitals"], (list, dict)):
            raise ValueError("Vitals must be a list or dict")

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
    """Preserve duplicate-medication ambiguity instead of pairing by name.

    Independent candidates may have different occurrence counts. Without
    verified source occurrence IDs it is unsafe to choose the medication
    instance that happens to match a model's dose, route or frequency.
    """
    discrepancies: List[Dict[str, Any]] = []
    rule_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    ai_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def collect(records: Any, target: Dict[str, List[Dict[str, Any]]]) -> None:
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            name = str(record.get("name") or "").strip().casefold()
            if name:
                target[name].append(record)

    collect(rule_extraction.get("medications"), rule_by_name)
    collect(ai_candidate.get("medications"), ai_by_name)

    for name in sorted(set(rule_by_name) | set(ai_by_name)):
        rules = rule_by_name.get(name, [])
        proposals = ai_by_name.get(name, [])
        if not rules:
            for item in proposals:
                discrepancies.append({
                    "type": "omitted_medication",
                    "medication": name,
                    "detail": "AI proposed a medication occurrence missing from the rule output",
                    "ai_candidate": item,
                })
            continue
        if not proposals:
            discrepancies.append({
                "type": "ai_omission",
                "medication": name,
                "detail": "Rule output contained medication not identified by AI",
                "rule_count": len(rules),
            })
            continue
        if len(rules) != 1 or len(proposals) != 1:
            discrepancies.append({
                "type": "ambiguous_duplicate_occurrences",
                "medication": name,
                "detail": "Duplicate-name occurrences need source-grounded reviewer pairing",
                "rule_count": len(rules),
                "ai_count": len(proposals),
            })
            continue
        rule_item, ai_item = rules[0], proposals[0]
        for field in ("dose", "route", "frequency", "action"):
            rule_value = str(rule_item.get(field) or "").strip().casefold()
            ai_value = str(ai_item.get(field) or "").strip().casefold()
            if rule_value and ai_value and rule_value != ai_value:
                discrepancies.append({
                    "type": f"{field}_discrepancy",
                    "medication": name,
                    "detail": f"Rules and AI disagree on {field}",
                    "rule_value": rule_value,
                    "ai_value": ai_value,
                })
    return discrepancies
