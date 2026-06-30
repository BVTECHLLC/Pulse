#!/usr/bin/env bash
# One-shot Linode bootstrap for the BVTech daily publisher.
# Run once on the box (after cloning this repo from public GitHub). It clones the
# website repo using a GitLab DEPLOY TOKEN read from /etc/bvtech/agent.env, wires
# the paths, and runs preflight. Secrets are NEVER written to a file or printed —
# the git credential helper reads them from the environment at runtime.
#
#   git clone https://github.com/BVTECHLLC/Pulse.git /srv/pulse
#   cd /srv/pulse && git checkout claude/pulse-rmm-msp-features-c4ug25
#   bash opspilot/automation/bootstrap_linode.sh
set -uo pipefail

ENV_FILE=/etc/bvtech/agent.env
PUB_ENV=/etc/bvtech/publisher.env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib_env.sh"; bvtech_load_env

PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
BV_WEBSITE_REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"
WEBSITE_GIT_URL="${WEBSITE_GIT_URL:-https://gitlab.com/bvtechllc-group/bvtech-website-new.git}"

echo "== BVTech Linode bootstrap =="

# Stop chmod +x from showing up as a tracked change and blocking `git pull`.
git -C "${PULSE_REPO%/opspilot}" config core.fileMode false 2>/dev/null || true

# ---- Required secrets (presence only; values never printed) ----------------
# ANTHROPIC_API_KEY is read from your existing agent.env (JSON "anthropic_key"
# is auto-mapped). The GitLab deploy token goes in a clean shell file so we
# never touch/append to your JSON.
miss=0
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "  ❌ Anthropic key not found in $ENV_FILE (looked for anthropic_key/ANTHROPIC_API_KEY/etc)"
  echo "     Here are the key names actually in your file (values hidden):"
  bvtech_env_keys "$ENV_FILE"
  echo "     → tell Claude that exact key name, or rename it to \"anthropic_key\"."
  miss=1
fi
[ -n "${BV_GL_USER:-}" ]  || { echo "  ❌ BV_GL_USER missing  — GitLab deploy-token USERNAME"; miss=1; }
[ -n "${BV_GL_TOKEN:-}" ] || { echo "  ❌ BV_GL_TOKEN missing — GitLab deploy-token VALUE"; miss=1; }
if [ "$miss" != 0 ]; then
  cat <<TIP

  To create the GitLab deploy token (one time):
    GitLab → bvtech-website-new → Settings → Repository → Deploy tokens
    name: linode-publisher   scopes: read_repository + write_repository → Create
  Then put the two values in a CLEAN shell file (NOT your JSON agent.env):
    nano $PUB_ENV
  and add:
    export BV_GL_USER='<deploy-token-username>'
    export BV_GL_TOKEN='<deploy-token-value>'
  Save, then re-run this script.
TIP
  exit 1
fi
echo "  ✅ secrets present (ANTHROPIC_API_KEY ${#ANTHROPIC_API_KEY} chars, deploy token set)"

# ---- Env-based git credentials: token is read from env, never stored -------
git config --global credential.helper \
  '!f() { test "$1" = get && printf "username=%s\npassword=%s\n" "$BV_GL_USER" "$BV_GL_TOKEN"; }; f'

# ---- Clone or update the website repo --------------------------------------
if [ -d "$BV_WEBSITE_REPO/.git" ]; then
  echo "  • website repo exists — pulling latest"
  git -C "$BV_WEBSITE_REPO" pull --ff-only || true
else
  echo "  • cloning website repo → $BV_WEBSITE_REPO"
  git clone "$WEBSITE_GIT_URL" "$BV_WEBSITE_REPO" || { echo "  ❌ clone failed — check the deploy token scopes"; exit 1; }
fi
git -C "$BV_WEBSITE_REPO" config user.name  "BVTech Publisher"
git -C "$BV_WEBSITE_REPO" config user.email "publisher@bvtech.org"

# ---- Persist paths for cron (idempotent) — into the CLEAN shell file -------
touch "$PUB_ENV"; chmod 600 "$PUB_ENV"
grep -q 'PULSE_REPO='      "$PUB_ENV" 2>/dev/null || echo "export PULSE_REPO=$PULSE_REPO"           >> "$PUB_ENV"
grep -q 'BV_WEBSITE_REPO=' "$PUB_ENV" 2>/dev/null || echo "export BV_WEBSITE_REPO=$BV_WEBSITE_REPO" >> "$PUB_ENV"

chmod +x "$PULSE_REPO"/automation/*.sh 2>/dev/null || true
echo
echo "== preflight =="
bash "$PULSE_REPO/automation/preflight.sh"
rc=$?
echo
if [ "$rc" -eq 0 ]; then
  cat <<EOF
READY ✅  Next:
  1) Live dry run:   bash $PULSE_REPO/automation/daily_blog.sh
                     tail -n 60 /var/log/bvtech/daily-\$(date +%F).log
  2) Schedule daily (07:30 CT):
     ( crontab -l 2>/dev/null; echo "30 12 * * * $PULSE_REPO/automation/daily_blog.sh" ) | crontab -
EOF
fi
exit "$rc"
