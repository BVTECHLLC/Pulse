"""Self-hosted, no-signup human check for public forms (v1.122).

A visible **slide-to-fit puzzle** (drag the piece into the gap) that gates every
contact/lead form, backed by a server-verified proof-of-work and a honeypot, with
disposable-email blocking handled in ``email_guard``. 100% in-house: no reCAPTCHA
/ hCaptcha / Turnstile, no third-party account, no visitor data leaves the site.

Layers (defense in depth):
  * The visitor must DRAG a puzzle piece into a randomly-placed gap — a real
    interaction a drive-by bot won't perform. Solving it runs a SHA-256
    proof-of-work in the browser and unlocks the form.
  * Every POST to ``/tools-api/lead`` then carries a fresh, single-use PoW token
    (``v1:<5-min-bucket>:<rand>:<nonce>`` whose sha256 starts with DIFFICULTY hex
    zeros). The server (``verify``) checks the honeypot is empty, the token is
    well-formed, fresh, valid and not replayed. A bot POSTing directly has no
    token and is refused; one scripting a browser still pays the PoW every time.
  * ``email_guard`` rejects disposable/throwaway addresses server-side.

Web Crypto does the hashing so the browser digest always matches Python's hashlib.
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
MARKER = "bvHuman-v1"         # idempotency marker (kept stable across widget versions)

# POST endpoints the browser widget gates: it blocks the request until the
# puzzle is solved, then attaches a fresh PoW token + honeypot to the JSON body.
# Covers the static site's lead form AND the portal's public account forms.
PROTECTED_POST_PATHS = [
    "/tools-api/lead", "/api/public-tools/lead",   # contact / lead capture
    "/api/signup",                                  # portal access request
    "/api/academy/register",                        # academy open self-registration
]

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


# Human-readable messages for each failure reason, safe to show a real visitor.
_FRIENDLY = {
    "honeypot": "Submission blocked. Please try again from a normal browser.",
    "missing_or_malformed_token": "Please slide the puzzle piece to confirm you're human, then try again.",
    "stale_token": "That took a moment too long — please slide the puzzle again and resubmit.",
    "bad_pow": "Human check failed — please slide the puzzle again and resubmit.",
    "replayed": "Please slide the puzzle again and resubmit.",
    "disposable": "Please use a real, permanent email address (temporary/disposable inboxes aren't accepted).",
    "invalid": "That email address doesn't look valid — please double-check it.",
}


def friendly(reason: str) -> str:
    return _FRIENDLY.get(reason, "Please complete the human check and try again.")


def guard(payload: dict, *, email: str | None = None, now: float | None = None) -> tuple[bool, str]:
    """One call for public form endpoints: proof-of-work + honeypot (via verify)
    AND disposable-email rejection (via email_guard). Returns (ok, reason) where
    reason is already a visitor-friendly message when ok is False. Fails closed
    on bot signals; honours the ENFORCE master switch through verify()."""
    ok, reason = verify(payload, now=now)
    if not ok:
        return False, friendly(reason)
    if email:
        try:
            from . import email_guard
            eok, ereason = email_guard.check(email)
            if not eok:
                return False, friendly(ereason)
        except Exception:  # noqa: BLE001 — never let the guard crash a submission path
            pass
    return True, "ok"


# --------------------------------------------------------------------------- #
# Client widget — a visible slide-to-fit puzzle, auto-attached to every contact/
# lead form on any page that includes this script. Placeholders are filled below.
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
  st.textContent=".bvcap{display:block;max-width:300px;margin:14px 0;padding:12px;border:1px solid rgba(127,127,160,.4);border-radius:12px;background:rgba(127,127,160,.07);font-family:inherit;line-height:1.3;-webkit-user-select:none;user-select:none}"
    +".bvcap-head{font-size:.82rem;font-weight:700;opacity:.9;margin:0 0 8px}"
    +".bvcap-canvas{display:block;width:100%;height:90px;border-radius:8px;background:#0d1b2e;touch-action:none}"
    +".bvcap-track{position:relative;height:40px;margin-top:9px;border-radius:20px;background:rgba(127,127,160,.16);border:1px solid rgba(127,127,160,.32);overflow:hidden}"
    +".bvcap-track .fill{position:absolute;left:0;top:0;bottom:0;width:0;background:linear-gradient(90deg,rgba(38,196,133,.25),rgba(38,196,133,.4))}"
    +".bvcap-handle{position:absolute;left:3px;top:3px;width:34px;height:32px;border-radius:16px;background:#fff;box-shadow:0 2px 7px #0007;cursor:grab;display:flex;align-items:center;justify-content:center;color:#0d1b2e;font-weight:900;font-size:16px;touch-action:none}"
    +".bvcap-handle:active{cursor:grabbing}.bvcap.ok .bvcap-track{background:rgba(38,196,133,.16);border-color:#26C485}.bvcap.ok .bvcap-handle{background:#26C485;color:#fff;cursor:default}"
    +".bvcap.err .bvcap-track{animation:bvshake .3s}@keyframes bvshake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}"
    +".bvcap-hint{font-size:.72rem;opacity:.6;margin-top:7px;text-align:center}";
  (document.head||document.documentElement).appendChild(st);
  function makeWidget(){
    var w=document.createElement('div'); w.className='bvcap'; w.setAttribute('role','group'); w.setAttribute('aria-label','Human verification puzzle');
    w.innerHTML='<div class="bvcap-head">🧩 Slide the piece into the gap to continue</div>'
      +'<canvas class="bvcap-canvas" width="280" height="90" aria-hidden="true"></canvas>'
      +'<div class="bvcap-track"><div class="fill"></div><div class="bvcap-handle" tabindex="0" aria-label="Slide to verify">⇢</div></div>'
      +'<div class="bvcap-hint">in-house check · spam-free · no tracking</div>';
    var cv=w.querySelector('canvas'), ctx=cv.getContext('2d');
    var track=w.querySelector('.bvcap-track'), handle=w.querySelector('.bvcap-handle'), fill=w.querySelector('.fill'), head=w.querySelector('.bvcap-head');
    var W=280,H=90,pw=42,gapX=0,gapY=0,curX=3,solved=false;
    function rnd(a,b){return a+Math.random()*(b-a);}
    function path(x,y){var r=8;ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+pw,y,x+pw,y+pw,r);ctx.arcTo(x+pw,y+pw,x,y+pw,r);ctx.arcTo(x,y+pw,x,y,r);ctx.arcTo(x,y,x+pw,y,r);ctx.closePath();}
    function draw(){
      ctx.clearRect(0,0,W,H);
      var g=ctx.createLinearGradient(0,0,W,H);g.addColorStop(0,'#1b3b6b');g.addColorStop(1,'#0e2347');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
      ctx.globalAlpha=.5;ctx.fillStyle='#2a4f8a';ctx.fillRect(38,18,58,16);ctx.fillStyle='#39507f';ctx.beginPath();ctx.arc(214,28,20,0,7);ctx.fill();ctx.fillStyle='#2f477a';ctx.fillRect(150,56,70,18);ctx.globalAlpha=1;
      path(gapX,gapY);ctx.fillStyle='rgba(0,0,0,.45)';ctx.fill();ctx.strokeStyle='rgba(255,255,255,.35)';ctx.setLineDash([4,3]);ctx.stroke();ctx.setLineDash([]);
      path(curX,gapY);ctx.fillStyle=solved?'#26C485':'#ffd34d';ctx.fill();ctx.strokeStyle='#0d1b2e';ctx.lineWidth=2;ctx.stroke();
      ctx.fillStyle='#0d1b2e';ctx.beginPath();ctx.arc(curX+pw/2,gapY+pw/2,4,0,7);ctx.fill();
    }
    function setup(){gapX=Math.round(rnd(120,W-pw-12));gapY=Math.round(rnd(12,H-pw-12));curX=3;solved=false;w.classList.remove('ok','err');handle.textContent='⇢';head.textContent='🧩 Slide the piece into the gap to continue';draw();}
    function maxX(){return track.clientWidth-handle.offsetWidth-6;}
    function moveTo(px){var m=maxX();px=Math.max(0,Math.min(m,px));handle.style.left=(px+3)+'px';fill.style.width=(px+handle.offsetWidth)+'px';curX=3+Math.round(px/m*(W-pw-6));draw();}
    var dragging=false,sx=0,sl=0;
    function down(e){if(solved)return;dragging=true;sx=(e.touches?e.touches[0].clientX:e.clientX);sl=(parseFloat(handle.style.left||'3')-3);try{handle.setPointerCapture(e.pointerId);}catch(_){}}
    function move(e){if(!dragging)return;var x=(e.touches?e.touches[0].clientX:e.clientX);moveTo(sl+(x-sx));if(e.cancelable)e.preventDefault();}
    function up(){if(!dragging)return;dragging=false;check();}
    function check(){
      if(Math.abs(curX-gapX)<8){solved=true;verified=true;w.classList.remove('err');w.classList.add('ok');handle.textContent='✓';head.textContent='✓ Verified — thank you!';draw();try{solve();}catch(_){}}
      else{w.classList.remove('err');void w.offsetWidth;w.classList.add('err');setTimeout(function(){if(!solved)moveTo(0);},240);}
    }
    handle.addEventListener('pointerdown',down);handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',up);handle.addEventListener('pointercancel',up);handle.addEventListener('lostpointercapture',up);
    handle.addEventListener('touchstart',down,{passive:false});handle.addEventListener('touchmove',move,{passive:false});handle.addEventListener('touchend',up);
    setTimeout(setup,0);
    return w;
  }
  function addHoneypot(f){
    if(f.querySelector('input[name="__HPF__"]'))return;
    var hp=document.createElement('input');hp.type='text';hp.name='__HPF__';hp.tabIndex=-1;hp.autocomplete='off';hp.setAttribute('aria-hidden','true');hp.value='';
    hp.style.cssText='position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;pointer-events:none';
    f.appendChild(hp);
  }
  function isLead(f){
    if(f.__bvcap)return false;
    // Explicit opt-out / opt-in (opt-in wins even when a password field is present,
    // e.g. the Academy open-registration form we DO want gated).
    if(f.getAttribute&&f.getAttribute('data-bv-no-captcha')!==null)return false;
    if(f.getAttribute&&f.getAttribute('data-bv-protect')!==null)return true;
    var h=(f.innerHTML||'');var cls=(f.className||'');
    if(f.querySelector('input[type=password]'))return false;   // plain login form — left puzzle-free
    return !!(f.querySelector('input[type=email]') || /tools-api\/lead/.test(h) || /bv-lead|p2s-row|contact/i.test(cls));
  }
  function gate(f,w){
    function blocked(e){if(!verified){e.preventDefault();if(e.stopImmediatePropagation)e.stopImmediatePropagation();w.classList.remove('err');void w.offsetWidth;w.classList.add('err');try{w.scrollIntoView({block:'center',behavior:'smooth'});}catch(_){}return true;}return false;}
    f.addEventListener('submit',blocked,true);
    var btn=f.querySelector('button[type=submit]')||f.querySelector('button');
    if(btn)btn.addEventListener('click',blocked,true);
  }
  function attach(f){
    if(!isLead(f))return;f.__bvcap=true;addHoneypot(f);
    var w=makeWidget();gate(f,w);
    var btn=f.querySelector('button[type=submit]')||f.querySelector('button');
    if(btn&&btn.parentNode){btn.parentNode.insertBefore(w,btn);}else{f.appendChild(w);}
  }
  function scan(){var fs=document.querySelectorAll('form');for(var i=0;i<fs.length;i++)attach(fs[i]);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan);else scan();
  try{new MutationObserver(function(){scan();}).observe(document.documentElement,{childList:true,subtree:true});}catch(e){}
  var PATHS=__POST_PATHS__;
  function isProtectedUrl(url){for(var i=0;i<PATHS.length;i++){if(url.indexOf(PATHS[i])>=0)return true;}return false;}
  function flashAll(){var ws=document.querySelectorAll('.bvcap');for(var i=0;i<ws.length;i++){var w=ws[i];w.classList.remove('err');void w.offsetWidth;w.classList.add('err');if(i===0){try{w.scrollIntoView({block:'center',behavior:'smooth'});}catch(_){}}}}
  var of=window.fetch;
  window.fetch=function(u,o){
    try{
      var url=(typeof u==='string')?u:((u&&u.url)||'');
      var method=((o&&o.method)||(u&&u.method)||'GET').toUpperCase();
      if(method==='POST' && isProtectedUrl(url) && (!o || typeof o.body==='string' || o.body==null)){
        if(!verified){flashAll();return Promise.resolve(new Response(JSON.stringify({ok:false,detail:'Please slide the puzzle piece below to confirm you are human, then try again.'}),{status:403,headers:{'Content-Type':'application/json'}}));}
        return solve().then(function(tk){
          try{if(o&&typeof o.body==='string'){var j=JSON.parse(o.body);if(tk)j.pow=tk;var hp=document.querySelector('input[name="__HPF__"]');j.__HPF__=hp?(hp.value||''):'';o.body=JSON.stringify(j);}}catch(e){}
          return of(u,o);
        });
      }
    }catch(e){}
    return of(u,o);
  };
  window.bvHuman={ready:function(){return verified;},token:solve,rescan:scan};
})();
</script>"""

