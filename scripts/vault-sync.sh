#!/usr/bin/env bash
# PolarPrivate Vault Sync — automated backup/restore via git
#
# Usage:
#   vault-sync.sh backup    — export encrypted backup + git push
#   vault-sync.sh restore   — git pull + import backup into local vault
#   vault-sync.sh setup     — store Master Password in macOS Keychain
#
# Prerequisites:
#   - PolarPrivate backend running and vault unlocked
#   - git configured with push access to the PolarPrivate repo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYNC_DIR="$PROJECT_DIR/sync"
BACKUP_FILE="$SYNC_DIR/vault-backup.json"
API_BASE="${PRIVPORTAL_API_BASE:-http://127.0.0.1:12790}"
KEYCHAIN_SERVICE="com.privportal.master-password"
KEYCHAIN_ACCOUNT="privportal"

log() { echo "[vault-sync] $(date +%H:%M:%S) $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

get_master_password() {
  security find-generic-password \
    -s "$KEYCHAIN_SERVICE" \
    -a "$KEYCHAIN_ACCOUNT" \
    -w 2>/dev/null || true
}

check_vault_health() {
  local status
  status=$(curl -sf "$API_BASE/health" 2>/dev/null || echo '{}')
  local unlocked
  unlocked=$(echo "$status" | python3 -c "import json,sys; print(json.load(sys.stdin).get('vault_unlocked', False))" 2>/dev/null || echo "False")
  [ "$unlocked" = "True" ]
}

cmd_setup() {
  log "Storing Master Password in macOS Keychain..."
  log "(This password never leaves your Mac — stored in the Secure Enclave)"
  echo -n "Enter Master Password: "
  read -rs pw
  echo
  if [ ${#pw} -lt 8 ]; then
    die "Password must be at least 8 characters"
  fi
  security delete-generic-password \
    -s "$KEYCHAIN_SERVICE" \
    -a "$KEYCHAIN_ACCOUNT" 2>/dev/null || true
  security add-generic-password \
    -s "$KEYCHAIN_SERVICE" \
    -a "$KEYCHAIN_ACCOUNT" \
    -w "$pw" \
    -T "" \
    -U
  log "Master Password stored in Keychain (service: $KEYCHAIN_SERVICE)"
}

cmd_backup() {
  log "Starting vault backup..."
  if ! check_vault_health; then
    log "Vault is locked — skipping backup (unlock at http://localhost:12795 to enable)"
    exit 0
  fi

  mkdir -p "$SYNC_DIR"
  local response
  response=$(curl -sf -X POST "$API_BASE/api/vault/backup" 2>/dev/null) || die "Backup API call failed"

  echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(json.dumps(data, indent=2))
" > "$BACKUP_FILE"

  local secret_count
  secret_count=$(echo "$response" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data.get('payload', '')))
" 2>/dev/null)
  log "Backup saved to $BACKUP_FILE ($secret_count chars encrypted)"

  cd "$PROJECT_DIR"
  if git diff --quiet sync/vault-backup.json 2>/dev/null; then
    log "No changes since last backup — skipping git push"
    return 0
  fi

  git add sync/vault-backup.json
  git commit -m "chore: vault backup $(date +%Y-%m-%d-%H%M)" --no-verify 2>/dev/null
  log "Committed. Pushing..."
  
  local retries=3
  while [ $retries -gt 0 ]; do
    if git push origin HEAD 2>&1; then
      log "Pushed to GitHub successfully"
      return 0
    fi
    retries=$((retries - 1))
    [ $retries -gt 0 ] && { log "Push failed, retrying in 5s..."; sleep 5; }
  done
  log "WARNING: git push failed after 3 attempts"
}

cmd_restore() {
  log "Starting vault restore..."
  
  cd "$PROJECT_DIR"
  log "Pulling latest from GitHub..."
  git pull --ff-only origin main 2>/dev/null || git pull origin main 2>/dev/null || log "WARNING: git pull failed"

  [ -f "$BACKUP_FILE" ] || die "No backup file found at $BACKUP_FILE"

  check_vault_health || die "Vault is not unlocked. Open http://localhost:12795 and unlock first."

  local master_pw
  master_pw=$(get_master_password)
  if [ -z "$master_pw" ]; then
    log "Master Password not in Keychain. Run: vault-sync.sh setup"
    echo -n "Enter source device Master Password: "
    read -rs master_pw
    echo
  fi

  python3 "$SCRIPT_DIR/vault-restore-helper.py" "$BACKUP_FILE" "$master_pw" "$API_BASE" \
    || die "Restore failed — wrong password or API error"

  log "Restore complete"
}

case "${1:-help}" in
  backup)  cmd_backup ;;
  restore) cmd_restore ;;
  setup)   cmd_setup ;;
  *)
    echo "Usage: vault-sync.sh {backup|restore|setup}"
    echo ""
    echo "  setup    — Store Master Password in macOS Keychain"
    echo "  backup   — Export encrypted backup + git push"
    echo "  restore  — git pull + import from backup"
    exit 1
    ;;
esac
