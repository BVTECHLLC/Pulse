"""v1.15 PSA Intelligence API — SLA foresight, contract margin, revenue leakage.

Staff-only (it exposes cross-client money + contract economics). Rates are
OWNER-only to change.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import psa_intel

router = APIRouter(prefix="/api/psa", tags=["psa"])


@router.get("/sla-radar")
def sla_radar(horizon_hours: int = 8, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    horizon_hours = max(1, min(72, horizon_hours))
    return psa_intel.sla_radar(db, horizon_hours=horizon_hours)


@router.get("/contract-intel")
def contract_intel(db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return psa_intel.contract_intel(db)


@router.get("/revenue-leakage")
def revenue_leakage(db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return psa_intel.revenue_leakage(db)


@router.get("/rates")
def get_rates(db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return psa_intel.get_rates(db)


class RatesIn(BaseModel):
    bill_rate: float | None = None
    cost_rate: float | None = None


@router.put("/rates")
def put_rates(body: RatesIn, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER))):
    if body.bill_rate is None and body.cost_rate is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide bill_rate and/or cost_rate.")
    return psa_intel.set_rates(db, bill_rate=body.bill_rate, cost_rate=body.cost_rate)
