#!/usr/bin/env bash
# BVTech OpsPilot — auto-deploy.
# Pulls main; if anything changed, rebuilds the app, runs migrations, restarts
# the api. Safe to run on a timer — it's a no-op when already up to date.
#
# One-time install of the 2-minute poller (run as root on the server):
#   chmod +x /opt/bvtech-portal/opspilot/deploy.sh
#   ( crontab -l 2>/dev/null | grep -v deploy.sh; \
#     echo '*/2 * * * * /opt/bvtech-portal/opspilot/deploy.sh >> /var/log/opspilot-deploy.log 2>&1' ) | crontab -
set -euo pipefail

REPO_DIR="${OPSPILOT_REPO_DIR:-/opt/bvtech-portal}"
COMPOSE_DIR="$REPO_DIR/opspilot"

cd "$REPO_DIR"
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0   # nothing new — done
fi

echo "[$(date -u +%FT%TZ)] deploying ${LOCAL:0:8} -> ${REMOTE:0:8}"
git pull --ff-only origin main

cd "$COMPOSE_DIR"
docker compose up -d --build
docker compose exec -T api alembic upgrade head
docker compose restart api
echo "[$(date -u +%FT%TZ)] deploy complete"
