"""v0.38 SLA escalation — when a ticket breaches its SLA, don't just flag it: act.

The run-checks tick already detects a *newly* breached ticket (de-duped via
`sla_breach_alerted`). This service turns that detection into concrete, in-app
escalation so a breach can't quietly rot:

  1. **Bump priority** one level (low → normal → high → urgent), capped — for
     routing/visibility. We deliberately do NOT re-stamp SLA targets (that would
     reset the clock and hide the breach); the ticket stays breached.
  2. **Post an internal note** documenting the breach + what was escalated.
  3. **Raise a notification** (in-app + fan-out to channels) so a human sees it.

Pure in-platform actions — nothing leaves the box except notification channels
the user configured.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Notification, PRIORITIES, SupportTicket, TicketComment
from . import sla


def _next_priority(current: str) -> str:
    try:
        i = PRIORITIES.index(current)
    except ValueError:
        return "high"
    return PRIORITIES[min(i + 1, len(PRIORITIES) - 1)]


def escalate(db: Session, ticket: SupportTicket, now: datetime | None = None,
             bump_priority: bool = True) -> dict:
    """Apply built-in escalation to a breached ticket. Adds to the session but
    does NOT commit (the caller controls the transaction). Returns a summary."""
    now = now or datetime.now(timezone.utc)
    s = sla.evaluate(ticket, now)
    which = "Resolution" if s.get("resolution_breached") else "Response"

    old_pri = ticket.priority
    new_pri = old_pri
    if bump_priority:
        new_pri = _next_priority(old_pri)
        ticket.priority = new_pri   # intentional: do NOT re-stamp SLA (stay breached)

    bumped = new_pri != old_pri
    note = (f"⚠️ SLA breached — auto-escalated. {which} target passed."
            + (f" Priority raised {old_pri} → {new_pri}." if bumped else
               f" Already at top priority ({old_pri})."))
    db.add(TicketComment(ticket_id=ticket.id, author_email="sla-escalation@system",
                         author_role="system", body=note, internal=True))

    msg = (f"SLA BREACH — ticket #{ticket.id}: {ticket.subject} "
           f"({which.lower()} overdue)" + (f", escalated to {new_pri}" if bumped else ""))
    db.add(Notification(client_id=ticket.client_id, kind="sla_escalation",
                        severity="critical", message=msg[:1000]))
    # Best-effort fan-out to configured channels (email/Slack/Teams/webhook).
    sent = 0
    try:
        from . import notifications as notif_svc
        sent = notif_svc.fanout(db, message=msg, severity="critical",
                                client_id=ticket.client_id)
    except Exception:  # noqa: BLE001 — escalation must never crash the tick
        pass

    return {"ticket_id": ticket.id, "which": which.lower(), "priority_bumped": bumped,
            "old_priority": old_pri, "new_priority": new_pri, "channels_notified": sent}
