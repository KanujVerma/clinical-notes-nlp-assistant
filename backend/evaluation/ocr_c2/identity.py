"""Campaign-2 fingerprints. Inference and scoring identities are separate."""
from __future__ import annotations

import ast
import json

from evaluation.ocr_c2.protocol import IDENTITY_VERSION, MANIFEST_PATH, PARTITION_PATH, ROOT, load_protocol
from evaluation.public_amr_benchmark import sha

INFERENCE_FILES = (
    "backend/evaluation/ocr_c2/native.py",
    "backend/evaluation/ocr_c2/segment.py",
    "backend/evaluation/ocr_c2/runner.py",
)
INFERENCE_SYMBOLS = (
    ("backend/evaluation/public_amr_benchmark.py", ("MAX_INPUT_BYTES", "check", "infer_image")),
)
SCORING_FILES = (
    "backend/evaluation/ocr_c2/metrics.py",
)
SCORING_SYMBOLS = (
    ("backend/evaluation/pr10_replay.py", ("critical_occurrences", "align_critical", "reference_text")),
    ("backend/evaluation/public_amr_benchmark.py", ("CRITICAL", "score")),
    ("backend/evaluation/local_vision_eval.py", ("exact_critical_tokens", "_score_text")),
    ("backend/services/multimodal_service.py", ("_levenshtein_distance", "calculate_cer_wer")),
)
CONTROL_SYMBOLS = (
    ("backend/services/multimodal_service.py", (
        "OLLAMA_BASE_URL", "DEFAULT_OCR_MODEL", "DEFAULT_VL_MODEL",
        "_ensure_local_ollama_endpoint", "_parse_model_json",
        "query_ollama_multimodal", "glm_ocr_infer",
    )),
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def _assigned_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign):
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        return names[0] if len(names) == 1 else None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def symbol_source(text: str, names: tuple[str, ...]) -> str:
    """Source of named implementations, in the requested order."""
    tree = ast.parse(text)
    found: dict[str, str] = {}
    for node in tree.body:
        name = _assigned_name(node)
        if name in names and name not in found:
            found[name] = ast.get_source_segment(text, node) or ""
    missing = [name for name in names if name not in found]
    if missing:
        raise ValueError("OCR_C2_FINGERPRINT_SYMBOLS:" + ",".join(missing))
    return "\n".join(found[name] for name in names)


def _parts(files: tuple[str, ...], symbols: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    parts = [relative + "\n" + sha(_read(relative).encode()) for relative in files]
    for relative, names in symbols:
        parts.append(relative + ":" + ",".join(names) + "\n" + symbol_source(_read(relative), names))
    return parts


def _bundle(parts: list[str]) -> str:
    return sha("\n".join(parts).encode())


def inference_hash() -> str:
    return _bundle(_parts(INFERENCE_FILES, INFERENCE_SYMBOLS))


def scoring_hash() -> str:
    return _bundle(_parts(SCORING_FILES, SCORING_SYMBOLS))


def control_hash() -> str:
    return _bundle(_parts((), CONTROL_SYMBOLS))


def request_identity(
    candidate: str, dataset: str, case_ids: list[str], model_digest: str, parent: str | None = None,
) -> dict:
    from evaluation.ocr_c2.native import resolved_spec
    protocol = load_protocol()
    spec = resolved_spec(candidate, parent)
    body = {
        "identity_version": IDENTITY_VERSION,
        "campaign_id": protocol["campaign_id"],
        "candidate": candidate,
        "parent": spec.get("parent"),
        "dataset": dataset,
        "case_ids_sha256": sha("\n".join(case_ids).encode()),
        "protocol_sha256": sha(MANIFEST_PATH.read_bytes()),
        "partition_sha256": sha(PARTITION_PATH.read_bytes()),
        "model": protocol["model"]["tag"],
        "model_digest": model_digest,
        "geometry": spec.get("geometry"),
        "num_ctx": spec.get("num_ctx"),
        "num_predict": spec.get("num_predict"),
        "keep_alive": spec.get("keep_alive"),
        "prompt": protocol["model"]["native_prompt"] if spec["role"] != "control" else spec["prompt"],
        "inference_sha256": inference_hash(),
        "scoring_sha256": scoring_hash(),
    }
    if spec["role"] == "control":
        body["control_sha256"] = control_hash()
    body["experiment_fingerprint"] = sha(json.dumps(body, sort_keys=True).encode())
    return body
