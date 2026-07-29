#!/usr/bin/env bash
# BVTech OpsPilot — tunnel & stack watchdog (self-healing)
#
# Error 1033 ("Cloudflare Tunnel error") means the cloudflared connector on this
# box lost its link to Cloudflare — the app is usually fine, but the doorway is
# shut. This watchdog runs every 2 minutes and heals that automatically:
#   * if cloudflared (systemd OR docker) is down/inactive -> restart it
#   * if the api/db/caddy containers are not running        -> `compose up -d`
#   * if the disk is critically full (a common crash cause) -> prune old images
# Everything is logged to the journal (tag: opspilot-watchdog) and is safe to
# run repeatedly. It NEVER touches data volumes.
#
# Install once (from the box):
#   cd /opt/bvtech-portal/opspilot
#   sudo bash scripts/tunnel_watchdog.sh --install
#
# Check it:   systemctl status opspilot-watchdog.timer
#             journalctl -u opspilot-watchdog -n 40
# Run once:   sudo bash scripts/tunnel_watchdog.sh
set -uo pipefail

REPO_DIR="/opt/bvtech-portal/opspilot"
LOG_TAG="opspilot-watchdog"
DISK_CRITICAL_PCT=93          # prune unused images above this root-fs usage

log() { echo "$*" | logger -t "$LOG_TAG" 2>/dev/null; echo "[$LOG_TAG] $*"; }

# --------------------------------------------------------------------------- #
# Installer: systemd service + 2-minute timer
# --------------------------------------------------------------------------- #
if [[ "${1:-}" == "--install" ]]; then
  if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo bash $0 --install"; exit 1; fi
  cat >/etc/systemd/system/opspilot-watchdog.service <<EOF
[Unit]
Description=BVTech OpsPilot tunnel & stack watchdog (self-healing)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash ${REPO_DIR}/scripts/tunnel_watchdog.sh
EOF
  cat >/etc/systemd/system/opspilot-watchdog.timer <<EOF
[Unit]
Description=Run the OpsPilot watchdog every 2 minutes

[Timer]
OnBootSec=60
OnUnitActiveSec=120
AccuracySec=15s

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now opspilot-watchdog.timer
  log "installed + started opspilot-watchdog.timer (every 2 min)"
  systemctl status opspilot-watchdog.timer --no-pager 2>/dev/null | head -6 || true
  exit 0
fi

# --------------------------------------------------------------------------- #
# 0) Disk pressure — a full root fs crashes cloudflared and the containers.
# --------------------------------------------------------------------------- #
USE_PCT="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"
if [[ -n "$USE_PCT" && "$USE_PCT" -ge "$DISK_CRITICAL_PCT" ]]; then
  log "disk at ${USE_PCT}% — pruning unused docker images to recover space"
  docker system prune -af >/dev/null 2>&1 || true   # images/containers only; NOT volumes
fi

# --------------------------------------------------------------------------- #
# 1) cloudflared — the tunnel connector (systemd service OR docker container).
# --------------------------------------------------------------------------- #
healed_tunnel=0
if systemctl list-unit-files 2>/dev/null | grep -q '^cloudflared\.service'; then
  if ! systemctl is-active --quiet cloudflared; then
    log "cloudflared systemd service is DOWN — restarting"
    systemctl restart cloudflared && healed_tunnel=1
  fi
  systemctl is-enabled --quiet cloudflared 2>/dev/null || systemctl enable cloudflared 2>/dev/null || true
else
  # Docker-hosted cloudflared (name usually contains 'cloudflared').
  cf_name="$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -i cloudflared | head -1)"
  if [[ -n "$cf_name" ]]; then
    state="$(docker inspect -f '{{.State.Running}}' "$cf_name" 2>/dev/null || echo false)"
    if [[ "$state" != "true" ]]; then
      log "cloudflared container '$cf_name' is DOWN — starting"
      docker start "$cf_name" >/dev/null 2>&1 && healed_tunnel=1
    fi
  else
    log "WARN: no cloudflared systemd unit or container found — tunnel may be run another way"
  fi
fi

# --------------------------------------------------------------------------- #
# 2) The app stack — make sure api/db/redis/caddy are up.
# --------------------------------------------------------------------------- #
healed_stack=0
if [[ -d "$REPO_DIR" ]]; then
  cd "$REPO_DIR" || exit 0
  # api is the load-bearing container; if it's not running, bring the stack up.
  api_running="$(docker compose ps --status running --services 2>/dev/null | grep -c '^api$' || true)"
  if [[ "${api_running:-0}" -lt 1 ]]; then
    log "api container not running — 'docker compose up -d'"
    docker compose up -d >/dev/null 2>&1 && healed_stack=1
  fi
fi

# --------------------------------------------------------------------------- #
# 3) Local liveness proof (best-effort) — the api answers on the compose net.
# --------------------------------------------------------------------------- #
if command -v curl >/dev/null 2>&1 && [[ -d "$REPO_DIR" ]]; then
  if ! docker compose -f "$REPO_DIR/docker-compose.yml" exec -T api \
        curl -fsS -m 5 http://localhost:8000/api/health >/dev/null 2>&1; then
    : # non-fatal: api may still be warming up; step 2 already nudged it.
  fi
fi

if [[ "$healed_tunnel" -eq 1 || "$healed_stack" -eq 1 ]]; then
  log "healed: tunnel=${healed_tunnel} stack=${healed_stack}"
fi
exit 0
