"""v1.1 heartbeat — the master maintenance tick, callable from anywhere.

This is the body of what used to live only inside POST /api/automation/run-checks.
Extracting it lets THREE callers share one implementation:
  * the Autopilot background scheduler (scheduler.py) — no external cron needed
  * the /api/automation/run-checks endpoint — staff "run now"
  * tests — deterministic, offline

Every sub-task is best-effort: one failing integration never blocks the rest
(a dead SMTP config shouldn't stop SLA breach detection).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import SupportTicket, TicketStatus
from . import monitoring, sla


def run_all(db: Session, now: datetime | None = None) -> dict:
    """Run every recurring check/automation once. Idempotent by design — each
    sub-service dedupes its own sends (weekly digest per ISO week, SLA breach
    via sla_breach_alerted, reports via their own schedule bookkeeping...), so
    calling this as often as every couple of minutes is safe."""
    from . import automation as automation_svc  # local import: avoid cycles
    now = now or datetime.now(timezone.utc)

    # 1) Offline sweep -> alert.opened automations + auto-remediation.
    sweep, new_offline = monitoring.sweep_offline(db)
    from . import auto_remediation
    from ..models import Device
    for alert in new_offline:
        dev = db.get(Device, alert.device_id)
        automation_svc.dispatch(db, "alert.opened",
                                automation_svc.build_alert_context(alert, dev))
        try:
            auto_remediation.on_alert(db, alert, dev)   # detect → fix
        except Exception:  # noqa: BLE001
            pass

    # 2) SLA breach detection + built-in escalation (deduped per ticket).
    from . import sla_escalation
    open_tickets = (db.query(SupportTicket)
                    .filter(SupportTicket.status.in_([TicketStatus.OPEN,
                                                      TicketStatus.IN_PROGRESS]))
                    .all())
    sla_fired = 0
    escalated = 0
    for t in open_tickets:
        s = sla.evaluate(t, now)
        if s["breached"] and not t.sla_breach_alerted:
            t.sla_breach_alerted = True
            esc = sla_escalation.escalate(db, t, now)
            if esc["priority_bumped"]:
                escalated += 1
            db.commit()   # persist flag + escalation before custom rules dispatch
            ctx = automation_svc.build_ticket_context(t)
            ctx["breach"] = True
            automation_svc.dispatch(db, "ticket.sla_breached", ctx)
            sla_fired += 1

    # 3) Due time-based automation rules (v0.53).
    scheduled = automation_svc.run_scheduled(db, now)

    # 4) Recurring billing (v0.58).
    from . import recurring_billing
    recurring = []
    try:
        recurring = recurring_billing.generate_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 5) A/R payment reminders (v0.62).
    from . import ar_aging
    reminders = []
    try:
        reminders = ar_aging.send_due_reminders(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 6) Posture snapshots + grade-slip alerts (v0.67).
    from . import posture_history
    snapshots = []
    try:
        snapshots = posture_history.snapshot_all(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 7) Auto-posting (v0.70).
    from . import autopost
    posts = []
    try:
        posts = autopost.publish_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 8) Weekly "State of the Practice" digest (v0.85).
    from . import weekly_digest
    digest = {"sent": False}
    try:
        digest = weekly_digest.maybe_send(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 9) Due scheduled client reports (v0.20).
    from . import scheduled_reports
    reports = {"reports_sent": 0}
    try:
        reports = scheduled_reports.send_due(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 10) Connector health watchdog (v0.52.2) — at most hourly.
    from . import integration_health
    health = None
    try:
        health = integration_health.maybe_sweep(db, min_interval_minutes=60)
    except Exception:  # noqa: BLE001
        pass

    # 11) AI ticket triage (v1.1) — Claude reads new tickets, suggests priority/
    #     summary/next step. No-op when AI is off or every ticket is triaged.
    from . import ai_triage
    triaged = []
    try:
        triaged = ai_triage.sweep(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 12) Academy streak-saver emails (v1.3) — afternoon nudge for streaks that
    #     die at midnight; once per user per day.
    from . import academy
    streaks_saved = []
    try:
        streaks_saved = academy.streak_reminders(db, now)
    except Exception:  # noqa: BLE001
        pass

    # 13) Academy AI question refresh (v1.3) — monthly, only when Claude is
    #     connected; cheap month-key check otherwise.
    academy_ai = {"refreshed": False}
    try:
        academy_ai = academy.ai_refresh(db, now)
    except Exception:  # noqa: BLE001
        pass

    return {"offline": sweep, "sla_breaches_fired": sla_fired, "escalated": escalated,
            "reports": reports, "health_checked": (health or {}).get("checked", 0),
            "scheduled_fired": len(scheduled), "recurring_invoices": len(recurring),
            "reminders_sent": len(reminders), "posture_snapshots": len(snapshots),
            "posts_published": len([p for p in posts if p.get("ok")]),
            "weekly_digest": digest, "ai_triaged": len(triaged),
            "streak_reminders": len(streaks_saved), "academy_ai": academy_ai}
