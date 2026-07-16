#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_contains() {
  local file=$1 text=$2
  grep -Fq "$text" "$file" || fail "$file does not contain $text"
}

assert_not_contains() {
  local file=$1 pattern=$2
  if grep -En "$pattern" "$file"; then
    fail "$file contains forbidden runtime behavior"
  fi
}

for launcher in "$ROOT/Start/backend.sh" "$ROOT/Start/frontend.sh"; do
  [ -x "$launcher" ] || fail "$launcher must exist and be executable"
  assert_contains "$launcher" '127.0.0.1:11050'
  assert_contains "$launcher" '/api/health'
  assert_contains "$launcher" 'port-claim.sh'
  assert_contains "$launcher" 'claim_port'
  assert_contains "$launcher" 'release_port'
  assert_contains "$launcher" 'exec '
  assert_not_contains "$launcher" '(^|[[:space:]])(nohup|disown|pkill|killall|kill|lsof)([[:space:]]|$)|PID_FILE|[^&]&[[:space:]]*$'
done

assert_contains "$ROOT/Start/backend.sh" 'claim_port "privportal-backend" "PolarPrivate" 12790'
assert_contains "$ROOT/Start/backend.sh" 'PRIVPORTAL_API_PORT=$PORT'
assert_contains "$ROOT/Start/frontend.sh" 'claim_port "privportal-frontend" "PolarPrivate" 12795'
assert_contains "$ROOT/Start/frontend.sh" 'service_name") == "privportal-backend"'
assert_contains "$ROOT/Start/frontend.sh" 'POLARPRIVATE_BACKEND_URL'

assert_contains "$ROOT/frontend/vite.config.ts" 'POLARPRIVATE_FRONTEND_PORT'
assert_contains "$ROOT/frontend/vite.config.ts" 'POLARPRIVATE_BACKEND_URL'
assert_not_contains "$ROOT/frontend/vite.config.ts" 'port: 12795'
assert_not_contains "$ROOT/frontend/vite.config.ts" 'target: "http://127.0.0.1:12790"'

assert_contains "$ROOT/scripts/register-runtime.sh" 'start_script_dir: "-"'
assert_contains "$ROOT/scripts/register-runtime.sh" '127.0.0.1:11050'
assert_contains "$ROOT/scripts/register-runtime.sh" '/api/ports/reserve'
assert_contains "$ROOT/scripts/register-runtime.sh" '/api/ports/reserve/polarprivate/PolarPrivate'
assert_contains "$ROOT/scripts/register-runtime.sh" '/api/ports/reserve/polarprivate-frontend/PolarPrivate'
assert_contains "$ROOT/scripts/register-runtime.sh" 'privportal-backend'
assert_contains "$ROOT/scripts/register-runtime.sh" 'privportal-frontend'
assert_not_contains "$ROOT/scripts/register-runtime.sh" 'api/services/.*/(start|stop|restart)'
assert_not_contains "$ROOT/scripts/register-runtime.sh" 'command:.*--port'

for client in \
  "$ROOT/backend/Start/start.sh" \
  "$ROOT/backend/Start/stop.sh" \
  "$ROOT/backend/Start/restart.sh"; do
  assert_contains "$client" 'privportal-backend'
  assert_contains "$client" '127.0.0.1:11055'
  assert_not_contains "$client" '(^|[[:space:]])(nohup|disown|pkill|killall|kill|lsof)([[:space:]]|$)|PID_FILE|[^&]&[[:space:]]*$'
done

jq -e '
  .service_management.service_id == "privportal-backend" and
  .service_management.start_command == "bash Start/backend.sh" and
  .service_management.auto_start == true and
  (.service_management.services | length) == 2 and
  ([.service_management.services[] | .service_id] | sort) == ["privportal-backend", "privportal-frontend"] and
  ([.service_management.services[] | .preferred_port] | sort) == [12790, 12795] and
  ([.service_management.services[] | .auto_start] == [true, true])
' "$ROOT/polaris.json" >/dev/null || fail "polaris.json does not declare both governed services"

jq -e '
  .requirements[]
  | select(.id == "R10")
  | .features[]
  | select(.name == "runtime_governance")
  | .status == "in-progress" or .status == "tested" or .status == "done"
' "$ROOT/polaris.json" >/dev/null || fail "runtime_governance SSoT is missing"

printf 'PolarPrivate runtime governance contract passed\n'
