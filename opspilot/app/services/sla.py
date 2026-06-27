"""SLA engine: resolve per-priority response/resolution targets and compute
breach state for a ticket.

Resolution order for a target: a per-client SLAPolicy row > a global (client_id
NULL) row > the built-in defaults below. Targets are in minutes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import SLAPolicy, SupportTicket

# Built-in defaults (minutes): response, resolution — sane MSP starting points.
DEFAULT_TARGETS: dict[str, tuple[int, int]] = {
    "urgent": (30, 240),     # 30 min / 4 h
    "high":   (60, 480),     # 1 h  / 8 h
    "normal": (240, 1440),   # 4 h  / 24 h
    "low":    (480, 2880),   # 8 h  / 48 h
}


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; normalize to UTC-aware for math."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_targets(db: Session, client_id: int, priority: str) -> tuple[int, int]:
    """Return (response_minutes, resolution_minutes) for a client+priority."""
    row = (db.query(SLAPolicy)
           .filter(SLAPolicy.client_id == client_id, SLAPolicy.priority == priority)
           .first())
    if not row:
        row = (db.query(SLAPolicy)
               .filter(SLAPolicy.client_id.is_(None), SLAPolicy.priority == priority)
               .first())
    if row:
        return row.response_minutes, row.resolution_minutes
    return DEFAULT_TARGETS.get(priority, DEFAULT_TARGETS["normal"])


def stamp_due_dates(db: Session, ticket: SupportTicket) -> None:
    """Set first_response_due_at / resolution_due_at from the effective policy.
    Call on create and whenever priority changes. Does not commit."""
    resp_min, res_min = resolve_targets(db, ticket.client_id, ticket.priority)
    base = _aware(ticket.created_at) or datetime.now(timezone.utc)
    ticket.first_response_due_at = base + timedelta(minutes=resp_min)
    ticket.resolution_due_at = base + timedelta(minutes=res_min)


def evaluate(ticket: SupportTicket, now: datetime | None = None) -> dict:
    """Compute live SLA state for a ticket (pure; no DB)."""
    now = now or datetime.now(timezone.utc)
    is_closed = ticket.status is not None and ticket.status.value in ("resolved", "closed")

    resp_due = _aware(ticket.first_response_due_at)
    res_due = _aware(ticket.resolution_due_at)
    responded = ticket.first_responded_at is not None

    # Response SLA breaches only while still awaiting the first reply.
    response_breached = bool(resp_due and not responded and not is_closed and now > resp_due)
    # Resolution SLA breaches only while still unresolved.
    resolution_breached = bool(res_due and not is_closed and now > res_due)

    def _mins_left(due):
        return int((due - now).total_seconds() // 60) if due else None

    return {
        "first_response_due_at": resp_due.isoformat() if resp_due else None,
        "resolution_due_at": res_due.isoformat() if res_due else None,
        "responded": responded,
        "response_breached": response_breached,
        "resolution_breached": resolution_breached,
        # Negative => overdue by N minutes; used by the UI to flag "at risk".
        "response_minutes_left": None if responded or is_closed else _mins_left(resp_due),
        "resolution_minutes_left": None if is_closed else _mins_left(res_due),
        "breached": response_breached or resolution_breached,
    }
