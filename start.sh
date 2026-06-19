#!/usr/bin/env bash
#
# Start the whole app: FastAPI backend (:8000) + Next.js frontend (:3000).
#
#   ./start.sh                                  # run both, Ctrl-C stops both
#   BACKEND_PORT=9000 FRONTEND_PORT=4000 ./start.sh
#
# The backend's own start.sh handles its venv/.env on first run; this script
# installs frontend deps and seeds frontend/.env.local if needed. Symptom search
# needs OPENROUTER_API_KEY in backend/.env.

set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

pids=()
cleaned=0
cleanup() {
  [[ "${cleaned}" == "1" ]] && return
  cleaned=1
  echo ""
  echo "==> Shutting down…"
  for pid in "${pids[@]}"; do
    kill "${pid}" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# --- Backend -------------------------------------------------------------
echo "==> Starting backend on http://127.0.0.1:${BACKEND_PORT}"
( cd "${ROOT}/backend" && PORT="${BACKEND_PORT}" ./start.sh ) &
pids+=($!)

# --- Frontend ------------------------------------------------------------
cd "${ROOT}/frontend"
if [[ ! -d node_modules ]]; then
  echo "==> Installing frontend dependencies"
  npm install
fi
if [[ ! -f .env.local ]]; then
  echo "==> Seeding frontend/.env.local"
  cp .env.local.example .env.local
fi
echo "==> Starting frontend on http://localhost:${FRONTEND_PORT}"
BACKEND_URL="http://localhost:${BACKEND_PORT}" npm run dev -- --port "${FRONTEND_PORT}" &
pids+=($!)

cd "${ROOT}"
echo ""
echo "==> Up. Frontend: http://localhost:${FRONTEND_PORT}  ·  API: http://localhost:${BACKEND_PORT}"
echo "==> Press Ctrl-C to stop both."
wait
