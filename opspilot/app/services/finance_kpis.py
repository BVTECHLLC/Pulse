"""v0.63 Finance KPIs — the owner's money cockpit in one call.

Pulls the revenue picture together from the payment ledger + A/R aging:
  * collected this month / last 30 days / all time
  * outstanding and overdue A/R (from ar_aging)
  * payment-method mix (how clients actually pay)
  * the most recent payments

Pure read-only aggregation; safe to call as often as the dashboard refreshes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Client, Invoice, InvoiceStatus, Payment
from . import ar_aging


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def summary(db: Session, now: datetime | None = None, recent: int = 8) -> dict:
    now = now or datetime.now(timezone.utc)
    month_start = _month_start(now)
    last30 = now - timedelta(days=30)

    def _collected(since: datetime | None) -> float:
        q = db.query(func.coalesce(func.sum(Payment.amount), 0.0))
        if since is not None:
            q = q.filter(Payment.received_at >= since)
        return round(float(q.scalar() or 0.0), 2)

    # Payment-method mix (all time).
    mix_rows = (db.query(Payment.method, func.coalesce(func.sum(Payment.amount), 0.0),
                         func.count(Payment.id))
                .group_by(Payment.method).all())
    method_mix = sorted(
        [{"method": m, "amount": round(float(amt or 0), 2), "count": int(cnt)}
         for m, amt, cnt in mix_rows],
        key=lambda r: r["amount"], reverse=True)

    aging = ar_aging.aging_report(db, now)

    # Recent payments, newest first, with the client name for context.
    names = {c.id: c.name for c in db.query(Client).all()}
    inv_client = dict(db.query(Invoice.id, Invoice.client_id).all())
    recent_rows = (db.query(Payment).order_by(Payment.received_at.desc())
                   .limit(max(1, min(recent, 50))).all())
    recent_payments = [{
        "id": p.id, "invoice_id": p.invoice_id, "amount": p.amount, "method": p.method,
        "client": names.get(inv_client.get(p.invoice_id)),
        "received_at": p.received_at.isoformat() if p.received_at else None,
    } for p in recent_rows]

    # Counts that round out the picture.
    open_count = (db.query(func.count(Invoice.id))
                  .filter(Invoice.status == InvoiceStatus.SENT).scalar())

    return {
        "collected_month": _collected(month_start),
        "collected_30d": _collected(last30),
        "collected_total": _collected(None),
        "outstanding": aging["total"],
        "overdue": aging["overdue_total"],
        "open_invoices": int(open_count or 0),
        "aging_buckets": aging["buckets"],
        "method_mix": method_mix,
        "recent_payments": recent_payments,
    }
