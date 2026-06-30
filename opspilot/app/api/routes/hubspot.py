"""v0.49 HubSpot connector — sync Pulse CRM contacts to HubSpot. Staff-only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import CrmContact, Role, User
from ...services import audit, crm, hubspot, secure_config

router = APIRouter(prefix="/api/hubspot", tags=["hubspot"])

PROVIDER = "hubspot"


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _client(db: Session) -> hubspot.HubSpotClient:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    token = secure_config.get_secret(cfg, "token")
    if not token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "HubSpot not configured — add a private-app token in Settings.")
    return hubspot.HubSpotClient(str(token))


class HSSettingsIn(BaseModel):
    token: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    return {"configured": secure_config.configured(cfg, ("token",)),
            "fields": secure_config.public_view(cfg)}


@router.put("/settings")
def save_settings(body: HSSettingsIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, PROVIDER, "HubSpot", "CRM", payload)
    audit.record(db, action="hubspot.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="hubspot token")
    cfg = conn.config or {}
    return {"ok": True, "configured": secure_config.configured(cfg, ("token",)),
            "fields": secure_config.public_view(cfg)}


@router.post("/test")
def test(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    client = _client(db)
    try:
        client.whoami()
    except hubspot.HubSpotError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    return {"ok": True}


@router.post("/contacts/{contact_id}/push")
def push_contact(contact_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(CrmContact, contact_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found")
    client = _client(db)
    try:
        hs_id = client.upsert_contact(email=c.email, name=c.name, phone=c.phone, company=c.company)
        if c.notes:
            client.log_note(hs_id, c.notes)
    except hubspot.HubSpotError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    crm.log_activity(db, c, "note", subject="Synced to HubSpot",
                     body=f"hubspot_id={hs_id}", user_id=user.id)
    audit.record(db, action="hubspot.push_contact", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="crm_contact", target_id=str(c.id),
                 ip=_ip(request), detail=f"hubspot={hs_id}")
    return {"ok": True, "hubspot_id": hs_id}
