#!/usr/bin/env bash
# BVTech OpsPilot — box self-updater (v1.61)
#
# Runs on the Linode host every 5 minutes (systemd timer). When origin/main
# moves, it deploys AUTOMATICALLY — but only commits that passed CI, so a
# mid-push or broken build can never take the box down. This removes the
# need to SSH in for updates: whatever ships to main from a Pulse session
# is live on the box within ~5 minutes of CI going green.
#
# ONE-TIME INSTALL (the last SSH you need for deploys):
#   cd /opt/bvtech-portal/opspilot
#   sudo bash scripts/box_autoupdate.sh --install
#
# Manual run / status:
#   sudo systemctl start pulse-autoupdate.service
#   systemctl list-timers pulse-autoupdate.timer
#   journalctl -u pulse-autoupdate.service -n 50
set -euo pipefail

REPO_DIR="/opt/bvtech-portal/opspilot"
GH_REPO="BVTECHLLC/Pulse"
LOG_TAG="pulse-autoupdate"

log() { echo "[$LOG_TAG] $*"; logger -t "$LOG_TAG" "$*" 2>/dev/null || true; }

install_units() {
    cat > /etc/systemd/system/pulse-autoupdate.service <<'UNIT'
[Unit]
Description=BVTech OpsPilot self-update (deploy CI-green main)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash /opt/bvtech-portal/opspilot/scripts/box_autoupdate.sh
TimeoutStartSec=900
UNIT
    cat > /etc/systemd/system/pulse-autoupdate.timer <<'UNIT'
[Unit]
Description=Run the OpsPilot self-updater every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
UNIT
    systemctl daemon-reload
    systemctl enable --now pulse-autoupdate.timer
    log "installed + started pulse-autoupdate.timer (every 5 min)"
    systemctl list-timers pulse-autoupdate.timer --no-pager || true
}

if [[ "${1:-}" == "--install" ]]; then
    install_units
    exit 0
fi

cd "$REPO_DIR"

git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [[ "$LOCAL" == "$REMOTE" ]]; then
    exit 0                                        # already current — silent
fi

log "new main detected: ${LOCAL:0:8} -> ${REMOTE:0:8}; checking CI"

# Deploy ONLY CI-green commits. Public repo -> unauthenticated check-runs API.
CI_STATE=$(curl -sS --max-time 30 \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$GH_REPO/commits/$REMOTE/check-runs" \
    | python3 -c "
import json, sys
try:
    runs = json.load(sys.stdin).get('check_runs') or []
except Exception:
    print('error'); raise SystemExit
if not runs:
    print('pending'); raise SystemExit
if any(r.get('status') != 'completed' for r in runs):
    print('pending')
elif all(r.get('conclusion') in ('success', 'skipped', 'neutral') for r in runs):
    print('success')
else:
    print('failure')
" 2>/dev/null || echo "error")

case "$CI_STATE" in
    success) ;;
    pending) log "CI still running for ${REMOTE:0:8}; will retry next tick"; exit 0 ;;
    failure) log "CI FAILED for ${REMOTE:0:8}; holding current version"; exit 0 ;;
    *)       log "CI status unavailable; holding current version this tick"; exit 0 ;;
esac

log "CI green for ${REMOTE:0:8} — deploying"
git merge --ff-only origin/main
if docker compose up -d --build 2>&1 | tail -3 | logger -t "$LOG_TAG" 2>/dev/null; then
    :
else
    docker compose up -d --build
fi

# health gate: give the api 90s to come healthy; roll back if it never does
for _ in $(seq 1 18); do
    STATE=$(docker inspect --format '{{.State.Health.Status}}' opspilot-api-1 2>/dev/null || echo "unknown")
    [[ "$STATE" == "healthy" ]] && { log "deployed ${REMOTE:0:8}; api healthy"; exit 0; }
    sleep 5
done
log "api NOT healthy after deploy of ${REMOTE:0:8} — rolling back to ${LOCAL:0:8}"
git reset --hard "$LOCAL"
docker compose up -d --build
log "rolled back to ${LOCAL:0:8}"
exit 1
