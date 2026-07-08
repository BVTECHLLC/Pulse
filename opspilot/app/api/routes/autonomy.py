"""v1.17 Autonomy Engine API — the trust ledger, the Self-Driving Report, and
the operator's autonomy controls. Staff-only; threshold/ceiling changes OWNER-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import autonomy

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


@router.get("/report")
def self_driving_report(days: int = 7, db: Session = Depends(get_db),
                        user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return autonomy.report(db, days=days)


@router.get("/ledger")
def trust_ledger(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return autonomy.ledger(db)


@router.get("/memory")
def memory(client_id: int | None = None, action_type: str | None = None,
           playbook: str | None = None, db: Session = Depends(get_db),
           user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return autonomy.playbook_memory(db, client_id=client_id,
                                    action_type=action_type, playbook=playbook)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return autonomy.get_settings(db)


class SettingsIn(BaseModel):
    min_samples: int | None = None
    min_success: float | None = None
    ceilings: dict[str, str] | None = None   # {client_id: "auto"|"supervised"}


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    if body.min_samples is None and body.min_success is None and body.ceilings is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to change.")
    if body.ceilings and any(v not in ("auto", "supervised") for v in body.ceilings.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Ceilings must be 'auto' or 'supervised'.")
    return autonomy.save_settings(db, min_samples=body.min_samples,
                                  min_success=body.min_success, ceilings=body.ceilings)
