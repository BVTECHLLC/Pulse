#!/usr/bin/env bash
# Shared env loader. Normalizes the box's secrets into the variable names this
# toolkit uses — whether the file is shell (`export K=V`) OR JSON (e.g. the
# OpsPilot agent.env with "anthropic_key": "..."). Values are never printed.
#
# Robust JSON detection: we *try to parse* each file as JSON (tolerating a BOM
# or leading whitespace); only if that fails do we treat it as a shell file.
#
# Sources, in order (later files override earlier ones):
#   /etc/bvtech/agent.env       (your existing JSON or shell file)
#   /etc/bvtech/publisher.env   (clean shell file for the GitLab deploy token)
#   /etc/bvtech-daily.env       (legacy, optional)
bvtech_load_env() {
  local f exports
  for f in /etc/bvtech/agent.env /etc/bvtech/publisher.env /etc/bvtech-daily.env; do
    [ -f "$f" ] || continue
    if exports="$(python3 - "$f" <<'PY'
import json, sys, shlex
try:
    with open(sys.argv[1], encoding="utf-8-sig") as fh:
        d = json.load(fh)
    assert isinstance(d, dict)
except Exception:
    sys.exit(3)   # not JSON -> caller falls back to shell-sourcing
low = {str(k).lower(): v for k, v in d.items() if isinstance(v, (str, int, float))}
def emit(env, *aliases):
    for a in aliases:
        v = low.get(a.lower())
        if v is not None and str(v).strip():
            print("export %s=%s" % (env, shlex.quote(str(v))))
            return
emit('ANTHROPIC_API_KEY', 'anthropic_api_key', 'anthropic_key', 'anthropic_token',
     'claude_api_key', 'claude_code_oauth_token', 'claude_key', 'api_key')
emit('BV_GL_USER', 'bv_gl_user', 'gl_user', 'gitlab_user', 'gitlab_deploy_user',
     'deploy_token_user', 'deploy_user', 'gitlab_deploy_token_user')
emit('BV_GL_TOKEN', 'bv_gl_token', 'gl_token', 'gitlab_token', 'gitlab_deploy_token',
     'deploy_token', 'deploy_token_value', 'gitlab_pat', 'pat')
emit('PULSE_REPO', 'pulse_repo')
emit('BV_WEBSITE_REPO', 'bv_website_repo', 'website_repo')
emit('WEBSITE_GIT_URL', 'website_git_url')
PY
)"; then
      eval "$exports"
    else
      set -a; . "$f"; set +a
    fi
  done
}

# Diagnostic: print only the KEY NAMES present in a JSON env file (never values).
# Used by bootstrap when a required secret can't be found, so we can see what the
# key is actually called without exposing anything sensitive.
bvtech_env_keys() {
  local f="${1:-/etc/bvtech/agent.env}"
  [ -f "$f" ] || { echo "(no file at $f)"; return; }
  python3 - "$f" <<'PY' 2>/dev/null || echo "(not valid JSON — may be a shell file)"
import json, sys
with open(sys.argv[1], encoding="utf-8-sig") as fh:
    d = json.load(fh)
print("  JSON keys present:", ", ".join(sorted(d.keys())))
PY
}
