#!/usr/bin/env bash
# BVTech — daily security advisory generator + publisher.
# Runs headless Claude Code on the Linode box (via cron), writes today's post in
# Jordan's voice grounded in real, current threat news, and publishes it to the
# bvtech-website-new repo (Cloudflare Pages auto-deploys on push).
#
# Cron (07:30 CT daily):  30 12 * * *  /srv/pulse/opspilot/automation/daily_blog.sh
# (12:30 UTC = 07:30 CDT. Adjust for your timezone.)
set -euo pipefail

# ---- Config (override via /etc/bvtech-daily.env) --------------------------- #
PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
export BV_WEBSITE_REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"
LOG_DIR="${LOG_DIR:-/var/log/bvtech}"
LOCK="/tmp/bvtech-daily.lock"
# Secrets (ANTHROPIC_API_KEY, GitLab deploy token, optional repo paths) come from
# the box's protected env files. The shared loader handles JSON or shell formats
# and normalizes key names (e.g. "anthropic_key" -> ANTHROPIC_API_KEY). Values
# are never echoed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib_env.sh"; bvtech_load_env || true
# Re-apply path defaults after loading (loader may set them).
PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
export BV_WEBSITE_REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"

mkdir -p "$LOG_DIR" "$PULSE_REPO/automation/out"
LOG="$LOG_DIR/daily-$(date +%F).log"
exec >>"$LOG" 2>&1
echo "===== $(date -Is) daily_blog start ====="

# Preflight: fail loudly (without leaking the key) if the essentials are missing.
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: ANTHROPIC_API_KEY not set (expected in /etc/bvtech/agent.env)"; exit 1
fi
for d in "$PULSE_REPO/automation" "$BV_WEBSITE_REPO/.git"; do
  [ -d "$d" ] || { echo "FATAL: missing $d — check PULSE_REPO/BV_WEBSITE_REPO"; exit 1; }
done

# Single-instance guard.
exec 9>"$LOCK"
if ! flock -n 9; then echo "another run is in progress; exiting"; exit 0; fi

# Keep both repos current before we generate.
git -C "$PULSE_REPO" pull --ff-only origin "$(git -C "$PULSE_REPO" rev-parse --abbrev-ref HEAD)" || true
git -C "$BV_WEBSITE_REPO" pull --ff-only origin main || true

cd "$PULSE_REPO"
PROMPT="$(cat automation/bvtech_persona.md; echo; echo '---'; echo; cat automation/daily_blog_prompt.md)"

# Headless Claude Code: web-search today's story, write the post, run
# scripts/publish_post.py to publish. In cron there's no one to approve prompts,
# so we bypass permissions (the prompt + repo scope constrain what it does).
#   -p / --print            : non-interactive, print result and exit
#   --permission-mode bypassPermissions : run unattended (no approval prompts)
# This flag set is stable across Claude Code 2.x. If your build differs, run
# `claude --help` and adjust this one line.
claude -p "$PROMPT" --permission-mode bypassPermissions \
  || echo "claude run returned non-zero (safety-net publish below will still try)"

# ---- Safety-net publish: if Claude wrote today.json but didn't push, do it. -- #
TODAY_JSON="automation/out/today.json"
if [ -f "$TODAY_JSON" ]; then
  # If the body lives only in today.md, splice it in.
  if ! grep -q '"body"' "$TODAY_JSON" && [ -f automation/out/today.md ]; then
    python3 - "$TODAY_JSON" automation/out/today.md <<'PY'
import json, sys
meta = json.load(open(sys.argv[1]))
meta["body"] = open(sys.argv[2], encoding="utf-8").read()
json.dump(meta, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY
  fi
  echo "safety-net publish from $TODAY_JSON"
  python3 scripts/publish_post.py --repo "$BV_WEBSITE_REPO" --infile "$TODAY_JSON" --git \
    || echo "publish step failed (post may already be published by Claude)"
  # Archive so we don't republish tomorrow.
  mv "$TODAY_JSON" "automation/out/published-$(date +%F).json" 2>/dev/null || true
  rm -f automation/out/today.md
else
  echo "no today.json produced — nothing to publish"
fi

echo "===== $(date -Is) daily_blog done ====="
