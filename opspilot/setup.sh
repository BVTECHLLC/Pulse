#!/usr/bin/env bash
# BVTech OpsPilot — one-shot "get me live" setup.
#
# Does all the SSH-side Tier 1 steps for you, interactively:
#   1) installs the auto-deploy poller cron (so merges go live on their own)
#   2) installs the run-checks scheduler cron (weekly digest, auto-posting,
#      A/R reminders, recurring invoices, posture snapshots, SLA escalation, …)
#   3) sets your email (SMTP) + Claude (Anthropic) keys in .env
#   4) restarts the app so the new settings take effect
#
# Safe to run as many times as you like — it updates in place, never duplicates.
#
# Usage (on the Linode box):
#   cd <your repo>/opspilot
#   sudo bash setup.sh
set -uo pipefail

say(){ printf '\n\033[1;36m%s\033[0m\n' "$*"; }
ok(){  printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[1;33m!\033[0m %s\n' "$*"; }
ask(){ local p="$1" d="${2:-}"; local a; read -r -p "  $p ${d:+[$d] }" a; echo "${a:-$d}"; }

# --- Locate the repo + compose dir ----------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR"
if [ ! -f "$COMPOSE_DIR/docker-compose.yml" ]; then
  for d in /opt/bvtech-portal/opspilot /srv/pulse/opspilot /srv/pulse /opt/pulse/opspilot; do
    [ -f "$d/docker-compose.yml" ] && COMPOSE_DIR="$d" && break
  done
fi
if [ ! -f "$COMPOSE_DIR/docker-compose.yml" ]; then
  echo "ERROR: couldn't find the opspilot dir (with docker-compose.yml). Run this from inside it."; exit 1
fi
DEPLOY_SH="$COMPOSE_DIR/deploy.sh"
ENV_FILE="$COMPOSE_DIR/.env"
PORTAL_URL="$(ask 'Portal URL' 'https://portal.bvtech.org')"
say "Using: $COMPOSE_DIR"

# --- .env helper: set KEY=VALUE (update in place or append) ----------------- #
touch "$ENV_FILE"
set_env(){
  local key="$1" val="$2"
  [ -z "$val" ] && return 0
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    # replace the whole line safely (value may contain / & etc.)
    local tmp; tmp="$(mktemp)"
    grep -v "^${key}=" "$ENV_FILE" > "$tmp"
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
    mv "$tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
  ok "$key set"
}

# --- cron helper: install/replace a line matched by a tag ------------------- #
add_cron(){
  local match="$1" line="$2"
  local tmp; tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -vF "$match" > "$tmp" || true
  echo "$line" >> "$tmp"
  crontab "$tmp"; rm -f "$tmp"
}

# --- 1) Auto-deploy poller -------------------------------------------------- #
say "1) Auto-deploy poller (redeploys within ~2 min of every merge to main)"
if [ -f "$DEPLOY_SH" ]; then
  chmod +x "$DEPLOY_SH"
  add_cron "deploy.sh" "*/2 * * * * $DEPLOY_SH >> /var/log/opspilot-deploy.log 2>&1"
  ok "deploy poller installed"
else
  warn "deploy.sh not found at $DEPLOY_SH — skipping (merges won't auto-deploy)."
fi

# --- 2) Scheduler (run-checks) --------------------------------------------- #
say "2) Scheduler heartbeat — powers the weekly digest, auto-posting, A/R"
echo "   reminders, recurring invoices, posture snapshots, SLA escalation, etc."
echo "   First create a key in the portal:  Settings → API Keys → Create key"
API_KEY="$(ask 'Paste your API key (blank = skip for now):' '')"
if [ -n "$API_KEY" ]; then
  add_cron "automation/run-checks" \
    "*/5 * * * * curl -s -X POST -H \"X-API-Key: $API_KEY\" $PORTAL_URL/api/automation/run-checks >/dev/null 2>&1"
  ok "run-checks scheduled every 5 minutes"
else
  warn "skipped — automations stay dormant until you add this. Re-run setup.sh anytime."
fi

# --- 3) Email (SMTP) -------------------------------------------------------- #
say "3) Outbound email (SMTP) — welcome emails, invites, resets, digests"
SMTP_HOST_IN="$(ask 'SMTP host (blank = skip):' '')"
if [ -n "$SMTP_HOST_IN" ]; then
  set_env SMTP_HOST "$SMTP_HOST_IN"
  set_env SMTP_PORT "$(ask 'SMTP port' '587')"
  set_env SMTP_USER "$(ask 'SMTP username:' '')"
  read -r -s -p "  SMTP password (hidden): " SMTP_PW_IN; echo
  set_env SMTP_PASSWORD "$SMTP_PW_IN"
  set_env SMTP_FROM "$(ask 'From address' 'help@bvtech.org')"
else
  warn "skipped — email stays a safe no-op (logged, not sent)."
fi

# --- 4) Claude (Anthropic) -------------------------------------------------- #
say "4) Claude AI key — copilot, QBR narratives, AI marketing posts"
ANTHROPIC_IN="$(ask 'Anthropic API key (sk-ant-… , blank = skip):' '')"
set_env ANTHROPIC_API_KEY "$ANTHROPIC_IN"

# --- 5) Restart ------------------------------------------------------------- #
say "5) Restarting the app to apply .env changes"
if command -v docker >/dev/null 2>&1 && (cd "$COMPOSE_DIR" && docker compose ps >/dev/null 2>&1); then
  (cd "$COMPOSE_DIR" && docker compose restart api) && ok "api restarted"
else
  warn "couldn't run 'docker compose restart api' here — the deploy poller will pick up .env within ~2 min."
fi

say "Done! What's live now:"
crontab -l 2>/dev/null | grep -E "deploy.sh|run-checks" | sed 's/^/   cron: /'
echo
echo "  Left to do (in the portal, click-only): secure your owner login + MFA,"
echo "  then Microsoft SSO, Stripe, Google Business, etc. See CHANGELOG / the"
echo "  Settings → Setup checklist for the rest."
