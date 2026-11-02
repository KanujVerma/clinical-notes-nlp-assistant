"""Own one Vision helper process. The helper never receives a shell string."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from evaluation.ocr_c3.budget import BudgetExhausted, Ledger
from evaluation.ocr_c3.protocol import load_protocol
from evaluation.ocr_c3.schema import validate_result


class HelperTimeout(RuntimeError):
    pass


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=5)


def run_helper(
    binary: Path,
    image_path: Path,
    output_path: Path,
    request_id: str,
    config_path: Path,
    source_fingerprint: str,
    dataset: str,
    case_id: str,
    page_index: int,
    source_sha256: str,
    prepared: bytes,
    ledger: Ledger,
    launch=None,
) -> dict:
    protocol = load_protocol()
    deadline = min(protocol["budgets"]["per_page_seconds"], ledger.remaining())
    try:
        allowed = ledger.begin(request_id, deadline)
    except BudgetExhausted:
        return {"status": "budget_blocked", "completed": False, "transcription": ""}
    argv = [
        str(binary),
        "--image", str(image_path),
        "--output", str(output_path),
        "--request-id", request_id,
        "--config", str(config_path),
        "--source-fingerprint", source_fingerprint,
        "--dataset", dataset,
        "--case-id", case_id,
        "--page-index", str(page_index),
        "--source-sha256", source_sha256,
    ]
    started = time.perf_counter()
    launcher = launch or _launch
    try:
        completed = launcher(argv, allowed, output_path)
    except HelperTimeout:
        elapsed = time.perf_counter() - started
        ledger.finish(request_id, max(elapsed, allowed))
        return {"status": "timeout", "completed": False, "transcription": "", "elapsed_seconds": elapsed}
    except Exception:
        ledger.recover_crashes()
        raise
    elapsed = time.perf_counter() - started
    ledger.finish(request_id, elapsed)
    if completed.get("returncode") not in (0, None) and not output_path.exists():
        return {"status": "vision_request_failed", "completed": False, "transcription": "", "elapsed_seconds": elapsed}
    try:
        payload = json.loads(output_path.read_text())
        checked = validate_result(payload, prepared, protocol["runtime"]["vision_revision"])
    except (OSError, json.JSONDecodeError, ValueError):
        return {"status": "integrity_blocked", "completed": False, "transcription": "", "elapsed_seconds": elapsed}
    status = payload.get("status")
    return {
        "status": status,
        "completed": status == "completed",
        "transcription": checked["transcription"] if status == "completed" else "",
        "elapsed_seconds": elapsed,
        "result": payload,
    }


def _launch(argv: list[str], allowed: float, output_path: Path) -> dict:
    process = subprocess.Popen(argv, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.communicate(timeout=allowed)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        if output_path.exists():
            output_path.unlink()
        raise HelperTimeout("timeout")
    return {"returncode": process.returncode}
