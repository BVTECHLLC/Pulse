"""v2.0 Sales engine API — deals (pipeline) + quotes (signable proposals).

Staff endpoints (OWNER/TECH, audited) manage the pipeline and build/send quotes.
Public endpoints (no auth, token-gated) let a prospect view and e-sign a quote,
which converts the deal to a Client and drafts the onboarding invoice. The public
accept page itself is served at /q/{token}.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Deal, DEAL_STAGES, Quote, Role, User
from ...services import audit, sales

router = APIRouter(tags=["sales"])

_STAFF = require_roles(Role.OWNER, Role.TECH)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _deal(db: Session, deal_id: int) -> Deal:
    d = db.get(Deal, deal_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found")
    return d


def _quote(db: Session, quote_id: int) -> Quote:
    q = db.get(Quote, quote_id)
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found")
    return q


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
@router.get("/api/deals/board")
def deals_board(db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    return sales.pipeline_board(db)


@router.get("/api/deals")
def list_deals(stage: str | None = Query(None), limit: int = Query(300, ge=1, le=1000),
               db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    q = db.query(Deal)
    if stage:
        q = q.filter(Deal.stage == stage)
    rows = q.order_by(Deal.updated_at.desc()).limit(limit).all()
    return {"deals": [sales.deal_dict(db, d) for d in rows], "count": len(rows)}


class DealIn(BaseModel):
    title: str
    contact_id: int | None = None
    value: float = 0.0
    stage: str = "new"
    probability: int | None = None
    source: str | None = None
    notes: str | None = None
    expected_close: str | None = None


@router.post("/api/deals")
def create_deal(body: DealIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(_STAFF)):
    if not body.title.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "title is required")
    d = sales.create_deal(db, title=body.title, contact_id=body.contact_id,
                          value=body.value, stage=body.stage, probability=body.probability,
                          source=body.source or "manual", notes=body.notes,
                          expected_close=_parse_date(body.expected_close), user_id=user.id)
    db.commit()
    audit.record(db, action="deal.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="deal", target_id=str(d.id),
                 ip=_ip(request), detail=f"{d.title} @ {d.value}")
    return sales.deal_dict(db, d, with_quotes=True)


@router.get("/api/deals/{deal_id}")
def get_deal(deal_id: int, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    return sales.deal_dict(db, _deal(db, deal_id), with_quotes=True)


class DealUpdate(BaseModel):
    title: str | None = None
    value: float | None = None
    stage: str | None = None
    probability: int | None = None
    contact_id: int | None = None
    source: str | None = None
    notes: str | None = None
    expected_close: str | None = None
    lost_reason: str | None = None


@router.put("/api/deals/{deal_id}")
def update_deal(deal_id: int, body: DealUpdate, request: Request,
                db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    d = _deal(db, deal_id)
    if body.stage is not None and body.stage != d.stage:
        if body.stage not in DEAL_STAGES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid stage {body.stage!r}")
        sales.move_stage(db, d, body.stage, lost_reason=body.lost_reason)
    if body.title is not None:
        d.title = body.title.strip()[:200] or d.title
    if body.value is not None:
        d.value = sales._money(body.value)
    if body.probability is not None:
        d.probability = max(0, min(100, body.probability))
    if body.contact_id is not None:
        d.contact_id = body.contact_id
    if body.source is not None:
        d.source = body.source
    if body.notes is not None:
        d.notes = body.notes
    if body.expected_close is not None:
        d.expected_close = _parse_date(body.expected_close)
    d.updated_at = sales._utcnow()
    db.commit()
    audit.record(db, action="deal.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="deal", target_id=str(d.id),
                 ip=_ip(request), detail=f"stage={d.stage}")
    return sales.deal_dict(db, d, with_quotes=True)


@router.delete("/api/deals/{deal_id}")
def delete_deal(deal_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(_STAFF)):
    d = _deal(db, deal_id)
    db.query(Quote).filter(Quote.deal_id == d.id).delete(synchronize_session=False)
    db.delete(d)
    db.commit()
    audit.record(db, action="deal.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="deal", target_id=str(deal_id),
                 ip=_ip(request), detail=d.title)
    return {"ok": True, "deleted": deal_id}


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #
class LineItemIn(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    recurring: bool = False


class QuoteIn(BaseModel):
    title: str | None = None
    line_items: list[LineItemIn] = []
    onboarding_fee: float = 0.0
    tax_rate: float = 0.0
    notes: str | None = None
    valid_days: int = 30


@router.post("/api/deals/{deal_id}/quotes")
def create_quote(deal_id: int, body: QuoteIn, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    d = _deal(db, deal_id)
    q = sales.create_quote(db, d, title=body.title,
                           line_items=[li.model_dump() for li in body.line_items],
                           onboarding_fee=body.onboarding_fee, tax_rate=body.tax_rate,
                           notes=body.notes, valid_days=body.valid_days, user_id=user.id)
    db.commit()
    audit.record(db, action="quote.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="quote", target_id=str(q.id),
                 ip=_ip(request), detail=f"{q.number} total={q.total}")
    return sales.quote_dict(q)


@router.get("/api/quotes/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    return sales.quote_dict(_quote(db, quote_id))


@router.put("/api/quotes/{quote_id}")
def update_quote(quote_id: int, body: QuoteIn, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    q = _quote(db, quote_id)
    try:
        sales.update_quote(db, q, title=body.title,
                           line_items=[li.model_dump() for li in body.line_items],
                           onboarding_fee=body.onboarding_fee, tax_rate=body.tax_rate,
                           notes=body.notes)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    audit.record(db, action="quote.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="quote", target_id=str(q.id),
                 ip=_ip(request), detail=f"total={q.total}")
    return sales.quote_dict(q)


@router.post("/api/quotes/{quote_id}/send")
def send_quote(quote_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(_STAFF)):
    q = _quote(db, quote_id)
    sales.send_quote(db, q)
    db.commit()
    audit.record(db, action="quote.send", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="quote", target_id=str(q.id),
                 ip=_ip(request), detail=q.number or "")
    base = str(request.base_url).rstrip("/")
    return {**sales.quote_dict(q), "accept_url": f"{base}/q/{q.public_token}"}


class QuoteAcceptIn(BaseModel):
    name: str
    title: str | None = None


@router.post("/api/quotes/{quote_id}/accept")
def staff_accept_quote(quote_id: int, body: QuoteAcceptIn, request: Request,
                       db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    """Owner records a verbal/written acceptance on the client's behalf."""
    q = _quote(db, quote_id)
    try:
        out = sales.accept_quote(db, q, name=body.name, title=body.title,
                                 ip=f"staff:{user.email}")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit.record(db, action="quote.accept.staff", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="quote", target_id=str(q.id),
                 ip=_ip(request), detail=f"client_id={out.get('client_id')}")
    return out


