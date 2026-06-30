"""v0.33 Predictive Foresight API.

Per-device forecast (days-to-disk-full, resource/health trajectory) and a
fleet-wide risk roll-up. Read-only, tenant-scoped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff
from ...models import Device, User
from ...services import foresight as fs

router = APIRouter(prefix="/api", tags=["foresight"])

# Severity ordering so the fleet view leads with the most urgent risks.
_SEV = {"critical": 3, "high": 2, "medium": 1, "low": 0}


@router.get("/devices/{device_id}/forecast")
def device_forecast(device_id: int, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    assert_client_access(user, dev.client_id)
    return fs.forecast_device(db, dev)


@router.get("/foresight")
def fleet_foresight(client_id: int | None = Query(default=None),
                    db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Fleet-wide predictive risks, most urgent first. Staff see all clients (or
    one via ?client_id); a client user is pinned to their own org."""
    staff = is_staff(user)
    if client_id is not None and not staff:
        assert_client_access(user, client_id)
    if not staff:
        scope = [user.client_id] if user.client_id else []
    elif client_id is not None:
        scope = [client_id]
    else:
        scope = None
    now = datetime.now(timezone.utc)
    risks = fs.fleet_risks(db, scope, now)
    risks.sort(key=lambda r: (-_SEV.get(r["severity"], 0),
                              r["days"] if r.get("days") is not None else 1e9))
    return {"generated_at": now.isoformat(), "total": len(risks), "risks": risks}
