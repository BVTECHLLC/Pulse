"""Inbox Guardian — portal UI + API for the in-house AI email filter.

Staff-only. The page is a self-contained dashboard that reads the live
classification feed and lets the owner flip settings, run a scan, and
allow/block senders. Safe by default (dry-run until explicitly enabled).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import email_filter

router = APIRouter(tags=["email-filter"])
_STAFF = require_roles(Role.OWNER, Role.TECH)


@router.get("/api/email-filter/state")
def ef_state(db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    return email_filter.status(db)


@router.post("/api/email-filter/scan")
def ef_scan(db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    return email_filter.scan(db)


class _Settings(BaseModel):
    enabled: bool | None = None
    apply: bool | None = None
    aggressiveness: str | None = None
    mailbox: str | None = None
    tenant: str | None = None


@router.post("/api/email-filter/settings")
def ef_settings(body: _Settings, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    email_filter.set_setting(db, **body.model_dump(exclude_none=True))
    return email_filter.status(db)


class _Sender(BaseModel):
    email: str
    where: str   # "allow" | "block"


@router.post("/api/email-filter/sender")
def ef_sender(body: _Sender, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    email_filter.add_sender(db, body.email, body.where)
    return email_filter.status(db)


_PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Inbox Guardian — BVTech</title>
<style>
:root{--bg:#0b1020;--card:#141a2e;--line:rgba(255,255,255,.1);--txt:#e7ecf5;--mut:#93a0bd;--o:#5b8cff;--keep:#2fbf71;--rev:#f5be58;--junk:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--o)}.wrap{max-width:1040px;margin:0 auto;padding:26px 18px 80px}
h1{font-size:1.6rem;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 22px}
.row{display:flex;gap:14px;flex-wrap:wrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.kpi{flex:1;min-width:120px;text-align:center}.kpi b{display:block;font-size:1.9rem;font-family:Georgia,serif}
.kpi.keep b{color:var(--keep)}.kpi.rev b{color:var(--rev)}.kpi.junk b{color:var(--junk)}
.kpi small{color:var(--mut);text-transform:uppercase;letter-spacing:.08em;font-size:.7rem;font-weight:700}
.bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:18px 0}
button{font:inherit;cursor:pointer;border-radius:9px;border:1px solid var(--line);background:#1d2742;color:var(--txt);padding:9px 15px;font-weight:600}
button.primary{background:linear-gradient(135deg,#5b8cff,#8f6bff);border:0;color:#fff}
button:disabled{opacity:.5;cursor:default}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;font-weight:700;padding:3px 10px;border-radius:999px}
.pill.keep{background:rgba(47,191,113,.16);color:var(--keep)}.pill.review{background:rgba(245,190,88,.16);color:var(--rev)}.pill.junk{background:rgba(255,107,107,.16);color:var(--junk)}
table{width:100%;border-collapse:collapse;margin-top:6px}th,td{text-align:left;padding:10px 8px;border-top:1px solid var(--line);vertical-align:top;font-size:.9rem}
th{color:var(--mut);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.from{color:var(--mut);font-size:.8rem}.reason{color:var(--mut);font-size:.8rem}
.mini{padding:4px 9px;font-size:.76rem;font-weight:700}
.tag{font-size:.72rem;color:var(--mut)}
.toggle{display:flex;align-items:center;gap:8px}
.switch{width:42px;height:24px;border-radius:14px;background:#2a3657;position:relative;transition:.15s;border:0;padding:0}
.switch.on{background:var(--keep)}.switch::after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;transition:.15s}.switch.on::after{left:21px}
select{font:inherit;background:#1d2742;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.note{color:var(--mut);font-size:.82rem}.warn{color:var(--rev)}
.status-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px}
.ok{background:var(--keep)}.bad{background:var(--junk)}
@media(max-width:620px){.hide-sm{display:none}}
</style></head><body><div class=wrap>
<h1>🛡️ Inbox Guardian</h1>
<p class=sub>Your in-house AI email filter. It reads every message to your mailbox, keeps the real people, and quietly sets aside the solicitors — reversible, nothing deleted.</p>
<div id=conn class=note></div>
<div class="row" style="margin:16px 0">
  <div class="card kpi keep"><b id=k-keep>–</b><small>Kept</small></div>
  <div class="card kpi rev"><b id=k-rev>–</b><small>Review</small></div>
  <div class="card kpi junk"><b id=k-junk>–</b><small>Filtered</small></div>
  <div class="card kpi"><b id=k-moved>–</b><small>Moved</small></div>
</div>
<div class="card">
  <div class="bar">
    <div class=toggle><button class=switch id=sw-enabled aria-label="Enabled"></button><span>Filtering on</span></div>
    <div class=toggle><button class=switch id=sw-apply aria-label="Apply"></button><span>Move filtered mail <span class=note>(off = dry-run, just classify)</span></span></div>
    <label class=toggle>Strictness
      <select id=aggr><option value=lenient>Lenient</option><option value=balanced>Balanced</option><option value=strict>Strict</option></select>
    </label>
    <button class=primary id=scan>⟳ Scan now</button>
  </div>
  <div class=note id=meta></div>
</div>
<div class="card" style="margin-top:16px">
  <div class=bar style="margin:0 0 6px"><b>Recent decisions</b><span class=note id=mode></span></div>
  <table><thead><tr><th>From</th><th>Subject</th><th>Call</th><th class=hide-sm>Why</th><th></th></tr></thead>
  <tbody id=rows><tr><td colspan=5 class=note>Loading…</td></tr></tbody></table>
</div>
<p class=note style="margin-top:18px">Known contacts from your CRM are always kept automatically. Allow/Block here teaches it for next time. Built by BVTech — ask us about running this on your mailbox too.</p>
</div>
<script>
var S={};
function api(p,m,b){return fetch(p,{method:m||'GET',headers:{'content-type':'application/json'},body:b?JSON.stringify(b):undefined,credentials:'same-origin'}).then(function(r){if(r.status===401||r.status===403)throw new Error('auth');return r.json();});}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function render(){
  var st=S['stats']||{};
  document.getElementById('k-keep').textContent=st.keep||0;
  document.getElementById('k-rev').textContent=st.review||0;
  document.getElementById('k-junk').textContent=st.junk||0;
  document.getElementById('k-moved').textContent=st.moved||0;
  document.getElementById('sw-enabled').classList.toggle('on',!!S.enabled);
  document.getElementById('sw-apply').classList.toggle('on',!!S.apply);
  document.getElementById('aggr').value=S.aggressiveness||'balanced';
  var c=document.getElementById('conn');
  c.innerHTML=S.connected?('<span class="status-dot ok"></span>Connected to <b>'+esc(S.mailbox)+'</b>'):('<span class="status-dot bad"></span><span class=warn>Mailbox not connected yet</span> — '+esc(S.connect_error||'grant the Graph app Mail.ReadWrite consent for '+(S.tenant||''))+'');
  document.getElementById('mode').textContent=S.apply?'· moving filtered mail to the "BVTech Filtered" folder':'· dry-run — classifying only, nothing is moved';
  document.getElementById('meta').textContent=(S.last_scan?('Last scan '+new Date(S.last_scan).toLocaleString()):'Not scanned yet')+(S.last_error?(' · '+S.last_error):'');
  var rows=(S.recent||[]);var tb=document.getElementById('rows');
  if(!rows.length){tb.innerHTML='<tr><td colspan=5 class=note>No messages classified yet. Turn filtering on and hit Scan now.</td></tr>';return;}
  tb.innerHTML=rows.map(function(r){
    var v=r.verdict||'review';
    return '<tr><td><b>'+esc(r.from_name||r.from)+'</b><div class=from>'+esc(r.from)+'</div></td>'
      +'<td>'+esc(r.subject)+'<div class=tag>'+esc(r.category||'')+(r.by==='rule'?' · rule':'')+(r.moved?' · moved':'')+'</div></td>'
      +'<td><span class="pill '+v+'">'+v+'</span></td>'
      +'<td class=hide-sm><span class=reason>'+esc(r.reason||'')+'</span></td>'
      +'<td><button class=mini data-allow="'+esc(r.from)+'">Always allow</button> <button class=mini data-block="'+esc(r.from)+'">Block</button></td></tr>';
  }).join('');
}
function load(){api('/api/email-filter/state').then(function(d){S=d;render();}).catch(function(e){document.getElementById('conn').innerHTML=(e.message==='auth'?'Please <a href="/login">sign in</a> as staff to use the Inbox Guardian.':'Could not load.');});}
document.getElementById('scan').addEventListener('click',function(){var b=this;b.disabled=true;b.textContent='Scanning…';api('/api/email-filter/scan','POST').then(function(){return api('/api/email-filter/state');}).then(function(d){S=d;render();}).catch(function(){}).then(function(){b.disabled=false;b.textContent='⟳ Scan now';});});
function setting(k,v){api('/api/email-filter/settings','POST',(function(o){o[k]=v;return o;})({})).then(function(d){S=d;render();});}
document.getElementById('sw-enabled').addEventListener('click',function(){setting('enabled',!S.enabled);});
document.getElementById('sw-apply').addEventListener('click',function(){setting('apply',!S.apply);});
document.getElementById('aggr').addEventListener('change',function(){setting('aggressiveness',this.value);});
document.getElementById('rows').addEventListener('click',function(e){var a=e.target.getAttribute('data-allow'),b=e.target.getAttribute('data-block');if(a||b){api('/api/email-filter/sender','POST',{email:(a||b),where:a?'allow':'block'}).then(function(d){S=d;render();});}});
load();
</script></body></html>"""


@router.get("/email-filter", response_class=HTMLResponse, include_in_schema=False)
def ef_page(request: Request) -> HTMLResponse:
    return HTMLResponse(_PAGE, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
