#!/usr/bin/env bash
# Shared env loader. Normalizes the box's secrets into the variable names this
# toolkit uses — whether the file is shell (`export K=V`) OR JSON (e.g. the
# OpsPilot agent.env with "anthropic_key": "..."). Values are never printed.
#
# Sources, in order (later files override earlier ones):
#   /etc/bvtech/agent.env       (your existing JSON or shell file)
#   /etc/bvtech/publisher.env   (clean shell file for the GitLab deploy token)
#   /etc/bvtech-daily.env       (legacy, optional)
bvtech_load_env() {
  local f first
  for f in /etc/bvtech/agent.env /etc/bvtech/publisher.env /etc/bvtech-daily.env; do
    [ -f "$f" ] || continue
    first="$(head -c1 "$f" 2>/dev/null)"
    if [ "$first" = "{" ]; then
      # JSON file — extract + normalize the keys we need (case-insensitive).
      eval "$(python3 - "$f" <<'PY'
import json, sys, shlex
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
low = {k.lower(): v for k, v in d.items() if isinstance(v, (str, int, float))}
def emit(env, *aliases):
    for a in aliases:
        v = low.get(a.lower())
        if v is not None and str(v).strip():
            print("export %s=%s" % (env, shlex.quote(str(v))))
            return
emit('ANTHROPIC_API_KEY', 'anthropic_api_key', 'anthropic_key', 'anthropic_token',
     'claude_api_key', 'claude_code_oauth_token')
emit('BV_GL_USER', 'bv_gl_user', 'gl_user', 'gitlab_user', 'gitlab_deploy_user',
     'deploy_token_user', 'deploy_user')
emit('BV_GL_TOKEN', 'bv_gl_token', 'gl_token', 'gitlab_token', 'gitlab_deploy_token',
     'deploy_token', 'deploy_token_value')
emit('PULSE_REPO', 'pulse_repo')
emit('BV_WEBSITE_REPO', 'bv_website_repo', 'website_repo')
emit('WEBSITE_GIT_URL', 'website_git_url')
PY
)"
    else
      set -a; . "$f"; set +a
    fi
  done
}
