"""v0.15 notification channels — staff-managed delivery targets (email / Slack /
Teams / generic webhook) that the automation `notify` action fans out to."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import CHANNEL_TYPES, Client, NotificationChannel, Role, SEVERITY_RANK, User
from ...services import audit, notifications

router = APIRouter(prefix="/api/notification-channels", tags=["notification-channels"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(c: NotificationChannel) -> dict:
    # Mask the target a little so webhook secrets aren't echoed in full.
    t = c.target
    shown = t if c.type == "email" else (t[:40] + "…" if len(t) > 42 else t)
    return {"id": c.id, "name": c.name, "type": c.type, "target": shown,
            "min_severity": c.min_severity, "client_id": c.client_id, "enabled": c.enabled}


class ChannelIn(BaseModel):
    name: str
    type: str
    target: str
    min_severity: str = "info"
    client_id: int | None = None


@router.get("")
def list_channels(db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return [_serialize(c) for c in db.query(NotificationChannel).order_by(NotificationChannel.name).all()]


@router.post("", status_code=201)
def create_channel(body: ChannelIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if body.type not in CHANNEL_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"type must be one of {list(CHANNEL_TYPES)}")
    if body.min_severity not in SEVERITY_RANK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"min_severity must be one of {list(SEVERITY_RANK)}")
    if not body.target.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "target is required")
    if body.type != "email" and not body.target.startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "webhook target must be an http(s) URL")
    if body.client_id is not None and not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    c = NotificationChannel(name=body.name[:120], type=body.type, target=body.target.strip(),
                            min_severity=body.min_severity, client_id=body.client_id)
    db.add(c)
    db.commit()
    audit.record(db, action="channel.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="notification_channel", target_id=str(c.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"type={c.type}")
    return {"id": c.id}


class ChannelUpdate(BaseModel):
    enabled: bool | None = None
    min_severity: str | None = None


@router.patch("/{channel_id}")
def update_channel(channel_id: int, body: ChannelUpdate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(NotificationChannel, channel_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    if body.enabled is not None:
        c.enabled = body.enabled
    if body.min_severity is not None:
        if body.min_severity not in SEVERITY_RANK:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid min_severity")
        c.min_severity = body.min_severity
    db.commit()
    return _serialize(c)


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    c = db.get(NotificationChannel, channel_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    db.delete(c)
    db.commit()
    audit.record(db, action="channel.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="notification_channel",
                 target_id=str(channel_id), ip=_ip(request))
    return {"ok": True}


@router.post("/{channel_id}/test")
def test_channel(channel_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(NotificationChannel, channel_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found")
    ok = notifications.deliver(c, "BVTech OpsPilot test notification — your channel works! ✅", "info")
    return {"ok": ok, "detail": "Delivered" if ok else "Delivery failed (check the target/URL)"}
