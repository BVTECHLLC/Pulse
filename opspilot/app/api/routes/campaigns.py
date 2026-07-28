"""v0.45 Campaigns — email (M365) + SMS (Dialpad) outreach to CRM contacts.

Reuses the already-configured M365 mailbox and Dialpad credentials. Compliance
(CAN-SPAM do-not-contact + footer, TCPA sms opt-in) and timeline logging live in
services/campaigns.py. Staff-only; sends are OWNER/TECH and audited.
"""
from __future__ import annotations

import json
from urllib import error
from urllib import request as urlrequest

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, campaigns, m365, secure_config
from .mailbox import PROVIDER as MAILBOX_PROVIDER, _client_for as _mailbox_client

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

DIALPAD_SMS_API = "https://dialpad.com/api/v2/sms"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #
class EmailCampaignIn(BaseModel):
    subject: str
    body: str
    ids: list[int] | None = None
    status: str | None = None
    market: str | None = None
    dry_run: bool = False


@router.post("/email")
def email_campaign(body: EmailCampaignIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.subject.strip() or not body.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "subject and body are required")
    contacts = campaigns.select_contacts(db, ids=body.ids, status=body.status,
                                          market=body.market, channel="email")
    if not contacts:
        return {"audience": 0, "sent": 0, "failed": 0, "dry_run": body.dry_run,
                "note": "No eligible contacts (need an email + not do-not-contact)."}

    graph = sender = None
    if not body.dry_run:
        graph, sender = _mailbox_client(db)  # raises 503 if mailbox unconfigured

    def send_fn(to: str, subject: str, text: str) -> None:
        graph.send_mail(sender, [to], subject, text, html=False)

    try:
        result = campaigns.run_email(db, send_fn, contacts, body.subject, body.body,
                                     sender or "Pulse", dry_run=body.dry_run, user_id=user.id)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    if not body.dry_run:
        audit.record(db, action="campaign.email", actor_user_id=user.id, actor_email=user.email,
                     actor_role=user.role.value, target_type="campaign", target_id="email",
                     ip=_ip(request), detail=f"sent={result['sent']} audience={result['audience']}")
    return result


# --------------------------------------------------------------------------- #
# SMS (Dialpad)
# --------------------------------------------------------------------------- #
class SmsCampaignIn(BaseModel):
    message: str
    ids: list[int] | None = None
    status: str | None = None
    market: str | None = None
    dry_run: bool = False


def _dialpad_sms_sender(db: Session):
    cfg = (secure_config.get_platform(db, "dialpad") or None)
    cfg = (cfg.config if cfg else None) or {}
    api_key = secure_config.get_secret(cfg, "api_key")
    user_id = secure_config.get_secret(cfg, "user_id") or cfg.get("user_id")
    from_number = cfg.get("caller_number")
    if not (api_key and (user_id or from_number)):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Dialpad not configured — add it in Settings → Dialpad.")

    def send_fn(to: str, text: str) -> None:
        payload = {"to_numbers": [to], "text": text, "infer_country_code": True}
        if from_number:
            payload["from_number"] = str(from_number)
        if user_id:
            payload["user_id"] = str(user_id)
        req = urlrequest.Request(DIALPAD_SMS_API, data=json.dumps(payload).encode(),
                                 method="POST", headers={"Authorization": f"Bearer {api_key}",
                                                         "Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=30) as r:
                r.read()
        except error.HTTPError as e:
            raise RuntimeError(f"Dialpad SMS HTTP {e.code}: {e.read().decode(errors='replace')[:160]}")
    return send_fn


@router.post("/sms")
def sms_campaign(body: SmsCampaignIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not body.message.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "message is required")
    contacts = campaigns.select_contacts(db, ids=body.ids, status=body.status,
                                          market=body.market, channel="sms")
    if not contacts:
        return {"audience": 0, "sent": 0, "failed": 0, "dry_run": body.dry_run,
                "note": "No eligible contacts (need a phone + SMS opt-in for TCPA)."}
    send_fn = (lambda to, text: None) if body.dry_run else _dialpad_sms_sender(db)
    result = campaigns.run_sms(db, send_fn, contacts, body.message,
                               dry_run=body.dry_run, user_id=user.id)
    if not body.dry_run:
        audit.record(db, action="campaign.sms", actor_user_id=user.id, actor_email=user.email,
                     actor_role=user.role.value, target_type="campaign", target_id="sms",
                     ip=_ip(request), detail=f"sent={result['sent']} audience={result['audience']}")
    return result


# --------------------------------------------------------------------------- #
# v1.56 OUTBOUND — the autonomous daily acquisition engine (services/outbound).
# Status / config / one-off test send / run-now, all OWNER-only + audited.
# --------------------------------------------------------------------------- #
from datetime import datetime, timezone as _tz

from ...core.config import get_settings as _get_settings
from ...services import outbound as outbound_svc


@router.get("/outbound/status")
def outbound_status(db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER))):
    """One card: config, transport, lead counts, and today's would-be batch."""
    from ...models import CrmContact
    cfg = outbound_svc.get_config(db)
    send_fn, transport = outbound_svc.resolve_send_fn(db)
    now = datetime.now(_tz.utc)
    plan = outbound_svc.run_daily(db, lambda *a: None, now,
                                  force=True, dry_run=True)
    total = db.query(CrmContact).filter(CrmContact.email.isnot(None)).count()
    dnc = db.query(CrmContact).filter(CrmContact.do_not_contact.is_(True)).count()
    return {"config": {k: cfg[k] for k in ("enabled", "target", "sender", "reply_to",
                                           "physical_address", "started_on",
                                           "test_sent_on")},
            "env_mode": outbound_svc._env_mode(),
            "transport": transport, "transport_ready": send_fn is not None,
            "leads_with_email": total, "do_not_contact": dnc,
            "today": {"cap": plan.get("cap"), "day_index": plan.get("day_index"),
                      "already_sent": plan.get("already_sent_today"),
                      "eligible": plan.get("eligible"),
                      "plan_preview": (plan.get("plan") or [])[:10]}}


