#!/usr/bin/env bash
# Repair /etc/bvtech/agent.env back to valid JSON by removing any shell `export`
# lines that got pasted into it (which broke your other automation). Backs up
# first, then validates. Never prints secret values.
set -uo pipefail
F=/etc/bvtech/agent.env
[ -f "$F" ] || { echo "no $F"; exit 1; }

BAK="$F.bak.$(date +%s)"
cp "$F" "$BAK"
echo "backed up -> $BAK"

# Remove shell lines pasted into the JSON: `export K=V`, quoted `"export K=V`,
# AND bare `KEY=value` assignments (which start with an unquoted identifier+`=` —
# never valid JSON, where lines start with a quoted "key":).
sed -i -E '/^[[:space:]]*"?export /d; /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=/d' "$F"

if python3 -c "import json;json.load(open('$F',encoding='utf-8-sig'));print('VALID JSON ✓')" 2>/dev/null; then
  echo "agent.env is valid JSON again — your other automation can read it."
  echo "keys present:"
  python3 - "$F" <<'PY'
import json,sys
print("  " + ", ".join(sorted(json.load(open(sys.argv[1],encoding="utf-8-sig")).keys())))
PY
else
  echo "STILL not valid JSON — there's more than just export lines wrong."
  echo "Showing the structure around the break (values hidden):"
  python3 - "$F" <<'PY'
import json,sys
try:
    json.load(open(sys.argv[1],encoding="utf-8-sig"))
except json.JSONDecodeError as e:
    ln=e.lineno
    with open(sys.argv[1],encoding="utf-8-sig") as fh: rows=fh.read().splitlines()
    import re
    for i in range(max(0,ln-3),min(len(rows),ln+2)):
        masked=re.sub(r'(:\s*").*?("\s*,?\s*$)', r'\1<hidden>\2', rows[i])
        print(f"  {i+1}: {masked}")
    print(f"  -> JSON error at line {ln}: {e.msg}")
PY
  echo "Restore with:  cp $BAK $F   (then tell Claude the masked lines above)."
fi
