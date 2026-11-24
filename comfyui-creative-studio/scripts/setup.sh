#!/usr/bin/env bash
# One-time setup: Python venv + backend deps, frontend deps + production build.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"' \
  || { echo "Python 3.10+ is required (found: $($PY --version 2>&1))"; exit 1; }
command -v npm >/dev/null || { echo "Node.js 18+ (npm) is required: https://nodejs.org or 'brew install node'"; exit 1; }

echo "→ Python virtualenv (.venv)"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r backend/requirements-dev.txt

echo "→ Frontend dependencies and build"
(cd frontend && npm ci && npm run build)

[ -f .env ] || { cp .env.example .env; echo "→ Created .env from .env.example"; }
echo
echo "Done. Start the app with:  ./scripts/start.sh"
echo "Install the ComfyUI nodes:  ./scripts/install_nodes.sh /path/to/ComfyUI"
