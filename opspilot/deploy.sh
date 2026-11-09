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

# v1.149: SELF-INSTALL the 2-minute poller so auto-deploy becomes PERMANENT after
# a single manual run — after this, every push to main goes live on its own with
# no further server access. Idempotent: only adds the cron line if it's missing.
# Disable with OPSPILOT_NO_CRON=1 (e.g. if you manage the schedule elsewhere).
SELF="$COMPOSE_DIR/deploy.sh"
if [ "${OPSPILOT_NO_CRON:-0}" != "1" ] && command -v crontab >/dev/null 2>&1; then
  if ! crontab -l 2>/dev/null | grep -qF "$SELF"; then
    ( crontab -l 2>/dev/null; \
      echo "*/2 * * * * $SELF >> /var/log/opspilot-deploy.log 2>&1" ) | crontab - \
      && log "INSTALLED 2-minute auto-deploy cron — push-to-live is now automatic." \
      || log "WARN: could not install cron (need a user crontab); add it by hand once."
  fi
fi

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
# v1.108: the games (/arena, /signal) are static WASM bundles bind-mounted into
# the api container, so rebuilding api above already picks up new game builds.
# Stop the retired Signal 199X node service if it is still running (idempotent).
docker compose stop game 2>/dev/null; docker compose rm -f game 2>/dev/null || true
log "applying migrations..."
docker compose exec -T api alembic upgrade head 2>&1 | tail -5 | sed 's/^/  /' || log "WARN: alembic failed"
docker compose restart api >/dev/null 2>&1 || log "WARN: restart failed"
sleep 3
NOW_VER=$(ver)
log "DEPLOY COMPLETE — running version now: ${NOW_VER:-unknown}"
if [ -n "$REPO_VER" ] && [ "$NOW_VER" != "$REPO_VER" ]; then
  log "ERROR: running version ($NOW_VER) still != repo version ($REPO_VER) — check 'docker compose logs api' and disk space (df -h)"
fi

# v1.124: bust Cloudflare's edge cache on every real deploy. The portal and
# bvtech.org both sit behind Cloudflare, whose edge kept serving OLD /kart/,
# /explore/, and lead-form HTML for hours after a deploy (reads as "I pushed
# but the site didn't change"). A full-zone purge on bvtech.org clears the
# portal.bvtech.org subdomain too, so the game, explore, and forms all go
# fresh at once. Best-effort: a missing/invalid token just logs and moves on.
log "purging Cloudflare edge cache (bvtech + jp zones)..."
docker compose exec -T api python - <<'PYPURGE' 2>&1 | sed 's/^/  /' || log "WARN: cache purge step failed"
from app.core.db import SessionLocal
from app.services import cloudflare
db = SessionLocal()
try:
    for site in ("bvtech", "jp"):
        try:
            r = cloudflare.purge_everything(db, site)
            print(f"{site}: {r.get('detail')}")
        except Exception as e:
            print(f"{site}: purge error {e}")
finally:
    db.close()
PYPURGE

# v1.149: AUTO-PUBLISH the static site so SITE changes (nav, tools, the captcha
# sweep across every form, new pages) go live automatically too — not just the
# API container. destination.publish is idempotent (commits only changed files)
# and resilient (chunked GitLab commits), but it is heavier than a redeploy, so
# we throttle it to at most once per 30 min and run it best-effort AFTER the api
# is already up (it can never break the deploy). Opt out with OPSPILOT_AUTO_PUBLISH=0.
STAMP="/var/tmp/opspilot-last-publish"
PUB_AGE=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
if [ "${OPSPILOT_AUTO_PUBLISH:-1}" = "1" ] && [ "$PUB_AGE" -gt 1800 ]; then
  log "publishing static site (destination.publish) so site changes go live..."
  docker compose exec -T api python - <<'PYPUB' 2>&1 | sed 's/^/  /' || log "WARN: site publish step failed"
from app.core.db import SessionLocal
from app.services import destination
db = SessionLocal()
try:
    r = destination.publish(db)
    print(f"publish ok={r.get('ok')} pages={len(r.get('pages', []))}")
except Exception as e:
    print(f"publish error: {e}")
finally:
    db.close()
PYPUB
  touch "$STAMP"
fi
log "DONE."
