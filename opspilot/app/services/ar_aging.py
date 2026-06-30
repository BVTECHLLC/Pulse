"""v0.62 A/R aging + automatic payment reminders.

Outstanding = SENT invoices with a positive balance (total − payments). Each is
bucketed by how long it's been overdue relative to its due date:

    current · 1-30 · 31-60 · 61-90 · 90+

and the dollars roll up per bucket for the classic A/R aging view.

Reminders: once an invoice is past due with a balance, a polite email goes to the
client's billing contact with a link to pay. A 7-day cadence (tracked on
`Invoice.last_reminded_at`) keeps it from nagging every scheduler tick. The mail
sender is injectable so the logic is testable offline, and an undeliverable
attempt (SMTP off) does NOT mark the invoice reminded — so real reminders still
fire once mail is configured.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Client, Invoice, InvoiceStatus, Role, User
from . import billing_payments, email as email_svc

BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")
_REMINDER_GAP_DAYS = 7


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_overdue(inv: Invoice, now: datetime) -> int:
    due = _aware(inv.due_at)
    if not due:
        return 0
    return max(0, (now - due).days)


def bucket_for(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def outstanding(db: Session, client_id: int | None = None) -> list[tuple[Invoice, float]]:
    """(invoice, balance) for every SENT invoice that still owes money."""
    q = db.query(Invoice).filter(Invoice.status == InvoiceStatus.SENT)
    if client_id:
        q = q.filter(Invoice.client_id == client_id)
    out = []
    for inv in q.all():
        bal = billing_payments.balance(inv, billing_payments.amount_paid(db, inv.id))
        if bal > 0.005:
            out.append((inv, round(bal, 2)))
    return out


def aging_report(db: Session, now: datetime | None = None,
                 client_id: int | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    buckets = {b: {"amount": 0.0, "count": 0} for b in BUCKETS}
    invoices = []
    total = 0.0
    for inv, bal in outstanding(db, client_id):
        d = _days_overdue(inv, now)
        b = bucket_for(d)
        buckets[b]["amount"] = round(buckets[b]["amount"] + bal, 2)
        buckets[b]["count"] += 1
        total = round(total + bal, 2)
        invoices.append({"id": inv.id, "number": inv.number, "client_id": inv.client_id,
                         "balance": bal, "days_overdue": d, "bucket": b,
                         "due_at": inv.due_at.isoformat() if inv.due_at else None})
    invoices.sort(key=lambda r: r["days_overdue"], reverse=True)
    overdue_total = round(sum(v["amount"] for k, v in buckets.items() if k != "current"), 2)
    return {"buckets": buckets, "total": total, "overdue_total": overdue_total,
            "count": len(invoices), "invoices": invoices}


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #
def billing_contact(db: Session, client_id: int) -> str | None:
    """Where a client's invoice reminder should go: the Client.email, else the
    first active CLIENT_ADMIN user for that client."""
    client = db.get(Client, client_id)
    if client and client.email:
        return client.email
    admin = (db.query(User)
             .filter(User.client_id == client_id, User.role == Role.CLIENT_ADMIN,
                     User.is_active.is_(True))
             .order_by(User.id.asc()).first())
    return admin.email if admin else None


def compose_reminder(inv: Invoice, balance: float, days_overdue: int,
                     contact_name: str | None = None) -> tuple[str, str]:
    s = get_settings()
    num = inv.number or f"#{inv.id}"
    cur = inv.currency or "USD"
    due = inv.due_at.strftime("%b %d, %Y") if inv.due_at else "—"
    link = f"{s.PUBLIC_BASE_URL.rstrip('/')}/invoice/{inv.id}"
    when = (f"was due on {due} ({days_overdue} day{'s' if days_overdue != 1 else ''} ago)"
            if days_overdue > 0 else f"is due on {due}")
    subject = f"Payment reminder — Invoice {num} ({cur} {balance:,.2f} due)"
    body = (
        f"Hi {contact_name or 'there'},\n\n"
        f"This is a friendly reminder that invoice {num} {when}.\n"
        f"Balance due: {cur} {balance:,.2f}\n\n"
        f"You can view the invoice and pay online here:\n  {link}\n\n"
        "If you've already sent payment, thank you — please disregard this note.\n\n"
        "Thank you,\nBVTech LLC"
    )
    return subject, body


def send_due_reminders(db: Session, now: datetime | None = None, *, sender=None) -> list[dict]:
    """Email a reminder for each overdue, unpaid invoice not reminded in the last
    7 days. Returns the list actually sent. `sender(to, subject, body) -> bool`
    defaults to the real email service; only a True result marks it reminded."""
    now = now or datetime.now(timezone.utc)
    send = sender or email_svc.send
    sent = []
    for inv, bal in outstanding(db):
        due = _aware(inv.due_at)
        if not due or now < due:
            continue   # not overdue yet
        last = _aware(inv.last_reminded_at)
        if last and (now - last) < timedelta(days=_REMINDER_GAP_DAYS):
            continue   # reminded recently
        to = billing_contact(db, inv.client_id)
        if not to:
            continue
        client = db.get(Client, inv.client_id)
        days = _days_overdue(inv, now)
        subject, body = compose_reminder(inv, bal, days,
                                         client.primary_contact if client else None)
        ok = False
        try:
            ok = bool(send(to, subject, body))
        except Exception:  # noqa: BLE001 — email must never break the tick
            ok = False
        if ok:
            inv.last_reminded_at = now
            inv.reminder_count = (inv.reminder_count or 0) + 1
            db.commit()
            sent.append({"invoice_id": inv.id, "number": inv.number, "to": to,
                         "balance": bal, "days_overdue": days})
    return sent


def remind_one(db: Session, inv: Invoice, now: datetime | None = None, *, sender=None) -> dict:
    """Send a single reminder now (manual 'Remind' button). Marks reminded on
    success regardless of cadence."""
    now = now or datetime.now(timezone.utc)
    send = sender or email_svc.send
    bal = billing_payments.balance(inv, billing_payments.amount_paid(db, inv.id))
    if bal <= 0.005:
        return {"ok": False, "reason": "Invoice has no outstanding balance."}
    to = billing_contact(db, inv.client_id)
    if not to:
        return {"ok": False, "reason": "No billing contact email for this client."}
    client = db.get(Client, inv.client_id)
    days = _days_overdue(inv, now)
    subject, body = compose_reminder(inv, bal, days,
                                     client.primary_contact if client else None)
    ok = bool(send(to, subject, body))
    if ok:
        inv.last_reminded_at = now
        inv.reminder_count = (inv.reminder_count or 0) + 1
        db.commit()
    return {"ok": ok, "to": to, "balance": round(bal, 2), "days_overdue": days,
            "delivered": ok}
