#!/usr/bin/env bash
# Start the hub on the middle server (DD-0015).
# Side Effects: listens on 127.0.0.1:${PORT}; writes logs/.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"

if command -v tailscale >/dev/null 2>&1; then
  if ! tailscale serve status 2>/dev/null | grep -q "${PORT}"; then
    echo "[hint] HTTPS is not served yet. Run once:  tailscale serve --bg ${PORT}"
  fi
fi

exec uv run python -m nasura_comm.hub --port "${PORT}" "$@"
