#!/usr/bin/env bash
# Static OSS packaging checks — does not start services or docker compose up.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    fail "missing required file: $path"
  fi
  pass "found $path"
}

require_file "Dockerfile"
require_file "docker-compose.yml"
require_file "SECURITY.md"
require_file ".dockerignore"

if ! grep -q '127\.0\.0\.1:12790' docker-compose.yml; then
  fail "docker-compose.yml must bind 127.0.0.1:12790"
fi
pass "docker-compose.yml binds 127.0.0.1:12790"

if grep -q '0\.0\.0\.0' docker-compose.yml; then
  fail "docker-compose.yml must not expose 0.0.0.0"
fi
pass "docker-compose.yml has no 0.0.0.0 binding"

if ! grep -q 'PolarPrivate_OpenSource' README.md; then
  fail "README.md must reference clone URL PolarPrivate_OpenSource"
fi
pass "README.md references PolarPrivate_OpenSource"

# Independent install section must not recommend privportal start as the primary path.
indep_section="$(awk '/^### 独立安装/{flag=1;next} /^### /{flag=0} flag' README.md)"
if [[ -z "$indep_section" ]]; then
  fail "README.md missing ### 独立安装 section"
fi
if echo "$indep_section" | grep -q 'privportal start'; then
  fail "独立安装 section must not use privportal start (PolarProcess-only)"
fi
pass "README 独立安装 section avoids privportal start"

if ! grep -Eiq 'localhost|127\.0\.0\.1|本地主机' SECURITY.md; then
  fail "SECURITY.md must discuss localhost trust boundary"
fi
if ! grep -Eiq 'rebind|rebinding|DNS.?rebind|重绑定' SECURITY.md; then
  fail "SECURITY.md must discuss DNS rebinding"
fi
pass "SECURITY.md covers localhost and DNS rebinding"

if command -v docker >/dev/null 2>&1; then
  docker compose -f docker-compose.yml config >/dev/null
  pass "docker compose config succeeded"
else
  echo "SKIP: docker not available — compose config not validated"
fi

echo "smoke-opensource: all checks passed"
