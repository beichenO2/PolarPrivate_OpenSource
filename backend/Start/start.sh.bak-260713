#!/usr/bin/env bash
# PolarPrivate backend lifecycle — PolarProcess + launchd compatible.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$SCRIPT_DIR/.pid"
SERVICE_NAME="polarprivate"
PROJECT="PolarPrivate"
PREFERRED_PORT=12790
VENV="$PROJECT_DIR/.venv/bin/privportal"

cd "$PROJECT_DIR"

source "$PROJECT_DIR/../../Agent_core/scripts/port-claim.sh"
PORT=$(claim_port "$SERVICE_NAME" "$PROJECT" "$PREFERRED_PORT")
HEALTH_URL="http://127.0.0.1:${PORT}/health"
LOG_FILE="$SCRIPT_DIR/polarprivate-backend.log"
mkdir -p "$SCRIPT_DIR"

do_start() {
  if [ ! -x "$VENV" ]; then
    echo "Missing venv at $VENV — run: cd backend && pip install -e ." >&2
    exit 1
  fi

  OCCUPANT_PID=$(lsof -iTCP:"$PORT" -sTCP:LISTEN -P -n -t 2>/dev/null | head -1 || true)
  if [ -n "$OCCUPANT_PID" ]; then
    echo "Already running pid=$OCCUPANT_PID port=$PORT"
    exit 0
  fi

  if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
      echo "Already running pid=$OLD_PID port=$PORT"
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  export PRIVPORTAL_API_HOST=127.0.0.1
  export PRIVPORTAL_API_PORT="$PORT"

  if [ "${LAUNCHD:-}" = "1" ]; then
    exec "$VENV" start >> "$LOG_FILE" 2>&1
  fi

  nohup "$VENV" start >> "$LOG_FILE" 2>&1 &
  DAEMON_PID=$!
  echo "$DAEMON_PID" > "$PID_FILE"

  for i in $(seq 1 30); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
      echo "Started pid=$DAEMON_PID port=$PORT"
      exit 0
    fi
    if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
      echo "Process exited immediately" >&2
      tail -20 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      exit 1
    fi
    sleep 1
  done

  echo "Timed out waiting for health endpoint on port $PORT" >&2
  rm -f "$PID_FILE"
  exit 1
}

do_stop() {
  local pids=""
  if [ -f "$PID_FILE" ]; then pids="$(cat "$PID_FILE" 2>/dev/null || true)"; fi
  pids="$pids $(lsof -iTCP:"$PORT" -sTCP:LISTEN -P -n -t 2>/dev/null || true)"
  pids=$(printf '%s\n' $pids | grep -E '^[0-9]+$' | sort -u || true)

  if [ -z "$pids" ]; then
    echo "Not running"
    rm -f "$PID_FILE"
    exit 0
  fi

  for p in $pids; do kill "$p" 2>/dev/null || true; done
  for i in $(seq 1 10); do
    local alive=""
    for p in $pids; do kill -0 "$p" 2>/dev/null && alive="$alive $p"; done
    [ -z "$alive" ] && break
    sleep 1
  done
  for p in $pids; do kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true; done
  rm -f "$PID_FILE"
  echo "Stopped"
}

do_restart() { do_stop; do_start; }

do_status() {
  local pid=""
  if [ -f "$PID_FILE" ]; then pid=$(cat "$PID_FILE" 2>/dev/null || true); fi
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "Running pid=$pid port=$PORT"
    exit 0
  fi
  local occ
  occ=$(lsof -iTCP:"$PORT" -sTCP:LISTEN -P -n -t 2>/dev/null | head -1 || true)
  if [ -n "$occ" ]; then
    echo "Running pid=$occ port=$PORT (PID file stale)"
    echo "$occ" > "$PID_FILE"
    exit 0
  fi
  echo "Not running"
  exit 1
}

case "${1:-start}" in
  start)   do_start   ;;
  stop)    do_stop    ;;
  restart) do_restart ;;
  status)  do_status  ;;
  *)
    echo "Usage: bash Start/start.sh [start|stop|restart|status]" >&2
    exit 1
    ;;
esac
