"""Real two-PROCESS SQLite persistence gate for the synthetic review workflow.

Starts Flask in a disposable subprocess, creates a source-bound completed
review, STOPS the process, starts a new process on the SAME disposable SQLite
file, and verifies history/source/extraction/metrics survived. No real PHI,
production database, cloud service, Vercel or paid inference is touched.

    python scripts/check_restart_persistence.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SYNTHETIC = "Synthetic review demo. BP: 120/80. HR: 72. No identifying data."
WORKSPACE = "synthetic-qa-process-restart"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json(base_url: str, path: str, session: str, payload=None):
    headers = {"X-Session-ID": session}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        base_url + path, data=body, headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read(250_000).decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read(250_000).decode("utf-8"))


def _start(port: int, db_url: str):
    env = {
        **os.environ,
        "APP_MODE": "local",
        "DATABASE_URL": db_url,
        "ENABLE_EXTERNAL_EXPLAINER": "false",
        "FRONTEND_URL": "",
        "PYTHONPATH": str(BACKEND),
    }
    command = [
        sys.executable, "-u", "-c",
        (
            "import sys; from app import create_app; "
            "app=create_app(); "
            "app.run(host='127.0.0.1', port=int(sys.argv[1]), "
            "debug=False, use_reloader=False)"
        ),
        str(port),
    ]
    process = subprocess.Popen(
        command, cwd=str(BACKEND), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = "http://127.0.0.1:" + str(port)
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("LOCAL_FLASK_PROCESS_EXITED")
        try:
            with urlopen(base + "/api/health/ready", timeout=1) as response:
                if response.status == 200:
                    return process, base
        except (HTTPError, URLError, TimeoutError):
            time.sleep(0.25)
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("LOCAL_FLASK_READINESS_TIMEOUT")


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _decisions(extracted):
    decisions = {}
    for category in ("vitals", "instructions", "metadata"):
        for field, value in (extracted.get(category) or {}).items():
            if value is not None:
                decisions[category + "." + field] = {"decision": "accept"}
    for index, med in enumerate(extracted.get("medications") or []):
        identity = med.get("id") or med.get("source_occurrence_id") or ("med_" + str(index))
        decisions["med." + str(identity)] = {"decision": "accept"}
    return decisions


def verify() -> dict:
    with tempfile.TemporaryDirectory(prefix="clinical-nlp-restart-synthetic-") as tmp:
        db_path = Path(tmp) / "synthetic-restart.sqlite"
        url = "sqlite:///" + str(db_path)
        port = _port()
        process, base = _start(port, url)
        try:
            status, created = _json(base, "/api/notes", WORKSPACE, {"text": SYNTHETIC})
            if status != 201:
                raise RuntimeError("SYNTHETIC_NOTE_CREATION_FAILED")
            note_id = created["note_id"]
            status, source = _json(base, "/api/notes/" + str(note_id) + "/source", WORKSPACE)
            if status != 200:
                raise RuntimeError("SOURCE_READ_FAILED")
            status, detail = _json(base, "/api/notes/" + str(note_id), WORKSPACE)
            if status != 200:
                raise RuntimeError("SYNTHETIC_NOTE_READ_FAILED")
            payload = {
                "note_id": note_id,
                "source_revision_id": created["revision_id"],
                "source_hash": source["sha256"],
                "extraction_id": created["extraction_id"],
                "expected_lock_version": 0,
                "event_kind": "review_completed",
                "item_decisions": _decisions(detail["extracted_json"]),
                "category_acknowledgments": {
                    "metadata": True, "vitals": True,
                    "instructions": True, "medications": True,
                },
                "idempotency_key": "synthetic-restart-review-once",
            }
            status, completed = _json(
                base, "/api/extractions/" + created["extraction_id"] + "/reviews",
                WORKSPACE, payload,
            )
            if status != 201 or completed["derived_outcome"] != "reviewed_unchanged":
                raise RuntimeError("SYNTHETIC_REVIEW_COMPLETION_FAILED")
            event_id = completed["event_id"]
        finally:
            _stop(process)

        # A genuinely new OS process reopens the same SQLite file, not a
        # test-client object reusing Python module state.
        port = _port()
        process, base = _start(port, url)
        try:
            status, after = _json(base, "/api/notes/" + str(note_id), WORKSPACE)
            if (status != 200 or after["review_head"]["event_id"] != event_id
                    or after["current_extraction_id"] != created["extraction_id"]
                    or after["current_source_revision_id"] != created["revision_id"]):
                raise RuntimeError("REVIEW_LOST_AFTER_PROCESS_RESTART")
            status, after_source = _json(base, "/api/notes/" + str(note_id) + "/source", WORKSPACE)
            if status != 200 or after_source["sha256"] != source["sha256"]:
                raise RuntimeError("SOURCE_CHANGED_AFTER_PROCESS_RESTART")
            status, events = _json(base, "/api/notes/" + str(note_id) + "/review-events", WORKSPACE)
            if status != 200 or len(events) != 1 or events[0]["id"] != event_id:
                raise RuntimeError("REVIEW_EVENT_HISTORY_CHANGED")
            status, metrics = _json(base, "/api/metrics", WORKSPACE)
            by_status = metrics.get("db_stats", {}).get("by_status", []) if status == 200 else []
            if not any(row.get("status") == "reviewed_unchanged" and row.get("count") == 1
                       for row in by_status):
                raise RuntimeError("CURRENT_REVIEW_METRICS_CHANGED")
            status, queue = _json(base, "/api/queue", WORKSPACE)
            if status != 200 or queue.get("count") != 0:
                raise RuntimeError("COMPLETED_REVIEW_RETURNED_TO_QUEUE")
            unauthorized, _ = _json(base, "/api/notes/" + str(note_id), "other-synthetic-workspace")
            if unauthorized not in (403, 404):
                raise RuntimeError("CROSS_WORKSPACE_READ_SUCCEEDED")
        finally:
            _stop(process)

    return {
        "status": "passed_real_process_restart",
        "synthetic_only": True,
        "processes": 2,
        "review_events": 1,
        "same_source_hash": True,
        "same_extraction": True,
        "current_metrics_preserved": True,
        "workspace_isolation_preserved": True,
        "database": "disposable_sqlite",
    }


def main():
    try:
        result = verify()
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        code = str(exc)
        if not (code.isupper() and "_" in code):
            code = "SYNTHETIC_RESTART_CHECK_FAILED"
        print(json.dumps({"status": "failed", "code": code}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
