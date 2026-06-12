#!/bin/bash
# PolarPrivate (PrivPortal) 常驻启动脚本
# 功能: 版本检查 → 依赖更新 → 数据库迁移 → 启动 API 服务器
# 由 launchd 调用，也可手动执行

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$DIR/backend"
LOG_PREFIX="[privportal]"

log() { echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') $*"; }

# ── 版本检查与自动更新 ──────────────────────────

cd "$DIR"

log "检查版本更新..."
git fetch origin main --quiet 2>/dev/null || {
  log "⚠️  git fetch 失败（网络问题？），使用当前版本继续"
}

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")

if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
  DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [ "$DIRTY" -eq 0 ]; then
    log "发现新版本，正在更新..."
    git pull origin main --quiet
    log "更新依赖..."
    cd "$BACKEND_DIR" && uv sync --quiet 2>/dev/null
    cd "$DIR"
    log "✅ 已更新到最新版本"
  else
    log "⚠️  有 $DIRTY 个未提交文件，跳过自动更新"
  fi
else
  log "✅ 已是最新版本"
fi

# ── 确保虚拟环境已安装 ──────────────────────────

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  log "安装后端依赖..."
  uv sync 2>/dev/null
fi

# ── 数据库迁移 ───────────────────────────────────

log "检查数据库迁移..."
.venv/bin/privportal init-db 2>/dev/null || log "⚠️  数据库迁移跳过"

# ── 启动 API 服务器 ─────────────────────────────

log "启动 PrivPortal API 服务器 (port 12790)..."
exec .venv/bin/privportal start
