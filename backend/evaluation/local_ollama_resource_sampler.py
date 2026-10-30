"""Best-effort LOCAL Ollama resource observations during REAL inference.

The Python benchmark process RSS is not the Ollama model's RAM. This sampler
records model residency reported by Ollama /api/ps and the separately observed
runner-process RSS, without conflating the two. No synthetic measurements.
Missing samples are explicitly UNMEASURED, never zero.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
from typing import Any
from urllib.request import Request, urlopen

from services.multimodal_service import (
    DEFAULT_OCR_MODEL, DEFAULT_VL_MODEL, OLLAMA_BASE_URL,
    _ensure_local_ollama_endpoint,
)

_ARM_NAMES = {
    "glm_ocr": DEFAULT_OCR_MODEL,
    "qwen3_vl": DEFAULT_VL_MODEL,
}


def _parse_running_models(raw: bytes, expected: set[str]) -> list[dict[str, Any]]:
    obj = json.loads(raw.decode("utf-8"))
    records = obj.get("models") if isinstance(obj, dict) else None
    if not isinstance(records, list):
        raise ValueError("OLLAMA_PS_INVALID")
    found = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("model")
        if name not in expected:
            continue
        size = entry.get("size")
        vram = entry.get("size_vram")
        if type(size) is not int or size < 0 or type(vram) is not int or vram < 0:
            continue
        found.append({
            "model": name,
            "model_residency_bytes": size,
            "model_vram_bytes": vram,
        })
    return found


def _local_runner_rss_bytes() -> int | None:
    """Observed per-process RSS only, not GPU VRAM or allocated model size."""
    try:
        out = subprocess.run(
            ["ps", "-ax", "-o", "rss=", "-o", "command="],
            text=True, capture_output=True, check=True, timeout=2,
        ).stdout[:500000]
    except (OSError, subprocess.SubprocessError):
        return None
    rss = []
    for line in out.splitlines():
        m = re.match(r"^\s*(\d+)\s+(.+)$", line)
        if not m:
            continue
        command = m.group(2).casefold()
        if ("ollama runner" in command or "ollama_llama_server" in command
                or "ollama-runner" in command):
            rss.append(int(m.group(1)) * 1024)  # ps rss is KiB on Linux/macOS
    return sum(rss) if rss else None


class LocalOllamaResourceSampler:
    """Limited independent observer, not an inference runner or memory profiler."""

    def __init__(self, arms: tuple[str, ...], interval_seconds: float = 0.25):
        self.expected = {_ARM_NAMES[a] for a in arms if a in _ARM_NAMES}
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.poll_count = 0
        self.error_count = 0
        self.peak_model_residency_bytes: int | None = None
        self.peak_model_vram_bytes: int | None = None
        self.peak_runner_rss_bytes: int | None = None
        self.sampled_names: set[str] = set()

    def __enter__(self):
        if self.expected:
            # This hard-fails if OLLAMA_HOST is not a loopback-only endpoint.
            _ensure_local_ollama_endpoint()
            self._thread = threading.Thread(
                target=self._poll_loop, name="local-ollama-residency", daemon=True,
            )
            self._thread.start()
        return self

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                req = Request(
                    OLLAMA_BASE_URL.rstrip("/") + "/api/ps",
                    headers={"User-Agent": "ClinicalNLPLocalResourceProbe/1.0"},
                )
                with urlopen(req, timeout=1) as response:
                    raw = response.read(256 * 1024 + 1)
                if len(raw) > 256 * 1024:
                    raise ValueError("OLLAMA_PS_TOO_LARGE")
                rows = _parse_running_models(raw, self.expected)
                self.poll_count += 1
                if rows:
                    self.sampled_names.update(x["model"] for x in rows)
                    residency = sum(x["model_residency_bytes"] for x in rows)
                    vram = sum(x["model_vram_bytes"] for x in rows)
                    self.peak_model_residency_bytes = max(
                        residency, self.peak_model_residency_bytes or 0,
                    )
                    self.peak_model_vram_bytes = max(
                        vram, self.peak_model_vram_bytes or 0,
                    )
                    rss = _local_runner_rss_bytes()
                    if rss is not None:
                        self.peak_runner_rss_bytes = max(
                            rss, self.peak_runner_rss_bytes or 0,
                        )
            except (OSError, ValueError, KeyError, TypeError, TimeoutError):
                self.error_count += 1
            self._stop.wait(self.interval_seconds)

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def report(self) -> dict[str, Any]:
        return {
            "status": (
                "not_applicable_tesseract_only" if not self.expected
                else "observed_local_ollama" if self.sampled_names
                else "unmeasured_no_matching_loaded_model_sample"
            ),
            "requested_model_names": sorted(self.expected),
            "observed_model_names": sorted(self.sampled_names),
            "poll_count": self.poll_count,
            "probe_errors": self.error_count,
            "peak_reported_model_residency_bytes": self.peak_model_residency_bytes,
            "peak_reported_model_vram_bytes": self.peak_model_vram_bytes,
            "peak_unattributed_ollama_runner_rss_bytes": self.peak_runner_rss_bytes,
            "measurement_limits": [
                "Ollama /api/ps reports loaded-model residency, not total system RAM",
                "GPU VRAM is separate from process RSS; these numbers must not be added",
                "The ps RSS may cover other concurrent Ollama runners",
                "Polling can miss brief loads; absent samples mean unmeasured, never zero",
            ],
        }
