"""v1.8 Patch management — staff approve Windows Update installs per device.

The install itself flows through the governed deployment pipeline (approve ->
agent pulls /jobs -> agent installs -> reports /jobs/{id}/result). Only
OWNER/TECH can approve.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Device, Role, User
from ...services import audit, patching

router = APIRouter(prefix="/api/patching", tags=["patching"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


class ApproveIn(BaseModel):
    device_id: int
    kbs: list[str] | None = None   # None/empty = all pending updates
    reason: str | None = None


@router.post("/approve", status_code=201)
def approve(body: ApproveIn, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    dev = db.get(Device, body.device_id)
    if not dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    dep = patching.approve_patches(db, dev, user, kbs=body.kbs, reason=body.reason)
    audit.record(db, action="patching.approve", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="device", target_id=str(dev.id), client_id=dev.client_id,
                 ip=_ip(request), detail=f"job={dep.id} kbs={body.kbs or 'all'}")
    return {"ok": True, "job_id": dep.id, "status": dep.status.value,
            "hint": "The agent installs approved updates on its next check-in "
                    "(within ~5 minutes) and reports the result here."}


@router.get("/jobs")
def jobs(device_id: int, db: Session = Depends(get_db),
         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Device, device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return {"jobs": patching.list_jobs(db, device_id)}


class PolicyIn(BaseModel):
    auto_approve: bool | None = None
    min_severity: str | None = None          # critical | important | all
    only_in_maintenance: bool | None = None


@router.get("/policy")
def get_policy(db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return patching.get_policy(db)


@router.put("/policy")
def save_policy(body: PolicyIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER))):
    out = patching.save_policy(db, auto_approve=body.auto_approve,
                               min_severity=body.min_severity,
                               only_in_maintenance=body.only_in_maintenance)
    audit.record(db, action="patching.policy", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value,
                 target_type="patch_policy", ip=_ip(request),
                 detail=f"auto={out['auto_approve']} sev={out['min_severity']} "
                        f"maint={out['only_in_maintenance']}")
    return out
