#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
POLARPORT_URL=${POLARPORT_URL:-http://127.0.0.1:11050}
PREFERRED_PORT=12795
NODE_BIN=${NODE_BIN:-/opt/homebrew/bin/node}
VITE_BIN="$PROJECT_DIR/frontend/node_modules/vite/bin/vite.js"

if [ "$#" -ne 0 ]; then
  echo "PolarPrivate Frontend lifecycle is managed by PolarProcess; do not pass lifecycle arguments" >&2
  exit 2
fi

if [ ! -x "$NODE_BIN" ]; then
  NODE_BIN=$(command -v node || true)
fi
if [ -z "$NODE_BIN" ] || [ ! -x "$NODE_BIN" ]; then
  echo "Node executable not found" >&2
  exit 1
fi
if [ ! -f "$VITE_BIN" ]; then
  echo "Frontend dependencies are not installed; run npm ci in frontend" >&2
  exit 1
fi

if ! curl -fsS --max-time 3 "$POLARPORT_URL/api/health" >/dev/null; then
  echo "PolarPort is unavailable; refusing preferred-port fallback" >&2
  exit 1
fi

source "$HOME/Polarisor/Agent_core/scripts/port-claim.sh"
PORT=$(claim_port "privportal-frontend" "PolarPrivate" 12795)

if [ "$PORT" -ne "$PREFERRED_PORT" ]; then
  release_port "$PORT"
  echo "PolarPort returned $PORT, but PolarPrivate Frontend SSoT requires preferred port $PREFERRED_PORT" >&2
  exit 1
fi

BACKEND_PORT=$(curl -fsS --max-time 3 "$POLARPORT_URL/api/list" | python3 -c '
import json, sys
ports = json.load(sys.stdin)
matches = [p["port"] for p in ports if p.get("service_name") == "privportal-backend" and p.get("project") == "PolarPrivate" and p.get("status") == "active"]
if len(matches) != 1:
    raise SystemExit(1)
print(matches[0])
') || {
  release_port "$PORT"
  echo "PolarPrivate Backend has no unique active PolarPort record; refusing an unmanaged proxy target" >&2
  exit 1
}

cd "$PROJECT_DIR/frontend"
export POLARPRIVATE_FRONTEND_PORT=$PORT
export POLARPRIVATE_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
exec "$NODE_BIN" "$VITE_BIN" --host 127.0.0.1 --port "$PORT" --strictPort
