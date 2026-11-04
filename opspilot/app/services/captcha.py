"""Self-hosted, no-signup human check for public forms (v1.118).

Problem: the public lead / contact forms were getting hit by spam bots that
POST straight to the lead endpoint. We want to block non-humans WITHOUT signing
up for reCAPTCHA / hCaptcha / Turnstile or sending any visitor data to a third
party.

How it works — a tiny proof-of-work + honeypot, verified server-side:

  * The page runs an inline ``bvHuman`` script. On load it computes a PoW token
    ``v1:<bucket>:<rand>:<nonce>`` where ``sha256(token)`` begins with
    ``DIFFICULTY`` hex zeros. ``bucket = floor(epoch/300)`` (a 5-minute window)
    so a token is only valid for a short time, and ``rand`` makes each token
    unique so it can't be replayed. The script wraps ``window.fetch`` and
    transparently attaches the token to every POST to ``/tools-api/lead`` — so
    EVERY real submission from the page carries a valid token with no per-form
    code.
  * A spam bot that POSTs the endpoint directly (the common case) never runs the
    script, so it has no token and is rejected. A bot that *does* drive a real
    browser still pays CPU for the PoW on every attempt, which throttles volume,
    and a classic hidden honeypot field catches naive form-fillers.
  * The server (``verify``) checks: token shape, a fresh bucket, the PoW hash,
    one-time use (in-process replay cache), and an empty honeypot. Fails closed.

Deterministic, dependency-free, no network, no secret to leak. Web Crypto
(``crypto.subtle``) does the client hashing so the client digest always matches
Python's ``hashlib`` — no hand-rolled SHA-256 to get wrong.
"""
from __future__ import annotations

import hashlib
import re
import time

# Leading hex zeros required of sha256(token). 3 => ~4096 hashes average: a few
# hundred ms of background work for a real browser, invisible to the user, but a
# real per-request cost to anyone POSTing at volume. Bump to slow bots further.
DIFFICULTY = 3
BUCKET_SECONDS = 300          # token validity window granularity (5 min)
MAX_AGE_BUCKETS = 3           # accept tokens up to ~15 min old (+1 for clock skew)
ENFORCE = True                # master switch; False = log-only (never blocks)

_TOKEN_RE = re.compile(r"^v1:(\d{1,12}):([0-9a-f]{8,32}):(\d{1,12})$")
_RAND_RE = re.compile(r"^[0-9a-f]{8,32}$")

# In-process one-time-use cache: {"bucket:rand": expiry_epoch}. Per-worker memory
# is fine — a replayed token within the window is refused by whichever worker saw
# it; across workers the short bucket + PoW cost keep abuse negligible.
_seen: dict[str, float] = {}


