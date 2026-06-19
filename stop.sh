#!/usr/bin/env bash
#
# Stop the Medicine Search app (any uvicorn process running app.main:app).
#
#   ./stop.sh
#
# Sends SIGTERM for a graceful shutdown, waits, then escalates to SIGKILL if
# anything is still alive. Safe to run when the app isn't running.

set -uo pipefail

PATTERN="uvicorn app.main:app"

if ! pgrep -f "$PATTERN" >/dev/null 2>&1; then
  echo "==> Not running (no '$PATTERN' process found)"
  exit 0
fi

echo "==> Stopping:"
pgrep -fl "$PATTERN"

pkill -f "$PATTERN"

# Give it a few seconds to shut down gracefully.
for _ in 1 2 3 4 5; do
  pgrep -f "$PATTERN" >/dev/null 2>&1 || break
  sleep 1
done

# Escalate if anything survived.
if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  echo "!!  Did not exit gracefully; forcing (SIGKILL)"
  pkill -9 -f "$PATTERN"
  sleep 1
fi

if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  echo "!!  Still running — check 'pgrep -fl \"$PATTERN\"'"
  exit 1
fi

echo "==> Stopped"
