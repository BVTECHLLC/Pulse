"""Core resource routes: clients, devices, licenses, audit log."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Client, Device, License, AuditLog, Role, User
from ...services import audit

router = APIRouter(prefix="/api", tags=["resources"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


# --------------------------------------------------------------------------- #
# Clients (staff only for write; clients see just themselves)
# --------------------------------------------------------------------------- #
class ClientIn(BaseModel):
    name: str
    primary_contact: str | None = None
    email: str | None = None
    phone: str | None = None
    site_address: str | None = None
    notes: str | None = None


@router.get("/clients")
def list_clients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Client)
    if not is_staff(user):
        q = q.filter(Client.id == user.client_id)
    return [
        {"id": c.id, "name": c.name, "primary_contact": c.primary_contact,
         "email": c.email, "phone": c.phone, "is_active": c.is_active}
        for c in q.order_by(Client.name).all()
    ]


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = Client(**body.model_dump())
    db.add(c)
    db.commit()
    audit.record(db, action="client.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="client", target_id=str(c.id),
                 client_id=c.id, ip=_ip(request), detail=f"name={c.name}")
    return {"id": c.id}


# --------------------------------------------------------------------------- #
# Devices
# --------------------------------------------------------------------------- #
@router.get("/devices")
def list_devices(client_id: int | None = None, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    q = db.query(Device)
    if is_staff(user):
        if client_id:
            q = q.filter(Device.client_id == client_id)
    else:
        q = q.filter(Device.client_id == user.client_id)
    out = []
    for d in q.order_by(Device.hostname).all():
        out.append({
            "id": d.id, "client_id": d.client_id, "hostname": d.hostname,
            "os": d.os, "ip": d.ip, "cpu_pct": d.cpu_pct, "ram_pct": d.ram_pct,
            "disk_pct": d.disk_pct, "av_status": d.av_status, "patch_status": d.patch_status,
            "health_score": d.health_score,
            "last_checkin": d.last_checkin.isoformat() if d.last_checkin else None,
        })
    return out


# --------------------------------------------------------------------------- #
# Licenses
# --------------------------------------------------------------------------- #
class LicenseIn(BaseModel):
    client_id: int
    product: str
    seats: int | None = None
    seats_used: int | None = None
    monthly_cost: float | None = None
    vendor: str | None = None
    renewal_date: datetime | None = None
    notes: str | None = None


@router.get("/licenses")
def list_licenses(client_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = db.query(License)
    if is_staff(user):
        if client_id:
            q = q.filter(License.client_id == client_id)
    else:
        q = q.filter(License.client_id == user.client_id)
    return [
        {"id": l.id, "client_id": l.client_id, "product": l.product, "seats": l.seats,
         "seats_used": l.seats_used, "monthly_cost": l.monthly_cost, "vendor": l.vendor,
         "renewal_date": l.renewal_date.isoformat() if l.renewal_date else None}
        for l in q.order_by(License.product).all()
    ]


@router.post("/licenses", status_code=201)
def create_license(body: LicenseIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    assert_client_access(user, body.client_id)
    l = License(**body.model_dump())
    db.add(l)
    db.commit()
    audit.record(db, action="license.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="license", target_id=str(l.id),
                 client_id=l.client_id, ip=_ip(request), detail=f"product={l.product}")
    return {"id": l.id}


# --------------------------------------------------------------------------- #
# Audit log (staff only)
# --------------------------------------------------------------------------- #
@router.get("/audit")
def list_audit(limit: int = 100, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    limit = max(1, min(limit, 500))
    rows = db.query(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).all()
    return [
        {"ts": r.ts.isoformat(), "actor_email": r.actor_email, "actor_role": r.actor_role,
         "action": r.action, "target_type": r.target_type, "target_id": r.target_id,
         "client_id": r.client_id, "ip": r.ip, "success": r.success, "detail": r.detail}
        for r in rows
    ]
