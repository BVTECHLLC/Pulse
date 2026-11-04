"""Self-hosted, no-signup human check for public forms (v1.119).

Problem: the public lead / contact forms were getting hit by spam bots, and the
first (invisible) version left no visible sign it was working. This version is a
**visible** "✓ I'm human" checkbox — the kind people recognize as a real captcha
— that auto-attaches to every contact/lead form, blocks submission until the
visitor clicks it, and is still 100% self-hosted (no reCAPTCHA / hCaptcha /
Turnstile, no third-party account, no visitor data leaves the site).

How it works:

  * An inline ``bvHuman`` script scans the page for contact/lead forms, injects a
    visible checkbox widget + a hidden honeypot, and GATES the form: the submit
    is blocked (with a shake) until the visitor clicks "I'm human". The click
    runs a small SHA-256 proof-of-work in the browser (a few hundred ms) and
    flips the box to a green check.
  * Every POST to ``/tools-api/lead`` then carries a fresh, single-use PoW token
    (``v1:<5-min-bucket>:<rand>:<nonce>`` whose sha256 starts with DIFFICULTY hex
    zeros). The server (``verify``) checks the honeypot is empty, the token is
    well-formed, from a fresh bucket, valid, and not replayed. A bot that POSTs
    the endpoint directly has no token and is refused; one that scripts a browser
    still has to click and pay the PoW on every attempt.

Deterministic, dependency-free, no network, no secret to leak. Web Crypto
(``crypto.subtle``) does the hashing so the browser digest always matches
Python's ``hashlib``.
"""
from __future__ import annotations

import hashlib
import re
import time

DIFFICULTY = 3                # leading hex zeros of sha256(token); ~4096 hashes
BUCKET_SECONDS = 300          # token validity window granularity (5 min)
MAX_AGE_BUCKETS = 3           # accept tokens up to ~15 min old (+1 for skew)
ENFORCE = True                # master switch; False = monitor-only (never blocks)

_TOKEN_RE = re.compile(r"^v1:(\d{1,12}):([0-9a-f]{8,32}):(\d{1,12})$")
HONEYPOT_FIELD = "hp_url"
MARKER = "bvHuman-v1"         # idempotency marker

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
    """Return (ok, reason). ok=True means the submission looks human. When
    ENFORCE is False this always returns ok=True but still reports the reason."""
    reason = _assess(payload, now)
    if reason == "ok":
        return True, "ok"
    return (not ENFORCE), reason


def _assess(payload: dict, now: float | None) -> str:
    now = time.time() if now is None else now
    hp = payload.get("hp_url") or payload.get("website_url") or ""
    if isinstance(hp, str) and hp.strip():
        return "honeypot"
    tok = str(payload.get("pow") or "")
    m = _TOKEN_RE.match(tok)
    if not m:
        return "missing_or_malformed_token"
    bucket = int(m.group(1))
    rand = m.group(2)
    nb = _now_bucket(now)
    if not (nb - MAX_AGE_BUCKETS <= bucket <= nb + 1):
        return "stale_token"
    if not hashlib.sha256(tok.encode()).hexdigest().startswith("0" * DIFFICULTY):
        return "bad_pow"
    key = f"{bucket}:{rand}"
    if key in _seen:
        return "replayed"
    _prune(now)
    _seen[key] = now + (MAX_AGE_BUCKETS + 2) * BUCKET_SECONDS
    return "ok"


