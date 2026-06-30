"""v0.10 invoicing — turn billable time entries + licenses into invoices.

Staff generate/manage invoices; clients can view their own once sent. Generating
from time marks those entries invoiced so they're never billed twice.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import (
    Client, Invoice, InvoiceLineItem, InvoiceStatus, License, PAYMENT_METHODS,
    Payment, Role, TimeEntry, User,
)
from ...services import ar_aging, audit, billing_payments

router = APIRouter(prefix="/api", tags=["invoices"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _recompute(db: Session, inv: Invoice) -> None:
    lines = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == inv.id).all()
    inv.subtotal = round(sum(li.amount for li in lines), 2)
    inv.tax_amount = round(inv.subtotal * (inv.tax_rate or 0) / 100.0, 2)
    inv.total = round(inv.subtotal + inv.tax_amount, 2)


def _serialize(inv: Invoice, lines: list[InvoiceLineItem] | None = None,
               paid: float | None = None) -> dict:
    d = {
        "id": inv.id, "client_id": inv.client_id, "number": inv.number,
        "status": inv.status.value, "currency": inv.currency,
        "subtotal": inv.subtotal, "tax_rate": inv.tax_rate, "tax_amount": inv.tax_amount,
        "total": inv.total, "notes": inv.notes,
        "period_start": inv.period_start.isoformat() if inv.period_start else None,
        "period_end": inv.period_end.isoformat() if inv.period_end else None,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        "due_at": inv.due_at.isoformat() if inv.due_at else None,
        "created_at": inv.created_at.isoformat(),
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
    }
    if paid is not None:
        d["amount_paid"] = round(paid, 2)
        d["balance"] = round((inv.total or 0.0) - paid, 2)
    if lines is not None:
        d["line_items"] = [
            {"id": li.id, "description": li.description, "quantity": li.quantity,
             "unit_price": li.unit_price, "amount": li.amount, "source": li.source}
            for li in lines
        ]
    return d


class GenerateIn(BaseModel):
    client_id: int
    period_start: datetime | None = None
    period_end: datetime | None = None
    include_time: bool = True
    include_licenses: bool = False
    hourly_rate: float | None = None
    tax_rate: float = 0.0
    due_days: int = 14


@router.post("/invoices/generate", status_code=201)
def generate_invoice(body: GenerateIn, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    now = datetime.now(timezone.utc)
    start = body.period_start or (now - timedelta(days=3650))
    end = body.period_end or (now + timedelta(days=1))

    inv = Invoice(client_id=body.client_id, status=InvoiceStatus.DRAFT, tax_rate=body.tax_rate,
                  period_start=start, period_end=end, issued_at=now,
                  due_at=now + timedelta(days=max(0, body.due_days)),
                  created_by_user_id=user.id)
    db.add(inv)
    db.flush()
    inv.number = f"INV-{inv.id:05d}"

    if body.include_time:
        entries = (db.query(TimeEntry)
                   .filter(TimeEntry.client_id == body.client_id, TimeEntry.billable.is_(True),
                           TimeEntry.invoiced.is_(False),
                           TimeEntry.created_at >= start, TimeEntry.created_at <= end).all())
        total_min = sum(e.minutes for e in entries)
        if total_min > 0:
            if body.hourly_rate is None or body.hourly_rate <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "hourly_rate is required when invoicing billable time")
            hours = round(total_min / 60.0, 2)
            amount = round(hours * body.hourly_rate, 2)
            db.add(InvoiceLineItem(invoice_id=inv.id,
                                   description=f"Professional services ({total_min} min)",
                                   quantity=hours, unit_price=body.hourly_rate, amount=amount,
                                   source="time"))
            for e in entries:
                e.invoiced = True
                e.invoice_id = inv.id

    if body.include_licenses:
        for lic in (db.query(License)
                    .filter(License.client_id == body.client_id, License.monthly_cost.isnot(None)).all()):
            db.add(InvoiceLineItem(invoice_id=inv.id, description=f"{lic.product} (subscription)",
                                   quantity=1, unit_price=lic.monthly_cost, amount=lic.monthly_cost,
                                   source="license"))

    db.flush()  # materialize line items before totals are summed (autoflush is off)
    _recompute(db, inv)
    db.commit()
    audit.record(db, action="invoice.generate", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=body.client_id, ip=_ip(request), detail=f"total={inv.total}")
    return {"id": inv.id, "number": inv.number, "total": inv.total}


@router.get("/invoices")
def list_invoices(client_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = db.query(Invoice)
    if is_staff(user):
        if client_id:
            q = q.filter(Invoice.client_id == client_id)
    else:
        # Clients see only their own, and never drafts.
        q = q.filter(Invoice.client_id == user.client_id, Invoice.status != InvoiceStatus.DRAFT)
    rows = q.order_by(Invoice.created_at.desc()).limit(200).all()
    return [_serialize(i, paid=billing_payments.amount_paid(db, i.id)) for i in rows]


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if not is_staff(user):
        if inv.client_id != user.client_id or inv.status == InvoiceStatus.DRAFT:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    lines = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == inv.id).all()
    return _serialize(inv, lines, paid=billing_payments.amount_paid(db, inv.id))


class PaymentIn(BaseModel):
    amount: float
    method: str = "other"
    reference: str | None = None
    note: str | None = None


@router.get("/invoices/{invoice_id}/payments")
def list_payments(invoice_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if not is_staff(user):
        if inv.client_id != user.client_id or inv.status == InvoiceStatus.DRAFT:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    rows = (db.query(Payment).filter(Payment.invoice_id == inv.id)
            .order_by(Payment.received_at.desc()).all())
    paid = billing_payments.amount_paid(db, inv.id)
    return {"invoice_id": inv.id, "total": inv.total, "amount_paid": round(paid, 2),
            "balance": round((inv.total or 0.0) - paid, 2), "status": inv.status.value,
            "payments": [{"id": p.id, "amount": p.amount, "method": p.method,
                          "reference": p.reference, "note": p.note,
                          "received_at": p.received_at.isoformat()} for p in rows]}


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: int, body: PaymentIn, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.status == InvoiceStatus.VOID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot record a payment on a void invoice")
    if body.amount is None or body.amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "amount must be positive")
    if body.method not in PAYMENT_METHODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"method must be one of {list(PAYMENT_METHODS)}")
    result = billing_payments.record_payment(
        db, inv, body.amount, body.method, reference=body.reference,
        note=body.note, user_id=user.id)
    audit.record(db, action="invoice.payment", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=inv.client_id, ip=_ip(request),
                 detail=f"{body.method} {body.amount} balance={result['balance']}")
    return result


class LineItemIn(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0


@router.post("/invoices/{invoice_id}/line-items", status_code=201)
def add_line_item(invoice_id: int, body: LineItemIn, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.status != InvoiceStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft invoices can be edited")
    li = InvoiceLineItem(invoice_id=inv.id, description=body.description[:300],
                         quantity=body.quantity, unit_price=body.unit_price,
                         amount=round(body.quantity * body.unit_price, 2), source="manual")
    db.add(li)
    db.flush()
    _recompute(db, inv)
    db.commit()
    return {"id": li.id, "invoice_total": inv.total}


@router.post("/invoices/{invoice_id}/remind")
def remind_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Email the client a payment reminder for this invoice now."""
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.status != InvoiceStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a sent invoice can be reminded")
    result = ar_aging.remind_one(db, inv)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("reason") or "Could not send reminder")
    audit.record(db, action="invoice.remind", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=inv.client_id, ip=_ip(request), detail=f"to={result.get('to')}")
    return result


