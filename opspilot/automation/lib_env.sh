#!/usr/bin/env bash
# Shared env loader. Pulls the secrets this toolkit needs into normalized
# variable names. Values are never printed.
#
#   /etc/bvtech/agent.env      -> treated as JSON ONLY (your big config file).
#                                 We parse it read-only and NEVER shell-source it,
#                                 so a malformed file can't spew errors here.
#   /etc/bvtech/publisher.env  -> a clean shell file WE own (export K=V). This is
#                                 the reliable home for the publisher's secrets.
#   /etc/bvtech-daily.env      -> legacy shell file, optional.
bvtech_load_env() {
  _bvtech_load_json /etc/bvtech/agent.env || true
  local f
  for f in /etc/bvtech/publisher.env /etc/bvtech-daily.env; do
    if [ -f "$f" ]; then set -a; . "$f"; set +a; fi
  done
  return 0   # never let a missing optional file trip the caller's `set -e`
}

_bvtech_load_json() {
  local f="$1" exports
  [ -f "$f" ] || return 0
  if exports="$(python3 - "$f" <<'PY'
import json, sys, shlex
try:
    with open(sys.argv[1], encoding="utf-8-sig") as fh:
        d = json.load(fh)
    assert isinstance(d, dict)
except Exception:
    sys.exit(3)   # not valid JSON -> skip (do NOT shell-source a config file)
low = {str(k).lower(): v for k, v in d.items() if isinstance(v, (str, int, float))}
def emit(env, *aliases):
    for a in aliases:
        v = low.get(a.lower())
        if v is not None and str(v).strip():
            print("export %s=%s" % (env, shlex.quote(str(v))))
            return
emit('ANTHROPIC_API_KEY', 'anthropic_api_key', 'anthropic_key', 'anthropic_token',
     'claude_api_key', 'claude_code_oauth_token', 'claude_key')
emit('BV_GL_USER', 'bv_gl_user', 'gl_user', 'gitlab_user', 'gitlab_deploy_user',
     'deploy_token_user', 'deploy_user')
emit('BV_GL_TOKEN', 'bv_gl_token', 'gl_token', 'gitlab_token', 'gitlab_deploy_token',
     'deploy_token', 'deploy_token_value', 'gitlab_pat')
emit('PULSE_REPO', 'pulse_repo')
emit('BV_WEBSITE_REPO', 'bv_website_repo', 'website_repo')
emit('WEBSITE_GIT_URL', 'website_git_url')
PY
)"; then
    eval "$exports"
  else
    echo "note: $f is not valid JSON right now — skipping it (using publisher.env)." >&2
    echo "      If your other automation reads $f, restore it to pure JSON." >&2
  fi
}

# Diagnostic: print only the KEY NAMES in a JSON env file (never the values).
bvtech_env_keys() {
  local f="${1:-/etc/bvtech/agent.env}"
  [ -f "$f" ] || { echo "(no file at $f)"; return; }
  python3 - "$f" <<'PY' 2>/dev/null || echo "(not valid JSON — likely has non-JSON lines pasted in)"
import json, sys
with open(sys.argv[1], encoding="utf-8-sig") as fh:
    d = json.load(fh)
print("  JSON keys present:", ", ".join(sorted(d.keys())))
PY
}
