"""v0.14 recurring service contracts. Active contracts contribute to MRR
(normalized to a monthly figure) in the billing rollup. Staff manage; clients
read their own."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, is_staff, require_roles
from ...models import Client, Contract, Role, User
from ...services import audit

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

_PERIOD_TO_MONTHLY = {"monthly": 1.0, "quarterly": 1 / 3.0, "annual": 1 / 12.0}


def monthly_value(c: Contract) -> float:
    """Normalize a contract's per-period amount to a monthly figure for MRR."""
    return (c.amount or 0.0) * _PERIOD_TO_MONTHLY.get(c.billing_period, 1.0)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _serialize(c: Contract) -> dict:
    return {
        "id": c.id, "client_id": c.client_id, "name": c.name, "amount": c.amount,
        "billing_period": c.billing_period, "status": c.status,
        "monthly_value": round(monthly_value(c), 2),
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "notes": c.notes,
        "auto_invoice": bool(getattr(c, "auto_invoice", False)),
        "last_invoiced_at": c.last_invoiced_at.isoformat() if getattr(c, "last_invoiced_at", None) else None,
    }


class ContractIn(BaseModel):
    client_id: int
    name: str
    amount: float
    billing_period: str = "monthly"
    start_date: datetime | None = None
    end_date: datetime | None = None
    notes: str | None = None
    auto_invoice: bool = False


@router.get("")
def list_contracts(client_id: int | None = None, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    q = db.query(Contract)
    if is_staff(user):
        if client_id:
            q = q.filter(Contract.client_id == client_id)
    else:
        q = q.filter(Contract.client_id == user.client_id)
    return [_serialize(c) for c in q.order_by(Contract.status, Contract.name).all()]


@router.post("", status_code=201)
def create_contract(body: ContractIn, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    if body.billing_period not in _PERIOD_TO_MONTHLY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"billing_period must be one of {list(_PERIOD_TO_MONTHLY)}")
    c = Contract(client_id=body.client_id, name=body.name[:200], amount=body.amount,
                 billing_period=body.billing_period, start_date=body.start_date,
                 end_date=body.end_date, notes=body.notes, auto_invoice=bool(body.auto_invoice))
    db.add(c)
    db.commit()
    audit.record(db, action="contract.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="contract", target_id=str(c.id),
                 client_id=body.client_id, ip=_ip(request),
                 detail=f"{body.name} {body.amount}/{body.billing_period}")
    return {"id": c.id}


class ContractUpdate(BaseModel):
    status: str | None = None
    amount: float | None = None
    notes: str | None = None
    auto_invoice: bool | None = None


@router.post("/run-recurring")
def run_recurring(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER))):
    """Generate invoices now for any due auto-invoice contracts (also runs on the
    scheduler tick)."""
    from ...services import recurring_billing
    created = recurring_billing.generate_due(db)
    audit.record(db, action="contract.run_recurring", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="billing", ip=_ip(request),
                 detail=f"invoices_created={len(created)}")
    return {"ok": True, "created": created}


@router.patch("/{contract_id}")
def update_contract(contract_id: int, body: ContractUpdate, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    c = db.get(Contract, contract_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    if body.status is not None:
        if body.status not in ("active", "paused", "expired"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
        c.status = body.status
    if body.amount is not None:
        c.amount = body.amount
    if body.notes is not None:
        c.notes = body.notes
    if body.auto_invoice is not None:
        c.auto_invoice = body.auto_invoice
    db.commit()
    audit.record(db, action="contract.update", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="contract", target_id=str(c.id),
                 client_id=c.client_id, ip=_ip(request), detail=f"status={c.status}")
    return _serialize(c)