class QuoteDeclineIn(BaseModel):
    reason: str | None = None


@router.post("/api/quotes/{quote_id}/decline")
def decline_quote(quote_id: int, body: QuoteDeclineIn, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    q = _quote(db, quote_id)
    try:
        sales.decline_quote(db, q, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    return sales.quote_dict(q)


@router.delete("/api/quotes/{quote_id}")
def delete_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(_STAFF)):
    q = _quote(db, quote_id)
    db.delete(q)
    db.commit()
    return {"ok": True, "deleted": quote_id}


# --------------------------------------------------------------------------- #
# PUBLIC — prospect view + e-sign accept (no auth; token-gated)
# --------------------------------------------------------------------------- #
def _public_quote(db: Session, token: str) -> Quote:
    q = db.query(Quote).filter(Quote.public_token == token).first()
    if not q or not q.public_token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found")
    return q


@router.get("/api/public/quote/{token}")
def public_get_quote(token: str, db: Session = Depends(get_db)):
    q = _public_quote(db, token)
    if q.status == "sent" and not q.viewed_at:
        q.viewed_at = sales._utcnow()
        db.commit()
    return sales.public_quote_dict(db, q)


@router.post("/api/public/quote/{token}/accept")
def public_accept_quote(token: str, body: QuoteAcceptIn, request: Request,
                        db: Session = Depends(get_db)):
    q = _public_quote(db, token)
    if not (body.name or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please type your full name to sign.")
    try:
        out = sales.accept_quote(db, q, name=body.name, title=body.title, ip=_ip(request))
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return out


@router.post("/api/public/quote/{token}/decline")
def public_decline_quote(token: str, body: QuoteDeclineIn, db: Session = Depends(get_db)):
    q = _public_quote(db, token)
    try:
        sales.decline_quote(db, q, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    return {"ok": True, "status": q.status}


@router.get("/q/{token}", response_class=HTMLResponse)
def public_accept_page(token: str, db: Session = Depends(get_db)):
    # Validate the token server-side so a bad link 404s instead of rendering an
    # empty shell; the page then fetches the JSON itself.
    _public_quote(db, token)
    return HTMLResponse(_ACCEPT_PAGE.replace("__TOKEN__", token))


# Self-contained, branded accept page. Fetches /api/public/quote/{token}, renders
# the quote, and captures a typed signature with a visible IP+timestamp audit
# stamp to the RIGHT of the signature (consistent with the e-sign tool).
_ACCEPT_PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Review & Accept — BVTech</title>
<style>
 :root{--ink:#0f172a;--mut:#64748b;--line:#e2e8f0;--bg:#f1f5f9;--brand:#4440DB;--ok:#059669;--card:#fff}
 *{box-sizing:border-box}
 body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      color:var(--ink);background:var(--bg);-webkit-text-size-adjust:100%}
 .wrap{max-width:760px;margin:0 auto;padding:24px 16px 72px}
 .brand{display:flex;align-items:center;gap:10px;margin:8px 0 18px}
 .brand .logo{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#4440DB,#7c3aed);
      color:#fff;display:grid;place-items:center;font-weight:800}
 .brand b{font-size:17px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;
      box-shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(15,23,42,.05);margin-bottom:16px}
 h1{font-size:22px;margin:.1em 0 .2em} .sub{color:var(--mut);margin:0 0 6px}
 .meta{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--mut);font-size:13px;margin-top:8px}
 table{width:100%;border-collapse:collapse;margin:10px 0 2px}
 th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
 th{font-size:12px;letter-spacing:.03em;text-transform:uppercase;color:var(--mut)}
 td.r,th.r{text-align:right;white-space:nowrap}
 .tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;
      background:#eef2ff;color:#4338ca;margin-left:6px}
 .tot{display:flex;justify-content:flex-end;margin-top:8px}
 .tot table{width:auto;min-width:260px} .tot td{border:0;padding:4px 8px}
 .tot .grand td{font-size:18px;font-weight:800;border-top:2px solid var(--ink);padding-top:10px}
 .mrr{color:var(--ok);font-weight:700}
 .notes{white-space:pre-wrap;color:#334155;background:#f8fafc;border:1px solid var(--line);
      border-radius:10px;padding:12px;margin-top:10px;font-size:14px}
 label{display:block;font-weight:600;margin:12px 0 5px}
 .row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:200px}
 input[type=text]{width:100%;padding:12px 12px;border:1.5px solid #cbd5e1;border-radius:10px;
      font-size:16px;background:#fff;color:var(--ink)}
 input[type=text]:focus{outline:0;border-color:var(--brand);box-shadow:0 0 0 3px rgba(68,64,219,.16)}
 .sigbox{display:flex;gap:14px;align-items:stretch;margin-top:6px;flex-wrap:wrap}
 .sigpad{flex:1;min-width:240px;border:1.5px dashed #94a3b8;border-radius:12px;background:#fff;
      padding:14px 16px;min-height:74px;display:flex;align-items:center}
 .sigpad .sig{font-family:"Segoe Script","Brush Script MT",cursive;font-size:30px;color:#111827}
 .sigpad .ph{color:#94a3b8;font-size:14px}
 .stamp{width:230px;min-width:200px;border:1px solid var(--line);border-radius:12px;background:#f8fafc;
      padding:10px 12px;font-size:11.5px;color:var(--mut);line-height:1.5}
 .stamp b{color:#334155;display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}
 .cta{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap}
 button{font:inherit;font-weight:700;border:0;border-radius:11px;padding:13px 20px;cursor:pointer}
 .accept{background:var(--brand);color:#fff;flex:1;min-width:200px}
 .accept:disabled{opacity:.5;cursor:not-allowed}
 .decline{background:#fff;color:#64748b;border:1.5px solid var(--line)}
 .fine{color:var(--mut);font-size:12px;margin-top:12px}
 .done{text-align:center;padding:26px 10px}
 .done .big{font-size:46px}.done h2{margin:.2em 0}
 .err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:10px 12px;border-radius:10px;margin-top:12px;display:none}
 @media(max-width:560px){.stamp{width:100%}}
</style></head>
<body><div class="wrap">
 <div class="brand"><div class="logo">B</div><b>BVTech</b><span style="color:var(--mut)">Managed IT &amp; Security</span></div>
 <div id="app"><div class="card">Loading your proposal…</div></div>
 <p class="fine">Secured by BVTech • This proposal and your electronic signature are
   recorded with a timestamp and IP address for both parties' records. By signing you
   agree this constitutes a legally binding electronic signature.</p>
</div>
<script>
const TOKEN="__TOKEN__";
const $=s=>document.querySelector(s);
const money=(n,c)=>new Intl.NumberFormat('en-US',{style:'currency',currency:c||'USD'}).format(n||0);
let Q=null;
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));}
async function load(){
  try{
    const r=await fetch('/api/public/quote/'+TOKEN);
    if(!r.ok) throw new Error('not found');
    Q=await r.json(); render();
  }catch(e){ $('#app').innerHTML='<div class="card"><h1>Link not found</h1><p class="sub">This proposal link is invalid or has expired. Please contact BVTech for a fresh copy.</p></div>'; }
}
function lineRows(){
  return (Q.line_items||[]).map(i=>`<tr><td>${esc(i.description)}${i.recurring?'<span class="tag">monthly</span>':''}</td>
    <td class="r">${i.quantity}</td><td class="r">${money(i.unit_price,Q.currency)}</td>
    <td class="r">${money(i.amount,Q.currency)}</td></tr>`).join('');
}
function render(){
  if(Q.status==='accepted'){ return renderDone(); }
  const feeRow = Q.onboarding_fee>0 ? `<tr><td>One-time onboarding fee</td><td class="r">1</td>
      <td class="r">${money(Q.onboarding_fee,Q.currency)}</td><td class="r">${money(Q.onboarding_fee,Q.currency)}</td></tr>`:'';
  $('#app').innerHTML=`
   <div class="card">
     <h1>${esc(Q.title||'Service Proposal')}</h1>
     <p class="sub">Prepared for ${esc(Q.to_company||Q.to_name||'you')}</p>
     <div class="meta"><span>Quote <b>${esc(Q.number||'')}</b></span>
       ${Q.valid_until?`<span>Valid until ${esc(Q.valid_until.slice(0,10))}</span>`:''}</div>
     <table><thead><tr><th>Description</th><th class="r">Qty</th><th class="r">Price</th><th class="r">Amount</th></tr></thead>
       <tbody>${lineRows()}${feeRow}</tbody></table>
     <div class="tot"><table>
       <tr><td>Subtotal</td><td class="r">${money(Q.subtotal,Q.currency)}</td></tr>
       ${Q.tax_rate>0?`<tr><td>Tax (${Q.tax_rate}%)</td><td class="r">${money(Q.tax_amount,Q.currency)}</td></tr>`:''}
       <tr class="grand"><td>Due today</td><td class="r">${money(Q.total,Q.currency)}</td></tr>
       ${Q.mrr>0?`<tr><td class="mrr">Then monthly</td><td class="r mrr">${money(Q.mrr,Q.currency)}/mo</td></tr>`:''}
     </table></div>
     ${Q.notes?`<div class="notes">${esc(Q.notes)}</div>`:''}
   </div>
   <div class="card">
     <h1 style="font-size:18px">Accept &amp; sign</h1>
     <div class="row">
       <div><label for="nm">Full name</label><input id="nm" type="text" autocomplete="name" placeholder="Your full legal name" oninput="sync()"></div>
       <div><label for="ti">Title (optional)</label><input id="ti" type="text" autocomplete="organization-title" placeholder="e.g. Owner"></div>
     </div>
     <label>Signature</label>
     <div class="sigbox">
       <div class="sigpad"><span id="sigview" class="ph">Type your name above to sign</span></div>
       <div class="stamp"><b>Audit record</b>
         <div id="stamp">Signed on acceptance.<br>IP + timestamp captured automatically.</div></div>
     </div>
     <div class="err" id="err"></div>
     <div class="cta">
       <button class="accept" id="go" disabled onclick="accept()">Accept &amp; sign proposal</button>
       <button class="decline" onclick="decline()">Decline</button>
     </div>
   </div>`;
}
function sync(){
  const v=$('#nm').value.trim();
  $('#sigview').className=v?'sig':'ph';
  $('#sigview').textContent=v||'Type your name above to sign';
  $('#go').disabled=!v;
  $('#stamp').innerHTML=(v?('Signer: '+esc(v)+'<br>'):'')+'Date: '+new Date().toLocaleString()+'<br>IP captured on submit.';
}
async function accept(){
  const name=$('#nm').value.trim(); if(!name) return;
  $('#go').disabled=true; $('#go').textContent='Signing…'; $('#err').style.display='none';
  try{
    const r=await fetch('/api/public/quote/'+TOKEN+'/accept',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:name,title:$('#ti').value.trim()||null})});
    const d=await r.json();
    if(!r.ok) throw new Error(d.detail||'Could not record acceptance.');
    Q.status='accepted'; Q.accepted_name=name; Q.accepted_at=d.accepted_at||new Date().toISOString();
    renderDone();
  }catch(e){ $('#err').textContent=e.message; $('#err').style.display='block';
    $('#go').disabled=false; $('#go').textContent='Accept & sign proposal'; }
}
async function decline(){
  if(!confirm('Decline this proposal?')) return;
  try{ await fetch('/api/public/quote/'+TOKEN+'/decline',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({})});}catch(e){}
  $('#app').innerHTML='<div class="card done"><div class="big">✓</div><h2>Thanks for letting us know</h2><p class="sub">We\'ve recorded that you\'ve declined. Reach out anytime if things change.</p></div>';
}
function renderDone(){
  $('#app').innerHTML=`<div class="card done"><div class="big" style="color:var(--ok)">✓</div>
    <h2>Proposal accepted — welcome aboard!</h2>
    <p class="sub">Signed by <b>${esc(Q.accepted_name||'')}</b>${Q.accepted_at?(' on '+new Date(Q.accepted_at).toLocaleString()):''}.</p>
    <p class="sub">BVTech will reach out shortly to kick off onboarding. A copy of this
    signed proposal is on file for your records.</p></div>`;
}
load();
</script></body></html>"""
