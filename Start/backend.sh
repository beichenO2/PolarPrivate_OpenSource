#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
POLARPORT_URL=${POLARPORT_URL:-http://127.0.0.1:11050}
PREFERRED_PORT=12790
UVICORN_BIN="$PROJECT_DIR/backend/.venv/bin/uvicorn"

if [ "$#" -ne 0 ]; then
  echo "PolarPrivate Backend lifecycle is managed by PolarProcess; do not pass lifecycle arguments" >&2
  exit 2
fi

if [ ! -x "$UVICORN_BIN" ]; then
  echo "Backend dependencies are not installed; run pip install -r backend/requirements.txt" >&2
  exit 1
fi

if ! curl -fsS --max-time 3 "$POLARPORT_URL/api/health" >/dev/null; then
  echo "PolarPort is unavailable; refusing preferred-port fallback" >&2
  exit 1
fi

source "$HOME/Polarisor/Agent_core/scripts/port-claim.sh"
PORT=$(claim_port "privportal-backend" "PolarPrivate" 12790)

if [ "$PORT" -ne "$PREFERRED_PORT" ]; then
  release_port "$PORT"
  echo "PolarPort returned $PORT, but PolarPrivate Backend SSoT requires preferred port $PREFERRED_PORT" >&2
  exit 1
fi

cd "$PROJECT_DIR/backend"
export PRIVPORTAL_API_HOST=127.0.0.1
export PRIVPORTAL_API_PORT=$PORT
export CLOUD_EMBED_MODEL="${CLOUD_EMBED_MODEL:-qwen3.7-text-embedding}"
exec "$UVICORN_BIN" app.main:app --host "$PRIVPORTAL_API_HOST" --port "$PRIVPORTAL_API_PORT"
