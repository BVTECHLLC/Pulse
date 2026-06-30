#!/usr/bin/env bash
# JordanPolasek.com — daily founder/thought-leadership post generator + publisher.
# Mirror of daily_blog.sh, pointed at the JP repo + persona. Cloudflare
# (jordanpolasek-com) auto-deploys on push.
#
# Cron (08:00 CT daily):  0 13 * * *  /srv/pulse/opspilot/automation/daily_jp_blog.sh
set -euo pipefail

PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
export BV_JP_WEBSITE_REPO="${BV_JP_WEBSITE_REPO:-/srv/jordanpolasek-website}"
LOG_DIR="${LOG_DIR:-/var/log/bvtech}"
LOCK="/tmp/bvtech-jp-daily.lock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib_env.sh"; bvtech_load_env || true
PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
export BV_JP_WEBSITE_REPO="${BV_JP_WEBSITE_REPO:-/srv/jordanpolasek-website}"

mkdir -p "$LOG_DIR" "$PULSE_REPO/automation/out-jp"
LOG="$LOG_DIR/daily-jp-$(date +%F).log"
exec >>"$LOG" 2>&1
echo "===== $(date -Is) daily_jp_blog start ====="

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: ANTHROPIC_API_KEY not set"; exit 1
fi
for d in "$PULSE_REPO/automation" "$BV_JP_WEBSITE_REPO/.git"; do
  [ -d "$d" ] || { echo "FATAL: missing $d — check PULSE_REPO/BV_JP_WEBSITE_REPO"; exit 1; }
done

exec 9>"$LOCK"
if ! flock -n 9; then echo "another JP run is in progress; exiting"; exit 0; fi

git -C "$PULSE_REPO" pull --ff-only origin "$(git -C "$PULSE_REPO" rev-parse --abbrev-ref HEAD)" || true
git -C "$BV_JP_WEBSITE_REPO" pull --ff-only origin main || true

cd "$PULSE_REPO"
PROMPT="$(cat automation/jp_persona.md; echo; echo '---'; echo; cat automation/jp_daily_prompt.md)"

CLAUDE_TOOLS="WebSearch WebFetch Read Write Edit Bash Glob Grep"
claude -p "$PROMPT" --allowedTools "$CLAUDE_TOOLS" \
  || echo "claude run returned non-zero (safety-net publish below will still try)"

TODAY_JSON="automation/out-jp/today.json"
if [ -f "$TODAY_JSON" ]; then
  echo "safety-net publish from $TODAY_JSON"
  # Publish with JP branding + canonical so posts get jordanpolasek.com URLs
  # (not bvtech.org). This is what makes them show up as real JP posts.
  python3 scripts/publish_post.py --repo "$BV_JP_WEBSITE_REPO" --infile "$TODAY_JSON" --git \
    --site "https://jordanpolasek.com" --org "Jordan Polasek" \
    --author-url "https://jordanpolasek.com" \
    || echo "publish step failed (post may already be published by Claude)"
  # Cross-post to LinkedIn (best-effort).
  python3 scripts/post_linkedin.py --from-json "$TODAY_JSON" --tag jp \
    || echo "linkedin post skipped/failed (token may be expired)"
  mv "$TODAY_JSON" "automation/out-jp/published-$(date +%F).json" 2>/dev/null || true
  rm -f automation/out-jp/today.md
else
  echo "no today.json produced — nothing to publish"
fi

echo "===== $(date -Is) daily_jp_blog done ====="