def _transition(db: Session, user: User, request: Request, invoice_id: int,
                to: InvoiceStatus, allowed_from: set[InvoiceStatus]) -> dict:
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.status not in allowed_from:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move a {inv.status.value} invoice to {to.value}")
    inv.status = to
    now = datetime.now(timezone.utc)
    if to == InvoiceStatus.SENT:
        inv.sent_at = now
    if to == InvoiceStatus.PAID:
        inv.paid_at = now
    db.commit()
    audit.record(db, action=f"invoice.{to.value}", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="invoice", target_id=str(inv.id),
                 client_id=inv.client_id, ip=_ip(request))
    return {"id": inv.id, "status": inv.status.value}


@router.post("/invoices/{invoice_id}/send")
def send_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _transition(db, user, request, invoice_id, InvoiceStatus.SENT, {InvoiceStatus.DRAFT})


@router.post("/invoices/{invoice_id}/paid")
def mark_paid(invoice_id: int, request: Request, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _transition(db, user, request, invoice_id, InvoiceStatus.PAID,
                       {InvoiceStatus.SENT, InvoiceStatus.DRAFT})


@router.post("/invoices/{invoice_id}/void")
def void_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER))):
    return _transition(db, user, request, invoice_id, InvoiceStatus.VOID,
                       {InvoiceStatus.DRAFT, InvoiceStatus.SENT})
