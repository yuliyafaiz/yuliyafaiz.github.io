#!/usr/bin/env bash
# Start Creative Studio (backend serves the built frontend) on http://127.0.0.1:8420
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] || { echo "Run ./scripts/setup.sh first"; exit 1; }
[ -f frontend/dist/index.html ] || (cd frontend && npm run build)
set -a; [ -f .env ] && . ./.env; set +a
HOST="${CS_HOST:-127.0.0.1}"; PORT="${CS_PORT:-8420}"
echo "Creative Studio → http://$HOST:$PORT   (ComfyUI: ${CS_COMFY_URL:-http://127.0.0.1:8188})"
exec .venv/bin/python -m uvicorn --app-dir backend app.main:create_app --factory --host "$HOST" --port "$PORT"
