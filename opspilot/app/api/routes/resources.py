"""Core resource routes: clients, devices, licenses, audit log."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from sqlalchemy import func

from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import (
    Client, Device, DeviceCheckin, DevicePatch, DeviceSoftware, License,
    AuditLog, Role, User,
)
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
    staff = is_staff(user)
    return [
        {"id": c.id, "name": c.name, "primary_contact": c.primary_contact,
         "email": c.email, "phone": c.phone, "is_active": c.is_active,
         **({"sso_domains": c.sso_domains or []} if staff else {})}
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


class OnboardIn(BaseModel):
    name: str
    contact_email: str          # becomes the client's first portal login
    contact_name: str | None = None
    phone: str | None = None
    site_address: str | None = None
    sso_domains: list[str] | str | None = None   # authorize zero-touch SSO (v0.91)


@router.post("/clients/onboard", status_code=201)
def onboard_client(body: OnboardIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """One-action client onboarding: create the client, provision their first
    CLIENT_ADMIN portal login, email a welcome, and hand back an agent-enrollment
    token — so a new client (or a new franchise location's client) is fully set up
    in a single step, the same way every time."""
    from ...core.security import hash_password, random_token, mint_enrollment_token
    from ...services import email as email_svc, sso_provision

    email_l = (body.contact_email or "").strip().lower()
    if "@" not in email_l:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid contact email is required.")
    if db.query(User).filter(User.email == email_l).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has a login.")

    # Authorize zero-touch SSO for the contact's own domain by default (unless it's
    # a free mailbox), plus anything explicitly passed. So a client's team can sign
    # in themselves from day one.
    domains = sso_provision.normalize_domains(body.sso_domains) if body.sso_domains is not None \
        else sso_provision.normalize_domains(email_l.rsplit("@", 1)[-1])

    c = Client(name=body.name[:200], primary_contact=body.contact_name, email=email_l,
               phone=body.phone, site_address=body.site_address, sso_domains=domains)
    db.add(c)
    db.flush()

    temp_pw = random_token(12)
    admin = User(email=email_l, full_name=body.contact_name,
                 password_hash=hash_password(temp_pw), role=Role.CLIENT_ADMIN,
                 client_id=c.id, is_active=True)
    db.add(admin)
    db.commit()

    emailed = email_svc.send_invite(email_l, body.contact_name, temp_pw, "client admin")
    # A ready-to-use enrollment token so the client can install the agent now.
    try:
        enroll_token = mint_enrollment_token(client_id=c.id)
    except Exception:
        enroll_token = None
    audit.record(db, action="client.onboard", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="client", target_id=str(c.id),
                 client_id=c.id, ip=_ip(request), detail=f"onboarded {c.name}")
    return {"client_id": c.id, "portal_user": email_l, "temp_password": temp_pw,
            "emailed": emailed, "enroll_token": enroll_token, "sso_domains": domains}


class SSODomainsIn(BaseModel):
    sso_domains: list[str] | str | None = None


@router.get("/clients/{client_id}/sso-domains")
def get_client_sso_domains(client_id: int, db: Session = Depends(get_db),
                           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return {"client_id": client_id, "sso_domains": c.sso_domains or []}


@router.put("/clients/{client_id}/sso-domains")
def set_client_sso_domains(client_id: int, body: SSODomainsIn, request: Request,
                           db: Session = Depends(get_db),
                           user: User = Depends(require_roles(Role.OWNER))):
    """Set the email domains authorized to zero-touch-provision read-only logins
    for this client. Free/public mailbox domains are dropped for safety."""
    from ...services import sso_provision
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    domains = sso_provision.normalize_domains(body.sso_domains)
    c.sso_domains = domains
    db.commit()
    audit.record(db, action="client.sso_domains", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="client", target_id=str(client_id),
                 client_id=client_id, ip=_ip(request), detail=",".join(domains) or "(cleared)")
    return {"client_id": client_id, "sso_domains": domains}


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
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    # Online if seen within 3 check-in intervals (agent reports ~every 60s).
    online_cutoff = now - timedelta(seconds=180)
    out = []
    for d in q.order_by(Device.hostname).all():
        lc = d.last_checkin
        if lc is not None and lc.tzinfo is None:
            lc = lc.replace(tzinfo=timezone.utc)
        out.append({
            "id": d.id, "client_id": d.client_id, "hostname": d.hostname,
            "os": d.os, "ip": d.ip, "cpu_pct": d.cpu_pct, "ram_pct": d.ram_pct,
            "disk_pct": d.disk_pct, "av_status": d.av_status, "patch_status": d.patch_status,
            "patches_pending": d.patches_pending, "health_score": d.health_score,
            "last_checkin": d.last_checkin.isoformat() if d.last_checkin else None,
            "agent_version": d.agent_version, "platform": d.platform,
            "logged_in_user": d.logged_in_user,
            "online": bool(lc and lc >= online_cutoff),
        })
    return out


# --------------------------------------------------------------------------- #
# Software inventory (v0.19) — reported by the agent, read here with tenant RBAC
# --------------------------------------------------------------------------- #
@router.get("/devices/{device_id}/detail")
def device_detail(device_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    """Device 360 — everything about one endpoint in a single call: live health,
    open alerts, and inventory/patch counts. Powers the drill-down modal."""
    from datetime import datetime, timedelta, timezone
    from ...models import Alert, AlertStatus, DevicePatch, DeviceSoftware
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)
    now = datetime.now(timezone.utc)
    lc = dev.last_checkin
    if lc is not None and lc.tzinfo is None:
        lc = lc.replace(tzinfo=timezone.utc)
    alerts = (db.query(Alert)
              .filter(Alert.device_id == device_id, Alert.status != AlertStatus.RESOLVED)
              .order_by(Alert.severity, Alert.last_seen.desc()).all())
    sw_count = db.query(DeviceSoftware).filter(DeviceSoftware.device_id == device_id).count()
    return {
        "id": dev.id, "client_id": dev.client_id, "client_name": (dev.client.name if dev.client else None),
        "hostname": dev.hostname, "os": dev.os, "serial": dev.serial, "ip": dev.ip,
        "platform": dev.platform, "agent_version": dev.agent_version,
        "logged_in_user": dev.logged_in_user, "av_status": dev.av_status,
        "patch_status": dev.patch_status, "patches_pending": dev.patches_pending or 0,
        "cpu_pct": dev.cpu_pct, "ram_pct": dev.ram_pct, "disk_pct": dev.disk_pct,
        "health_score": dev.health_score,
        "last_checkin": dev.last_checkin.isoformat() if dev.last_checkin else None,
        "online": bool(lc and lc >= now - timedelta(seconds=180)),
        "software_count": sw_count,
        "alerts": [{"id": a.id, "kind": a.kind, "severity": a.severity.value,
                    "message": a.message, "status": a.status.value,
                    "first_seen": a.first_seen.isoformat() if a.first_seen else None}
                   for a in alerts],
    }


@router.get("/devices/{device_id}/software")
def device_software(device_id: int, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)   # staff-any or own-client only
    rows = (db.query(DeviceSoftware)
            .filter(DeviceSoftware.device_id == device_id)
            .order_by(DeviceSoftware.name).all())
    return {
        "device_id": device_id, "hostname": dev.hostname, "count": len(rows),
        "software": [{"name": r.name, "version": r.version, "publisher": r.publisher,
                      "reported_at": r.reported_at.isoformat() if r.reported_at else None}
                     for r in rows],
    }


@router.get("/software/search")
def software_search(q: str = "", client_id: int | None = None,
                    db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Fleet-wide 'who has this app?' — aggregates install counts by name+version
    across devices the caller may see. Powers license reconciliation and
    vulnerability response ('which machines run OpenSSL 3.0.1?')."""
    query = (db.query(DeviceSoftware.name, DeviceSoftware.version,
                      func.count(func.distinct(DeviceSoftware.device_id)).label("devices"))
             .group_by(DeviceSoftware.name, DeviceSoftware.version))
    if is_staff(user):
        if client_id:
            query = query.filter(DeviceSoftware.client_id == client_id)
    else:
        query = query.filter(DeviceSoftware.client_id == user.client_id)
    if q.strip():
        query = query.filter(DeviceSoftware.name.ilike(f"%{q.strip()}%"))
    rows = query.order_by(func.count(func.distinct(DeviceSoftware.device_id)).desc(),
                          DeviceSoftware.name).limit(200).all()
    return [{"name": n, "version": v, "devices": d} for (n, v, d) in rows]


# --------------------------------------------------------------------------- #
# Patch management (v0.20) — pending OS/software updates reported by the agent
# --------------------------------------------------------------------------- #
@router.get("/devices/{device_id}/patches")
def device_patches(device_id: int, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)
    rows = (db.query(DevicePatch)
            .filter(DevicePatch.device_id == device_id)
            .order_by(DevicePatch.severity, DevicePatch.name).all())
    return {
        "device_id": device_id, "hostname": dev.hostname,
        "pending": dev.patches_pending or 0,
        "patches": [{"name": r.name, "kb": r.kb, "severity": r.severity} for r in rows],
    }


# --------------------------------------------------------------------------- #
# Metric history (v0.20) — recent check-in trend for sparkline charts
# --------------------------------------------------------------------------- #
@router.get("/devices/{device_id}/metrics")
def device_metrics(device_id: int, limit: int = 50, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)
    limit = max(1, min(limit, 500))
    rows = (db.query(DeviceCheckin)
            .filter(DeviceCheckin.device_id == device_id)
            .order_by(DeviceCheckin.ts.desc()).limit(limit).all())
    rows = list(reversed(rows))   # oldest -> newest for charting
    return {
        "device_id": device_id, "hostname": dev.hostname, "points": len(rows),
        "series": [
            {"ts": r.ts.isoformat() if r.ts else None, "cpu_pct": r.cpu_pct,
             "ram_pct": r.ram_pct, "disk_pct": r.disk_pct, "health_score": r.health_score}
            for r in rows
        ],
    }


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
