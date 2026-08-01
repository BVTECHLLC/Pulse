#!/usr/bin/env bash
# BVTech OpsPilot — self-healing auto-deploy.
#
# Converges the running app to the latest main: it redeploys whenever new commits
# exist OR the running version != the committed version (so a half-failed deploy
# self-heals on the next run instead of wedging). Rebuilds ONLY the api service
# (never the proxy/db), logs every step, and never `set -e`-aborts mid-way.
#
# One-time install of the 2-minute poller (run as root on the server):
#   chmod +x /opt/bvtech-portal/opspilot/deploy.sh
#   ( crontab -l 2>/dev/null | grep -v deploy.sh; \
#     echo '*/2 * * * * /opt/bvtech-portal/opspilot/deploy.sh >> /var/log/opspilot-deploy.log 2>&1' ) | crontab -
set -uo pipefail

REPO_DIR="${OPSPILOT_REPO_DIR:-/opt/bvtech-portal}"
COMPOSE_DIR="$REPO_DIR/opspilot"
log(){ echo "[$(date -u +%FT%TZ)] $*"; }

cd "$REPO_DIR" || { log "ERROR: repo dir $REPO_DIR not found"; exit 1; }
git fetch origin main --quiet || log "WARN: git fetch failed"
LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null)
REPO_VER=$(grep -oP 'APP_VERSION: str = "\K[^"]+' "$COMPOSE_DIR/app/core/config.py" 2>/dev/null)

cd "$COMPOSE_DIR" || { log "ERROR: compose dir not found"; exit 1; }
ver(){ docker compose exec -T api python -c "import app.core.config as c;print(c.get_settings().APP_VERSION)" 2>/dev/null | tr -d '\r\n '; }
RUN_VER=$(ver)

if [ "$LOCAL" = "$REMOTE" ] && [ -n "$RUN_VER" ] && [ "$RUN_VER" = "$REPO_VER" ]; then
  exit 0   # already current — nothing to do
fi

log "DEPLOY: git ${LOCAL:0:8}->${REMOTE:0:8} | running=${RUN_VER:-none} repo=${REPO_VER:-?}"
cd "$REPO_DIR"
# v1.41.2: self-heal ANY git wedge — wrong branch, local commits, dirty tree.
# `git pull --ff-only` fails forever once the mirror diverges, and the old
# script then quietly rebuilt STALE code every 2 minutes. The deploy mirror
# must exactly track origin/main, unconditionally.
git checkout -f main 2>/dev/null || git checkout -B main origin/main 2>&1 | sed 's/^/  /'
git reset --hard origin/main 2>&1 | sed 's/^/  /' || log "WARN: git reset failed"
REPO_VER=$(grep -oP 'APP_VERSION: str = "\K[^"]+' "$COMPOSE_DIR/app/core/config.py" 2>/dev/null)  # re-read AFTER reset
cd "$COMPOSE_DIR"
log "building api image..."
docker compose up -d --build api 2>&1 | tail -3 | sed 's/^/  /' || log "WARN: build/up failed"
log "applying migrations..."
docker compose exec -T api alembic upgrade head 2>&1 | tail -5 | sed 's/^/  /' || log "WARN: alembic failed"
docker compose restart api >/dev/null 2>&1 || log "WARN: restart failed"
sleep 3
NOW_VER=$(ver)
log "DEPLOY COMPLETE — running version now: ${NOW_VER:-unknown}"
if [ -n "$REPO_VER" ] && [ "$NOW_VER" != "$REPO_VER" ]; then
  log "ERROR: running version ($NOW_VER) still != repo version ($REPO_VER) — check 'docker compose logs api' and disk space (df -h)"
fi
