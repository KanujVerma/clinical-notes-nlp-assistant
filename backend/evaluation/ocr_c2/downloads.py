"""Authorize the optional TrOCR file set. This module does not fetch weights."""
from __future__ import annotations

from evaluation.ocr_c2.protocol import load_protocol


class DownloadRefused(ValueError):
    pass


def authorize(files: list[dict]) -> dict:
    spec = load_protocol()["trocr_authorized_files"]
    cap = load_protocol()["budgets"]["max_new_model_bytes"]
    names = [item["name"] for item in files]
    if any(name.endswith(".bin") or name in spec["forbid"] for name in names):
        raise DownloadRefused("bin_weight_forbidden")
    weights = [item for item in files if item["name"].endswith(".safetensors")]
    if len(weights) != 1:
        raise DownloadRefused("weight_count")
    allowed = spec["files"]
    if any(item["name"] not in allowed for item in files):
        raise DownloadRefused("unexpected_file")
    if any(item["size"] != allowed[item["name"]] for item in files):
        raise DownloadRefused("size_mismatch")
    total = sum(item["size"] for item in files)
    if total > cap or total <= 0:
        raise DownloadRefused("byte_cap")
    return {"bytes": total, "files": names, "downloaded": False}