class OutboundConfigIn(BaseModel):
    enabled: bool | None = None
    sender: str | None = None
    reply_to: str | None = None
    physical_address: str | None = None
    target: int | None = None


@router.put("/outbound/config")
def outbound_config(body: OutboundConfigIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER))):
    cfg = outbound_svc.save_config(db, enabled=body.enabled, sender=body.sender,
                                   reply_to=body.reply_to,
                                   physical_address=body.physical_address,
                                   target=body.target)
    audit.record(db, action="outbound.config", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="campaign", target_id="outbound", ip=_ip(request),
                 detail=f"enabled={cfg['enabled']} target={cfg['target']}")
    return {k: cfg[k] for k in ("enabled", "target", "sender", "reply_to",
                                "physical_address")}


class OutboundTestIn(BaseModel):
    to: str | None = None       # defaults to the shop's SUPPORT_EMAIL


@router.post("/outbound/test-send")
def outbound_test_send(body: OutboundTestIn, request: Request,
                       db: Session = Depends(get_db),
                       user: User = Depends(require_roles(Role.OWNER))):
    """Send ONE fully rendered sample (touch 1 of 3) to your own inbox — never
    to a lead. The fastest way to see exactly what a lead would receive."""
    cfg = outbound_svc.get_config(db)
    if not cfg["sender"] or not cfg["physical_address"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Set sender + physical_address first (CAN-SPAM).")
    send_fn, transport = outbound_svc.resolve_send_fn(db)
    if send_fn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, transport)
    to = (body.to or _get_settings().SUPPORT_EMAIL).strip()
    subject, text = outbound_svc.render(
        0, type("C", (), {"name": "Alex Carter", "company": "Carter & Co"})(),
        cfg["sender"], cfg["physical_address"])
    try:
        send_fn(to, f"[Pulse sample] {subject}", text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)[:200])
    audit.record(db, action="outbound.test_send", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="campaign", target_id="outbound", ip=_ip(request),
                 detail=f"to={to} via {transport}")
    return {"ok": True, "to": to, "transport": transport, "subject": subject}


class OutboundRunIn(BaseModel):
    dry_run: bool = True


@router.post("/outbound/run")
def outbound_run(body: OutboundRunIn, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    """Preview (dry_run, default) or fire today's real batch right now. Real
    sends require the program to be enabled — the ramp/caps still apply."""
    now = datetime.now(_tz.utc)
    if body.dry_run:
        return outbound_svc.run_daily(db, lambda *a: None, now,
                                      force=True, dry_run=True)
    cfg = outbound_svc.get_config(db)
    if not cfg["enabled"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Enable the program first (PUT /outbound/config "
                            "enabled=true, or PULSE_OUTBOUND=live on the box).")
    send_fn, transport = outbound_svc.resolve_send_fn(db)
    if send_fn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, transport)
    out = outbound_svc.run_daily(db, send_fn, now)
    out["transport"] = transport
    audit.record(db, action="outbound.run", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="campaign", target_id="outbound", ip=_ip(request),
                 detail=f"sent={out.get('sent')} cap={out.get('cap')}")
    return out
