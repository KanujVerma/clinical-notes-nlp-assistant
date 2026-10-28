#!/usr/bin/env bash
# Run the local synthetic workbench and its single durable AI/processing worker.
# No paid APIs, deployments, or model pulls are performed by this script.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Local Python environment missing: $PYTHON" >&2
  echo "Create .venv and install requirements.txt first." >&2
  exit 1
fi
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "Frontend dependencies missing. Run: cd frontend && npm ci" >&2
  exit 1
fi
export APP_MODE=local
export ENABLE_EXTERNAL_EXPLAINER=false
export PYTHONUNBUFFERED=1

"$PYTHON" backend/app.py &
api_pid=$!
"$PYTHON" backend/worker.py &
worker_pid=$!
(
  cd frontend
  npm run dev -- --host 127.0.0.1
) &
vite_pid=$!

cleanup() {
  trap - EXIT INT TERM
  kill "$api_pid" "$worker_pid" "$vite_pid" 2>/dev/null || true
  wait "$api_pid" "$worker_pid" "$vite_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Local synthetic workbench starting:"
echo "  Frontend: http://127.0.0.1:5173"
echo "  Flask:    http://127.0.0.1:5000"
echo "  Worker:   one process, persistent SQLite job queue"
echo "  Ollama:   optional at http://127.0.0.1:11434 (manual install/start)"
echo "Press Ctrl-C to stop all workbench services."
while kill -0 "$api_pid" 2>/dev/null &&
      kill -0 "$worker_pid" 2>/dev/null &&
      kill -0 "$vite_pid" 2>/dev/null; do
  sleep 1
done
echo "One or more workbench services exited; shutting down the others." >&2
exit 1
