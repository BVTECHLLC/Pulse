"""v0.27 asset management (CMDB) — track every non-agent asset + warranties.

Staff manage; the owning client can view their own inventory (read-only). The
warranty view surfaces what's expiring so nothing lapses silently."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import ASSET_STATUSES, ASSET_TYPES, Asset, Client, Role, User
from ...services import audit

router = APIRouter(prefix="/api/assets", tags=["assets"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _aware(dt):
    return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)


def _out(a: Asset, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    we = _aware(a.warranty_expires)
    warranty = None
    if we:
        days = (we - now).days
        warranty = "expired" if days < 0 else ("expiring" if days <= 60 else "ok")
    return {
        "id": a.id, "client_id": a.client_id, "name": a.name, "asset_type": a.asset_type,
        "make": a.make, "model": a.model, "serial": a.serial, "asset_tag": a.asset_tag,
        "location": a.location, "assigned_to": a.assigned_to, "status": a.status,
        "cost": a.cost, "device_id": a.device_id, "notes": a.notes,
        "purchase_date": _aware(a.purchase_date).isoformat() if a.purchase_date else None,
        "warranty_expires": we.isoformat() if we else None,
        "warranty_state": warranty,
    }


def _get(db: Session, user: User, asset_id: int) -> Asset:
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    assert_client_access(user, a.client_id)
    return a


class AssetIn(BaseModel):
    client_id: int
    name: str
    asset_type: str = "other"
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    asset_tag: str | None = None
    location: str | None = None
    assigned_to: str | None = None
    status: str = "active"
    purchase_date: datetime | None = None
    warranty_expires: datetime | None = None
    cost: float | None = None
    device_id: int | None = None
    notes: str | None = None


@router.get("/meta")
def meta():
    return {"types": ASSET_TYPES, "statuses": ASSET_STATUSES}


@router.get("")
def list_assets(client_id: int | None = None, asset_type: str | None = None,
                status_filter: str | None = None, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    q = db.query(Asset)
    if is_staff(user):
        if client_id:
            q = q.filter(Asset.client_id == client_id)
    else:
        q = q.filter(Asset.client_id == user.client_id)
    if asset_type:
        q = q.filter(Asset.asset_type == asset_type)
    if status_filter:
        q = q.filter(Asset.status == status_filter)
    now = datetime.now(timezone.utc)
    return [_out(a, now) for a in q.order_by(Asset.name).all()]


@router.get("/warranty-expiring")
def warranty_expiring(days: int = 60, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    """Assets whose warranty has expired or expires within `days` — so nothing
    lapses unnoticed."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=max(0, days))
    q = db.query(Asset).filter(Asset.warranty_expires.isnot(None), Asset.warranty_expires <= cutoff)
    if not is_staff(user):
        q = q.filter(Asset.client_id == user.client_id)
    rows = q.order_by(Asset.warranty_expires).all()
    return [_out(a, now) for a in rows]


@router.post("", status_code=201)
def create_asset(body: AssetIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    atype = body.asset_type if body.asset_type in ASSET_TYPES else "other"
    st = body.status if body.status in ASSET_STATUSES else "active"
    a = Asset(client_id=body.client_id, name=body.name.strip(), asset_type=atype,
              make=body.make, model=body.model, serial=body.serial, asset_tag=body.asset_tag,
              location=body.location, assigned_to=body.assigned_to, status=st,
              purchase_date=body.purchase_date, warranty_expires=body.warranty_expires,
              cost=body.cost, device_id=body.device_id, notes=body.notes)
    db.add(a)
    db.commit()
    audit.record(db, action="asset.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="asset", target_id=str(a.id),
                 client_id=a.client_id, ip=_ip(request), detail=f"{a.asset_type}:{a.name}")
    return _out(a)


class AssetPatch(BaseModel):
    name: str | None = None
    asset_type: str | None = None
    make: str | None = None
    model: str | None = None
    serial: str | None = None
    asset_tag: str | None = None
    location: str | None = None
    assigned_to: str | None = None
    status: str | None = None
    purchase_date: datetime | None = None
    warranty_expires: datetime | None = None
    cost: float | None = None
    device_id: int | None = None
    notes: str | None = None


@router.patch("/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    a = _get(db, user, asset_id)
    data = body.model_dump(exclude_unset=True)
    if "asset_type" in data and data["asset_type"] not in ASSET_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid asset_type")
    if "status" in data and data["status"] not in ASSET_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    for k, v in data.items():
        setattr(a, k, v.strip() if isinstance(v, str) and k == "name" else v)
    db.commit()
    return _out(a)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    a = _get(db, user, asset_id)
    db.delete(a)
    db.commit()
