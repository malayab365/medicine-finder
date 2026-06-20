#!/usr/bin/env bash
#
# Start the Medicine Search app.
#
#   ./start.sh                 # run on http://127.0.0.1:8000 with auto-reload
#   HOST=0.0.0.0 PORT=9000 ./start.sh
#   ./start.sh --no-reload     # run without the reloader (closer to production)
#
# On first run it creates a .venv, installs dependencies, and seeds .env from
# .env.example. Symptom search needs OPENROUTER_API_KEY set in .env.

set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="--reload"
if [[ "${1:-}" == "--no-reload" ]]; then
  RELOAD=""
fi

# 1. Virtual environment + dependencies (only set up once).
if [[ ! -d .venv ]]; then
  echo "==> Creating virtual environment (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import uvicorn" >/dev/null 2>&1; then
  echo "==> Installing dependencies"
  pip install --quiet --upgrade pip
  pip install --quiet -e ".[dev]"
fi

# 2. Environment file.
if [[ ! -f .env ]]; then
  echo "==> No .env found; creating one from .env.example"
  cp .env.example .env
fi

if ! grep -qE '^OPENROUTER_API_KEY=.+' .env; then
  echo "!!  OPENROUTER_API_KEY is not set in .env — name search works, but"
  echo "!!  symptom search will fail until you add a key."
fi

# 3. Launch.
echo "==> Starting on http://${HOST}:${PORT} (Ctrl-C to stop)"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" ${RELOAD}
