#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
POLARPROCESS_URL=${POLARPROCESS_URL:-http://127.0.0.1:11055}
POLARPORT_URL=${POLARPORT_URL:-http://127.0.0.1:11050}

reserve_port() {
  local service_name=$1 preferred_port=$2
  curl -fsS -X POST "$POLARPORT_URL/api/ports/reserve" \
    -H 'Content-Type: application/json' \
    -d "{\"service_name\":\"$service_name\",\"project\":\"PolarPrivate\",\"preferred_port\":$preferred_port}"
  printf '\n'
}

register_service() {
  local id=$1 name=$2 command=$3 port=$4 health_url=$5
  local payload
  payload=$(jq -n \
    --arg id "$id" \
    --arg name "$name" \
    --arg command "$command" \
    --arg work_dir "$PROJECT_DIR" \
    --arg health_check_url "$health_url" \
    --argjson port "$port" \
    '{
      id: $id,
      name: $name,
      command: $command,
      work_dir: $work_dir,
      device_id: "any",
      auto_start: true,
      restart_on_failure: true,
      max_restarts: 10,
      port: $port,
      health_check_url: $health_check_url,
      start_script_dir: "-"
    }')

  curl -fsS -X POST "$POLARPROCESS_URL/api/services/register" \
    -H 'Content-Type: application/json' \
    -d "$payload"
  printf '\n'
}

curl -fsS --max-time 3 "$POLARPORT_URL/api/health" >/dev/null
curl -fsS --max-time 3 "$POLARPROCESS_URL/api/health" >/dev/null

# Dedicated identity migration: replace only PolarPrivate's two legacy
# preferred-port reservations. This does not release an active port or perform
# a service lifecycle action.
curl -fsS -X DELETE "$POLARPORT_URL/api/ports/reserve/polarprivate/PolarPrivate" >/dev/null
curl -fsS -X DELETE "$POLARPORT_URL/api/ports/reserve/polarprivate-frontend/PolarPrivate" >/dev/null
reserve_port privportal-backend 12790
reserve_port privportal-frontend 12795

register_service \
  privportal-backend \
  "PolarPrivate Backend" \
  "bash Start/backend.sh" \
  12790 \
  "http://127.0.0.1:12790/health"
register_service \
  privportal-frontend \
  "PolarPrivate Frontend" \
  "bash Start/frontend.sh" \
  12795 \
  "http://127.0.0.1:12795/"
