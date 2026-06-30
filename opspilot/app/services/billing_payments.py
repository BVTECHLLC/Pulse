"""v0.61 Payments & balance tracking.

An invoice's balance is its total minus the sum of recorded `Payment` rows.
Online card payments write a Payment automatically (Stripe webhook); offline
rails (wire, check, Zelle, Cash App, PayPal, cash…) are recorded by staff. When
the balance reaches zero the invoice auto-marks **paid**; partial payments leave
it open with a smaller balance, and the client-facing pay links bill exactly the
remaining balance.

Pure-ish: the math (`amount_paid` / `balance`) is trivially testable, and
`record_payment` is the single place that reconciles an invoice's status.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Invoice, InvoiceStatus, Payment

# Cent tolerance so float rounding never leaves an invoice a penny short of paid.
_EPS = 0.005


def amount_paid(db: Session, invoice_id: int) -> float:
    total = (db.query(func.coalesce(func.sum(Payment.amount), 0.0))
             .filter(Payment.invoice_id == invoice_id).scalar())
    return round(float(total or 0.0), 2)


def balance(invoice: Invoice, paid: float) -> float:
    return round(float(invoice.total or 0.0) - float(paid or 0.0), 2)


def record_payment(db: Session, invoice: Invoice, amount: float, method: str, *,
                   reference: str | None = None, note: str | None = None,
                   user_id: int | None = None,
                   received_at: datetime | None = None) -> dict:
    """Record a payment and reconcile the invoice's status. Commits."""
    amt = round(float(amount), 2)
    pay = Payment(invoice_id=invoice.id, amount=amt, method=method,
                  reference=(reference or None), note=(note or None),
                  received_at=received_at or datetime.now(timezone.utc),
                  created_by_user_id=user_id)
    db.add(pay)
    db.flush()
    paid = amount_paid(db, invoice.id)
    bal = balance(invoice, paid)
    # Auto-reconcile: zero (or over) balance -> paid; a payment on a draft also
    # implicitly "sends" it conceptually, but we only flip to paid here to avoid
    # surprising the draft workflow. A VOID invoice is never auto-flipped.
    if bal <= _EPS and invoice.status != InvoiceStatus.VOID:
        if invoice.status != InvoiceStatus.PAID:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(timezone.utc)
    db.commit()
    return {"payment_id": pay.id, "amount": amt, "method": method,
            "amount_paid": paid, "balance": max(bal, 0.0),
            "status": invoice.status.value, "fully_paid": bal <= _EPS}


def reconcile_from_external(db: Session, invoice: Invoice, amount: float | None,
                           method: str, reference: str | None) -> dict | None:
    """Idempotently record an external (Stripe) payment. If a payment with the
    same provider reference already exists, do nothing (webhooks can retry)."""
    if reference:
        existing = (db.query(Payment)
                    .filter(Payment.invoice_id == invoice.id, Payment.reference == reference)
                    .first())
        if existing:
            return None
    amt = amount if (amount and amount > 0) else balance(invoice, amount_paid(db, invoice.id))
    return record_payment(db, invoice, amt, method, reference=reference)
