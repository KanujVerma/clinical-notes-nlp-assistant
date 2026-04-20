#!/bin/bash
set -e
echo "=== startup: PORT=${PORT} WORKERS=1 ==="
echo "=== python: $(python --version 2>&1) ==="
echo "=== gunicorn: $(gunicorn --version 2>&1) ==="
exec gunicorn "app:create_app()" \
    --bind "0.0.0.0:${PORT}" \
    --workers 1 \
    --timeout 120 \
    --log-level info \
    --capture-output
