#!/usr/bin/env bash
# test-qcsa-routing.sh — Automated QCSA routing smoke test
# Verifies every QCSA capability code in CAPABILITY_CLOUD_MAP is accepted
# by PolarPrivate and returns a valid chat completion response.
#
# Usage:
#   bash scripts/test-qcsa-routing.sh              # default: http://127.0.0.1:12790
#   bash scripts/test-qcsa-routing.sh <base_url>   # custom endpoint
#   PP_MAX_TOKENS=5 bash scripts/test-qcsa-routing.sh  # override max_tokens

set -uo pipefail

BASE_URL="${1:-http://127.0.0.1:12790}"
ENDPOINT="$BASE_URL/v1/chat/completions"
MAX_TOKENS="${PP_MAX_TOKENS:-5}"
TIMEOUT=30

TEXT_CODES=(
  "0000"  # 默认均衡 (GLM-5.1)
  "0010"  # 快速 (DS V4 Flash)
  "0100"  # 长上下文 (DS V4 Pro)
  "0110"  # 快速+长上下文 (MiniMax-M3)
  "1000"  # 旗舰 (GLM-5.1)
  "1110"  # 推理 (M3-Thinking)
)

AGENT_CODES=(
  "0001"  # Agent 均衡 (DS V4 Flash, tool call)
  "0011"  # Agent 快速
  "0101"  # Agent 长上下文 (DS V4 Pro)
  "1001"  # Agent 旗舰 (DS V4 Pro)
  "1011"  # Agent 旗舰+快速
  "1101"  # Agent 旗舰+长上下文
)

VISION_CODES=(
  "V0000"  # 默认视觉 (qwen3.7)
  "V0010"  # 视觉快速 (vl-flash)
  "V1000"  # 视觉旗舰 (Kimi K2.6)
  "V0001"  # 视觉 Agent (K2.6)
  "V0101"  # 视觉 Agent 多图 (qwen3.7)
)

LOCAL_CODES=(
  "L0000"  # 本地推理
)

EMBED_CODES=(
  "E000"   # 嵌入
)

pass=0
fail=0
skip=0
warn=0
failed_codes=()
warned_codes=()

_inc_pass()  { pass=$((pass + 1)); }
_inc_fail()  { fail=$((fail + 1)); }
_inc_skip()  { skip=$((skip + 1)); }
_inc_warn()  { warn=$((warn + 1)); }

