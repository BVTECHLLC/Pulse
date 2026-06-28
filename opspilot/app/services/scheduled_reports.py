"""v0.20 scheduled client reports. The run-checks tick calls send_due() which
emails a brief branded snapshot to each enabled schedule whose cadence is due.
Email delivery is a safe no-op (logged) until SMTP is configured."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import (
    Alert, AlertStatus, Client, Device, ReportSchedule, SupportTicket,
    TicketStatus,
)
from . import email as email_svc

_PERIOD = {"weekly": timedelta(days=7), "monthly": timedelta(days=30),
           "quarterly": timedelta(days=90)}


def _is_due(sched: ReportSchedule, now: datetime) -> bool:
    if not sched.enabled:
        return False
    if sched.last_sent_at is None:
        return True
    period = _PERIOD.get(sched.cadence, _PERIOD["monthly"])
    last = sched.last_sent_at
    if last.tzinfo is None:                 # normalize naive (SQLite) timestamps
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= period


def _summary_text(db: Session, client: Client, now: datetime) -> str:
    devices = db.query(Device).filter(Device.client_id == client.id).all()
    healths = [d.health_score for d in devices if d.health_score is not None]
    avg_health = round(sum(healths) / len(healths)) if healths else "n/a"
    open_alerts = (db.query(Alert)
                   .filter(Alert.client_id == client.id,
                           Alert.status != AlertStatus.RESOLVED).count())
    open_tickets = (db.query(SupportTicket)
                    .filter(SupportTicket.client_id == client.id,
                            SupportTicket.status.in_([TicketStatus.OPEN,
                                                      TicketStatus.IN_PROGRESS])).count())
    pending_patches = sum((d.patches_pending or 0) for d in devices)
    s = get_settings()
    return (
        f"{s.APP_NAME} — service report for {client.name}\n"
        f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"{'-' * 48}\n"
        f"Devices monitored : {len(devices)}\n"
        f"Average health    : {avg_health}\n"
        f"Open alerts       : {open_alerts}\n"
        f"Open tickets      : {open_tickets}\n"
        f"Pending patches   : {pending_patches}\n"
        f"{'-' * 48}\n"
        f"View the full interactive report at {s.PUBLIC_BASE_URL}/report/{client.id}\n"
    )


def send_due(db: Session, now: datetime | None = None) -> dict:
    """Email every due schedule. Returns counts. Safe to call every tick."""
    now = now or datetime.now(timezone.utc)
    schedules = db.query(ReportSchedule).filter(ReportSchedule.enabled.is_(True)).all()
    sent = 0
    for sched in schedules:
        if not _is_due(sched, now):
            continue
        client = db.get(Client, sched.client_id)
        if not client:
            continue
        subject = f"{get_settings().APP_NAME} report — {client.name}"
        email_svc.send(sched.recipient_email, subject, _summary_text(db, client, now))
        sched.last_sent_at = now
        sent += 1
    if sent:
        db.commit()
    return {"schedules": len(schedules), "reports_sent": sent}