def _now_bucket(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // BUCKET_SECONDS)


def _prune(now: float) -> None:
    if len(_seen) < 20000:
        return
    for k, exp in list(_seen.items()):
        if exp < now:
            _seen.pop(k, None)


def verify(payload: dict, *, now: float | None = None) -> tuple[bool, str]:
    """Return (ok, reason). ok=True means the submission looks human.

    Checks (in order): honeypot empty, token present + well-formed, bucket fresh,
    proof-of-work valid, token not already used. When ENFORCE is False this always
    returns ok=True (monitor mode) but still reports the reason it *would* have
    blocked, so a caller can log it.
    """
    reason = _assess(payload, now)
    if reason == "ok":
        return True, "ok"
    return (not ENFORCE), reason


def _assess(payload: dict, now: float | None) -> str:
    now = time.time() if now is None else now
    # 1) honeypot: a hidden field real users never see or fill
    hp = payload.get("hp_url") or payload.get("website_url") or ""
    if isinstance(hp, str) and hp.strip():
        return "honeypot"
    # 2) token shape
    tok = str(payload.get("pow") or "")
    m = _TOKEN_RE.match(tok)
    if not m:
        return "missing_or_malformed_token"
    bucket = int(m.group(1))
    rand = m.group(2)
    # 3) freshness
    nb = _now_bucket(now)
    if not (nb - MAX_AGE_BUCKETS <= bucket <= nb + 1):
        return "stale_token"
    # 4) proof of work
    if not hashlib.sha256(tok.encode()).hexdigest().startswith("0" * DIFFICULTY):
        return "bad_pow"
    # 5) one-time use
    key = f"{bucket}:{rand}"
    if key in _seen:
        return "replayed"
    _prune(now)
    _seen[key] = now + (MAX_AGE_BUCKETS + 2) * BUCKET_SECONDS
    return "ok"


# --------------------------------------------------------------------------- #
# Client widget — an inline, dependency-free script. Include once per page that
# has a lead/contact form. It needs no markup changes: it wraps fetch and adds a
# valid PoW token to every POST to /tools-api/lead. A honeypot field is added to
# forms that opt in via the field name below.
# --------------------------------------------------------------------------- #
HONEYPOT_FIELD = "hp_url"
MARKER = "bvHuman-v1"    # presence marker so the hardener stays idempotent

WIDGET_JS = (
    "<script data-bvhuman=\"" + MARKER + "\">\n"
    "(function(){\n"
    "  if(window.__bvHuman)return; window.__bvHuman=true;\n"
    "  var DIFF=" + str(DIFFICULTY) + ", BW=" + str(BUCKET_SECONDS * 1000) + ";\n"
    "  var curBucket=null, curTok=null;\n"
    "  function bucket(){return Math.floor(Date.now()/BW);}\n"
    "  function rhex(n){var s='';for(var i=0;i<n;i++)s+=((Math.random()*16)|0).toString(16);return s;}\n"
    "  function hexPrefix(buf){var a=new Uint8Array(buf),s='';for(var i=0;i<((DIFF>>1)+1);i++){s+=(a[i]>>4).toString(16)+(a[i]&15).toString(16);}return s;}\n"
    "  async function compute(){\n"
    "    if(!(window.crypto&&crypto.subtle))return '';\n"
    "    var b=bucket(), ch='v1:'+b+':'+rhex(16), tgt=Array(DIFF+1).join('0'), enc=new TextEncoder();\n"
    "    for(var n=0;n<5000000;n++){\n"
    "      var tok=ch+':'+n;\n"
    "      var buf=await crypto.subtle.digest('SHA-256', enc.encode(tok));\n"
    "      if(hexPrefix(buf).slice(0,DIFF)===tgt) return tok;\n"
    "    }\n"
    "    return '';\n"
    "  }\n"
    "  function token(){ if(curTok&&curBucket===bucket())return curTok; curBucket=bucket(); curTok=compute(); return curTok; }\n"
    "  try{ token(); }catch(e){}\n"   # warm up in the background on load
    "  var of=window.fetch;\n"
    "  window.fetch=function(u,o){\n"
    "    try{\n"
    "      var url=(typeof u==='string')?u:((u&&u.url)||'');\n"
    "      if(url.indexOf('/tools-api/lead')>=0 && o && (o.method||'').toUpperCase()==='POST' && typeof o.body==='string'){\n"
    "        return Promise.resolve(token()).then(function(tk){\n"
    "          try{var j=JSON.parse(o.body); if(tk)j.pow=tk;\n"
    "            var hp=document.querySelector('input[name=\\\"" + HONEYPOT_FIELD + "\\\"]'); if(hp)j." + HONEYPOT_FIELD + "=hp.value||'';\n"
    "            o.body=JSON.stringify(j);}catch(e){}\n"
    "          return of(u,o);\n"
    "        });\n"
    "      }\n"
    "    }catch(e){}\n"
    "    return of(u,o);\n"
    "  };\n"
    "})();\n"
    "</script>"
)

# A visually-hidden honeypot input to drop into built forms (defense in depth).
HONEYPOT_HTML = (
    '<div aria-hidden="true" style="position:absolute;left:-9999px;top:-9999px;'
    'width:1px;height:1px;overflow:hidden" tabindex="-1">'
    '<label>Leave this field empty'
    f'<input type="text" name="{HONEYPOT_FIELD}" tabindex="-1" autocomplete="off" value=""></label></div>'
)


def inject(html: str) -> tuple[str, bool]:
    """Idempotently add the bvHuman widget to a page that has a lead form.

    Only touches pages that reference the lead endpoint and don't already carry
    the widget. Inserts before </body> (or </html>, or appends). Returns
    (html, changed)."""
    if not html or MARKER in html:
        return html, False
    if "/tools-api/lead" not in html and "public-tools/lead" not in html:
        return html, False
    low = html.lower()
    for tag in ("</body>", "</html>"):
        i = low.rfind(tag)
        if i != -1:
            return html[:i] + WIDGET_JS + "\n" + html[i:], True
    return html + "\n" + WIDGET_JS, True
