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
