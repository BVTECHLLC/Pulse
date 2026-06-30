#!/usr/bin/env bash
# One-shot: finish wiring full autopilot on the Linode box.
#  - clones the JP website repo (so the daily JP post can publish to it)
#  - drops a .assetsignore in both site repos (keeps .git off the public site)
#  - records BV_JP_WEBSITE_REPO in publisher.env
#  - installs the daily cron jobs (BVTech 07:30 CT, JP 08:00 CT)
# Idempotent — safe to re-run. Never prints secrets.
set -uo pipefail

PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
PUB_ENV=/etc/bvtech/publisher.env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib_env.sh"; bvtech_load_env || true

BV_WEBSITE_REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"
BV_JP_WEBSITE_REPO="${BV_JP_WEBSITE_REPO:-/srv/jordanpolasek-website}"
JP_GIT_URL="${JP_GIT_URL:-https://gitlab.com/bvtechllc-group/jordanpolasek-website.git}"

echo "== Finish autopilot =="

# Make sure git can push both repos using the env-based credentials (PAT).
git config --global credential.helper \
  '!f() { test "$1" = get && printf "username=%s\npassword=%s\n" "$BV_GL_USER" "$BV_GL_TOKEN"; }; f' 2>/dev/null || true

# 1) Clone the JP site repo if it's not already on the box.
if [ -d "$BV_JP_WEBSITE_REPO/.git" ]; then
  echo "  • JP repo present — pulling"; git -C "$BV_JP_WEBSITE_REPO" pull --ff-only || true
else
  echo "  • cloning JP repo -> $BV_JP_WEBSITE_REPO"
  git clone "$JP_GIT_URL" "$BV_JP_WEBSITE_REPO" || { echo "  ❌ clone failed (check PAT)"; exit 1; }
fi
git -C "$BV_JP_WEBSITE_REPO" config core.fileMode false 2>/dev/null || true
git -C "$BV_JP_WEBSITE_REPO" config user.name  "Jordan Polasek" 2>/dev/null || true
git -C "$BV_JP_WEBSITE_REPO" config user.email "help@bvtech.org" 2>/dev/null || true

# 2) .assetsignore in both repos so .git is never shipped to the public site.
for repo in "$BV_WEBSITE_REPO" "$BV_JP_WEBSITE_REPO"; do
  [ -d "$repo/.git" ] || continue
  if [ ! -f "$repo/.assetsignore" ]; then
    printf '.git\n.gitignore\n.assetsignore\nnode_modules\ndist\n' > "$repo/.assetsignore"
    git -C "$repo" add .assetsignore
    git -C "$repo" commit -m "Add .assetsignore (keep .git off the public site)" >/dev/null 2>&1 || true
    git -C "$repo" push origin main >/dev/null 2>&1 && echo "  • .assetsignore pushed to $(basename "$repo")" \
      || echo "  • .assetsignore commit ready in $(basename "$repo") (push if needed)"
  fi
done

# 3) Record the JP repo path for the cron jobs (clean shell file, not the JSON).
touch "$PUB_ENV"; chmod 600 "$PUB_ENV"
grep -q 'BV_JP_WEBSITE_REPO=' "$PUB_ENV" 2>/dev/null \
  || echo "export BV_JP_WEBSITE_REPO=$BV_JP_WEBSITE_REPO" >> "$PUB_ENV"

# 4) Install cron jobs (idempotent).
chmod +x "$PULSE_REPO"/automation/*.sh 2>/dev/null || true
CRON_BV="30 12 * * * $PULSE_REPO/automation/daily_blog.sh"
CRON_JP="0 13 * * * $PULSE_REPO/automation/daily_jp_blog.sh"
TMP="$(mktemp)"; crontab -l 2>/dev/null > "$TMP" || true
grep -qF "daily_blog.sh" "$TMP" || echo "$CRON_BV" >> "$TMP"
grep -qF "daily_jp_blog.sh" "$TMP" || echo "$CRON_JP" >> "$TMP"
crontab "$TMP"; rm -f "$TMP"

echo
echo "== Status =="
echo "  BVTech daily  : $PULSE_REPO/automation/daily_blog.sh   (07:30 CT)"
echo "  JP daily      : $PULSE_REPO/automation/daily_jp_blog.sh (08:00 CT)"
echo "  JP repo       : $BV_JP_WEBSITE_REPO"
echo "  LinkedIn      : $([ -n "${LINKEDIN_ACCESS_TOKEN:-}" ] && echo 'env token set' || echo 'reads linkedin_access_token from agent.env')"
echo "  Cron now:"; crontab -l 2>/dev/null | sed 's/^/    /'
echo
echo "READY ✅  Optional smoke test now (writes a real JP post + pushes):"
echo "    bash $PULSE_REPO/automation/daily_jp_blog.sh ; tail -n 40 /var/log/bvtech/daily-jp-\$(date +%F).log"