import json as _json

WIDGET_JS = (_WIDGET_TEMPLATE
             .replace("__MARKER__", MARKER)
             .replace("__DIFF__", str(DIFFICULTY))
             .replace("__BW__", str(BUCKET_SECONDS * 1000))
             .replace("__POST_PATHS__", _json.dumps(PROTECTED_POST_PATHS))
             .replace("__HPF__", HONEYPOT_FIELD))

# The same widget as a bare JS body (no <script> wrapper), for serving as a
# standalone file that server-rendered portal templates include with
# <script src="/human.js">. Strips the opening/closing <script> tags.
WIDGET_SRC_JS = re.sub(r"^<script[^>]*>\s*|\s*</script>\s*$", "", WIDGET_JS).strip()

HONEYPOT_HTML = (
    '<div aria-hidden="true" style="position:absolute;left:-9999px;top:-9999px;'
    'width:1px;height:1px;overflow:hidden" tabindex="-1">'
    '<label>Leave this field empty'
    f'<input type="text" name="{HONEYPOT_FIELD}" tabindex="-1" autocomplete="off" value=""></label></div>'
)

_SCRIPT_RE = re.compile(r'<script data-bvhuman="[^"]*">.*?</script>\s*', re.S)


def inject(html: str) -> tuple[str, bool]:
    """Idempotently ensure the CURRENT bvHuman widget is on any page with a
    contact/lead form. Strips any previous widget first so a republish UPGRADES
    an older widget in place. Returns (html, changed)."""
    if not html:
        return html, False
    orig = html
    work = _SCRIPT_RE.sub("", html) if "data-bvhuman" in html else html
    low = work.lower()
    needs = (("/tools-api/lead" in low or "public-tools/lead" in low)
             or ("<form" in low and 'type="email"' in low))
    if needs:
        placed = False
        for tag in ("</body>", "</html>"):
            i = work.lower().rfind(tag)
            if i != -1:
                work = work[:i] + WIDGET_JS + "\n" + work[i:]
                placed = True
                break
        if not placed:
            work = work + "\n" + WIDGET_JS
    return work, (work != orig)
