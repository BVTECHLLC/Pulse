#!/usr/bin/env bash
# BVTech daily-publisher preflight. Run this ON THE LINODE BOX to confirm
# everything is wired before enabling the cron. It checks secrets, repos, the
# Claude CLI, GitLab push access, and the renderer — and NEVER prints secret
# values (only "set / not set" + lengths). Exit 0 = ready.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib_env.sh"; bvtech_load_env
PULSE_REPO="${PULSE_REPO:-/srv/pulse/opspilot}"
BV_WEBSITE_REPO="${BV_WEBSITE_REPO:-/srv/bvtech-website-new}"

ok=0; fail=0
pass(){ echo "  ✅ $1"; ok=$((ok+1)); }
bad(){  echo "  ❌ $1"; fail=$((fail+1)); }

echo "== BVTech daily-publisher preflight =="

# 1) Secret present? (report only length, never the value)
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  pass "ANTHROPIC_API_KEY is set (${#ANTHROPIC_API_KEY} chars)"
else
  bad "ANTHROPIC_API_KEY is NOT set — add it to /etc/bvtech/agent.env"
fi

# 2) Claude CLI present?
if command -v claude >/dev/null 2>&1; then
  pass "claude CLI found ($(claude --version 2>/dev/null | head -1))"
else
  bad "claude CLI not on PATH"
fi

# 3) Pulse repo + automation + publish script
if [ -d "$PULSE_REPO/automation" ] && [ -f "$PULSE_REPO/scripts/publish_post.py" ]; then
  pass "pulse repo OK ($PULSE_REPO)"
else
  bad "pulse repo missing automation/ or scripts/publish_post.py at $PULSE_REPO"
fi

# 4) Website repo present + is a git checkout (blog/ is created on first publish)
if [ -d "$BV_WEBSITE_REPO/.git" ]; then
  n=$(ls "$BV_WEBSITE_REPO"/blog/*.html 2>/dev/null | wc -l)
  pass "website repo OK ($BV_WEBSITE_REPO, $n posts)"
  [ "$n" -eq 0 ] && echo "     ⚠️  note: repo has no blog posts yet — push your V107 site so the homepage exists and posts get pixel-perfect templates."
else
  bad "website repo not found / not a git checkout at $BV_WEBSITE_REPO"
fi

# 5) GitLab push access (read test via deploy key — doesn't push anything)
if [ -d "$BV_WEBSITE_REPO/.git" ] && git -C "$BV_WEBSITE_REPO" ls-remote origin >/dev/null 2>&1; then
  pass "git remote reachable with the box's key (push access expected)"
else
  bad "cannot reach git remote — check the GitLab deploy key / ssh config"
fi

# 6) Renderer works (dry-run, writes nothing)
if [ -f "$PULSE_REPO/scripts/publish_post.py" ]; then
  if python3 "$PULSE_REPO/scripts/publish_post.py" --repo "$BV_WEBSITE_REPO" \
       --title "Preflight Test Post" --kind advisory \
       --body-file <(printf '## Test\nPreflight render check.\n') --dry-run >/dev/null 2>&1; then
    pass "publish_post.py renders cleanly (dry-run)"
  else
    bad "publish_post.py dry-run failed — run it directly to see the error"
  fi
fi

echo "== result: $ok passed, $fail failed =="
[ "$fail" -eq 0 ] && echo "READY ✅  — you can run automation/daily_blog.sh" || echo "NOT READY — fix the ❌ items above"
exit "$fail"