_test_code() {
  local code="$1"
  local category="$2"
  local body

  if [[ "$code" == E* ]]; then
    body=$(printf '{"model":"%s","input":"hello"}' "$code")
    local result
    result=$(curl -s --max-time "$TIMEOUT" -w "\n%{http_code}" \
      -X POST "$BASE_URL/v1/embeddings" \
      -H "Content-Type: application/json" \
      -d "$body" 2>&1) || true
    local http_code
    http_code=$(echo "$result" | tail -1)
    local resp_body
    resp_body=$(echo "$result" | sed '$d')

    printf "  %-8s %-20s " "$code" "($category)"
    if [[ "$http_code" =~ ^2 ]]; then
      printf "\033[32m✓ %s\033[0m\n" "$http_code"
      _inc_pass
    elif [[ "$http_code" == "000" ]]; then
      printf "\033[33m⊘ TIMEOUT/UNREACHABLE\033[0m\n"
      _inc_skip
    elif [[ "$http_code" == "422" ]]; then
      printf "\033[31m✗ %s ROUTING FAIL\033[0m\n" "$http_code"
      _inc_fail
      failed_codes+=("$code")
    else
      printf "\033[33m⚡ %s upstream\033[0m\n" "$http_code"
      _inc_warn
      warned_codes+=("$code")
    fi
    return
  fi

  if [[ "$code" == V* ]]; then
    body=$(printf '{"model":"%s","messages":[{"role":"user","content":[{"type":"text","text":"describe"},{"type":"image_url","image_url":{"url":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}}]}],"max_tokens":%d}' \
      "$code" "$MAX_TOKENS")
  elif [[ "$code" == L* ]]; then
    body=$(printf '{"model":"%s","messages":[{"role":"user","content":"hi"}],"max_tokens":%d}' \
      "$code" "$MAX_TOKENS")
  else
    body=$(printf '{"model":"%s","messages":[{"role":"user","content":"hi"}],"max_tokens":%d}' \
      "$code" "$MAX_TOKENS")
  fi

  local result
  result=$(curl -s --max-time "$TIMEOUT" -w "\n%{http_code}" \
    -X POST "$ENDPOINT" \
    -H "Content-Type: application/json" \
    -d "$body" 2>&1) || true

  local http_code
  http_code=$(echo "$result" | tail -1)
  local resp_body
  resp_body=$(echo "$result" | sed '$d')

  printf "  %-8s %-20s " "$code" "($category)"

  if [[ "$http_code" =~ ^2 ]]; then
    local has_choices
    has_choices=$(echo "$resp_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'choices' in d else 'no')" 2>/dev/null || echo "no")
    if [[ "$has_choices" == "yes" ]]; then
      printf "\033[32m✓ %s\033[0m\n" "$http_code"
      _inc_pass
    else
      printf "\033[33m⚠ %s (no choices)\033[0m\n" "$http_code"
      _inc_fail
      failed_codes+=("$code")
    fi
  elif [[ "$http_code" == "000" ]]; then
    printf "\033[33m⊘ TIMEOUT/UNREACHABLE\033[0m\n"
    _inc_skip
  elif [[ "$http_code" == "422" ]]; then
    local detail
    detail=$(echo "$resp_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',{}).get('code','') if isinstance(d.get('detail'),dict) else str(d.get('detail',''))[:80])" 2>/dev/null || echo "")
    printf "\033[31m✗ %s ROUTING FAIL\033[0m" "$http_code"
    [[ -n "$detail" ]] && printf " — %s" "$detail"
    printf "\n"
    _inc_fail
    failed_codes+=("$code")
  else
    local detail
    detail=$(echo "$resp_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',{}).get('code','') if isinstance(d.get('detail'),dict) else str(d.get('detail',''))[:80])" 2>/dev/null || echo "")
    printf "\033[33m⚡ %s upstream\033[0m" "$http_code"
    [[ -n "$detail" ]] && printf " — %s" "$detail"
    printf "\n"
    _inc_warn
    warned_codes+=("$code")
  fi
}

echo "╔══════════════════════════════════════════════════╗"
echo "║  PolarPrivate QCSA Routing Smoke Test            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Endpoint : $ENDPOINT"
echo "  Tokens   : $MAX_TOKENS"
echo ""

# Health check
printf "  Health check... "
health=$(curl -s --max-time 5 "$BASE_URL/health" 2>/dev/null || echo "")
if [[ -n "$health" ]]; then
  printf "\033[32mOK\033[0m\n\n"
else
  printf "\033[31mFAILED\033[0m (is PolarPrivate running on $BASE_URL?)\n"
  exit 1
fi

echo "── Text-only QCSA ──"
for code in "${TEXT_CODES[@]}"; do
  _test_code "$code" "text"
done

echo ""
echo "── Agentic QCSA ──"
for code in "${AGENT_CODES[@]}"; do
  _test_code "$code" "agent"
done

echo ""
echo "── Vision QCSA ──"
for code in "${VISION_CODES[@]}"; do
  _test_code "$code" "vision"
done

echo ""
echo "── Local / Embed ──"
for code in "${LOCAL_CODES[@]}"; do
  _test_code "$code" "local"
done
for code in "${EMBED_CODES[@]}"; do
  _test_code "$code" "embed"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
total=$((pass + fail + skip + warn))
printf "  Total: %d  |  \033[32mPass: %d\033[0m  |  \033[31mRoute Fail: %d\033[0m  |  \033[33mUpstream: %d\033[0m  |  Skip: %d\n" \
  "$total" "$pass" "$fail" "$warn" "$skip"

if [[ ${#failed_codes[@]} -gt 0 ]]; then
  printf "  Route failures: \033[31m%s\033[0m\n" "${failed_codes[*]}"
fi
if [[ ${#warned_codes[@]} -gt 0 ]]; then
  printf "  Upstream issues: \033[33m%s\033[0m (routed OK, upstream rejected)\n" "${warned_codes[*]}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ $fail -eq 0 ]] && exit 0 || exit 1
