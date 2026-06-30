"""v0.58 Recurring billing — turn active contracts into invoices automatically.

For each active contract flagged `auto_invoice`, when its billing period comes
due (deduped via `last_invoiced_at`) we generate a DRAFT invoice with a single
line item for the contract amount. Wired into the run-checks tick, so it runs on
its own; also exposed as a manual "run now". Pure date logic is unit-tested.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Contract, Invoice, InvoiceLineItem, InvoiceStatus

# Minimum gap before a contract can be re-invoiced (dedup guard, slightly under
# the nominal period so a monthly contract bills ~once a month reliably).
_MIN_GAP_DAYS = {"monthly": 27, "quarterly": 88, "annual": 362}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_due(contract: Contract, now: datetime) -> bool:
    """Is this contract due for its next recurring invoice at `now`?"""
    if contract.status != "active" or not getattr(contract, "auto_invoice", False):
        return False
    start = _aware(contract.start_date)
    end = _aware(contract.end_date)
    if start and now < start:
        return False
    if end and now > end:
        return False
    if (contract.amount or 0) <= 0:
        return False
    last = _aware(contract.last_invoiced_at)
    if last is None:
        return True
    gap = _MIN_GAP_DAYS.get(contract.billing_period or "monthly", 27)
    return (now - last) >= timedelta(days=gap)


def generate_due(db: Session, now: datetime | None = None) -> list[dict]:
    """Create invoices for all due auto-invoice contracts. Commits. Returns a
    summary list. Deduped via last_invoiced_at, so it's safe to call every tick."""
    now = now or datetime.now(timezone.utc)
    created = []
    contracts = (db.query(Contract)
                 .filter(Contract.status == "active", Contract.auto_invoice.is_(True)).all())
    for c in contracts:
        if not is_due(c, now):
            continue
        inv = Invoice(client_id=c.client_id, status=InvoiceStatus.DRAFT, tax_rate=0.0,
                      period_start=now, period_end=now, issued_at=now,
                      due_at=now + timedelta(days=15))
        db.add(inv)
        db.flush()
        inv.number = f"INV-{inv.id:05d}"
        amount = round(float(c.amount), 2)
        db.add(InvoiceLineItem(invoice_id=inv.id,
                               description=f"{c.name} ({c.billing_period} service)",
                               quantity=1, unit_price=amount, amount=amount, source="contract"))
        inv.subtotal = amount
        inv.tax_amount = 0.0
        inv.total = amount
        c.last_invoiced_at = now
        db.flush()
        created.append({"invoice_id": inv.id, "number": inv.number,
                        "client_id": c.client_id, "contract": c.name, "total": amount})
    if created:
        db.commit()
    return created
