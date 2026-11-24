#!/usr/bin/env bash
# Development: backend with auto-reload on :8420 + Vite dev server on :5173 (proxies /api).
set -euo pipefail
cd "$(dirname "$0")/.."
. scripts/_env.sh
.venv/bin/python -m uvicorn --app-dir backend app.main:create_app --factory --reload --reload-dir backend \
  --host 127.0.0.1 --port "${CS_PORT:-8420}" &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT INT TERM
(cd frontend && CS_BACKEND_URL="http://127.0.0.1:${CS_PORT:-8420}" npm run dev)
