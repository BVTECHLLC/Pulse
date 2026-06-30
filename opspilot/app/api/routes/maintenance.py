"""v0.39 Maintenance windows — schedule periods where monitoring alerts are
suppressed (patching, reboots, migrations). Staff manage; the monitoring engine
checks `in_maintenance()` before opening any alert. Tenant-scoped reads."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import Device, MaintenanceWindow, Role, User
from ...services import audit

router = APIRouter(prefix="/api", tags=["maintenance"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(w: MaintenanceWindow, now: datetime) -> dict:
    s = w.starts_at if w.starts_at.tzinfo else w.starts_at.replace(tzinfo=timezone.utc)
    e = w.ends_at if w.ends_at.tzinfo else w.ends_at.replace(tzinfo=timezone.utc)
    state = "active" if s <= now <= e else ("scheduled" if now < s else "ended")
    return {"id": w.id, "client_id": w.client_id, "device_id": w.device_id,
            "starts_at": s.isoformat(), "ends_at": e.isoformat(),
            "reason": w.reason, "state": state}


class WindowIn(BaseModel):
    client_id: int
    device_id: int | None = None
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None


@router.post("/maintenance-windows", status_code=201)
def create_window(body: WindowIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    assert_client_access(user, body.client_id)
    if body.ends_at <= body.starts_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ends_at must be after starts_at")
    if body.device_id is not None:
        dev = db.get(Device, body.device_id)
        if not dev or dev.client_id != body.client_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "device not in this client")
    w = MaintenanceWindow(client_id=body.client_id, device_id=body.device_id,
                          starts_at=body.starts_at, ends_at=body.ends_at,
                          reason=(body.reason or None), created_by_user_id=user.id)
    db.add(w)
    db.commit()
    audit.record(db, action="maintenance.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="maintenance_window", target_id=str(w.id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"device={body.device_id or 'all'} {body.starts_at}..{body.ends_at}")
    return _serialize(w, datetime.now(timezone.utc))


@router.get("/maintenance-windows")
def list_windows(client_id: int | None = Query(default=None),
                 active_only: bool = Query(default=False),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    q = db.query(MaintenanceWindow)
    if not is_staff(user):
        q = q.filter(MaintenanceWindow.client_id == user.client_id)
    elif client_id is not None:
        assert_client_access(user, client_id)
        q = q.filter(MaintenanceWindow.client_id == client_id)
    if active_only:
        q = q.filter(MaintenanceWindow.starts_at <= now, MaintenanceWindow.ends_at >= now)
    rows = q.order_by(MaintenanceWindow.starts_at.desc()).limit(500).all()
    return [_serialize(w, now) for w in rows]


@router.delete("/maintenance-windows/{window_id}")
def delete_window(window_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    w = db.get(MaintenanceWindow, window_id)
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Window not found")
    assert_client_access(user, w.client_id)
    cid = w.client_id
    db.delete(w)
    db.commit()
    audit.record(db, action="maintenance.delete", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="maintenance_window",
                 target_id=str(window_id), client_id=cid, ip=_ip(request))
    return {"ok": True}