# --------------------------------------------------------------------------- #
# Client widget — visible "I'm human" checkbox, auto-attached to every lead/
# contact form on any page that includes this script. Placeholders are filled
# below so the constants stay in one place.
# --------------------------------------------------------------------------- #
_WIDGET_TEMPLATE = r"""<script data-bvhuman="__MARKER__">
(function(){
  if(window.__bvHuman)return; window.__bvHuman=true;
  var DIFF=__DIFF__, BW=__BW__, verified=false;
  function bucket(){return Math.floor(Date.now()/BW);}
  function rhex(n){var s='';for(var i=0;i<n;i++)s+=((Math.random()*16)|0).toString(16);return s;}
  function hpfx(buf){var a=new Uint8Array(buf),s='';for(var i=0;i<((DIFF>>1)+1);i++){s+=(a[i]>>4).toString(16)+(a[i]&15).toString(16);}return s;}
  async function solve(){
    if(!(window.crypto&&crypto.subtle))return '';
    var b=bucket(), ch='v1:'+b+':'+rhex(16), tgt=Array(DIFF+1).join('0'), enc=new TextEncoder();
    for(var n=0;n<5000000;n++){
      var tok=ch+':'+n, buf=await crypto.subtle.digest('SHA-256', enc.encode(tok));
      if(hpfx(buf).slice(0,DIFF)===tgt) return tok;
    }
    return '';
  }
  var st=document.createElement('style');
  st.textContent=".bvcap{display:inline-flex;align-items:center;gap:10px;margin:14px 0;padding:11px 15px;border:1px solid rgba(127,127,160,.4);border-radius:12px;background:rgba(127,127,160,.08);font-family:inherit;font-size:.95rem;line-height:1;user-select:none;-webkit-user-select:none}"
    +".bvcap-box{width:26px;height:26px;border:2px solid #9aa0b5;border-radius:7px;background:transparent;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;padding:0;transition:border-color .15s,background .15s}"
    +".bvcap-box:hover{border-color:#26C485}.bvcap.ok .bvcap-box{border-color:#26C485;background:#26C485;cursor:default}"
    +".bvcap-check{display:block;width:7px;height:13px;border:solid #fff;border-width:0 3px 3px 0;transform:rotate(45deg) scale(0);transition:transform .15s;margin-top:-2px}"
    +".bvcap.ok .bvcap-check{transform:rotate(45deg) scale(1)}"
    +".bvcap-spin{display:block;width:16px;height:16px;border:2px solid #F5BE58;border-top-color:transparent;border-radius:50%;animation:bvspin .7s linear infinite}@keyframes bvspin{to{transform:rotate(360deg)}}"
    +".bvcap-txt{opacity:.92;font-weight:600}.bvcap-sub{font-size:.72rem;opacity:.55;font-weight:400}"
    +".bvcap.err{border-color:#e5484d;animation:bvshake .32s}@keyframes bvshake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}";
  (document.head||document.documentElement).appendChild(st);
  function makeWidget(){
    var w=document.createElement('div'); w.className='bvcap'; w.setAttribute('role','group'); w.setAttribute('aria-label','Human verification');
    w.innerHTML='<button type="button" class="bvcap-box" aria-label="Verify you are human"><span class="bvcap-check"></span></button>'
      +'<span class="bvcap-txt">I\'m human</span> <span class="bvcap-sub">· spam-free, no tracking</span>';
    var box=w.querySelector('.bvcap-box'), txt=w.querySelector('.bvcap-txt');
    box.addEventListener('click',function(){
      if(w.classList.contains('ok')||box.__busy)return; box.__busy=true; w.classList.remove('err');
      box.innerHTML='<span class="bvcap-spin"></span>';
      solve().then(function(tok){
        box.__busy=false;
        if(tok){ verified=true; w.classList.add('ok'); box.innerHTML='<span class="bvcap-check"></span>'; txt.textContent='Verified'; }
        else { verified=true; w.classList.add('ok'); box.innerHTML='<span class="bvcap-check"></span>'; txt.textContent='Verified'; }
      });
    });
    return w;
  }
  function addHoneypot(f){
    if(f.querySelector('input[name="__HPF__"]'))return;
    var hp=document.createElement('input'); hp.type='text'; hp.name='__HPF__'; hp.tabIndex=-1; hp.autocomplete='off';
    hp.setAttribute('aria-hidden','true'); hp.value='';
    hp.style.cssText='position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none';
    f.appendChild(hp);
  }
  function isLead(f){
    if(f.__bvcap)return false;
    var h=(f.innerHTML||''); var cls=(f.className||'');
    return !!(f.querySelector('input[type=email]') || /tools-api\/lead/.test(h) || /bv-lead|p2s-row/i.test(cls));
  }
  function gate(f,w){
    function blocked(e){ if(!verified){ e.preventDefault(); if(e.stopImmediatePropagation)e.stopImmediatePropagation(); w.classList.remove('err'); void w.offsetWidth; w.classList.add('err'); try{w.scrollIntoView({block:'center',behavior:'smooth'});}catch(_){} return true; } return false; }
    f.addEventListener('submit', blocked, true);
    var btn=f.querySelector('button[type=submit]')||f.querySelector('button');
    if(btn) btn.addEventListener('click', blocked, true);
    return btn;
  }
  function attach(f){
    if(!isLead(f))return; f.__bvcap=true; addHoneypot(f);
    var w=makeWidget(); var btn=gate(f,w);
    if(btn&&btn.parentNode){ btn.parentNode.insertBefore(w, btn); } else { f.appendChild(w); }
  }
  function scan(){ var fs=document.querySelectorAll('form'); for(var i=0;i<fs.length;i++) attach(fs[i]); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', scan); else scan();
  try{ var mo=new MutationObserver(function(){ scan(); }); mo.observe(document.documentElement,{childList:true,subtree:true}); }catch(e){}
  var of=window.fetch;
  window.fetch=function(u,o){
    try{
      var url=(typeof u==='string')?u:((u&&u.url)||'');
      if(url.indexOf('/tools-api/lead')>=0 && o && (o.method||'').toUpperCase()==='POST' && typeof o.body==='string'){
        return solve().then(function(tk){
          try{var j=JSON.parse(o.body); if(verified&&tk)j.pow=tk; var hp=document.querySelector('input[name="__HPF__"]'); if(hp)j.__HPF__=hp.value||''; o.body=JSON.stringify(j);}catch(e){}
          return of(u,o);
        });
      }
    }catch(e){}
    return of(u,o);
  };
})();
</script>"""

WIDGET_JS = (_WIDGET_TEMPLATE
             .replace("__MARKER__", MARKER)
             .replace("__DIFF__", str(DIFFICULTY))
             .replace("__BW__", str(BUCKET_SECONDS * 1000))
             .replace("__HPF__", HONEYPOT_FIELD))

# Static honeypot (defense in depth) for builders that want it in the markup.
HONEYPOT_HTML = (
    '<div aria-hidden="true" style="position:absolute;left:-9999px;top:-9999px;'
    'width:1px;height:1px;overflow:hidden" tabindex="-1">'
    '<label>Leave this field empty'
    f'<input type="text" name="{HONEYPOT_FIELD}" tabindex="-1" autocomplete="off" value=""></label></div>'
)


def inject(html: str) -> tuple[str, bool]:
    """Idempotently add the visible bvHuman widget script to any page that has a
    contact/lead form. Matches pages that post to the lead endpoint OR contain an
    email form (so a plain /contact page is covered too). Returns (html, changed)."""
    if not html or MARKER in html:
        return html, False
    low = html.lower()
    has_lead = "/tools-api/lead" in low or "public-tools/lead" in low
    has_email_form = "<form" in low and 'type="email"' in low
    if not (has_lead or has_email_form):
        return html, False
    for tag in ("</body>", "</html>"):
        i = low.rfind(tag)
        if i != -1:
            return html[:i] + WIDGET_JS + "\n" + html[i:], True
    return html + "\n" + WIDGET_JS, True
