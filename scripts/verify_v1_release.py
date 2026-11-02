#!/usr/bin/env python3
"""Coordinate the offline v1 release checks and write a verification summary.

Reuses the existing test commands. A required check that is skipped or
missing fails the gate. Browser checks run when --with-browser is set.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _python() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.is_file() else Path(sys.executable))


def _run(name: str, command: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    print(f"\n== {name} ==\n$ {' '.join(command)}", flush=True)
    merged = os.environ.copy()
    merged.setdefault("APP_MODE", "local")
    merged.setdefault("ENABLE_LOCAL_AI", "false")
    merged.setdefault("ENABLE_EXTERNAL_EXPLAINER", "false")
    if env:
        merged.update(env)
    t0 = time.monotonic()
    completed = subprocess.run(command, cwd=cwd or ROOT, env=merged, text=True)
    record = {
        "name": name,
        "command": command,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - t0, 2),
        "exit_code": completed.returncode,
    }
    print(f"-- {name} exit {completed.returncode}", flush=True)
    return record


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _benchmark_replay(python: str) -> dict:
    script = r"""
from pathlib import Path
import base64, hashlib, zipfile
src = Path('docs/validation/evidence/PR8_REAL_BENCHMARK_EVIDENCE.zip.base64.txt')
payload = base64.b64decode(src.read_text(encoding='ascii').strip(), validate=True)
expected = 'd073a12c5f9f7b9ff2a3cb406a5d4c06e50c7812f4ddda43e72001007a73a80d'
digest = hashlib.sha256(payload).hexdigest()
if digest != expected:
    raise SystemExit(f'ZIP_SHA_MISMATCH {digest}')
out = Path('artifacts/verification') / 'pr8_real_vision_benchmark_evidence_verified.zip'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(payload)
with zipfile.ZipFile(out) as archive:
    bad = archive.testzip()
    if bad is not None:
        raise SystemExit(f'ZIP_MEMBER_CORRUPT {bad}')
print('ORIGINAL_EVIDENCE_VERIFIED', expected)
"""
    return _run("frozen_benchmark_archive", [python, "-c", script])


def _ensure_browser_servers(python: str) -> list[subprocess.Popen]:
    busy = [port for port in (5000, 5173) if _port_open(port)]
    if busy:
        listed = ", ".join(str(port) for port in busy)
        raise SystemExit(
            f"Ports {listed} are already in use. Stop those listeners so browser "
            "verification starts this checkout's Flask and Vite. Reusing another "
            "checkout's servers would label their result with this head."
        )
    logs = ROOT / "artifacts" / "verification"
    logs.mkdir(parents=True, exist_ok=True)
    db = logs / "verify-browser.sqlite"
    if db.exists():
        db.unlink()
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{db}",
        "APP_MODE": "local",
        "ENABLE_LOCAL_AI": "false",
        "ENABLE_EXTERNAL_EXPLAINER": "false",
    })
    backend_log = open(logs / "verify-backend.log", "w", encoding="utf-8")
    frontend_log = open(logs / "verify-frontend.log", "w", encoding="utf-8")
    backend = subprocess.Popen(
        [python, "backend/app.py"], cwd=ROOT, env=env,
        stdout=backend_log, stderr=subprocess.STDOUT,
    )
    frontend = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=ROOT / "frontend", env=env,
        stdout=frontend_log, stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        if _port_open(5000) and _port_open(5173):
            return [backend, frontend]
        if backend.poll() is not None or frontend.poll() is not None:
            break
        time.sleep(2)
    backend.terminate()
    frontend.terminate()
    raise SystemExit("Flask or Vite did not become ready for browser checks")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-browser", action="store_true")
    args = parser.parse_args()
    python = _python()
    probe = subprocess.run(
        [python, "-c", "import PIL; print(PIL.__version__)"],
        cwd=ROOT, text=True, capture_output=True,
    )
    if probe.stdout.strip() != "10.4.0":
        raise SystemExit(
            "Pillow 10.4.0 is required to reproduce the frozen image bytes. "
            "requirements.txt is hash-frozen at pillow>=10, so install the pin separately: "
            "python -m pip install 'pillow==10.4.0'"
        )
    head = _sha()
    summary_dir = ROOT / "artifacts" / "verification" / f"v1-release-{head}"
    summary_dir.mkdir(parents=True, exist_ok=True)
    checks = [
        _run("backend", [python, "-m", "pytest", "backend/tests/", "-q", "--tb=line"]),
        _run(
            "postgres",
            [python, "-m", "pytest", "backend/tests/test_postgres_concurrency.py", "-q", "--tb=short"],
            env={"REQUIRE_POSTGRES": "1"},
        ),
        _run("frontend", ["npm", "test", "--prefix", "frontend", "--", "--run"]),
        _run("lint", ["npm", "run", "lint", "--prefix", "frontend"]),
        _run("build", ["npm", "run", "build", "--prefix", "frontend"]),
        _run("restart_persistence", [python, "scripts/check_restart_persistence.py"]),
        _benchmark_replay(python),
    ]
    started_servers: list[subprocess.Popen] = []
    if args.with_browser:
        started_servers = _ensure_browser_servers(python)
        checks.append(_run(
            "playwright",
            ["npx", "playwright", "test", "--workers=1", "--reporter=line"],
            env={"CI": "true"},
            cwd=ROOT / "frontend",
        ))
        for proc in started_servers:
            proc.terminate()
    failed = [item["name"] for item in checks if item["exit_code"] != 0]
    summary = {
        "head": head,
        "started_at": checks[0]["started_at"],
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "python": python,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "node": shutil.which("node"),
        "checks": checks,
        "failed": failed,
        "release_gate": "fail" if failed else "pass",
    }
    target = summary_dir / "summary.json"
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nWROTE {target}")
    print("RELEASE_GATE", summary["release_gate"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
