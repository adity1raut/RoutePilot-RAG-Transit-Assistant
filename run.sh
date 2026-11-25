#!/usr/bin/env bash
# Start RoutePilot: builds the frontend if needed, then serves API + UI on http://localhost:8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "Backend not installed. See README.md > Setup." >&2
  exit 1
fi

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "Building frontend..."
  (cd "$ROOT/frontend" && npm install --no-fund --no-audit && npm run build)
fi

cd "$ROOT/backend"
echo "RoutePilot running at http://localhost:${PORT:-8000}"
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
